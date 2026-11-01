# -*- coding: utf-8 -*-
"""まだ測っていなかった2つ ── 隊列と枠順。

  python3 scripts/ana/nankan_shape.py [場名...]

隊列
  出走各馬の「ふだんの4角位置」から、前に行きたい馬が何頭いるかを
  発走前に数える。多ければ先行争いがきつくなり、少なければ楽に行ける。
  これまで馬ごとの材料しか見ていなかったので、鞍の形は完全に未着手。

枠順
  内か外か。場と距離でちがうはずだが、一度も測っていない。
"""
import json, statistics as st, sys
from collections import defaultdict

BA = sys.argv[1:] or ['大井', '船橋', '川崎', '浦和']
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
DIVF = {'船橋': 'div_funabashi.json', '大井': 'div_year.json'}

R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R.sort(key=lambda r: (r['ymd'], r['rid']))

for ba in BA:
    DIV = {}
    if ba in DIVF:
        try:
            DIV = json.load(open(f'{SP}/{DIVF[ba]}', encoding='utf-8'))
        except Exception:
            pass
    POS, GAIN = defaultdict(list), defaultdict(list)
    ROWS = []
    for r in R:
        if r['ba'] != ba or not r.get('dist'):
            continue
        c3 = {u: i + 1 for i, u in enumerate(r.get('c3') or [])}
        c4 = {u: i + 1 for i, u in enumerate(r.get('c4') or [])}
        n = r['n'] or len(r['e'])
        fk = dict((DIV.get(r['ymd'], {}).get(str(r['R']), {})).get('複勝', []))
        # ── 発走前に数えられる「前に行きたい馬」 ──
        front = 0
        known = 0
        for e in r['e']:
            pp = POS[e['nm']][-5:]
            if len(pp) >= 3:
                known += 1
                if st.median(pp) <= 3:
                    front += 1
        for e in r['e']:
            if not e.get('f', '').isdigit():
                continue
            nm = e['nm']
            pp, pg = POS[nm][-5:], GAIN[nm][-5:]
            pop = e.get('pop', '')
            waku = e.get('waku', '')
            ROWS.append(dict(
                hit=int(e['f']) <= 3,
                pop=int(pop) if pop.isdigit() else None,
                fuku=fk.get(str(int(e['u'])), 0), has=bool(fk),
                front=front, known=known, n=n,
                u=int(e['u']), waku=int(waku) if str(waku).isdigit() else None,
                ur=int(e['u']) / n if n else None,
                pos=st.median(pp) if len(pp) >= 3 else None,
                gain=st.median(pg) if len(pg) >= 3 else None,
                dist=r['dist']))
        for e in r['e']:
            nm = e['nm']
            p4, p3 = c4.get(int(e['u'])), c3.get(int(e['u']))
            if p4 and len(c4):
                POS[nm].append(p4)
            if p4 and p3:
                GAIN[nm].append(p3 - p4)

    P = [x for x in ROWS if x['pop'] and x['pop'] >= 6 and x['known'] >= 6]
    if len(P) < 500:
        print(f'■ {ba}  材料不足（{len(P)}頭）\n')
        continue
    base = 100 * sum(x['hit'] for x in P) / len(P)
    print(f'■ {ba}　人気薄 {len(P)}頭　3着内 {base:.1f}%')

    def show(lab, f, mn=80):
        v = [x for x in P if f(x)]
        if len(v) < mn:
            print(f'    {lab:<28} 材料不足({len(v)})')
            return
        i = sum(x['hit'] for x in v)
        d = [x for x in v if x['has']]
        roi = f'  回収 {sum(x["fuku"] for x in d)/len(d):5.0f}%' if d else ''
        print(f'    {lab:<28} {100*i/len(v):5.1f}%{roi}  ({i}/{len(v)})'
              f' {100*i/len(v)-base:+5.1f}pt')

    print('  〈隊列〉前に行きたい馬（ふだん4角3番手以内）が何頭いる鞍か')
    for lab, lo, hi in (('0〜1頭', 0, 2), ('2頭', 2, 3), ('3頭', 3, 4),
                        ('4頭以上', 4, 99)):
        show(lab, lambda x, a=lo, b=hi: a <= x['front'] < b)
    print('  〈隊列 × その馬の脚質〉')
    for fl, flo, fhi in (('前が少ない鞍(0-1頭)', 0, 2), ('前が多い鞍(3頭以上)', 3, 99)):
        for pl, pf in (('ふだん前め(3番手以内)', lambda x: x['pos'] is not None and x['pos'] <= 3),
                       ('ふだん後ろ(8番手以降)', lambda x: x['pos'] is not None and x['pos'] > 7)):
            show(f'{fl} × {pl}',
                 lambda x, a=flo, b=fhi, g=pf: a <= x['front'] < b and g(x), mn=40)
    print('  〈枠順〉馬番を頭数で割った位置')
    for lab, lo, hi in (('内から1/4', 0, 0.25), ('1/4〜1/2', 0.25, 0.5),
                        ('1/2〜3/4', 0.5, 0.75), ('外から1/4', 0.75, 1.01)):
        show(lab, lambda x, a=lo, b=hi: x['ur'] is not None and a < x['ur'] <= b)
    print()
