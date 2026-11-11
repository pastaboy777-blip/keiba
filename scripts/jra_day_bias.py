"""研究: 当日のそれより前のレースの決まり方(前残り/差し、内/外)で、次のレースの赤丸の当たり方は変わるか。

    python3 scripts/jra_day_bias.py --data data/jra/races.jsonl

当日の傾向 = 同じ日・同じ場・同じ芝ダで、それより前に終わったレース(2鞍以上)の1〜3着の
   前残り度 … 4角の位置(0=先頭〜1=最後方)の平均
   内外     … 4角で横並びだった時の組の中の位置(0=最内〜1=外)の平均
これを三等分(前/中/後、内/中/外)し、今回の鞍を展開図と同じ作りで想定して
   「想定の前4割の内寄り」「想定の前4割の外寄り」「想定の後ろ半分」の3着内率を比べる(鞍平均比)。
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


def groups(s):
    out = {}
    for m in re.finditer(r"\(([^)]*)\)|(\d+)", (s or "").replace("*", "")):
        if m.group(1) is not None:
            g = [int(x) for x in re.findall(r"\d+", m.group(1))]
            for i, u in enumerate(g):
                out[u] = (i + 1, len(g))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/jra/races.jsonl")
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    rows = [d for d in rows if d.get("surface") in ("芝", "ダ")]
    rows.sort(key=lambda d: (d["date"], d["race_id"]))
    cut = rows[len(rows) // 2]["date"]
    jk = Path("/tmp/claude-0/-home-user-keiba/c5bae7ed-eac5-5fc6-be17-700f927018b6/scratchpad/jk_day_cut.json")
    subprocess.run([sys.executable, str(Path(__file__).parent / "jra_jockey.py"), "--data", a.data,
                    "--before", cut, "--out", str(jk)], check=True, capture_output=True)
    Z.JOCKEY_STATS, Z._JK = jk, None

    # レースごとの「決まり方」(結果)
    shape = {}
    for d in rows:
        n = d["field_size"]
        G = groups(d["corners"].get("4") or d["corners"].get("3"))
        top = [x for x in d["result"][:3] if x.get("corner_pos")]
        if len(top) == 3 and n > 1:
            fr = st.mean((x["corner_pos"][-1] - 1) / (n - 1) for x in top)
            lat = [(G[x["umaban"]][0] - 1) / (G[x["umaban"]][1] - 1) for x in top if x["umaban"] in G and G[x["umaban"]][1] >= 2]
            shape[d["race_id"]] = (fr, st.mean(lat) if lat else None)
    day = collections.defaultdict(list)
    for d in rows:
        day[(d["date"], d["place"], d["surface"])].append(d["race_id"])

    hist: dict = {}
    recs = []
    for d in rows:
        n = d["field_size"]
        past = {x["umaban"]: {"name": x["horse_name"], "runs": sorted(hist.get(x["horse_id"], []),
                                                                     key=lambda r: r["date"], reverse=True)[:5]}
                for x in d["result"]}
        prev = [shape[r] for r in day[(d["date"], d["place"], d["surface"])] if r < d["race_id"] and r in shape]
        known = sum(1 for p in past.values() if any(r["corner"] for r in p["runs"])) / max(1, n)
        if d["date"] >= cut and len(prev) >= 2 and known >= 0.7 and n >= 8:
            waku = {x["umaban"]: x.get("waku") or Z.waku_of(x["umaban"], n) for x in d["result"]}
            jks = {x["umaban"]: x.get("jockey") for x in d["result"]}
            try:
                fc, rws, rk = Z.build(past, waku, place=d["place"], dist=d["distance"], surface=d["surface"],
                                      baba=d.get("baba"), jockeys=jks)
                Z.lateral_layout(rws, fc, n, key="pos", band=0.07)
                pr = sorted([r for r in rws if r.get("pos") is not None and "outer_score" in r], key=lambda r: -r["pos"])
            except Exception:  # noqa: BLE001
                pr = []
            if len(pr) >= 6:
                res = {x["umaban"]: x["finish_pos"] <= 3 for x in d["result"]}
                front = pr[: round(len(pr) * 0.4)]
                med = st.median(r["outer_score"] for r in front)
                lats = [p[1] for p in prev if p[1] is not None]
                recs.append({
                    "day_front": st.mean(p[0] for p in prev), "day_lat": st.mean(lats) if lats else None,
                    "base": st.mean(res.get(r["ub"], False) for r in pr),
                    "前×内": [res.get(r["ub"], False) for r in front if r["outer_score"] <= med],
                    "前×外": [res.get(r["ub"], False) for r in front if r["outer_score"] > med],
                    "後ろ半分": [res.get(r["ub"], False) for r in pr[len(pr) // 2:]],
                })
        for x in d["result"]:
            hist.setdefault(x["horse_id"], []).append({
                "date": d["date"], "place": d["place"], "surface": d.get("surface"), "dist": d["distance"],
                "time": x.get("time"), "n": n, "fin": x["finish_pos"], "corner": x.get("corner_pos") or [],
                "agari": x.get("agari"), "baba": d.get("baba")})

    print(f"検証(境 {cut} 以降)で当日の前のレースが2鞍以上ある鞍: {len(recs)}")
    for key, labs in (("day_front", ("前残りの日", "中くらい", "差しの日")), ("day_lat", ("内が来る日", "中くらい", "外が来る日"))):
        g = [r for r in recs if r[key] is not None]
        v = sorted(r[key] for r in g)
        q = (v[len(v) // 3], v[2 * len(v) // 3])
        print(f"\n== 当日の傾向: {'前残りか差しか' if key == 'day_front' else '内か外か'} ==")
        for i, lab in enumerate(labs):
            gg = [r for r in g if (r[key] <= q[0]) if i == 0] if i == 0 else \
                 [r for r in g if q[0] < r[key] <= q[1]] if i == 1 else [r for r in g if r[key] > q[1]]
            b = st.mean(r["base"] for r in gg)
            cells = []
            for z in ("前×内", "前×外", "後ろ半分"):
                xs = [x for r in gg for x in r[z]]
                cells.append(f"{z} {st.mean(xs):5.1%}(×{st.mean(xs) / b:.2f})")
            print(f"  {lab:<8s} {len(gg):4d}鞍  " + "  ".join(cells))


if __name__ == "__main__":
    main()
