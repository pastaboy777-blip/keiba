# -*- coding: utf-8 -*-
"""馬体が馬場・距離・場・性齢とどう噛み合うかを回収率で測る（C班）。

  python3 -I scripts/ana/body_fit.py

土台は scripts/ana/nankan_body.py。load_body / ev / show / placebo / by_pop を
そのまま使う。結合は書き直さない。

── 測る形（先に決めた8つだけ。増やさない）────────────────────
  ① wt_norm 3帯 × 馬場2群 × 人気薄
  ② 絶対体重 3帯 × 馬場2群 × 人気薄
  ③ wt_norm 3帯 × 距離3帯 × 人気薄
  ④ wt_norm 3帯 × 場 × 人気薄（その場の層と比べる）
  ⑤ sx_k × 人気薄（by_pop も）
  ⑥ age 帯 × 人気薄（by_pop も）
  ⑦ sx_k × 馬場2群 × 人気薄
  ⑧ 2〜3歳の wt_diff 帯 × 人気薄

── 読み方の決めごと ──────────────────────────────────────────
・母数20頭未満は数字を出さず「母数不足。判定しない」（nankan_body.show）
・比べる相手は**条件をそろえた層**。①なら「人気薄 × その馬場群の全体」。
  4場を混ぜた層（人気薄65.4%）は場の構成で動くので、場ごとの数字は
  必ずその場の層と比べる（川崎74.2 / 大井54.2 / 船橋56.5 / 浦和93.3）。
・前半／後半はそれぞれ**層の同じ半期**と比べる。片方だけなら採らない。
・単勝回収が層を30pt以上超えた形だけ偽薬を5回。偽薬の幅に入るなら採らない。
・偽薬の漏れをそろえる。該当が wt_diff のある馬だけなら、偽薬の母集団も
  wt_diff のある馬だけにする（CLAUDE.md「偽薬も同じ漏れを持っているか」）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nankan_body as NB                                    # noqa: E402

SCR = ('/tmp/claude-0/-home-user-keiba/'
       'a716475a-b623-5ff0-8a6c-762d20462748/scratchpad')
BODY = os.path.join(SCR, 'nankan_body.jsonl')

GAP = 30.0          # 層をこれだけ上回ったら偽薬を置く（単勝回収のpt）

# 母数不足の数え上げ（報告の「何割が判定できなかったか」用）
TALLY = {'all': 0, 'short': 0}


# ── 帯の定義 ──────────────────────────────────────────────────
BABA2 = (('良・稍重', ('良', '稍重')), ('重・不良', ('重', '不良')))

WN3 = (('軽い側1/3', lambda v: v < 1 / 3),
       ('中1/3', lambda v: 1 / 3 <= v < 2 / 3),
       ('重い側1/3', lambda v: v >= 2 / 3))

WT3 = (('〜449kg', lambda v: v <= 449),
       ('450〜499kg', lambda v: 450 <= v <= 499),
       ('500kg〜', lambda v: v >= 500))

D3 = (('〜1200m', lambda v: v <= 1200),
      ('1300〜1500m', lambda v: 1300 <= v <= 1500),
      ('1600m〜', lambda v: v >= 1600))

AGE4 = (('2〜3歳', lambda v: v in (2, 3)),
        ('4〜5歳', lambda v: v in (4, 5)),
        ('6〜7歳', lambda v: v in (6, 7)),
        ('8歳以上', lambda v: v >= 8))

WD5 = (('−5kg以下', lambda v: v <= -5),
       ('−4〜−1kg', lambda v: -4 <= v <= -1),
       ('増減なし', lambda v: v == 0),
       ('+1〜+4kg', lambda v: 1 <= v <= 4),
       ('+5kg以上', lambda v: v >= 5))

BA4 = ('川崎', '大井', '船橋', '浦和')


# ── 小道具 ────────────────────────────────────────────────────
def q(v):
    return f'{v:.1f}' if v is not None else '―'


def exp_base(S, pool):
    """偽薬の期待値（厳密）。

    placebo() は「各鞍で該当が何頭いたか」だけを守って無作為に取る。
    その期待値は閉じた式で出せる：

        E[単回収] = Σ_鞍 m_鞍 × (その鞍の母集団の平均単払戻) ÷ Σ_鞍 m_鞍

    5回の無作為抽出より揺れない。層（鞍を数えず全頭を平均したもの）との
    差は**鞍の構成の差**なので、この期待値と比べれば構成の差は落ちる。
    該当が「その鞍の母集団からどう選ばれたか」だけが残る。
    """
    from collections import defaultdict as dd
    need = dd(int)
    for x in S:
        need[x['rid']] += 1
    byr = dd(list)
    for x in pool:
        byr[x['rid']].append(x)
    wt = t = fk = 0.0
    for rid, m in need.items():
        c = byr.get(rid, [])
        if not c:
            continue
        m = min(m, len(c))
        wt += m
        t += m * sum((y.get('ptan') or 0) for y in c) / len(c)
        fk += m * sum((y.get('pfuku') or 0) for y in c) / len(c)
    return ((t / wt, fk / wt) if wt else (None, None))


def layer(S, label, mid):
    """層の1行。母数不足の数え上げには入れない。"""
    o = NB.ev(S, mid)
    if o['short']:
        print(f'  層   {label}　{o["n"]}頭　母数不足。判定しない')
        return o
    print(f'  層   {label}　{o["n"]}頭　3着内{o["top3"]:.1f}%　'
          f'1着{o["win"]:.1f}%　単{o["tan"]:.1f}%　複{o["fuku"]:.1f}%'
          f'　｜前半 単{q(o["a_tan"])}/複{q(o["a_fuku"])}　'
          f'後半 単{q(o["b_tan"])}/複{q(o["b_fuku"])}')
    return o


def cell(S, label, mid, lay, pool, tag, no_pops=False):
    """該当の1行。層を30pt超えたら偽薬も置く。"""
    TALLY['all'] += 1
    o = NB.ev(S, mid)
    if o['short']:
        TALLY['short'] += 1
        print(f'  該当 {label}　{o["n"]}頭　母数不足。判定しない')
        return o
    print(f'  該当 {label}　{o["n"]}頭　3着内{o["top3"]:.1f}%　'
          f'1着{o["win"]:.1f}%　単{o["tan"]:.1f}%　複{o["fuku"]:.1f}%'
          f'　｜前半{o["a_n"]}頭 単{q(o["a_tan"])}/複{q(o["a_fuku"])}　'
          f'後半{o["b_n"]}頭 単{q(o["b_tan"])}/複{q(o["b_fuku"])}'
          f'　｜最大1頭({o["nomax"]:,.0f}円)抜き 単{o["tan_nomax"]:.1f}%')

    # 前半／後半それぞれを層の同じ半期と比べる
    if lay and not lay['short']:
        d0 = o['tan'] - lay['tan']
        ha = (o['a_tan'] is not None and lay['a_tan'] is not None
              and o['a_tan'] > lay['a_tan'])
        hb = (o['b_tan'] is not None and lay['b_tan'] is not None
              and o['b_tan'] > lay['b_tan'])
        la = (o['a_tan'] is not None and lay['a_tan'] is not None
              and o['a_tan'] < lay['a_tan'])
        lb = (o['b_tan'] is not None and lay['b_tan'] is not None
              and o['b_tan'] < lay['b_tan'])
        if ha and hb:
            v = '両方で層超え'
        elif la and lb:
            v = '両方で層以下（下向きに一貫）'
        else:
            v = '採らない（片側だけ）'
        et, ef = exp_base(S, pool)
        print(f'       層との差 単{d0:+.1f}pt　'
              f'前半{"層超え" if ha else "層以下"}／'
              f'後半{"層超え" if hb else "層以下"}　→ {v}')
        if et is not None:
            print(f'       偽薬の期待値（鞍の構成をそろえた厳密値）'
                  f'単{et:.1f}%／複{ef:.1f}%　'
                  f'→ 期待値との差 単{o["tan"]-et:+.1f}pt／'
                  f'複{o["fuku"]-ef:+.1f}pt')
        # 偽薬を置く条件：層を30pt以上離れた形（指示）＋前後半で向きが
        # そろった形（30pt未満でも「残った／落ちた」と書くには偽薬が要る）。
        # 下向きも同じ扱いにする（②の判定に効く）
        if abs(d0) >= GAP or (ha and hb) or (la and lb):
            why = (f'層と{GAP:.0f}pt以上離れた' if abs(d0) >= GAP else '') + \
                  ('／' if (abs(d0) >= GAP and (ha and hb or la and lb))
                   else '') + \
                  ('前後半とも層超え' if (ha and hb) else
                   ('前後半とも層以下' if (la and lb) else ''))
            print(f'       {why}。偽薬5回（{tag}）')
            band = []
            for i, p in enumerate(NB.placebo(S, pool, k=5, mid=mid), 1):
                if p['short']:
                    print(f'         {i}回目　母数不足。判定しない')
                else:
                    band.append((p['tan'], p['tan_nomax']))
                    print(f'         {i}回目　{p["n"]}頭　単{p["tan"]:>6.1f}%'
                          f'　複{p["fuku"]:>6.1f}%　'
                          f'最大1頭抜き 単{p["tan_nomax"]:>6.1f}%')
            if band:
                lo, hi = min(b[0] for b in band), max(b[0] for b in band)
                nlo, nhi = min(b[1] for b in band), max(b[1] for b in band)

                def out(v, a, b2):
                    return '幅の上に出た' if v > b2 else (
                        '幅の下に出た' if v < a else '幅の中')
                print(f'         偽薬の幅 単{lo:.1f}〜{hi:.1f}%　'
                      f'最大1頭抜き 単{nlo:.1f}〜{nhi:.1f}%　→ 該当は'
                      f'{out(o["tan"], lo, hi)}'
                      f'（最大1頭抜きは{out(o["tan_nomax"], nlo, nhi)}）')
            if not no_pops:
                print('       人気帯をそろえて（構成の差ではないかを見る）')
                pops(S, pool, mid)
    return o


def pops(S, pool, mid):
    """by_pop を出す。人気帯の構成の差かどうかを見る。"""
    for lab, a, b in NB.by_pop(S, pool, mid=mid):
        def fmt(o):
            if o['short']:
                return f'{o["n"]:>5}頭　母数不足。判定しない'
            return (f'{o["n"]:>5}頭　3着内{o["top3"]:>5.1f}%　'
                    f'単{o["tan"]:>6.1f}%　複{o["fuku"]:>6.1f}%')
        print(f'       {lab:<12}該当 {fmt(a)}')
        print(f'       {"":<12}層　 {fmt(b)}')


def head(t):
    print('\n' + '━' * 78)
    print(t)
    print('━' * 78)


# ── 本体 ──────────────────────────────────────────────────────
def main(path=BODY):
    rows, mid = NB.load_body(path)
    print(f'{len(rows)}頭を読んだ　前半／後半の境目 {mid}')

    # 層の母数：払戻が取れて完走6頭以上（nankan_body の決めごとと同じ）
    pool = [x for x in rows if x['ptan'] is not None and x['n'] >= 6]
    und = [x for x in pool if x['pop'] is not None and x['pop'] >= 6]
    print(f'層 {len(pool)}頭　人気薄(6番人気以降) {len(und)}頭')

    head('全体の層（比べる相手）')
    layer(pool, '南関4場', mid)
    layer(und, '人気薄(6番人気以降)', mid)
    for ba in BA4:
        layer([x for x in und if x['ba'] == ba], f'人気薄 × {ba}', mid)

    # ── ① wt_norm 3帯 × 馬場2群 × 人気薄 ──────────────────────
    head('① wt_norm 3帯 × 馬場2群 × 人気薄')
    for blab, bs in BABA2:
        P = [x for x in und if x['baba'] in bs and x['wt_norm'] is not None]
        print(f'\n[{blab}]')
        lay = layer(P, f'人気薄 × {blab}', mid)
        for wlab, fn in WN3:
            S = [x for x in P if fn(x['wt_norm'])]
            cell(S, f'{wlab}', mid, lay, P, f'①{blab}×{wlab}')

    # ── ② 絶対体重 3帯 × 馬場2群 × 人気薄 ─────────────────────
    head('② 絶対体重 3帯 × 馬場2群 × 人気薄'
          '（「重馬場は重い馬」が値段に入っているか）')
    for blab, bs in BABA2:
        P = [x for x in und if x['baba'] in bs and x['wt'] is not None]
        print(f'\n[{blab}]')
        lay = layer(P, f'人気薄 × {blab}', mid)
        for wlab, fn in WT3:
            S = [x for x in P if fn(x['wt'])]
            cell(S, f'{wlab}', mid, lay, P, f'②{blab}×{wlab}')

    # ── ③ wt_norm 3帯 × 距離3帯 × 人気薄 ──────────────────────
    head('③ wt_norm 3帯 × 距離3帯 × 人気薄')
    for dlab, dfn in D3:
        P = [x for x in und if x['dist'] is not None and dfn(x['dist'])
             and x['wt_norm'] is not None]
        print(f'\n[{dlab}]')
        lay = layer(P, f'人気薄 × {dlab}', mid)
        for wlab, fn in WN3:
            S = [x for x in P if fn(x['wt_norm'])]
            cell(S, f'{wlab}', mid, lay, P, f'③{dlab}×{wlab}')

    # ── ④ wt_norm 3帯 × 場 × 人気薄 ───────────────────────────
    head('④ wt_norm 3帯 × 場 × 人気薄（その場の層と比べる）')
    for ba in BA4:
        P = [x for x in und if x['ba'] == ba and x['wt_norm'] is not None]
        print(f'\n[{ba}]')
        lay = layer(P, f'人気薄 × {ba}', mid)
        for wlab, fn in WN3:
            S = [x for x in P if fn(x['wt_norm'])]
            cell(S, f'{wlab}', mid, lay, P, f'④{ba}×{wlab}')

    # ── ⑤ sx_k × 人気薄 ───────────────────────────────────────
    head('⑤ sx_k（牡／牝／セ）× 人気薄')
    lay = layer(und, '人気薄', mid)
    for k in ('牡', '牝', 'セ'):
        S = [x for x in und if x['sx_k'] == k]
        cell(S, k, mid, lay, und, f'⑤{k}', no_pops=True)
        print('       人気帯をそろえて（指示：⑤は全帯で出す）')
        pops(S, und, mid)

    # ── ⑥ age 帯 × 人気薄 ─────────────────────────────────────
    head('⑥ age 帯 × 人気薄')
    P = [x for x in und if x['age'] is not None]
    lay = layer(P, '人気薄（年齢が取れた馬）', mid)
    for alab, fn in AGE4:
        S = [x for x in P if fn(x['age'])]
        cell(S, alab, mid, lay, P, f'⑥{alab}', no_pops=True)
        print('       人気帯をそろえて（指示：⑥は全帯で出す）')
        pops(S, P, mid)

    # ── ⑦ sx_k × 馬場2群 × 人気薄 ─────────────────────────────
    head('⑦ sx_k × 馬場2群 × 人気薄（牝馬が渋り馬場でどうなるか）')
    for blab, bs in BABA2:
        P = [x for x in und if x['baba'] in bs]
        print(f'\n[{blab}]')
        lay = layer(P, f'人気薄 × {blab}', mid)
        for k in ('牡', '牝', 'セ'):
            S = [x for x in P if x['sx_k'] == k]
            cell(S, k, mid, lay, P, f'⑦{blab}×{k}')

    # ── ⑧ 2〜3歳の wt_diff × 人気薄 ───────────────────────────
    head('⑧ 2〜3歳の wt_diff（成長期の体重増）× 人気薄')
    P = [x for x in und if x['age'] in (2, 3) and x['wt_diff'] is not None]
    lay = layer(P, '人気薄 × 2〜3歳（前走の体重が取れた馬）', mid)
    for wlab, fn in WD5:
        S = [x for x in P if fn(x['wt_diff'])]
        cell(S, wlab, mid, lay, P, f'⑧2〜3歳×{wlab}')
    print('\n  比べ：4歳以上の同じ帯（成長なのか太いだけなのかを見る）')
    Q = [x for x in und if x['age'] is not None and x['age'] >= 4
         and x['wt_diff'] is not None]
    lay2 = layer(Q, '人気薄 × 4歳以上（前走の体重が取れた馬）', mid)
    for wlab, fn in WD5:
        S = [x for x in Q if fn(x['wt_diff'])]
        cell(S, wlab, mid, lay2, Q, f'⑧4歳以上×{wlab}')

    print('\n' + '━' * 78)
    print(f'該当の枠 {TALLY["all"]}　うち母数不足 {TALLY["short"]}　'
          f'{TALLY["short"]/TALLY["all"]*100:.1f}%')
    print('━' * 78)

    diag(und, mid)


def diag(und, mid):
    """残ったものの点検。新しい条件を探すためではなく、壊すために回す。

    (a) 残った5つがどれくらい重なっているか。重なっていれば1つの話。
    (b) 浦和を抜いても残るか（浦和は層が単93.3%で他場と大きく違う）。
    """
    head('残ったものの点検（共線性と、浦和を抜いたとき）')

    def wn_lo(x):
        return x['wt_norm'] is not None and x['wt_norm'] < 1 / 3

    SUR = [
        ('③1300〜1500m×軽い側1/3',
         lambda x: (x['dist'] is not None and 1300 <= x['dist'] <= 1500
                    and wn_lo(x))),
        ('④浦和×軽い側1/3', lambda x: x['ba'] == '浦和' and wn_lo(x)),
        ('⑥6〜7歳', lambda x: x['age'] in (6, 7)),
        ('⑦重・不良×牝',
         lambda x: x['baba'] in ('重', '不良') and x['sx_k'] == '牝'),
        ('⑧2〜3歳×−4〜−1kg',
         lambda x: (x['age'] in (2, 3) and x['wt_diff'] is not None
                    and -4 <= x['wt_diff'] <= -1)),
        # 下向きに残ったもの（偽薬の幅の下に出た4つ）。向きが逆でも同じ点検を通す
        ('③1300〜1500m×中1/3',
         lambda x: (x['dist'] is not None and 1300 <= x['dist'] <= 1500
                    and x['wt_norm'] is not None
                    and 1 / 3 <= x['wt_norm'] < 2 / 3)),
        ('④浦和×重い側1/3',
         lambda x: (x['ba'] == '浦和' and x['wt_norm'] is not None
                    and x['wt_norm'] >= 2 / 3)),
        ('⑦重・不良×牡',
         lambda x: x['baba'] in ('重', '不良') and x['sx_k'] == '牡'),
        ('⑧2〜3歳×+5kg以上',
         lambda x: (x['age'] in (2, 3) and x['wt_diff'] is not None
                    and x['wt_diff'] >= 5)),
    ]
    SET = [(lab, {id(x) for x in und if fn(x)}) for lab, fn in SUR]

    print('\n(a) 重なり（上向きに残った5つ。行の何%が列にも入るか）')
    U = SET[:5]
    print('      ' + ''.join(f'{l[:8]:>10}' for l, _ in U))
    for la, A in U:
        row = ''.join(f'{len(A & B)/len(A)*100:>9.0f}%' for _, B in U)
        print(f'  {la[:20]:<20}{row}　（{len(A)}頭）')

    print('\n(b) 浦和を抜いたとき（層＝浦和を抜いた人気薄）')
    nu = [x for x in und if x['ba'] != '浦和']
    lay = layer(nu, '人気薄（浦和を除く）', mid)
    for lab, fn in SUR:
        if lab.startswith('④'):
            print(f'  該当 {lab}　浦和そのものなので抜けない')
            continue
        S = [x for x in nu if fn(x)]
        cell(S, f'{lab}（浦和を除く）', mid, lay, nu,
             f'点検{lab}', no_pops=True)


if __name__ == '__main__':
    main(*(sys.argv[1:] or []))
