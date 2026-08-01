#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""その日の傾向と【真逆】の競馬をして、それでも僅差で負けた馬を拾う。

考え方:
  馬場が「外を回した馬が来る日」なら、内で我慢した馬は不利を受けている。
  それでも勝ち馬から僅差なら、内容は勝ち馬より上。
  そして負けているので次は人気を落とす ── ここが買える場所になる。

  逆に、有利な位置を通って勝った馬は「馬場のおかげ」の分が乗っているので、
  次に同じ評価で買うと高い。

やること:
  ① 開催日ごとに4角ポジション別の3着内率を出し、その日いちばん不利だった位置を決める
  ② その位置を通り、上がり3Fがメンバー上位で、かつ勝ち馬から僅差(既定0.6秒)で
     4着以下に負けた馬を拾う

     ★着差の扱いを検証した（船橋5-6月）：
        僅差0.6秒以内 … 次走を追えた9頭で 1着11% / 3着内44%
        着差を問わない … 18頭で 1着11% / 3着内17%（南関基準は8%/25%）
     着差を外すと基準割れする。大敗馬の「メンバー最速上がり」は、前が総崩れの中を
     最後だけ流し込んだだけのことが多い（例：6/2 ドラゴンライト +3.6秒・4角12番手・上がり1位）。
     着差は「不利を受けながらも前に居られた」ことの証明なので、外さないほうがよい。
     ※ただし次走を追えたのが9頭。母数を増やしてから確定させること。
  ③ その馬の次走がキャッシュにあれば、実際に巻き返したかを併記して答え合わせする

使い方:
  python3 scripts/ana/gyakubari.py 船橋 --from 2026-05-01 --to 2026-06-30
  python3 scripts/ana/gyakubari.py 船橋 --sa 0.4 --min-lift 0.8
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
from nar_day import KEYS, classify


def sec(t):
    m = re.match(r"(\d+):(\d+)\.(\d)", t or "")
    return int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 10 if m else None


def parse(fn):
    t = open(fn, "rb").read().decode("euc-jp", errors="replace")
    flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))
    hd = re.search(r"(20\d\d)年(\d+)月(\d+)日.{0,50}?(大井|川崎|船橋|浦和)", flat)
    if not hd:
        return None
    d = f"{hd.group(1)}-{int(hd.group(2)):02d}-{int(hd.group(3)):02d}"
    rows = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S):
        if "/horse/" not in r:
            continue
        c = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", z)).strip()
             for z in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
        if len(c) < 16 or not c[0].isdigit():
            continue
        nk = None
        for i, v in enumerate(c):
            if re.match(r"^\d+\.\d$", v) and i + 1 < len(c) and re.match(r"^\d+$", c[i+1]):
                nk = int(c[i+1]); break
        rows.append(dict(chaku=int(c[0]), ub=int(c[2]) if c[2].isdigit() else None,
                         name=c[3], jockey=c[6], t=sec(c[7]), ninki=nk,
                         pas=c[14], agari=(float(c[15]) if re.match(r"^\d+\.\d$", c[15]) else None)))
    x = re.sub(r"<[^>]+>", "|", t); x = re.sub(r"[ 　]+", " ", x)
    fy = re.sub(r"\s+", " ", x)
    c4 = re.search(r"4コーナー\| \|([^|]+)\|", fy)
    cond = re.search(r"(ダ|芝)(?:左|右|直)?(\d+)m.{0,60}?(良|稍重|重|不良)", fy)
    return dict(date=d, place=hd.group(4), rn=int(os.path.basename(fn)[-7:-5]),
                dist=(int(cond.group(2)) if cond else None), baba=(cond.group(3) if cond else "?"),
                rows=rows, c4=(c4.group(1).strip() if c4 else ""))


