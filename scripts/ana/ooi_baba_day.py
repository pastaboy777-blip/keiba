# -*- coding: utf-8 -*-
"""その日の馬場が「時計の出る日」だったかを、1日ごとの残りで測る。

  python3 scripts/ana/ooi_baba_day.py

各鞍について、その鞍より前の走だけでレベルを推し、3着時計の見当を作る。
実際の3着時計との差（残り）を日ごとにまとめる。レベルの推定が
メンバーの過去から来ているので、残りはクラスを抜いたぶん＝
その日その場の速さに近い。
"""
import collections, json, re, statistics as st

SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
WET = ('重', '不良')


def sec(t):
    m = re.match(r'^(?:(\d+):)?(\d+)\.(\d)$', t.strip()) if t else None
    return None if not m else (int(m.group(1) or 0)) * 60 + int(m.group(2)) \
        + int(m.group(3)) / 10


R2 = [json.loads(l) for l in open(SP + '/ooi_2026_runs.jsonl', encoding='utf-8')]
R2 = [r for r in R2 if r.get('dist') and r.get('e')]
R2.sort(key=lambda r: (r['ymd'], r['rid']))

cell = collections.defaultdict(list)
for r in R2:
    for e in r['e']:
        t = sec(e['tm'])
        if t:
            cell[(r['dist'], r['baba'])].append(t)
M = {k: st.median(v) for k, v in cell.items() if len(v) >= 40}
G = collections.defaultdict(list)
for (d, b), v in cell.items():
    G[(d, 'wet' if b in WET else 'dry')] += v
GM = {k: st.median(v) for k, v in G.items() if len(v) >= 25}


def med(d, b):
    return M.get((d, b)) or GM.get((d, 'wet' if b in WET else 'dry'))


gap = []
for r in R2:
    m = med(r['dist'], r['baba'])
    ts = sorted(sec(e['tm']) for e in r['e'] if sec(e['tm']))
    if m and len(ts) >= 7:
        gap.append((st.median(ts) - m, st.median(ts) - ts[2]))
g3 = st.linear_regression([x[0] for x in gap], [x[1] for x in gap])

H = collections.defaultdict(list)
day = collections.defaultdict(list)
for r in R2:
    m = med(r['dist'], r['baba'])
    ts = sorted(sec(e['tm']) for e in r['e'] if sec(e['tm']))
    pw = [st.median(H[e['nm']][-5:]) for e in r['e'] if len(H[e['nm']]) >= 2]
    if m and len(ts) >= 3 and len(pw) >= max(4, len(r['e']) * 0.5):
        L = 0.88 * st.median(pw) - 0.20
        t3 = m + L - (g3.slope * L + g3.intercept)
        day[r['ymd']].append(ts[2] - t3)
    for e in r['e']:
        t = sec(e['tm'])
        if t and m:
            H[e['nm']].append(t - m)

ds = [(d, st.median(v), len(v)) for d, v in sorted(day.items()) if len(v) >= 5]
allr = [x for d, v in day.items() for x in v]
print(f'{len(ds)}日 / {len(allr)}鞍')
print(f'1鞍ぶんの残り  中央値 {st.median(allr):+.2f}秒 / '
      f'絶対値の中央値 {st.median([abs(x) for x in allr]):.2f}秒')
v = sorted(x[1] for x in ds)
print(f'日ごとの残り  中央値 {st.median(v):+.2f} / '
      f'上から1/4 {v[int(len(v)*.75)]:+.2f} / 下から1/4 {v[int(len(v)*.25)]:+.2f}')
print(f'  いちばん遅い日 {v[-1]:+.2f} / いちばん速い日 {v[0]:+.2f}')
print('\n■ 直近の日（＋は見当より遅い＝時計の出ない日）')
for d, mdn, n in ds[-16:]:
    bar = '█' * min(22, int(abs(mdn) * 14))
    side = ' ' * 22 if mdn >= 0 else ' ' * (22 - len(bar)) + bar
    print(f'  {d}  {mdn:+5.2f}  {n:>2}鞍  {side}│{bar if mdn>=0 else ""}')
TARGET = '20261028'
if TARGET in day:
    t = st.median(day[TARGET])
    rk = sum(1 for x in v if x < t)
    print(f'\n  {TARGET} は {t:+.2f}秒 ── {len(v)}日のうち遅いほうから '
          f'{len(v)-rk}番目（上位 {100*(len(v)-rk)/len(v):.0f}%）')
