# -*- coding: utf-8 -*-
"""「毎回同じ上がりを出す」（上がりのばらつきが小さい）は効くのか。

今年の大井で、各馬のその鞍より前の走だけを使って
  ・同じ距離帯の上がりの中央値
  ・そのばらつき（標準偏差）
を出し、3着内率を見る。
"""
import json, re, statistics as st
from collections import defaultdict, Counter

SC = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
RS = []
for l in open(f'{SC}/ooi_2026_runs.jsonl', encoding='utf-8'):
    r = json.loads(l)
    if r.get('dist') and r.get('e'):
        RS.append(r)
RS.sort(key=lambda r: (r.get('ymd') or '', r['rid']))

H = defaultdict(list)          # 馬名 -> [(距離, 上がり), ...]
c = Counter()


def band(d):
    return 'S' if d <= 1300 else 'M' if d <= 1700 else 'L'


for r in RS:
    d = r['dist']
    for e in r['e']:
        nm = e['nm']
        past = [a for dd, a in H[nm] if band(dd) == band(d)]
        if not e.get('f', '').isdigit():
            continue
        hit = int(e['f']) <= 3
        pop = e.get('pop', '')
        thin = not (len(past) >= 4)
        if not thin:
            sd = st.pstdev(past[-5:])
            k = ('0.3未満' if sd < 0.3 else '0.3-0.6' if sd < 0.6
                 else '0.6-1.0' if sd < 1.0 else '1.0以上')
            c[(k, 'n')] += 1
            c[(k, 'i')] += hit
            if pop.isdigit() and int(pop) >= 6:
                c[(k, 'pn')] += 1
                c[(k, 'pi')] += hit
    for e in r['e']:
        if re.match(r'^\d+\.\d$', e.get('ag') or ''):
            H[e['nm']].append((d, float(e['ag'])))

print('■ 上がりのばらつき（同じ距離帯の直近5走、4走以上ある馬だけ）')
print(f"{'ばらつき':>10} {'全馬':>20} {'6番人気以下':>20}")
for k in ('0.3未満', '0.3-0.6', '0.6-1.0', '1.0以上'):
    n, i = c[(k, 'n')], c[(k, 'i')]
    pn, pi = c[(k, 'pn')], c[(k, 'pi')]
    a = f'{100*i/n:5.1f}% ({i}/{n})' if n else '－'
    b = f'{100*pi/pn:5.1f}% ({pi}/{pn})' if pn else '－'
    print(f'  {k:>8}  {a:>20} {b:>20}')
tn = sum(c[(k, 'n')] for k in ('0.3未満', '0.3-0.6', '0.6-1.0', '1.0以上'))
ti = sum(c[(k, 'i')] for k in ('0.3未満', '0.3-0.6', '0.6-1.0', '1.0以上'))
tpn = sum(c[(k, 'pn')] for k in ('0.3未満', '0.3-0.6', '0.6-1.0', '1.0以上'))
tpi = sum(c[(k, 'pi')] for k in ('0.3未満', '0.3-0.6', '0.6-1.0', '1.0以上'))
print(f'\n  この条件に入る馬ぜんぶ  {100*ti/tn:.1f}% ({ti}/{tn}) / '
      f'6番人気以下 {100*tpi/tpn:.1f}% ({tpi}/{tpn})')
