# -*- coding: utf-8 -*-
"""レーティング ── 全レースを1本の物差しに乗せる（ヨーロッパ式）。

  python3 scripts/ana/rating.py [場名...]

これまで作った指標は、どれもレースの中での相対だった。
  粘り              同じ鞍のほかの馬との比較
  Finishing Speed % そのレースの平均との比較
  Turn Time         その場その距離の水準との比較
  コーナーの動き      同じ鞍の中での位置
だから格の違う相手を比べられない。強い鞍の6着と弱い鞍の2着のどちらが
上かに答えられなかった。

Timeform／Racing Post Ratings のやり方はこう。
  その走の点 ＝ 背負った斤量 − 負けた馬身 × 1馬身あたりの斤量 ＋ そのレースの水準

負けた馬身は走破時計の差から出す（着差の表記より細かい）。
1馬身あたりの斤量は距離で変わる。短いほど1馬身が重い。
英国の目安（5F=3ポンド〜12F=1.25ポンド）をkgに直すと、おおよそ
1380÷距離。1200mで1.15kg、1600mで0.86kg、2000mで0.69kg。

そのレースの水準は、出走馬がほかの走で出している点から決める。
決めた水準で点を直し、直した点で水準をまた決める。これを繰り返すと
全レースが同じ物差しに乗る。

点が乗ると、いまは見えない材料が2つ出る。
  格下げ            強い鞍から弱い鞍に回ってきた馬
  点は高いのに人気がない馬
"""
import json, re, statistics as st, sys
from collections import defaultdict

BA = sys.argv[1:] or ['船橋', '大井']
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
DIVF = {'船橋': 'div_funabashi.json', '大井': 'div_year.json'}
IT = 8                      # 繰り返しの回数


def sec(t):
    m = re.match(r'^(?:(\d+):)?(\d+)\.(\d)$', t.strip()) if t else None
    return None if not m else int(m.group(1) or 0) * 60 + int(m.group(2)) \
        + int(m.group(3)) / 10


R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R.sort(key=lambda r: (r['ymd'], r['rid']))

# ── 1走ごとの素点 ──
RUN = []                                 # (rid, 馬名, ymd, 素点)
for r in R:
    if not r.get('dist'):
        continue
    ts = [(sec(e.get('tm')), e) for e in r['e'] if e.get('f', '').isdigit()]
    ts = [(t, e) for t, e in ts if t]
    if len(ts) < 4:
        continue
    twin = min(t for t, _ in ts)
    if twin <= 0:
        continue
    spl = 2.4 / (r['dist'] / twin)       # 1馬身あたりの秒数
    kgl = 1380 / r['dist']               # 1馬身あたりの斤量(kg)
    for t, e in ts:
        try:
            kin = float(e.get('kin') or 0)
        except ValueError:
            continue
        if kin <= 0:
            continue
        beaten = (t - twin) / spl
        if beaten > 40:                  # 大差は点にしない
            continue
        RUN.append([r['rid'], e['nm'], r['ymd'], kin - beaten * kgl])

print(f'素点が出た走 {len(RUN)}　馬 {len({x[1] for x in RUN})}頭')

byr = defaultdict(list)
byh = defaultdict(list)
for i, x in enumerate(RUN):
    byr[x[0]].append(i)
    byh[x[1]].append(i)

off = defaultdict(float)
for it in range(IT):
    # 馬ごとの点（水準をのせた素点の平均）
    hr = {}
    for nm, idx in byh.items():
        hr[nm] = st.mean(RUN[i][3] + off[RUN[i][0]] for i in idx)
    # レースの水準を、出走馬の点から決め直す
    mv = 0.0
    for rid, idx in byr.items():
        v = [hr[RUN[i][1]] - RUN[i][3] for i in idx]
        nw = st.median(v)
        mv = max(mv, abs(nw - off[rid]))
        off[rid] = nw
    print(f'  {it+1}回目　水準の動き最大 {mv:.3f}kg')

# ── 1走ごとの点が決まった ──
PERF = defaultdict(list)                 # 馬 -> [(ymd, 点, rid)]
for i, x in enumerate(RUN):
    PERF[x[1]].append((x[2], x[3] + off[x[0]], x[0]))
for v in PERF.values():
    v.sort()
LV = {rid: off[rid] for rid in byr}
allp = sorted(p for v in PERF.values() for _, p, _ in v)
print(f'\n点の広がり　下1/4 {allp[len(allp)//4]:.1f}　中央 '
      f'{allp[len(allp)//2]:.1f}　上1/4 {allp[3*len(allp)//4]:.1f}kg')
