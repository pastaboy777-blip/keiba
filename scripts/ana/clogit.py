# -*- coding: utf-8 -*-
"""条件付きロジット ── 鞍のなかで正規化して当てはめる。

  python3 scripts/ana/clogit.py [場名...]

いままでの作りは「絶対値を出してから並べ替える」だった。最後の一歩で
相対性を捨てている。レーティングの「出走馬の中央との差」も、絶対値を
作ってから後づけで引いているだけ。

条件付きロジットは当てはめの段階で鞍のなかで正規化する。

  P(その馬が勝つ) = exp(x·β) / Σ_鞍の全馬 exp(x·β)

分母が鞍ごとなので、βは「速い馬とは何か」ではなく「この相手に勝つとは
何か」を学ぶ。ベンターがこれを使ったのは、競馬が相対的な競技だから。

同じ材料で2つ作って比べる。差は相対性を当てはめに入れたかどうかだけ。
  (A) 絶対値を出して並べ替える（レーティングと同じ作り）
  (B) 条件付きロジット

前半で作って後半で試す。人気は入れない（まず能力側だけで作る。
市場を混ぜるのはベンターの2段目で、それは次の話）。

【結果：勝たなかった】後半の人気薄2,813頭（層9.3%・回収63%）
  (A) 絶対値を並べ替え      上位1/5 13.2%・回収72% ／ 下位1/5 6.2%
  (B) 1着を正解            上位1/5 12.6%・回収64%
  (B) 3着内を正解          上位1/5 11.6%・回収60%
  (B) 3着内＋区切りつき      上位1/5 12.9%・回収65%
どれも(A)に届かない。

【なぜか】
① 条件付きロジットは鞍のなかの差しか使わない。(A)も鞍のなかで並べる。
   構造としては同じで、違いは重みをどう決めたかだけ。418鞍では
   当てはめのほうが不利になる。
② 材料が能力中心だと、相対的に当てはめても中身は能力モデルのまま。
   相対的なのは並べ方ではなく材料そのもの。
③ 重みを見ると mean+0.69・best+0.39 に対し a0+0.07・a1+0.07。
   能力が展開の8倍。そして能力はすでに値段に入っている。

【途中で2つ間違えた。記録として残す】
・最初の版で me（ふだんの位置）と ahead（前に行く馬の数）を両方入れた。
  ほぼ同じことを測るので共線性が出て、me -0.921／ahead +0.881 という
  符号が逆の大きな重みが並んだ。これを見て「展開が能力より大きい」と
  読んだが、片方を外すと ahead は +0.047 に縮む。全部共線性だった。
・1着を正解にして当てはめ、3着内で採点していた。前に行く馬の数は
  1着と3着内で向きが逆（前に0頭 1着2.5%・3着内11.6% ／ 前に1頭
  1着1.6%・3着内15.5%）。噛み合っていなかった。正解を3着内に
  そろえると a1 が -0.003 から +0.072 に反転して、正しく動いた。

【分かったこと】
ahead は山型（0頭11.6%・1頭15.5%・2頭13.0%・3頭以上9.9%）なので、
直線の重みでは表せない。区切りにして初めて乗る。
相対的な材料は、直線のモデルに素直に入らない形をしていることがある。
"""
import datetime as dt
import json, re, statistics as st, sys
from collections import defaultdict
import numpy as np

BA = sys.argv[1:] or ['船橋', '大井']
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
CUT = '20260701'
DIVF = {'船橋': 'div_funabashi.json', '大井': 'div_year.json'}


def sec(t):
    m = re.match(r'^(?:(\d+):)?(\d+)\.(\d)$', t.strip()) if t else None
    return None if not m else int(m.group(1) or 0) * 60 + int(m.group(2)) \
        + int(m.group(3)) / 10


R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R.sort(key=lambda r: (r['ymd'], r['rid']))

# ── レーティング（絶対値）を日付順に作る ──
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
pre = [r for r in R if r['ymd'] < CUT and r['rid'] in RAW]
off = defaultdict(float)
byh = defaultdict(list)
for r in pre:
    for nm in RAW[r['rid']]:
        byh[nm].append(r['rid'])
