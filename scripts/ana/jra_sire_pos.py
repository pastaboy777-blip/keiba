# -*- coding: utf-8 -*-
"""血統を、着順ではなく「どこを走ったか」で見る。

  python3 scripts/ana/jra_sire_pos.py <結果json> <corner json> <sire jsonl>

1日12鞍188頭では、父ごとの3着内率は測れない（1頭が2頭になるだけで倍になる）。
なので着順ではなく、父が「前に行く産駒か／終いを使う産駒か」を見る。
位置と上がりは全馬ぶん出るので、着順より母数が効く。

出すもの
  ① 3着内36頭の父・母父（記述。条件ではない）
  ② 4頭以上いる父の、4角位置の中央値と上がり順位の中央値
  ③ 同じ割り方を母父にも当てる
  ④ 偽薬：馬番の偶奇で割っても同じ差が出ないか
"""
import json
import re
import statistics as st
import sys
from collections import defaultdict

RES, COR, SIRE = sys.argv[1], sys.argv[2], sys.argv[3]
R = json.load(open(RES, encoding='utf-8'))
C = json.load(open(COR, encoding='utf-8'))
P = {}
for l in open(SIRE, encoding='utf-8'):
    try:
        d = json.loads(l)
        P[d['hid']] = d
    except Exception:
        pass

T = []
for k, r in R.items():
    c4 = (C.get(k) or {}).get('c4') or {}
    ent = [e for e in r['e'] if str(e.get('f', '')).isdigit()]
    n = len(ent)
    ags = sorted({float(e['ag']) for e in ent if e.get('ag')})
    rk = {a: i + 1 for i, a in enumerate(ags)}
    for e in ent:
        u, hid = str(e['u']), e.get('hid')
        if u not in c4 or not e.get('ag') or hid not in P:
            continue
        p, o = e.get('pop', ''), e.get('odds', '')
        T.append(dict(R=int(k), surf=r['surf'], dist=r['dist'], n=n, nm=e['nm'],
                      u=int(e['u']), f=int(e['f']),
                      pop=int(p) if p.isdigit() else None,
                      odds=float(o) if re.match(r'^[\d.]+$', o or '') else None,
                      c4=c4[u], c4r=round(c4[u] * (n - 1)) + 1,
                      agr=rk[float(e['ag'])], ag=float(e['ag']),
                      sire=P[hid]['sire'], damsire=P[hid]['damsire']))

print(f'■ 材料がそろった {len(T)}頭 / {len({x["R"] for x in T})}鞍\n')

print('■ ① 3着内36頭（父 / 母父）')
for x in sorted([x for x in T if x['f'] <= 3], key=lambda y: (y['R'], y['f'])):
    print(f"  {x['R']:>2}R {x['surf']}{x['dist']:>4} {x['f']}着 {x['pop']:>2}人気 "
          f"4角{x['c4r']:>2}番手 上り順{x['agr']:>2}  {x['nm']:<12} "
          f"{x['sire']} / {x['damsire']}")


def tbl(lab, key, mn=4):
    g = defaultdict(list)
    for x in T:
        g[x[key]].append(x)
    v = sorted([(k, s) for k, s in g.items() if len(s) >= mn],
               key=lambda t: st.median(x['c4'] for x in t[1]))
    print(f'\n■ {lab}（{mn}頭以上。0が先頭・1.00が最後方）')
    print(f'  {"":<18}{"頭":>3}  {"4角の中央値":>10}  {"上がり順位":>9}  {"3着内":>6}')
    for k, s in v:
        print(f'  {k:<18}{len(s):>3}  '
              f'{st.median(x["c4"] for x in s):>10.2f}  '
              f'{st.median(x["agr"] for x in s):>9.1f}  '
              f'{sum(1 for x in s if x["f"]<=3):>4}頭')


tbl('② 父ごとの、走った場所', 'sire')
tbl('③ 母父ごとの、走った場所', 'damsire')

print('\n■ ④ 偽薬：馬番の偶奇で割る（血統と関係ない割り方）')
for t, f in (('奇数番', lambda x: x['u'] % 2 == 1), ('偶数番', lambda x: x['u'] % 2 == 0)):
    s = [x for x in T if f(x)]
    print(f'  {t:<18}{len(s):>3}  '
          f'{st.median(x["c4"] for x in s):>10.2f}  '
          f'{st.median(x["agr"] for x in s):>9.1f}  '
          f'{sum(1 for x in s if x["f"]<=3):>4}頭')
print('  ここに差が出るなら、②③の差も割り方のゆらぎの範囲。')
