# -*- coding: utf-8 -*-
"""判別テスト：後半が速く出るのは「時刻」か「前後半の構成の違い」か。

同じ日・同じレースに対して、標準タイム(par)の作り方だけを変えて比べる。
  A par = 距離のみ            … クラスを見ない
  B par = 距離 × 級           … クラスを見る
前半は2歳・3歳・C級＋短距離、後半はB級・A級＋長距離という構成差があるので、
Aだと後半が速く出て当然。Bでスイングが消えるなら、原因は時刻ではなく構成。
対照として偶数R−奇数R（構成が同じ割り方）も並べる。
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
for pl in ("船橋", "川崎", "大井", "浦和"):
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
print("\r" + " " * 26 + "\r", end="")

def swings(mode):
    out_h, out_oe = [], []
    for pl in sorted({r["pl"] for r in rec}):
        R = [r for r in rec if r["pl"] == pl]
        key = (lambda r: r["dist"]) if mode == "A" else (lambda r: (r["dist"], r["g"]))
        by = defaultdict(list)
        for r in R:
            by[key(r)].append(r["t"])
        std = {k: st.median(v) for k, v in by.items() if len(v) >= 3}
        bd = defaultdict(list)
        for r in R:
            bd[r["dist"]].append(r["t"])
        std_d = {k: st.median(v) for k, v in bd.items()}
        for r in R:
            b = std.get(key(r), std_d.get(r["dist"]))
            r["v"] = (r["t"] - b) / (r["dist"] / 1000) if b else None
        for d in sorted({r["d"] for r in R}):
            day = [r for r in R if r["d"] == d and r["v"] is not None]
            f = [r["v"] for r in day if r["rno"] <= 6]
            b_ = [r["v"] for r in day if r["rno"] > 6]
            o = [r["v"] for r in day if r["rno"] % 2 == 1]
            e = [r["v"] for r in day if r["rno"] % 2 == 0]
            if min(len(f), len(b_)) >= 4:
                out_h.append((st.median(b_) - st.median(f)) * REF / 1000)
            if min(len(o), len(e)) >= 4:
                out_oe.append((st.median(e) - st.median(o)) * REF / 1000)
    return out_h, out_oe

print(f"■ 南関4場 {len({(r['pl'], r['d']) for r in rec})}開催日／{REF}m換算\n")
print(f"{'par の作り方':<22}{'割り方':<14}{'平均':>8}{'SE':>7}{'z':>8}{'後半が速い日':>14}")
for mode, lab in (("A", "距離のみ（級を見ない）"), ("B", "距離 × 級")):
    h, oe = swings(mode)
    for v, name, cnt in ((h, "前半後半", sum(1 for x in h if x < 0)),
                         (oe, "偶数奇数（対照）", sum(1 for x in oe if x < 0))):
        se = st.pstdev(v) / len(v) ** 0.5
        print(f"{lab if name.startswith('前半') else '':<22}{name:<14}"
              f"{st.mean(v):>+8.3f}{se:>7.3f}{st.mean(v)/se:>8.1f}{cnt:>8}/{len(v)}日")
