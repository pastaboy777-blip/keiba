# -*- coding: utf-8 -*-
"""レーティング（未来の情報を入れない版）。

  python3 scripts/ana/rating2.py <区切り日YYYYMMDD> [場名...]

rating.py はレースの水準を全期間で決めていた。今日の水準が今日の結果から
決まるので、未来の情報が混ざる。%Early のときと同じ失敗。

ここでは日付順に進める。
  区切り日より前   繰り返しで水準をそろえる（ここは過去なので自由に使える）
  区切り日より後   1レースずつ日付順に
                    ① 出走馬の「それまでの点」だけで今日の相手関係を出す
                    ② その相手関係で当たるかを測る  ← 検証はここだけ
                    ③ 終わってから今日のレースに水準をつけ、点を記録する
                       （次のレースのためだけに使う）

相手関係 ＝ 出走馬それまでの点の中央値。これは前日に分かる。
格下げ   ＝ 前走の相手関係 − 今日の相手関係。これも前日に分かる。

【結果】区切り20260701・後1,104鞍で検証
点は効いた。これまでで最もきれいな材料。
  船橋 人気薄1,026頭（層10.8%・回収65%）
    点が上位1/5 18.8%・回収82%（+8.0pt）／下位1/5 4.4%・23%
  大井 人気薄2,340頭（層9.3%・回収62%）
    点が上位1/5 13.6%・回収57%（+4.4pt）／下位1/5 3.6%・48%
2場あわせて 点が上位1/5 × 6〜7番人気 で 22.1%・回収75%（+12.3pt）。
3着内率は層の2.3倍で最大。ただし回収は75%で止まる。これは南関の
払戻率とほぼ同じで、控除率を引く前の正しい値段に届いたところまで。
8番人気以降では効かない（船橋12.5%・大井7.0%）。効くのは6〜7番人気の帯。
馬場を足しても動かない（渋76%・良75%）。

格下げは落ちた。rating.py（全期間で水準を決める版）では船橋18.9%・
回収100%と出たが、前日に分かる情報だけにすると12.3%・回収62%でほぼ
消える。あれは未来の情報の混入だった。
枠と重ねても単体より落ちる（船橋 点上位1/5単体18.5% → 外1/3と重ねて17.3%）。
"""
import json, re, statistics as st, sys
from collections import defaultdict

CUT = sys.argv[1]
BA = sys.argv[2:] or ['船橋', '大井']
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
DIVF = {'船橋': 'div_funabashi.json', '大井': 'div_year.json'}


def sec(t):
    m = re.match(r'^(?:(\d+):)?(\d+)\.(\d)$', t.strip()) if t else None
    return None if not m else int(m.group(1) or 0) * 60 + int(m.group(2)) \
        + int(m.group(3)) / 10


R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R.sort(key=lambda r: (r['ymd'], r['rid']))

RAW = {}                                  # rid -> {馬名: 素点}
for r in R:
    if not r.get('dist'):
        continue
    ts = [(sec(e.get('tm')), e) for e in r['e'] if e.get('f', '').isdigit()]
    ts = [(t, e) for t, e in ts if t]
    if len(ts) < 4:
        continue
    twin = min(t for t, _ in ts)
    spl = 2.4 / (r['dist'] / twin)
    kgl = 1380 / r['dist']
    d = {}
    for t, e in ts:
        try:
            kin = float(e.get('kin') or 0)
        except ValueError:
            continue
        if kin <= 0:
            continue
        b = (t - twin) / spl
        if b <= 40:
            d[e['nm']] = kin - b * kgl
    if len(d) >= 4:
        RAW[r['rid']] = d

# ── 区切り日より前で、繰り返して水準をそろえる ──
pre = [r for r in R if r['ymd'] < CUT and r['rid'] in RAW]
off = defaultdict(float)
byh = defaultdict(list)
for r in pre:
    for nm in RAW[r['rid']]:
        byh[nm].append(r['rid'])
for _ in range(8):
    hr = {nm: st.mean(RAW[x][nm] + off[x] for x in v) for nm, v in byh.items()}
    for r in pre:
        rid = r['rid']
        off[rid] = st.median([hr[nm] - RAW[rid][nm] for nm in RAW[rid]
                              if nm in hr])
print(f'区切り {CUT}　前 {len(pre)}鞍で水準をそろえた'
      f'　後 {sum(1 for r in R if r["ymd"]>=CUT and r["rid"] in RAW)}鞍で検証')

PERF = defaultdict(list)                  # 馬 -> [(ymd, 点)]
for r in pre:
    for nm, v in RAW[r['rid']].items():
        PERF[nm].append((r['ymd'], v + off[r['rid']]))
for v in PERF.values():
    v.sort()

