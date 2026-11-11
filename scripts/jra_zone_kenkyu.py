"""研究: 赤丸(狙う帯)を「レース前の想定」で選んだとき、どの帯がいちばん来るか。想定ペースごとに学習する。

    python3 scripts/jra_zone_kenkyu.py --data data/jra/races.jsonl

各鞍を展開図と同じ作り(jra_tenkai_zu.build: 学習済みの4角位置モデル・ハナモデル、内外は馬番+騎手)で想定し、
  前後の幅 … 想定4角位置の前 30% / 40% / 50%
  内外     … その中で外度(outer_score)が中央値以下=内 / 以上=外 / 両方
の9通りを、想定ペース(S/M/H)ごとに比べる。指標は帯の馬の3着内率・鞍平均比(lift)・穴(7番人気以下)の3着内率。
前半(学習)で各ペースの最良の帯を決め、後半(検証)で確かめる。騎手の集計は境より前だけで作ったものを使う。
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import statistics as st
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import jra_tenkai_zu as Z  # noqa: E402
from jra_pace_model import PaceModel  # noqa: E402
from nankeiba.scraping.db_race import pace_of  # noqa: E402

FRONTS = (0.3, 0.4, 0.5)
SIDES = ("内", "外", "両方")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/jra/races.jsonl")
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    rows = [d for d in rows if d.get("surface") in ("芝", "ダ")]
    rows.sort(key=lambda d: (d["date"], d["race_id"]))
    lap_ok = [d for d in rows if pace_of(d.get("lap") or [], d["distance"])]
    cut = lap_ok[len(lap_ok) // 2]["date"]
    # 騎手の集計は境より前だけ
    jk = Path("/tmp/claude-0/-home-user-keiba/c5bae7ed-eac5-5fc6-be17-700f927018b6/scratchpad/jk_zone_cut.json")
    subprocess.run([sys.executable, str(Path(__file__).parent / "jra_jockey.py"), "--data", a.data,
                    "--before", cut, "--out", str(jk)], check=True, capture_output=True)
    Z.JOCKEY_STATS, Z._JK = jk, None
    pm = PaceModel().fit([d for d in lap_ok if d["date"] < cut])
    v = sorted(pace_of(d["lap"], d["distance"])["diff"] for d in lap_ok if d["date"] < cut)
    q = (v[len(v) // 3], v[2 * len(v) // 3])

    hist: dict = {}
    R = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0, 0, 0, 0]))  # [頭数,3着内,穴頭数,穴3着内,鞍数]
    base = collections.defaultdict(lambda: [0, 0])
    for d in rows:
        n = d["field_size"]
        past = {x["umaban"]: {"name": x["horse_name"], "runs": sorted(hist.get(x["horse_id"], []),
                                                                     key=lambda r: r["date"], reverse=True)[:5]}
                for x in d["result"]}
        known = sum(1 for p in past.values() if any(r["corner"] for r in p["runs"])) / max(1, n)
        if known >= 0.7 and n >= 8 and pace_of(d.get("lap") or [], d["distance"]):
            waku = {x["umaban"]: x.get("waku") or Z.waku_of(x["umaban"], n) for x in d["result"]}
            jks = {x["umaban"]: x.get("jockey") for x in d["result"]}
            try:
                fc, rws, rk = Z.build(past, waku, place=d["place"], dist=d["distance"], surface=d["surface"],
                                      baba=d.get("baba"), jockeys=jks)
                Z.lateral_layout(rws, fc, n, key="pos", band=0.07)
            except Exception:  # noqa: BLE001
                rws = []
            pr = [r for r in rws if r.get("pos") is not None and "outer_score" in r]
            if len(pr) >= 6:
                diff = pm.predict(d)
                pace = "H" if diff < q[0] else ("S" if diff > q[1] else "M")
                half = "学習" if d["date"] < cut else "検証"
                res = {x["umaban"]: x for x in d["result"]}
                pr.sort(key=lambda r: -r["pos"])
                b = base[(half, pace)]
                b[0] += len(pr)
                b[1] += sum(res[r["ub"]]["finish_pos"] <= 3 for r in pr if r["ub"] in res)
                for fr in FRONTS:
                    front = pr[: max(1, round(len(pr) * fr))]
                    med = st.median(r["outer_score"] for r in front)
                    for side in SIDES:
                        sel = [r for r in front if side == "両方" or (side == "内" and r["outer_score"] <= med)
                               or (side == "外" and r["outer_score"] > med)]
                        c = R[(half, pace)][(fr, side)]
                        c[4] += 1
                        for r in sel:
                            x = res.get(r["ub"])
                            if not x:
                                continue
                            c[0] += 1
                            c[1] += x["finish_pos"] <= 3
                            if (x.get("popularity") or 0) >= 7:
                                c[2] += 1
                                c[3] += x["finish_pos"] <= 3
        for x in d["result"]:
            hist.setdefault(x["horse_id"], []).append({
                "date": d["date"], "place": d["place"], "surface": d.get("surface"), "dist": d["distance"],
                "time": x.get("time"), "n": n, "fin": x["finish_pos"], "corner": x.get("corner_pos") or [],
                "agari": x.get("agari"), "baba": d.get("baba")})

    print(f"境 {cut}(前半=学習で帯を選び、後半=検証で確かめる)  ペース区分の境 {q[0]:+.2f} / {q[1]:+.2f}")
    best = {}
    for pace, lab in (("S", "スロー想定"), ("M", "平均想定"), ("H", "ハイ想定")):
        for half in ("学習", "検証"):
            b = base[(half, pace)]
            br = b[1] / max(1, b[0])
            print(f"\n【{lab}・{half}】 鞍数 {R[(half, pace)][(0.4, '両方')][4]}  全馬の3着内率 {br:.1%}")
            print("  帯               頭数/鞍  3着内率  鞍平均比  穴の3着内率(頭数)")
            scored = []
            for (fr, side), c in sorted(R[(half, pace)].items()):
                if not c[0]:
                    continue
                rate = c[1] / c[0]
                scored.append(((fr, side), rate / br if br else 0))
                mark = " ←学習で最良" if half == "検証" and best.get(pace) == (fr, side) else ""
                print(f"  前{int(fr * 100)}%×{side:<3s}  {c[0] / c[4]:5.1f}   {rate:6.1%}   ×{rate / br:4.2f}   "
                      f"{c[3] / max(1, c[2]):6.1%}({c[2]}){mark}")
            if half == "学習":
                # 帯の頭数が少なすぎないもの(1鞍あたり2頭以上)から、鞍平均比が最大の帯
                ok = [s for s in scored if R[(half, pace)][s[0]][0] / R[(half, pace)][s[0]][4] >= 2]
                best[pace] = max(ok, key=lambda s: s[1])[0] if ok else None
    json.dump({p: list(b) for p, b in best.items() if b}, open(Path(__file__).resolve().parents[1] / "models" / "zone_rule.json", "w"),
              ensure_ascii=False)
    print("\n学習で選んだ帯:", {p: f"前{int(b[0] * 100)}%×{b[1]}" for p, b in best.items() if b})


if __name__ == "__main__":
    main()
