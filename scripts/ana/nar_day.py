#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""南関の開催日を1日ずつ分析する（netkeibaキャッシュから）。

出すもの:
  ① 4角のポジション別 3着内率（先頭／ラチ沿い追走／外を回す／単独）
     通過順位の括弧は併走で、括弧内は内側の馬から順に書かれる規約を使う。
  ② 枠（内／中／外）
  ③ ペース（前半3F-後半3F）と上がり水準
  ④ 人気と配当（1着馬の人気、単勝・三連単の中央値）
  ⑤ 前半1-6R と 後半7-12R の差

使い方:
  python3 scripts/ana/nar_day.py 船橋 --from 2026-05-01 --to 2026-06-30
  python3 scripts/ana/nar_day.py 川崎 --from 2026-07-27
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import h2h

KEYS = ["先頭", "ラチ沿い追走", "外を回す", "単独"]


def parse(fn):
    t = open(fn, "rb").read().decode("euc-jp", errors="replace")
    hd = re.search(r"(20\d\d)年(\d+)月(\d+)日.{0,50}?(大井|川崎|船橋|浦和)",
                   re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)))
    if not hd:
        return None
    d = f"{hd.group(1)}-{int(hd.group(2)):02d}-{int(hd.group(3)):02d}"
    x = re.sub(r"<[^>]+>", "|", t); x = re.sub(r"[ 　]+", " ", x); x = re.sub(r"\|{3,}", "||", x)
    fy = re.sub(r"\s+", " ", x)
    rows = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S):
        if "/horse/" not in r:
            continue
        c = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", z)).strip()
             for z in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
        if len(c) < 15 or not c[0].isdigit():
            continue
        nk = None
        for i, v in enumerate(c):
            if re.match(r"^\d+\.\d$", v) and i + 1 < len(c) and re.match(r"^\d+$", c[i+1]):
                nk = int(c[i+1]); break
        rows.append(dict(chaku=int(c[0]), waku=int(c[1]) if c[1].isdigit() else None,
                         ub=int(c[2]) if c[2].isdigit() else None, ninki=nk))
    c4 = re.search(r"4コーナー\| \|([^|]+)\|", fy)
    lap = re.search(r"ラップ\| \|([0-9.\- ]+)\|", fy)
    pace = re.search(r"\(([\d.]+)-([\d.]+)\)", fy)
    cond = re.search(r"(ダ|芝)(?:左|右|直)?(\d+)m.{0,60}?(良|稍重|重|不良)", fy)
    tan = re.search(r"単勝\| \|\d+\| \|([\d,]+)\|", fy)
    san = re.search(r"三連単\| \|[\d →]+\| \|([\d,]+)\|", fy)
    return dict(date=d, place=hd.group(4), rn=int(os.path.basename(fn)[-7:-5]),
                dist=(int(cond.group(2)) if cond else None), baba=(cond.group(3) if cond else "?"),
                rows=rows, c4=(c4.group(1).strip() if c4 else ""),
                laps=[float(v) for v in lap.group(1).split("-")] if lap else [],
                f3=(float(pace.group(1)) if pace else None),
                l3=(float(pace.group(2)) if pace else None),
                tan=(int(tan.group(1).replace(",", "")) if tan else None),
                san=(int(san.group(1).replace(",", "")) if san else None))


def classify(c4):
    out, rank = {}, 0
    for tok in re.findall(r"\([^)]*\)|\d+", c4):
        if tok.startswith("("):
            for k, u in enumerate(int(v) for v in re.findall(r"\d+", tok)):
                rank += 1
                out[u] = ("先頭" if rank == 1 else ("ラチ沿い追走" if k == 0 else "外を回す"), rank)
        else:
            rank += 1
            out[int(tok)] = ("先頭" if rank == 1 else "単独", rank)
    return out


