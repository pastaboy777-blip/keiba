# -*- coding: utf-8 -*-
"""通過順位の記号から、各馬の中間の通過タイムを推定する。

  python3 scripts/ana/corner_split.py <corners_margin.jsonl> [場名]

考え方は米国の区間タイムと同じ。公式に測っているのは先頭だけで、
各馬の区間は「先頭の時計 ＋ 着差」から計算する。

  先頭の通過時計 … ハロンタイムの累積
  各馬の着差     … 通過順位の記号から読む

記号の読み方（馬身）
  ( )  ほぼ横並び   … 0
  ,    1馬身以内    … 0.7
  -    1〜2馬身     … 1.5
  =    大きくあいた … 3.0
1馬身は 0.21秒。これは置いた値ではなく、検算のズレがいちばん
小さくなる値を探して決めた（0.12〜0.25秒を試して 0.21 が最小）。
記号の馬身も 0.5/1.2 〜 1.0/2.2 を試し、0.7/1.5 が最小だった。

検算：4角の推定通過 ＋ 自身の上り3F ＝ 走破時計 になるはず。
この差を見れば、置いた数字が妥当かどうかが分かる。
"""
import json, re, statistics as st, sys
from collections import defaultdict

SRC = sys.argv[1]
BA = sys.argv[2] if len(sys.argv) > 2 else None
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
GAP = {',': 0.7, '-': 1.5, '=': 3.0}      # 記号 → 馬身
SEC_PER_LEN = 0.21                        # 1馬身あたりの秒数（詰めた値）


def parse_corner(s):
    """記号つきの通過順位を [(馬番, 先頭からの馬身)] に直す"""
    if not s:
        return None
    out, lead = [], 0.0
    i, cur = 0, []
    # ( ) でくくられた馬は同じ位置。くくりの外の記号が次との間隔
    toks = re.findall(r'\((?:\d+,?)+\)|\d+|[,=\-]', s)
    for t in toks:
        if t in GAP:
            lead += GAP[t]
            continue
        if t.startswith('('):
            for u in re.findall(r'\d+', t):
                out.append((int(u), lead))
        else:
            out.append((int(t), lead))
    return out


def sec(t):
    m = re.match(r'^(?:(\d+):)?(\d+)\.(\d)$', t.strip()) if t else None
    return None if not m else (int(m.group(1) or 0)) * 60 + int(m.group(2)) \
        + int(m.group(3)) / 10


CM = {}
for l in open(SRC, encoding='utf-8'):
    v = json.loads(l)
    CM[v['rid']] = v
R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
print(f'記号つきで取れた {len(CM)}鞍 / 全 {len(R)}鞍\n')

err, n, byba = [], 0, defaultdict(list)
for r in R:
    if BA and r['ba'] != BA:
        continue
    v = CM.get(r['rid'])
    lap = r.get('lap')
    if not v or not lap or not r.get('dist'):
        continue
    c4 = parse_corner(v.get('c4s'))
    if not c4:
        continue
    # 4角はゴールまで残り何メートルか。ハロンの刻みから、
    # 4角＝残り3〜4ハロンのあたりに置く（場で違うので後で詰める）
    nf = len(lap)
    k = max(0, nf - 3)                 # 残り3Fの地点を4角とみなす
    lead_t = sum(lap[:k])
    back = dict(c4)
    for e in r['e']:
        t, a = sec(e.get('tm')), sec(e.get('ag') or '')
        if t is None or a is None:
            continue
        b = back.get(int(e['u']))
        if b is None:
            continue
        est = lead_t + b * SEC_PER_LEN      # その馬の4角通過（推定）
        err.append((est + a) - t)           # 検算：＋上り3F ＝ 走破時計
        byba[r['ba']].append((est + a) - t)
        n += 1

if not err:
    raise SystemExit('まだ材料が足りない')
print('■ 検算　4角の推定通過 ＋ 自身の上り3F −（実際の走破時計）')
print(f'  {n}頭　中央値 {st.median(err):+.2f}秒　'
      f'絶対値の中央値 {st.median([abs(x) for x in err]):.2f}秒')
for ba, v in sorted(byba.items()):
    if len(v) >= 200:
        print(f'  {ba}  {len(v):>5}頭　中央値 {st.median(v):+.2f}　'
              f'絶対値 {st.median([abs(x) for x in v]):.2f}')
print('\n  中央値が0から離れていれば、4角の置き場所がずれている。')
print('  絶対値が大きければ、1馬身あたりの秒数か記号の読み方を詰める。')
