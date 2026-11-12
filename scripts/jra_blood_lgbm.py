"""研究: 新馬戦の1角位置を LightGBM で学習し、父の材料を入れると良くなるかを比べる(時系列で前半学習・後半検証)。

    python3 scripts/jra_blood_lgbm.py

材料(どれも、そのレースより前の情報だけ):
  基本 … 枠(相対)・頭数・芝ダ・距離・騎手の1角3番手以内率・騎手の騎乗数
  父   … 父の産駒の1角相対位置(縮めた平均)・ハナ率・産駒数(芝ダ別)、母の父の同じ数字、外国産か
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main():
    import lightgbm as lgb
    P = {}
    for l in open(ROOT / "data/jra/pedigree.jsonl"):
        d = json.loads(l)
        P[d["horse_id"]] = d
    raw = [json.loads(l) for l in open(ROOT / "data/jra/races.jsonl")]
    raw = [d for d in raw if d.get("surface") in ("芝", "ダ")]
    raw.sort(key=lambda d: (d["date"], d["race_id"]))
    S = collections.defaultdict(lambda: [0, 0.0, 0])
    J = collections.defaultdict(lambda: [0, 0])
    mu = [0, 0.0]
    rows = []
    K = 8.0
    for d in raw:
        c = (d.get("race_class") or "") + (d.get("name") or "")
        n = d["field_size"]
        rs = [r for r in d["result"] if r.get("corner_pos")]
        debut = ("新馬" in c or "デビュー" in c) and len(rs) >= 6
        if debut and sum(r["horse_id"] in P for r in rs) >= 0.8 * len(rs):
            m = mu[1] / max(1, mu[0])
            lead = min(r["corner_pos"][0] for r in rs)
            for r in rs:
                p = P.get(r["horse_id"]) or {}
                s = S[(p.get("sire"), d["surface"])]
                ds = S[("BMS:" + str(p.get("damsire")), d["surface"])]
                j = J[r.get("jockey")]
                base = [(r["umaban"] - 1) / max(1, n - 1), n, d["surface"] == "芝", d["distance"] / 1000,
                        (j[1] + 1) / (j[0] + 5), min(j[0], 500) / 500]
                blood = [(s[1] + K * m) / (s[0] + K), (s[2] + 0.5) / (s[0] + 8), min(s[0], 200) / 200,
                         (ds[1] + K * m) / (ds[0] + K), min(ds[0], 200) / 200, 1.0 if (p.get("origin") or "日") != "日" else 0.0]
                rows.append((d["date"], d["race_id"], base, blood, (r["corner_pos"][0] - 1) / max(1, n - 1),
                             r["corner_pos"][0] == lead))
        for r in rs:
            p = P.get(r["horse_id"])
            pos = (r["corner_pos"][0] - 1) / max(1, n - 1)
            if p:
                for key in ((p["sire"], d["surface"]), ("BMS:" + str(p.get("damsire")), d["surface"])):
                    s = S[key]
                    s[0] += 1; s[1] += pos; s[2] += r["corner_pos"][0] == 1
                mu[0] += 1; mu[1] += pos
            j = J[r.get("jockey")]
            j[0] += 1; j[1] += r["corner_pos"][0] <= 3
    races = sorted({(x[0], x[1]) for x in rows})
    cut = races[len(races) * 6 // 10]
    print(f"新馬戦 {len(races)}鞍 / 学習 〜{cut[0]} / 検証 {len(races) - len(races) * 6 // 10}鞍")
    params = {"objective": "regression", "learning_rate": 0.03, "num_leaves": 7, "min_data_in_leaf": 40, "verbose": -1}
    for nm, use_blood in (("基本(枠・騎手)", False), ("基本＋血統", True)):
        X = np.array([b + (bl if use_blood else []) for _, _, b, bl, _, _ in rows], dtype=float)
        y = np.array([t for *_, t, _ in rows])
        tr = np.array([(x[0], x[1]) < cut for x in rows])
        m = lgb.train(params, lgb.Dataset(X[tr], y[tr]), num_boost_round=300)
        pr = m.predict(X[~tr])
        te = [x for x, t in zip(rows, tr) if not t]
        by = collections.defaultdict(list)
        for x, p in zip(te, pr):
            by[x[1]].append((p, x[4], x[5]))
        rho, h1, h3 = [], 0, 0
        for v in by.values():
            a = [p for p, _, _ in v]; b = [t for _, t, _ in v]
            ra = np.argsort(np.argsort(a)); rb = np.argsort(np.argsort(b))
            rho.append(np.corrcoef(ra, rb)[0, 1])
            o = sorted(v)
            h1 += o[0][2]; h3 += any(z[2] for z in o[:3])
        print(f"  {nm:14s} 1角順位の相関 {np.mean(rho):+.3f}  ハナ1頭目 {h1/len(by):.1%}  上位3頭 {h3/len(by):.1%}")


if __name__ == "__main__":
    main()
