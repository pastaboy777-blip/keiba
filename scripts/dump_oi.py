# -*- coding: utf-8 -*-
"""大井の1日分（全12鞍）のラップ＋上位3頭を JSON に落とす。使い方: dump_oi.py YYYYMMDD out.json"""
import sys, json
sys.path.insert(0,'src'); sys.path.insert(0,'scripts')
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES
from nankeiba.scraping import parser as P
from pace_day import parse_laps, last_corner_order
from nankan_gyaku import result_rows

YMD, OUT = sys.argv[1], sys.argv[2]
c = PoliteClient(use_cache=True)
CARD = 'https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}'
PERF = 'https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}'
BABA = {'良':'良','稍重':'稍','重':'重','不良':'不'}
rs = dict(P.parse_race_links(c.get(CARD.format(r=day_index_race_id(YMD,'大井'))),
                             date_yyyymmdd=YMD, jyo_code=NANKAN_CODES['大井']))
out=[]
for rno, rid in sorted(rs.items()):
    h  = c.get(PERF.format(r=rid))
    pr = P.parse_result_page(h, rid)
    laps   = parse_laps(h)
    corner = last_corner_order(h)
    agari  = {r['umaban']: r.get('agari') for r in result_rows(h)}
    top=[]
    for row in pr.rows[:3]:
        um  = row.umaban
        pos = (corner.index(um)+1) if (corner and um in corner) else None
        top.append([row.finish_pos, um, row.horse_name, row.popularity, row.time, agari.get(um), pos])
    out.append(dict(rno=rno, dist=pr.distance, baba=BABA.get(pr.baba, pr.baba),
                    n=len(pr.rows), laps=laps, top=top))
    print(f"{rno:>2}R {pr.distance} {BABA.get(pr.baba)} {len(pr.rows):>2}頭 {laps} "
          f"4角{[t[6] for t in top]} 人気{[t[3] for t in top]}")
json.dump(out, open(OUT,'w'), ensure_ascii=False)
print('wrote', OUT)
