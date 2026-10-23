# -*- coding: utf-8 -*-
"""血統（父・母父）が南関で効くかを、人気を揃えて測る。

  python3 scripts/ped_edge.py <ped.jsonl> [--sire|--bms|--line <名前,名前>]

吉馬の結果ページから取った血統を、こちらの結果データに繋いで集計する。
「柔軟性」の検証用に、距離が前走から変わった馬だけを見る切り口も持つ。
"""
import json, glob, sys, collections, statistics

BA = {'18': '浦和', '19': '船橋', '20': '大井', '21': '川崎'}
PED = sys.argv[1]
MODE = sys.argv[2] if len(sys.argv) > 2 else '--sire'
LINE = (sys.argv[3].split(',') if len(sys.argv) > 3 else [])

ped = {}
for l in open(PED, encoding='utf-8'):
    x = json.loads(l)
    ped[x['nm']] = x

runs = []
for p in sorted(glob.glob('notes/live/*/results.json')):
    d = p.split('/')[2]
    if len(d) != 10:
        continue
    for Rs, r in json.load(open(p, encoding='utf-8')).items():
        ba = BA.get(str(r.get('rid', ''))[8:10])
        if not ba:
            continue
        for e in r['e']:
            if not str(e.get('f', '')).isdigit():
                continue
            runs.append(dict(d=d, ba=ba, R=int(Rs), dist=r['dist'], nm=e['nm'],
                             f=int(e['f']), pop=int(e['pop']), c4=e.get('c4')))
H = collections.defaultdict(list)
for x in runs:
    H[x['nm']].append(x)
for L in H.values():
    L.sort(key=lambda z: (z['d'], z['R']))
for L in H.values():
    for i, x in enumerate(L):
        x['prevdist'] = L[i - 1]['dist'] if i else None

rows = []
for x in runs:
    p = ped.get(x['nm'])
    if not p:
        continue
    rows.append(dict(x, sire=p['sire'], bms=p['bms'], dam=p['dam']))

exp = collections.defaultdict(lambda: [0, 0])
for x in rows:
    exp[x['pop']][0] += 1
    exp[x['pop']][1] += x['f'] <= 3


def stat(g):
    if not g:
        return None
    h = sum(1 for x in g if x['f'] <= 3)
    e = sum(exp[x['pop']][1] / exp[x['pop']][0] for x in g)
    return len(g), 100 * h / len(g), 100 * e / len(g), 100 * (h / len(g) - e / len(g)), \
        sum(1 for x in g if x['f'] == 1)


print('血統の繋がった %d頭 / 馬 %d頭' % (len(rows), len({x['nm'] for x in rows})))
key = 'bms' if MODE == '--bms' else 'sire'

if MODE == '--line':
    hit = [x for x in rows if any(n in (x['sire'], x['bms']) for n in LINE)]
    print('\n指定した血統 %s' % '／'.join(LINE))
    s = stat(hit)
    if s:
        print('  全体     %4d頭 3着内%5.1f%% 期待%5.1f%% %+5.1fpt 1着%d' % s)
    for lab, sel in (('7番人気以下', lambda x: x['pop'] >= 7),
                     ('距離が前走と違う', lambda x: x['prevdist'] and x['prevdist'] != x['dist']),
                     ('距離が前走と同じ', lambda x: x['prevdist'] and x['prevdist'] == x['dist'])):
        s = stat([x for x in hit if sel(x)])
        if s and s[0] >= 10:
            print('  %-10s %4d頭 3着内%5.1f%% 期待%5.1f%% %+5.1fpt 1着%d' % ((lab,) + s))
    sys.exit()

c = collections.Counter(x[key] for x in rows)
print('\n%s 別（20頭以上）' % ('母父' if key == 'bms' else '父'))
out = []
for name, n in c.items():
    if n < 20:
        continue
    s = stat([x for x in rows if x[key] == name])
    out.append((s[3], name) + s)
for d, name, n, hit, e, diff, w in sorted(out, reverse=True)[:12]:
    print('  %-18s %4d頭 3着内%5.1f%% 期待%5.1f%% %+5.1fpt 1着%d' % (name[:18], n, hit, e, diff, w))
print('  ...')
for d, name, n, hit, e, diff, w in sorted(out)[:6]:
    print('  %-18s %4d頭 3着内%5.1f%% 期待%5.1f%% %+5.1fpt 1着%d' % (name[:18], n, hit, e, diff, w))
