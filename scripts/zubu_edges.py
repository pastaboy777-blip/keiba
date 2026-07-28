# -*- coding: utf-8 -*-
"""オッズ未開放の日に、各馬のエッジ集合＋399下地を一覧する（ズブ穴の相手選び用）。

ana_recall.edges_for（穴ファクター）と ana399.evaluate（勝ち圏の上がり再現力）を
同じ表に並べるだけの補助ツール。軸そのものは predict_nankan（実力軸）で決める。

    python3 scripts/zubu_edges.py --date 2026-07-29 --place 川崎 --from 1 --to 5
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

import ana_recall as R
import ana399 as A

CARD_URL = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{race_id}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", default="川崎")
    ap.add_argument("--from", dest="r_from", type=int, default=1)
    ap.add_argument("--to", dest="r_to", type=int, default=12)
    ap.add_argument("--thr", type=float, default=40.5)
    args = ap.parse_args()

    pa, ba = A.load_adj()
    client = PoliteClient(use_cache=False)
    ymd = date.fromisoformat(args.date).strftime("%Y%m%d")
    html = client.get(CARD_URL.format(race_id=day_index_race_id(ymd, args.place)))
    races = dict(P.parse_race_links(html, date_yyyymmdd=ymd,
                                    jyo_code=NANKAN_CODES[args.place]))
    today = date.fromisoformat(args.date)

    for r in range(args.r_from, args.r_to + 1):
        if r not in races:
            continue
        page = P.parse_card_page(client.get(CARD_URL.format(race_id=races[r])), races[r])
        ents = getattr(page, "entries", page)
        tb = A.band(page.distance)
        print(f"=== {r}R ダ{page.distance} {len(ents)}頭")
        rows = []
        for e in ents:
            tags, cw = R.edges_for(e, page.distance, today=today)
            ev = A.evaluate(e, tb, args.place, pa, ba, args.thr, False)
            rows.append((len(tags), ev["score"], e, tags, ev, cw))
        for n, sc, e, tags, ev, bw in sorted(rows, key=lambda x: (-x[0], -x[1])):
            print(f"  {e.umaban:>2} {e.horse_name:<12} エッジ{n} 399={sc:4.1f} "
                  f"本物{ev['n_real']} 体重{bw or '-'} | {'・'.join(sorted(tags))}")
        print()


if __name__ == "__main__":
    main()
