# -*- coding: utf-8 -*-
"""突き合わせた動画解析の数値を、先に決めた4つの形で測る。

  python3 scripts/ana/gait_test.py <joined.jsonl> [--test 1234]

測る順は notes/live/2026-11-14/gait_join_plan.md に先に書いてある。
結果を見てから条件を選ばない。

  ① 速度依存の切り分け   同じ馬の速度違い2区間で、どの指標が動くか
  ② 位置との関係        同一レース内で、指標と4角順位の関係
  ③ 持ち越し           同じ馬の2走で、同じ値が出るか（自己相関）
  ④ 馬場との噛み合い     同じ馬の良と渋りで、相対的にどう変わるか

どれも母数が足りなければ「判定しない」と出す。無理に数字を出さない。
人気の帯をそろえた上振れptで見る。偽薬（馬番の偶奇）も必ず出す。
"""
import json
import statistics as st
import sys
from collections import defaultdict

SRC = sys.argv[1]
WHICH = sys.argv[sys.argv.index('--test') + 1] if '--test' in sys.argv else '1234'
D = [json.loads(l) for l in open(SRC, encoding='utf-8')]
M = [x for x in D if x['measured']]

SPEED_FREE = ('kakikomi', 'rhythm', 'arc_flat')      # 速度で割ってある／無次元
SPEED_DEP = ('stride', 'arc_fore', 'arc_hind', 'swing_hip', 'swing_fore')
ALL = SPEED_FREE + SPEED_DEP + ('reach', 'rider_shift')
MIN = 20                                              # これ未満は判定しない


def corr(a, b):
    n = len(a)
    if n < 3:
        return None
    ma, mb = st.mean(a), st.mean(b)
    s = st.pstdev(a) * st.pstdev(b)
    return (sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / n) / s if s else None


def have(k, S=None):
    return [x for x in (S if S is not None else M) if x.get(k) is not None]


print(f'■ 突き合わせ {len(D)}頭　うち測れた {len(M)}頭')
nm = len(D) - len(M)
if nm:
    a = [x for x in D if x['measured'] and x['f']], [x for x in D if not x['measured'] and x['f']]
    r = [100 * sum(1 for x in v if x['f'] <= 3) / len(v) if v else 0 for v in a]
    print(f'  測れなかった {nm}頭　3着内率  測れた {r[0]:.1f}% / 測れなかった {r[1]:.1f}%')
    print('  → 差が大きいなら「よく走った馬だから測れた」が混ざっている')
print()

# ── ① 速度依存の切り分け ──────────────────────────────
if '1' in WHICH:
    print('■ ① 速度依存の切り分け（同じ馬・同じレースの別区間）')
    g = defaultdict(list)
    for x in M:
        g[(x['rid'], x['u'])].append(x)
    pair = {k: v for k, v in g.items() if len(v) >= 2}
    if not pair:
        print('  区間が2つ以上ある馬がいない。判定しない\n')
    else:
        print(f'  {len(pair)}頭ぶん\n')
        print(f"  {'指標':<14}{'組':>4}{'差の中央値':>12}{'値の中央値':>12}{'変動率':>9}")
        for k in ALL:
            v = [(a, b) for a, b in
                 ((x[0].get(k), x[1].get(k)) for x in pair.values())
                 if a is not None and b is not None]
            if len(v) < 3:
                continue
            d = st.median(abs(a - b) for a, b in v)
            m = st.median(abs(a + b) / 2 for a, b in v)
            tag = ''
            if m:
                tag = '  ← 速度で動く' if d / m > .08 else '  ← 動かない'
            print(f'  {k:<14}{len(v):>4}{d:>12.3f}{m:>12.3f}'
                  f'{(100*d/m if m else 0):>8.1f}%{tag}')
        print()

# ── ② 位置との関係 ────────────────────────────────
if '2' in WHICH:
    print('■ ② 位置との関係（同一レース内で相対化）')
    byr = defaultdict(list)
    for x in M:
        if x.get('c4r'):
            byr[x['rid']].append(x)
    byr = {k: v for k, v in byr.items() if len(v) >= 3}
    print(f'  3頭以上測れた鞍 {len(byr)}　のべ {sum(len(v) for v in byr.values())}頭')
    if not byr:
        print('  判定しない\n')
    else:
        for k in ALL:
            xs, ys = [], []
            for v in byr.values():
                w = [x for x in v if x.get(k) is not None]
                if len(w) < 3:
                    continue
                mk = st.median(x[k] for x in w)
                mr = st.median(x['c4r'] for x in w)
                for x in w:                       # 鞍の中で中央値から引く
                    xs.append(x[k] - mk)
                    ys.append(x['c4r'] - mr)
            if len(xs) < MIN:
                print(f'  {k:<14}材料不足({len(xs)})')
                continue
            c = corr(xs, ys)
            print(f'  {k:<14}{len(xs):>4}頭  4角順位との相関 {c:+.3f}'
                  + ('  ← マイナスなら前にいる' if c is not None else ''))
        print()

