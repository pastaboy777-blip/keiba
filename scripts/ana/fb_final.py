# -*- coding: utf-8 -*-
"""月曜船橋を、検証を通った材料だけで組む。

  python3 scripts/ana/fb_final.py <card.json> <YYYYMMDD>

入れるもの（すべて前日に分かる・すべて船橋の人気薄で測った）
  レーティング   上位1/5 18.8%・回収82%（層10.8%・65%）
                 差+1.2kg以上が上位1/5、+3.3kg以上が上位1/10。3走以上に限る
  枠            1600m 外1/3 18.4%・回収109%（内1/3 7.6%・43%）
                 1200m 外1/3 12.8%・69% ／ 1500m 外1/3 12.1%・80%
  開催初日×前走も船橋  13.4%・75%（よその場 8.1%・62%）
  開催間隔 中22〜35日  12.3%・71%（中14日以内 8.2%）

入れないもの
  コーナーの動き … 船橋では逆向き（上げた3回以上 8.7%／層11.0%）
  血統ペース    … 着順の漏れだった。乱数で同点を崩すと効果が消える
"""
import datetime as dt
import json, re, statistics as st, sys
from collections import defaultdict

CARD, YMD = sys.argv[1], sys.argv[2]
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
WAKU = {1600: 18.4, 1200: 12.8, 1500: 12.1}
CUT5, CUT10, MINRUN = 1.2, 3.3, 3


def sec(t):
    m = re.match(r'^(?:(\d+):)?(\d+)\.(\d)$', t.strip()) if t else None
    return None if not m else int(m.group(1) or 0) * 60 + int(m.group(2)) \
        + int(m.group(3)) / 10


R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R = [r for r in R if r['ymd'] < YMD]
R.sort(key=lambda r: (r['ymd'], r['rid']))

RAW = {}
for r in R:
    if not r.get('dist'):
        continue
    ts = [(sec(e.get('tm')), e) for e in r['e'] if e.get('f', '').isdigit()]
    ts = [(t, e) for t, e in ts if t]
    if len(ts) < 4:
        continue
    tw = min(t for t, _ in ts)
    spl, kgl = 2.4 / (r['dist'] / tw), 1380 / r['dist']
    d = {}
    for t, e in ts:
        try:
            kin = float(e.get('kin') or 0)
        except ValueError:
            continue
        if kin > 0 and (t - tw) / spl <= 40:
            d[e['nm']] = kin - (t - tw) / spl * kgl
    if len(d) >= 4:
        RAW[r['rid']] = d
off = defaultdict(float)
byh = defaultdict(list)
for rid, d in RAW.items():
    for nm in d:
        byh[nm].append(rid)
for _ in range(8):
    hr = {nm: st.mean(RAW[x][nm] + off[x] for x in v) for nm, v in byh.items()}
    for rid, d in RAW.items():
        off[rid] = st.median([hr[nm] - d[nm] for nm in d if nm in hr])
PERF = defaultdict(list)
for r in R:
    if r['rid'] in RAW:
        for nm, v in RAW[r['rid']].items():
            PERF[nm].append((r['ymd'], v + off[r['rid']]))
for v in PERF.values():
    v.sort()
LAST = {}
for r in R:
    for e in r['e']:
        LAST[e['nm']] = (r['ymd'], r['ba'], e.get('f'))

C = json.load(open(CARD, encoding='utf-8'))
d0 = dt.date(int(YMD[:4]), int(YMD[4:6]), int(YMD[6:]))
out = []
for k in sorted((x for x in C if str(x).isdigit()), key=int):
    r = C[k]
    n, ds = r['n'], r['dist']
    rows = []
    for e in r['e']:
        pv = [p for y, p in PERF.get(e['nm'], []) if y < YMD][-5:]
        rows.append((e, max(pv) if pv else None, len(pv)))
    got = [x[1] for x in rows if x[1] is not None]
    med = st.median(got) if len(got) >= 5 else None
    for e, best, nr in rows:
        u = int(e['u'])
        pos = (u - 1) / (n - 1) if n > 1 else .5
        pv = LAST.get(e['nm'])
        gap = (d0 - dt.date(int(pv[0][:4]), int(pv[0][4:6]),
                            int(pv[0][6:]))).days if pv else None
        edge = (best - med) if (best is not None and med is not None) else None
        hit = []
        if edge is not None and nr >= MINRUN and edge >= CUT10:
            hit.append('点◎')
        elif edge is not None and nr >= MINRUN and edge >= CUT5:
            hit.append('点○')
        if ds in WAKU and pos > 2 / 3:
            hit.append(f'外枠({WAKU[ds]}%)')
        if pv and pv[1] == '船橋':
            hit.append('前走も船橋')
        if gap and 22 <= gap <= 35:
            hit.append(f'中{gap}日')
        out.append(dict(R=int(k), dist=ds, n=n, u=u, nm=e['nm'],
                        sire=e.get('sire'), prof=e.get('prof'),
                        edge=edge, nrun=nr, hit=hit, pos=pos,
                        pba=pv[1] if pv else None, pf=pv[2] if pv else None,
                        gap=gap))

print(f'■ {YMD} 船橋　検証を通った材料だけで並べる')
print('  点＝レーティング（出走馬の中央との差）◎は上位1/10・○は上位1/5')
print('  層は人気薄で3着内10.7%・複勝の回収65%\n')
for n in (4, 3):
    v = [x for x in out if len(x['hit']) == n]
    if not v:
        continue
    print(f'● {n}つ該当　{len(v)}頭')
    for x in sorted(v, key=lambda y: (y['R'], -(y['edge'] or 0))):
        print(f'  {x["R"]:>2}R {x["dist"]}m {x["n"]}頭  {x["u"]:>2}番 '
              f'{x["nm"]:<16}{"・".join(x["hit"])}')
        print(f'        点 {x["edge"]:+.1f}kg（{x["nrun"]}走）'
              f'　前走 {x["pba"]} {x["pf"]}着　父{x["sire"] or ""}')
    print()
print('● レーティングが上位1/10（点◎）の馬ぜんぶ')
for x in sorted((y for y in out if '点◎' in y['hit']),
                key=lambda y: -(y['edge'] or 0)):
    print(f'  {x["R"]:>2}R {x["dist"]}m  {x["u"]:>2}番 {x["nm"]:<16}'
          f'点 {x["edge"]:+.1f}kg　{"・".join(x["hit"][1:]) or "ほかの材料は該当なし"}')
print('\n  買うのは6〜7番人気になったときだけ。8番人気以降では点が効かない')
