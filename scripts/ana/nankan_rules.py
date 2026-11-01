# -*- coding: utf-8 -*-
"""大井で固めた3条件が、ほかの場でも効くかを確かめる。

  python3 scripts/ana/nankan_rules.py [場名...]

3条件
  ① 同じ距離帯の直近5走の上がりのばらつきが 0.6未満（4走以上ある馬）
  ② ふだんの4角が 7番手以内（直近5走の中央値、3走以上）
  ③ 3角→4角で下げない（同じく中央値が −0.5より大きい）

材料はその場の走りだけで作る。場がちがえば水準もちがうので、
ほかの場の走りは混ぜない。
"""
import json, re, statistics as st, sys
from collections import defaultdict

SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
BA = sys.argv[1:] or ['大井', '船橋', '川崎', '浦和']
WET = ('重', '不良')


def band(d):
    return 'S' if d <= 1300 else 'M' if d <= 1700 else 'L'


R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R.sort(key=lambda r: (r['ymd'], r['rid']))

for ba in BA:
    AG, POS, GAIN = defaultdict(list), defaultdict(list), defaultdict(list)
    ROWS = []
    nday = set()
    for r in R:
        if r['ba'] != ba or not r.get('dist'):
            continue
        nday.add(r['ymd'])
        d = r['dist']
        c3 = {u: i + 1 for i, u in enumerate(r.get('c3') or [])}
        c4 = {u: i + 1 for i, u in enumerate(r.get('c4') or [])}
        for e in r['e']:
            if not e.get('f', '').isdigit():
                continue
            nm = e['nm']
            pa = [a for dd, a in AG[nm] if band(dd) == band(d)][-5:]
            pp, pg = POS[nm][-5:], GAIN[nm][-5:]
            pop = e.get('pop', '')
            ROWS.append(dict(
                hit=int(e['f']) <= 3,
                pop=int(pop) if pop.isdigit() else None,
                sd=st.pstdev(pa) if len(pa) >= 4 else None,
                pos=st.median(pp) if len(pp) >= 3 else None,
                gain=st.median(pg) if len(pg) >= 3 else None,
                wet=r.get('baba') in WET))
        for e in r['e']:
            nm = e['nm']
            if re.match(r'^\d+\.\d$', e.get('ag') or ''):
                AG[nm].append((d, float(e['ag'])))
            p4, p3 = c4.get(int(e['u'])), c3.get(int(e['u']))
            if p4 and len(c4):
                POS[nm].append(p4)
            if p4 and p3:
                GAIN[nm].append(p3 - p4)

    P = [x for x in ROWS if x['pop'] and x['pop'] >= 6]
    if len(P) < 300:
        print(f'■ {ba}  材料不足（人気薄{len(P)}頭）\n')
        continue
    base = 100 * sum(x['hit'] for x in P) / len(P)
    print(f'■ {ba}　{len(nday)}日・{len(ROWS)}頭／人気薄 {len(P)}頭　'
          f'この層の3着内 {base:.1f}%')

    A = lambda x: x['sd'] is not None and x['sd'] < 0.6
    B = lambda x: x['pos'] is not None and x['pos'] <= 7
    C = lambda x: x['gain'] is not None and x['gain'] > -0.5

    def show(lab, f, mn=60):
        v = [x for x in P if f(x)]
        if len(v) < mn:
            print(f'    {lab:<26} 材料不足（{len(v)}頭）')
            return
        i = sum(x['hit'] for x in v)
        print(f'    {lab:<26} {100*i/len(v):5.1f}%  ({i}/{len(v)})'
              f'  {100*i/len(v)-base:+5.1f}pt')

    show('① ばらつき0.6未満', A)
    show('  くらべて 0.6以上', lambda x: x['sd'] is not None and not A(x))
    show('② ふだん4角7番手以内', B)
    show('  くらべて 8番手以降', lambda x: x['pos'] is not None and not B(x))
    show('③ 下げない', C)
    show('  くらべて 下げる', lambda x: x['gain'] is not None and not C(x))
    show('①＋②＋③', lambda x: A(x) and B(x) and C(x), mn=30)
    show('↑ × 渋った馬場', lambda x: A(x) and B(x) and C(x) and x['wet'], mn=25)
    print()
