#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""条件ごとの回収率を測る。南関キャッシュのみで完結。

測る条件:
  ① メンバー軸  … レベルの高いレースで4着以下だった馬
  ② 逆張り軸    … その日いちばん不利だった位置を通り、僅差で4着以下だった馬
  ③ ①×②       … 両方に該当

塞いだリーク（両方とも塞がないと回収率が上振れする）:
  ・買う馬自身の次走をレベルの材料から抜く
      抜かないと、その馬が勝ったことでレースのレベルが上がり、
      そのレベルを根拠にその馬を買う、という循環になる（勝ちを二度数える）。
  ・買う時点より後に走った後続もレベルの材料から抜く
      当日には見えない情報だから。

払戻は当該レースのpay_table（単勝・複勝）を使う。

使い方:
  python3 scripts/ana/kaishu.py                 # 南関全場
  python3 scripts/ana/kaishu.py --place 船橋
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import h2h
from gyakubari import parse
from nar_day import KEYS, classify


def payouts(fn):
    """{単勝: {馬番: 円}, 複勝: {馬番: 円}}"""
    t = open(fn, "rb").read().decode("euc-jp", errors="replace")
    out = {"単勝": {}, "複勝": {}}
    for m in re.finditer(r'<table[^>]*class="pay_table_01[^"]*"[^>]*>(.*?)</table>', t, re.S):
        for tr in re.findall(r"<tr>(.*?)</tr>", m.group(1), re.S):
            cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "|", c)).strip()
                     for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)]
            if len(cells) < 3:
                continue
            lab = cells[0].strip("| ")
            if lab not in ("単勝", "複勝"):
                continue
            nums = [z for z in re.split(r"\|+", cells[1]) if z.strip().isdigit()]
            yen = [z.replace(",", "") for z in re.split(r"\|+", cells[2]) if z.replace(",", "").strip().isdigit()]
            for n, y in zip(nums, yen):
                out[lab][int(n)] = int(y)
    return out


def load(place):
    races = []
    for fn in sorted(glob.glob(os.path.join(h2h.CACHE, "2026*.html"))):
        if os.path.getsize(fn) < 20000:
            continue
        p = parse(fn)
        if not p or (place and p["place"] != place):
            continue
        p["fn"] = fn
        races.append(p)
    races.sort(key=lambda z: (z["date"], z["place"], z["rn"]))
    return races