lv = sorted(LV.values())
print(f'レースの水準　下1/4 {lv[len(lv)//4]:+.1f}　中央 {lv[len(lv)//2]:+.1f}'
      f'　上1/4 {lv[3*len(lv)//4]:+.1f}kg')

json.dump({'off': {k: round(v, 3) for k, v in LV.items()},
           'perf': {k: [[a, round(b, 2), c] for a, b, c in v]
                    for k, v in PERF.items()}},
          open(f'{SP}/rating.json', 'w', encoding='utf-8'), ensure_ascii=False)

# ── 効くかを測る。使うのはその日より前の走だけ ──
print()
for ba in BA:
    try:
        DIV = json.load(open(f'{SP}/{DIVF[ba]}', encoding='utf-8'))
    except Exception:
        DIV = {}
    ROWS = []
    for r in R:
        if r['ba'] != ba or not r.get('dist'):
            continue
        fk = dict((DIV.get(r['ymd'], {}).get(str(r['R']), {})).get('複勝', []))
        # 出走馬それぞれの、その日より前の点
        cur = {}
        for e in r['e']:
            pv = [p for y, p, _ in PERF.get(e['nm'], []) if y < r['ymd']][-5:]
            if pv:
                cur[e['nm']] = (max(pv), st.mean(pv), len(pv))
        if len(cur) < 5:
            continue
        med = st.median(v[0] for v in cur.values())
        # 前走のレース水準（格下げを見る）
        for e in r['e']:
            if not e.get('f', '').isdigit() or e['nm'] not in cur:
                continue
            best, mean, nrun = cur[e['nm']]
            pr = [rid for y, _, rid in PERF.get(e['nm'], []) if y < r['ymd']]
            drop = (LV.get(pr[-1], 0) - LV.get(r['rid'], 0)) if pr else None
            pop = e.get('pop', '')
            ROWS.append(dict(hit=int(e['f']) <= 3,
                             pop=int(pop) if pop.isdigit() else None,
                             edge=best - med, mean_edge=mean - med,
                             drop=drop, nrun=nrun,
                             fuku=fk.get(str(int(e['u'])), 0), has=bool(fk)))
    P = [x for x in ROWS if x['pop'] and x['pop'] >= 6]
    if len(P) < 400:
        print(f'■ {ba} 材料不足（{len(P)}頭）\n')
        continue
    base = 100 * sum(x['hit'] for x in P) / len(P)
    d = [x for x in P if x['has']]
    print(f'■ {ba}　人気薄 {len(P)}頭　3着内 {base:.1f}%　'
          f'複勝の回収 {sum(x["fuku"] for x in d)/len(d):.0f}%')

    def show(lab, f, mn=120):
        v = [x for x in P if f(x)]
        if len(v) < mn:
            print(f'    {lab:<26} 材料不足({len(v)})')
            return
        i = sum(x['hit'] for x in v)
        dd = [x for x in v if x['has']]
        roi = f'  回収 {sum(x["fuku"] for x in dd)/len(dd):5.0f}%' if dd else ''
        print(f'    {lab:<26} {100*i/len(v):5.1f}%{roi}  ({i}/{len(v)})'
              f' {100*i/len(v)-base:+5.1f}pt')

    print('  〈自分の最高点 − 出走馬の中央〉')
    q = sorted(x['edge'] for x in P)
    for nm, lo, hi in (('上位1/5', .8, 1.01), ('2/5', .6, .8), ('3/5', .4, .6),
                       ('4/5', .2, .4), ('下位1/5', 0, .2)):
        a = q[int(len(q) * lo) - 1] if lo else q[0]
        b = q[min(int(len(q) * hi), len(q) - 1)]
        show(nm, lambda x, A=a, B=b: A <= x['edge'] <= B)
    print('  〈格下げ　前走のレース水準 − 今日のレース水準〉')
    dq = sorted(x['drop'] for x in P if x['drop'] is not None)
    for nm, lo, hi in (('下げ幅 上位1/4', .75, 1.01), ('2/4', .5, .75),
                       ('3/4', .25, .5), ('下位1/4（格上げ）', 0, .25)):
        a = dq[int(len(dq) * lo) - 1] if lo else dq[0]
        b = dq[min(int(len(dq) * hi), len(dq) - 1)]
        show(nm, lambda x, A=a, B=b: x['drop'] is not None and A <= x['drop'] <= B)
    print('  〈重ねる〉')
    e8 = q[int(len(q) * .7)]
    d7 = dq[int(len(dq) * .7)] if dq else 0
    show('点が上位3割', lambda x: x['edge'] >= e8)
    show('点が上位3割 × 格下げ上位3割',
         lambda x: x['edge'] >= e8 and x['drop'] is not None and x['drop'] >= d7,
         mn=60)
    print()
