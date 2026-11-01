# -*- coding: utf-8 -*-
"""前走を「その鞍の形」で補正して、次走が当たるかを測る。

  python3 scripts/ana/nankan_trip.py [場名...]

考え方は米国の trip handicapping と同じ。着順そのものではなく、
「その形の鞍で、その位置にいた馬がふつうどうなるか」からの
ズレを見る。

  形 … Finishing Speed %（後半600mの速さ ÷ 全体平均）がその距離の
        中央より上か下か。下＝終いが落ちた＝前が無理をした鞍
  位置 … 4角で前・中・後ろのどこにいたか

たとえば終いが落ちた1200mの4角先頭は、ふつう3着内が47%しかない。
そこで残した馬は、着順が同じでも中身が濃い。逆に終いが保った鞍の
先頭は60%来るので、同じ3着でも価値が低い。

この「ふつうとのズレ」を前走ぶん出して、次走の3着内を当てられるかを見る。

着順は3着内かどうかの2択ではなく、0〜1 に直して使う（1が勝ち）。
2択だと「難しい形の4着」と「同じ形の10着」が同じ扱いになり、
補正が効かなくなる。ここが最初の作りの失敗だった。
"""
import json, statistics as st, sys
from collections import defaultdict

BA = sys.argv[1:] or ['船橋', '大井']
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
DIVF = {'船橋': 'div_funabashi.json', '大井': 'div_year.json'}


def fs_pct(dist, lap):
    tot = sum(lap)
    if tot <= 0 or len(lap) < 4:
        return None
    return (600 / sum(lap[-3:])) / (dist / tot) * 100


R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R.sort(key=lambda r: (r['ymd'], r['rid']))

# ── その場その距離の Finishing Speed % の中央値 ──
FSM = defaultdict(list)
for r in R:
    if r.get('lap') and r.get('dist'):
        f = fs_pct(r['dist'], r['lap'])
        if f:
            FSM[(r['ba'], r['dist'])].append(f)
FSM = {k: st.median(v) for k, v in FSM.items() if len(v) >= 20}

# ── 1走ぶんの「形 × 位置」と結果 ──
CELL = defaultdict(lambda: [0.0, 0])   # (場,形,位置) -> [着順を0〜1にした合計, 頭数]
RUNS = defaultdict(list)                # 馬 -> [(ymd, 場, cell, 3着内)]
for r in R:
    if not (r.get('lap') and r.get('dist') and r.get('c4')):
        continue
    m = FSM.get((r['ba'], r['dist']))
    f = fs_pct(r['dist'], r['lap'])
    if m is None or f is None:
        continue
    shape = '保った' if f >= m else '落ちた'
    c4 = {u: i + 1 for i, u in enumerate(r['c4'])}
    n = len(r['c4'])
    for e in r['e']:
        if not e.get('f', '').isdigit():
            continue
        p = c4.get(int(e['u']))
        if not p or not n:
            continue
        rr = p / n
        posl = '前' if rr <= 0.3 else '中' if rr <= 0.65 else '後'
        key = (r['ba'], shape, posl)
        hit = int(e['f']) <= 3
        N = len([x for x in r['e'] if x.get('f', '').isdigit()])
        if N < 2:
            continue
        perf = 1 - (int(e['f']) - 1) / (N - 1)      # 1が勝ち、0が最下位
        CELL[key][0] += perf
        CELL[key][1] += 1
        RUNS[e['nm']].append((r['ymd'], r['ba'], key, perf, hit))

print('■ 「形 × 位置」でふつうどれだけ来るか')
for ba in BA:
    print(f'  {ba}')
    for shape in ('落ちた', '保った'):
        row = []
        for posl in ('前', '中', '後'):
            h, t = CELL[(ba, shape, posl)]
            row.append(f'{posl} {100*h/t:4.1f}%({t})' if t >= 100 else f'{posl} －')
        print(f'    終いが{shape}鞍　' + '  '.join(row))
print()

# ── 前走のズレで、次走を当てられるか ──
for ba in BA:
    DIV = {}
    if ba in DIVF:
        try:
            DIV = json.load(open(f'{SP}/{DIVF[ba]}', encoding='utf-8'))
        except Exception:
            pass
    ROWS = []
    for r in R:
        if r['ba'] != ba:
            continue
        fk = dict((DIV.get(r['ymd'], {}).get(str(r['R']), {})).get('複勝', []))
        for e in r['e']:
            if not e.get('f', '').isdigit():
                continue
            v = RUNS.get(e['nm']) or []
            pv = [x for x in v if x[0] < r['ymd']]
            if not pv:
                continue
            ymd, pba, key, perf, praw = pv[-1]
            h, t = CELL[key]
            if t < 100:
                continue
            pop = e.get('pop', '')
            ROWS.append(dict(hit=int(e['f']) <= 3,
                             pop=int(pop) if pop.isdigit() else None,
                             edge=perf - h / t,
                             praw=praw, shape=key[1], pos=key[2],
                             fuku=fk.get(str(int(e['u'])), 0), has=bool(fk)))
    P = [x for x in ROWS if x['pop'] and x['pop'] >= 6]
    if len(P) < 500:
        print(f'■ {ba} 材料不足（{len(P)}頭）\n')
        continue
    base = 100 * sum(x['hit'] for x in P) / len(P)
    print(f'■ {ba}　人気薄 {len(P)}頭　3着内 {base:.1f}%')

    def show(lab, f, mn=100):
        v = [x for x in P if f(x)]
        if len(v) < mn:
            print(f'    {lab:<30} 材料不足({len(v)})')
            return
        i = sum(x['hit'] for x in v)
        d = [x for x in v if x['has']]
        roi = f'  回収 {sum(x["fuku"] for x in d)/len(d):5.0f}%' if d else ''
        print(f'    {lab:<30} {100*i/len(v):5.1f}%{roi}  ({i}/{len(v)})'
              f' {100*i/len(v)-base:+5.1f}pt')

    print('  〈比べる相手〉前走が3着内だったかどうか（補正なし）')
    show('前走3着内', lambda x: x['praw'])
    show('前走は着外', lambda x: not x['praw'])
    print('  〈補正あり〉前走のズレ（その形・その位置のふつうからの差）')
    q = sorted(x['edge'] for x in P)
    for lab, lo, hi in (('ズレ 上位1/4', .75, 1.01), ('2/4', .5, .75),
                        ('3/4', .25, .5), ('下位1/4', 0, .25)):
        a = q[int(len(q) * lo) - 1] if lo else q[0]
        b = q[min(int(len(q) * hi), len(q) - 1)]
        show(lab, lambda x, A=a, B=b: A <= x['edge'] <= B)
    print('  〈前走が着外だった馬だけで〉ここがいちばん使える')
    sub = [x for x in P if not x['praw']]
    bb = 100 * sum(x['hit'] for x in sub) / len(sub)
    print(f'    前走着外ぜんぶ {bb:.1f}%（{len(sub)}頭）')
    qq = sorted(x['edge'] for x in sub)
    for lab, lo, hi in (('着外でズレ上位1/4', .75, 1.01), ('着外でズレ下位1/4', 0, .25)):
        a = qq[int(len(qq) * lo) - 1] if lo else qq[0]
        b = qq[min(int(len(qq) * hi), len(qq) - 1)]
        show(lab, lambda x, A=a, B=b: not x['praw'] and A <= x['edge'] <= B)
    print()
