# -*- coding: utf-8 -*-
"""4角の位置を、場×距離ごとに実測から決める。

  python3 scripts/ana/corner_fit.py <corners_margin.jsonl> [場名]

corner_split.py では4角を「残り3ハロン」に置いていた。これはハロンの
刻みに合わせた近似で、実際の4角はコースごとに決まった場所にある。
  船橋 1周1250m・直線308m
  大井 1周1600m（内1400m）・直線386m
なので、残り600mぴったりではない。

ここでは逆に解く。
  4角の推定通過 ＋ 自身の上り3F ＝ 走破時計
が成り立つはずなので、「残り何メートルを4角とみなすと、ズレの中央値が
0になるか」を距離ごとに探す。先頭の通過時計はハロンの境目でしか
分からないので、境目のあいだは線形で埋める。

出てきた値はコースの実際の4角位置そのものではなく、
「上り3Fの計測地点と足し合わせてつじつまが合う地点」。
使うぶんにはこちらが正しい。

【結果と、この当てはめの読み方】
9区分すべてがぴったり600mに出た。これは当たり前の結果で、4角の
位置を当てたことにはならない。上り3Fはゴールから600mの地点で
計測しているので、「4角通過＋上り3F＝走破時計」が閉じる地点は
定義上600mしかない。
つまりこの当てはめが確かめているのは4角の位置ではなく、記号から
秒への換算（1馬身0.21秒・記号0.7/1.5/3.0）が妥当かどうか。
1頭あたりの絶対誤差が0.17〜0.26秒で収まったので、換算は使える。
"""
import json, re, statistics as st, sys
from collections import defaultdict

SRC = sys.argv[1]
BAF = sys.argv[2] if len(sys.argv) > 2 else None
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
GAP = {',': 0.7, '-': 1.5, '=': 3.0}
SEC_PER_LEN = 0.21


def parse_corner(s):
    if not s:
        return None
    out, lead = [], 0.0
    for t in re.findall(r'\((?:\d+,?)+\)|\d+|[,=\-]', s):
        if t in GAP:
            lead += GAP[t]
        elif t.startswith('('):
            for u in re.findall(r'\d+', t):
                out.append((int(u), lead))
        else:
            out.append((int(t), lead))
    return out


def sec(t):
    m = re.match(r'^(?:(\d+):)?(\d+)\.(\d)$', t.strip()) if t else None
    return None if not m else (int(m.group(1) or 0)) * 60 + int(m.group(2)) \
        + int(m.group(3)) / 10


def segs(dist, lap):
    """各ハロンが受け持つメートル。1本目だけ100mや150mになる"""
    n = len(lap)
    return [dist - 200 * (n - 1)] + [200] * (n - 1)


def lead_at(dist, lap, rest):
    """先頭が「残り rest メートル」を通った時計。境目の間は線形で埋める"""
    sg = segs(dist, lap)
    pos, t = 0.0, 0.0
    target = dist - rest
    if target <= 0:
        return 0.0
    for d, l in zip(sg, lap):
        if pos + d >= target:
            return t + l * (target - pos) / d
        pos += d
        t += l
    return t


CM = {}
for l in open(SRC, encoding='utf-8'):
    v = json.loads(l)
    CM[v['rid']] = v
R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]

# (場, 距離) -> [(先頭の時計を出すのに必要な材料, 馬身, 上り3F, 走破時計)]
BK = defaultdict(list)
for r in R:
    if BAF and r['ba'] != BAF:
        continue
    v, lap = CM.get(r['rid']), r.get('lap')
    if not v or not lap or not r.get('dist'):
        continue
    c4 = parse_corner(v.get('c4s'))
    if not c4:
        continue
    back = dict(c4)
    for e in r['e']:
        t, a = sec(e.get('tm')), sec(e.get('ag') or '')
        if t is None or a is None:
            continue
        b = back.get(int(e['u']))
        if b is None:
            continue
        BK[(r['ba'], r['dist'])].append((r['dist'], tuple(lap), b, a, t))

print('■ 4角とみなす地点を、場×距離ごとに実測から決める')
print('   （上り3Fと足して走破時計になる地点。残り600mからのずれも出す）\n')
print(f'  {"場":<4}{"距離":>6}  {"頭数":>5}  {"4角=残り":>8}  '
      f'{"600mとの差":>9}  {"絶対誤差":>7}')
FIT = {}
for k in sorted(BK, key=lambda x: (x[0], x[1])):
    rows = BK[k]
    if len(rows) < 150:
        continue
    best = None
    for rest in range(450, 801, 5):
        err = [(lead_at(d, list(lp), rest) + b * SEC_PER_LEN + a) - t
               for d, lp, b, a, t in rows]
        m = abs(st.median(err))
        if best is None or m < best[0]:
            best = (m, rest, err)
    _, rest, err = best
    FIT[k] = rest
    ab = st.median([abs(x) for x in err])
    print(f'  {k[0]:<4}{k[1]:>6}  {len(rows):>5}  {rest:>7}m  '
          f'{rest-600:>+8}m  {ab:>7.2f}秒')

json.dump({f'{a}|{b}': v for (a, b), v in FIT.items()},
          open(f'{SP}/corner_fit.json', 'w'), ensure_ascii=False)
print(f'\n  → {SP}/corner_fit.json に保存')
