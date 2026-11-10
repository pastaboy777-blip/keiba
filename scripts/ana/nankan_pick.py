# -*- coding: utf-8 -*-
"""隊列と人気から、人気薄の該当馬を機械的に拾う。

  python3 scripts/ana/nankan_pick.py <nankan_raw.jsonl> <card.json> <odds.jsonl> [--before YYYYMMDD]

拾う条件（2026年の川崎159鞍と、11/9の実測から）

  人気薄（6番人気以降） かつ ポジションが振り切れている
    ふだん前   位置 ≤ 1/3
    ふだん後ろ 位置 > 2/3 かつ 終いが鞍の中央値より速い

中団は拾わない。11/9の川崎で、4角 中1/3にいた人気薄27頭は3着内ゼロだった。
好走した人気薄7頭は 前(0.00〜0.27)が4頭・後ろ(0.73〜1.00)が3頭で、
きれいに両端に割れている。

測定値
  川崎 重・不良 × 6番人気以降 × 4角 上位1/3   53頭 34.0%（期待13.5%）+20.5pt
  11/9の実測     人気薄 × 4角 上位1/3         15頭 26.7%
                人気薄 × 上がり1〜3位        13頭 30.8%
                人気薄 × 中1/3              27頭  0.0%

枠は11/9には効かなかった（1〜4枠の人気薄24頭で12.5%・全体9.5%）ので、
条件には入れず、参考として表示するだけにする。
"""
import json
import re
import statistics as st
import sys
from collections import defaultdict

SRC, CARD, ODDS = sys.argv[1], sys.argv[2], sys.argv[3]
YMD = sys.argv[sys.argv.index('--before') + 1] if '--before' in sys.argv else '99999999'


def groups(s):
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == '(':
            j = s.find(')', i)
            g = [int(x) for x in re.findall(r'\d+', s[i:j + 1])]
            if g:
                out.append(g)
            i = j + 1
        elif c.isdigit():
            j = i
            while j < len(s) and s[j].isdigit():
                j += 1
            out.append([int(s[i:j])])
            i = j
        else:
            i += 1
    return out


def waku(u, n):
    base, rem = divmod(n, 8)
    cnt = [base + (1 if (8 - i) < rem else 0) for i in range(1, 9)]
    s = 0
    for i, c in enumerate(cnt, 1):
        s += c
        if u <= s:
            return i
    return 8


H = defaultdict(list)
for l in open(SRC, encoding='utf-8'):
    r = json.loads(l)
    if r['ymd'] >= YMD:
        continue
    ent = [e for e in r['e'] if str(e.get('f', '')).isdigit()]
    n = len(ent)
    if n < 6:
        continue
    pos, rank = {}, 1
    for g in groups(r.get('c4') or ''):
        for u in g:
            pos[u] = (rank - 1) / (n - 1)
        rank += len(g)
    lap = r.get('lap') or []
    l3 = sum(lap[-3:]) if len(lap) >= 3 else None
    for e in ent:
        u = int(e['u'])
        if u not in pos:
            continue
        ag = float(e['ag']) if re.match(r'^[\d.]+$', e.get('ag') or '') else None
        H[e['nm']].append(dict(c4=pos[u], gap=(ag - l3) if (ag is not None and l3) else None,
                               ymd=r['ymd'], ba=r['ba'], dist=r.get('dist'),
                               f=int(e['f']), pop=e.get('pop'), n=n))

C = json.load(open(CARD, encoding='utf-8'))
O = {}
for l in open(ODDS, encoding='utf-8'):
    d = json.loads(l)
    O[int(d['rid'][-2:])] = {x['nm']: x for x in d['o']}

ALL = []
for R in range(1, 13):
    r = C.get(str(R))
    if not r:
        continue
    od = O.get(R, {})
    V = []
    for e in r['e']:
        v = H.get(e['nm'], [])[:8]
        o = od.get(e['nm'])
        if len(v) < 3:
            continue
        g = [x['gap'] for x in v if x['gap'] is not None]
        V.append(dict(u=e['u'], nm=e['nm'], waku=waku(e['u'], r['n']),
                      pop=o['pop'] if o else None, tan=o['tan'] if o else None,
                      pos=st.median(x['c4'] for x in v),
                      sd=st.pstdev([x['c4'] for x in v]),
                      gap=(st.median(g) if g else None), n=len(v), use=v))
    if not V:
        continue
    gs = [x['gap'] for x in V if x['gap'] is not None]
    mg = st.median(gs) if gs else None
    hit = []
    for x in V:
        if not x['pop'] or x['pop'] < 6:
            continue
        if x['pos'] <= 1 / 3:
            x['kind'] = '前'
            hit.append(x)
        elif x['pos'] > 2 / 3 and mg is not None and x['gap'] is not None and x['gap'] < mg:
            x['kind'] = '後ろ×終い'
            hit.append(x)
    print(f"\n■ {R}R {r['dist']}m {r['n']}頭"
          f"　（判定できた {len(V)}頭）" + ('' if hit else '　該当なし'))
    for x in sorted(hit, key=lambda y: (y['kind'] != '前', y['pos'])):
        gg = f"{x['gap']:+.2f}" if x['gap'] is not None else '  ―  '
        print(f"   {x['u']:>2}番 {x['nm']:<14}{x['pop']:>3}人気 単{x['tan']:>6.1f}"
              f"  {x['waku']}枠  位置{x['pos']:.2f} ぶれ{x['sd']:.2f} 終い{gg} {x['n']}走"
              f"  [{x['kind']}]")
        ALL.append((R, x))
print(f'\n■ 該当 {len(ALL)}頭')
if ALL:
    k = [x[1]['kind'] for x in ALL]
    print(f"   前 {k.count('前')}頭 ／ 後ろ×終い {k.count('後ろ×終い')}頭")
