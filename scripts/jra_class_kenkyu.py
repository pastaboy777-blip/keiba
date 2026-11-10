"""研究: クラス・年齢条件・グレードを足すと、ペース想定と推定時計はどこまで良くなるか。

    python3 scripts/jra_class_kenkyu.py --data data/jra/races.jsonl

クラスが記録されている鞍(JRA公式から取った分)だけを使い、時系列で前 2/3 学習・後 1/3 検証。
土台は jra_pace_model / jra_time_model と同じ「コース平均 + 馬場」。その残差をクラス等で説明する。
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
from jra_time_model import TimeModel, target  # noqa: E402
from nankeiba.scraping.db_race import pace_of  # noqa: E402

CLASSES = ["新馬", "未勝利", "1勝クラス", "2勝クラス", "3勝クラス", "オープン"]
TYPES = ["2歳", "3歳", "3歳以上", "4歳以上"]


def cls_x(d):
    c = d.get("race_class") or ""
    t = d.get("race_type") or ""
    g = d.get("grade") or ""
    x = [1.0 if c.startswith(k) else 0.0 for k in CLASSES]
    x += [1.0 if t == k else 0.0 for k in TYPES]
    x += [1.0 if g.startswith("G") else 0.0]
    return x


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/jra/races.jsonl")
    a = ap.parse_args()
    raw = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    raw = [d for d in raw if d.get("surface") in ("芝", "ダ") and d.get("race_class")
           and pace_of(d.get("lap") or [], d["distance"]) and d["result"][0].get("time")]
    raw.sort(key=lambda d: (d["date"], d["race_id"]))
    cut = raw[int(len(raw) * 2 / 3)]["date"]
    tr = [d for d in raw if d["date"] < cut]
    te = [d for d in raw if d["date"] >= cut]
    print(f"クラスのある鞍 {len(raw)}(期間 {raw[0]['date']}〜{raw[-1]['date']})  学習 {len(tr)} / 検証 {len(te)}(境 {cut})")
    cnt = collections.Counter((d["race_class"] or "")[:4] for d in raw)
    print("  クラス内訳:", dict(cnt.most_common(8)))

    for k, lab in [("diff", "前後半差(ペース)"), ("front3", "前半3F"), ("last3", "後半3F"), ("time", "勝ちタイム")]:
        key = "front3" if k == "diff" else k
        get = (lambda d: pace_of(d["lap"], d["distance"])["diff"]) if k == "diff" else (lambda d, kk=key: target(d, kk))
        if k == "diff":
            # PaceModel 相当: TimeModel の仕組みを前後半差に流用
            m = TimeModel("front3")
            m.k = "front3"
            ys = [get(d) for d in tr]
            import jra_pace_model as P
            pm = P.PaceModel().fit(tr)
            base_tr = [pm.predict(d) for d in tr]
            base_te = [pm.predict(d) for d in te]
        else:
            tm = TimeModel(k).fit(tr)
            base_tr = [tm.predict(d) for d in tr]
            base_te = [tm.predict(d) for d in te]
        y_tr = [get(d) for d in tr]
        y_te = [get(d) for d in te]
        w = J.ols([cls_x(d) for d in tr], [y - b for y, b in zip(y_tr, base_tr)])
        add = [sum(wi * xi for wi, xi in zip(w, cls_x(d))) for d in te]
        e0 = st.mean(abs(y - b) for y, b in zip(y_te, base_te))
        e1 = st.mean(abs(y - b - c) for y, b, c in zip(y_te, base_te, add))
        line = f"  {lab:<14s} 平均誤差 コース+馬場 {e0:.3f}秒 → +クラス {e1:.3f}秒"
        if k == "diff":
            v = sorted(y_tr)
            q = (v[len(v) // 3], v[2 * len(v) // 3])
            cl = lambda x: "H" if x < q[0] else ("S" if x > q[1] else "M")  # noqa: E731
            h0 = st.mean(cl(b) == cl(y) for y, b in zip(y_te, base_te))
            h1 = st.mean(cl(b + c) == cl(y) for y, b, c in zip(y_te, base_te, add))
            line += f"   3区分の的中 {h0:.1%} → {h1:.1%}"
        print(line)
        print("     係数(秒): " + "  ".join(f"{n} {wi:+.2f}" for n, wi in zip(CLASSES + TYPES + ["重賞"], w)))


if __name__ == "__main__":
    main()
