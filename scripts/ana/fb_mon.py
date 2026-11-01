# -*- coding: utf-8 -*-
"""月曜船橋の出馬表に、前日に分かる材料だけを当てる。

  python3 scripts/ana/fb_mon.py <card.json> <YYYYMMDD>

コーナーの動き（近5走の押し上げ）は入れない。船橋では効いていない。
  船橋 上げた3回以上 8.7%（層11.0%）／上げた4回以上 8.7%
  大井 13.0%（+4.0pt）・浦和 17.1%（+4.6pt）・川崎 12.3%
以前「近5走すべて押し上げ19.8%・回収123%」と出したのは4場を混ぜた
106頭で、中身は大井・浦和・川崎が持っていた。船橋は逆向き。

入れるのは船橋で測って効いた3つ。どれも前日に分かる。
  枠      1600m 外1/3 18.4%・回収109%（内1/3 7.6%・43%）
          1200m 外1/3 12.8%・回収69%
          1500m 外1/3 12.1%・回収80%
  開催初日 × 前走も船橋   13.4%・回収75%（よその場 8.1%・62%）
  開催間隔 中22〜35日     12.3%・回収71%（中14日以内 8.2%）
層は人気薄で10.7%・回収65%。
"""
import datetime as dt
import json, re, sys
from collections import defaultdict

CARD, YMD = sys.argv[1], sys.argv[2]
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
# 距離ごとに、外が効く強さ（測った値。+ptと回収）
WAKU = {1600: ('18.4%', '109%'), 1200: ('12.8%', '69%'), 1500: ('12.1%', '80%')}

R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R.sort(key=lambda r: (r['ymd'], r['rid']))
LAST = {}
for r in R:
    for e in r['e']:
        LAST[e['nm']] = (r['ymd'], r['ba'], r['dist'], e.get('f'), r.get('baba'))

C = json.load(open(CARD, encoding='utf-8'))
d0 = dt.date(int(YMD[:4]), int(YMD[4:6]), int(YMD[6:]))
out = []
for k in sorted((x for x in C if str(x).isdigit()), key=int):
    r = C[k]
    n, ds = r['n'], r['dist']
    for e in r['e']:
        u = int(e['u'])
        pos = (u - 1) / (n - 1) if n > 1 else 0.5
        soto = pos > 2 / 3
        uchi = pos <= 1 / 3
        pv = LAST.get(e['nm'])
        gap = (d0 - dt.date(int(pv[0][:4]), int(pv[0][4:6]),
                            int(pv[0][6:]))).days if pv else None
        out.append(dict(R=int(k), dist=ds, n=n, u=u, waku=e.get('waku'),
                        nm=e['nm'], sire=e.get('sire'), prof=e.get('prof'),
                        soto=soto, uchi=uchi, pos=pos,
                        pba=pv[1] if pv else None, pf=pv[3] if pv else None,
                        pymd=pv[0] if pv else None, gap=gap))

print(f'■ {YMD} 船橋　前日に分かる材料だけで並べる')
print('  枠（外が効く距離で外1/3）／前走も船橋／開催間隔 中22〜35日')
print('  層は人気薄で3着内10.7%・複勝の回収65%\n')

hit = [x for x in out if x['soto'] and x['dist'] in WAKU
       and x['pba'] == '船橋' and x['gap'] and 22 <= x['gap'] <= 35]
print(f'● 3つそろった馬　{len(hit)}頭')
for x in hit:
    w = WAKU[x['dist']]
    print(f'  {x["R"]:>2}R {x["dist"]}m {x["n"]}頭　{x["u"]:>2}番'
          f'（{x["waku"]}枠・外1/3）　{x["nm"]}')
    print(f'       前走 {x["pymd"][4:6]}/{x["pymd"][6:]} 船橋 {x["pf"]}着'
          f'　中{x["gap"]}日　この距離の外枠 {w[0]}・回収{w[1]}')
    print(f'       父{x["sire"] or ""}　{x["prof"] or ""}')

sub = [x for x in out if x['soto'] and x['dist'] in WAKU and x not in hit]
print(f'\n○ 外枠だけ該当　{len(sub)}頭')
for x in sub:
    g = f'中{x["gap"]}日' if x['gap'] else '－'
    print(f'  {x["R"]:>2}R {x["dist"]}m {x["u"]:>2}番 {x["nm"]:<16}'
          f'前走 {x["pba"] or "－"} {x["pf"] or "-"}着 {g}')

print(f'\n　内1/3（この距離で沈んでいる側）')
for x in out:
    if x['uchi'] and x['dist'] == 1600:
        print(f'  {x["R"]:>2}R 1600m {x["u"]:>2}番 {x["nm"]}')
json.dump(out, open(f'{SP}/fb_mon.json', 'w', encoding='utf-8'),
          ensure_ascii=False)
