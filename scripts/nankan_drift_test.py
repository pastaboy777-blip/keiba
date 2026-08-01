# -*- coding: utf-8 -*-
"""ドリフト（日中の馬場変化）が本物かを、偽のドリフトと比べて確かめる。

前半/後半で割ると差が出る。ただしその差が「時間とともに馬場が動いた」のか
「前半と後半でクラス・距離の構成が違い、parの偏りを拾っているだけ」なのかは、
前半/後半の比較だけでは分からない。

そこで同じ日を 奇数R/偶数R でも割る。奇数と偶数は時間的に交互なので、
本物の時間変化ならスイングはゼロ近くに潰れる。潰れなければ、
前半/後半で見えている差も同じ性質のノイズである可能性が高い。
"""
import sys, statistics as st
from collections import defaultdict
from datetime import date
sys.path.insert(0, "/home/user/keiba/scripts"); sys.path.insert(0, "/home/user/keiba/src")
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from nankan_babasa import grade, sec, REF
from nankan_zubu_backtest import CARD, PERF, race_days

c = PoliteClient(use_cache=True)
rec = []
for pl in ("船橋", "川崎"):
    for d, rs in race_days(c, pl, date(2026, 5, 1), date(2026, 7, 31)):
        for rno, rid in sorted(rs.items()):
            try:
                res = P.parse_result_page(c.get(PERF.format(r=rid)), rid)
                cls = P.parse_race_class(c.get(CARD.format(r=rid)))
            except Exception:
                continue
            w = next((r for r in res.rows if r.finish_pos == 1), None)
            t = sec(w.time) if w else None
            if t and res.distance:
                rec.append(dict(pl=pl, d=d, rno=rno, dist=res.distance, g=grade(cls), t=t))
        print(f"\r  {pl} {d}", end="", flush=True)
print("\r" + " " * 24 + "\r", end="")

for pl in ("船橋", "川崎"):
    R = [r for r in rec if r["pl"] == pl]
    by = defaultdict(list)
    for r in R:
        by[(r["dist"], r["g"])].append(r["t"])
    std = {k: st.median(v) for k, v in by.items() if len(v) >= 3}
    bd = defaultdict(list)
    for r in R:
        bd[r["dist"]].append(r["t"])
    std_d = {k: st.median(v) for k, v in bd.items()}
    for r in R:
        b = std.get((r["dist"], r["g"]), std_d.get(r["dist"]))
        r["v"] = (r["t"] - b) / (r["dist"] / 1000) if b else None

    real, fake = [], []
    for d in sorted({r["d"] for r in R}):
        day = [r for r in R if r["d"] == d and r["v"] is not None]
        f = [r["v"] for r in day if r["rno"] <= 6]
        b = [r["v"] for r in day if r["rno"] > 6]
        o = [r["v"] for r in day if r["rno"] % 2 == 1]
        e = [r["v"] for r in day if r["rno"] % 2 == 0]
        if min(len(f), len(b)) >= 4:
            real.append((st.median(b) - st.median(f)) * REF / 1000)
        if min(len(o), len(e)) >= 4:
            fake.append((st.median(e) - st.median(o)) * REF / 1000)
    f = lambda v: (f"平均{st.mean(v):+.2f}  標準偏差{st.pstdev(v):.2f}  "
                   f"幅{min(v):+.2f}〜{max(v):+.2f}  |0.3秒|超え{sum(1 for x in v if abs(x)>0.3)}/{len(v)}日")
    print(f"\n■ {pl}（{len(real)}開催日・{REF}m換算）")
    print(f"  本物の候補 後半−前半 : {f(real)}")
    print(f"  偽（対照） 偶数−奇数 : {f(fake)}")
