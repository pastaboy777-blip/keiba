"""3年分から、ペース(スロー/ミドル/ハイ)の特徴を見つける。

    python3 scripts/jra_pace_tokucho.py --data data/jra/races.jsonl

1. コース(場×芝ダ×距離)ごとの スロー/ミドル/ハイ の割合と前半3F・後半3F。ハイになりやすい／スローになりやすいコース
2. ペースが動く条件: 頭数・クラス・馬場・季節・2歳戦(同じコースの中で比べるため、コース平均からのずれで見る)
3. 想定が外れやすいコース(ずれの大きさ)
区分の境は全鞍の前後半差の三分位。
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.scraping.db_race import pace_of  # noqa: E402


def klass(d):
    c = (d.get("race_class") or "") + (d.get("name") or "")
    for k in ("新馬", "未勝利", "1勝", "2勝", "3勝"):
        if k in c:
            return k
    if d.get("grade"):
        return "重賞"
    return "OP/特別" if c else "不明"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/jra/races.jsonl")
    a = ap.parse_args()
    R = []
    for l in open(a.data, encoding="utf-8"):
        d = json.loads(l)
        if d.get("surface") in ("芝", "ダ"):
            p = pace_of(d.get("lap") or [], d["distance"])
            if p:
                R.append((d, p))
    v = sorted(p["diff"] for _, p in R)
    q = (v[len(v) // 3], v[2 * len(v) // 3])
    cl = lambda x: "H" if x < q[0] else ("S" if x > q[1] else "M")  # noqa: E731
    print(f"{len(R)}鞍。区分の境: 前後半差 {q[0]:+.2f}秒より前傾=ハイ / {q[1]:+.2f}秒より後傾=スロー\n")

    C = collections.defaultdict(list)
    for d, p in R:
        C[(d["place"], d["surface"], d["distance"])].append((d, p))
    cmean = {k: st.mean(p["diff"] for _, p in g) for k, g in C.items()}
    rows = []
    for k, g in C.items():
        if len(g) >= 30:
            c = collections.Counter(cl(p["diff"]) for _, p in g)
            rows.append((k, len(g), c["S"] / len(g), c["M"] / len(g), c["H"] / len(g),
                         st.mean(p["front3"] for _, p in g), st.mean(p["last3"] for _, p in g),
                         st.pstdev(p["diff"] for _, p in g)))
    print("== 1. コースごとのペースの癖(30鞍以上) ==")
    print("  ハイになりやすいコース(ハイの割合 上位10)")
    for k, n, s_, m_, h_, f3, l3, sd in sorted(rows, key=lambda r: -r[4])[:10]:
        print(f"    {k[0]}{k[1]}{k[2]:>4}m n={n:3d}  S{s_:4.0%} M{m_:4.0%} H{h_:4.0%}  前半3F {f3:.1f} 後半3F {l3:.1f}")
    print("  スローになりやすいコース(スローの割合 上位10)")
    for k, n, s_, m_, h_, f3, l3, sd in sorted(rows, key=lambda r: -r[2])[:10]:
        print(f"    {k[0]}{k[1]}{k[2]:>4}m n={n:3d}  S{s_:4.0%} M{m_:4.0%} H{h_:4.0%}  前半3F {f3:.1f} 後半3F {l3:.1f}")
    print("  どれにも偏らない=読みにくいコース(いちばん多い区分でも50%未満、ずれのばらつき大きい順)")
    for k, n, s_, m_, h_, f3, l3, sd in sorted([r for r in rows if max(r[2:5]) < 0.5], key=lambda r: -r[7])[:10]:
        print(f"    {k[0]}{k[1]}{k[2]:>4}m n={n:3d}  S{s_:4.0%} M{m_:4.0%} H{h_:4.0%}  ばらつき {sd:.2f}秒")

    print("\n== 2. ペースが動く条件(同じコースの平均からのずれ。+はスロー寄り、−はハイ寄り) ==")
    def eff(lab, f):
        g = collections.defaultdict(list)
        for d, p in R:
            k = (d["place"], d["surface"], d["distance"])
            if len(C[k]) >= 30:
                g[f(d)].append(p["diff"] - cmean[k])
        print(f"  [{lab}]  " + "  ".join(f"{kk} {st.mean(x):+.2f}(n={len(x)})" for kk, x in sorted(g.items(), key=lambda t: str(t[0])) if len(x) >= 50))
    eff("頭数", lambda d: "〜10頭" if d["field_size"] <= 10 else ("11〜14頭" if d["field_size"] <= 14 else "15頭〜"))
    eff("クラス", klass)
    eff("馬場(芝)", lambda d: d.get("baba") if d["surface"] == "芝" else None)
    eff("馬場(ダ)", lambda d: d.get("baba") if d["surface"] == "ダ" else None)
    eff("季節", lambda d: {12: "冬", 1: "冬", 2: "冬", 3: "春", 4: "春", 5: "春", 6: "夏", 7: "夏", 8: "夏"}.get(int(d["date"][5:7]), "秋"))
    eff("R番号", lambda d: "1-4R" if int(d["race_id"][-2:]) <= 4 else ("5-8R" if int(d["race_id"][-2:]) <= 8 else "9-12R"))


if __name__ == "__main__":
    main()
