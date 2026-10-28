# -*- coding: utf-8 -*-
"""「速さ」は加速ではなく減速の小ささか、を今年の大井のラップで測る。

  python3 scripts/ana/ooi_decel.py

(1) ラップの形 ── 最高速はどこで出て、そのあとどうなるか
(2) 走破時計のちらばりは、前半と後半のどちらから来ているか
(3) 1頭ごとに ── 前に行ったことと、落ちなかったこと、どちらが着順に効くか
"""
import json, re, statistics as st
from collections import defaultdict

SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')


def sec(t):
    m = re.match(r'^(?:(\d+):)?(\d+)\.(\d)$', t.strip()) if t else None
    return None if not m else (int(m.group(1) or 0)) * 60 + int(m.group(2)) \
        + int(m.group(3)) / 10


def cor(a, b):
    ma, mb = st.mean(a), st.mean(b)
    n = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    d = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** .5
    return n / d if d else 0


LAP = {}
for l in open(f'{SP}/corners_2026.jsonl', encoding='utf-8'):
    v = json.loads(l)
    if v.get('lap'):
        LAP[v['rid']] = v['lap']
R2 = []
for l in open(f'{SP}/ooi_2026_runs.jsonl', encoding='utf-8'):
    r = json.loads(l)
    if r.get('dist') and r.get('e'):
        R2.append(r)

print('■ (1) ラップの形（今年の大井・各ハロンの中央値）')
for dist in (1200, 1400, 1600, 1800):
    v = [LAP[r['rid']] for r in R2
         if r['dist'] == dist and r['rid'] in LAP
         and len(LAP[r['rid']]) == dist // 200]
    if len(v) < 20:
        continue
    med = [st.median([x[i] for x in v]) for i in range(len(v[0]))]
    fast = med.index(min(med))
    s = '  '.join(f'{"[" if i == fast else " "}{x:.1f}'
                  f'{"]" if i == fast else " "}' for i, x in enumerate(med))
    print(f'  {dist}m {len(v):>3}鞍   {s}')
    print(f'{"":>14}   最高速は{fast+1}本目。そこから最後までで '
          f'{med[-1]-min(med):+.1f}秒おちる')

print('\n■ (2) 走破時計のちらばりは、前半と後半のどちらから来ているか')
print(f'{"":>8} {"前3F":>22} {"上り3F":>22}')
for dist in (1200, 1400, 1600):
    rows = []
    for r in R2:
        lap = LAP.get(r['rid'])
        if not lap or len(lap) != dist // 200:
            continue
        ts = sorted(x for x in (sec(e['tm']) for e in r['e']) if x)
        if len(ts) < 3:
            continue
        rows.append((sum(lap[:3]), sum(lap[-3:]), ts[0]))
    if len(rows) < 20:
        continue
    f3 = [x[0] for x in rows]
    a3 = [x[1] for x in rows]
    tt = [x[2] for x in rows]
    print(f'  {dist}m {len(rows):>3}鞍  '
          f'ばらつき {st.pstdev(f3):.2f}秒 / 勝ち時計との相関 {cor(f3, tt):+.2f}   '
          f'ばらつき {st.pstdev(a3):.2f}秒 / 相関 {cor(a3, tt):+.2f}')

print('\n■ (3) 1頭ごと ── 前に行ったことと、落ちなかったこと')
print('   自前半＝走破時計−自身の上り3F。どちらも鞍の中央からの差で見る。')
H = defaultdict(lambda: [0, 0])
for r in R2:
    hs = []
    for e in r['e']:
        t, a = sec(e['tm']), sec(e.get('ag') or '')
        if t and a and e.get('f', '').isdigit():
            hs.append((e, t - a, a))
    if len(hs) < 7:
        continue
    mh = st.median([x[1] for x in hs])
    ma = st.median([x[2] for x in hs])
    for e, h, a in hs:
        dh, da = h - mh, a - ma            # マイナスほど速い
        kh = ('前半 速い' if dh <= -0.3 else '前半 ふつう' if dh < 0.3
              else '前半 おそい')
        ka = ('上り 速い' if da <= -0.3 else '上り ふつう' if da < 0.3
              else '上り おそい')
        hit = int(e['f']) <= 3
        H[(kh, ka)][0] += hit
        H[(kh, ka)][1] += 1
        H[('合計', ka)][0] += hit
        H[('合計', ka)][1] += 1
        H[(kh, '合計')][0] += hit
        H[(kh, '合計')][1] += 1

KH = ['前半 速い', '前半 ふつう', '前半 おそい', '合計']
KA = ['上り 速い', '上り ふつう', '上り おそい', '合計']
print(f'\n{"":>12}' + ''.join(f'{k:>16}' for k in KA))
for kh in KH:
    cells = ''
    for ka in KA:
        i, n = H[(kh, ka)]
        cells += f'{(f"{100*i/n:.1f}% ({n})" if n else "-"):>16}'
    print(f'{kh:>12}' + cells)
