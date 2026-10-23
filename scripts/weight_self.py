# -*- coding: utf-8 -*-
"""馬体重を「その馬の自分比」で測る。

・ベスト体重 … 過去に3着内だったときの体重の中央値（無ければ全走の中央値）
・今回の乖離 … 今回の体重 − ベスト体重
・前走からの増減（紙面の±）

他馬との比較（鞍内で軽い/重い）はしない。人気を揃えて上振れを出す。
"""
import json, glob, collections, statistics

BA = {'18': '浦和', '19': '船橋', '20': '大井', '21': '川崎'}
H = collections.defaultdict(list)
for p in sorted(glob.glob('notes/live/*/results.json')):
    d = p.split('/')[2]
    if len(d) != 10:
        continue
    for Rs, r in json.load(open(p, encoding='utf-8')).items():
        ba = BA.get(str(r.get('rid', ''))[8:10])
        if not ba:
            continue
        for e in r['e']:
            if not str(e.get('f', '')).isdigit() or not e.get('wt'):
                continue
            dw = e.get('dw')
            try:
                dwv = int(str(dw).replace('±', '').replace('+', ''))
            except Exception:
                dwv = None
            H[e['nm']].append(dict(d=d, ba=ba, R=int(Rs), dist=r['dist'],
                                   f=int(e['f']), pop=int(e['pop']), c4=e.get('c4'),
                                   wt=e['wt'], dw=dwv))
for L in H.values():
    L.sort(key=lambda z: (z['d'], z['R']))

rows = []
for nm, L in H.items():
    for i, x in enumerate(L):
        past = L[:i]
        if len(past) < 2:
            continue
        good = [p['wt'] for p in past if p['f'] <= 3]
        best = statistics.median(good) if good else statistics.median([p['wt'] for p in past])
        rows.append(dict(x, nm=nm, best=best, gap=x['wt'] - best,
                         nrun=len(past), hasgood=bool(good),
                         debut=L[0]['wt']))
exp = collections.defaultdict(lambda: [0, 0])
for x in rows:
    exp[x['pop']][0] += 1
    exp[x['pop']][1] += x['f'] <= 3


def rep(sel, lab, mn=25, popmin=0):
    g = [x for x in rows if x['pop'] >= popmin and sel(x) and exp[x['pop']][0] >= 8]
    if len(g) < mn:
        print('%-38s n=%d (少)' % (lab, len(g)))
        return
    h = sum(1 for x in g if x['f'] <= 3)
    w = sum(1 for x in g if x['f'] == 1)
    e = sum(exp[x['pop']][1] / exp[x['pop']][0] for x in g)
    print('%-38s n=%4d 3着内%3d(%5.1f%%) 1着%2d 期待%5.1f%% %+5.1fpt'
          % (lab, len(g), h, 100 * h / len(g), w, 100 * e / len(g),
             100 * (h / len(g) - e / len(g))))


print('%d頭（過去2走以上・体重あり）／ 馬 %d頭' % (len(rows), len({x['nm'] for x in rows})))
for popmin, tag in ((0, '全体'), (7, '7番人気以下')):
    print('\n=== %s ────────────' % tag)
    rep(lambda x: True, 'ぜんぶ（基準）', 40, popmin)
    print('--- ベスト体重（好走時の体重）との差')
    rep(lambda x: x['hasgood'] and abs(x['gap']) <= 2, 'ベスト体重 ±2kg以内', 25, popmin)
    rep(lambda x: x['hasgood'] and 3 <= x['gap'] <= 8, 'ベストより +3〜8kg', 25, popmin)
    rep(lambda x: x['hasgood'] and x['gap'] >= 9, 'ベストより +9kg以上（太め）', 25, popmin)
    rep(lambda x: x['hasgood'] and -8 <= x['gap'] <= -3, 'ベストより −3〜8kg', 25, popmin)
    rep(lambda x: x['hasgood'] and x['gap'] <= -9, 'ベストより −9kg以上（絞れた）', 25, popmin)
    print('--- 前走からの増減だけで見る（他馬とも自分比とも無関係）')
    rep(lambda x: x['dw'] is not None and x['dw'] >= 10, '前走から +10kg以上', 25, popmin)
    rep(lambda x: x['dw'] is not None and x['dw'] <= -10, '前走から −10kg以上', 25, popmin)
    rep(lambda x: x['dw'] is not None and abs(x['dw']) <= 2, '前走から ±2kg以内', 25, popmin)
print('\n=== 「デビュー時の体重に戻る」の検算 ───────')
g = [x for x in rows if x['hasgood']]
if g:
    print('  好走時の体重 − デビュー時の体重 の中央値 %+.1fkg（%d頭）'
          % (statistics.median([x['best'] - x['debut'] for x in g]), len(g)))
    for lo, hi, lab in ((-999, -5, 'デビューより5kg以上 軽い'), (-5, 5, 'デビュー±5kg'),
                        (5, 999, 'デビューより5kg以上 重い')):
        s = [x for x in g if lo <= x['best'] - x['debut'] < hi]
        if s:
            print('    %-22s %4d頭' % (lab, len(s)))
