"""研究: ペースの「決め方」で、決着の形(3着内の馬の4角位置)がどれだけ分かれるか。

    python3 scripts/jra_pace_teigi.py

決め方 3通り(どれも3等分):
  A いま … 前後差(前半3F−後半3F)そのまま
  B コース比の前後差 … 前後差 − コース平均(PaceModel)
  C コース比のテン … 前半3F − コース平均(TimeModel front3)  ※note むねひろ の言い方に近い
各区分で 3着内の馬の4角相対位置(0=先頭, 1=最後方) の平均と「4角前1/3から3着内」の割合。
S と H の差が大きいほど、その決め方は決着の形をよく言い当てる。
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from jra_pace_model import PaceModel  # noqa: E402
from jra_time_model import TimeModel  # noqa: E402
from nankeiba.scraping.db_race import pace_of  # noqa: E402

raw = [json.loads(l) for l in open("data/jra/races.jsonl")]
raw = [d for d in raw if d.get("surface") in ("芝", "ダ") and pace_of(d.get("lap") or [], d["distance"])
       and d["result"][0].get("time") and d["field_size"] >= 8]
pm = PaceModel().fit(raw)
tf = TimeModel("front3").fit(raw)
X = {"A": [], "B": [], "C": []}
for d in raw:
    pc = pace_of(d["lap"], d["distance"])
    X["A"].append(pc["diff"])
    X["B"].append(pc["diff"] - pm.predict(d))
    X["C"].append(-(pc["front3"] - tf.predict(d)))      # +ほどテンが遅い=スロー
pos = []
for d in raw:
    n = d["field_size"]
    ps = [(r["corner_pos"][-1] - 1) / (n - 1) for r in d["result"] if r["finish_pos"] <= 3 and r.get("corner_pos")]
    pos.append(ps)
for key, nm in (("A", "いま(前後差そのまま)"), ("B", "コース比の前後差"), ("C", "コース比のテン")):
    v = sorted(X[key])
    q = (v[len(v) // 3], v[2 * len(v) // 3])
    out = {}
    for lab in ("S", "M", "H"):
        ps = [p for x, ps in zip(X[key], pos) if (("H" if x < q[0] else "S" if x > q[1] else "M") == lab) for p in ps]
        out[lab] = (st.mean(ps), sum(p <= 1 / 3 for p in ps) / len(ps))
    print(f"{nm:14s}  S: 位置{out['S'][0]:.3f} 前から{out['S'][1]:.1%}   M: {out['M'][0]:.3f} {out['M'][1]:.1%}   "
          f"H: {out['H'][0]:.3f} {out['H'][1]:.1%}   → S−H 差 {out['H'][0]-out['S'][0]:.3f} / {out['S'][1]-out['H'][1]:.1%}")
# 組み合わせ: B と C の両方が同じ向きなら強く言える
v = sorted(X["B"]); qb = (v[len(v) // 3], v[2 * len(v) // 3])
v = sorted(X["C"]); qc = (v[len(v) // 3], v[2 * len(v) // 3])
cl = lambda x, q: "H" if x < q[0] else "S" if x > q[1] else "M"  # noqa: E731
for lab in ("S", "H"):
    ps = [p for b, c, ps in zip(X["B"], X["C"], pos) if cl(b, qb) == lab and cl(c, qc) == lab for p in ps]
    print(f"B と C が両方 {lab}: 3着内の位置 {st.mean(ps):.3f} 前から {sum(p <= 1/3 for p in ps)/len(ps):.1%} (馬 {len(ps)})")
