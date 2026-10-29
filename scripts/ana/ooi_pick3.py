# -*- coding: utf-8 -*-
"""検証ずみの3条件に当てはまる馬を、出馬表から拾う。

  python3 scripts/ana/ooi_pick3.py <card.json> [as-ofのYYYYMMDD]

3条件（今年の大井・人気薄6,394頭で検証）
  ① 同じ距離帯の直近5走の上がりのばらつきが 0.6未満（4走以上ある馬）
  ② ふだんの4角が 7番手以内（直近5走の中央値、3走以上）
  ③ 3角→4角で下げない（同じく中央値が −0.5より大きい）
  3つそろって 16.1%・複勝の回収87%。人気薄ぜんぶは 9.0%・61%

あわせて「粘りの向き」も出す。これは買い材料としては弱く（+1.2pt）、
下向きを外す材料として使う。
"""
import json, re, statistics as st, sys
from collections import defaultdict

CARD = sys.argv[1]
ASOF = sys.argv[2] if len(sys.argv) > 2 else '99999999'
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')


def sec(t):
    m = re.match(r'^(?:(\d+):)?(\d+)\.(\d)$', t.strip()) if t else None
    return None if not m else (int(m.group(1) or 0)) * 60 + int(m.group(2)) \
        + int(m.group(3)) / 10


def band(d):
    return 'S' if d <= 1300 else 'M' if d <= 1700 else 'L'


CN = {}
for l in open(f'{SP}/corners_2026.jsonl', encoding='utf-8'):
    v = json.loads(l)
    CN[v['rid']] = v
R2 = []
for l in open(f'{SP}/ooi_2026_runs.jsonl', encoding='utf-8'):
    r = json.loads(l)
    if r.get('dist') and r.get('e') and r['ymd'] < ASOF:
        R2.append(r)
R2.sort(key=lambda r: (r['ymd'], r['rid']))

AG, POS, GAIN, NEB, POP = (defaultdict(list), defaultdict(list),
                           defaultdict(list), defaultdict(list),
                           defaultdict(list))
for r in R2:
    cn = CN.get(r['rid']) or {}
    c3 = {u: i + 1 for i, u in enumerate(cn.get('c3') or [])}
    c4 = {u: i + 1 for i, u in enumerate(cn.get('c4') or [])}
    hs = []
    for e in r['e']:
        t, a = sec(e.get('tm')), sec(e.get('ag') or '')
        if t and a and t > a:
            hs.append((e, t - a, a))
    if len(hs) >= 7:
        mh = st.median([x[1] for x in hs])
        ma = st.median([x[2] for x in hs])
        for e, h, a in hs:
            NEB[e['nm']].append(-((a - ma) - (h - mh)))
    for e in r['e']:
        nm = e['nm']
        if re.match(r'^\d+\.\d$', e.get('ag') or ''):
            AG[nm].append((r['dist'], float(e['ag'])))
        p4, p3 = c4.get(int(e['u'])), c3.get(int(e['u']))
        if p4 and len(c4):
            POS[nm].append(p4)
        if p4 and p3:
            GAIN[nm].append(p3 - p4)
        if str(e.get('pop', '')).isdigit():
            POP[nm].append(int(e['pop']))

C = json.load(open(CARD, encoding='utf-8'))
hit, thin = [], 0
for k in sorted((x for x in C if str(x).isdigit()), key=int):
    r = C[k]
    d = r['dist']
    for e in r['e']:
        nm = e['nm']
        pa = [a for dd, a in AG[nm] if band(dd) == band(d)][-5:]
        pp, pg, pn = POS[nm][-5:], GAIN[nm][-5:], NEB[nm][-5:]
        if len(pa) < 4 or len(pp) < 3 or len(pg) < 3:
            thin += 1
            continue
        sd = st.pstdev(pa)
        pos = st.median(pp)
        gn = st.median(pg)
        if not (sd < 0.6 and pos <= 7 and gn > -0.5):
            continue
        hit.append(dict(R=int(k), dist=d, n=r['n'], u=e['u'], nm=nm,
                        sire=e.get('sire', ''), sd=round(sd, 2),
                        pos=pos, gain=gn, nag=len(pa),
                        trend=round(st.mean(pn[3:]) - st.mean(pn[:3]), 2)
                        if len(pn) == 5 else None,
                        lv=round(st.mean(pn[-2:]), 2) if len(pn) >= 2 else None,
                        pop3=st.median(POP[nm][-3:]) if POP[nm] else None,
                        wt=e.get('wt', '')))

nall = sum(len(C[k]['e']) for k in C if str(k).isdigit())
print(f'出走 {nall}頭 / 材料が足りない {thin}頭 / 3条件に合う {len(hit)}頭\n')
print(f"{'R':>3} {'番':>3} {'馬名':<14}{'ばらつき':>8}{'ふだん4角':>9}"
      f"{'3→4角':>8}{'粘りの向き':>10}{'直近人気':>8}")
for x in hit:
    tr = f"{x['trend']:+.2f}" if x['trend'] is not None else '－'
    p3 = f"{x['pop3']:.0f}" if x['pop3'] is not None else '－'
    print(f"{x['R']:>3} {x['u']:>3} {x['nm']:<14}{x['sd']:>8.2f}"
          f"{x['pos']:>8.1f}番{x['gain']:>+8.1f}{tr:>10}{p3:>7}人")
json.dump(hit, open(f'{SP}/pick3.json', 'w', encoding='utf-8'),
          ensure_ascii=False)
print(f'\n書き出し {SP}/pick3.json')
