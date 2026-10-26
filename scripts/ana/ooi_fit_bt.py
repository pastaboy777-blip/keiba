# -*- coding: utf-8 -*-
"""「普段の脚で足りるか」の当たりはずれを、今年の大井の全鞍で測る。

  python3 scripts/ana/ooi_fit_bt.py

各鞍について、その鞍より前の走だけで出走各馬の「水準からのズレ」を出し、
その鞍の条件（距離×馬場）の水準に置き直して見込み時計をつくる。
鞍の中で並べ、見込み上位が本当に3着内に来たかを数える。
水準そのものは年間ぜんぶから作っているので、ここだけは先の情報が入る。
向きを測るのが目的なので、それは許容する。
"""
import collections, json, re, statistics as st

SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
WET = ('重', '不良')


def sec(t):
    m = re.match(r'^(?:(\d+):)?(\d+)\.(\d)$', t.strip()) if t else None
    return None if not m else (int(m.group(1) or 0) * 60 + int(m.group(2))
                               + int(m.group(3)) / 10)


def fnum(x):
    try:
        return float(x)
    except Exception:
        return None


R2 = [json.loads(l) for l in open(SP + '/ooi_2026_runs.jsonl', encoding='utf-8')]
R2 = [r for r in R2 if r['dist']]
R2.sort(key=lambda r: (r['ymd'], r['rid']))

cell = collections.defaultdict(list)
for r in R2:
    for e in r['e']:
        t, a = sec(e['tm']), fnum(e['ag'])
        if t and a:
            cell[(r['dist'], r['baba'])].append((t - a, a))
MED = {k: (st.median([x[0] for x in v]), st.median([x[1] for x in v]))
       for k, v in cell.items() if len(v) >= 40}
grp = collections.defaultdict(list)
for (d, b), v in cell.items():
    grp[(d, 'wet' if b in WET else 'dry')] += v
    grp[(d, 'all')] += v
GM = {k: (st.median([x[0] for x in v]), st.median([x[1] for x in v]))
      for k, v in grp.items() if len(v) >= 25}
dw = [(GM[(d, 'wet')][0] - GM[(d, 'dry')][0], GM[(d, 'wet')][1] - GM[(d, 'dry')][1])
      for d in {x[0] for x in GM} if (d, 'wet') in GM and (d, 'dry') in GM]
DW = (st.median([x[0] for x in dw]), st.median([x[1] for x in dw]))


def med(d, b):
    w = 'wet' if b in WET else 'dry'
    if (d, b) in MED:
        return MED[(d, b)]
    if (d, w) in GM:
        return GM[(d, w)]
    if (d, 'all') in GM:
        x = GM[(d, 'all')]
        return (x[0] + (DW[0] if w == 'wet' else 0),
                x[1] + (DW[1] if w == 'wet' else 0))
    return None


hist = collections.defaultdict(list)          # 馬名 -> それまでの走
tab = collections.defaultdict(lambda: [0, 0])  # ラベル -> [3着内, 出走]
base = [0, 0]
rows = []
for r in R2:
    m = med(r['dist'], r['baba'])
    if not m:
        continue
    ent = []
    for e in r['e']:
        nm = e['nm']
        hs = [x for x in hist[nm] if med(x['dist'], x['baba'])][-5:]
        f = int(e['f']) if str(e['f']).isdigit() else None
        pop = int(e['pop']) if str(e['pop']).isdigit() else None
        g = None
        if len(hs) >= 2:
            dh, da = [], []
            for x in hs:
                mm = med(x['dist'], x['baba'])
                dh.append(x['h'] - mm[0])
                da.append(x['a'] - mm[1])
            last = hs[-1]
            g = dict(ph=m[0] + st.median(dh), pa=m[1] + st.median(da),
                     da=st.median(da), dh=st.median(dh),
                     drop=m[1] - med(last['dist'], last['baba'])[1],
                     cold=all(x['f'] and x['f'] >= 4 for x in hs[-2:]))
            g['pt'] = g['ph'] + g['pa']
        ent.append(dict(nm=nm, f=f, pop=pop, g=g))
    # 鞍の中で並べる
    hv = [x for x in ent if x['g']]
    for i, x in enumerate(sorted(hv, key=lambda z: z['g']['pt']), 1):
        x['rk'] = i
    for i, x in enumerate(sorted(hv, key=lambda z: z['g']['ph']), 1):
        x['hrk'] = i
    for x in ent:
        t, a = sec(next((e['tm'] for e in r['e'] if e['nm'] == x['nm']), '')), None
        if x['f']:
            base[1] += 1
            base[0] += x['f'] <= 3
        if not x['g'] or not x['f']:
            continue
        g, hit = x['g'], x['f'] <= 3
        for lab in [f"見込み{min(x['rk'],6)}位" if x['rk'] <= 5 else '見込み6位以下']:
            tab[lab][0] += hit
            tab[lab][1] += 1
        if x['rk'] <= 3:
            tab['見込み3位以内'][0] += hit
            tab['見込み3位以内'][1] += 1
            if g['cold']:
                tab['3位以内×直近2走4着以下'][0] += hit
                tab['3位以内×直近2走4着以下'][1] += 1
                if x['pop'] and x['pop'] >= 6:
                    tab['↑×6人気以下'][0] += hit
                    tab['↑×6人気以下'][1] += 1
                if g['drop'] >= 0.3:
                    tab['↑×上り水準が0.3秒以上下りる'][0] += hit
                    tab['↑×上り水準が0.3秒以上下りる'][1] += 1
                if g['da'] > 0:
                    tab['↑×ズブい(上り偏差+)'][0] += hit
                    tab['↑×ズブい(上り偏差+)'][1] += 1
                if x['hrk'] <= 3:
                    tab['↑×自前半も3位以内'][0] += hit
                    tab['↑×自前半も3位以内'][1] += 1
        if x['pop'] and x['pop'] >= 6:
            tab['[参考]6人気以下ぜんぶ'][0] += hit
            tab['[参考]6人気以下ぜんぶ'][1] += 1
            if x['rk'] <= 3:
                tab['[参考]6人気以下×見込み3位以内'][0] += hit
                tab['[参考]6人気以下×見込み3位以内'][1] += 1
        rows.append(dict(ymd=r['ymd'], dist=r['dist'], baba=r['baba'], nm=x['nm'],
                         f=x['f'], pop=x['pop'], rk=x['rk'], hrk=x['hrk'],
                         pt=round(g['pt'], 1), da=round(g['da'], 1),
                         drop=round(g['drop'], 1), cold=g['cold']))
    for e in r['e']:
        t, a = sec(e['tm']), fnum(e['ag'])
        if t and a:
            hist[e['nm']].append(dict(
                ymd=r['ymd'], dist=r['dist'], baba=r['baba'], t=t, h=t - a, a=a,
                f=int(e['f']) if str(e['f']).isdigit() else None,
                pop=int(e['pop']) if str(e['pop']).isdigit() else None))

bp = base[0] / base[1] * 100
print(f'全出走 {base[1]}頭 3着内 {base[0]} = {bp:.1f}%\n')
for k, (h, n) in sorted(tab.items(), key=lambda z: -z[1][1]):
    if n < 30:
        continue
    print(f'{k:<30} {h:>4}/{n:<5} {h/n*100:>5.1f}%  {h/n*100-bp:+5.1f}pt')
json.dump(rows, open(SP + '/ooi_fit_bt.json', 'w', encoding='utf-8'),
          ensure_ascii=False)
