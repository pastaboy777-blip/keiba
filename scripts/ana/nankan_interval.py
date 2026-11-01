# -*- coding: utf-8 -*-
"""開催が空いたあと、どういう馬が走るかを測る。

  python3 scripts/ana/nankan_interval.py [場名]

南関は場ごとに開催がかたまるので、その場だけ見ていると
「久々」に見える馬が、じつは他場を使ってきていることがある。
だから間隔は4場をまたいで数える。

  間隔   … 前走（南関のどこでも）から何日あいたか
  前走の場 … 同じ場か、よその場か
  開催日目 … その開催の何日目か
"""
import datetime as dt
import json, statistics as st, sys
from collections import defaultdict

BA = sys.argv[1] if len(sys.argv) > 1 else '船橋'
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
DIVF = {'船橋': 'div_funabashi.json', '大井': 'div_year.json'}


def day(s):
    return dt.date(int(s[:4]), int(s[4:6]), int(s[6:]))


R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R.sort(key=lambda r: (r['ymd'], r['rid']))

# その場の開催の切れ目から「何日目か」を出す
days = sorted({r['ymd'] for r in R if r['ba'] == BA})
nth, blk = {}, 0
prev = None
for d in days:
    if prev is None or (day(d) - day(prev)).days > 4:
        blk, n = blk + 1, 1
    else:
        n += 1
    nth[d] = n
    prev = d

DIV = {}
if BA in DIVF:
    try:
        DIV = json.load(open(f'{SP}/{DIVF[BA]}', encoding='utf-8'))
    except Exception:
        DIV = {}

LAST = {}
ROWS = []
for r in R:
    fk = dict((DIV.get(r['ymd'], {}).get(str(r['R']), {})).get('複勝', []))
    if r['ba'] == BA:
        for e in r['e']:
            if not e.get('f', '').isdigit():
                continue
            nm = e['nm']
            pv = LAST.get(nm)
            pop = e.get('pop', '')
            ROWS.append(dict(
                hit=int(e['f']) <= 3,
                pop=int(pop) if pop.isdigit() else None,
                gap=((day(r['ymd']) - day(pv[0])).days if pv else None),
                pba=(pv[1] if pv else None),
                nth=nth.get(r['ymd']),
                fuku=fk.get(str(int(e['u'])), 0), has=bool(fk)))
    for e in r['e']:
        if e.get('tm'):
            LAST[e['nm']] = (r['ymd'], r['ba'])

P = [x for x in ROWS if x['pop'] and x['pop'] >= 6]
base = 100 * sum(x['hit'] for x in P) / len(P)
hasdiv = [x for x in P if x['has']]
broi = (sum(x['fuku'] for x in hasdiv) / len(hasdiv)) if hasdiv else None
print(f'{BA}　人気薄 {len(P)}頭　3着内 {base:.1f}%'
      + (f'　複勝の回収 {broi:.0f}%' if broi else '') + '\n')


def show(lab, f, mn=60):
    v = [x for x in P if f(x)]
    if len(v) < mn:
        print(f'  {lab:<24} 材料不足（{len(v)}頭）')
        return
    i = sum(x['hit'] for x in v)
    d = [x for x in v if x['has']]
    roi = f'  回収 {sum(x["fuku"] for x in d)/len(d):5.0f}%' if d else ''
    print(f'  {lab:<24} {100*i/len(v):5.1f}%{roi}  ({i}/{len(v)})'
          f' {100*i/len(v)-base:+5.1f}pt')


print('■ 前走からの間隔（南関4場をまたいで数える）')
for lab, lo, hi in (('中7日以内', 0, 8), ('中8〜14日', 8, 15), ('中15〜21日', 15, 22),
                    ('中22〜35日', 22, 36), ('中36〜60日', 36, 61),
                    ('61日以上', 61, 9999)):
    show(lab, lambda x, a=lo, b=hi: x['gap'] is not None and a <= x['gap'] < b)

print('\n■ 開催の何日目か')
for n in (1, 2, 3, 4, 5):
    show(f'{n}日目', lambda x, k=n: x['nth'] == k)

print('\n■ 開催初日だけを、間隔で割る')
for lab, lo, hi in (('中21日以内', 0, 22), ('中22〜35日', 22, 36), ('中36日以上', 36, 9999)):
    show(f'初日 × {lab}',
         lambda x, a=lo, b=hi: x['nth'] == 1 and x['gap'] is not None
         and a <= x['gap'] < b, mn=30)

print('\n■ 前走をどこで使ってきたか')
show(f'前走も{BA}', lambda x: x['pba'] == BA)
show('前走はよその場', lambda x: x['pba'] and x['pba'] != BA)
print('  （開催初日だけ）')
show(f'初日 × 前走も{BA}', lambda x: x['nth'] == 1 and x['pba'] == BA, mn=30)
show('初日 × 前走はよその場',
     lambda x: x['nth'] == 1 and x['pba'] and x['pba'] != BA, mn=30)
