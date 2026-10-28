# -*- coding: utf-8 -*-
"""上がりのばらつきを、もう少し疑って測り直す。

(1) 0.3未満が0.3-0.6より低いのは本当か（母数と幅）
(2) ばらつきが小さい馬は、そもそも上がりが速いだけではないか
(3) 走数で切り方が変わらないか
(4) ほかの材料（位置・壁までの余裕）に足して上がるのか
"""
import json, math, re, statistics as st
from collections import defaultdict, Counter

SC = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
RS = []
for l in open(f'{SC}/ooi_2026_runs.jsonl', encoding='utf-8'):
    r = json.loads(l)
    if r.get('dist') and r.get('e'):
        RS.append(r)
RS.sort(key=lambda r: (r.get('ymd') or '', r['rid']))


def band(d):
    return 'S' if d <= 1300 else 'M' if d <= 1700 else 'L'


def ci(i, n):
    """3着内率の幅（ウィルソンの95%）"""
    if not n:
        return (0, 0)
    p, z = i / n, 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * (c - w), 100 * (c + w))


H = defaultdict(list)
ROWS = []                       # 人気薄の1頭ぶん
for r in RS:
    d, n = r['dist'], len(r['e'])
    # その鞍の、同距離帯の上がり中央値での順位を作る（事前に分かる形）
    cand = []
    for e in r['e']:
        past = [a for dd, a in H[e['nm']] if band(dd) == band(d)]
        cand.append((e, past))
    mids = {e['nm']: (st.median(p[-5:]) if len(p) >= 4 else None)
            for e, p in cand}
    have = sorted([v for v in mids.values() if v is not None])
    for e, past in cand:
        if not e.get('f', '').isdigit():
            continue
        pop = e.get('pop', '')
        if not pop.isdigit() or int(pop) < 6:
            continue
        if len(past) < 4:
            continue
        p5 = past[-5:]
        sd = st.pstdev(p5)
        mid = st.median(p5)
        rk = have.index(mid) + 1 if mid in have else None
        ROWS.append(dict(nm=e['nm'], hit=int(e['f']) <= 3, win=e['f'] == '1',
                         sd=sd, mid=mid, rk=rk, nh=len(have), n=n,
                         nrun=len(past), pop=int(pop), dist=d,
                         baba=r.get('baba')))
    # この鞍を過去に積む（次の鞍から材料になる）
    for e in r['e']:
        if re.match(r'^\d+\.\d$', e.get('ag') or ''):
            H[e['nm']].append((d, float(e['ag'])))

print(f'人気薄（6番人気以下）で上がりの材料が4走以上ある {len(ROWS)}頭で測る')
BASE = sum(x['hit'] for x in ROWS) / len(ROWS)
print(f'この層ぜんぶの3着内率 {100*BASE:.1f}%\n')


def tab(key, bins, lab):
    print(f'■ {lab}')
    print(f"{'':>12} {'3着内率':>9} {'的中/頭数':>12} {'95%の幅':>16}")
    for name, f in bins:
        v = [x for x in ROWS if f(x[key])]
        if not v:
            continue
        i, n = sum(x['hit'] for x in v), len(v)
        lo, hi = ci(i, n)
        print(f'  {name:>10}  {100*i/n:7.1f}%  {i:>5}/{n:<6} '
              f'{lo:5.1f} 〜 {hi:4.1f}%')
    print()


tab('sd', [('0.3未満', lambda v: v < 0.3), ('0.3-0.6', lambda v: 0.3 <= v < 0.6),
           ('0.6-1.0', lambda v: 0.6 <= v < 1.0), ('1.0以上', lambda v: v >= 1.0)],
    '(1) ばらつき ── 幅つきで見る')

tab('sd', [('0.6未満', lambda v: v < 0.6), ('0.6以上', lambda v: v >= 0.6)],
    '    2つに割ると')

print('■ (2) ばらつきが小さい馬は、上がりそのものも速いのか')
a = [x['sd'] for x in ROWS]
b = [x['rk'] / x['nh'] for x in ROWS if x['rk']]
a2 = [x['sd'] for x in ROWS if x['rk']]
ma, mb = st.mean(a2), st.mean(b)
num = sum((x - ma) * (y - mb) for x, y in zip(a2, b))
den = (sum((x - ma) ** 2 for x in a2) * sum((y - mb) ** 2 for y in b)) ** .5
print(f'  ばらつき と 鞍内の上がり順位（上位からの割合）の相関 {num/den:+.2f}')
print('  → 0に近ければ別の材料。大きければ「速い馬を拾っているだけ」\n')

print('■ (3) 上がり順位で分けたうえで、ばらつきが効くか')
print(f"{'上がり順位':>12} {'ばらつき':>9} {'3着内率':>9} {'的中/頭数':>12}")
for rname, rf in (('鞍内3位以内', lambda x: x['rk'] and x['rk'] <= 3),
                  ('4位以下', lambda x: x['rk'] and x['rk'] > 3)):
    for sname, sf in (('0.6未満', lambda v: v < 0.6), ('0.6以上', lambda v: v >= 0.6)):
        v = [x for x in ROWS if rf(x) and sf(x['sd'])]
        if not v:
            continue
        i, n = sum(x['hit'] for x in v), len(v)
        print(f'  {rname:>10}  {sname:>8}  {100*i/n:7.1f}%  {i:>5}/{n}')
print()

print('■ (4) 走数で切り方が変わるか')
for nname, nf in (('4走', lambda v: v == 4), ('5走以上', lambda v: v >= 5)):
    for sname, sf in (('0.6未満', lambda v: v < 0.6), ('0.6以上', lambda v: v >= 0.6)):
        v = [x for x in ROWS if nf(x['nrun']) and sf(x['sd'])]
        if not v:
            continue
        i, n = sum(x['hit'] for x in v), len(v)
        print(f'  {nname:>6}  {sname:>8}  {100*i/n:7.1f}%  {i:>5}/{n}')
print()

print('■ (5) 馬場・距離で向きが変わるか（0.6未満 − 0.6以上）')
for lab, f in (('良・稍重', lambda x: x['baba'] not in ('重', '不良')),
               ('重・不良', lambda x: x['baba'] in ('重', '不良')),
               ('1300m以下', lambda x: x['dist'] <= 1300),
               ('1400-1700m', lambda x: 1400 <= x['dist'] <= 1700),
               ('1800m以上', lambda x: x['dist'] >= 1800)):
    lo = [x for x in ROWS if f(x) and x['sd'] < 0.6]
    hi = [x for x in ROWS if f(x) and x['sd'] >= 0.6]
    if not lo or not hi:
        continue
    pl = sum(x['hit'] for x in lo) / len(lo)
    ph = sum(x['hit'] for x in hi) / len(hi)
    print(f'  {lab:>11}  {100*pl:5.1f}% ({len(lo)}頭) vs {100*ph:5.1f}% '
          f'({len(hi)}頭)   差 {100*(pl-ph):+5.1f}pt')
