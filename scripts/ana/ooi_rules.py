# -*- coding: utf-8 -*-
"""出馬表と過去走だけで使える条件を、今年の大井でぜんぶ測り直す。

  python3 scripts/ana/ooi_rules.py

道具がなくても新聞で確かめられるものだけを並べる。
人気薄（6番人気以下）と、全馬の両方で出す。
"""
import json, re, statistics as st
from collections import defaultdict

SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
WET = ('重', '不良')


def band(d):
    return 'S' if d <= 1300 else 'M' if d <= 1700 else 'L'


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

AG = defaultdict(list)     # 上がり（距離帯ごと）
POS = defaultdict(list)    # 4角の順位（頭数で割ったもの）
GAIN = defaultdict(list)   # 3角→4角で上げた数
PREV = {}
ROWS = []
for r in R2:
    d, n = r['dist'], len(r['e'])
    cn = CN.get(r['rid']) or {}
    c3, c4 = cn.get('c3') or [], cn.get('c4') or []
    i3 = {u: i + 1 for i, u in enumerate(c3)}
    i4 = {u: i + 1 for i, u in enumerate(c4)}
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
            pop=int(pop) if pop.isdigit() else None,
            sd=st.pstdev(pa) if len(pa) >= 4 else None,
            pos=st.median(pp) if len(pp) >= 3 else None,
            gain=st.median(pg) if len(pg) >= 3 else None,
            wt=int(e['wt']) if (e.get('wt') or '').isdigit() else None,
            wet=r.get('baba') in WET,
            pd=PREV.get(nm), dist=d))
    for e in r['e']:
        nm = e['nm']
        if re.match(r'^\d+\.\d$', e.get('ag') or ''):
            AG[nm].append((d, float(e['ag'])))
        p4, p3 = i4.get(int(e['u'])), i3.get(int(e['u']))
        if p4 and len(c4):
            POS[nm].append(p4)
        if p4 and p3:
            GAIN[nm].append(p3 - p4)
        if e.get('tm'):
            PREV[nm] = d

P = [x for x in ROWS if x['pop'] and x['pop'] >= 6]
ALL = ROWS
print(f'全馬 {len(ALL)}頭 / 人気薄（6番人気以下）{len(P)}頭')
print(f'3着内率  全馬 {100*sum(x["hit"] for x in ALL)/len(ALL):.1f}%  '
      f'人気薄 {100*sum(x["hit"] for x in P)/len(P):.1f}%\n')


def show(lab, f, base=P, bl='人気薄'):
    v = [x for x in base if f(x)]
    if len(v) < 40:
        print(f'  {lab:<34} 材料不足（{len(v)}頭）')
        return
    i = sum(x['hit'] for x in v)
    w = sum(x['win'] for x in v)
    b = 100 * sum(x['hit'] for x in base) / len(base)
    print(f'  {lab:<34} {100*i/len(v):5.1f}%  ({i}/{len(v)})  '
          f'{100*i/len(v)-b:+5.1f}pt   勝ち {100*w/len(v):4.1f}%')


print('■ 1. 上がりが毎回そろっている（同じ距離帯の直近5走）')
show('ばらつき 0.6未満', lambda x: x['sd'] is not None and x['sd'] < 0.6)
show('ばらつき 0.6以上', lambda x: x['sd'] is not None and x['sd'] >= 0.6)
show('↑0.6未満 × 渋った馬場',
     lambda x: x['sd'] is not None and x['sd'] < 0.6 and x['wet'])

print('\n■ 2. 普段どこを走っているか（直近5走の4角の順位）')
show('ふだん4角 3番手以内', lambda x: x['pos'] is not None and x['pos'] <= 3)
show('ふだん4角 4〜7番手', lambda x: x['pos'] is not None and 3 < x['pos'] <= 7)
show('ふだん4角 8番手以降', lambda x: x['pos'] is not None and x['pos'] > 7)

print('\n■ 3. 3角→4角で順位を上げるか下げるか')
show('ふだん 上げる（+0.5以上）', lambda x: x['gain'] is not None and x['gain'] >= 0.5)
show('ふだん 変わらない', lambda x: x['gain'] is not None and -0.5 < x['gain'] < 0.5)
show('ふだん 下げる（−0.5以下）', lambda x: x['gain'] is not None and x['gain'] <= -0.5)

print('\n■ 4. 当日の人気')
for lo, hi, lab in ((6, 7, '6〜7番人気'), (8, 10, '8〜10番人気'),
                    (11, 99, '11番人気以下')):
    show(lab, lambda x, a=lo, b=hi: a <= x['pop'] <= b)

print('\n■ 5. 馬体重')
for lo, hi, lab in ((0, 439, '439kg以下'), (440, 469, '440〜469kg'),
                    (470, 499, '470〜499kg'), (500, 999, '500kg以上')):
    show(lab, lambda x, a=lo, b=hi: x['wt'] and a <= x['wt'] <= b)
print('  （渋った馬場だけ）')
for lo, hi, lab in ((440, 469, '440〜469kg'), (500, 999, '500kg以上')):
    show(lab, lambda x, a=lo, b=hi: x['wt'] and a <= x['wt'] <= b and x['wet'])

print('\n■ 6. 前走からの距離')
show('短縮', lambda x: x['pd'] and x['dist'] < x['pd'] - 50)
show('同じ', lambda x: x['pd'] and abs(x['dist'] - x['pd']) <= 50)
show('延長', lambda x: x['pd'] and x['dist'] > x['pd'] + 50)

print('\n■ 7. 重ねるとどうなるか（人気薄）')
A = lambda x: x['sd'] is not None and x['sd'] < 0.6
B = lambda x: x['pos'] is not None and x['pos'] <= 7
C = lambda x: x['gain'] is not None and x['gain'] > -0.5
show('① 上がりがそろっている', A)
show('①＋② ふだん7番手以内', lambda x: A(x) and B(x))
show('①＋②＋③ 下げない', lambda x: A(x) and B(x) and C(x))
show('①＋②＋③ × 6〜7番人気',
     lambda x: A(x) and B(x) and C(x) and 6 <= x['pop'] <= 7)
print()
show('ひとつも当てはまらない',
     lambda x: (x['sd'] is not None and x['pos'] is not None
                and x['gain'] is not None and not A(x) and not B(x)))
