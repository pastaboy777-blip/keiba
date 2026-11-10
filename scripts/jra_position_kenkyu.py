"""研究: JRA公式の新しい項目(斤量・馬体重・増減・年齢・間隔・昇級/降級)で隊列(前後)の想定は良くなるか。

    python3 scripts/jra_position_kenkyu.py --data data/jra/races.jsonl

jra_position_model2.py の全特徴量を土台に、新しい項目を1つずつ足して検証区間の順位相関を比べる。
対象は新しい項目がある鞍(JRA公式から取った分)。前 2/3 学習・後 1/3 検証。
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import statistics as st
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import jra_learn as J  # noqa: E402
from nankeiba.core import dataset as ds, tenkai as tk  # noqa: E402
from nankeiba.core.backtest import record_result  # noqa: E402

BASE = ["1", "early", "known", "nige", "med_c4", "sim_c1", "sim_c4", "has_sim", "dist_diff", "surf_change",
        "gain", "jk_bias"]
CLASS_RANK = {"新馬": 0, "未勝利": 0, "1勝": 1, "2勝": 2, "3勝": 3, "オープン": 4}
STEPS = [("+斤量(鞍の平均との差)", ["kin"]), ("+馬体重(鞍の平均との差)", ["wt"]), ("+増減", ["dwt"]),
         ("+年齢", ["age"]), ("+間隔(長い休み明け)", ["layoff", "short"]), ("+昇級・降級", ["up", "down"])]


def norm(r, i):
    return (r.corner_pos[i] - 1) / max(1, r.field_size - 1)


def crank(c):
    for k, v in CLASS_RANK.items():
        if (c or "").startswith(k):
            return v
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/jra/races.jsonl")
    a = ap.parse_args()
    raw = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    raw = [d for d in raw if d.get("surface") in ("芝", "ダ")]
    raw.sort(key=lambda d: (d["date"], d["race_id"]))
    h: dict = {}
    jk = collections.defaultdict(list)
    last_cls: dict = {}
    R = []
    for d in raw:
        r = ds.race_from_dict(d)
        n = len(r.entries)
        res = {x["umaban"]: x for x in d["result"]}
        has_new = d.get("source") == "jra.go.jp"
        kins = [x.get("kinryo") for x in d["result"] if x.get("kinryo")]
        wts = [x.get("weight") for x in d["result"] if x.get("weight")]
        rows = []
        for e in r.entries:
            past = h.get(e.horse_id, [])
            runs = [x for x in past if x.corner_pos and x.field_size > 1]
            sp = tk.style_profile(past)
            sim = [x for x in runs if x.surface == r.surface and abs(x.distance - r.distance) <= 200]
            early = sp.early_or(0.5)
            last = past[0] if past else None
            x = res.get(e.num(), {})
            jb = jk.get(e.jockey) or []
            iv = (date.fromisoformat(d["date"]) - date.fromisoformat(last.date)).days if last else None
            age = re.search(r"\d+", x.get("sex_age") or "")
            cr, lc = crank(d.get("race_class")), last_cls.get(e.horse_id)
            f = {"1": 1.0, "early": early, "known": 1.0 if sp.early is not None else 0.0, "nige": sp.nige_rate,
                 "med_c4": st.median(norm(y, -1) for y in runs) if runs else 0.5,
                 "sim_c1": st.median(norm(y, 0) for y in sim) if sim else early,
                 "sim_c4": st.median(norm(y, -1) for y in sim) if sim else early,
                 "has_sim": 1.0 if sim else 0.0,
                 "dist_diff": ((r.distance - last.distance) / 1000) if last else 0.0,
                 "surf_change": 1.0 if last and last.surface and last.surface != r.surface else 0.0,
                 "gain": st.median(norm(y, 0) - norm(y, -1) for y in runs) if runs else 0.0,
                 "jk_bias": (sum(jb) / (len(jb) + 10)) if jb else 0.0,
                 "kin": ((x.get("kinryo") or 0) - st.mean(kins)) if kins and x.get("kinryo") else 0.0,
                 "wt": ((x.get("weight") or 0) - st.mean(wts)) / 20 if wts and x.get("weight") else 0.0,
                 "dwt": (x.get("weight_diff") or 0) / 10,
                 "age": (int(age.group()) - 4) if age else 0.0,
                 "layoff": 1.0 if iv and iv >= 90 else 0.0, "short": 1.0 if iv is not None and iv <= 21 else 0.0,
                 "up": 1.0 if cr is not None and lc is not None and cr > lc else 0.0,
                 "down": 1.0 if cr is not None and lc is not None and cr < lc else 0.0}
            if e.corner_pos and n > 1:
                rows.append({"x": f, "c1": (e.corner_pos[0] - 1) / (n - 1), "c4": (e.corner_pos[-1] - 1) / (n - 1)})
        if has_new and len(rows) >= 8:
            R.append({"date": d["date"], "rows": rows, "known": st.mean(y["x"]["known"] for y in rows)})
        for e in r.entries:
            sp = tk.style_profile(h.get(e.horse_id, []))
            if e.corner_pos and sp.early is not None and e.jockey and n > 1:
                jk[e.jockey].append((e.corner_pos[0] - 1) / (n - 1) - sp.early)
            c = crank(d.get("race_class"))
            if c is not None:
                last_cls[e.horse_id] = c
        record_result(r, h)

    R = [q for q in R if q["known"] >= 0.7]
    cut = R[int(len(R) * 2 / 3)]["date"]
    tr = [q for q in R if q["date"] < cut]
    te = [q for q in R if q["date"] >= cut]
    print(f"新しい項目のある鞍(履歴7割以上) 学習 {len(tr)} / 検証 {len(te)}(境 {cut})")

    def ev(feats, tgt):
        w = J.ols([[y["x"][k] for k in feats] for q in tr for y in q["rows"]], [y[tgt] for q in tr for y in q["rows"]], l2=1e-3)
        cs = [J.rank_corr([sum(wi * y["x"][k] for wi, k in zip(w, feats)) for y in q["rows"]], [y[tgt] for y in q["rows"]]) for q in te]
        return st.mean(c for c in cs if c == c), w

    for tgt, lab in [("c1", "1角"), ("c4", "4角")]:
        feats = list(BASE)
        c, _ = ev(feats, tgt)
        print(f"\n== {lab} ==  土台(今のモデル) {c:+.4f}")
        for name, add in STEPS:
            c1, w = ev(feats + add, tgt)
            print(f"  {name:<22s} {c1:+.4f} ({c1 - c:+.4f})   係数 " + " ".join(f"{k} {w[len(feats) + i]:+.3f}" for i, k in enumerate(add)))
        c_all, w = ev(feats + [k for _, ad in STEPS for k in ad], tgt)
        print(f"  全部足す                 {c_all:+.4f} ({c_all - c:+.4f})")


if __name__ == "__main__":
    main()
