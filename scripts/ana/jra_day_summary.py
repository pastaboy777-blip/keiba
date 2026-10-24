# -*- coding: utf-8 -*-
"""中央1日ぶんの結果を、芝とダートに分けてまとめる。

  python3 scripts/ana/jra_day_summary.py <jra_kb.json>

競馬ブックの成績から、場・馬場の推移、人気の決まり方、4角位置、
前半3F/上り3F の形を芝・ダート別に出す。
"""
import json, sys, collections, statistics

D = json.load(open(sys.argv[1], encoding='utf-8'))
rows = []
for rid, r in sorted(D.items(), key=lambda z: (z[1]['ba'][:2], z[1]['R'])):
    for e in r['e']:
        if not e['f'].isdigit():
            continue
        rows.append(dict(ba=r['ba'][:2], R=r['R'], surf=r['surf'], dist=r['dist'],
                         baba=r['baba'], tenki=r.get('tenki', ''), name=r['name'],
                         pace=r['pace'], kime=r['kime'], agari=r['agari'],
                         f=int(e['f']), pop=int(e['pop']) if e['pop'].isdigit() else None,
                         lane=e['lane'], f3=e['f3'], ag=e['ag'], nm=e['nm'], u=e['u']))


def pct(a, b):
    return f'{a/b*100:.0f}%' if b else '—'


print('# 2026/10/24 中央 ── 芝とダート\n')
for surf in ('芝', 'ダート'):
    rs = [x for x in rows if x['surf'] == surf]
    races = sorted({(x['ba'], x['R']) for x in rs})
    print(f'\n## {surf}　{len(races)}鞍 / {len(rs)}頭')
    # 馬場
    bb = collections.Counter((x['ba'], x['baba']) for x in rs)
    print('  馬場 … ' + '／'.join(f'{b}{k}' for (b, k), v in sorted(bb.items())))
    # 人気
    print('\n  | 人気 | 頭数 | 勝 | 3着内 | 複勝率 |')
    print('  |---|---|---|---|---|')
    for lo, hi, lab in ((1, 1, '1番人気'), (2, 3, '2〜3'), (4, 6, '4〜6'),
                        (7, 9, '7〜9'), (10, 30, '10番人気以下')):
        g = [x for x in rs if x['pop'] and lo <= x['pop'] <= hi]
        if not g:
            continue
        w = sum(1 for x in g if x['f'] == 1)
        h = sum(1 for x in g if x['f'] <= 3)
        print(f'  | {lab} | {len(g)} | {w} | {h} | {pct(h,len(g))} |')
    # 4角位置
    print('\n  | 4角位置 | 頭数 | 3着内 | 複勝率 |')
    print('  |---|---|---|---|')
    order = ['最内', '内', '中', '外', '大外']
    cnt = collections.Counter(x['lane'] for x in rs)
    for k in order + [k for k in cnt if k not in order]:
        g = [x for x in rs if x['lane'] == k]
        if len(g) < 5:
            continue
        h = sum(1 for x in g if x['f'] <= 3)
        print(f'  | {k or "（記載なし）"} | {len(g)} | {h} | {pct(h,len(g))} |')
    # 勝ち馬の形
    print('\n  | 場 | R | 距離 | 馬場 | レース | ペース | 決め手 | 前後半 |')
    print('  |---|---|---|---|---|---|---|---|')
    for (ba, R) in races:
        r = next(x for x in rs if x['ba'] == ba and x['R'] == R)
        w = next((x for x in rs if x['ba'] == ba and x['R'] == R and x['f'] == 1), None)
        print(f"  | {ba} | {R} | {r['dist']} | {r['baba']} | {r['name'][:14]} | "
              f"{r['pace']} | {r['kime'][:22]} | {r['agari']} |")
