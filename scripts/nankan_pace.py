# -*- coding: utf-8 -*-
"""「上がりがかかる日」を前日に見分けられるかを、出走馬の脚質構成で測る。

背景（2026-08-01）:
  川崎7か月・6番人気以下を平等に買うと、勝ち馬の上がりが40.4秒以上のレースだけで 117.9%、
  38.6秒以下のレースだけで 53.1%。65ポイント差。人気薄が浮くかどうかは「日」で決まっていた。
  ところが馬場は代用にならなかった（勝ち馬の上がりは良39.34/稍39.46/重39.78/不39.14と
  ほとんど動かず、しかも不良がいちばん速い。ダートは湿ると速い）。

  上がりがかかる正体は、前半が速すぎて全馬の脚が上がること。だとすれば予測材料は馬場ではなく
  「前に行きたい馬が何頭いるか」。これは出馬表の4角通過順から前日に作れる。

測ること:
  ① 先行型の頭数（および比率）は、そのレースの勝ち馬の上がりを予測するか
  ② 先行型が多いレースだけを買ったとき、6番人気以下の土台は 100% を超えるか

    python3 scripts/nankan_pace.py --place 川崎 --from 2026-01-01 --to 2026-07-31
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

from nankan_zubu_backtest import CARD, PERF, payouts, race_agari, race_days


def front_ratio(entry):
    """近5走の4角位置から『前に行く馬か』を 0〜1 で。小さいほど前。"""
    rs = [r for r in (entry.recent_runs or []) if r.corner and r.field_size][:5]
    if not rs:
        return None
    return st.median(r.corner[-1] / r.field_size for r in rs)


def main():
    ap = argparse.ArgumentParser(description="脚質構成で『かかる日』を予測できるか")
    ap.add_argument("--place", default="川崎")
    ap.add_argument("--from", dest="d_from", required=True)
    ap.add_argument("--to", dest="d_to", required=True)
    ap.add_argument("--pop-min", type=int, default=6)
    ap.add_argument("--front", type=float, default=0.35,
                    help="この比率より前を『先行型』とみなす")
    args = ap.parse_args()

    client = PoliteClient(use_cache=True)
    days = race_days(client, args.place,
                     date.fromisoformat(args.d_from), date.fromisoformat(args.d_to))
    print(f"■ {args.place} {args.d_from}〜{args.d_to}：開催 {len(days)}日\n")

    races = []
    for d, rs in days:
        for rno, rid in sorted(rs.items()):
            try:
                page = P.parse_card_page(client.get(CARD.format(r=rid)), rid)
                rhtml = client.get(PERF.format(r=rid))
                res = P.parse_result_page(rhtml, rid)
            except Exception:
                continue
            ra = race_agari(rhtml)
            tan, fuku = payouts(rhtml)
            if ra is None or not fuku or not res.rows:
                continue
            ents = getattr(page, "entries", page)
            fr = [front_ratio(e) for e in ents]
            known = [x for x in fr if x is not None]
            if len(known) < 5:
                continue
            n_front = sum(1 for x in known if x < args.front)
            fin = {r.umaban: r for r in res.rows}
            bets = []
            for e in ents:
                r_ = fin.get(e.umaban)
                if not r_ or not r_.popularity or r_.popularity < args.pop_min:
                    continue
                bets.append((tan.get(e.umaban, 0) if r_.finish_pos == 1 else 0,
                             fuku.get(e.umaban, 0) if r_.finish_pos <= 3 else 0,
                             1 if r_.finish_pos == 1 else 0))
            races.append(dict(agari=ra, n_front=n_front, field=len(known),
                              ratio=n_front / len(known), bets=bets,
                              dist=page.distance, baba=res.baba))
        print(f"\r{d} まで集計", end="", flush=True)
    print(f"\n対象 {len(races)}レース\n")

    def show(label, sel):
        if not sel:
            return
        bets = [b for r in sel for b in r["bets"]]
        n = len(bets)
        if not n:
            return
        tp = sum(b[0] for b in bets)
        fp = sum(b[1] for b in bets)
        w = sum(b[2] for b in bets)
        print(f"  {label:<16}{len(sel):>5}R{n:>7}点{w/n*100:>7.1f}%"
              f"{tp/(n*100)*100:>9.1f}%{fp/(n*100)*100:>9.1f}%{(tp+fp)/(n*200)*100:>10.1f}%"
              f"{st.mean(r['agari'] for r in sel):>10.2f}")

    print("① 先行型の頭数と、そのレースの勝ち馬の上がり")
    print(f"  {'':<16}{'R数':>6}{'点数':>8}{'勝率':>7}{'単回収':>9}{'複回収':>9}"
          f"{'単複均等':>10}{'勝ち馬上り':>11}")
    for k in range(0, 8):
        sel = [r for r in races if r["n_front"] == k]
        if len(sel) >= 5:
            show(f"先行{k}頭", sel)
    show("先行8頭以上", [r for r in races if r["n_front"] >= 8])

    print("\n② 先行型の比率で3分割")
    q = sorted(r["ratio"] for r in races)
    lo, hi = q[len(q) // 3], q[len(q) * 2 // 3]
    show(f"比率 <{lo:.2f}", [r for r in races if r["ratio"] < lo])
    show(f"比率 {lo:.2f}-{hi:.2f}", [r for r in races if lo <= r["ratio"] < hi])
    show(f"比率 >={hi:.2f}", [r for r in races if r["ratio"] >= hi])

    print("\n③ 参考：実際にかかったレース（勝ち馬の上がり）で分けた場合")
    show("40.4以上", [r for r in races if r["agari"] >= 40.4])
    show("38.6以下", [r for r in races if r["agari"] <= 38.6])

    rr = [r["ratio"] for r in races]
    aa = [r["agari"] for r in races]
    if len(rr) > 2:
        mr, ma = st.mean(rr), st.mean(aa)
        cov = sum((x - mr) * (y - ma) for x, y in zip(rr, aa)) / len(rr)
        sd = st.pstdev(rr) * st.pstdev(aa)
        print(f"\n先行比率と勝ち馬の上がりの相関係数: {cov / sd if sd else 0:+.3f}"
              "  （負なら『前が多いほど上がりがかかる』）")


if __name__ == "__main__":
    main()