def main():
    ap = argparse.ArgumentParser(description="その日の傾向と真逆で僅差負けした馬")
    ap.add_argument("place")
    ap.add_argument("--from", dest="dfrom", default="2026-01-01")
    ap.add_argument("--to", dest="dto", default="2026-12-31")
    ap.add_argument("--sa", type=float, default=0.6,
                    help="勝ち馬との秒差の上限。既定0.6。99にすると着差を問わない")
    ap.add_argument("--agari-rank", type=int, default=3, help="上がり3Fがメンバー何位以内なら『強い内容』とみなすか")
    ap.add_argument("--min-lift", type=float, default=0.8, help="この倍率未満の位置を『不利』とみなす")
    args = ap.parse_args()

    byday = defaultdict(list)
    for fn in sorted(glob.glob(os.path.join(h2h.CACHE, "2026*.html"))):
        if os.path.getsize(fn) < 20000:
            continue
        p = parse(fn)
        if p and p["place"] == args.place and args.dfrom <= p["date"] <= args.dto:
            byday[p["date"]].append(p)
    if not byday:
        raise SystemExit("該当開催がキャッシュにない")

    # 次走照合用に全レースを時系列で持つ
    allr = sorted((r for rs in byday.values() for r in rs), key=lambda z: (z["date"], z["rn"]))
    seq = defaultdict(list)
    for i, r in enumerate(allr):
        for h in r["rows"]:
            seq[h["name"]].append((r["date"], i))
    for n in seq:
        seq[n].sort()

    print(f"■ {args.place} {args.dfrom}〜{args.dto}  {len(byday)}開催日")
    print(f"  条件：その日の倍率{args.min_lift}未満の位置を通り、勝ち馬から{args.sa}秒以内で4着以下\n")
    picks = []
    for d in sorted(byday):
        rs = sorted(byday[d], key=lambda z: z["rn"])
        tot, hit = Counter(), Counter()
        for r in rs:
            cl = classify(r["c4"])
            for h in r["rows"]:
                k = cl.get(h["ub"], ("?", 0))[0]
                tot[k] += 1
                if h["chaku"] <= 3:
                    hit[k] += 1
        N = sum(tot.values()); base = sum(hit.values()) / N
        lift = {k: (hit[k] / tot[k] / base if tot[k] else None) for k in KEYS}
        bad = [k for k in KEYS if lift[k] is not None and lift[k] < args.min_lift]
        if not bad:
            continue
        badtxt = "／".join(f"{k}{lift[k]:.2f}" for k in bad)
        found = []
        for r in rs:
            cl = classify(r["c4"])
            wt = next((h["t"] for h in r["rows"] if h["chaku"] == 1), None)
            if wt is None:
                continue
            ags = sorted(z["agari"] for z in r["rows"] if z["agari"])
            for h in r["rows"]:
                k, rank = cl.get(h["ub"], ("?", 0))
                if k not in bad or h["chaku"] < 4 or h["t"] is None:
                    continue
                sa = round(h["t"] - wt, 1)
                if sa > args.sa:
                    continue
                if not h["agari"] or not ags:
                    continue
                arank = ags.index(h["agari"]) + 1        # 同タイムは上位扱い
                if arank > args.agari_rank:
                    continue
                s = seq[h["name"]]
                pos = next((q for q, (dd, j) in enumerate(s) if j == allr.index(r)), None)
                nxt = None
                if pos is not None and pos + 1 < len(s):
                    nr = allr[s[pos + 1][1]]
                    fin = next((z["chaku"] for z in nr["rows"] if z["name"] == h["name"]), None)
                    nk = next((z["ninki"] for z in nr["rows"] if z["name"] == h["name"]), None)
                    if fin:
                        nxt = (nr["date"], nr["place"], nr["rn"], fin, nk)
                found.append((r, h, k, rank, sa, nxt, arank))
        if not found:
            continue
        print(f"── {d}（馬場{rs[0]['baba']}） 不利だった位置：{badtxt} ──")
        for r, h, k, rank, sa, nxt, arank in sorted(found, key=lambda z: (z[6], z[4])):
            nx = "次走なし"
            if nxt:
                mk = "★1着" if nxt[3] == 1 else ("○%d着" % nxt[3] if nxt[3] <= 3 else "%d着" % nxt[3])
                nx = f"次走 {nxt[0]} {nxt[1]}{nxt[2]}R {mk}" + (f" {nxt[4]}人気" if nxt[4] else "")
            print(f"   {r['rn']:>2}R ダ{r['dist']} {h['ub']:>2}番 {h['name']:<15}"
                  f"{h['chaku']:>2}着 {sa:+.1f}秒 {h['ninki'] or 0:>2}人気 "
                  f"[{k}/4角{rank}] 上り{h['agari']:.1f}(メンバー{arank}位) {h['jockey']:<7} {nx}")
            picks.append(nxt)
        print()

    ok = [p for p in picks if p]
    if ok:
        w = sum(1 for p in ok if p[3] == 1); pl = sum(1 for p in ok if p[3] <= 3)
        print(f"■ 拾った馬の次走成績： {len(ok)}頭中 1着{w}({w/len(ok)*100:.0f}%) 3着内{pl}({pl/len(ok)*100:.0f}%)")
        print("  （南関全体の次走勝率はおよそ8%・3着内25%）")


if __name__ == "__main__":
    main()
