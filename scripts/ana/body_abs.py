# -*- coding: utf-8 -*-
"""馬体重そのもの・鞍の中での相対体重・負担率を回収率で測る。

  python3 -I scripts/ana/body_abs.py [body.jsonl]

測る形は先に7つ決めてある（増やさない）。
  ① 絶対体重5帯 × 人気薄
  ② wt_norm 3帯 × 人気薄
  ③ wt_med 3帯 × 人気薄
  ④ load 3帯（三分位は分布から出す）× 人気薄
  ⑤ ②を場ごと
  ⑥ ② × hp（ふだんの4角位置が上位1/3・hn>=3）
  ⑦ 絶対体重と wt_norm の相関（共線性の確認）

nankan_body.py の load_body / ev / show / placebo / by_pop をそのまま使う。
結合は書き直さない。単勝回収が層を30pt以上超えた形だけ、偽薬5回と
人気帯そろえを追加で出す。
"""
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nankan_body import (BODY, HP_MIN, MIN_N, by_pop, ev, load_body,  # noqa
                         placebo, show)

EXCESS = 30.0          # 層の単勝回収をこれ以上超えたら追加検証にかける


# ── 表示 ──────────────────────────────────────────────────────
def q(v):
    return f'{v:.1f}' if v is not None else '―'


def row(S, label, mid, ref=None):
    """1行出して ev を返す。ref（層の単勝回収）を超えた幅も出す。"""
    o = ev(S, mid)
    if o['short']:
        print(f'  {label:<22}{o["n"]:>5}頭　母数不足。判定しない')
        return o
    s = (f'  {label:<22}{o["n"]:>5}頭　3着内{o["top3"]:>5.1f}%　'
         f'1着{o["win"]:>4.1f}%　単{o["tan"]:>6.1f}%　複{o["fuku"]:>6.1f}%　'
         f'｜前半{o["a_n"]:>4}頭 単{q(o["a_tan"]):>6}/複{q(o["a_fuku"]):>5}　'
         f'後半{o["b_n"]:>4}頭 単{q(o["b_tan"]):>6}/複{q(o["b_fuku"]):>5}　'
         f'｜最大1頭({o["nomax"]:>6,.0f}円)抜き 単{o["tan_nomax"]:>6.1f}%')
    if ref is not None:
        o['excess'] = o['tan'] - ref
        s += f'　｜層差 {o["excess"]:+.1f}pt'
    print(s)
    return o


def winners(S):
    """1着馬を払戻の高い順に。(払戻, 識別子) の列。"""
    return sorted(((x.get('ptan') or 0),
                   f'{x["ymd"]}{x["rid"]}-{x["u"]}', x['nm'])
                  for x in S if x['f'] == 1)[::-1]


def conc(S, pool, label, ref_label):
    """該当と層の両方の上位払戻を並べ、同じ馬が効いていないか確かめる。

    CLAUDE.md「単勝回収は分散が大きい」。該当だけ上位を抜いても、層の側も
    同じ馬で出来ていれば、超えて見えるのは層の集中が該当に写っているだけ。
    単勝回収が層を超えた形では必ずこれを通す。
    """
    print(f'\n   ◆集中度：該当と層の上位払戻が同じ馬かどうか')
    rec = {}
    for nm_, T in ((f'該当（{label}）', S), (f'層（{ref_label}）', pool)):
        w = winners(T)
        tot = sum(v for v, _, _ in w)
        print(f'     {nm_}　{len(T)}頭　1着{len(w)}頭　単{tot/len(T):.1f}%')
        s = []
        for k in (1, 2, 3):
            if len(w) > k:
                s.append(f'上位{k}頭抜き {(tot-sum(v for v,_,_ in w[:k]))/len(T):.1f}%')
        print('       ' + '　'.join(s))
        print('       上位3頭の払戻：'
              + ' / '.join(f'{v:,.0f}円({nm})' for v, _, nm in w[:3]))
        rec[nm_] = {i for _, i, _ in w[:3]}
    a, b = list(rec.values())
    same = a & b
    print(f'     上位3頭のうち該当と層で同じ馬：{len(same)}頭')
    if same:
        print('     → 層が高いこと自体がその馬で出来ており、該当はそれを'
              '含んでいるだけ、という形になりうる')
    # 公平な抜き方：該当の上位3頭を「該当からも層からも」抜く。
    # 該当から3頭だけ抜いて層は丸ごとのまま比べると、分母が違うので
    # 同じ1頭が該当では大きく層では小さく効き、該当だけが不利になる。
    print('     同じ馬を該当と層の両方から抜いて比べる（分母はそのまま）')
    ids = {i for _, i, _ in winners(S)[:3]}
    for nm_, T in ((f'該当', S), (f'層', pool)):
        w = winners(T)
        tot = sum(v for v, _, _ in w)
        cut = sum(v for v, i, _ in w if i in ids)
        print(f'       {nm_}　抜く前 {tot/len(T):>6.1f}%　'
              f'該当の上位3頭を抜くと {(tot-cut)/len(T):>6.1f}%'
              f'（抜けた払戻 {cut:,.0f}円 / {len(T)}頭）')


