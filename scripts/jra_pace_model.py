"""ペース想定(前半3F − 後半3F)のモデル比較と、確度つきの想定。

    python3 scripts/jra_pace_model.py --data data/jra/races.jsonl

時系列: 前 2/3 で作り、後 1/3 で当たりを測る。
3区分(スロー/ミドル/ハイ)の境目は学習区間の実際の前後半差の三分位。
  的中     … 想定区分 = 実際区分
  大外れ   … スロー想定で実際ハイ、またはハイ想定で実際スロー
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

import jra_learn as J  # noqa: E402
from nankeiba.core import course as cs  # noqa: E402
from nankeiba.scraping.db_race import pace_of  # noqa: E402


def lin_x(d):
    return [1.0, d["distance"] / 1000, cs.front_bias(d["place"], d["surface"]),
            d["field_size"] / 18, 1.0 if d["surface"] == "芝" else 0.0]


def baba_x(d):
    b = d.get("baba") or "良"
    return [1.0 if b == "稍" else 0.0, 1.0 if b == "重" else 0.0, 1.0 if b == "不" else 0.0]


class PaceModel:
    """コース(場×芝ダ×距離)の実績平均を、件数に応じて直線式へ縮める。+ 馬場・頭数の補正。"""

    def __init__(self, shrink: float = 8.0):
        self.shrink = shrink

    def fit(self, races):
        ys = [pace_of(d["lap"], d["distance"])["diff"] for d in races]
        self.w_lin = J.ols([lin_x(d) for d in races], ys)
        cell = collections.defaultdict(list)
        for d, y in zip(races, ys):
            cell[(d["place"], d["surface"], d["distance"])].append(y - self._lin(d))
        self.cell = {k: (sum(v) / (len(v) + self.shrink), len(v)) for k, v in cell.items()}
        res = [y - self._lin(d) - self._cell(d) for d, y in zip(races, ys)]
        self.w_baba = J.ols([baba_x(d) + [1.0] for d in races], res)
        return self

    def _lin(self, d):
        return sum(a * b for a, b in zip(self.w_lin, lin_x(d)))

    def _cell(self, d):
        return self.cell.get((d["place"], d["surface"], d["distance"]), (0.0, 0))[0]

    def predict(self, d, *, use_cell=True, use_baba=True):
        p = self._lin(d)
        if use_cell:
            p += self._cell(d)
        if use_baba:
            p += sum(a * b for a, b in zip(self.w_baba, baba_x(d) + [1.0]))
        return p

    def n_cell(self, d):
        return self.cell.get((d["place"], d["surface"], d["distance"]), (0.0, 0))[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/jra/races.jsonl")
    ap.add_argument("--day-weight", type=float, default=0.3)
    a = ap.parse_args()

    raw = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    raw = [d for d in raw if d.get("surface") in ("芝", "ダ") and pace_of(d.get("lap") or [], d["distance"])]
    raw.sort(key=lambda d: (d["date"], d["race_id"]))
    cut = raw[int(len(raw) * 2 / 3)]["date"]
    tr = [d for d in raw if d["date"] < cut]
    te = [d for d in raw if d["date"] >= cut]
    y = {d["race_id"]: pace_of(d["lap"], d["distance"])["diff"] for d in raw}
    m = PaceModel().fit(tr)
    v = sorted(y[d["race_id"]] for d in tr)
    q = (v[len(v) // 3], v[2 * len(v) // 3])
    cls = lambda x: "H" if x < q[0] else ("S" if x > q[1] else "M")  # noqa: E731

    # 当日のずれ(同日・同場・同芝ダ、それより前のレース)
    def day_adj(d, pred_fn):
        prev = [y[e["race_id"]] - pred_fn(e) for e in raw
                if e["date"] == d["date"] and e["place"] == d["place"]
                and e["surface"] == d["surface"] and e["race_id"] < d["race_id"]]
        return a.day_weight * st.mean(prev) if prev else 0.0

    variants = {
        "1 今(直線式)": lambda d: m.predict(d, use_cell=False, use_baba=False),
        "2 コース平均": lambda d: m.predict(d, use_baba=False),
        "3 +馬場": lambda d: m.predict(d),
        "4 +当日のずれ": lambda d: m.predict(d) + day_adj(d, m.predict),
    }
    print(f"学習 {len(tr)}鞍 / 検証 {len(te)}鞍(境 {cut})  区分の境: ハイ < {q[0]:+.2f}秒 ≤ ミドル ≤ {q[1]:+.2f}秒 < スロー")
    print(f"{'モデル':<12s} {'相関':>6s} {'的中':>6s} {'大外れ':>6s}")
    best = None
    for name, f in variants.items():
        p = [f(d) for d in te]
        t = [y[d["race_id"]] for d in te]
        hit = sum(cls(a1) == cls(b1) for a1, b1 in zip(p, t)) / len(te)
        big = sum({cls(a1), cls(b1)} == {"H", "S"} for a1, b1 in zip(p, t)) / len(te)
        print(f"{name:<12s} {J.corr(p, t):+.3f} {hit:6.1%} {big:6.1%}")
        best = (name, f)

    # 確度: 想定値が区分の境目からどれだけ離れているか
    f = best[1]
    rows = []
    for d in te:
        p = f(d)
        margin = min(abs(p - q[0]), abs(p - q[1]))
        rows.append((margin, cls(p) == cls(y[d["race_id"]]), {cls(p), cls(y[d["race_id"]])} == {"H", "S"}))
    rows.sort(key=lambda r: -r[0])
    print("\n確度(境目からの距離)で分けた当たり具合 [最後のモデル]:")
    for name, lo, hi in [("確度 高(上位1/3)", 0, len(rows) // 3), ("確度 中", len(rows) // 3, 2 * len(rows) // 3),
                         ("確度 低(境目付近)", 2 * len(rows) // 3, len(rows))]:
        g = rows[lo:hi]
        print(f"  {name:<14s} 境目から {g[-1][0]:.2f}秒以上  的中 {sum(r[1] for r in g) / len(g):.1%}"
              f"  大外れ {sum(r[2] for r in g) / len(g):.1%}")


if __name__ == "__main__":
    main()
