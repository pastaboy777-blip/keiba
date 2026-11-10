"""研究: ハナ(1角先頭)を当てることだけに絞ったモデルで、的中率はどこまで上がるか。

    python3 scripts/jra_hana_kenkyu.py --data data/jra/races.jsonl

今の方法 = 隊列予想(序盤位置の直近加重)の1番手。比べるのは「先頭になったか(0/1)」を直接学習したモデル。
特徴: 逃げ率・序盤位置・過去の最小1角位置・前走の1角・同条件での逃げ率・騎手の癖・枠・距離変更・頭数。
前 2/3 学習・後 1/3 検証(履歴7割以上の鞍)。上位2頭・3頭に入る率も出す。
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
from nankeiba.core import dataset as ds, tenkai as tk  # noqa: E402
from nankeiba.core.backtest import record_result  # noqa: E402

F = ["1", "nige", "early", "min_c1", "last_c1", "last_lead", "sim_nige", "jk_bias", "gate", "gate_x_short",
     "dist_diff", "n_runs", "field"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/jra/races.jsonl")
    a = ap.parse_args()
    raw = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    raw = [d for d in raw if d.get("surface") in ("芝", "ダ")]
    raw.sort(key=lambda d: (d["date"], d["race_id"]))
    h: dict = {}
    jk = collections.defaultdict(list)
    R = []
    for d in raw:
        r = ds.race_from_dict(d)
        n = len(r.entries)
        rows = []
        for e in r.entries:
            past = h.get(e.horse_id, [])
            runs = [x for x in past if x.corner_pos and x.field_size > 1]
            sp = tk.style_profile(past)
            sim = [x for x in runs if x.surface == r.surface and abs(x.distance - r.distance) <= 200]
            jb = jk.get(e.jockey) or []
            last = runs[0] if runs else None
            gate = ((e.umaban or 1) - 1) / max(1, n - 1)
            f = {"1": 1.0, "nige": sp.nige_rate, "early": sp.early_or(0.5),
                 "min_c1": min((x.corner_pos[0] - 1) / (x.field_size - 1) for x in runs) if runs else 0.5,
                 "last_c1": (last.corner_pos[0] - 1) / (last.field_size - 1) if last else 0.5,
                 "last_lead": 1.0 if last and last.corner_pos[0] == 1 else 0.0,
                 "sim_nige": (sum(x.corner_pos[0] == 1 for x in sim) / len(sim)) if sim else sp.nige_rate,
                 "jk_bias": (sum(jb) / (len(jb) + 10)) if jb else 0.0,
                 "gate": gate, "gate_x_short": gate * (1.0 if r.distance <= 1400 else 0.0),
                 "dist_diff": ((r.distance - past[0].distance) / 1000) if past else 0.0,
                 "n_runs": min(len(runs), 5) / 5, "field": n / 18}
            if e.corner_pos:
                rows.append({"x": f, "lead": 1.0 if e.corner_pos[0] == 1 else 0.0, "known": sp.early is not None})
        if len(rows) >= 8 and sum(y["lead"] for y in rows) == 1:
            R.append({"date": d["date"], "rows": rows, "known": st.mean(y["known"] for y in rows)})
        for e in r.entries:
            sp = tk.style_profile(h.get(e.horse_id, []))
            if e.corner_pos and sp.early is not None and e.jockey and n > 1:
                jk[e.jockey].append((e.corner_pos[0] - 1) / (n - 1) - sp.early)
        record_result(r, h)

    R = [q for q in R if q["known"] >= 0.7]
    cut = R[int(len(R) * 2 / 3)]["date"]
    tr = [q for q in R if q["date"] < cut]
    te = [q for q in R if q["date"] >= cut]
    w = J.ols([[y["x"][k] for k in F] for q in tr for y in q["rows"]], [y["lead"] for q in tr for y in q["rows"]], l2=1e-3)
    score = lambda y: sum(wi * y["x"][k] for wi, k in zip(w, F))  # noqa: E731

    def topk(q, key, k, rev):
        o = sorted(q["rows"], key=key, reverse=rev)[:k]
        return any(y["lead"] for y in o)

    print(f"学習 {len(tr)}鞍 / 検証 {len(te)}鞍(境 {cut})  当てずっぽう ≒ {st.mean(1 / len(q['rows']) for q in te):.1%}")
    for name, key, rev in [("今(序盤位置の1番手)", lambda y: y["x"]["early"], False),
                           ("逃げ率の1番手", lambda y: (y["x"]["nige"], -y["x"]["early"]), True),
                           ("ハナ専用モデル", score, True)]:
        print(f"  {name:<18s} 1番手が的中 {st.mean(topk(q, key, 1, rev) for q in te):.1%}"
              f" / 上位2頭に入る {st.mean(topk(q, key, 2, rev) for q in te):.1%}"
              f" / 上位3頭に入る {st.mean(topk(q, key, 3, rev) for q in te):.1%}")
    # 確度: 1番手と2番手のスコア差
    gaps = []
    for q in te:
        o = sorted(q["rows"], key=score, reverse=True)
        gaps.append((score(o[0]) - score(o[1]), o[0]["lead"]))
    gaps.sort(key=lambda g: -g[0])
    k = len(gaps) // 3
    print(f"  確度(1番手と2番手の差)上位1/3の鞍: 的中 {st.mean(g[1] for g in gaps[:k]):.1%} / 下位1/3: {st.mean(g[1] for g in gaps[-k:]):.1%}")
    print("  係数: " + "  ".join(f"{k_} {wi:+.3f}" for k_, wi in zip(F, w)))
    json.dump({"features": F, "coef": w, "cut": cut},
              open(Path(__file__).resolve().parents[1] / "models" / "hana_model.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