def main():
    ap = argparse.ArgumentParser(description="条件別の回収率")
    ap.add_argument("--place", help="場を絞る")
    ap.add_argument("--sa", type=float, default=0.6, help="逆張り軸：勝ち馬との秒差の上限")
    ap.add_argument("--min-lift", type=float, default=0.85, help="逆張り軸：この倍率未満を不利とみなす")
    ap.add_argument("--lv-min", type=float, default=2.0, help="メンバー軸：敗者巻き返しが基準の何倍以上か")
    args = ap.parse_args()

    R = load(args.place)
    print(f"■ 対象 {len(R)}レース（{R[0]['date']}〜{R[-1]['date']}）")

    idx = {(r["date"], r["place"], r["rn"]): i for i, r in enumerate(R)}
    seq = defaultdict(list)
    for i, r in enumerate(R):
        for h in r["rows"]:
            seq[h["name"]].append(i)
    for n in seq:
        seq[n].sort()

    # ── メンバー軸（リークを塞いだ版）─────────────────────────
    def member_lift(i, exclude_horse, asof):
        """レースiの敗者巻き返し率。exclude_horse を除き、asof より後の次走も除く。"""
        r = R[i]
        w = n = 0
        for h in r["rows"]:
            if h["chaku"] < 4 or h["name"] == exclude_horse:
                continue
            s = seq[h["name"]]
            k = next((q for q, j in enumerate(s) if j == i), None)
            if k is None or k + 1 >= len(s):
                continue
            j = s[k + 1]
            if R[j]["date"] >= asof:            # 買う時点で見えない
                continue
            fin = next((z["chaku"] for z in R[j]["rows"] if z["name"] == h["name"]), None)
            if fin is None:
                continue
            n += 1
            if fin == 1:
                w += 1
        return (w, n)

    base_w = base_n = 0
    for i, r in enumerate(R):
        for h in r["rows"]:
            if h["chaku"] < 4:
                continue
            s = seq[h["name"]]
            k = next((q for q, j in enumerate(s) if j == i), None)
            if k is None or k + 1 >= len(s):
                continue
            fin = next((z["chaku"] for z in R[s[k+1]]["rows"] if z["name"] == h["name"]), None)
            if fin is not None:
                base_n += 1
                base_w += (fin == 1)
    base = base_w / base_n
    print(f"  敗者の次走勝率（全体基準）{base*100:.1f}%  n={base_n}\n")

    # ── 逆張り軸 ─────────────────────────────────────────
    daylift = {}
    byday = defaultdict(list)
    for i, r in enumerate(R):
        byday[(r["date"], r["place"])].append(i)
    for k, ids in byday.items():
        tot, hit = Counter(), Counter()
        for i in ids:
            cl = classify(R[i]["c4"])
            for h in R[i]["rows"]:
                p = cl.get(h["ub"], ("?", 0))[0]
                tot[p] += 1
                if h["chaku"] <= 3:
                    hit[p] += 1
        N = sum(tot.values()); b = sum(hit.values()) / N if N else 0
        daylift[k] = {p: (hit[p]/tot[p]/b if tot[p] and b else None) for p in KEYS}

    groups = defaultdict(list)          # ラベル -> [(次走index, 馬番, 馬名)]
    for i, r in enumerate(R):
        cl = classify(r["c4"])
        L = daylift[(r["date"], r["place"])]
        wt = next((h["t"] for h in r["rows"] if h["chaku"] == 1), None)
        for h in r["rows"]:
            if h["chaku"] < 4:
                continue
            s = seq[h["name"]]
            k = next((q for q, j in enumerate(s) if j == i), None)
            if k is None or k + 1 >= len(s):
                continue
            j = s[k + 1]
            asof = R[j]["date"]
            # ② 逆張り
            p, _ = cl.get(h["ub"], ("?", 0))
            gy = (L.get(p) is not None and L[p] < args.min_lift
                  and wt is not None and h["t"] is not None and (h["t"] - wt) <= args.sa)
            # ① メンバー
            w2, n2 = member_lift(i, h["name"], asof)
            mb = (n2 >= 4 and base > 0 and (w2 / n2) / base >= args.lv_min)
            rec = (j, next((z["ub"] for z in R[j]["rows"] if z["name"] == h["name"]), None), h["name"])
            groups["無差別（4着以下の全馬）"].append(rec)
            if mb: groups["①メンバー軸のみ"].append(rec)
            if gy: groups["②逆張り軸のみ"].append(rec)
            if mb and gy: groups["③両方に該当"].append(rec)

    print(f"  {'条件':<22}{'頭数':>6}{'1着':>6}{'3着内':>7}{'単回収':>8}{'複回収':>8}")
    for lab in ["無差別（4着以下の全馬）", "①メンバー軸のみ", "②逆張り軸のみ", "③両方に該当"]:
        v = groups[lab]
        if not v:
            print(f"  {lab:<22}{'該当なし':>6}")
            continue
        n = w = pl = 0; tan = fuku = 0
        for j, ub, nm in v:
            if ub is None:
                continue
            fin = next((z["chaku"] for z in R[j]["rows"] if z["name"] == nm), None)
            if fin is None:
                continue
            pay = payouts(R[j]["fn"])
            n += 1
            if fin == 1:
                w += 1; tan += pay["単勝"].get(ub, 0)
            if fin <= 3:
                pl += 1; fuku += pay["複勝"].get(ub, 0)
        if not n:
            continue
        print(f"  {lab:<22}{n:>6}{w:>6}{pl:>7}{tan/(n*100)*100:>7.0f}%{fuku/(n*100)*100:>7.0f}%")
    print("\n  ※リークは2つとも塞いである（買う馬自身を材料から除外／買う時点より後の次走を除外）。")


if __name__ == "__main__":
    main()
