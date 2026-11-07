# -*- coding: utf-8 -*-
"""荒れた日の中身を、同じ日の他場と比べて説明する。

  python3 scripts/ana/jra_rough.py 福島:notes/.../2026030301.json:notes/.../fukushima_corner.json \
                                   京都:notes/.../2026080501.json \
                                   東京:notes/.../2026050501.json

「荒れた」は結果の言い換えでしかないので、荒れ方の中身を分ける。
  ① どの人気が来たか（＝どれだけ荒れたか）
  ② 前が残ったのか、差しが届いたのか（4角の位置）
  ③ 上がりがそのまま順位になったのか（上がり順位と着順の一致）
  ④ 決着の詰まり方（1着から3着までの差）
  ⑤ 距離と頭数の構成

③が低い日は「能力どおりに決まらない日」。
コーナーの括弧の中は同じ順位として扱う。
"""
import json
import re
import statistics as st
import sys
from collections import defaultdict


def load(spec):
    v = spec.split(':')
    ba, res = v[0], v[1]
    cor = json.load(open(v[2], encoding='utf-8')) if len(v) > 2 else {}
    D = json.load(open(res, encoding='utf-8'))
    out = []
    for k in sorted(D, key=lambda x: int(x)):
        r = D[k]
        if '障' in (r.get('surf') or '') or '障' in (r.get('title') or ''):
            continue
        ent = [e for e in r['e'] if str(e.get('f', '')).isdigit()]
        n = len(ent)
        if n < 6:
            continue
        c4 = (cor.get(k) or {}).get('c4') or {}
        lap = (cor.get(k) or {}).get('lap') or []
        # 上がり順位（速い順。同値は同順位）
        ags = sorted({float(e['ag']) for e in ent if e.get('ag')})
        rk = {a: i + 1 for i, a in enumerate(ags)}
        for e in ent:
            pop = e.get('pop', '')
            out.append(dict(
                ba=ba, R=int(k), surf=r.get('surf'), dist=r.get('dist'),
                baba=r.get('baba'), n=n, f=int(e['f']), u=int(e['u']),
                nm=e['nm'], tm=e.get('tm', ''),
                pop=int(pop) if str(pop).isdigit() else None,
                odds=float(e['odds']) if re.match(r'^[\d.]+$', e.get('odds') or '') else None,
                ag=float(e['ag']) if e.get('ag') else None,
                agr=rk.get(float(e['ag'])) if e.get('ag') else None,
                c4=c4.get(str(e['u'])), lap=lap))
    return out


def sec(t):
    m = re.match(r'(\d):(\d\d)\.(\d)', t or '')
    return int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 10 if m else None


SETS = [load(a) for a in sys.argv[1:]]

print('■ ① どの人気が来たか')
print(f'  {"":<6}{"1着馬の人気":<30}{"3着内の中央値":>12}{"6人気以降":>10}{"1番人気の3着内":>14}')
for S in SETS:
    ba = S[0]['ba']
    w = [x['pop'] for x in sorted(S, key=lambda y: (y['R'], y['f'])) if x['f'] == 1]
    h = [x['pop'] for x in S if x['f'] <= 3 and x['pop']]
    f1 = [x for x in S if x['pop'] == 1]
    print(f'  {ba:<6}{",".join(str(x) for x in w):<30}'
          f'{st.median(h):>12.1f}{100*sum(1 for x in h if x>=6)/len(h):>9.0f}%'
          f'{100*sum(1 for x in f1 if x["f"]<=3)/len(f1):>13.0f}%')

print('\n■ ② 3着内馬は、4角でどこにいたか（0が先頭・1.00が最後方）')
for S in SETS:
    T = [x for x in S if x['c4'] is not None]
    if not T:
        print(f'  {S[0]["ba"]:<6}（4角の材料なし）')
        continue
    h = [x['c4'] for x in T if x['f'] <= 3]
    print(f'  {S[0]["ba"]:<6}中央値 {st.median(h):.2f}　'
          f'上位1/3から {100*sum(1 for x in h if x<=1/3)/len(h):.0f}%　'
          f'下位1/3から {100*sum(1 for x in h if x>2/3)/len(h):.0f}%　({len(h)}頭)')
    for lo, hi, t in ((0, 1/3, '4角 上位1/3'), (1/3, 2/3, '4角 中1/3'),
                      (2/3, 1.01, '4角 下位1/3')):
        v = [x for x in T if lo <= x['c4'] < hi]
        if len(v) >= 20:
            print(f'      {t:<12}{len(v):>4}頭 3着内 {100*sum(1 for x in v if x["f"]<=3)/len(v):5.1f}%')

print('\n■ ③ 上がりがそのまま順位になったか')
print('   （上がり1位の馬が3着内に入った割合／3着内馬の上がり順位の中央値）')
for S in SETS:
    byR = defaultdict(list)
    for x in S:
        byR[x['R']].append(x)
    top, hit = 0, 0
    for R, v in byR.items():
        a = [x for x in v if x['agr'] == 1]
        if a:
            top += 1
            hit += any(x['f'] <= 3 for x in a)
    h = [x['agr'] for x in S if x['f'] <= 3 and x['agr']]
    print(f'  {S[0]["ba"]:<6}上がり1位が3着内 {hit}/{top}鞍'
          f'　3着内馬の上がり順位 中央値 {st.median(h):.1f}')

print('\n■ ④ 決着の詰まり方（1着から3着までのタイム差）')
for S in SETS:
    byR = defaultdict(dict)
    for x in S:
        if x['f'] <= 3:
            byR[x['R']][x['f']] = sec(x['tm'])
    d = [v[3] - v[1] for v in byR.values() if v.get(1) and v.get(3)]
    print(f'  {S[0]["ba"]:<6}中央値 {st.median(d):.1f}秒　'
          f'0.3秒以内に3頭 {sum(1 for x in d if x<=0.3)}/{len(d)}鞍')

print('\n■ ⑤ 構成（距離・頭数・馬場）')
for S in SETS:
    byR = {}
    for x in S:
        byR[x['R']] = x
    v = list(byR.values())
    short = [x for x in v if x['dist'] and x['dist'] <= 1400]
    print(f'  {S[0]["ba"]:<6}{len(v)}鞍　1400m以下 {len(short)}鞍　'
          f'頭数の中央値 {st.median([x["n"] for x in v]):.0f}　'
          f'馬場 {"・".join(sorted({x["baba"] for x in v if x["baba"]}))}')

print('\n■ ⑥ 人気薄（6番人気以降）が、どこから来たか')
for S in SETS:
    T = [x for x in S if x['c4'] is not None and x['pop'] and x['pop'] >= 6]
    if len(T) < 30:
        print(f'  {S[0]["ba"]:<6}（材料不足 {len(T)}）')
        continue
    print(f'  {S[0]["ba"]:<6}{len(T)}頭')
    for lo, hi, t in ((0, 1/3, '4角 上位1/3'), (1/3, 2/3, '4角 中1/3'),
                      (2/3, 1.01, '4角 下位1/3')):
        v = [x for x in T if lo <= x['c4'] < hi]
        if len(v) >= 15:
            print(f'      {t:<12}{len(v):>4}頭 3着内 '
                  f'{100*sum(1 for x in v if x["f"]<=3)/len(v):5.1f}%')
