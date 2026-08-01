# -*- coding: utf-8 -*-
"""今日の出走馬が『どのレベルのレースで負けてきたか』を出す。

考え方（2026-08-01）:
  レースレベルを出走馬のその後で測ると、勝ち馬より敗戦馬のほうが使える。
  勝ち馬は誰にでも見えて人気を被るが、強い相手に揉まれて着順を落とした馬は
  次に人気を落として出てくる。市場は着順を読み、相手関係までは値段に入れきらない。

  そこで今日の各馬について、過去に走ったレースのレベルを引き当て、
  「高レベル戦で4着以下に負けていた馬」を拾う。

  ★レベルはそのレースより後の出走で作るので、今日の予想に使う分には未来を見ていない
    （過去レースの評価に、今日より前の出走しか使わない）。ただし当該レースの直後には
    まだ後続が溜まっていないので、直近1〜2走のレースは判定できないことが多い。

    python3 scripts/nankan_level_today.py --date 2026-08-02 --place 船橋
    python3 scripts/nankan_level_today.py --date 2026-08-02 --place 船橋 --from 1 --to 5
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES
from nankeiba.scraping import parser as P

from nankan_racelevel import collect, VENUES
from nankan_zubu_backtest import CARD


def levels(races, timeline, losers_from, shrink=8.0, min_cover=6):
    """各レースの『敗戦馬のその後』レベル。{race_id: (level, 偏差, 敗者勝利数)}"""
    raw = {}
    for rid, r in races.items():
        tot, cover, wins = 0.0, 0, 0
        for row in r["rows"]:
            if row.finish_pos < losers_from:
                continue
            later = [x for x in timeline[row.horse_id] if x[0] > r["date"]]
            if not later:
                continue
            cover += 1
            tot += st.mean(x[2] for x in later)
            wins += sum(1 for x in later if x[3] == 1)
        if cover >= min_cover:
            raw[rid] = (tot, cover, wins)
    if not raw:
        return {}
    g = sum(v[0] for v in raw.values()) / sum(v[1] for v in raw.values())
    lv = {rid: (t + shrink * g) / (c + shrink) for rid, (t, c, _w) in raw.items()}
    mu, sd = st.mean(lv.values()), st.pstdev(lv.values())
    return {rid: (v, (v - mu) / sd if sd else 0.0, raw[rid][2]) for rid, v in lv.items()}


def main():
    ap = argparse.ArgumentParser(description="今日の出走馬の『経験したレースレベル』")
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", default="船橋", choices=list(NANKAN_CODES))
    ap.add_argument("--from", dest="r_from", type=int, default=1)
    ap.add_argument("--to", dest="r_to", type=int, default=12)
    ap.add_argument("--since", default="2026-01-01", help="レベルを作る収集の開始日")
    ap.add_argument("--losers", type=int, default=4, help="この着順以下だけでレベルを測る")
    ap.add_argument("--min-z", type=float, default=1.0, help="この偏差以上を『高レベル戦』とする")
    args = ap.parse_args()

    today = date.fromisoformat(args.date)
    client = PoliteClient(use_cache=True)
    races, timeline = collect(client, VENUES, date.fromisoformat(args.since), today)
    lv = levels(races, timeline, args.losers)
    print(f"\n■ レベルを付けられたレース {len(lv)}件（{args.losers}着以下の馬のその後で測定）\n")

    ymd = today.strftime("%Y%m%d")
    card = dict(P.parse_race_links(
        client.get(CARD.format(r=day_index_race_id(ymd, args.place))),
        date_yyyymmdd=ymd, jyo_code=NANKAN_CODES[args.place]))

    for rno in range(args.r_from, args.r_to + 1):
        if rno not in card:
            continue
        page = P.parse_card_page(client.get(CARD.format(r=card[rno])), card[rno])
        rows = []
        for e in getattr(page, "entries", page):
            hits = []
            for d, rid, _score, fin in timeline.get(e.horse_id, []):
                if d >= today or rid not in lv or fin < args.losers:
                    continue
                z = lv[rid][1]
                if z >= args.min_z:
                    r = races[rid]
                    hits.append((z, d, r["place"], r["rno"], fin, lv[rid][2]))
            if hits:
                hits.sort(reverse=True)
                rows.append((hits[0][0], e, hits))
        print(f"=== {rno}R ダ{page.distance} {len(getattr(page,'entries',page))}頭"
              f"　該当 {len(rows)}頭")
        if not rows:
            print("   （高レベル戦で負けてきた馬なし）\n")
            continue
        rows.sort(key=lambda x: -x[0])
        for _z, e, hits in rows:
            pop = f"想定{e.exp_pop}人" if e.exp_pop else "想定-"
            print(f"  {e.umaban:>2} {e.horse_name:<14}{pop:>8} "
                  f"{e.horse_weight or '-'}kg")
            for z, d, pl, rn, fin, w in hits[:2]:
                print(f"        {d} {pl}{rn}R {fin}着　そのレースの敗者レベル 偏差{z:+.2f}"
                      f"（敗者の後続{w}勝）")
        print()


if __name__ == "__main__":
    main()
