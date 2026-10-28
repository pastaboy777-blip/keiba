# -*- coding: utf-8 -*-
"""今開催に出た馬の「粘り」の推移を書き出す。

  python3 scripts/ana/ooi_nebari_data.py <out.json>

粘り ＝ −（上がりの鞍内差 − 自前半の鞍内差）
その鞍の中央を0に置いて、上にあるほど後半の落ち込みが小さい。
鞍の中央を引いてあるので、その日のペースやクラスは抜けている。

向き ＝ 直近2走の平均 − その前3走の平均。プラスなら上向き。
"""
import json, re, statistics as st, sys
from collections import defaultdict

OUT = sys.argv[1]
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
MEET = ('20261026', '20261027', '20261028')


def sec(t):
    m = re.match(r'^(?:(\d+):)?(\d+)\.(\d)$', t.strip()) if t else None
    return None if not m else (int(m.group(1) or 0)) * 60 + int(m.group(2)) \
        + int(m.group(3)) / 10


R2 = []
for l in open(f'{SP}/ooi_2026_runs.jsonl', encoding='utf-8'):
    r = json.loads(l)
    if r.get('dist') and r.get('e'):
        R2.append(r)
R2.sort(key=lambda r: (r.get('ymd') or '', r['rid']))

H = defaultdict(list)
LAST = {}
for r in R2:
    hs = []
    for e in r['e']:
        t, a = sec(e.get('tm')), sec(e.get('ag') or '')
        if t and a:
            hs.append((e, t - a, a))
    if len(hs) < 7:
        continue
    mh = st.median([x[1] for x in hs])
    ma = st.median([x[2] for x in hs])
    for e, h, a in hs:
        H[e['nm']].append(dict(
            d=r['ymd'], dist=r['dist'], baba=r.get('baba'),
            R=int(r['rid'][-2:]), f=e.get('f'), pop=e.get('pop'),
            wt=e.get('wt'), nebari=round(-((a - ma) - (h - mh)), 2)))
    if r['ymd'] in MEET:
        for e in r['e']:
            LAST[e['nm']] = dict(d=r['ymd'], R=int(r['rid'][-2:]),
                                 u=e['u'], f=e.get('f'), pop=e.get('pop'),
                                 dist=r['dist'], wt=e.get('wt'),
                                 jk=e.get('jk'), tr=e.get('tr'))

out = []
for nm, meta in LAST.items():
    v = H.get(nm) or []
    v = [x for x in v if x['d'] <= meta['d']][-5:]
    if len(v) < 5:
        continue
    ser = [x['nebari'] for x in v]
    out.append(dict(nm=nm, runs=v, ser=ser,
                    trend=round(st.mean(ser[3:]) - st.mean(ser[:3]), 2),
                    level=round(st.mean(ser[3:]), 2), **meta))
out.sort(key=lambda z: -z['trend'])
json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print(f'{len(out)}頭 書き出し {OUT}')
print('\n■ 上向き 12頭')
for z in out[:12]:
    print(f"  {z['nm']:<14} 向き {z['trend']:+5.2f}  "
          f"粘り {' '.join(f'{x:+5.2f}' for x in z['ser'])}  "
          f"（{z['d'][4:6]}/{z['d'][6:]} {z['R']}R {z['f']}着 {z['pop']}人）")
print('\n■ 下向き 6頭')
for z in out[-6:]:
    print(f"  {z['nm']:<14} 向き {z['trend']:+5.2f}  "
          f"粘り {' '.join(f'{x:+5.2f}' for x in z['ser'])}  "
          f"（{z['d'][4:6]}/{z['d'][6:]} {z['R']}R {z['f']}着 {z['pop']}人）")
