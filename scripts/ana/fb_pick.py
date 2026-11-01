# -*- coding: utf-8 -*-
"""船橋で検証した材料に合う馬を、出馬表から拾う。

  python3 scripts/ana/fb_pick.py <card.json> <その日のYYYYMMDD>

船橋の人気薄3,468頭（層10.8%・複勝の回収65%）で効いたのは2つ。
  ① 3角→4角で押し上げる（直近5走の中央値が +1以上）
       17.3%・回収89%。下げる馬は 7.7%・56%
  ② 開催初日は、前走も船橋だった馬（＝そのリズムに乗っている）
       13.7%・回収77%。よその場を挟んだ馬は 8.3%・61%
大井で使った「上がりのばらつき」は船橋では効かないので使わない。
"""
import datetime as dt
import json, statistics as st, sys
from collections import defaultdict

CARD, YMD = sys.argv[1], sys.argv[2]
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')


def day(s):
    return dt.date(int(s[:4]), int(s[4:6]), int(s[6:]))


R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R = [r for r in R if r['ymd'] < YMD]
R.sort(key=lambda r: (r['ymd'], r['rid']))

GAIN, POS, POP, LAST = (defaultdict(list), defaultdict(list),
                        defaultdict(list), {})
FORM = defaultdict(list)
for r in R:
    c3 = {u: i + 1 for i, u in enumerate(r.get('c3') or [])}
    c4 = {u: i + 1 for i, u in enumerate(r.get('c4') or [])}
    for e in r['e']:
        nm = e['nm']
        p4, p3 = c4.get(int(e['u'])), c3.get(int(e['u']))
        if p4 and p3:
            GAIN[nm].append(p3 - p4)
        if p4 and len(c4):
            POS[nm].append(p4)
        if str(e.get('pop', '')).isdigit():
            POP[nm].append(int(e['pop']))
        if e.get('tm'):
            LAST[nm] = (r['ymd'], r['ba'])
            FORM[nm].append((r['ymd'], r['ba'], r['dist'], r.get('baba'),
                             e.get('pop'), e.get('f'), e.get('ag'),
                             e.get('wt'), (p3 - p4) if (p3 and p4) else None))

C = json.load(open(CARD, encoding='utf-8'))
hit, thin = [], 0
for k in sorted((x for x in C if str(x).isdigit()), key=int):
    r = C[k]
    for e in r['e']:
        nm = e['nm']
        pg, pp = GAIN[nm][-5:], POS[nm][-5:]
        if len(pg) < 3:
            thin += 1
            continue
        g = st.median(pg)
        pv = LAST.get(nm)
        gap = (day(YMD) - day(pv[0])).days if pv else None
        hit.append(dict(R=int(k), dist=r['dist'], n=r['n'], u=e['u'], nm=nm,
                        sire=e.get('sire', ''), gain=g,
                        pos=st.median(pp) if len(pp) >= 3 else None,
                        pba=(pv[1] if pv else None), gap=gap,
                        pop3=st.median(POP[nm][-3:]) if POP[nm] else None,
                        form=FORM[nm][-5:]))

A = [x for x in hit if x['gain'] >= 1]
B = [x for x in A if x['pba'] == '船橋' and x['gap'] and 22 <= x['gap'] <= 35]
ANA = [x for x in B if x['pop3'] and x['pop3'] >= 6]

nall = sum(len(C[k]['e']) for k in C if str(k).isdigit())
print(f'出走 {nall}頭 / 通過順位が足りない {thin}頭')
print(f'① 押し上げ+1以上 … {len(A)}頭')
print(f'② ＋ 前走も船橋で中22〜35日 … {len(B)}頭')
print(f'③ ＋ 直近3走が6番人気以下 … {len(ANA)}頭\n')


def rows(v, lab):
    print(f'■ {lab}')
    if not v:
        print('  なし\n')
        return
    for x in sorted(v, key=lambda z: (z['R'], -z['gain'])):
        p3 = f"{x['pop3']:.0f}人" if x['pop3'] else '－'
        pos = f"{x['pos']:.1f}番手" if x['pos'] is not None else '－'
        print(f"  {x['R']:>2}R {x['dist']}m {x['n']}頭  {x['u']:>2} "
              f"{x['nm']:<14}3→4角 {x['gain']:+.1f}  ふだん4角 {pos:<8}"
              f"前走 {x['pba']}・中{x['gap']}日  直近{p3}")
        for d, ba, di, bb, pop, f, ag, wt, gg in x['form']:
            print(f"        {d[4:6]}/{d[6:]} {ba} {di}m {bb or '':<3} "
                  f"{pop or '-':>2}人 {f or '-':>3}着 上り{ag or '-':>5} "
                  f"{wt or '-':>4}kg  3→4角 {f'{gg:+d}' if gg is not None else '－'}")
        print()


rows(ANA, '①②③ そろった馬（いちばん厚い形）')
rows([x for x in B if x not in ANA], '①② そろった馬（人気は直近5番人気以内）')
json.dump(dict(all=A, B=B, ana=ANA),
          open(f'{SP}/fb_pick.json', 'w', encoding='utf-8'), ensure_ascii=False)
