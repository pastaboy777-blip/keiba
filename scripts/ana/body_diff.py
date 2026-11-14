# -*- coding: utf-8 -*-
"""馬体重の増減（前走比 wt_diff）と休養日数（rest）を回収率で測る。

  python3 -I scripts/ana/body_diff.py

土台は scripts/ana/nankan_body.py をそのまま読み込んで使う（結合は書き直さない）。
測る形は8つに先に決めてあり、結果を見てから条件を足さない
（CLAUDE.md「前半で見つけて後半で確かめる」）。

守っていること
・層と比べる。人気薄（6番人気以降）が比べる相手。
・rest は必ず by_pop() で人気帯をそろえた数字も出す
  （CLAUDE.md「全体の数字は構成の差かもしれない」。長く休む馬は人気になりやすい）。
・wt_diff が出せるのは前走がデータ内にある馬だけ。初出走・転入初戦・長期離脱明けが
  抜ける。出せた馬と出せなかった馬の層の回収率を先に並べて、選択の偏りの大きさを見る。
・単勝回収は必ず「最大1頭を抜いた値」と前半／後半を並べる。
・層を単勝回収で30pt以上超えた形だけ偽薬を5回置く。偽薬は同じ鞍・同数・無作為。
  偽薬の母集団は「wt_diff（または rest）が出せた人気薄」にそろえる。
  条件側と同じ漏れを偽薬にも持たせるため（CLAUDE.md「偽薬を置く」）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)        # python3 -I は script の dir を入れない

import nankan_body as NB            # noqa: E402

GAP = 30.0                          # 層を単勝回収でこれ以上超えたら偽薬を置く

# ── 帯の定義（先に決めてある。増やさない）─────────────────────
DIFF_BANDS = (
    ('−10kg以下', lambda v: v <= -10),
    ('−9〜−5kg', lambda v: -9 <= v <= -5),
    ('−4〜+4kg', lambda v: -4 <= v <= 4),
    ('+5〜+9kg', lambda v: 5 <= v <= 9),
    ('+10kg以上', lambda v: v >= 10),
)
REST_BANDS = (
    ('7日以内', lambda v: v <= 7),
    ('8〜20日', lambda v: 8 <= v <= 20),
    ('21〜45日', lambda v: 21 <= v <= 45),
    ('46〜90日', lambda v: 46 <= v <= 90),
    ('91日以上', lambda v: v >= 91),
)


def q(v, w=6):
    return f'{v:>{w}.1f}' if v is not None else f'{"―":>{w}}'


# ── 前後半の割り方（訂正版）────────────────────────────────────
# load_body() が返す mid（データ全体の開催日の中央 '20260805'）で割ってはいけない。
# wt_diff も rest も hp も前走の履歴が要るので、データの頭のほうには材料がない。
# hp（3走以上）が出せる割合は 〜3月 0.1% → 4〜6月 23.7% → 7〜9月 51.0%
# → 10月〜 65.2%。全体の中央で割ると前半がほぼ空になり、残ったわずかな頭数に
# 1頭の大穴が乗って「前半◯◯%」が出る。
# 例：川崎 人気薄 × hp<=1/3 の251頭を mid で割ると前半30頭 単201.0% だが、
# 1着1頭・払戻6,030円の1頭だけ（6030÷30=201.0）。検定が成立していない。
# 代わりに「該当馬それ自身の日付の中央」で割る。層も該当馬と同じ期間に絞る。
MIN_W = 3                # 片方の期の1着がこれ未満なら検定として成立しない


def cut(S):
    """該当馬それ自身の開催日の中央で前半／後半に割る。"""
    d = sorted({x['ymd'] for x in S})
    m = d[len(d) // 2]
    return [x for x in S if x['ymd'] < m], [x for x in S if x['ymd'] >= m]


def cutm(S):
    d = sorted({x['ymd'] for x in S})
    return d[len(d) // 2]


def rr(S):
    """回収率と、1着の頭数・払戻の内訳。母数20未満でも数字は出し、旗を立てる。"""
    n = len(S)
    if not n:
        return None
    w = sorted((x.get('ptan') or 0) for x in S if x['f'] == 1)
    return dict(n=n, nw=len(w), w=w,
                tan=sum((x.get('ptan') or 0) for x in S) / n,
                fuku=sum((x.get('pfuku') or 0) for x in S) / n,
                top3=sum(1 for x in S if x['f'] <= 3) / n * 100,
                lo=min(x['ymd'] for x in S), hi=max(x['ymd'] for x in S))


def wtxt(w):
    if not w:
        return '1着0頭'
    return f'1着{len(w)}頭（' + '＋'.join(f'{v:,.0f}' for v in w) + '円）'


def h2(S, pool, label, pad=26):
    """該当馬自身の中央で割り、同じ期間に絞った層と並べる。

    返すのは dict。判定は
      ok      前後半のどちらも同期間の層の単勝回収を超えた
      valid   前後半のどちらも20頭以上かつ1着3頭以上（検定として成立する）
    """
    o = rr(S)
    if o is None:
        print(f'  {label:<{pad}}0頭')
        return None
    if o['n'] < NB.MIN_N:
        print(f'  {label:<{pad}}{o["n"]}頭　母数不足。判定しない')
        return dict(short=True, n=o['n'], label=label)
    m = cutm(S)
    P = [x for x in pool if o['lo'] <= x['ymd'] <= o['hi']]
    A, B = cut(S)
    PA = [x for x in P if x['ymd'] < m]
    PB = [x for x in P if x['ymd'] >= m]
    e = NB.ev(S)
    print(f'  {label}　{o["n"]}頭　3着内{o["top3"]:.1f}%　{wtxt(o["w"])}　'
          f'単{o["tan"]:.1f}%　複{o["fuku"]:.1f}%　'
          f'最大1頭({e["nomax"]:,.0f}円)抜き 単{e["tan_nomax"]:.1f}%')
    pf = rr(P)
    print(f'    期間 {o["lo"]}〜{o["hi"]}　分割日 {m}（該当馬自身の中央）　'
          f'同期間の層 {pf["n"]}頭 単{pf["tan"]:.1f}% 複{pf["fuku"]:.1f}%')
    out = {}
    for k, T, PT in (('前半', A, PA), ('後半', B, PB)):
        t, p = rr(T), rr(PT)
        out[k] = (t, p)
        flag = ''
        if t['n'] < NB.MIN_N:
            flag += '　※母数不足'
        if t['nw'] < MIN_W:
            flag += f'　※1着{t["nw"]}頭。検定として成立しない'
        print(f'    {k}　該当 {t["n"]}頭　{wtxt(t["w"])}　'
              f'単{t["tan"]:.1f}%　複{t["fuku"]:.1f}%　｜'
              f'同期間の層 {p["n"]}頭 単{p["tan"]:.1f}%/複{p["fuku"]:.1f}%'
              f'（1着{p["nw"]}頭）{flag}')
    (ta, pa), (tb, pb) = out['前半'], out['後半']
    ok = (ta['tan'] > pa['tan']) and (tb['tan'] > pb['tan'])
    valid = (ta['n'] >= NB.MIN_N and tb['n'] >= NB.MIN_N
             and ta['nw'] >= MIN_W and tb['nw'] >= MIN_W)
    print(f'    判定　両期で層超え {"はい" if ok else "いいえ"}　／　'
          f'検定として成立 {"する" if valid else "しない"}')
    return dict(short=False, label=label, n=o['n'], tan=o['tan'],
                fuku=o['fuku'], nomax=e['tan_nomax'], base=pf['tan'],
                ok=ok, valid=valid, a=ta, b=tb, pa=pa, pb=pb, m=m)


def line(S, label, mid, pad=22):
    """1行。頭数・3着内・1着・単・複・前半・後半・最大1頭抜きを全部出す。"""
    o = NB.ev(S, mid)
    if o['short']:
        print(f'  {label:<{pad}}{o["n"]:>5}頭　母数不足。判定しない')
        return o
    print(f'  {label:<{pad}}{o["n"]:>5}頭　3着内{o["top3"]:>5.1f}%　'
          f'1着{o["win"]:>4.1f}%　単{o["tan"]:>6.1f}%　複{o["fuku"]:>6.1f}%　｜'
          f'前半{o["a_n"]:>4}頭 単{q(o["a_tan"])}/複{q(o["a_fuku"])}　'
          f'後半{o["b_n"]:>4}頭 単{q(o["b_tan"])}/複{q(o["b_fuku"])}　｜'
          f'最大1頭({o["nomax"]:>6,.0f}円)抜き 単{o["tan_nomax"]:>6.1f}%')
    return o


def pops(S, pool, mid, pad=14):
    """人気帯をそろえて該当と層を並べる。"""
    for lab, a, b in NB.by_pop(S, pool, mid=mid):
        for who, o in (('該当', a), ('層　', b)):
            if o['short']:
                print(f'    {lab if who=="該当" else "":<{pad}}{who} '
                      f'{o["n"]:>5}頭　母数不足')
            else:
                print(f'    {lab if who=="該当" else "":<{pad}}{who} '
                      f'{o["n"]:>5}頭　3着内{o["top3"]:>5.1f}%　'
                      f'1着{o["win"]:>4.1f}%　単{o["tan"]:>6.1f}%　'
                      f'複{o["fuku"]:>6.1f}%')


def pla(S, pool, mid, label=''):
    """偽薬5回。"""
    print(f'    偽薬5回（{label}）')
    vals = []
    for i, o in enumerate(NB.placebo(S, pool, k=5, mid=mid), 1):
        if o['short']:
            print(f'      {i}回目　{o["n"]}頭　母数不足。判定しない')
        else:
            vals.append(o['tan'])
            print(f'      {i}回目　{o["n"]:>5}頭　単{o["tan"]:>6.1f}%　'
                  f'複{o["fuku"]:>6.1f}%　最大1頭抜き 単{o["tan_nomax"]:>6.1f}%')
    if vals:
        print(f'      → 偽薬の単勝の幅 {min(vals):.1f}〜{max(vals):.1f}%')
    return vals


def band_split(S, bands, key):
    for lab, fn in bands:
        yield lab, [x for x in S if x[key] is not None and fn(x[key])]


def main(path=NB.BODY):
    rows, mid = NB.load_body(path)
    pool = [x for x in rows if x['ptan'] is not None and x['n'] >= 6]
    und = [x for x in pool if x['pop'] is not None and x['pop'] >= 6]
    und_d = [x for x in und if x['wt_diff'] is not None]
    und_r = [x for x in und if x['rest'] is not None]
    print(f'{len(rows)}頭　境目 {mid}')
    print(f'層：南関4場 {len(pool)}頭　人気薄(6番人気以降) {len(und)}頭')
    print(f'  うち wt_diff が出せた人気薄 {len(und_d)}頭　'
          f'rest が出せた人気薄 {len(und_r)}頭')

    # ── 0. 層 ─────────────────────────────────────────────────
    print('\n=== 0. 比べる相手（層）===')
    line(pool, '南関4場ぜんぶ', mid)
    line(und, '人気薄(6番人気以降)', mid)
    line(und_d, '└ wt_diff が出せた人気薄', mid)
    line(und_r, '└ rest が出せた人気薄', mid)

    # ── 0b. 選択の偏り：wt_diff が出せた馬／出せなかった馬 ────
    print('\n=== 0b. 選択の偏り（wt_diff が出せた馬と出せなかった馬）===')
    print('  wt_diff は「前走がデータ内にある馬」にしか出ない。'
          '初出走・転入初戦・長期離脱明けが抜ける。')
    for lab, S in (('全体・出せた', [x for x in pool if x['wt_diff'] is not None]),
                   ('全体・出せなかった',
                    [x for x in pool if x['wt_diff'] is None]),
                   ('人気薄・出せた', und_d),
                   ('人気薄・出せなかった',
                    [x for x in und if x['wt_diff'] is None])):
        line(S, lab, mid)
    print('  人気帯をそろえる（該当＝wt_diff が出せた人気薄／層＝人気薄ぜんぶ）')
    pops(und_d, und, mid)
    print('  ※上の「層」は該当を含むので薄まる。出せた／出せなかったを直接比べる：')
    for lab, lo, hi in (('6〜7番人気', 6, 7), ('8〜10番人気', 8, 10),
                        ('11番人気以降', 11, 99)):
        A = [x for x in und_d if x['pop'] is not None and lo <= x['pop'] <= hi]
        B = [x for x in und if x['wt_diff'] is None and x['pop'] is not None
             and lo <= x['pop'] <= hi]
        for who, S in (('出せた　　', A), ('出せなかった', B)):
            o = NB.ev(S, mid)
            if o['short']:
                print(f'    {lab:<14}{who} {o["n"]:>5}頭　母数不足')
            else:
                print(f'    {lab:<14}{who} {o["n"]:>5}頭　3着内{o["top3"]:>5.1f}%　'
                      f'1着{o["win"]:>4.1f}%　単{o["tan"]:>6.1f}%　'
                      f'複{o["fuku"]:>6.1f}%')
    print('  人気の構成（出せた／出せなかった）')
    for lab, S in (('出せた', und_d),
                   ('出せなかった', [x for x in und if x['wt_diff'] is None])):
        b = [0, 0, 0]
        for x in S:
            if x['pop'] is None:
                continue
            b[0 if x['pop'] <= 7 else (1 if x['pop'] <= 10 else 2)] += 1
        t = sum(b) or 1
        print(f'    {lab:<12}6〜7番人気{b[0]/t*100:>5.1f}%　'
              f'8〜10番人気{b[1]/t*100:>5.1f}%　11番人気以降{b[2]/t*100:>5.1f}%')

    # ── ① wt_diff 5帯 × 人気薄 ────────────────────────────────
    print('\n=== ① wt_diff 5帯 × 人気薄 ===')
    print(f'  （比べる相手：人気薄ぜんぶ 単65.4%／wt_diff が出せた人気薄 '
          f'単{NB.ev(und_d, mid)["tan"]:.1f}%）')
    D1 = {}
    for lab, S in band_split(und_d, DIFF_BANDS, 'wt_diff'):
        D1[lab] = (S, line(S, lab, mid))

    # ── ② ①を人気帯でそろえる ────────────────────────────────
    print('\n=== ② ①を人気帯でそろえる（層＝wt_diff が出せた人気薄）===')
    for lab, (S, o) in D1.items():
        print(f'  ◇ {lab}')
        pops(S, und_d, mid)

    # ── ③ rest 5帯 × 人気薄 ───────────────────────────────────
    print('\n=== ③ rest 5帯 × 人気薄（そろえる前）===')
    print(f'  （比べる相手：人気薄ぜんぶ 単65.4%／rest が出せた人気薄 '
          f'単{NB.ev(und_r, mid)["tan"]:.1f}%）')
    R1 = {}
    for lab, S in band_split(und_r, REST_BANDS, 'rest'):
        R1[lab] = (S, line(S, lab, mid))

    # ── ④ ③を人気帯でそろえる（必須）────────────────────────
    print('\n=== ④ ③を人気帯でそろえる（層＝rest が出せた人気薄）===')
    print('  休養明けは人気になりやすい。そろえる前の数字だけでは読まない。')
    print('  参考：各帯の人気の構成')
    for lab, (S, o) in R1.items():
        if not S:
            continue
        b = {'6〜7': 0, '8〜10': 0, '11+': 0}
        for x in S:
            if x['pop'] is None:
                continue
            k = '6〜7' if x['pop'] <= 7 else ('8〜10' if x['pop'] <= 10 else '11+')
            b[k] += 1
        t = sum(b.values()) or 1
        print(f'    {lab:<10}6〜7番人気{b["6〜7"]/t*100:>5.1f}%　'
              f'8〜10番人気{b["8〜10"]/t*100:>5.1f}%　'
              f'11番人気以降{b["11+"]/t*100:>5.1f}%')
    for lab, (S, o) in R1.items():
        print(f'  ◇ {lab}')
        pops(S, und_r, mid)

    # ── ⑤ wt_diff × rest ─────────────────────────────────────
    print('\n=== ⑤ wt_diff × rest の掛け合わせ × 人気薄 ===')
    both = [x for x in und if x['wt_diff'] is not None and x['rest'] is not None]
    print(f'  両方出せた人気薄 {len(both)}頭')
    line(both, '両方出せた人気薄（層）', mid)
    C5 = {}
    for rl, rfn in (('休み46日以上', lambda v: v >= 46),
                    ('休み45日以下', lambda v: v <= 45)):
        for dl, dfn in (('+5kg以上', lambda v: v >= 5),
                        ('−5kg以下', lambda v: v <= -5),
                        ('−4〜+4kg', lambda v: -4 <= v <= 4)):
            S = [x for x in both if rfn(x['rest']) and dfn(x['wt_diff'])]
            C5[f'{rl} × {dl}'] = (S, line(S, f'{rl} × {dl}', mid, pad=26))
    print('  人気帯をそろえる（層＝両方出せた人気薄）')
    for lab, (S, o) in C5.items():
        if lab.startswith('休み46日以上') and not lab.endswith('−4〜+4kg'):
            print(f'  ◇ {lab}')
            pops(S, both, mid)

    # ── ⑤b 掛け合わせを分解する ──────────────────────────────
    print('\n=== ⑤b 掛け合わせの分解（単独の帯と比べる）===')
    r46 = [x for x in both if x['rest'] >= 46]
    dm5 = [x for x in both if x['wt_diff'] <= -5]
    line(r46, '休み46日以上だけ', mid, pad=26)
    line(dm5, '−5kg以下だけ', mid, pad=26)
    line(C5['休み46日以上 × −5kg以下'][0], '掛け合わせ', mid, pad=26)
    print('  追加の偽薬（30pt基準には届かないが、前後半の両方で層を超えたため置く）')
    pla(C5['休み46日以上 × −5kg以下'][0], both, mid, label='両方出せた人気薄')
    print('  休みの帯をさらに割る（確認のためだけ。ここから条件を選ばない）')
    for rl, rfn in (('休み46〜90日', lambda v: 46 <= v <= 90),
                    ('休み91日以上', lambda v: v >= 91)):
        S = [x for x in both if rfn(x['rest']) and x['wt_diff'] <= -5]
        line(S, f'{rl} × −5kg以下', mid, pad=26)

    # ── ⑥ |wt_diff| >= 15 ────────────────────────────────────
    print('\n=== ⑥ 増減の絶対値が大きい馬（|wt_diff| >= 15kg）× 人気薄 ===')
    S6 = [x for x in und_d if abs(x['wt_diff']) >= 15]
    o6 = line(S6, '|wt_diff|>=15kg', mid)
    line([x for x in und_d if x['wt_diff'] >= 15], '  うち +15kg以上', mid)
    line([x for x in und_d if x['wt_diff'] <= -15], '  うち −15kg以下', mid)
    print('  人気帯をそろえる（層＝wt_diff が出せた人気薄）')
    pops(S6, und_d, mid)

    # ── ⑦ ①を場ごとに ───────────────────────────────────────
    print('\n=== ⑦ ① を場ごとに割る ===')
    D7 = {}
    for ba in ('川崎', '大井', '船橋', '浦和'):
        bu = [x for x in und if x['ba'] == ba]
        bd = [x for x in und_d if x['ba'] == ba]
        print(f'  ── {ba}（人気薄 {len(bu)}頭／wt_diff が出せた人気薄 '
              f'{len(bd)}頭）')
        line(bu, f'{ba} 人気薄（層）', mid)
        line(bd, f'{ba} wt_diff 出せた（層）', mid)
        for lab, S in band_split(bd, DIFF_BANDS, 'wt_diff'):
            D7[(ba, lab)] = (S, bd, line(S, f'{ba} {lab}', mid))

    # ── ⑧ ① × hp（ふだんの4角位置が上位1/3）───────────────────
    print('\n=== ⑧ ① × hp<=1/3（hn>=3）===')
    print('  川崎 × 人気薄 × hp<=1/3 は251頭 単163.5%（層74.2%）。'
          '増減がこれに足せるのかを見る。')
    D8 = {}
    for ba in ('川崎', '大井', '船橋', '浦和', '南関4場'):
        bu = und if ba == '南関4場' else [x for x in und if x['ba'] == ba]
        hp = [x for x in bu if x['hn'] >= NB.HP_MIN and x['hp'] is not None
              and x['hp'] <= 1 / 3]
        hpd = [x for x in hp if x['wt_diff'] is not None]
        print(f'  ── {ba}')
        line(hp, f'{ba} hp<=1/3（増減は問わない）', mid, pad=26)
        line(hpd, f'{ba} hp<=1/3 ＆ wt_diff 出せた', mid, pad=26)
        for lab, S in band_split(hpd, DIFF_BANDS, 'wt_diff'):
            D8[(ba, lab)] = (S, hpd, line(S, f'{ba} hp<=1/3 {lab}', mid,
                                          pad=26))
        # 粗く2つに割った版（細かく割ると母数が足りない）
        for lab, fn in (('減(<=-5kg)', lambda v: v <= -5),
                        ('ほぼ同じ(-4〜+4)', lambda v: -4 <= v <= 4),
                        ('増(>=+5kg)', lambda v: v >= 5)):
            S = [x for x in hpd if fn(x['wt_diff'])]
            D8[(ba, lab)] = (S, hpd, line(S, f'{ba} hp<=1/3 {lab}', mid,
                                          pad=26))

    # ── ⑧b hp<=1/3 の母集団の癖（⑧をどこまで読めるか）────────
    print('\n=== ⑧b hp<=1/3 の母集団の癖 ===')
    hp_all = [x for x in und if x['hn'] >= NB.HP_MIN and x['hp'] is not None
              and x['hp'] <= 1 / 3]
    nd = sum(1 for x in hp_all if x['wt_diff'] is None)
    print(f'  hp<=1/3 の人気薄 {len(hp_all)}頭　'
          f'うち wt_diff が出せなかった {nd}頭')
    print('  → hp は hn>=3（過去3走がデータ内にある）を要る。'
          'その馬は必ず前走もデータ内にあるので wt_diff も出る。'
          '⑧には「増減が出せたかどうか」の偏りは入らない。')
    a = sum(1 for x in hp_all if x['ymd'] < mid)
    print(f'  前半 {a}頭 / 後半 {len(hp_all)-a}頭'
          f'（{(len(hp_all)-a)/len(hp_all)*100:.0f}%が後半）')
    print('  → 履歴が3走たまるのに時間がかかるので後半に寄る。'
          '⑧を帯で割ると前半が20頭に届かず、前後半の確かめができない。')
    from collections import Counter
    for ba in ('川崎',):
        H = [x for x in hp_all if x['ba'] == ba]
        c = Counter()
        for x in H:
            c[x['rid']] += 1
        g = Counter(c.values())
        print(f'  {ba} hp<=1/3 {len(H)}頭 / {len(c)}鞍　'
              f'1鞍あたりの該当頭数 '
              + '　'.join(f'{k}頭:{v}鞍' for k, v in sorted(g.items())))
        print('  → 1鞍1頭の鞍が多いので、同じ鞍から同数を引く偽薬は'
              '該当馬そのものを引きやすい。⑧の偽薬は該当と大きく重なる。')

    # ── 偽薬：層を単勝30pt以上超えた形だけ ───────────────────
    print('\n=== 偽薬（層を単勝回収で30pt以上超えた形だけ）===')
    cand = []
    for lab, (S, o) in D1.items():
        cand.append((f'① {lab}', S, und_d, o, NB.ev(und_d, mid)['tan'],
                     'wt_diff が出せた人気薄'))
    for lab, (S, o) in R1.items():
        cand.append((f'③ {lab}', S, und_r, o, NB.ev(und_r, mid)['tan'],
                     'rest が出せた人気薄'))
    base5 = NB.ev(both, mid)['tan']
    for lab, (S, o) in C5.items():
        cand.append((f'⑤ {lab}', S, both, o, base5, '両方出せた人気薄'))
    cand.append(('⑥ |wt_diff|>=15kg', S6, und_d, o6,
                 NB.ev(und_d, mid)['tan'], 'wt_diff が出せた人気薄'))
    for (ba, lab), (S, bd, o) in D7.items():
        b = NB.ev(bd, mid)
        if not b['short']:
            cand.append((f'⑦ {ba} {lab}', S, bd, o, b['tan'],
                         f'{ba} の wt_diff が出せた人気薄'))
    for (ba, lab), (S, hpd, o) in D8.items():
        b = NB.ev(hpd, mid)
        if not b['short']:
            cand.append((f'⑧ {ba} hp<=1/3 {lab}', S, hpd, o, b['tan'],
                         f'{ba} の hp<=1/3 ＆ wt_diff が出せた人気薄'))

    # ── まとめ：前後半の両方で層を超えたか（目で選ばず機械的に）──
    print('\n=== まとめ：前半と後半の両方で層を超えた形 ===')
    print('  条件：前半・後半どちらも20頭以上あり、どちらも層の同じ期間の'
          '単勝回収を超える。')
    kept = []
    for lab, S, p, o, base, pl in cand:
        if o['short']:
            continue
        b = NB.ev(p, mid)
        if b['short']:
            continue
        if o['a_n'] < NB.MIN_N or o['b_n'] < NB.MIN_N:
            print(f'  × {lab}　{o["n"]}頭　前半{o["a_n"]}頭/後半{o["b_n"]}頭　'
                  f'片方が20頭未満。前後半の確かめができない')
            continue
        ok = (o['a_tan'] > b['a_tan']) and (o['b_tan'] > b['b_tan'])
        mark = '○' if ok else '×'
        print(f'  {mark} {lab}　{o["n"]}頭　単{o["tan"]:.1f}%（層{b["tan"]:.1f}%）'
              f'　前半{o["a_tan"]:.1f}/層{b["a_tan"]:.1f}　'
              f'後半{o["b_tan"]:.1f}/層{b["b_tan"]:.1f}')
        if ok:
            kept.append((lab, o, b))
    print(f'  → 前後半の両方で層を超えた形 {len(kept)}件')
    kl = {lab for lab, o, b in kept}
    for lab, o, b in kept:
        print(f'     {lab}　単{o["tan"]:.1f}%（層{b["tan"]:.1f}% / '
              f'+{o["tan"]-b["tan"]:.1f}pt）　'
              f'最大1頭抜き 単{o["tan_nomax"]:.1f}%（層{b["tan_nomax"]:.1f}%）')
    print('\n  残った4件には、30pt基準と関係なく偽薬を置く')
    for lab, S, p, o, base, pl in cand:
        if lab in kl:
            print(f'  ◆ {lab}　{o["n"]}頭　単{o["tan"]:.1f}%')
            pla(S, p, mid, label=pl)

    # ══ 訂正：該当馬自身の日付の中央で割り直す ═══════════════
    print('\n' + '=' * 72)
    print('【訂正】ここから下は「該当馬自身の日付の中央」で割り直した数字。')
    print('層も該当馬と同じ期間に絞る。上の mid（全体の中央 '
          f'{mid}）版は消さずに残してある。')
    print('=' * 72)

    print('\n=== 割り方の検算（川崎 人気薄 × hp<=1/3 の251頭）===')
    kw = [x for x in pool if x['ba'] == '川崎' and x['pop'] >= 6]
    k251 = [x for x in kw if x['hn'] >= NB.HP_MIN and x['hp'] is not None
            and x['hp'] <= 1 / 3]
    print('  全体の中央で割った場合：')
    line(k251, '川崎 人気薄 × hp<=1/3', mid, pad=26)
    A, B = [x for x in k251 if x['ymd'] < mid], [x for x in k251
                                                 if x['ymd'] >= mid]
    for k, T in (('前半', A), ('後半', B)):
        t = rr(T)
        print(f'    {k}　{t["n"]}頭　{wtxt(t["w"])}　単{t["tan"]:.1f}%')
    print('  該当馬自身の中央で割った場合：')
    h2(k251, kw, '川崎 人気薄 × hp<=1/3')
    print('  （予定 前半80頭150.8%・1着5頭／後半171頭169.5%・1着7頭）')

    print('\n=== 訂正版：①〜⑧の全セル ===')
    H = []
    for lab, S, p, o, base, pl in cand:
        r = h2(S, p, lab)
        if r is not None:
            H.append((lab, S, p, r, pl))

    print('\n=== 訂正版のまとめ ===')
    kept2 = [(lab, r) for lab, S, p, r, pl in H
             if not r['short'] and r['ok'] and r['valid']]
    nv = [(lab, r) for lab, S, p, r, pl in H
          if not r['short'] and r['ok'] and not r['valid']]
    print(f'  両期で同期間の層を超え、かつ検定として成立した形 {len(kept2)}件')
    for lab, r in kept2:
        print(f'    ○ {lab}　{r["n"]}頭　単{r["tan"]:.1f}%'
              f'（同期間の層{r["base"]:.1f}% / +{r["tan"]-r["base"]:.1f}pt）　'
              f'前半{r["a"]["tan"]:.1f}%（1着{r["a"]["nw"]}頭）/層'
              f'{r["pa"]["tan"]:.1f}%　'
              f'後半{r["b"]["tan"]:.1f}%（1着{r["b"]["nw"]}頭）/層'
              f'{r["pb"]["tan"]:.1f}%　最大1頭抜き 単{r["nomax"]:.1f}%')
    print(f'  両期で層を超えたが、検定として成立しない形 {len(nv)}件'
          '（どちらかの期が20頭未満か1着3頭未満）')
    for lab, r in nv:
        print(f'    △ {lab}　{r["n"]}頭　単{r["tan"]:.1f}%　'
              f'前半{r["a"]["n"]}頭/1着{r["a"]["nw"]}頭　'
              f'後半{r["b"]["n"]}頭/1着{r["b"]["nw"]}頭')

    print('\n=== 訂正版：同期間の層を単勝30pt以上超えた形に偽薬 ===')
    n30 = 0
    for lab, S, p, r, pl in H:
        if r['short'] or r['tan'] - r['base'] < GAP:
            continue
        n30 += 1
        print(f'  ◆ {lab}　{r["n"]}頭　単{r["tan"]:.1f}%'
              f'（同期間の層{r["base"]:.1f}% / +{r["tan"]-r["base"]:.1f}pt）　'
              f'検定として成立 {"する" if r["valid"] else "しない"}')
        pla(S, p, mid, label=pl)
    if not n30:
        print('  該当なし')

    print('\n=== 訂正版：残った形に偽薬（30pt基準と関係なく）===')
    for lab, S, p, r, pl in H:
        if r['short'] or not (r['ok'] and r['valid']):
            continue
        if r['tan'] - r['base'] >= GAP:
            continue        # 上で置いた
        print(f'  ◆ {lab}　{r["n"]}頭　単{r["tan"]:.1f}%'
              f'（同期間の層{r["base"]:.1f}%）')
        pla(S, p, mid, label=pl)

    done = 0
    for lab, S, p, o, base, pl in cand:
        if o['short'] or o['tan'] - base < GAP:
            continue
        done += 1
        print(f'  ◆ {lab}　{o["n"]}頭　単{o["tan"]:.1f}%'
              f'（層{base:.1f}% / +{o["tan"]-base:.1f}pt）　'
              f'最大1頭抜き 単{o["tan_nomax"]:.1f}%')
        pla(S, p, mid, label=pl)
    if not done:
        print('  該当なし（層を単勝回収で30pt以上超えた形は無かった）')


if __name__ == '__main__':
    main(*(sys.argv[1:] or []))
