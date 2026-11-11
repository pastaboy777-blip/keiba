"""隊列(前後)をちゃんと学ぶ: 1角・4角それぞれを目的に、手がかりを1つずつ足して検証区間で比べる。

    python3 scripts/jra_position_model2.py --data data/jra/races.jsonl

時系列: 前 2/3 で学習、後 1/3 で検証。騎手の癖なども「その鞍より前」の情報だけで作る。
指標(1鞍ごと→平均): 順位相関 / 前1/3一致 / ハナ(1角)・先頭(4角)的中
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
from jra_pace_model import PaceModel  # noqa: E402
from nankeiba.core import dataset as ds, tenkai as tk  # noqa: E402
from nankeiba.core.backtest import record_result  # noqa: E402
from nankeiba.scraping.db_race import pace_of  # noqa: E402

BASE = ["1", "early", "known", "nige", "med_c4"]
STEPS = [
    ("+似た条件の過去走", ["sim_c1", "sim_c4", "has_sim"]),
    ("+距離変更", ["dist_diff", "surf_change"]),
    ("+押し上げ癖", ["gain"]),
    ("+騎手の癖", ["jk_bias", "jk_change"]),
    ("+枠×距離", ["gate", "gate_x_short"]),
    ("+ペース想定", ["pace", "pace_x_early"]),
    ("+同じ芝ダの過去走の位置", ["early_ss", "has_ss", "early_ss_x_chg"]),
    ("+同じ芝ダ・近い距離の位置(長距離も)", ["early_sim", "has_sim2", "long_x_sim"]),
    ("+流れ別の位置(想定ペースと同じ流れ)", ["early_samepace", "has_samepace", "pace_sens_x_pace"]),
    ("+出遅れ率(推定)", ["late_rate", "late_x_early"]),
    ("+相手との比較(レース内の順位・差)", [k + s_ for k in ("early", "nige", "early_sim", "med_c4")
                                       for s_ in ("_rk", "_gap_prev", "_gap_next")]),
]


def norm(r, i):
    return (r.corner_pos[i] - 1) / max(1, r.field_size - 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/jra/races.jsonl")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "models" / "position_model.json"))
    a = ap.parse_args()
    raw = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    raw = [d for d in raw if d.get("surface") in ("芝", "ダ")]
    raw.sort(key=lambda d: (d["date"], d["race_id"]))
    cut = raw[int(len(raw) * 2 / 3)]["date"]
    lap_ok = [d for d in raw if pace_of(d.get("lap") or [], d["distance"])]
    pm = PaceModel().fit([d for d in lap_ok if d["date"] < cut])

    h: dict = {}
    jk_res = collections.defaultdict(list)   # 騎手 → (実際1角 − 馬のいつもの位置)
    vv = sorted(pace_of(d["lap"], d["distance"])["diff"] for d in lap_ok if d["date"] < cut)
    pq = (vv[len(vv) // 3], vv[2 * len(vv) // 3])
    pcls = lambda x: "H" if x < pq[0] else ("S" if x > pq[1] else "M")  # noqa: E731
    hp = collections.defaultdict(list)       # 馬 → [(その走の実際のペース区分, 1角位置, 4角位置)]
    R = []
    for d in raw:
        r = ds.race_from_dict(d)
        n = len(r.entries)
        pace = pm.predict(d) / 2
        rows = []
        for e in r.entries:
            past = h.get(e.horse_id, [])
            runs = [x for x in past if x.corner_pos and x.field_size > 1]
            sp = tk.style_profile(past)
            sim = [x for x in runs if x.surface == r.surface and abs(x.distance - r.distance) <= 200]
            jb = jk_res.get(e.jockey) or []
            last = past[0] if past else None
            early = sp.early_or(0.5)
            ss = [x for x in past if x.surface == r.surface]
            sp_ss = tk.style_profile(ss)
            sim2 = [x for x in ss if abs(x.distance - r.distance) <= 300]
            sp_sim = tk.style_profile(sim2)
            chg = 1.0 if last and last.surface and last.surface != r.surface else 0.0
            # 出遅れ率(推定): その走の1角位置が、ほかの走の1角位置の中央値より 0.35 以上うしろ
            c1s = [norm(x, 0) for x in runs]
            late = 0
            for i_, c in enumerate(c1s):
                others = c1s[:i_] + c1s[i_ + 1:]
                if others and c - st.median(others) >= 0.35:
                    late += 1
            late_rate = (late / len(c1s)) if len(c1s) >= 3 else 0.0
            today = pcls(pm.predict(d))
            hpr = hp.get(e.horse_id, [])
            same = [c1 for k_, c1, _ in hpr if k_ == today]
            fast = [c1 for k_, c1, _ in hpr if k_ == "H"]
            slow = [c1 for k_, c1, _ in hpr if k_ == "S"]
            sens = (st.mean(fast) - st.mean(slow)) if fast and slow else 0.0   # + = 速い流れだと後ろになる馬
            f = {
                "late_rate": late_rate, "late_x_early": late_rate * (0.5 - early),
                "early_samepace": st.mean(same) if same else early, "has_samepace": 1.0 if same else 0.0,
                "pace_sens_x_pace": sens * (1.0 if today == "H" else (-1.0 if today == "S" else 0.0)),
                "early_ss": sp_ss.early_or(early), "has_ss": 1.0 if sp_ss.early is not None else 0.0,
                "early_ss_x_chg": sp_ss.early_or(early) * chg,
                "early_sim": sp_sim.early_or(early), "has_sim2": 1.0 if sp_sim.early is not None else 0.0,
                "long_x_sim": sp_sim.early_or(early) * (1.0 if r.distance >= 2000 else 0.0),
                "1": 1.0, "early": early, "known": 1.0 if sp.early is not None else 0.0, "nige": sp.nige_rate,
                "med_c4": st.median(norm(x, -1) for x in runs) if runs else 0.5,
                "sim_c1": st.median(norm(x, 0) for x in sim) if sim else early,
                "sim_c4": st.median(norm(x, -1) for x in sim) if sim else early,
                "has_sim": 1.0 if sim else 0.0,
                "dist_diff": ((r.distance - last.distance) / 1000) if last else 0.0,
                "surf_change": 1.0 if last and last.surface and last.surface != r.surface else 0.0,
                "gain": st.median(norm(x, 0) - norm(x, -1) for x in runs) if runs else 0.0,
                "jk_bias": (sum(jb) / (len(jb) + 10)) if jb else 0.0,
                "jk_change": 1.0 if last and last.jockey and e.jockey and last.jockey != e.jockey else 0.0,
                "gate": ((e.umaban or 1) - 1) / max(1, n - 1),
                "gate_x_short": (((e.umaban or 1) - 1) / max(1, n - 1)) * (1.0 if r.distance <= 1400 else 0.0),
                "pace": pace, "pace_x_early": pace * early,
            }
            if e.corner_pos and n > 1:
                rows.append({"x": f, "c1": (e.corner_pos[0] - 1) / (n - 1), "c4": (e.corner_pos[-1] - 1) / (n - 1),
                             "lead1": e.corner_pos[0] == 1, "lead4": e.corner_pos[-1] == 1, "cur": early})
        for key in ("early", "nige", "early_sim", "med_c4"):
            vals = sorted(x["x"][key] for x in rows)
            for x in rows:
                v_ = x["x"][key]
                i_ = vals.index(v_)
                x["x"][key + "_rk"] = i_ / max(1, len(vals) - 1)
                x["x"][key + "_gap_prev"] = (v_ - vals[i_ - 1]) if i_ > 0 else 0.0
                x["x"][key + "_gap_next"] = (vals[i_ + 1] - v_) if i_ + 1 < len(vals) else 0.0
        if len(rows) >= 8:
            R.append({"date": d["date"], "rows": rows, "known": st.mean(x["x"]["known"] for x in rows)})
        # 流れ別の位置を更新(結果を見た後)
        pc_ = pace_of(d.get("lap") or [], d["distance"])
        if pc_:
            for e in r.entries:
                if e.corner_pos and n > 1:
                    hp[e.horse_id].append((pcls(pc_["diff"]), (e.corner_pos[0] - 1) / (n - 1),
                                           (e.corner_pos[-1] - 1) / (n - 1)))
        # 騎手の癖を更新(結果を見た後)
        for e in r.entries:
            past = h.get(e.horse_id, [])
            sp = tk.style_profile(past)
            if e.corner_pos and sp.early is not None and e.jockey and n > 1:
                jk_res[e.jockey].append((e.corner_pos[0] - 1) / (n - 1) - sp.early)
        record_result(r, h)

    tr = [q for q in R if q["date"] < cut and q["known"] >= 0.5]
    te = [q for q in R if q["date"] >= cut and q["known"] >= 0.7]

    def evaluate(f, target, lead):
        cors, front, ld = [], [], []
        for q in te:
            rs = q["rows"]
            p = [f(x) for x in rs]
            c = J.rank_corr(p, [x[target] for x in rs])
            if c == c:
                cors.append(c)
            k = len(rs) // 3
            pf = set(sorted(range(len(rs)), key=lambda i: p[i])[:k])
            af = set(sorted(range(len(rs)), key=lambda i: rs[i][target])[:k])
            front.append(len(pf & af) / max(1, k))
            ld.append(rs[min(range(len(rs)), key=lambda i: p[i])][lead])
        return st.mean(cors), st.mean(front), st.mean(ld)

    print(f"学習 {len(tr)}鞍 / 検証 {len(te)}鞍(履歴7割以上、境 {cut})")
    best = {}
    for target, lead, lab in [("c1", "lead1", "1角"), ("c4", "lead4", "4角")]:
        print(f"\n== 目的: {lab}の位置 ==   順位相関 / 前1/3一致 / {'ハナ' if lab == '1角' else '先頭'}的中")
        c, fr, ld = evaluate(lambda x: x["cur"], target, lead)
        print(f"  今の予想(通過順の直近加重)       {c:+.3f} / {fr:.1%} / {ld:.1%}")
        feats = list(BASE)
        for name, add in [("学習: 基本", [])] + STEPS:
            feats = feats + add
            w = J.ols([[x["x"][k] for k in feats] for q in tr for x in q["rows"]],
                      [x[target] for q in tr for x in q["rows"]], l2=1e-3)
            f = (lambda w, fs: (lambda x: sum(wi * x["x"][k] for wi, k in zip(w, fs))))(w, feats)
            c, fr, ld = evaluate(f, target, lead)
            print(f"  {name:<24s} {c:+.3f} / {fr:.1%} / {ld:.1%}")
            best[lab] = {"features": feats, "coef": w}
        print("  係数(最後のモデル、+ほど後ろ): " + "  ".join(f"{k} {wi:+.2f}" for k, wi in zip(feats, w)))
        try:   # 非線形(LightGBM): 条件の組み合わせを拾えるか
            import lightgbm as lgb
            import numpy as np
            feats = [k for k in feats if k not in ("pace", "pace_x_early")]   # 図ではペース想定より先に隊列を出すので外す
            Xtr = np.array([[x["x"][k] for k in feats] for q in tr for x in q["rows"]])
            ytr = np.array([x[target] for q in tr for x in q["rows"]])
            gb = lgb.train({"objective": "regression", "learning_rate": 0.03, "num_leaves": 31,
                            "min_data_in_leaf": 80, "bagging_fraction": 0.8, "bagging_freq": 1,
                            "feature_fraction": 0.8, "verbose": -1}, lgb.Dataset(Xtr, ytr), num_boost_round=400)
            # 1鞍ずつまとめて予測(速さのため)
            cache = {}
            for q in te:
                pv = gb.predict(np.array([[x["x"][k] for k in feats] for x in q["rows"]]))
                for x, v_ in zip(q["rows"], pv):
                    cache[id(x)] = float(v_)
            c, fr, ld = evaluate(lambda x: cache[id(x)], target, lead)
            print(f"  {'非線形(LightGBM)':<24s} {c:+.3f} / {fr:.1%} / {ld:.1%}")
            # 並び順を当てる学び方(lambdarank): 前にいるほど関連度が高い
            grp = [len(q["rows"]) for q in tr]
            rel = np.array([min(20, max(0, int(round((1 - x[target]) * 20)))) for q in tr for x in q["rows"]])
            rk = lgb.train({"objective": "lambdarank", "learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 80,
                            "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "verbose": -1,
                            "label_gain": list(range(21)), "lambdarank_truncation_level": 20},
                           lgb.Dataset(Xtr, rel, group=grp), num_boost_round=300)
            cache2 = {}
            for q in te:
                pv = rk.predict(np.array([[x["x"][k] for k in feats] for x in q["rows"]]))
                for x, v_ in zip(q["rows"], pv):
                    cache2[id(x)] = -float(v_)
            c, fr, ld = evaluate(lambda x: cache2[id(x)], target, lead)
            print(f"  {'順位学習(lambdarank)':<24s} {c:+.3f} / {fr:.1%} / {ld:.1%}")
            best[lab + "_lgbm"] = gb.model_to_string()
            best[lab + "_lgbm_features"] = feats
        except ImportError:
            pass
    best["cut"] = cut
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(best, open(a.out, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
