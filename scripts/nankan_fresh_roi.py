# -*- coding: utf-8 -*-
"""『開催初日に、他場を短い間隔で使ってきた馬』を買うと増えるか。

きっかけ（2026-08-02 の船橋、前開催から29日空いた開催初日）:
  全12鞍110頭を分けると、前走が船橋以外の41頭が単223%・複137%、
  船橋だった69頭が単31.7%・複91.9%。間隔35日以上の31頭は単18.4%・複43.5%。
  勝ち馬12頭のうち7頭が他場帰りで、高配当（単4,900/1,290/1,180/1,100）が全部そこにあった。

  ただし1日ぶんの観測である。南関4場の全開催初日に当てて、再現するかを見る。

  南関4場1,749レースで測ると、前の開催日から21日以上空いた初日は
  1200m戦の前半600mが0.73秒遅く（z=+3.0）、上がりは変わらない（z=+1.2）。
  「全体がズブくて誰も前半から動けない」は成立している。
  ならばその中で唯一動ける馬＝休んでいない馬に値が付いていないはずだ、というのがこの仮説。

  ★『開催初日』は『馬場が新しい日』でもあり、この粒度では分けられない。
    ここで測るのは馬ごとの間隔と使い場所であって、馬場の効果ではない。

    python3 scripts/nankan_fresh_roi.py --from 2026-01-01 --to 2026-07-31
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

from nankan_racelevel import VENUES
from nankan_zubu_backtest import CARD, PERF, race_days, payouts


def line(name, v):
    if len(v) < 30:
        print(f"{name:<28}n={len(v)} で足りない")
        return
    w = sum(1 for x in v if x["fin"] == 1)
    p = sum(1 for x in v if x["fuku"])
    se = lambda k: st.pstdev([x[k] for x in v]) / len(v) ** 0.5
    print(f"{name:<28}{len(v):>6}{w / len(v) * 100:>7.1f}%{p / len(v) * 100:>8.1f}%"
          f"{sum(x['tan'] for x in v) / len(v):>9.1f}%±{se('tan'):<5.0f}"
          f"{sum(x['fuku'] for x in v) / len(v):>8.1f}%±{se('fuku'):<4.0f}")


def main():
    ap = argparse.ArgumentParser(description="開催初日×他場帰りの回収率")
    ap.add_argument("--from", dest="d_from", default="2026-01-01")
    ap.add_argument("--to", dest="d_to", default="2026-07-31")
    ap.add_argument("--gap", type=int, default=21,
                    help="前の開催日からこの日数以上空いたら『開催初日』")
    args = ap.parse_args()

    client = PoliteClient(use_cache=True)
    d0, d1 = date.fromisoformat(args.d_from), date.fromisoformat(args.d_to)

    runs = []
    for place in VENUES:
        days = race_days(client, place, d0, d1)
        prev = None
        for i, (d, rs) in enumerate(days, 1):
            gap_day = (d - prev).days if prev else None
            prev = d
            if gap_day is None:
                continue
            opening = gap_day >= args.gap
            for rno, rid in sorted(rs.items()):
                try:
                    html = client.get(PERF.format(r=rid))
                    res = P.parse_result_page(html, rid)
                    tan, fuku = payouts(html)
                    card = P.parse_card_page(client.get(CARD.format(r=rid)), rid)
                except Exception:
                    continue
                if not fuku:
                    continue
                ent = {e.horse_id: e for e in getattr(card, "entries", card)}
                for r in res.rows:
                    if not r.finish_pos or r.umaban is None:
                        continue
                    e = ent.get(r.horse_id)
                    pr = (e.recent_runs or [None])[0] if e else None
                    hgap = None
                    if pr and pr.date:
                        try:
                            hgap = (d - date.fromisoformat(str(pr.date))).days
                        except Exception:
                            hgap = None
                    runs.append(dict(opening=opening, place=place,
                                     prev_place=pr.place if pr else None,
                                     hgap=hgap, fin=r.finish_pos,
                                     tan=float(tan.get(r.umaban, 0)),
                                     fuku=float(fuku.get(r.umaban, 0))))
            print(f"\r{place} {i}/{len(days)}日 {len(runs)}走", end="", flush=True)
        print()

    op = [x for x in runs if x["opening"]]
    print(f"\n収集 延べ{len(runs):,}走／開催初日 {len(op):,}走（境目 {args.gap}日）\n")
    print(f"{'区分':<28}{'頭数':>6}{'勝率':>7}{'複勝率':>8}{'単回収':>10}{'':<6}{'複回収':>8}")

    def fresh(x):
        return (x["prev_place"] is not None and x["prev_place"] != x["place"]
                and x["hgap"] is not None and x["hgap"] <= 21)

    print("── 開催初日（21日以上空いた日） ──")
    line("すべて", op)
    line("他場帰り×21日以内", [x for x in op if fresh(x)])
    line("　うち南関3場から", [x for x in op if fresh(x) and x["prev_place"] in VENUES])
    line("　うち南関外から", [x for x in op if fresh(x) and x["prev_place"] not in VENUES])
    line("同じ場・35日以上", [x for x in op if x["prev_place"] == x["place"]
                              and x["hgap"] is not None and x["hgap"] >= 35])
    print("── 2日目以降（比較用） ──")
    reg = [x for x in runs if not x["opening"]]
    line("すべて", reg)
    line("他場帰り×21日以内", [x for x in reg if fresh(x)])
    print("\n  控除率のぶん、無差別に買えば75%前後に沈む。見るのは『すべて』の行との差。")


if __name__ == "__main__":
    main()