# ── ③ 持ち越し ────────────────────────────────
if '3' in WHICH:
    print('■ ③ 持ち越し（同じ馬の2走で同じ値が出るか）')
    g = defaultdict(list)
    for x in M:
        g[x['nm']].append(x)
    seq = {k: sorted(v, key=lambda y: y['ymd']) for k, v in g.items() if len(v) >= 2}
    print(f'  2走以上測れた馬 {len(seq)}頭')
    if not seq:
        print('  判定しない\n')
    else:
        for k in ALL:
            xs, ys = [], []
            for v in seq.values():
                for i in range(len(v) - 1):
                    a, b = v[i].get(k), v[i + 1].get(k)
                    if a is not None and b is not None:
                        xs.append(a)
                        ys.append(b)
            if len(xs) < 5:
                print(f'  {k:<14}材料不足({len(xs)})')
                continue
            c = corr(xs, ys)
            tag = ''
            if c is not None:
                tag = ('  ← 馬の性質。前日に使える' if c >= .6 else
                       '  ← 弱いが使える' if c >= .3 else
                       '  ← その日の状態。前日には使えない')
            print(f'  {k:<14}{len(xs):>4}組  自己相関 {c:+.3f}{tag}')
        print('  （参考：ふだんの4角位置 → 次走の4角位置 は +0.29 だった）\n')

# ── ④ 馬場との噛み合い ───────────────────────────
if '4' in WHICH:
    print('■ ④ 馬場との噛み合い（同じ馬の良と渋りを比べる）')
    WET, DRY = ('重', '不良'), ('良', '稍重')

    def band(x):
        return 'wet' if x.get('baba') in WET else ('dry' if x.get('baba') in DRY else None)
    g = defaultdict(lambda: {'wet': [], 'dry': []})
    for x in M:
        b = band(x)
        if b and x.get('f') and x.get('n'):
            g[x['nm']][b].append(x)
    both = {k: v for k, v in g.items() if v['wet'] and v['dry']}
    print(f'  良と渋りの両方で測れた馬 {len(both)}頭')
    if len(both) < MIN:
        print(f'  {MIN}頭未満なので判定しない（目安：向きが見える20頭・判定100頭）\n')
    else:
        def rel(S):           # 正規化着順。0が1着・1.00が最下位
            return st.mean((x['f'] - 1) / (x['n'] - 1) for x in S if x['n'] > 1)
        for k in SPEED_FREE:
            v = [(st.median([y[k] for y in u['wet'] + u['dry'] if y.get(k) is not None]),
                  rel(u['wet']) - rel(u['dry']))
                 for u in both.values()
                 if any(y.get(k) is not None for y in u['wet'] + u['dry'])]
            v = [(a, b) for a, b in v if a is not None]
            if len(v) < MIN:
                print(f'  {k:<14}材料不足({len(v)})')
                continue
            c = corr([a for a, _ in v], [b for _, b in v])
            print(f'  {k:<14}{len(v):>4}頭  相関 {c:+.3f}'
                  '  ← マイナスなら、値が高い馬ほど渋りで良くなる')
        print()

# ── 偽薬 ────────────────────────────────────
print('■ 偽薬（馬番の偶奇。関係ない割り方で差が出ないか）')
for t, f in (('奇数番', lambda x: x['u'] % 2 == 1), ('偶数番', lambda x: x['u'] % 2 == 0)):
    S = [x for x in M if f(x) and x.get('f')]
    if len(S) < 10:
        print(f'  {t:<8}材料不足({len(S)})')
        continue
    print(f'  {t:<8}{len(S):>4}頭  3着内 {100*sum(1 for x in S if x["f"]<=3)/len(S):5.1f}%')
print('  ここに差が出るなら、上の数字も割り方のゆらぎの範囲。')