for _ in range(8):
    hr = {nm: st.mean(RAW[x][nm] + off[x] for x in v) for nm, v in byh.items()}
    for r in pre:
        off[r['rid']] = st.median([hr[nm] - RAW[r['rid']][nm]
                                   for nm in RAW[r['rid']] if nm in hr])
PERF = defaultdict(list)
for r in pre:
    for nm, v in RAW[r['rid']].items():
        PERF[nm].append((r['ymd'], v + off[r['rid']]))
for v in PERF.values():
    v.sort()

# ── 鞍ごとに材料をそろえる ──
POS = defaultdict(list)
LAST = {}
RACES = []
for r in R:
    rid = r['rid']
    n = len([e for e in r['e'] if e.get('f', '').isdigit()])
    fk = dict((json.load(open(f'{SP}/{DIVF[r["ba"]]}', encoding='utf-8'))
               if False else {}).get('x', {}))
    cur, me = {}, {}
    for e in r['e']:
        pv = [p for y, p in PERF.get(e['nm'], []) if y < r['ymd']][-5:]
        if pv:
            cur[e['nm']] = (max(pv), st.mean(pv), len(pv))
        v = [p for y, p in POS.get(e['nm'], []) if y < r['ymd']][-5:]
        if len(v) >= 3:
            me[e['nm']] = st.median(v)
    if r['ba'] in BA and len(cur) >= 6 and len(me) >= 5 and n >= 6:
        rows = []
        for e in r['e']:
            nm = e['nm']
            if not e.get('f', '').isdigit() or nm not in cur or nm not in me:
                continue
            u = int(e['u'])
            pv = LAST.get(nm)
            gap = None
            if pv:
                a = dt.date(int(pv[0][:4]), int(pv[0][4:6]), int(pv[0][6:]))
                b = dt.date(int(r['ymd'][:4]), int(r['ymd'][4:6]),
                            int(r['ymd'][6:]))
                gap = (b - a).days
            try:
                kin = float(e.get('kin') or 0)
            except ValueError:
                kin = 0
            try:
                dw = float((e.get('dw') or '0').replace('+', '') or 0)
            except ValueError:
                dw = 0
            pop = e.get('pop', '')
            rows.append(dict(
                nm=nm, u=u, f=int(e['f']),
                pop=int(pop) if pop.isdigit() else None,
                best=cur[nm][0], mean=cur[nm][1], nrun=cur[nm][2],
                me=me[nm], pos=(u - 1) / (n - 1) if n > 1 else .5,
                kin=kin, dw=dw, gap=gap if gap else 30,
                same=1.0 if (pv and pv[1] == r['ba']) else 0.0))
        if len(rows) >= 6:
            ahead = {x['nm']: sum(1 for y in rows if y['me'] < x['me'])
                     for x in rows}
            for x in rows:
                a = ahead[x['nm']]
                x['ahead'] = a
                # 山型なので区切りにする。直線の重みでは乗らない
                x['a0'] = 1.0 if a == 0 else 0.0
                x['a1'] = 1.0 if a == 1 else 0.0
                x['a2'] = 1.0 if a == 2 else 0.0
                x['a3'] = 1.0 if a >= 3 else 0.0
            RACES.append(dict(rid=rid, ba=r['ba'], ymd=r['ymd'], R=r['R'],
                              n=len(rows), rows=rows))
    c4 = r.get('c4') or []
    if c4:
        p = {u: (i + 1) / len(c4) for i, u in enumerate(c4)}
        for e in r['e']:
            if int(e['u']) in p:
                POS[e['nm']].append((r['ymd'], p[int(e['u'])]))
    for e in r['e']:
        LAST[e['nm']] = (r['ymd'], r['ba'])

DIV = {}
for ba, fn in DIVF.items():
    try:
        DIV[ba] = json.load(open(f'{SP}/{fn}', encoding='utf-8'))
    except Exception:
        pass
for rc in RACES:
    fk = dict((DIV.get(rc['ba'], {}).get(rc['ymd'], {})
               .get(str(rc['R']), {})).get('複勝', []))
    for x in rc['rows']:
        x['fuku'] = fk.get(str(x['u']), 0)
        x['has'] = bool(fk)

