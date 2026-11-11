"""ペース(スロー/ミドル/ハイ)を当てることに集中する: 効く材料を全部まとめて、区分を直接学習する(LightGBM)。

    python3 scripts/jra_pace_lgbm.py --data data/jra/races.jsonl

材料: コース平均の想定(PaceModel)・距離・頭数・芝ダ・馬場・クラス・場・月・
      出走馬の顔ぶれ(逃げ率合計・先行馬割合・前に行く3頭が過去に作ったペースのずれ)・当日の前のレースのずれ・風(東西/南北/強さ)
比べる: (1) 今(コース平均+馬場)、(2) LightGBM 回帰で前後半差 → 区分、(3) LightGBM 3区分の分類。
前半で学習・後半で 3区分の的中・大外れ・芝ダ別。出力 models/pace_lgbm.json。
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
from jra_wind_kenkyu import wind_at  # noqa: E402
from jra_class_kenkyu import cls_x  # noqa: E402
from nankeiba.core import dataset as ds, tenkai as tk, course as cs  # noqa: E402
from nankeiba.core.backtest import race_contexts, record_result  # noqa: E402
from nankeiba.scraping.db_race import pace_of  # noqa: E402

PLACES = ["札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"]


def main() -> None:
    import lightgbm as lgb
    import numpy as np
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/jra/races.jsonl")
    a = ap.parse_args()
    raw = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    raw = [d for d in raw if d.get("surface") in ("芝", "ダ") and pace_of(d.get("lap") or [], d["distance"])]
    raw.sort(key=lambda d: (d["date"], d["race_id"]))
    cut = raw[len(raw) // 2]["date"]
    pm = PaceModel().fit([d for d in raw if d["date"] < cut])
    v = sorted(pace_of(d["lap"], d["distance"])["diff"] for d in raw if d["date"] < cut)
    q = (v[len(v) // 3], v[2 * len(v) // 3])
    lab = lambda x: 2 if x < q[0] else (0 if x > q[1] else 1)  # noqa: E731   0=S 1=M 2=H
    h: dict = {}
    front_hist: dict = {}
    day_res = collections.defaultdict(list)
    X, Y, D, B = [], [], [], []
    for d in raw:
        r = ds.race_from_dict(d)
        c = race_contexts(r, h)
        fc = tk.forecast({e.num(): p for e, p, _ in c}, place=r.place, distance=r.distance, surface=r.surface)
        known = [s for s in fc.styles.values() if s.early is not None]
        n = d["field_size"]
        base = pm.predict(d)
        hid = {e.num(): e.horse_id for e in r.entries}
        lr = [st.mean(front_hist[hid[u]][-3:]) for u in fc.order[:3] if front_hist.get(hid[u])]
        dk = (d["date"], d["place"], d["surface"])
        w = wind_at(d["place"], d["date"], int(d["race_id"][-2:])) or (0.0, 0.0, 0.0)
        mon = int(d["date"][5:7])
        x = [base, d["distance"] / 1000, n / 18, 1.0 if d["surface"] == "芝" else 0.0,
             {"良": 0, "稍": 1, "重": 2, "不": 3}.get(d.get("baba") or "良", 0), cs.front_bias(d["place"], d["surface"]),
             PLACES.index(d["place"]) if d["place"] in PLACES else -1, mon,
             sum(s.nige_rate for s in known), sum(1 for s in known if s.early <= 0.25) / max(1, n),
             len(known) / max(1, n), st.mean(lr) if lr else 0.0, len(lr),
             st.mean(day_res[dk]) if day_res[dk] else 0.0, len(day_res[dk]), w[0], w[1], w[2],
             int(d["race_id"][-2:])] + cls_x(d)
        y = pace_of(d["lap"], d["distance"])["diff"]
        X.append(x)
        Y.append(y)
        D.append(d)
        B.append(base)
        res = y - base
        day_res[dk].append(res)
        for e in r.entries:
            if e.corner_pos and e.corner_pos[0] <= 2:
                front_hist.setdefault(e.horse_id, []).append(res)
        record_result(r, h)
    X = np.array(X)
    Y = np.array(Y)
    tr = np.array([d["date"] < cut for d in D])
    te = ~tr
    ytr_c = np.array([lab(y) for y in Y[tr]])
    yte_c = np.array([lab(y) for y in Y[te]])
    sf_te = np.array([d["surface"] for d in D])[te]

    def report(name, pred_c):
        acc = (pred_c == yte_c).mean()
        big = ((pred_c == 0) & (yte_c == 2) | (pred_c == 2) & (yte_c == 0)).mean()
        turf = (pred_c[sf_te == "芝"] == yte_c[sf_te == "芝"]).mean()
        dirt = (pred_c[sf_te == "ダ"] == yte_c[sf_te == "ダ"]).mean()
        print(f"  {name:<28s} 的中 {acc:.1%}  大外れ {big:.1%}   芝 {turf:.1%} / ダ {dirt:.1%}")

    print(f"学習 {tr.sum()}鞍 / 検証 {te.sum()}鞍(境 {cut})  区分の境 {q[0]:+.2f} / {q[1]:+.2f}")
    report("今(コース平均+馬場)", np.array([lab(b) for b in np.array(B)[te]]))
    params = {"learning_rate": 0.03, "num_leaves": 15, "min_data_in_leaf": 60, "feature_fraction": 0.8,
              "bagging_fraction": 0.8, "bagging_freq": 1, "verbose": -1}
    reg = lgb.train(dict(params, objective="regression"), lgb.Dataset(X[tr], Y[tr]), num_boost_round=500)
    report("LightGBM 回帰→区分", np.array([lab(p) for p in reg.predict(X[te])]))
    clf = lgb.train(dict(params, objective="multiclass", num_class=3), lgb.Dataset(X[tr], ytr_c), num_boost_round=500)
    prob = clf.predict(X[te])
    pc = prob.argmax(axis=1)
    report("LightGBM 3区分の分類", pc)
    # 確度(いちばん高い確率)別
    top = prob.max(axis=1)
    order = np.argsort(-top)
    k = len(order) // 3
    for name, idx in (("確度 高(上位1/3)", order[:k]), ("確度 中", order[k:2 * k]), ("確度 低", order[2 * k:])):
        print(f"    {name:<14s} 的中 {(pc[idx] == yte_c[idx]).mean():.1%}  (確率 {top[idx].min():.2f}以上)")
    imp = sorted(zip(["想定", "距離", "頭数", "芝", "馬場", "直線", "場", "月", "逃げ率合計", "先行割合", "既知率",
                      "前3頭の過去ペース", "その数", "当日のずれ", "当日鞍数", "風東西", "風南北", "風強さ", "R"]
                     + ["新馬", "未勝利", "1勝", "2勝", "3勝", "OP", "2歳", "3歳", "3歳上", "4歳上", "重賞"],
                     clf.feature_importance("gain")), key=lambda t: -t[1])
    print("  効いた材料(上位):", " ".join(f"{n_}" for n_, _ in imp[:8]))
    json.dump({"q": q, "cut": cut, "clf": clf.model_to_string(), "reg": reg.model_to_string()},
              open(Path(__file__).resolve().parents[1] / "models" / "pace_lgbm.json", "w"))


if __name__ == "__main__":
    main()
