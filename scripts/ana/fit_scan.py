# -*- coding: utf-8 -*-
"""噛み合いを総当たりで洗う。能力ではなく「このレースとの相性」。

  python3 scripts/ana/fit_scan.py [場名]

能力の絶対値はもう値段に入っている。今日のレーティングが3着内率を
層の2.3倍にしても回収75%で止まったのがその証拠。南関の払戻率と同じ。

100%を超えたのは「噛み合い」だけだった。
  船橋1600m 外枠 109% ／ 大井3条件×渋った馬場 135%
いっぽう能力側は レーティング上位1/5 82%／×6〜7番人気 75%。

そこで、市場が単純な見方で済ませていそうな掛け算を総当たりで洗う。
世間が値段をつけるのに使うのは前走着順・人気・騎手名・血統の知名度で、
「この枠でこの馬場でこの頭数なら」という掛け算はしていない。

総当たりは当てずっぽうが混ざるので、前半で見つけて後半で確かめる。
後半で残らなかったものは採らない。
"""
import json, re, sys
from collections import defaultdict

BA = sys.argv[1] if len(sys.argv) > 1 else None
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
CUT = '20260701'
DIVF = {'船橋': 'div_funabashi.json', '大井': 'div_year.json'}

R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R.sort(key=lambda r: (r['ymd'], r['rid']))
D = {}
for ba, fn in DIVF.items():
    try:
        D[ba] = json.load(open(f'{SP}/{fn}', encoding='utf-8'))
    except Exception:
        pass

LAST = {}
ROWS = []
for r in R:
    n = len([e for e in r['e'] if e.get('f', '').isdigit()])
    fk = dict((D.get(r['ba'], {}).get(r['ymd'], {})
               .get(str(r['R']), {})).get('複勝', []))
    for e in r['e']:
        if not e.get('f', '').isdigit():
            continue
        u = int(e['u'])
        pop = e.get('pop', '')
        pv = LAST.get(e['nm'])
        try:
            dw = int((e.get('dw') or '').replace('+', '') or 0)
        except ValueError:
            dw = None
        try:
            kin = float(e.get('kin') or 0)
        except ValueError:
            kin = 0
        ROWS.append(dict(
            ba=r['ba'], ymd=r['ymd'], dist=r['dist'], n=n, u=u,
            baba=r.get('baba') or '', hit=int(e['f']) <= 3,
            pop=int(pop) if pop.isdigit() else None,
            pos=(u - 1) / (n - 1) if n > 1 else .5,
            jk=e.get('jk'), tr=e.get('tr'), kin=kin, dw=dw,
            sx=(e.get('sx') or '')[:1],
            pba=pv[1] if pv else None, pf=pv[2] if pv else None,
            fuku=fk.get(str(u), 0), has=bool(fk)))
        LAST[e['nm']] = (r['ymd'], r['ba'], e.get('f'))

P = [x for x in ROWS if x['pop'] and x['pop'] >= 6 and x['has']
     and (not BA or x['ba'] == BA)]
A = [x for x in P if x['ymd'] < CUT]
B = [x for x in P if x['ymd'] >= CUT]
print(f'人気薄で払戻の分かる {len(P)}頭　前半 {len(A)} / 後半 {len(B)}')
print(f'  前半の回収 {sum(x["fuku"] for x in A)/len(A):.0f}%　'
      f'後半 {sum(x["fuku"] for x in B)/len(B):.0f}%\n')

wet = lambda x: x['baba'] in ('稍重', '重', '不良')
WEDGE = []
# 掛け算の候補。どれも前日に分かるもの
def cells():
    for ba in sorted({x['ba'] for x in P}):
        for ds in sorted({x['dist'] for x in P if x['dist']}):
            for lab, f in (('内1/3', lambda x: x['pos'] <= 1/3),
                           ('中1/3', lambda x: 1/3 < x['pos'] <= 2/3),
                           ('外1/3', lambda x: x['pos'] > 2/3)):
                for wl, wf in (('馬場どちらも', lambda x: True),
                               ('良', lambda x: not wet(x)),
                               ('渋った', wet)):
                    yield (f'{ba} {ds}m {lab} {wl}',
                           lambda x, B=ba, DS=ds, F=f, W=wf:
                           x['ba'] == B and x['dist'] == DS and F(x) and W(x))
    for lab, f in (('馬体重 増えた(+4以上)', lambda x: x['dw'] is not None and x['dw'] >= 4),
                   ('馬体重 減った(-4以下)', lambda x: x['dw'] is not None and x['dw'] <= -4),
                   ('馬体重 ほぼ同じ', lambda x: x['dw'] is not None and abs(x['dw']) <= 3),
                   ('斤量 軽い(53以下)', lambda x: 0 < x['kin'] <= 53),
                   ('斤量 重い(56以上)', lambda x: x['kin'] >= 56),
                   ('牝馬', lambda x: x['sx'] == '牝'),
                   ('前走も同じ場', lambda x: x['pba'] == x['ba']),
                   ('前走はよその場', lambda x: x['pba'] and x['pba'] != x['ba']),
                   ('前走着外(6着以降)', lambda x: (x['pf'] or '').isdigit() and int(x['pf']) >= 6),
                   ('少頭数(10頭以下)', lambda x: x['n'] <= 10),
                   ('多頭数(13頭以上)', lambda x: x['n'] >= 13)):
        yield lab, f
        for wl, wf in (('× 渋った', wet), ('× 良', lambda x: not wet(x)),
                       ('× 外1/3', lambda x: x['pos'] > 2/3),
                       ('× 内1/3', lambda x: x['pos'] <= 1/3)):
            yield f'{lab} {wl}', (lambda x, F=f, W=wf: F(x) and W(x))
    for jk in sorted({x['jk'] for x in P if x['jk']}):
        yield f'騎手 {jk}', (lambda x, J=jk: x['jk'] == J)
    for tr in sorted({x['tr'] for x in P if x['tr']}):
        yield f'厩舎 {tr}', (lambda x, T=tr: x['tr'] == T)

cand = []
for lab, f in cells():
    a = [x for x in A if f(x)]
    if len(a) < 80:
        continue
    ra = sum(x['fuku'] for x in a) / len(a)
    if ra >= 100:
        cand.append((lab, f, len(a), ra))
print(f'■ 前半で回収100%以上だったもの　{len(cand)}通り'
      f'（80頭以上のものだけ）\n')
ok = []
for lab, f, na, ra in sorted(cand, key=lambda y: -y[3]):
    b = [x for x in B if f(x)]
    if len(b) < 40:
        continue
    rb = sum(x['fuku'] for x in b) / len(b)
    hb = 100 * sum(x['hit'] for x in b) / len(b)
    mark = '○' if rb >= 100 else '×'
    print(f'  {mark} {lab:<28} 前半 {na:>5}頭 回収{ra:>4.0f}%　'
          f'→ 後半 {len(b):>5}頭 回収{rb:>4.0f}% 3着内{hb:4.1f}%')
    if rb >= 100:
        ok.append(lab)
print(f'\n  後半でも100%を超えたのは {len(ok)}通り')
if cand:
    print(f'  前半で100%を超えたもののうち後半でも残ったのは '
          f'{100*len(ok)/max(1,len([1 for l,f,n,r in cand if len([x for x in B if f(x)])>=40])):.0f}%')