def day_report(rs):
    tot, hit, win = Counter(), Counter(), Counter()
    H = {"前": [Counter(), Counter()], "後": [Counter(), Counter()]}
    wk = defaultdict(lambda: [0, 0])
    nin, tans, sans, l3s = [], [], [], []
    for r in rs:
        cl = classify(r["c4"]); n = len(r["rows"])
        half = "前" if r["rn"] <= 6 else "後"
        if r["tan"]: tans.append(r["tan"])
        if r["san"]: sans.append(r["san"])
        if r["l3"]: l3s.append((r["dist"], r["l3"]))
        for h in r["rows"]:
            k = cl.get(h["ub"], ("?", 0))[0]
            tot[k] += 1; H[half][0][k] += 1
            if h["chaku"] <= 3:
                hit[k] += 1; H[half][1][k] += 1
            if h["chaku"] == 1:
                win[k] += 1
                if h["ninki"]: nin.append(h["ninki"])
            if h["ub"] and n > 1:
                rel = (h["ub"] - 1) / (n - 1)
                w = "内" if rel < 0.34 else ("中" if rel < 0.67 else "外")
                wk[w][0] += 1
                if h["chaku"] <= 3: wk[w][1] += 1
    return tot, hit, win, H, wk, nin, tans, sans, l3s


def main():
    ap = argparse.ArgumentParser(description="南関の開催日を1日ずつ分析")
    ap.add_argument("place", help="大井/川崎/船橋/浦和")
    ap.add_argument("--from", dest="dfrom", default="2026-01-01")
    ap.add_argument("--to", dest="dto", default="2026-12-31")
    args = ap.parse_args()

    byday = defaultdict(list)
    for fn in sorted(glob.glob(os.path.join(h2h.CACHE, "2026*.html"))):
        if os.path.getsize(fn) < 20000:
            continue
        p = parse(fn)
        if p and p["place"] == args.place and args.dfrom <= p["date"] <= args.dto:
            byday[p["date"]].append(p)
    if not byday:
        raise SystemExit("該当する開催日がキャッシュにない")

    print(f"■ {args.place} {args.dfrom}〜{args.dto}  {len(byday)}開催日\n")
    allc = Counter(); allh = Counter()
    for d in sorted(byday):
        rs = sorted(byday[d], key=lambda z: z["rn"])
        tot, hit, win, H, wk, nin, tans, sans, l3s = day_report(rs)
        N = sum(tot.values()); base = sum(hit.values()) / N
        for k in KEYS:
            allc[k] += tot[k]; allh[k] += hit[k]
        baba = Counter(r["baba"] for r in rs).most_common(1)[0][0]
        print(f"── {d}（{len(rs)}R・{N}頭・馬場{baba}） 全体3着内率{base*100:.1f}% ──")
        line = []
        for k in KEYS:
            if tot[k]:
                line.append(f"{k} {hit[k]}/{tot[k]}={hit[k]/tot[k]*100:.0f}%(倍率{hit[k]/tot[k]/base:.2f}) 1着{win[k]}")
        print("   " + " ／ ".join(line))
        wl = " ／ ".join(f"{k}枠 {v[1]}/{v[0]}={v[1]/v[0]*100:.0f}%" for k, v in wk.items() if v[0])
        print(f"   枠：{wl}")
        pa, pb = H["前"], H["後"]
        def lift(C, k):
            N2 = sum(C[0].values()); b2 = sum(C[1].values()) / N2 if N2 else 0
            return (C[1][k] / C[0][k] / b2) if (C[0][k] and b2) else None
        a, b = lift(pa, "先頭"), lift(pb, "先頭")
        arrow = "—"
        if a is not None and b is not None:
            arrow = "↑" if b - a >= 0.3 else ("↓" if a - b >= 0.3 else "→")
        print(f"   先頭の倍率 前半{a if a is None else round(a,2)} → 後半{b if b is None else round(b,2)} {arrow}"
              f"   1着馬の人気 {nin}")
        d14 = [v for dd, v in l3s if dd in (1200, 1500)]
        print(f"   単勝中央{st.median(tans) if tans else 0:.0f}円 三連単中央{st.median(sans) if sans else 0:,.0f}円"
              f"  最高{max(sans) if sans else 0:,}円"
              f"  後半3F中央{(st.median(d14) if d14 else 0):.1f}\n")
    NA = sum(allc.values()); ba = sum(allh.values()) / NA
    print("── 期間まとめ ──")
    for k in KEYS:
        if allc[k]:
            print(f"  {k:<14}{allh[k]:>4}/{allc[k]:<4} = {allh[k]/allc[k]*100:>5.1f}%  倍率{allh[k]/allc[k]/ba:.2f}")


if __name__ == "__main__":
    main()
