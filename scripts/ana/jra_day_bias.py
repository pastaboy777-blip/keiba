# -*- coding: utf-8 -*-
"""中央の当日結果から、枠と脚質の傾向を出す。

  python3 scripts/ana/jra_day_bias.py notes/live/2026-11-07/2026050501.json 東京

生の3着内率は人気でほとんど説明がついてしまうので、人気別の3着内率から
期待値を出して、実績との差（上振れpt）も並べる。
障害は上りの意味が違うので外す。
"""
import json
import re
import statistics as st
import sys
from collections import defaultdict

SRC = sys.argv[1]
BA = sys.argv[2] if len(sys.argv) > 2 else ''
D = json.load(open(SRC, encoding='utf-8'))

ROWS = []
for k in sorted(D, key=lambda x: int(x) if str(x).isdigit() else 99):
    r = D[k]
    surf = r.get('surf') or ''
    if '障' in surf or '障' in (r.get('title') or ''):
        continue
    ent = [e for e in r['e'] if str(e.get('f', '')).isdigit()]
    n = len(ent)
    if n < 6:
        continue
    for e in ent:
        pop = e.get('pop', '')
        u = int(e['u'])
        ps = [int(x) for x in re.findall(r'\d+', e.get('pass_') or '')]
        ROWS.append(dict(
            R=int(k), surf=surf, dist=r.get('dist'), baba=r.get('baba'),
            n=n, u=u, waku=int(e.get('waku') or 0),
            pos=(u - 1) / (n - 1) if n > 1 else .5,
            f=int(e['f']), hit=int(e['f']) <= 3,
            pop=int(pop) if str(pop).isdigit() else None,
            c4=(ps[-1] if ps else None),
            crel=((ps[-1] - 1) / (n - 1)) if (ps and n > 1) else None,
            ag=e.get('ag'), hid=e.get('hid'), nm=e['nm']))

# 人気別の3着内率（この日の全場ぶんが理想だが、1場でも目安になる）
byp = defaultdict(lambda: [0, 0])
for x in ROWS:
    if x['pop']:
        byp[x['pop']][0] += 1
        byp[x['pop']][1] += x['hit']
EXP = {p: (b / a) for p, (a, b) in byp.items() if a >= 3}


def blk(lab, S):
    if len(S) < 25:
        print(f'  {lab:<22} 材料不足({len(S)})')
        return
    hit = sum(x['hit'] for x in S)
    exp = sum(EXP.get(x['pop'], 0) for x in S if x['pop'])
    m = len([x for x in S if x['pop']])
    print(f'  {lab:<22}{len(S):>4}頭 3着内{100*hit/len(S):5.1f}%'
          f'  人気からの期待{100*exp/m:5.1f}%  上振れ{100*(hit/len(S))-100*exp/m:+6.1f}pt')


for surf in ('芝', 'ダ'):
    S = [x for x in ROWS if surf in (x['surf'] or '')]
    if len(S) < 30:
        continue
    bb = {x['baba'] for x in S}
    print(f'\n■ {BA} {surf}　{len(S)}頭 / '
          f'{len({x["R"] for x in S})}鞍　馬場 {"・".join(sorted(bb))}')
    print(' 〈枠〉')
    blk('内1/3', [x for x in S if x['pos'] <= 1 / 3])
    blk('中1/3', [x for x in S if 1 / 3 < x['pos'] <= 2 / 3])
    blk('外1/3', [x for x in S if x['pos'] > 2 / 3])
    print(' 〈4角の位置〉')
    T = [x for x in S if x['crel'] is not None]
    blk('先頭から上位1/3', [x for x in T if x['crel'] <= 1 / 3])
    blk('中1/3', [x for x in T if 1 / 3 < x['crel'] <= 2 / 3])
    blk('下位1/3', [x for x in T if x['crel'] > 2 / 3])
    w = [x['crel'] for x in T if x['hit']]
    if w:
        print(f'  3着内馬の4角位置 中央値 {st.median(w):.2f}'
              f'　上位1/3の割合 {100*sum(1 for x in w if x<=1/3)/len(w):.0f}%')
    print(' 〈距離を分ける〉')
    for lo, hi, t in ((0, 1400, '〜1400m'), (1401, 1900, '1500〜1800m'),
                      (1901, 9999, '1900m〜')):
        v = [x for x in S if x['dist'] and lo <= x['dist'] <= hi]
        if len(v) >= 30:
            print(f'  {t}')
            blk('   内1/3', [x for x in v if x['pos'] <= 1 / 3])
            blk('   外1/3', [x for x in v if x['pos'] > 2 / 3])
