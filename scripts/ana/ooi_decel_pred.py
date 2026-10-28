# -*- coding: utf-8 -*-
"""「減速しない馬」を発走前に見分けられるかを測る。

  python3 scripts/ana/ooi_decel_pred.py

1頭1走を、鞍の中央からの差で2つに分ける。
  dh … 自前半のズレ（マイナスほど前に行った）
  da … 上がりのズレ（マイナスほど落ちなかった）
走破時計のズレは dh+da、使い方のクセは da-dh。後者を「減速ぐせ」と呼ぶ。

(1) 減速ぐせは、その馬の性質として次走に残るか
(2) 残るとして、着順に効くか。走破時計の実力を抜いても残るか
(3) 普段の4角位置を抜いても残るか（ただの差し馬ではないか）
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


CN = {}
for l in open(f'{SP}/corners_2026.jsonl', encoding='utf-8'):
    v = json.loads(l)
    if v.get('c4'):
        CN[v['rid']] = v['c4']
R2 = []
for l in open(f'{SP}/ooi_2026_runs.jsonl', encoding='utf-8'):
    r = json.loads(l)
    if r.get('dist') and r.get('e'):
        R2.append(r)
R2.sort(key=lambda r: (r.get('ymd') or '', r['rid']))

H = defaultdict(list)          # 馬名 -> [(減速ぐせ, 走破のズレ, 4角の割合), ...]
PAIR, ROWS = [], []
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
    c4 = CN.get(r['rid']) or []
    idx = {u: (i + 1) / len(c4) for i, u in enumerate(c4)} if c4 else {}
    for e, h, a in hs:
        dh, da = h - mh, a - ma
        D, T = da - dh, da + dh          # 減速ぐせ / 走破のズレ
        p = idx.get(int(e['u']))
        past = H[e['nm']][-5:]
        if len(past) >= 3:
            pD = st.median([x[0] for x in past])
            pT = st.median([x[1] for x in past])
            pp = [x[2] for x in past if x[2] is not None]
            PAIR.append((pD, D))
            pop = e.get('pop', '')
            ROWS.append(dict(pD=pD, pT=pT, D=D, T=T,
                             pos=st.median(pp) if pp else None,
                             hit=int(e['f']) <= 3,
                             pop=int(pop) if pop.isdigit() else None))
        H[e['nm']].append((D, T, p))

print(f'材料が3走以上ある {len(ROWS)}頭ぶんで測る\n')
print('■ (1) 減速ぐせは次走に残るか')
print(f'  過去の減速ぐせ と 今走の減速ぐせ の相関  '
      f'{cor([x[0] for x in PAIR], [x[1] for x in PAIR]):+.2f}')
print(f'  くらべて 過去の走破のズレ と 今走の走破のズレ  '
      f'{cor([x["pT"] for x in ROWS], [x["T"] for x in ROWS]):+.2f}')

print('\n■ (2) 着順に効くか（6番人気以下だけ）')
P = [x for x in ROWS if x['pop'] and x['pop'] >= 6]
print(f'  人気薄 {len(P)}頭、3着内 '
      f'{100*sum(x["hit"] for x in P)/len(P):.1f}%')
q = sorted(x['pD'] for x in P)


def band(v, lab):
    out = []
    for n, f in lab:
        s = [x for x in v if f(x['pD'])]
        if len(s) >= 40:
            out.append(f'{n} {100*sum(y["hit"] for y in s)/len(s):5.1f}% '
                       f'({sum(y["hit"] for y in s)}/{len(s)})')
    return out


LAB = [('落ちない側 1/4', lambda z: z <= q[len(q)//4]),
       ('まん中', lambda z: q[len(q)//4] < z <= q[3*len(q)//4]),
       ('落ちる側 1/4', lambda z: z > q[3*len(q)//4])]
for s in band(P, LAB):
    print('   ' + s)

print('\n■ (3) 走破のズレ（実力）をそろえても残るか')
for tl, tf in (('時計が速い側 半分', lambda x: x['pT'] <= st.median([y['pT'] for y in P])),
               ('おそい側 半分', lambda x: x['pT'] > st.median([y['pT'] for y in P]))):
    sub = [x for x in P if tf(x)]
    print(f'  {tl}（{len(sub)}頭）')
    for s in band(sub, LAB):
        print('     ' + s)

print('\n■ (4) 普段の4角位置をそろえても残るか')
pp = [x for x in P if x['pos'] is not None]
m = st.median([x['pos'] for x in pp])
for pl, pf in (('普段 前め', lambda x: x['pos'] <= m),
               ('普段 後ろめ', lambda x: x['pos'] > m)):
    sub = [x for x in pp if pf(x)]
    print(f'  {pl}（{len(sub)}頭）')
    for s in band(sub, LAB):
        print('     ' + s)
