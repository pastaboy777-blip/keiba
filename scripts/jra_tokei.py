"""時計指数(人気を使わない地力の物差し)を作って検証する。

    python3 scripts/jra_tokei.py --data data/jra/races.jsonl

1走ごとの時計指数 = (標準タイム + その日の馬場差 − その馬の走破タイム) / 距離km   [秒/km、+ほど速い]
  標準タイム: scripts/jra_time_model.py の勝ちタイムモデル(コース平均+馬場)。
  その日の馬場差: 同日・同場・同芝ダの全レースで「勝ちタイム − 標準」の平均(過去の走なので結果を使ってよい)。
検証(後 1/3): 各馬の近3走の時計指数(最大・中央値)と着順の順位相関を、前走着順・隊列予想と比べる。
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
from jra_time_model import TimeModel  # noqa: E402
from nankeiba.scraping.db_race import pace_of  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/jra/races.jsonl")
    a = ap.parse_args()
    raw = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    raw = [d for d in raw if d.get("surface") in ("芝", "ダ") and d["result"][0].get("time")
           and pace_of(d.get("lap") or [], d["distance"])]
    raw.sort(key=lambda d: (d["date"], d["race_id"]))
    cut = raw[int(len(raw) * 2 / 3)]["date"]
    mid = raw[len(raw) // 2]["date"]
    # 標準タイムは反対側の期間で作る(自分の鞍の結果で標準を作らない)
    mA = TimeModel("time").fit([d for d in raw if d["date"] < mid])
    mB = TimeModel("time").fit([d for d in raw if d["date"] >= mid])
    std = {d["race_id"]: (mB if d["date"] < mid else mA).predict(d) for d in raw}
    day = collections.defaultdict(list)
    for d in raw:
        day[(d["date"], d["place"], d["surface"])].append(d["result"][0]["time"] - std[d["race_id"]])
    baba_sa = {k: st.mean(v) for k, v in day.items()}

    hist: dict = collections.defaultdict(list)   # horse_id → [(date, 指数, 着順, 頭数)]
    rows = []
    for d in raw:
        n = d["field_size"]
        if d["date"] >= cut and n >= 8:
            r = []
            for x in d["result"]:
                h = hist.get(x["horse_id"], [])[-3:]
                r.append({
                    "fin": x["finish_pos"],
                    "tmax": max(i for _, i, _, _ in h) if h else None,
                    "tmed": st.median(i for _, i, _, _ in h) if h else None,
                    "last_fin": (1 - (h[-1][2] - 1) / max(1, h[-1][3] - 1)) if h else None,
                })
            if sum(1 for y in r if y["tmax"] is not None) >= 0.7 * n:
                rows.append(r)
        ref = std[d["race_id"]] + baba_sa[(d["date"], d["place"], d["surface"])]
        for x in d["result"]:
            if x.get("time"):
                hist[x["horse_id"]].append((d["date"], (ref - x["time"]) / (d["distance"] / 1000), x["finish_pos"], n))

    print(f"検証 {len(rows)}鞍(境 {cut}、近走のある馬7割以上)。1鞍ごとの順位相関の平均(+ほど着順を当てる)")
    for key, lab in [("tmax", "時計指数(近3走の最大)"), ("tmed", "時計指数(近3走の中央値)"), ("last_fin", "前走着順")]:
        cs = []
        for r in rows:
            g = [y for y in r if y[key] is not None]
            c = J.rank_corr([-y[key] for y in g], [y["fin"] for y in g])
            if c == c:
                cs.append(c)
        top = []
        for r in rows:
            g = [y for y in r if y[key] is not None]
            if g:
                best = max(g, key=lambda y: y[key])
                top.append(best["fin"] <= 3)
        print(f"  {lab:<20s} 順位相関 {st.mean(cs):+.3f}   1位の馬の3着内率 {st.mean(top):.1%}")


if __name__ == "__main__":
    main()
