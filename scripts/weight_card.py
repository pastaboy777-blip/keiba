# -*- coding: utf-8 -*-
"""馬体重の自分比を、当日のカードに落とす。

  python3 scripts/weight_card.py <past5.json> <出力txt>

事前に分かるのは「前走の体重」と「その馬のベスト体重（近走で好走した時の体重）」。
当日の体重が出た時点で、下の2つを当てはめて絞る。

  切る … 前走から +10kg以上（7番人気以下の33頭で3着内ゼロ）
  拾う … 前走から ±2kg以内（7番人気以下で 10.9% 対 期待6.5%、+4.2pt）
"""
import json, sys, statistics

SRC, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(SRC, encoding='utf-8'))
O = []
P = O.append
P('# 10/23(金) 浦和 ── 馬体重の自分比')
P('')
P('ベスト体重 = 近5走のうち3着内だったときの体重の中央値（好走が無ければ全走の中央値）')
P('前走差 = 前走の体重 − ベスト体重。プラスが大きいほど前走は太めだった')
P('')
P('当日の使い方')
P('  切る … 発表体重が前走から +10kg以上（7番人気以下の33頭で3着内ゼロ）')
P('  拾う … 発表体重が前走から ±2kg以内 かつ 7番人気以下（10.9%／期待6.5%）')
P('')
for Rs in sorted(d, key=int):
    r = d[Rs]
    P('── %sR ダ%d %d頭 ──' % (Rs, r['dist'], r['n']))
    rows = []
    for e in r['e']:
        rs = [x for x in e['runs'] if x.get('wt')]
        if not rs:
            rows.append((e['u'], e['nm'], None, None, None, 0))
            continue
        good = [x['wt'] for x in rs if x['fin'] <= 3]
        best = statistics.median(good) if good else statistics.median([x['wt'] for x in rs])
        prev = rs[0]['wt']
        rows.append((e['u'], e['nm'], prev, best, prev - best, len(good)))
    for u, nm, prev, best, gap, ng in sorted(rows, key=lambda z: z[0]):
        if prev is None:
            P('   %2d %-15s 近走の体重なし' % (u, nm[:15]))
            continue
        mark = ''
        if gap >= 9:
            mark = '前走は太め（ベスト+%dk）… 絞れていれば買い' % gap
        elif abs(gap) <= 2:
            mark = 'ベスト体重で使えている'
        elif gap <= -9:
            mark = '前走は絞れすぎ（ベスト%dk）' % gap
        P('   %2d %-15s 前走%3dk ベスト%3.0fk 差%+4.0f %s%s'
          % (u, nm[:15], prev, best, gap, '好走%d走 ' % ng if ng else '好走なし ', mark))
    P('')
open(OUT, 'w', encoding='utf-8').write('\n'.join(O))
print(OUT)