NR = {}                                    # 馬 -> それまでの走の数
STD = {}                                  # rid -> 相手関係（前日に分かる）
LASTR = {}                                 # 馬 -> 直前に出たrid
ROWS = []
for r in R:
    rid = r['rid']
    if rid not in RAW:
        continue
    # ① それまでの点だけで相手関係を出す
    cur = {}
    for nm in RAW[rid]:
        pv = [p for y, p in PERF.get(nm, []) if y < r['ymd']][-5:]
        if pv:
            cur[nm] = max(pv)
            NR[nm] = len(pv)
    std = st.median(cur.values()) if len(cur) >= 5 else None
    if std is not None:
        STD[rid] = std
    # ② 検証（区切り日より後だけ）
    if r['ymd'] >= CUT and std is not None and r['ba'] in BA:
        for e in r['e']:
            nm = e['nm']
            if not e.get('f', '').isdigit() or nm not in cur:
                continue
            pr = LASTR.get(nm)
            pstd = STD.get(pr) if pr else None
            pop = e.get('pop', '')
            ROWS.append(dict(ba=r['ba'], ymd=r['ymd'], R=r['R'],
                             u=int(e['u']), nm=nm,
                             hit=int(e['f']) <= 3,
                             pop=int(pop) if pop.isdigit() else None,
                             edge=cur[nm] - std,
                             dist=r['dist'], n=len(cur), nh=len(
                                 [y for y in r['e']
                                  if y.get('f', '').isdigit()]),
                             baba=r.get('baba'), nrun=NR.get(nm, 0),
                             drop=(pstd - std) if pstd is not None else None))
    # ③ 終わってから今日に水準をつけ、点を記録する
    if cur:
        o = st.median([cur[nm] - RAW[rid][nm] for nm in RAW[rid] if nm in cur])
    else:
        o = st.mean(off.values()) if off else 0.0
    for nm, v in RAW[rid].items():
        PERF[nm].append((r['ymd'], v + o))
        LASTR[nm] = rid
    for nm in RAW[rid]:
        PERF[nm].sort()

print()
for ba in BA:
    try:
        DIV = json.load(open(f'{SP}/{DIVF[ba]}', encoding='utf-8'))
    except Exception:
        DIV = {}
    for x in ROWS:
        if x['ba'] != ba:
            continue
        fk = dict((DIV.get(x['ymd'], {}).get(str(x['R']), {})).get('複勝', []))
        x['fuku'] = fk.get(str(x['u']), 0)
        x['has'] = bool(fk)
    P = [x for x in ROWS if x['ba'] == ba and x['pop'] and x['pop'] >= 6]
    if len(P) < 300:
        print(f'■ {ba} 材料不足（{len(P)}頭）\n')
        continue
    base = 100 * sum(x['hit'] for x in P) / len(P)
    d = [x for x in P if x.get('has')]
    br = f'　複勝の回収 {sum(x["fuku"] for x in d)/len(d):.0f}%' if d else ''
    print(f'■ {ba}　区切り後の人気薄 {len(P)}頭　3着内 {base:.1f}%{br}')

    def show(lab, f, mn=80):
        v = [x for x in P if f(x)]
        if len(v) < mn:
            print(f'    {lab:<26} 材料不足({len(v)})')
            return
        i = sum(x['hit'] for x in v)
        dd = [x for x in v if x.get('has')]
        roi = f'  回収 {sum(x["fuku"] for x in dd)/len(dd):5.0f}%' if dd else ''
        print(f'    {lab:<26} {100*i/len(v):5.1f}%{roi}  ({i}/{len(v)})'
              f' {100*i/len(v)-base:+5.1f}pt')

    print('  〈自分の点 − 相手関係〉')
    q = sorted(x['edge'] for x in P)
    for nm, lo, hi in (('上位1/5', .8, 1.01), ('2/5', .6, .8), ('3/5', .4, .6),
                       ('4/5', .2, .4), ('下位1/5', 0, .2)):
        a = q[int(len(q) * lo) - 1] if lo else q[0]
        b = q[min(int(len(q) * hi), len(q) - 1)]
        show(nm, lambda x, A=a, B=b: A <= x['edge'] <= B)
    dq = sorted(x['drop'] for x in P if x['drop'] is not None)
    if len(dq) >= 300:
        print('  〈格下げ　前走の相手関係 − 今日の相手関係〉')
        for nm, lo, hi in (('下げ幅 上位1/4', .75, 1.01), ('2/4', .5, .75),
                           ('3/4', .25, .5), ('下位1/4（格上げ）', 0, .25)):
            a = dq[int(len(dq) * lo) - 1] if lo else dq[0]
            b = dq[min(int(len(dq) * hi), len(dq) - 1)]
            show(nm, lambda x, A=a, B=b: x['drop'] is not None
                 and A <= x['drop'] <= B)
        print('  〈重ねる〉')
        e7 = q[int(len(q) * .7)]
        d7 = dq[int(len(dq) * .7)]
        show('点が上位3割', lambda x: x['edge'] >= e7)
        show('点が上位3割 × 格下げ上位3割',
             lambda x: x['edge'] >= e7 and x['drop'] is not None
             and x['drop'] >= d7, mn=40)
    print()
json.dump(ROWS, open(f'{SP}/rating2_rows.json', 'w', encoding='utf-8'),
          ensure_ascii=False)
