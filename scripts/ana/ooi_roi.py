# -*- coding: utf-8 -*-
"""条件ごとの複勝の回収率を、今年の大井80日の払戻で出す。

  python3 scripts/ana/ooi_roi.py

3着内率が上がっても、オッズが低ければ儲からない。
買える形かどうかは、ここで決まる。
"""
import json, re, statistics as st
from collections import defaultdict

SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
WET = ('重', '不良')


def band(d):
    return 'S' if d <= 1300 else 'M' if d <= 1700 else 'L'


DIV = json.load(open(f'{SP}/div_year.json', encoding='utf-8'))
CN = {}
for l in open(f'{SP}/corners_2026.jsonl', encoding='utf-8'):
    v = json.loads(l)
    CN[v['rid']] = v
R2 = []
for l in open(f'{SP}/ooi_2026_runs.jsonl', encoding='utf-8'):
    r = json.loads(l)
    if r.get('dist') and r.get('e'):
        R2.append(r)
R2.sort(key=lambda r: (r.get('ymd') or '', r['rid']))

AG = defaultdict(list)
POS = defaultdict(list)
GAIN = defaultdict(list)
ROWS = []
for r in R2:
    d = r['dist']
    cn = CN.get(r['rid']) or {}
    c3, c4 = cn.get('c3') or [], cn.get('c4') or []
    i3 = {u: i + 1 for i, u in enumerate(c3)}
    i4 = {u: i + 1 for i, u in enumerate(c4)}
    day = DIV.get(r['ymd'], {})
    rno = str(int(r['rid'][-2:]))
    fuku = dict(day.get(rno, {}).get('複勝', []))
    tan = dict(day.get(rno, {}).get('単勝', []))
    for e in r['e']:
        if not e.get('f', '').isdigit():
            continue
        nm = e['nm']
        pa = [a for dd, a in AG[nm] if band(dd) == band(d)][-5:]
        pp = POS[nm][-5:]
        pg = GAIN[nm][-5:]
        pop = e.get('pop', '')
        ROWS.append(dict(
            hit=int(e['f']) <= 3, win=e['f'] == '1',
            fuku=fuku.get(str(int(e['u'])), 0),
            tan=tan.get(str(int(e['u'])), 0),
            pop=int(pop) if pop.isdigit() else None,
            sd=st.pstdev(pa) if len(pa) >= 4 else None,
            pos=st.median(pp) if len(pp) >= 3 else None,
            gain=st.median(pg) if len(pg) >= 3 else None,
            wet=r.get('baba') in WET, dist=d, has=bool(fuku)))
    for e in r['e']:
        nm = e['nm']
        if re.match(r'^\d+\.\d$', e.get('ag') or ''):
            AG[nm].append((d, float(e['ag'])))
        p4, p3 = i4.get(int(e['u'])), i3.get(int(e['u']))
        if p4 and len(c4):
            POS[nm].append(p4)
        if p4 and p3:
            GAIN[nm].append(p3 - p4)

ROWS = [x for x in ROWS if x['has']]
P = [x for x in ROWS if x['pop'] and x['pop'] >= 6]
print(f'払戻がそろった {len(ROWS)}頭 / 人気薄 {len(P)}頭')
hb = 100 * sum(x['hit'] for x in P) / len(P)
rb = sum(x['fuku'] for x in P) / len(P)
print(f'人気薄ぜんぶ  3着内 {hb:.1f}%  複勝の回収率 {rb:.0f}%\n')


def show(lab, f, base=P):
    v = [x for x in base if f(x)]
    if len(v) < 40:
        print(f'  {lab:<30} 材料不足（{len(v)}頭）')
        return
    i = sum(x['hit'] for x in v)
    roi = sum(x['fuku'] for x in v) / len(v)
    avg = (st.mean([x['fuku'] for x in v if x['hit']]) if i else 0)
    print(f'  {lab:<30} {100*i/len(v):5.1f}%  回収 {roi:5.0f}%  '
          f'({i}/{len(v)})  当たりの平均配当 {avg:.0f}円')


A = lambda x: x['sd'] is not None and x['sd'] < 0.6
B = lambda x: x['pos'] is not None and x['pos'] <= 7
C = lambda x: x['gain'] is not None and x['gain'] > -0.5

print('■ 条件を積む（人気薄）        3着内   回収率')
show('なにもしない', lambda x: True)
show('① 上がりがそろっている', A)
show('①＋② ふだん7番手以内', lambda x: A(x) and B(x))
show('①＋②＋③ 下げない', lambda x: A(x) and B(x) and C(x))
show('↑ × 6〜7番人気', lambda x: A(x) and B(x) and C(x) and x['pop'] <= 7)
show('↑ × 8番人気以下', lambda x: A(x) and B(x) and C(x) and x['pop'] >= 8)
show('↑ × 渋った馬場', lambda x: A(x) and B(x) and C(x) and x['wet'])

print('\n■ 人気だけで切るとどうなるか（人気薄）')
for lo, hi, lab in ((6, 7, '6〜7番人気'), (8, 10, '8〜10番人気'),
                    (11, 99, '11番人気以下')):
    show(lab, lambda x, a=lo, b=hi: a <= x['pop'] <= b)

print('\n■ 人気側（参考）')
Q = [x for x in ROWS if x['pop'] and x['pop'] <= 5]
show('1〜5番人気ぜんぶ', lambda x: True, Q)
for k in (1, 2, 3, 4, 5):
    show(f'{k}番人気', lambda x, a=k: x['pop'] == a, Q)