def deep(S, pool, label, mid, ref_label):
    """層を30pt以上超えた形だけ。偽薬5回・人気帯そろえ・集中度。"""
    print(f'\n  ◆追加検証：{label}（層は{ref_label}）')
    print('   偽薬（同じ鞍から同数を無作為に5回）')
    ts = []
    for i, o in enumerate(placebo(S, pool, k=5, mid=mid), 1):
        if o['short']:
            print(f'     {i}回目　{o["n"]}頭　母数不足。判定しない')
            continue
        ts.append(o['tan'])
        print(f'     {i}回目　{o["n"]:>5}頭　単{o["tan"]:>6.1f}%　'
              f'複{o["fuku"]:>6.1f}%　最大1頭抜き 単{o["tan_nomax"]:>6.1f}%')
    if ts:
        print(f'     偽薬の幅　単{min(ts):.1f}〜{max(ts):.1f}%')
    # 5回では偽薬自身の散らばりが分からない。同じ検定の回数だけ増やす
    # （新しい条件を試すのではないので、探し回ることにはならない）。
    big = [o['tan'] for o in placebo(S, pool, k=200, mid=mid)
           if not o['short']]
    if big:
        big.sort()
        obs = ev(S, mid)['tan']
        over = sum(1 for v in big if v >= obs)
        print(f'   偽薬を200回に増やす　単の分布 '
              f'最小{big[0]:.1f} / 5%点{big[len(big)//20]:.1f} / '
              f'中央{big[len(big)//2]:.1f} / '
              f'95%点{big[int(len(big)*0.95)]:.1f} / 最大{big[-1]:.1f}%')
        print(f'     該当の{obs:.1f}%以上が出た偽薬 {over}/{len(big)}回'
              f'（{over/len(big)*100:.1f}%）')
    print('   人気帯をそろえる')
    for lab, a, b in by_pop(S, pool, mid=mid):
        def fmt(o):
            if o['short']:
                return f'{o["n"]:>5}頭　母数不足'
            return (f'{o["n"]:>5}頭　3着内{o["top3"]:>5.1f}%　'
                    f'単{o["tan"]:>6.1f}%　複{o["fuku"]:>6.1f}%')
        print(f'     {lab:<12}該当 {fmt(a)}')
        print(f'     {"":<12}層　 {fmt(b)}')
    conc(S, pool, label, ref_label)


def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx, my = st.fmean(xs), st.fmean(ys)
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    return sxy / (sxx * syy) ** 0.5 if sxx and syy else None


# ── 帯の定義（先に決める。結果を見てから動かさない）────────────
WT_BANDS = (('〜429kg', lambda v: v <= 429),
            ('430〜459kg', lambda v: 430 <= v <= 459),
            ('460〜489kg', lambda v: 460 <= v <= 489),
            ('490〜519kg', lambda v: 490 <= v <= 519),
            ('520kg〜', lambda v: v >= 520))

NORM_BANDS = (('軽い側1/3', lambda v: v < 1 / 3),
              ('中1/3', lambda v: 1 / 3 <= v <= 2 / 3),
              ('重い側1/3', lambda v: v > 2 / 3))

