# -*- coding: utf-8 -*-
"""南関の、馬場状態ごとの中身を出す。

  python3 scripts/ana/nankan_wet.py <nankan_raw.jsonl> 川崎

重馬場は「前が止まらない」と言われるが、言葉で終わらせずに分ける。

  ① 4角でどこにいたか（前後）        ふだんと変わるのか
  ② 括弧の中で内から何番目か（内外）   渋ると内が荒れて外が伸びる、という話の確認
  ③ ペース（前半3F − 後半3F）        前が飛ばしているのか、垂れているのか
  ④ どの人気が来たか
  ⑤ 買う厩舎

どれも人気の帯をそろえた上振れptで見る。生の3着内率は人気でほとんど説明がつく。
括弧の中は内→外（楽天・netkeiba とも。実データで確かめた）。
"""
import json
import re
import statistics as st
import sys
from collections import defaultdict

SRC = sys.argv[1]
BA = sys.argv[2] if len(sys.argv) > 2 else '川崎'


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


ROWS = []
for l in open(SRC, encoding='utf-8'):
    r = json.loads(l)
    if r['ba'] != BA:
        continue
    ent = [e for e in r['e'] if str(e.get('f', '')).isdigit()]
    n = len(ent)
    if n < 8:
        continue
    s = r.get('c4') or ''
    pos, out, rank = {}, {}, 1
    for g in groups(s):
        for i, u in enumerate(g):
            pos[u] = (rank - 1) / (n - 1)
            out[u] = (i / (len(g) - 1)) if len(g) > 1 else None
        rank += len(g)
    lap = r.get('lap') or []
    d = (sum(lap[-3:]) - sum(lap[:3])) if len(lap) >= 6 else None
    ags = sorted({float(e['ag']) for e in ent if re.match(r'^[\d.]+$', e.get('ag') or '')})
    rk = {a: i + 1 for i, a in enumerate(ags)}
    for e in ent:
        u = int(e['u'])
        p = e.get('pop', '')
        ag = float(e['ag']) if re.match(r'^[\d.]+$', e.get('ag') or '') else None
        ROWS.append(dict(
            rid=r['rid'], ymd=r['ymd'], baba=r.get('baba'), dist=r.get('dist'),
            n=n, u=u, waku=int(e.get('waku') or 0), nm=e['nm'], tr=e.get('tr'),
            f=int(e['f']), pop=int(p) if str(p).isdigit() else None,
            c4=pos.get(u), soto=out.get(u), agr=rk.get(ag), d=d))

byp = defaultdict(lambda: [0, 0])
for x in ROWS:
    if x['pop']:
        byp[x['pop']][0] += 1
        byp[x['pop']][1] += (x['f'] <= 3)
EXP = {p: b / a for p, (a, b) in byp.items() if a >= 20}


def ed(S):
    h = sum(1 for x in S if x['f'] <= 3)
    m = [x for x in S if x['pop'] in EXP]
    if not m:
        return None, None, 0
    e = sum(EXP[x['pop']] for x in m) / len(m)
    return 100 * h / len(S), 100 * e, 100 * h / len(S) - 100 * e


def blk(lab, S, mn=30):
    if len(S) < mn:
        print(f'    {lab:<22}材料不足({len(S)})')
        return
    a, b, c = ed(S)
    print(f'    {lab:<22}{len(S):>5}頭 3着内{a:5.1f}%  期待{b:5.1f}%  上振れ{c:+6.1f}pt')


BABA = [('良', ('良',)), ('稍重', ('稍重',)), ('重・不良', ('重', '不良'))]
print(f'■ {BA}　{len({x["rid"] for x in ROWS})}鞍 {len(ROWS)}頭')
for t, ks in BABA:
    v = [x for x in ROWS if x['baba'] in ks]
    print(f'   {t:<8}{len({x["rid"] for x in v}):>4}鞍 {len(v):>5}頭')

print('\n■ ① 4角でどこにいたか（0が先頭・1.00が最後方）')
for t, ks in BABA:
    v = [x for x in ROWS if x['baba'] in ks and x['c4'] is not None]
    if len(v) < 60:
        continue
    h = [x['c4'] for x in v if x['f'] <= 3]
    print(f'  〈{t}〉3着内馬の4角 中央値 {st.median(h):.2f}　'
          f'上位1/3から {100*sum(1 for x in h if x<=1/3)/len(h):.0f}%')
    blk('4角 上位1/3', [x for x in v if x['c4'] <= 1 / 3])
    blk('4角 中1/3', [x for x in v if 1 / 3 < x['c4'] <= 2 / 3])
    blk('4角 下位1/3', [x for x in v if x['c4'] > 2 / 3])

print('\n■ ② 内か外か（括弧の中で内から何番目。0が最内・1.00が最外）')
for t, ks in BABA:
    v = [x for x in ROWS if x['baba'] in ks and x['soto'] is not None]
    if len(v) < 60:
        continue
    print(f'  〈{t}〉内外が読める {len(v)}頭')
    blk('外（0.5以上）', [x for x in v if x['soto'] >= .5])
    blk('内（0.5未満）', [x for x in v if x['soto'] < .5])
    F = [x for x in v if x['c4'] is not None and x['c4'] <= .5]
    blk('前 × 外', [x for x in F if x['soto'] >= .5])
    blk('前 × 内', [x for x in F if x['soto'] < .5])

print('\n■ ③ ペース（後半3F − 前半3F。プラスほど前が垂れている）')
for t, ks in BABA:
    v = [x['d'] for x in {x['rid']: x for x in ROWS if x['baba'] in ks}.values()
         if x['d'] is not None]
    if len(v) >= 15:
        print(f'  {t:<8}{len(v):>4}鞍　中央値 {st.median(v):+.2f}秒')

print('\n■ ④ どの人気が来たか')
for t, ks in BABA:
    v = [x for x in ROWS if x['baba'] in ks]
    h = [x['pop'] for x in v if x['f'] <= 3 and x['pop']]
    if len(h) < 40:
        continue
    print(f'  {t:<8}3着内馬の人気 中央値 {st.median(h):.1f}　'
          f'6番人気以降が {100*sum(1 for x in h if x>=6)/len(h):.0f}%')

print('\n■ ⑤ 重・不良で買う厩舎（3着内が多い順・10頭以上）')
W = [x for x in ROWS if x['baba'] in ('重', '不良')]
g = defaultdict(list)
for x in W:
    if x['tr']:
        g[x['tr']].append(x)
v = []
for k, S in g.items():
    if len(S) < 10:
        continue
    a, b, c = ed(S)
    if c is not None:
        v.append((c, a, len(S), k))
for c, a, n, k in sorted(v, reverse=True)[:12]:
    print(f'    {k:<12}{n:>4}頭 3着内{a:5.1f}%  上振れ{c:+6.1f}pt')