import os
# me と ahead はほぼ同じことを測るので片方だけにする（共線性）
FEAT = (os.environ.get('FEAT') or
        'best,mean,ahead,pos,kin,dw,gap,same,nrun').split(',')
TGT = os.environ.get('TGT', 'win')      # win: 1着だけ / top3: 3着内を正解に
print(f'鞍 {len(RACES)}　材料 {FEAT}')


def X(rows):
    return np.array([[float(x[f]) for f in FEAT] for x in rows])


A = [rc for rc in RACES if rc['ymd'] < CUT]
B = [rc for rc in RACES if rc['ymd'] >= CUT]
print(f'前半 {len(A)}鞍 / 後半 {len(B)}鞍')
allX = np.vstack([X(rc['rows']) for rc in A])
mu, sd = allX.mean(0), allX.std(0) + 1e-9


def fit(races, iters=400, lr=0.3, l2=1e-3):
    """条件付きロジット。鞍ごとに正規化した尤度を最大化する"""
    b = np.zeros(len(FEAT))
    Xs = [(X(rc['rows']) - mu) / sd for rc in races]
    if TGT == 'top3':
        # 3着内を正解にする。鞍ごとに合計1になるようにならす
        ys = []
        for rc in races:
            y = np.array([1.0 if x['f'] <= 3 else 0.0 for x in rc['rows']])
            ys.append(y / max(1.0, y.sum()))
    else:
        ys = [np.array([1.0 if x['f'] == 1 else 0.0 for x in rc['rows']])
              for rc in races]
    for it in range(iters):
        g = np.zeros(len(FEAT))
        for x, y in zip(Xs, ys):
            s = x @ b
            s -= s.max()
            p = np.exp(s)
            p /= p.sum()
            g += x.T @ (y - p)
        g = g / len(races) - l2 * b
        b += lr * g
    return b


b = fit(A)
print('\n■ 条件付きロジットの重み（鞍のなかで正規化して当てはめた）')
for f, w in sorted(zip(FEAT, b), key=lambda y: -abs(y[1])):
    print(f'    {f:<8}{w:+7.3f}')

# ── 後半で比べる ──
rowsB = []
for rc in B:
    x = (X(rc['rows']) - mu) / sd
    s = x @ b
    sc = {rc['rows'][i]['nm']: s[i] for i in range(len(rc['rows']))}
    med = st.median([r_['best'] for r_ in rc['rows']])
    o1 = sorted(rc['rows'], key=lambda y: -(y['best'] - med))
    o2 = sorted(rc['rows'], key=lambda y: -sc[y['nm']])
    for i, y in enumerate(o1):
        y['rkA'] = (i + 1) / len(o1)
    for i, y in enumerate(o2):
        y['rkB'] = (i + 1) / len(o2)
    rowsB += rc['rows']
P = [x for x in rowsB if x['pop'] and x['pop'] >= 6]
base = 100 * sum(1 for x in P if x['f'] <= 3) / len(P)
d = [x for x in P if x['has']]
print(f'\n■ 後半の人気薄 {len(P)}頭　3着内 {base:.1f}%　'
      f'複勝の回収 {sum(x["fuku"] for x in d)/len(d):.0f}%')
for key, lab in (('rkA', '(A) 絶対値を出して並べ替える'),
                 ('rkB', '(B) 条件付きロジット')):
    print(f'  〈{lab}〉')
    for nm, lo, hi in (('上位1/5', 0, .2), ('2/5', .2, .4), ('3/5', .4, .6),
                       ('4/5', .6, .8), ('下位1/5', .8, 1.01)):
        v = [x for x in P if lo < x[key] <= hi]
        if len(v) < 80:
            continue
        i = sum(1 for x in v if x['f'] <= 3)
        dd = [x for x in v if x['has']]
        roi = sum(x['fuku'] for x in dd) / len(dd) if dd else 0
        print(f'    {nm:<8}{len(v):>5}頭 {100*i/len(v):5.1f}%  回収{roi:5.0f}%'
              f' {100*i/len(v)-base:+5.1f}pt')
