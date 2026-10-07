# -*- coding: utf-8 -*-
"""当日の結果から馬場の傾向を出す。
  python3 ana.py ro1007.json "10/7 大井"
"""
import json, sys, collections, statistics

F, TITLE = sys.argv[1], sys.argv[2]
res = json.load(open(F, encoding='utf-8'))

ALL = []
for Rs in sorted(res, key=lambda x: int(x)):
    r = res[Rs]
    ags = sorted([e['ag'] for e in r['e'] if e.get('ag')])
    wts = sorted([e['wt'] for e in r['e'] if e.get('wt')])
    for e in r['e']:
        f = str(e.get('f', ''))
        if not f.isdigit():
            continue
        wq = wts.index(e['wt']) / float(len(wts)) if e.get('wt') in wts else None
        ALL.append(dict(R=int(Rs), dist=r['dist'], course=r['course'], baba=r['baba'],
                        cls=r['cls'], n=r['n'], lap=r['lap'], fin=int(f), u=e['u'],
                        nm=e['nm'], pop=e['pop'], c4=e.get('c4'), ag=e.get('ag'),
                        wt=e.get('wt'), dw=e.get('dw'), age=e.get('age'), sx=e.get('sx'),
                        agr=(ags.index(e['ag']) + 1) if e.get('ag') in ags else None, wq=wq))
fin = ALL
print('■ %s ── %d鞍 / 出走 %d頭' % (TITLE, len(res), len(fin)))


def rate(rows, lab, w=26):
    n = len(rows)
    if not n:
        print('   %-*s   0頭' % (w, lab))
        return
    t3 = sum(1 for x in rows if x['fin'] <= 3)
    win = sum(1 for x in rows if x['fin'] == 1)
    print('   %-*s %3d頭  3着内 %2d (%5.1f%%)  1着 %d' % (w, lab, n, t3, 100.0 * t3 / n, win))


print('\n■ ラップと結果')
for Rs in sorted(res, key=lambda x: int(x)):
    r = res[Rs]
    lap = [float(v) for v in r['lap'].split('-') if v]
    body = lap[1:] if lap and lap[0] < 10 else lap
    h = len(body) // 2
    fh, sh = (sum(body[:h]), sum(body[h:])) if h else (0, 0)
    w1 = [x for x in fin if x['R'] == int(Rs) and x['fin'] == 1][0]
    print('   %2sR ダ%4d%s %2d頭 %-12s 前半%5.1f 後半%5.1f (%+5.1f)  勝ち馬 4角%-3s 上%.1f %2d人気'
          % (Rs, r['dist'], r['course'], r['n'], r['cls'][:12], fh, sh, sh - fh,
             w1['c4'], w1['ag'], w1['pop']))

print('\n■ 4角の位置')
for lo, hi, lab in ((1, 1, '1番手'), (2, 2, '2番手'), (3, 4, '3〜4番手'),
                    (5, 6, '5〜6番手'), (7, 8, '7〜8番手'), (9, 99, '9番手〜')):
    rate([x for x in fin if x['c4'] and lo <= x['c4'] <= hi], '4角 ' + lab)

print('\n■ 上り順位（鞍内）')
for lo, hi, lab in ((1, 1, '1位'), (2, 3, '2〜3位'), (4, 5, '4〜5位'),
                    (6, 8, '6〜8位'), (9, 99, '9位以下')):
    rate([x for x in fin if x['agr'] and lo <= x['agr'] <= hi], '上り ' + lab)

print('\n■ 上り × 4角')
for al, ah, alab in ((1, 3, '上り3位以内'), (4, 99, '上り4位以下')):
    for cl, ch, clab in ((1, 2, '4角1〜2'), (3, 4, '4角3〜4'), (5, 99, '4角5〜')):
        rate([x for x in fin if x['agr'] and x['c4'] and al <= x['agr'] <= ah
              and cl <= x['c4'] <= ch], '%s × %s' % (alab, clab), 30)

print('\n■ 距離別の4角')
for dl, dh, dlab in ((1000, 1200, '1200m'), (1400, 1400, '1400m'), (1600, 2200, '1600m以上')):
    rows = [x for x in fin if dl <= x['dist'] <= dh]
    if not rows:
        continue
    print('   %s（%d鞍）' % (dlab, len({x['R'] for x in rows})))
    for lo, hi, lab in ((1, 2, '  4角1〜2番手'), (3, 4, '  4角3〜4番手'), (5, 99, '  4角5番手〜')):
        rate([x for x in rows if x['c4'] and lo <= x['c4'] <= hi], lab)

print('\n■ 内回り / 外回り')
for co in ('内', '外'):
    rows = [x for x in fin if x['course'] == co]
    if not rows:
        continue
    print('   %s回り（%d鞍 %d頭）' % (co, len({x['R'] for x in rows}), len(rows)))
    for lo, hi, lab in ((1, 2, '  4角1〜2番手'), (3, 4, '  4角3〜4番手'), (5, 99, '  4角5番手〜')):
        rate([x for x in rows if x['c4'] and lo <= x['c4'] <= hi], lab)

print('\n■ 馬体重（鞍内の軽い順）')
for lo, hi, lab in ((0, .34, '軽い1/3'), (.34, .67, '中'), (.67, 1.01, '重い1/3')):
    rate([x for x in fin if x['wq'] is not None and lo <= x['wq'] < hi], lab)

print('\n■ 馬体重の増減')
for lo, hi, lab in ((-999, -5, '−5kg以上減'), (-4, -1, '−1〜−4kg'),
                    (0, 0, '増減なし'), (1, 4, '+1〜+4kg'), (5, 999, '+5kg以上増')):
    rows = [x for x in fin if str(x['dw']).lstrip('+-').isdigit()
            and lo <= int(x['dw']) <= hi]
    rate(rows, lab)

print('\n■ 人気')
for lo, hi, lab in ((1, 1, '1番人気'), (2, 3, '2〜3番人気'), (4, 6, '4〜6番人気'),
                    (7, 99, '7番人気以下')):
    rate([x for x in fin if x['pop'] and lo <= x['pop'] <= hi], lab)

print('\n■ 1〜3着')
for Rs in sorted(res, key=lambda x: int(x)):
    r = res[Rs]
    print('  %2sR ダ%d%s %s' % (Rs, r['dist'], r['course'], r['cls'][:16]))
    for x in [y for y in fin if y['R'] == int(Rs) and y['fin'] <= 3]:
        print('    %d着 %2d %-15s %2d人気 上%.1f(%2d位) 4角%-3s %sk(%s) %d歳'
              % (x['fin'], x['u'], x['nm'][:15], x['pop'], x['ag'], x['agr'],
                 x['c4'], x['wt'], x['dw'], x['age']))
