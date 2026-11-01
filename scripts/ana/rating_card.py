# -*- coding: utf-8 -*-
"""レーティングを出馬表に当てる。

  python3 scripts/ana/rating_card.py <card.json> <YYYYMMDD> [場名]

rating2.py と同じ作り方で全レースを日付順に点にして、最後に出馬表の
出走馬それぞれの点を出す。使うのはその日より前の走だけ。

  自分の点     近5走でいちばん良かった点
  相手関係     出走馬の点の中央値
  差           自分の点 − 相手関係

測った結果（区切り20260701・後1,104鞍）
  船橋 点が上位1/5 18.8%・回収82%（層10.8%・65%）
  2場 点が上位1/5 × 6〜7番人気 22.1%・回収75%（層9.7%・64%）
  8番人気以降は効かない。6〜7番人気の帯で使う。

境目は実測で決める。人気薄3,309頭の差の分布で
  上位1/5 = 差 +1.2kg 以上
  上位1/10 = 差 +3.3kg 以上
走った数が足りない馬は外す。該当した662頭のうち607頭が5走そろった馬で、
走りの少ない馬はほとんど検証に入っていない（1走9頭・2走16頭）。
点が暴れるので、3走以上に限る。
  3走以上 × 上位1/5 × 6〜7番人気  21.3%・回収73%
"""
import json, re, statistics as st, sys
from collections import defaultdict

CARD, YMD = sys.argv[1], sys.argv[2]
BA = sys.argv[3] if len(sys.argv) > 3 else '船橋'
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')


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
    twin = min(t for t, _ in ts)
    spl, kgl = 2.4 / (r['dist'] / twin), 1380 / r['dist']
    d = {}
    for t, e in ts:
        try:
            kin = float(e.get('kin') or 0)
        except ValueError:
            continue
        if kin > 0 and (t - twin) / spl <= 40:
            d[e['nm']] = kin - (t - twin) / spl * kgl
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
            PERF[nm].append((r['ymd'], v + off[r['rid']], r['ba'], r['dist'],
                             r['R']))
for v in PERF.values():
    v.sort()

C = json.load(open(CARD, encoding='utf-8'))
print(f'■ {YMD} {BA}　レーティング')
print('  点は斤量に直した目安。自分の近5走でいちばん良かった点と、'
      '出走馬の中央値の差を見る')
print('  船橋の人気薄で 点が上位1/5 → 3着内18.8%・複勝の回収82%（層10.8%・65%）')
print('  6〜7番人気の帯でいちばん効く。8番人気以降では効かない\n')
CUT5, CUT10, MINRUN = 1.2, 3.3, 3
TOP = []
for k in sorted((x for x in C if str(x).isdigit()), key=int):
    r = C[k]
    rows = []
    for e in r['e']:
        pv = [(y, p) for y, p, *_ in PERF.get(e['nm'], []) if y < YMD][-5:]
        rows.append((e, max((p for _, p in pv), default=None), pv))
    got = [x[1] for x in rows if x[1] is not None]
    if len(got) < 5:
        print(f'  {k}R {r["dist"]}m　点の取れた馬が少ない（{len(got)}頭）\n')
        continue
    med = st.median(got)
    rows.sort(key=lambda x: -(x[1] if x[1] is not None else -99))
    print(f'  ── {k}R {r["dist"]}m {r["n"]}頭　相手関係 {med:.1f}kg ──')
    for e, best, pv in rows:
        if best is None:
            print(f'      {e["u"]:>2} {e["nm"]:<16} 点なし（南関での走りなし）')
            continue
        dd = best - med
        ok = len(pv) >= MINRUN
        mk = ('◆' if (ok and dd >= CUT10) else
              '○' if (ok and dd >= CUT5) else
              '･' if not ok else '  ')
        print(f'     {mk}{e["u"]:>2} {e["nm"]:<16}'
              f'{best:>6.1f}kg  差 {dd:>+5.1f}  {len(pv)}走'
              f'  {" ".join(f"{p:.0f}" for _, p in pv)}')
        if ok and dd >= CUT5:
            TOP.append((int(k), e['u'], e['nm'], best, dd, r['dist'],
                        len(pv)))
    print()
print(f'● 点が上位1/5（差 +{CUT5}kg以上）で3走以上　{len(TOP)}頭')
print('  ◆は上位1/10（差 +3.3kg以上）')
for x in sorted(TOP, key=lambda y: -y[4]):
    print(f'  {"◆" if x[4] >= CUT10 else "○"} {x[0]:>2}R {x[5]}m'
          f'  {x[1]:>2}番 {x[2]:<16}{x[3]:.1f}kg（差{x[4]:+.1f}・{x[6]}走）')
print('\n  買うのは6〜7番人気になったときだけ。8番人気以降では効かない')
print('  （船橋12.5%・大井7.0%。当日の人気を見てから決める）')
