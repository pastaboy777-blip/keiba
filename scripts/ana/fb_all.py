# -*- coding: utf-8 -*-
"""出走馬ぜんぶの近5走を、流れと動きで並べる。

  python3 scripts/ana/fb_all.py <card.json> <YYYYMMDD> [場名]

1走ごとに3つ出す。
  流れ … Turn Time がその場その距離の水準より速いか（厳しい／標準／ゆるい）
  形   … Finishing Speed % が水準より上か（保った／落ちた）
  動き … 最初に取れたコーナーから4角までで、位置を上げたか下げたか

南関4場2,751鞍・30,051頭で測ると
  下げた   1着1.5〜1.6% ／ 3着内 7.3〜9.9%
  不動     1着12.4〜14.2% ／ 3着内 32.0〜36.2%
  押し上げ 1着10.8〜11.4% ／ 3着内 35.2〜36.7%
流れを掛けても下げた馬は 厳しい7.3%・ゆるい9.9% で1.4倍しか動かない。
動きそのものが強く、流れは味つけ。
"""
import datetime as dt
import json, statistics as st, sys
from collections import defaultdict

CARD, YMD = sys.argv[1], sys.argv[2]
BA = sys.argv[3] if len(sys.argv) > 3 else '船橋'
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')


def segs(d, l):
    return [d - 200 * (len(l) - 1)] + [200] * (len(l) - 1)


def tt(d, l):
    sg = segs(d, l)
    i = 1 if sg[0] == 200 else 2
    v = l[i:i + 3]
    return sum(v) if len(v) == 3 else None


def fs(d, l):
    t = sum(l)
    return None if t <= 0 or len(l) < 4 else (600 / sum(l[-3:])) / (d / t) * 100


R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R = [r for r in R if r['ymd'] < YMD]
R.sort(key=lambda r: (r['ymd'], r['rid']))

TM, FM = defaultdict(list), defaultdict(list)
for r in R:
    if r.get('lap') and r.get('dist'):
        t, f = tt(r['dist'], r['lap']), fs(r['dist'], r['lap'])
        if t:
            TM[(r['ba'], r['dist'])].append(t)
        if f:
            FM[(r['ba'], r['dist'])].append(f)
TMED = {k: st.median(v) for k, v in TM.items() if len(v) >= 15}
FMED = {k: st.median(v) for k, v in FM.items() if len(v) >= 15}
alltt = sorted(tt(r['dist'], r['lap']) - TMED[(r['ba'], r['dist'])]
               for r in R if r.get('lap') and (r['ba'], r['dist']) in TMED
               and tt(r['dist'], r['lap']))
LO, HI = alltt[len(alltt) // 3], alltt[2 * len(alltt) // 3]

HIST = defaultdict(list)
for r in R:
    if not r.get('dist'):
        continue
    t = tt(r['dist'], r['lap']) if r.get('lap') else None
    f = fs(r['dist'], r['lap']) if r.get('lap') else None
    tm, fm = TMED.get((r['ba'], r['dist'])), FMED.get((r['ba'], r['dist']))
    flow = ('－' if (t is None or tm is None) else
            '厳' if t - tm <= LO else 'ゆ' if t - tm > HI else '標')
    shape = '－' if (f is None or fm is None) else ('保' if f >= fm else '落')
    first = r.get('c1') or r.get('c2') or r.get('c3')
    i0 = {u: i + 1 for i, u in enumerate(first)} if first else {}
    i4 = {u: i + 1 for i, u in enumerate(r.get('c4') or [])}
    for e in r['e']:
        if not e.get('f', '').isdigit():
            continue
        a, b = i0.get(int(e['u'])), i4.get(int(e['u']))
        mv = (a - b) if (a and b) else None
        HIST[e['nm']].append(dict(
            ymd=r['ymd'], ba=r['ba'], R=r['R'], dist=r['dist'],
            baba=r.get('baba'), pop=e.get('pop'), f=e['f'], ag=e.get('ag'),
            wt=e.get('wt'), flow=flow, shape=shape, mv=mv, p4=b, n=len(i4)))

C = json.load(open(CARD, encoding='utf-8'))
BAD = {'厳': '×', '標': '▲', 'ゆ': '△'}
out = []
for k in sorted((x for x in C if str(x).isdigit()), key=int):
    r = C[k]
    print(f"\n=== {k}R {r['dist']}m {r['n']}頭 "
          f"{'='*40}")
    for e in r['e']:
        v = HIST.get(e['nm'], [])[-5:]
        ng = [x for x in v if x['mv'] is not None and x['mv'] <= -1
              and x['flow'] == '厳']
        up = [x for x in v if x['mv'] is not None and x['mv'] >= 1]
        # 閾値は近5走そろう人気薄6,627頭で測った値。1回では動かない。
        #   下げた 0回11.0% 1回10.1% 2回8.9% 3回6.0%
        #   押し上げ 0回8.6% 3回11.8% 5回19.8%・複勝の回収123%
        mark = ('××' if len(ng) >= 3 else '×' if len(ng) >= 2 else
                '◎' if (len(v) == 5 and len(up) == 5) else
                '○' if len(up) >= 3 else ' ')
        print(f"  {mark} {e['u']:>2} {e['nm']:<15}父{(e.get('sire') or '')[:10]}")
        for x in v:
            mv = ('－' if x['mv'] is None else
                  f"+{x['mv']}" if x['mv'] > 0 else f"{x['mv']}" if x['mv'] < 0 else '±0')
            print(f"       {x['ymd'][4:6]}/{x['ymd'][6:]} {x['ba']} {x['dist']}m "
                  f"{x['baba'] or '':<3}{x['pop'] or '-':>3}人{x['f']:>3}着 "
                  f"上り{x['ag'] or '-':>5} 流れ{x['flow']} 形{x['shape']} "
                  f"動き{mv:>3} 4角{x['p4'] or '-'}/{x['n'] or '-'}")
        if not v:
            print('       （南関4場での走りなし）')
        out.append(dict(R=int(k), u=e['u'], nm=e['nm'], mark=mark,
                        ng=len(ng), up=len(up), nrun=len(v)))
json.dump(out, open(f'{SP}/fb_all.json', 'w', encoding='utf-8'),
          ensure_ascii=False)
n = len(out)
print(f"\n{'='*60}")
print(f'出走 {n}頭　× {sum(1 for x in out if x["mark"]=="×")}頭　'
      f'◎ {sum(1 for x in out if x["mark"]=="◎")}頭　'
      f'○ {sum(1 for x in out if x["mark"]=="○")}頭　'
      f'近5走が取れない馬 {sum(1 for x in out if x["nrun"]==0)}頭')
