"""agg.json → 距離別・クラス別の 騎手/厩舎/父 トップを整形出力。"""
import json, re
d = json.load(open("agg.json"))

def clean(s):
    return re.sub(r"\s+", "", s) if s else s

def top(cat, dim, by="good", minrun=1, n=6):
    m = d[cat].get(dim, {})
    items = [(clean(k), v[1], v[0], v[1]/v[0]) for k, v in m.items() if k and v[0] >= minrun]
    items.sort(key=lambda x: (x[1] if by == "good" else x[3], x[1]), reverse=True)
    return items[:n]

def show(dim, title, minrun_rate):
    print(f"\n========== {title} ==========")
    for cat, lbl in [("kisyu","騎手"),("kyusya","厩舎"),("sire","父")]:
        gg = top(cat, dim, "good", 1, 5)
        rr = top(cat, dim, "rate", minrun_rate, 5)
        print(f"[{lbl}] 好走数: " + " / ".join(f"{k}{g}勝負({run}走{rate*100:.0f}%)" for k,g,run,rate in gg))
        print(f"[{lbl}] 複勝率(≥{minrun_rate}走): " + " / ".join(f"{k}{rate*100:.0f}%({g}/{run})" for k,g,run,rate in rr))

print(f"総レース数 {d['nr']}R（2025年7-8月 大井）")
show("ALL", "全体", 10)
for dist in [1200, 1400, 1600, 1800, 2000]:
    dim = f"D{dist}"
    if dim in d["kisyu"]:
        show(dim, f"距離 {dist}m", 5)
for kl in ["2歳", "3歳", "C級", "B級", "A・OP"]:
    dim = f"K{kl}"
    if dim in d["kisyu"]:
        show(dim, f"クラス {kl}", 5)
# レース数内訳
print("\n--- 距離×クラスのレース数分布 ---")
from collections import Counter
