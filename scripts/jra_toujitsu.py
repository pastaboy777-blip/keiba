"""研究: 当日の時計・ラップから、後半(メイン)のレースのペースと時計をどこまで推測できるか。

    python3 scripts/jra_toujitsu.py --data data/jra/races.jsonl

各鞍について、同じ日・同じ場・同じ芝ダで「それより前に終わったレース」の
  ・勝ちタイムのずれ(実際 − 標準)  → 馬場の速さ
  ・前後半差のずれ(実際 − 標準)    → 前が流れる日か、溜める日か
を平均し、標準(コース+馬場+クラス)に足す。前のレースが k 鞍ある時点ごとに、
足さない場合と比べて誤差・的中がどれだけ縮むかを出す。ずれは何割足すのが良いかも学習区間で決める。
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jra_pace_model import PaceModel  # noqa: E402
from jra_time_model import TimeModel  # noqa: E402
from nankeiba.scraping.db_race import pace_of  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/jra/races.jsonl")
    a = ap.parse_args()
    raw = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    raw = [d for d in raw if d.get("surface") in ("芝", "ダ") and pace_of(d.get("lap") or [], d["distance"])
           and d["result"][0].get("time")]
    raw.sort(key=lambda d: (d["date"], d["race_id"]))
    cut = raw[int(len(raw) * 2 / 3)]["date"]
    tr = [d for d in raw if d["date"] < cut]
    pm, tm = PaceModel().fit(tr), TimeModel("time").fit(tr)
    v = sorted(pace_of(d["lap"], d["distance"])["diff"] for d in tr)
    q = (v[len(v) // 3], v[2 * len(v) // 3])
    cl = lambda x: "H" if x < q[0] else ("S" if x > q[1] else "M")  # noqa: E731

    rec = {}
    for d in raw:
        p = pace_of(d["lap"], d["distance"])
        rec[d["race_id"]] = {"d": d, "dp": p["diff"] - pm.predict(d), "dt": d["result"][0]["time"] - tm.predict(d),
                             "pp": pm.predict(d), "pt": tm.predict(d), "yp": p["diff"], "yt": d["result"][0]["time"]}
    day = collections.defaultdict(list)
    for d in raw:
        day[(d["date"], d["place"], d["surface"])].append(d["race_id"])

    def rows(sel):
        out = []
        for d in sel:
            prev = [rec[r] for r in day[(d["date"], d["place"], d["surface"])] if r < d["race_id"]]
            out.append((rec[d["race_id"]], prev, int(d["race_id"][-2:])))
        return out

    # 何割足すか(学習区間で決める)
    R_tr = [x for x in rows(tr) if x[1]]
    best = {}
    for key, yk, pk in [("dp", "yp", "pp"), ("dt", "yt", "pt")]:
        errs = {}
        for wgt in [0, .2, .3, .4, .5, .6, .7, .8, 1.0]:
            errs[wgt] = st.mean(abs(r[yk] - r[pk] - wgt * st.mean(p[key] for p in prev)) for r, prev, _ in R_tr)
        best[key] = min(errs, key=errs.get)
    print(f"学習区間で決めた足す割合: ペース {best['dp']:.1f} / 時計 {best['dt']:.1f}")

    R_te = rows([d for d in raw if d["date"] >= cut])
    print(f"検証 {len(R_te)}鞍(境 {cut})\n")
    print("当日それより前の同じ場・芝ダのレース数 | 鞍数 | 勝ちタイム誤差 足さない→足す | 前後半差誤差 | ペース3区分の的中")
    for lab, lo, hi in [("0鞍(1Rなど)", 0, 0), ("1〜2鞍", 1, 2), ("3〜4鞍", 3, 4), ("5鞍以上(後半・メイン)", 5, 99)]:
        g = [x for x in R_te if lo <= len(x[1]) <= hi]
        if not g:
            continue
        def adj(r, prev, key):
            return best[key] * st.mean(p[key] for p in prev) if prev else 0.0
        et0 = st.mean(abs(r["yt"] - r["pt"]) for r, _, _ in g)
        et1 = st.mean(abs(r["yt"] - r["pt"] - adj(r, p, "dt")) for r, p, _ in g)
        ep0 = st.mean(abs(r["yp"] - r["pp"]) for r, _, _ in g)
        ep1 = st.mean(abs(r["yp"] - r["pp"] - adj(r, p, "dp")) for r, p, _ in g)
        h0 = st.mean(cl(r["pp"]) == cl(r["yp"]) for r, _, _ in g)
        h1 = st.mean(cl(r["pp"] + adj(r, p, "dp")) == cl(r["yp"]) for r, p, _ in g)
        print(f"  {lab:<20s} {len(g):5d}  {et0:.2f}→{et1:.2f}秒   {ep0:.2f}→{ep1:.2f}秒   {h0:.1%}→{h1:.1%}")
    g = [x for x in R_te if x[2] == 11 and x[1]]
    if g:
        et0 = st.mean(abs(r["yt"] - r["pt"]) for r, _, _ in g)
        et1 = st.mean(abs(r["yt"] - r["pt"] - best["dt"] * st.mean(p["dt"] for p in prev)) for r, prev, _ in g)
        h0 = st.mean(cl(r["pp"]) == cl(r["yp"]) for r, _, _ in g)
        h1 = st.mean(cl(r["pp"] + best["dp"] * st.mean(p["dp"] for p in prev)) == cl(r["yp"]) for r, prev, _ in g)
        print(f"\n  メイン(11R)だけ {len(g)}鞍: 勝ちタイム誤差 {et0:.2f}→{et1:.2f}秒 / ペース3区分 {h0:.1%}→{h1:.1%}")
    json.dump(best, open(Path(__file__).resolve().parents[1] / "models" / "toujitsu_weight.json", "w"))


if __name__ == "__main__":
    main()
