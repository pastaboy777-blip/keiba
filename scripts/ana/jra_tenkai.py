# -*- coding: utf-8 -*-
"""4角の並びを、過去走だけで組む（展開予測）。

  python3 scripts/ana/jra_tenkai.py <pos.jsonl> <R> <距離> [--band 400]

netkeiba の AI展開予測と同じものを、中身の見える形で作る。
使うのは1頭あたり2つだけ。

  位置  ＝ 最終コーナーの正規化順位の中央値（0が先頭・1.00が最後方）
  終い  ＝ 自身の上り3F − そのレースの後半3F の中央値（マイナスほど速い）

どちらも「同じレースの中で自分がどこにいたか」なので、別の日・別の
メンバーのレースでも足し引きできる。絶対値ではない。

そして並べるときは、その鞍の18頭の中で相対化する。物差しは毎回変わる
（CLAUDE.md）。同じ位置0.60の馬でも、逃げ馬の多い鞍では後ろ、
差し馬ばかりの鞍では前になる。

同じ距離帯（±band m・同じ芝ダ）の走りに絞る。3走に満たない馬は
判定しない。測れないものを測れたことにしない。
"""
import json
import re
import statistics as st
import sys

SRC, R, TGT = sys.argv[1], sys.argv[2], int(sys.argv[3])
BAND = int(sys.argv[sys.argv.index('--band') + 1]) if '--band' in sys.argv else 400
D = [json.loads(l) for l in open(SRC, encoding='utf-8') if json.loads(l)['R'] == R]


def dnum(s):
    m = re.search(r'(\d{3,4})', s or '')
    return int(m.group(1)) if m else None


SURF = '芝' if TGT else ''
V = []
for h in D:
    runs = [r for r in h['runs'] if r['c4'] is not None]
    near = [r for r in runs if (r['dist'] or '').startswith(SURF)
            and dnum(r['dist']) and abs(dnum(r['dist']) - TGT) <= BAND]
    use = (near if len(near) >= 3 else runs)[:6]
    if len(use) < 3:
        V.append(dict(h=h, pos=None, gap=None, n=0, near=len(near), use=[]))
        continue
    g = [r['gap'] for r in use if r['gap'] is not None]
    V.append(dict(h=h, pos=st.median(r['c4'] for r in use),
                  gap=st.median(g) if g else None, n=len(use),
                  near=len(near), use=use,
                  spread=st.pstdev([r['c4'] for r in use])))

ok = [x for x in V if x['pos'] is not None and x['gap'] is not None]
mp = st.median(x['pos'] for x in ok)
mg = st.median(x['gap'] for x in ok)
# ぶれも鞍の中で相対化する。最大−最小は6走もあればどの馬も広くなるので、
# ばらつきは標準偏差で測り、この鞍で広いほうから1/3だけ印をつける
sp = sorted(x['spread'] for x in ok)
ms = sp[int(len(sp) * 2 / 3)]
print(f'■ {R}R　{TGT}m　{len(V)}頭　（同じ距離帯±{BAND}m の直近6走）')
print(f'  この鞍の物差し：位置の中央値 {mp:.2f}　終いの中央値 {mg:+.2f}秒\n')

ROW = [('先　頭', 0, .18), ('前　目', .18, .36), ('中　団', .36, .55),
       ('中団後', .55, .72), ('後　方', .72, 1.01)]
for lab, lo, hi in ROW:
    S = sorted([x for x in ok if lo <= x['pos'] < hi], key=lambda y: y['pos'])
    if not S:
        print(f'  {lab}　─')
        continue
    print(f'  {lab}　' + '  '.join(
        f"{int(x['h']['u']):>2}{x['h']['nm'][:6]}" for x in S))
print()

print(f'  {"番":>3} {"馬名":<13}{"位置":>6}{"終い":>8}{"ぶれ":>6}{"走":>4}  判定')
for x in sorted(V, key=lambda y: (y['pos'] is None, y['pos'] or 0)):
    h = x['h']
    if x['pos'] is None:
        print(f"  {int(h['u']):>3} {h['nm']:<13}{'―':>6}{'―':>8}{'―':>6}"
              f"{x['n']:>4}  材料不足")
        continue
    tag = []
    if x['pos'] > mp and x['gap'] < mg:
        tag.append('後ろ × 終い上位')
    if x['pos'] <= mp and x['gap'] < mg:
        tag.append('前 × 終い上位')
    if x['spread'] >= ms:
        tag.append('この鞍では位置が読みにくい')
    print(f"  {int(h['u']):>3} {h['nm']:<13}{x['pos']:>6.2f}{x['gap']:>+8.2f}"
          f"{x['spread']:>6.2f}{x['n']:>4}  {'／'.join(tag)}")

print('\n■ 根拠（該当馬の、使った走り）')
for x in sorted(ok, key=lambda y: -y['pos']):
    if not (x['pos'] > mp and x['gap'] < mg):
        continue
    h = x['h']
    print(f"\n  {int(h['u'])}番 {h['nm']}　{h['sxage']} {h['kin']}kg {h['jk']}")
    for r in x['use']:
        print(f"    {r['date']} {r['ba']:<7}{r['dist']:<8}{r['baba']:<2}"
              f"{r['n']:>3}頭 {r['pop']:>2}人気 {r['f']:>2}着  "
              f"4角{r['c4r']:>2}/{r['n']:<2} 上り{r['ag']}  終い{r['gap']:+.1f}")