MED_BANDS = (('−15kg以下', lambda v: v <= -15),
             ('−14〜+14kg', lambda v: -15 < v < 15),
             ('+15kg以上', lambda v: v >= 15))


def main(path=BODY):
    rows, mid = load_body(path)
    pool = [x for x in rows if x['ptan'] is not None and x['n'] >= 6]
    light = [x for x in pool if x['pop'] >= 6]
    print(f'{len(rows)}頭を読んだ　前半／後半の境目 {mid}')
    print(f'層：南関4場 {len(pool)}頭　人気薄(6番人気以降) {len(light)}頭')
    ref_all = sum(x['ptan'] for x in pool) / len(pool)
    ref = sum(x['ptan'] for x in light) / len(light)
    print(f'  南関4場 単{ref_all:.1f}%　人気薄 単{ref:.1f}%')
    todo = []            # (ラベル, 該当, 比べる母集団, 層の名前)

    # ───────────────────────────────────────────────────────────
    print('\n' + '=' * 78)
    print('① 絶対体重5帯 × 人気薄（層 単%.1f%%）' % ref)
    print('=' * 78)
    for lab, fn in WT_BANDS:
        S = [x for x in light if x['wt'] is not None and fn(x['wt'])]
        o = row(S, lab, mid, ref)
        if not o['short'] and o['tan'] - ref >= EXCESS:
            todo.append((f'① {lab} × 人気薄', S, light, '人気薄'))

    print('\n（参考：人気を絞らない南関4場全体。層 単%.1f%%）' % ref_all)
    for lab, fn in WT_BANDS:
        S = [x for x in pool if x['wt'] is not None and fn(x['wt'])]
        row(S, lab, mid, ref_all)

    # ───────────────────────────────────────────────────────────
    print('\n' + '=' * 78)
    print('② wt_norm 3帯 × 人気薄（層 単%.1f%%）' % ref)
    print('=' * 78)
    for lab, fn in NORM_BANDS:
        S = [x for x in light if x['wt_norm'] is not None and fn(x['wt_norm'])]
        o = row(S, lab, mid, ref)
        if not o['short'] and o['tan'] - ref >= EXCESS:
            todo.append((f'② {lab} × 人気薄', S, light, '人気薄'))

    print('\n（参考：人気を絞らない南関4場全体。層 単%.1f%%）' % ref_all)
    for lab, fn in NORM_BANDS:
        S = [x for x in pool if x['wt_norm'] is not None and fn(x['wt_norm'])]
        row(S, lab, mid, ref_all)

    # ───────────────────────────────────────────────────────────
    print('\n' + '=' * 78)
    print('③ wt_med 3帯 × 人気薄（層 単%.1f%%）' % ref)
    print('=' * 78)
    for lab, fn in MED_BANDS:
        S = [x for x in light if x['wt_med'] is not None and fn(x['wt_med'])]
        o = row(S, lab, mid, ref)
        if not o['short'] and o['tan'] - ref >= EXCESS:
            todo.append((f'③ {lab} × 人気薄', S, light, '人気薄'))

    # ───────────────────────────────────────────────────────────
    print('\n' + '=' * 78)
    print('④ load（負担率）3帯 × 人気薄（層 単%.1f%%）' % ref)
    print('=' * 78)
    ld = sorted(x['load'] for x in pool if x['load'] is not None)
    k1 = ld[len(ld) // 3]
    k2 = ld[len(ld) * 2 // 3]
    print(f'  三分位は南関4場 {len(ld)}頭の分布から出す：'
          f'{k1:.2f} / {k2:.2f}（最小{ld[0]:.2f} 中央{st.median(ld):.2f} '
          f'最大{ld[-1]:.2f}）')
    LOAD_BANDS = ((f'軽い（〜{k1:.2f}）', lambda v: v < k1),
                  (f'中（{k1:.2f}〜{k2:.2f}）', lambda v: k1 <= v < k2),
                  (f'重い（{k2:.2f}〜）', lambda v: v >= k2))
    for lab, fn in LOAD_BANDS:
        S = [x for x in light if x['load'] is not None and fn(x['load'])]
        o = row(S, lab, mid, ref)
        if not o['short'] and o['tan'] - ref >= EXCESS:
            todo.append((f'④ {lab} × 人気薄', S, light, '人気薄'))

    print('\n（参考：人気を絞らない南関4場全体。層 単%.1f%%）' % ref_all)
    for lab, fn in LOAD_BANDS:
        S = [x for x in pool if x['load'] is not None and fn(x['load'])]
        row(S, lab, mid, ref_all)

    # ───────────────────────────────────────────────────────────
    print('\n' + '=' * 78)
    print('⑤ ②を場ごと（層はその場の人気薄）')
    print('=' * 78)
    for ba in ('川崎', '大井', '船橋', '浦和'):
        B = [x for x in light if x['ba'] == ba]
        rb = sum(x['ptan'] for x in B) / len(B)
        print(f'\n  ── {ba}　人気薄 {len(B)}頭　層 単{rb:.1f}% ──')
        for lab, fn in NORM_BANDS:
            S = [x for x in B if x['wt_norm'] is not None and fn(x['wt_norm'])]
            o = row(S, lab, mid, rb)
            if not o['short'] and o['tan'] - rb >= EXCESS:
                todo.append((f'⑤ {ba} {lab} × 人気薄', S, B, f'{ba}の人気薄'))

    # ── 照合：帯の境目の取り方で頭数が変わる ──────────────────
    # 本稿の「軽い側1/3」は wt_norm < 1/3（境目の値を含めない）。
    # wt_norm = i/(k-1) なので、完走13頭の鞍では i=4 がちょうど 1/3 になり、
    # 含めるか含めないかで頭数が動く。両方出して並べる。
    print('\n  ── 照合：軽い側1/3の境目の取り方 ──')
    print('   本稿の定義は wt_norm < 1/3（ちょうど 1/3 の馬を入れない）。')
    print('   wt_norm は鞍の中の順位を 0〜1 に伸ばした値 i/(完走頭数-1) なので、')
    print('   完走13頭の鞍では i=4 がちょうど 1/3 になり、境目に馬が乗る。')
    for ba in ('浦和', '川崎', '大井', '船橋'):
        B = [x for x in light if x['ba'] == ba]
        rb = sum(x['ptan'] for x in B) / len(B)
        print(f'\n   {ba}（人気薄 {len(B)}頭　層 単{rb:.1f}%）')
        for lab, fn in (('wt_norm < 1/3 （本稿）', lambda v: v < 1 / 3),
                        ('wt_norm <= 1/3', lambda v: v <= 1 / 3)):
            S = [x for x in B if x['wt_norm'] is not None and fn(x['wt_norm'])]
            row(S, lab, mid, rb)
        eq = [x for x in B if x['wt_norm'] is not None
              and abs(x['wt_norm'] - 1 / 3) < 1e-9]
        print(f'     ちょうど wt_norm = 1/3 の馬 {len(eq)}頭'
              + (f'（1着{sum(1 for x in eq if x["f"]==1)}頭　'
                 f'単{sum(x["ptan"] for x in eq)/len(eq):.1f}%）' if eq else ''))
        v = sorted(x['wt_norm'] for x in B if x['wt_norm'] is not None)
        print(f'     この場の wt_norm の実測三分位：'
              f'{v[len(v)//3]:.4f} / {v[len(v)*2//3]:.4f}')

    # ── 照合：場の層そのものの集中度 ─────────────────────────
    # 浦和の層93.3%が高いこと自体が少数の馬で出来ていないか。
    print('\n  ── 照合：場ごとの人気薄の層そのものの集中度 ──')
    for ba in ('川崎', '大井', '船橋', '浦和'):
        B = [x for x in light if x['ba'] == ba]
        w = winners(B)
        tot = sum(v for v, _, _ in w)
        s = '　'.join(f'上位{k}頭抜き {(tot-sum(v for v,_,_ in w[:k]))/len(B):>5.1f}%'
                      for k in (1, 2, 3))
        print(f'   {ba}　{len(B):>5}頭　1着{len(w):>3}頭　単{tot/len(B):>6.1f}%'
              f'　{s}')
        print(f'        上位3頭の払戻：'
              + ' / '.join(f'{v:,.0f}円' for v, _, _ in w[:3]))

    # ───────────────────────────────────────────────────────────
    print('\n' + '=' * 78)
    print('⑥ ② × hp（ふだんの4角位置が上位1/3・hn>=3）')
    print('=' * 78)
    hpf = [x for x in light if x['hn'] >= HP_MIN and x['hp'] is not None
           and x['hp'] <= 1 / 3]
    rh = sum(x['ptan'] for x in hpf) / len(hpf)
    print(f'\n  ── 南関4場 人気薄 × hp<=1/3 ──')
    row(hpf, 'hp<=1/3（体重で割らない）', mid, ref)
    print(f'  この群を層として wt_norm で割る（層 単{rh:.1f}%）')
    for lab, fn in NORM_BANDS:
        S = [x for x in hpf if x['wt_norm'] is not None and fn(x['wt_norm'])]
        o = row(S, lab, mid, rh)
        if not o['short'] and o['tan'] - rh >= EXCESS:
            todo.append((f'⑥ 南関 hp<=1/3 × {lab}', S, hpf, 'hp<=1/3の人気薄'))

    kw = [x for x in light if x['ba'] == '川崎']
    kwh = [x for x in kw if x['hn'] >= HP_MIN and x['hp'] is not None
           and x['hp'] <= 1 / 3]
    rkh = sum(x['ptan'] for x in kwh) / len(kwh)
    print(f'\n  ── 川崎 人気薄 × hp<=1/3（既知の251頭）──')
    row(kwh, 'hp<=1/3（体重で割らない）', mid,
        sum(x['ptan'] for x in kw) / len(kw))
    print(f'  この群を層として wt_norm で割る（層 単{rkh:.1f}%）')
    for lab, fn in NORM_BANDS:
        S = [x for x in kwh if x['wt_norm'] is not None and fn(x['wt_norm'])]
        o = row(S, lab, mid, rkh)
        if not o['short'] and o['tan'] - rkh >= EXCESS:
            todo.append((f'⑥ 川崎 hp<=1/3 × {lab}', S, kwh, '川崎のhp<=1/3'))

    # 重なりを見る：hp<=1/3 の馬は体重のどこにいるか
    print('\n  ── 重なりの確認：hp<=1/3 の馬の wt_norm の分布 ──')
    hp3 = [x for x in light if x['hn'] >= HP_MIN and x['hp'] is not None]
    for lab, fn in NORM_BANDS:
        a = [x for x in hpf if x['wt_norm'] is not None and fn(x['wt_norm'])]
        b = [x for x in hp3 if x['wt_norm'] is not None and fn(x['wt_norm'])]
        print(f'    {lab:<12}hp<=1/3 {len(a):>5}頭 {len(a)/len(hpf)*100:>5.1f}%'
              f'　／ hpが出せた全馬 {len(b):>5}頭 {len(b)/len(hp3)*100:>5.1f}%')
    xs = [x['hp'] for x in hp3 if x['wt_norm'] is not None]
    ys = [x['wt_norm'] for x in hp3 if x['wt_norm'] is not None]
    print(f'    hp と wt_norm の相関 r={pearson(xs, ys):+.4f}（{len(xs)}頭）')

    # ───────────────────────────────────────────────────────────
    print('\n' + '=' * 78)
    print('⑦ 絶対体重と wt_norm の相関（共線性の確認）')
    print('=' * 78)
    W = [x for x in pool if x['wt'] is not None and x['wt_norm'] is not None]
    xs = [x['wt'] for x in W]
    ys = [x['wt_norm'] for x in W]
    print(f'  南関4場 {len(W)}頭　wt × wt_norm　r={pearson(xs, ys):+.4f}')
    L = [x for x in light if x['wt'] is not None and x['wt_norm'] is not None]
    print(f'  人気薄 {len(L)}頭　wt × wt_norm　r='
          f'{pearson([x["wt"] for x in L], [x["wt_norm"] for x in L]):+.4f}')
    M = [x for x in pool if x['wt'] is not None and x['wt_med'] is not None]
    print(f'  南関4場 {len(M)}頭　wt × wt_med　 r='
          f'{pearson([x["wt"] for x in M], [x["wt_med"] for x in M]):+.4f}')
    N = [x for x in pool if x['wt_norm'] is not None
         and x['wt_med'] is not None]
    print(f'  南関4場 {len(N)}頭　wt_norm × wt_med　r='
          f'{pearson([x["wt_norm"] for x in N], [x["wt_med"] for x in N]):+.4f}')
    LD = [x for x in pool if x['wt'] is not None and x['load'] is not None]
    print(f'  南関4場 {len(LD)}頭　wt × load　   r='
          f'{pearson([x["wt"] for x in LD], [x["load"] for x in LD]):+.4f}')

    # 絶対体重の帯ごとに wt_norm の平均を見る（①と②が重なる度合い）
    print('\n  絶対体重の帯ごとの wt_norm の平均（①と②の重なり）')
    for lab, fn in WT_BANDS:
        S = [x for x in pool if x['wt'] is not None and fn(x['wt'])
             and x['wt_norm'] is not None]
        if S:
            print(f'    {lab:<12}{len(S):>6}頭　wt_norm平均 '
                  f'{st.fmean(x["wt_norm"] for x in S):.3f}')

    # ───────────────────────────────────────────────────────────
    print('\n' + '=' * 78)
    print(f'追加検証にかける形（単勝回収が層を{EXCESS:.0f}pt以上超えたもの）'
          f'：{len(todo)}件')
    print('=' * 78)
    if not todo:
        print('  なし。どの帯も層を30pt以上超えなかった。')
    for lab, S, P, rl in todo:
        deep(S, P, lab, mid, rl)

    # ───────────────────────────────────────────────────────────
    # 記述（新しい仮説を立てるためではなく、上の数字の中身を見るため）
    # ・30pt超えの形は単勝が何頭で出来ているか
    # ・⑦の問い「①と②は別のものを測っているか」を場の中でも見る
    print('\n' + '=' * 78)
    print('記述：30pt超えの形の単勝の中身と、①②の重なり（場の中）')
    print('=' * 78)
    for lab, S, P, rl in todo:
        w = sorted((x['ptan'] for x in S if x['f'] == 1), reverse=True)
        print(f'\n  {lab}　{len(S)}頭　1着{len(w)}頭　'
              f'鞍数{len({x["rid"] for x in S})}')
        print('   1着の単勝払戻（高い順）：'
              + ' '.join(f'{v:,.0f}' for v in w))
        tot = sum(w)
        for k in (1, 2, 3):
            if len(w) > k:
                print(f'   上位{k}頭を抜くと 単{(tot-sum(w[:k]))/len(S):.1f}%'
                      f'（抜く前 {tot/len(S):.1f}%）')
        ym = sorted({x['ymd'][:6] for x in S if x['f'] == 1})
        print(f'   1着が出た月：{" ".join(ym)}')
        for k, T in (('前半', [x for x in S if x['ymd'] < mid]),
                     ('後半', [x for x in S if x['ymd'] >= mid])):
            v = sorted((x['ptan'] for x in T if x['f'] == 1), reverse=True)
            print(f'   {k} {len(T)}頭　1着{len(v)}頭　単{sum(v)/len(T):.1f}%'
                  f'　最大1頭抜き 単'
                  f'{(sum(v)-(v[0] if v else 0))/len(T):.1f}%　'
                  f'払戻 {" ".join(f"{z:,.0f}" for z in v)}')

    print('\n  ── ①（絶対体重）を場ごとに。②と同じものを見ているかの確認 ──')
    for ba in ('川崎', '大井', '船橋', '浦和'):
        B = [x for x in light if x['ba'] == ba]
        rb = sum(x['ptan'] for x in B) / len(B)
        print(f'\n  ── {ba}　人気薄 {len(B)}頭　層 単{rb:.1f}% ──')
        for lab, fn in WT_BANDS:
            S = [x for x in B if x['wt'] is not None and fn(x['wt'])]
            row(S, lab, mid, rb)
        W = [x for x in B if x['wt'] is not None and x['wt_norm'] is not None]
        print(f'    wt × wt_norm　r='
              f'{pearson([x["wt"] for x in W], [x["wt_norm"] for x in W]):+.4f}'
              f'　鞍あたり完走頭数の中央 '
              f'{st.median([x["n"] for x in B]):.0f}')


if __name__ == '__main__':
    main(*(sys.argv[1:] or []))
