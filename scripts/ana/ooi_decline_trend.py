# -*- coding: utf-8 -*-
"""「後半の落ち込みが減ってきている馬は調子が上がっている」を測る。

  python3 scripts/ana/ooi_decline_trend.py

1走ごとの落ち込みを、距離に左右されない形で出す。
  前半1Fあたり ＝ （走破時計 − 自身の上り3F）÷（距離/200 − 3）
  上がり1Fあたり ＝ 上り3F ÷ 3
  落ち込み ＝ 上がり1Fあたり − 前半1Fあたり
これを直近5走ならべ、「直近2走の平均 − その前3走の平均」で向きを見る。
マイナスなら落ち込みが小さくなってきている＝上向き。
"""
import json, re, statistics as st
from collections import defaultdict

SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')


def sec(t):
    m = re.match(r'^(?:(\d+):)?(\d+)\.(\d)$', t.strip()) if t else None
    return None if not m else (int(m.group(1) or 0)) * 60 + int(m.group(2)) \
        + int(m.group(3)) / 10


def decline(t, a, dist):
    """1走ぶんの落ち込み（1ハロンあたり）"""
    nf = dist / 200 - 3
    if nf <= 0 or t is None or a is None or t <= a:
        return None
    return a / 3 - (t - a) / nf


DIV = json.load(open(f'{SP}/div_year.json', encoding='utf-8'))
R2 = []
for l in open(f'{SP}/ooi_2026_runs.jsonl', encoding='utf-8'):
    r = json.loads(l)
    if r.get('dist') and r.get('e'):
        R2.append(r)
R2.sort(key=lambda r: (r.get('ymd') or '', r['rid']))

H = defaultdict(list)
ROWS = []
for r in R2:
    d = r['dist']
    fuku = dict((DIV.get(r['ymd'], {}).get(str(int(r['rid'][-2:])), {})
                 ).get('複勝', []))
    for e in r['e']:
        if not e.get('f', '').isdigit():
            continue
        past = H[e['nm']][-5:]
        pop = e.get('pop', '')
        if len(past) == 5:
            tr = st.mean(past[3:]) - st.mean(past[:3])
            ROWS.append(dict(hit=int(e['f']) <= 3, tr=tr,
                             lv=st.mean(past[3:]),
                             fuku=fuku.get(str(int(e['u'])), 0),
                             pop=int(pop) if pop.isdigit() else None))
    for e in r['e']:
        v = decline(sec(e.get('tm')), sec(e.get('ag') or ''), d)
        if v is not None:
            H[e['nm']].append(v)

P = [x for x in ROWS if x['pop'] and x['pop'] >= 6]
print(f'直近5走そろう {len(ROWS)}頭 / 人気薄 {len(P)}頭')
print(f'人気薄ぜんぶ  3着内 {100*sum(x["hit"] for x in P)/len(P):.1f}%  '
      f'回収 {sum(x["fuku"] for x in P)/len(P):.0f}%\n')
q = sorted(x['tr'] for x in P)


def show(lab, f, base=P, mn=60):
    v = [x for x in base if f(x)]
    if len(v) < mn:
        print(f'  {lab:<28} 材料不足（{len(v)}頭）')
        return
    i = sum(x['hit'] for x in v)
    print(f'  {lab:<28} {100*i/len(v):5.1f}%  回収 {sum(x["fuku"] for x in v)/len(v):5.0f}%'
          f'  ({i}/{len(v)})')


print('■ 落ち込みの向き（直近2走の平均 − その前3走の平均）')
BINS = [('よくなっている 上位1/4', lambda z: z <= q[len(q)//4]),
        ('やや よくなっている', lambda z: q[len(q)//4] < z <= q[len(q)//2]),
        ('やや わるくなっている', lambda z: q[len(q)//2] < z <= q[3*len(q)//4]),
        ('わるくなっている 下位1/4', lambda z: z > q[3*len(q)//4])]
for lab, f in BINS:
    show(lab, lambda x, g=f: g(x['tr']))

print('\n■ 水準もそろえる（直近2走の落ち込みの大きさで半分に割る）')
m = st.median([x['lv'] for x in P])
for ll, lf in (('もともと落ちない側', lambda x: x['lv'] <= m),
               ('もともと落ちる側', lambda x: x['lv'] > m)):
    print(f'  {ll}')
    for lab, f in (BINS[0], BINS[3]):
        show('   ' + lab, lambda x, g=f, h=lf: h(x) and g(x['tr']), mn=40)

print('\n■ 参考：全馬で見ると')
q2 = sorted(x['tr'] for x in ROWS)
for lab, f in [('よくなっている 上位1/4', lambda z: z <= q2[len(q2)//4]),
               ('わるくなっている 下位1/4', lambda z: z > q2[3*len(q2)//4])]:
    show(lab, lambda x, g=f: g(x['tr']), ROWS)
