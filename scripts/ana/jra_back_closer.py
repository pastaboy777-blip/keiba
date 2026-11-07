# -*- coding: utf-8 -*-
"""土曜に穴を出した形（4角で後ろ × 終いが速い）に、日曜の出走馬を当てる。

  python3 scripts/ana/jra_back_closer.py <pos.jsonl> [R,R,...]

土曜の福島188頭（11/7）
  4角 前   × 上がり1〜3位   14頭 3着内12頭 85.7%  3着内の単勝 中央値 10.2倍
  4角 前   × 上がり4位以下  55頭 3着内12頭 21.8%  3着内の単勝 中央値  8.0倍
  4角 後ろ × 上がり1〜3位   18頭 3着内 3頭 16.7%  3着内の単勝 中央値 28.6倍
  4角 後ろ × 上がり4位以下  41頭 3着内 0頭  0.0%  ―

前日に当てられるのは、その馬がふだんどこを走るか。
  位置   ＝ 最終コーナーの正規化順位の中央値（0が先頭）
  終い   ＝ 自身の上り3F − そのレースの後半3F の中央値（マイナスほど速い）

同じ条件で走ったときだけを見たいので、同じ距離帯（±200m）に絞る。
3走に満たない馬は判定しない。測れないものを測れたことにしない。
"""
import json
import re
import statistics as st
import sys

SRC = sys.argv[1]
ONLY = sys.argv[2].split(',') if len(sys.argv) > 2 else None
D = [json.loads(l) for l in open(SRC, encoding='utf-8')]
if ONLY:
    D = [x for x in D if x['R'] in ONLY]


def dist(s):
    m = re.search(r'(\d{3,4})', s or '')
    return int(m.group(1)) if m else None


def surf(s):
    return (s or '')[:1]


OUT = {}
for h in D:
    runs = [r for r in h['runs'] if r['c4'] is not None]
    tgt = 1200                      # 芝1200の鞍に当てる
    near = [r for r in runs if surf(r['dist']) == '芝'
            and dist(r['dist']) and abs(dist(r['dist']) - tgt) <= 200]
    use = near if len(near) >= 3 else runs
    if len(use) < 3:
        OUT.setdefault(h['R'], []).append(dict(h=h, pos=None, gap=None, n=0, near=len(near)))
        continue
    use = use[:6]                   # 直近6走まで
    g = [r['gap'] for r in use if r['gap'] is not None]
    OUT.setdefault(h['R'], []).append(dict(
        h=h, pos=st.median(r['c4'] for r in use),
        gap=st.median(g) if g else None, n=len(use), near=len(near),
        last=use[:5]))

for R in sorted(OUT, key=int):
    V = OUT[R]
    print(f'\n═══ 福島 {R}R　芝1200m　{len(V)}頭 ' + '═' * 28)
    ok = [x for x in V if x['pos'] is not None and x['gap'] is not None]
    # 鞍の中で相対化する。物差しはその鞍のメンバーで決まる（CLAUDE.md）
    ps = sorted(x['pos'] for x in ok)
    gs = sorted(x['gap'] for x in ok)
    print(f'  この鞍の物差し：位置の中央値 {st.median(ps):.2f}　'
          f'終いの中央値 {st.median(gs):+.2f}秒')
    print(f'  {"番":>3} {"馬名":<13}{"位置":>6}{"終い":>8}{"走":>4}  近走')
    for x in sorted(V, key=lambda y: (y['pos'] is None, -(y['pos'] or 0))):
        h = x['h']
        if x['pos'] is None:
            print(f'  {h["u"]:>3} {h["nm"]:<13}{"―":>6}{"―":>8}{x["n"]:>4}  材料不足')
            continue
        mark = ''
        if x['pos'] > st.median(ps) and x['gap'] < st.median(gs):
            mark = '  ← 後ろ × 終い上位'
        rec = ' '.join(f'{r["f"]}着({r["pop"]}人)' for r in x['last'][:4])
        print(f'  {h["u"]:>3} {h["nm"]:<13}{x["pos"]:>6.2f}{x["gap"]:>+8.2f}'
              f'{x["n"]:>4}  {rec}{mark}')
