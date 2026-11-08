# -*- coding: utf-8 -*-
"""4角で内にいたか外にいたかを、通過順の括弧から読む。

  python3 scripts/ana/jra_outside.py 福島:res.json:corner.json [場:res:corner ...]

netkeiba の凡例にこうある。
  (1,2,3) は1馬身未満の間隔で並走している馬群を「内側の馬番から」示します
つまり括弧の中の並び順が、そのまま内→外。

  外度 ＝ 括弧の中で内から何番目か ÷ (その群の頭数 − 1)   0が最内・1.00が最外
  単独で走っている馬は群がないので判定しない

これで「4角で後ろにいて、かつ外にいた馬」＝直線で外に出せた馬を切り出せる。
後ろにいても内で詰まった馬とは分けて数える。

着順は結果なので、これは「何が起きたか」の記述。
前日の材料にするには、枠順とふだんの位置から外に出せるかを読む必要がある。
"""
import json
import re
import statistics as st
import sys
from collections import defaultdict


def groups(s):
    """'(4,*10,13)(2,7)5' → [[4,10,13],[2,7],[5]] 並び順は内→外"""
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
for spec in sys.argv[1:]:
    ba, rp, cp = spec.split(':')
    R = json.load(open(rp, encoding='utf-8'))
    C = json.load(open(cp, encoding='utf-8'))
    for k, r in R.items():
        c = C.get(k)
        if not c or not c.get('corner_raw'):
            continue
        ent = [e for e in r['e'] if str(e.get('f', '')).isdigit()]
        n = len(ent)
        if n < 8:
            continue
        gs = groups(c['corner_raw'])
        pos, out, rank = {}, {}, 1
        for g in gs:
            for i, u in enumerate(g):
                pos[u] = (rank - 1) / (n - 1)
                out[u] = (i / (len(g) - 1)) if len(g) > 1 else None
            rank += len(g)
        ags = sorted({float(e['ag']) for e in ent if e.get('ag')})
        ar = {a: i + 1 for i, a in enumerate(ags)}
        for e in ent:
            u = int(e['u'])
            if u not in pos:
                continue
            p, o = e.get('pop', ''), e.get('odds', '')
            ROWS.append(dict(ba=ba, R=int(k), surf=r['surf'], dist=r['dist'], n=n,
                             nm=e['nm'], u=u, waku=int(e.get('waku') or 0),
                             f=int(e['f']), c4=pos[u], soto=out[u],
                             pop=int(p) if p.isdigit() else None,
                             odds=float(o) if re.match(r'^[\d.]+$', o or '') else None,
                             agr=ar.get(float(e['ag'])) if e.get('ag') else None))

print(f'■ 材料 {len(ROWS)}頭 / {len({(x["ba"], x["R"]) for x in ROWS})}鞍')
G = [x for x in ROWS if x['soto'] is not None]
print(f'  うち並走グループに入っていて内外が分かる {len(G)}頭 '
      f'({100*len(G)/len(ROWS):.0f}%)\n')


def blk(lab, S, mn=15):
    if len(S) < mn:
        print(f'  {lab:<26}材料不足({len(S)})')
        return
    h = [x for x in S if x['f'] <= 3]
    w = [x for x in S if x['f'] == 1]
    ret = sum(x['odds'] * 100 for x in w if x['odds']) / len(S)
    md = sorted(x['odds'] for x in h if x['odds'])
    print(f'  {lab:<26}{len(S):>4}頭 3着内{len(h):>3}頭 {100*len(h)/len(S):5.1f}%'
          f'  単勝回収{ret:5.0f}%'
          f'  3着内の単勝 中央値{(md[len(md)//2] if md else 0):>6.1f}倍')


print('■ ① 4角で後ろにいた馬を、内外で割る')
B = [x for x in G if x['c4'] > .5]
blk('後ろ × 外（外度0.5以上）', [x for x in B if x['soto'] >= .5])
blk('後ろ × 内（外度0.5未満）', [x for x in B if x['soto'] < .5])

print('\n■ ② 偽薬：前にいた馬にも同じ割り方を当てる')
F = [x for x in G if x['c4'] <= .5]
blk('前 × 外', [x for x in F if x['soto'] >= .5])
blk('前 × 内', [x for x in F if x['soto'] < .5])

print('\n■ ③ 後ろ × 外 を、さらに終いの速さで割る')
for t, f in (('上がり1〜3位', lambda x: x['agr'] and x['agr'] <= 3),
             ('上がり4位以下', lambda x: x['agr'] and x['agr'] > 3)):
    blk(f'後ろ × 外 × {t}', [x for x in B if x['soto'] >= .5 and f(x)])
    blk(f'後ろ × 内 × {t}', [x for x in B if x['soto'] < .5 and f(x)])

print('\n■ ④ 外に出せた馬は、枠が外だったのか（前日に読めるか）')
for t, lo, hi in (('内寄りの枠(1〜3枠)', 1, 3), ('中(4〜6枠)', 4, 6),
                  ('外寄りの枠(7〜8枠)', 7, 8)):
    S = [x for x in B if lo <= x['waku'] <= hi]
    if len(S) < 15:
        print(f'  {t:<26}材料不足({len(S)})')
        continue
    print(f'  {t:<26}{len(S):>4}頭  4角で外にいた割合 '
          f'{100*sum(1 for x in S if x["soto"]>=.5)/len(S):5.1f}%'
          f'  外度の中央値 {st.median(x["soto"] for x in S):.2f}')
