"""隊列想定(1角の位置)のモデル比較と確度。

    python3 scripts/jra_position_model.py --data data/jra/races.jsonl

時系列: 前 2/3 で学習、後 1/3 で検証。指標(1鞍ごと → 平均):
  順位相関 … 予想の並びと実際の1角の並び
  前1/3一致 … 予想で前1/3の馬が、実際に1角で前1/3にいた割合
  ハナ的中 … 予想1番手が実際に1角先頭
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import jra_learn as J  # noqa: E402
from nankeiba.core import dataset as ds, tenkai as tk  # noqa: E402
from nankeiba.core.backtest import race_contexts, record_result  # noqa: E402

FEATS = ["1", "early", "known", "nige", "last_c1", "med_c4", "gate", "dist_diff", "surf_change",
         "field", "n_runs", "early_x_dist", "last_c1_same_surf", "place_change"]


def feats(e, past, race):
    x = J.pos_features(e, past, race)
    runs = [r for r in past if r.corner_pos and r.field_size > 1]
    same = [r for r in runs if r.surface == race.surface]
    x["n_runs"] = min(len(runs), 5) / 5
    x["early_x_dist"] = x["early"] * x["dist_diff"]
    x["last_c1_same_surf"] = ((same[0].corner_pos[0] - 1) / (same[0].field_size - 1)) if same else x["last_c1"]
    x["place_change"] = 1.0 if past and past[0].place != race.place else 0.0
    return x


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/jra/races.jsonl")
    ap.add_argument("--out", default="data/jra/position_model.json")
    a = ap.parse_args()
    raw = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    raw = [d for d in raw if d.get("surface") in ("芝", "ダ")]
    raw.sort(key=lambda d: (d["date"], d["race_id"]))
    cut = raw[int(len(raw) * 2 / 3)]["date"]

    h: dict = {}
    R = []
    for d in raw:
        r = ds.race_from_dict(d)
        c = race_contexts(r, h)
        fc = tk.forecast({e.num(): p for e, p, _ in c}, place=r.place, distance=r.distance, surface=r.surface)
        rows = []
        for e, past, _ in c:
            if e.corner_pos and r.field_size > 1:
                x = feats(e, past, r)
                rows.append({"x": x, "cur": fc.styles[e.num()].early_or(0.5),
                             "c1": (e.corner_pos[0] - 1) / (r.field_size - 1), "lead": e.corner_pos[0] == 1,
                             "known": x["known"]})
        if len(rows) >= 8:
            R.append({"date": d["date"], "rows": rows, "known": st.mean(x["known"] for x in rows)})
        record_result(r, h)

    tr = [q for q in R if q["date"] < cut and q["known"] >= 0.5]
    te = [q for q in R if q["date"] >= cut]
    w = J.ols([[x["x"][f] for f in FEATS] for q in tr for x in q["rows"]], [x["c1"] for q in tr for x in q["rows"]])
    learned = lambda x: sum(wi * x["x"][f] for wi, f in zip(w, FEATS))  # noqa: E731

    def evaluate(qs, f):
        cors, front, lead = [], [], []
        for q in qs:
            rs = q["rows"]
            p = [f(x) for x in rs]
            cors.append(J.rank_corr(p, [x["c1"] for x in rs]))
            n = len(rs)
            pf = set(sorted(range(n), key=lambda i: p[i])[: n // 3])
            af = set(sorted(range(n), key=lambda i: rs[i]["c1"])[: n // 3])
            front.append(len(pf & af) / max(1, len(pf)))
            lead.append(rs[min(range(n), key=lambda i: p[i])]["lead"])
        cors = [c for c in cors if c == c]
        return st.mean(cors), st.mean(front), st.mean(lead)

    print(f"学習 {len(tr)}鞍 / 検証 {len(te)}鞍(境 {cut})")
    print(f"{'':<22s}{'順位相関':>8s}{'前1/3一致':>10s}{'ハナ的中':>9s}")
    for name, f in [("今(通過順の直近加重)", lambda x: x["cur"]), ("学習モデル", learned)]:
        for lab, qs in [("全鞍", te), ("履歴が揃った鞍(7割+)", [q for q in te if q["known"] >= 0.7])]:
            c, fr, ld = evaluate(qs, f)
            print(f"{name}・{lab:<12s} {c:+8.3f}{fr:10.1%}{ld:9.1%}")
    print("\n確度(その鞍の履歴の揃い具合)別・学習モデル:")
    for lab, lo, hi in [("履歴9割以上", 0.9, 1.01), ("7〜9割", 0.7, 0.9), ("5〜7割", 0.5, 0.7), ("5割未満", 0, 0.5)]:
        qs = [q for q in te if lo <= q["known"] < hi]
        if qs:
            c, fr, ld = evaluate(qs, learned)
            print(f"  {lab:<10s} {len(qs):4d}鞍  順位相関 {c:+.3f}  前1/3一致 {fr:.1%}  ハナ的中 {ld:.1%}")
    print("\n係数(+ ほど後ろ):")
    for f, wi in zip(FEATS, w):
        print(f"  {f:<18s} {wi:+.3f}")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump({"features": FEATS, "coef": w, "cut": cut}, open(a.out, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
