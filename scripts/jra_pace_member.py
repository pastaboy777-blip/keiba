"""ペース想定に「出走馬の顔ぶれ」を足す(芝ダ別)。3年分で 芝は逃げ率合計・先行馬の割合が効く(相関 −0.21)。

    python3 scripts/jra_pace_member.py --data data/jra/races.jsonl

土台 = jra_pace_model.PaceModel(コース平均+馬場)。その残差を 芝ダ別に [1, 逃げ率合計, 先行馬の割合] で回帰。
前半で学習・後半で 3区分の的中・大外れ を比べる。係数は models/pace_member.json。
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
from jra_pace_model import PaceModel  # noqa: E402
from nankeiba.core import dataset as ds, tenkai as tk  # noqa: E402
from nankeiba.core.backtest import race_contexts, record_result  # noqa: E402
from nankeiba.scraping.db_race import pace_of  # noqa: E402


def member_x(styles: dict, n: int) -> list[float]:
    known = [s for s in styles.values() if s.early is not None]
    return [1.0, sum(s.nige_rate for s in known), sum(1 for s in known if s.early <= 0.25) / max(1, n)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/jra/races.jsonl")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "models" / "pace_member.json"))
    a = ap.parse_args()
    raw = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    raw = [d for d in raw if d.get("surface") in ("芝", "ダ") and pace_of(d.get("lap") or [], d["distance"])]
    raw.sort(key=lambda d: (d["date"], d["race_id"]))
    cut = raw[len(raw) // 2]["date"]
    tr_ = [d for d in raw if d["date"] < cut]
    pm = PaceModel().fit(tr_)
    v = sorted(pace_of(d["lap"], d["distance"])["diff"] for d in tr_)
    q = (v[len(v) // 3], v[2 * len(v) // 3])
    cl = lambda x: "H" if x < q[0] else ("S" if x > q[1] else "M")  # noqa: E731
    h: dict = {}
    R = []
    for d in raw:
        r = ds.race_from_dict(d)
        c = race_contexts(r, h)
        fc = tk.forecast({e.num(): p for e, p, _ in c}, place=r.place, distance=r.distance, surface=r.surface)
        R.append((d, member_x(fc.styles, d["field_size"]), pm.predict(d), pace_of(d["lap"], d["distance"])["diff"]))
        record_result(r, h)
    out = {"cut": cut, "q": q}
    for sf in ("芝", "ダ"):
        tr = [x for x in R if x[0]["surface"] == sf and x[0]["date"] < cut]
        te = [x for x in R if x[0]["surface"] == sf and x[0]["date"] >= cut]
        w = J.ols([x[1] for x in tr], [x[3] - x[2] for x in tr])
        out[sf] = w
        add = lambda x: sum(a_ * b for a_, b in zip(w, x[1]))  # noqa: E731
        h0 = st.mean(cl(x[2]) == cl(x[3]) for x in te)
        h1 = st.mean(cl(x[2] + add(x)) == cl(x[3]) for x in te)
        b0 = st.mean({cl(x[2]), cl(x[3])} == {"S", "H"} for x in te)
        b1 = st.mean({cl(x[2] + add(x)), cl(x[3])} == {"S", "H"} for x in te)
        e0 = st.mean(abs(x[3] - x[2]) for x in te)
        e1 = st.mean(abs(x[3] - x[2] - add(x)) for x in te)
        print(f"[{sf}] 検証 {len(te)}鞍  3区分の的中 {h0:.1%} → {h1:.1%}  大外れ {b0:.1%} → {b1:.1%}  "
              f"前後半差の誤差 {e0:.2f} → {e1:.2f}秒   係数 切片{w[0]:+.2f} 逃げ率合計{w[1]:+.2f} 先行馬割合{w[2]:+.2f}")
    json.dump(out, open(a.out, "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
