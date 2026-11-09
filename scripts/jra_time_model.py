"""推定タイム・推定前半3F・推定後半3F を学習する(netkeiba AI の表示に相当するもの)。

    python3 scripts/jra_time_model.py --data data/jra/races.jsonl

各目的(前半3F/後半3F/走破タイム)ごとに PaceModel と同じ作り:
  直線式(距離・直線・頭数・芝ダ) + コース(場×芝ダ×距離)平均の縮約 + 馬場 + 当日のずれ(同日・同場・同芝ダの前のレース)
時系列: 前 2/3 で学習、後 1/3 で平均絶対誤差(秒)を測る。係数は models/time_model.json。
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
from jra_pace_model import lin_x, baba_x  # noqa: E402
from nankeiba.scraping.db_race import pace_of  # noqa: E402

TARGETS = {"front3": "推定前半3F", "last3": "推定後半3F", "time": "推定タイム"}


def target(d, k):
    if k == "time":
        return d["result"][0]["time"]
    return pace_of(d["lap"], d["distance"])[k]


class TimeModel:
    def __init__(self, k, shrink=8.0):
        self.k, self.shrink = k, shrink

    def fit(self, races):
        ys = [target(d, self.k) for d in races]
        X = [lin_x(d) + [d["distance"] ** 2 / 1e6] for d in races]
        self.w = J.ols(X, ys)
        cell = collections.defaultdict(list)
        for d, y in zip(races, ys):
            cell[(d["place"], d["surface"], d["distance"])].append(y - self._lin(d))
        self.cell = {"|".join(map(str, k)): sum(v) / (len(v) + self.shrink) for k, v in cell.items()}
        res = [y - self._lin(d) - self._cell(d) for d, y in zip(races, ys)]
        self.wb = J.ols([baba_x(d) + [1.0] for d in races], res)
        return self

    def _lin(self, d):
        return sum(a * b for a, b in zip(self.w, lin_x(d) + [d["distance"] ** 2 / 1e6]))

    def _cell(self, d):
        return self.cell.get("|".join(map(str, (d["place"], d["surface"], d["distance"]))), 0.0)

    def predict(self, d):
        return self._lin(d) + self._cell(d) + sum(a * b for a, b in zip(self.wb, baba_x(d) + [1.0]))

    def dump(self):
        return {"w": self.w, "cell": self.cell, "wb": self.wb}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/jra/races.jsonl")
    ap.add_argument("--day-weight", type=float, default=0.5)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "models" / "time_model.json"))
    a = ap.parse_args()
    raw = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    raw = [d for d in raw if d.get("surface") in ("芝", "ダ") and pace_of(d.get("lap") or [], d["distance"])
           and d["result"][0].get("time")]
    raw.sort(key=lambda d: (d["date"], d["race_id"]))
    cut = raw[int(len(raw) * 2 / 3)]["date"]
    tr = [d for d in raw if d["date"] < cut]
    te = [d for d in raw if d["date"] >= cut]
    print(f"学習 {len(tr)}鞍 / 検証 {len(te)}鞍(境 {cut})   平均絶対誤差[秒]")
    out = {"cut": cut}
    for k, lab in TARGETS.items():
        m = TimeModel(k).fit(tr)
        ys = {d["race_id"]: target(d, k) for d in raw}

        def with_day(d):
            prev = [ys[e["race_id"]] - m.predict(e) for e in raw
                    if e["date"] == d["date"] and e["place"] == d["place"]
                    and e["surface"] == d["surface"] and e["race_id"] < d["race_id"]]
            return m.predict(d) + (a.day_weight * st.mean(prev) if prev else 0.0)

        mean_only = {}
        for d in tr:
            mean_only.setdefault((d["surface"], d["distance"]), []).append(target(d, k))
        e0 = st.mean(abs(target(d, k) - st.mean(mean_only.get((d["surface"], d["distance"]), [target(d, k)]))) for d in te)
        e1 = st.mean(abs(target(d, k) - m.predict(d)) for d in te)
        e2 = st.mean(abs(target(d, k) - with_day(d)) for d in te)
        print(f"  {lab:<8s} 芝ダ×距離の平均だけ {e0:.2f} / 学習(コース+馬場) {e1:.2f} / +当日のずれ {e2:.2f}")
        out[k] = m.dump()
    out["day_weight"] = a.day_weight
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(a.out, "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
