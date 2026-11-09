"""ペースの「条件からのずれ」を、各馬が過去に作ったラップで当てられるかを調べる。

1回目の学習で、ペース(前半3F − 後半3F)は条件(距離・直線・頭数・芝ダ)でほぼ決まり、
逃げ率などのメンバー構成は上乗せゼロだった(notes/live/jra_learn_01.md)。
ここでは目的を「条件で決まる水準からのずれ(残差)」に絞り、手がかりを変える:

  各馬の過去走のうち「1角2番手以内で運んだ走」の残差 = その馬が前で作ったペースの速さ
  → 今回、前に行きそうな3頭(隊列予想の上位)のその値の平均 = 今日の前半が速くなりそうか

    python3 scripts/jra_pace_resid.py --data data/jra/races.jsonl
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
from nankeiba.scraping.db_race import pace_of  # noqa: E402

COND = ["1", "dist_km", "front_bias", "field", "turf"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/jra/races.jsonl")
    ap.add_argument("--front", type=int, default=3, help="隊列予想の前から何頭を見るか")
    a = ap.parse_args()

    raw = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    raw = [d for d in raw if d.get("surface") in ("芝", "ダ") and pace_of(d.get("lap") or [], d["distance"])]
    raw.sort(key=lambda d: (d["date"], d["race_id"]))
    races = [ds.race_from_dict(d) for d in raw]
    cut = raw[int(len(raw) * 2 / 3)]["date"]

    # 1) 条件だけのモデルを学習区間で作る
    def cond_x(r):
        from nankeiba.core import course as cs
        return {"1": 1.0, "dist_km": r.distance / 1000, "front_bias": cs.front_bias(r.place, r.surface),
                "field": r.field_size / 18, "turf": 1.0 if r.surface == "芝" else 0.0}
    ys = {d["race_id"]: pace_of(d["lap"], d["distance"])["diff"] for d in raw}
    tr = [(cond_x(r), ys[r.race_id]) for r in races if r.date < cut]
    w = J.ols([[x[f] for f in COND] for x, _ in tr], [y for _, y in tr])
    resid = {r.race_id: ys[r.race_id] - sum(wi * cond_x(r)[f] for wi, f in zip(w, COND)) for r in races}

    # 2) 時系列に: 前に行きそうな馬が過去に前で作ったペースの残差
    front_hist: dict[str, list[float]] = {}
    history: dict = {}
    rows = []
    for d, r in zip(raw, races):
        ctx = race_contexts(r, history)
        pasts = {e.num(): p for e, p, _ in ctx}
        fc = tk.forecast(pasts, place=r.place, distance=r.distance, surface=r.surface)
        hid = {e.num(): e.horse_id for e in r.entries}
        vals = []
        for u in fc.order[: a.front]:
            h = front_hist.get(hid[u])
            if h:
                vals.append(st.mean(h[-3:]))
        if len(vals) >= 2:
            rows.append((r.date, st.mean(vals), resid[r.race_id], fc.pace_index))
        for e in r.entries:
            if e.corner_pos and e.corner_pos[0] <= 2:
                front_hist.setdefault(e.horse_id, []).append(resid[r.race_id])
        record_result(r, history)

    te = [x for x in rows if x[0] >= cut]
    print(f"鞍 {len(raw)}  境 {cut}  手がかりのある鞍 {len(rows)}(検証区間 {len(te)})")
    print(f"条件だけのモデルの残差 標準偏差 {st.pstdev(resid.values()):.2f}秒")
    print(f"前3頭が過去に前で作ったペースの残差 vs 今回の残差: 相関 {J.corr([x[1] for x in rows], [x[2] for x in rows]):+.3f}"
          f"(検証区間 {J.corr([x[1] for x in te], [x[2] for x in te]):+.3f})")
    print(f"参考 今の pace_index vs 今回の残差: {J.corr([x[3] for x in rows], [x[2] for x in rows]):+.3f}"
          "  ※ハイ予想→前半速い→残差は負、が正解なので負なら当たり")


if __name__ == "__main__":
    main()
