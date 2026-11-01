# -*- coding: utf-8 -*-
"""血統ペース理論を出馬表に当てる。

  python3 scripts/ana/ped_pace_card.py <card.json> <YYYYMMDD> [場名]

やること
  ① 前走までの4角位置から、今日の先頭（逃げ馬）を予想する
  ② 各馬の祖先4代と、予想先頭の祖先4代との重なりを出す
     珍しい祖先ほど重く数える（Northern Dancer のようにほぼ全頭にいる
     祖先は軽く、固有の祖先は重く）
  ③ レースの中で順位にする

測った結果（人気薄8,845頭・層10.5%・複勝の回収66%）
  予想先頭に似ている 上位1/3  13.2%・回収79%
                   下位1/3   6.7%・回収44%
先頭の予想が当たるのは28%しかないが、それでも効く。
"""
import json, math, statistics as st, sys
from collections import defaultdict

CARD, YMD = sys.argv[1], sys.argv[2]
BA = sys.argv[3] if len(sys.argv) > 3 else '船橋'
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
DEPTH = 3

NM, SI = {}, {}
for l in open(f'{SP}/anc.jsonl', encoding='utf-8'):
    v = json.loads(l)
    SI[v['id']] = (v.get('s'), v.get('d'))
    if v.get('nm') and not v['nm'].isdigit():
        NM.setdefault(v['nm'], v['id'])
_c = {}


def anc(h, d=DEPTH):
    k = (h, d)
    if k in _c:
        return _c[k]
    o = {h}
    if d > 0 and h in SI:
        for p in SI[h]:
            if p:
                o |= anc(p, d - 1)
    _c[k] = o
    return o


PED = {}
for fn in ('ped_all.jsonl', 'ped2026.jsonl', 'ped_extra.jsonl', 'ped_mon.jsonl'):
    try:
        for l in open(f'{SP}/{fn}', encoding='utf-8'):
            v = json.loads(l)
            if v.get('nm') and v.get('sire'):
                PED[v['nm']] = (v['sire'], v.get('bms') or '',
                                v.get('sid'), v.get('bid'))
    except FileNotFoundError:
        pass

ANC = {}
for nm, t in PED.items():
    s, b = t[0], t[1]
    sid, bid = (t[2], t[3]) if len(t) > 3 else (None, None)
    a = set()
    for nam, i in ((s, sid), (b, bid)):
        hid = i if (i and i in SI) else (NM.get(nam) if nam else None)
        if hid:
            a |= anc(hid)
    if a:
        ANC[nm] = a

cnt = defaultdict(int)
for a in ANC.values():
    for x in a:
        cnt[x] += 1
N = len(ANC)
W = {x: math.log(N / c) for x, c in cnt.items()}
ID2NM = {i: n for n, i in NM.items()}


def sim(a, b):
    return sum(W.get(x, 0) for x in (a & b))


# ── 前走までの4角位置 ──
R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R = [r for r in R if r['ymd'] < YMD]
R.sort(key=lambda r: (r['ymd'], r['rid']))
HIST = defaultdict(list)
for r in R:
    c4 = r.get('c4') or []
    if not c4:
        continue
    for i, u in enumerate(c4):
        HIST.setdefault(None, None)
    pos = {u: (i + 1) / len(c4) for i, u in enumerate(c4)}
    for e in r['e']:
        if int(e['u']) in pos:
            HIST[e['nm']].append((r['ymd'], pos[int(e['u'])]))

C = json.load(open(CARD, encoding='utf-8'))
print(f'■ {YMD} {BA}　血統ペース ── 予想した先頭と配合が似ている馬')
print('  前走までの4角位置で先頭を予想し、祖先4代の重なりで並べる')
print('  人気薄で 上位1/3 13.2%・回収79% ／ 下位1/3 6.7%・44%'
      '（層10.5%・66%）\n')
TOP = []
for k in sorted((x for x in C if str(x).isdigit()), key=int):
    r = C[k]
    pred, best = None, 9
    for e in r['e']:
        v = [x for x in HIST.get(e['nm'], []) if x[0] < YMD][-5:]
        if len(v) >= 2:
            m = st.median(x[1] for x in v)
            if m < best:
                best, pred = m, e
    if not pred or pred['nm'] not in ANC:
        print(f'  ── {k}R {r["dist"]}m　先頭の予想が立たない'
              f'（{pred["nm"] if pred else "前走の位置なし"}）\n')
        continue
    pa = ANC[pred['nm']]
    rows = [(e, sim(ANC[e['nm']], pa)) for e in r['e']
            if e['nm'] in ANC and e['nm'] != pred['nm']]
    if len(rows) < 5:
        print(f'  ── {k}R {r["dist"]}m　血統の引ける馬が少ない'
              f'（{len(rows)}頭）\n')
        continue
    rows.sort(key=lambda x: -x[1])
    n = len(rows)
    print(f'  ── {k}R {r["dist"]}m {r["n"]}頭　'
          f'予想先頭 {pred["u"]}番 {pred["nm"]}'
          f'（父{(pred.get("sire") or "")[:10]}）──')
    for i, (e, s) in enumerate(rows):
        mk = '◎' if i < n / 3 else '　' if i < 2 * n / 3 else '×'
        shared = sorted((W.get(x, 0), ID2NM.get(x, x))
                        for x in (ANC[e['nm']] & pa))[-3:]
        sh = '・'.join(nm for _, nm in reversed(shared))
        print(f'     {mk}{e["u"]:>2} {e["nm"]:<16}重なり{s:>6.1f}  {sh}')
        if i < n / 3:
            TOP.append((int(k), e['u'], e['nm'], s, r['dist'],
                        pred['u'], pred['nm']))
    miss = [e['nm'] for e in r['e'] if e['nm'] not in ANC]
    if miss:
        print(f'       血統が引けない：{"、".join(miss)}')
    print()
print(f'● 予想先頭に似ている上位1/3　{len(TOP)}頭')
for x in TOP:
    print(f'  {x[0]:>2}R {x[4]}m  {x[1]:>2}番 {x[2]:<16}'
          f'（予想先頭 {x[5]}番 {x[6]}）')
