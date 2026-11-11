"""3年分を自分で展開・隊列予想して、結果と照らし合わせる(1鞍ずつ記録 → 外れやすい条件を洗い出す)。

    python3 scripts/jra_yosou_3nen.py --data data/jra/races.jsonl --out data/jra/yosou_3nen.jsonl

各鞍を日付順に、その日より前の情報だけで展開図と同じ作り(jra_tenkai_zu.build)で予想し、
  ペース(S/M/H)・4角の並び(順位相関)・前1/3の一致・ハナ(上位1頭/3頭)
を結果と比べて JSONL に書く。ペースモデルと騎手の集計は前半だけで作り、条件別の集計は後半(検証)で出す。
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

import jra_learn as J  # noqa: E402
import jra_tenkai_zu as Z  # noqa: E402
from jra_pace_model import PaceModel  # noqa: E402
from nankeiba.scraping.db_race import pace_of  # noqa: E402


def klass_of(d):
    c = d.get("race_class") or ""
    nm = d.get("name") or ""
    for k in ("新馬", "未勝利", "1勝", "2勝", "3勝", "オープン"):
        if c.startswith(k) or k in nm:
            return k
    return "不明"


def predict_all(path, out_path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    rows = [d for d in rows if d.get("surface") in ("芝", "ダ")]
    rows.sort(key=lambda d: (d["date"], d["race_id"]))
    lap_ok = [d for d in rows if pace_of(d.get("lap") or [], d["distance"])]
    cut = lap_ok[len(lap_ok) // 2]["date"]
    jk = Path("/tmp/claude-0/-home-user-keiba/c5bae7ed-eac5-5fc6-be17-700f927018b6/scratchpad/jk_yosou_cut.json")
    subprocess.run([sys.executable, str(Path(__file__).parent / "jra_jockey.py"), "--data", path,
                    "--before", cut, "--out", str(jk)], check=True, capture_output=True)
    Z.JOCKEY_STATS, Z._JK = jk, None
    pm = PaceModel().fit([d for d in lap_ok if d["date"] < cut])
    v = sorted(pace_of(d["lap"], d["distance"])["diff"] for d in lap_ok if d["date"] < cut)
    q = (v[len(v) // 3], v[2 * len(v) // 3])
    cls = lambda x: "H" if x < q[0] else ("S" if x > q[1] else "M")  # noqa: E731
    hist: dict = {}
    fo = open(out_path, "w", encoding="utf-8")
    for d in rows:
        n = d["field_size"]
        past = {x["umaban"]: {"name": x["horse_name"], "runs": sorted(hist.get(x["horse_id"], []),
                                                                     key=lambda r: r["date"], reverse=True)[:5]}
                for x in d["result"]}
        known = sum(1 for p in past.values() if any(r["corner"] for r in p["runs"])) / max(1, n)
        rec = {"race_id": d["race_id"], "date": d["date"], "half": "学習" if d["date"] < cut else "検証",
               "place": d["place"], "surface": d["surface"], "distance": d["distance"], "n": n,
               "klass": klass_of(d), "baba": d.get("baba"), "known": round(known, 2)}
        pc = pace_of(d.get("lap") or [], d["distance"])
        if pc:
            p = pm.predict(d)
            rec.update(pace_pred=cls(p), pace_act=cls(pc["diff"]), diff_pred=round(p, 2), diff_act=pc["diff"])
        if known >= 0.5 and n >= 5:
            waku = {x["umaban"]: x.get("waku") or Z.waku_of(x["umaban"], n) for x in d["result"]}
            jks = {x["umaban"]: x.get("jockey") for x in d["result"]}
            try:
                fc, rws, rk = Z.build(past, waku, place=d["place"], dist=d["distance"], surface=d["surface"],
                                      baba=d.get("baba"), jockeys=jks)
            except Exception:  # noqa: BLE001
                rws = []
            act4 = {x["umaban"]: x["corner_pos"][-1] for x in d["result"] if x.get("corner_pos")}
            act1 = {x["umaban"]: x["corner_pos"][0] for x in d["result"] if x.get("corner_pos")}
            pr = [r for r in rws if r.get("pos") is not None and r["ub"] in act4]
            if len(pr) >= 5:
                rec["corr4"] = round(J.rank_corr([-r["pos"] for r in pr], [act4[r["ub"]] for r in pr]), 3)
                k = max(1, len(pr) // 3)
                pf = {r["ub"] for r in sorted(pr, key=lambda r: -r["pos"])[:k]}
                af = {u for u, _ in sorted(((u, act4[u]) for u in (r["ub"] for r in pr)), key=lambda x: x[1])[:k]}
                rec["front_hit"] = round(len(pf & af) / k, 3)
                lead = {u for u, c in act1.items() if c == 1}
                hn = [r["ub"] for r in sorted([r for r in rws if "hana" in r], key=lambda r: -r["hana"])]
                if hn and lead:
                    rec["hana1"] = hn[0] in lead
                    rec["hana3"] = bool(set(hn[:3]) & lead)
                # 1頭ずつの外れ方(大きく外した馬の条件を見る)
                errs = []
                for r in pr:
                    pred_rank = sorted(pr, key=lambda x: -x["pos"]).index(r) / max(1, len(pr) - 1)
                    act_rank = sorted(act4.values()).index(act4[r["ub"]]) / max(1, len(act4) - 1)
                    last = r.get("last")
                    errs.append({"ub": r["ub"], "err": round(act_rank - pred_rank, 3),
                                 "dist_chg": (d["distance"] - last["dist"]) if last else None,
                                 "surf_chg": bool(last and last.get("surface") and last["surface"] != d["surface"]),
                                 "nruns": len(past[r["ub"]]["runs"])})
                rec["horses"] = errs
        fo.write(json.dumps(rec, ensure_ascii=False) + "\n")
        for x in d["result"]:
            hist.setdefault(x["horse_id"], []).append({
                "date": d["date"], "place": d["place"], "surface": d.get("surface"), "dist": d["distance"],
                "time": x.get("time"), "n": n, "fin": x["finish_pos"], "corner": x.get("corner_pos") or [],
                "agari": x.get("agari"), "baba": d.get("baba")})
    fo.close()
    return cut


def report(out_path, since=None):
    R = [json.loads(l) for l in open(out_path, encoding="utf-8")]
    te = [r for r in R if r["half"] == "検証" and (since is None or r["date"] >= since)]

    def line(lab, g):
        p = [r for r in g if "pace_pred" in r]
        c = [r["corr4"] for r in g if "corr4" in r and r["corr4"] == r["corr4"]]
        h = [r["hana3"] for r in g if "hana3" in r]
        return (f"  {lab:<18s} 鞍{len(g):5d}  ペース的中 {st.mean(r['pace_pred'] == r['pace_act'] for r in p):5.1%}"
                f"  大外れ {st.mean({r['pace_pred'], r['pace_act']} == {'S', 'H'} for r in p):4.1%}"
                f"  4角の並び {st.mean(c) if c else float('nan'):+.3f}(n={len(c)})"
                f"  ハナ上位3 {st.mean(h) if h else float('nan'):5.1%}") if p else f"  {lab} -"

    print("== 全体(検証の後半) ==")
    print(line("全体", te))
    for key, lab in [("surface", "芝ダ"), ("klass", "クラス"), ("place", "場")]:
        print(f"\n== {lab}別 ==")
        g = collections.defaultdict(list)
        for r in te:
            g[r[key]].append(r)
        for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
            if len(v) >= 40:
                print(line(str(k), v))
    print("\n== 距離帯別 ==")
    for lo, hi in [(0, 1200), (1201, 1600), (1601, 2000), (2001, 4000)]:
        print(line(f"{lo}〜{hi}m", [r for r in te if lo <= r["distance"] <= hi]))
    print("\n== 頭数別 ==")
    for lo, hi in [(5, 10), (11, 14), (15, 18)]:
        print(line(f"{lo}〜{hi}頭", [r for r in te if lo <= r["n"] <= hi]))
    print("\n== 過去走の揃い具合別 ==")
    for lo, hi in [(0.5, 0.7), (0.7, 0.9), (0.9, 1.01)]:
        print(line(f"{lo:.0%}〜{min(hi, 1):.0%}", [r for r in te if lo <= r["known"] < hi]))
    # 1頭ずつ: 想定より前に行った/後ろになった馬の条件
    H = [h for r in te for h in r.get("horses", [])]
    print(f"\n== 1頭ずつの外れ方(検証 {len(H)}頭、err=実際の順位−想定の順位、+は想定より後ろ) ==")
    for lab, f in [("距離延長(+200m以上)", lambda h: (h["dist_chg"] or 0) >= 200),
                   ("距離短縮(−200m以上)", lambda h: (h["dist_chg"] or 0) <= -200),
                   ("同距離", lambda h: h["dist_chg"] == 0),
                   ("芝ダ替わり", lambda h: h["surf_chg"]),
                   ("過去走1〜2走", lambda h: h["nruns"] <= 2),
                   ("過去走5走", lambda h: h["nruns"] >= 5)]:
        g = [h["err"] for h in H if f(h)]
        if g:
            print(f"  {lab:<18s} n={len(g):6d}  平均のずれ {st.mean(g):+.3f}  大きく外す(|ずれ|>0.4) {st.mean(abs(x) > 0.4 for x in g):5.1%}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/jra/races.jsonl")
    ap.add_argument("--out", default="data/jra/yosou_3nen.jsonl")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--since", help="この日以降だけで集計(隊列モデルの学習期間と重ねないため)")
    a = ap.parse_args()
    if not a.report_only:
        cut = predict_all(a.data, a.out)
        print(f"予想を書いた → {a.out}(境 {cut})\n")
    report(a.out, a.since)


if __name__ == "__main__":
    main()
