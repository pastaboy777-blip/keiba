# -*- coding: utf-8 -*-
"""年齢が人気薄の単勝回収に効くのかを精査する（E班）。

  python3 -I scripts/ana/body_age.py [body.jsonl]

土台は scripts/ana/nankan_body.py を読み込んで使う（結合は書き直さない）。
測る形は先に5つ決めてあり、結果を見てから条件を足さない。

  ① 船橋 × 人気薄 × 年齢4帯（2〜3 / 4〜5 / 6〜7 / 8歳以上）
  ② 年齢1歳刻み（人気薄・南関4場と船橋）。6歳と7歳を分ける
  ③ 年齢は何の言い換えか。hp / hn / sx_k / dist / kin の分布を
     6〜7歳とそれ以外で比べ、帯をそろえてから回収を比べる
  ④ 人気帯をそろえる（6〜7 / 8〜10 / 11番人気以降）を場ごとに
  ⑤ 偽薬200回。該当馬を除いて引く版と、6〜7歳以外から引く版

守っていること（CLAUDE.md「検証の作法」）
・前半／後半は**該当馬それ自身の開催日の中央**で割る。層も同じ境目で割り、
  同じ期間・同じ場に絞る。各期の1着の頭数を必ず出し、片方が3頭未満なら
  「検定として成立していない」と書く。
・集中度は該当の上位1,2,3,5頭を**該当と層の両方から**抜いて比べる。
・偽薬は200回。5回では分布の端が見えない。該当馬自身を引かないように除く。
・人気帯をそろえる。全体の差は人気の構成の差かもしれない。
・浦和を使うときは上位3頭を抜いた値を併記する。
"""
import os
import statistics as st
import sys
from collections import Counter, defaultdict
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nankan_body import BODY, MIN_N, load_body  # noqa: E402

SEED = 20261114
MIN_W = 3          # 片方の期の1着がこれ未満なら検定として成立しない
K = 200            # 偽薬の回数

AGE4 = (('2〜3歳', 2, 3), ('4〜5歳', 4, 5),
        ('6〜7歳', 6, 7), ('8歳以上', 8, 99))
BA4 = ('川崎', '大井', '船橋', '浦和')
POPB = (('6〜7番人気', 6, 7), ('8〜10番人気', 8, 10), ('11番人気以降', 11, 99))


# ── 小道具 ────────────────────────────────────────────────────
def kx(x):
    return (x['rid'], x['u'])


def inage(x, lo, hi):
    return x['age'] is not None and lo <= x['age'] <= hi


def cut(S):
    """該当馬それ自身の開催日の中央で前半／後半に割る。"""
    d = sorted({x['ymd'] for x in S})
    m = d[len(d) // 2]
    return [x for x in S if x['ymd'] < m], [x for x in S if x['ymd'] >= m]


def cutm(S):
    d = sorted({x['ymd'] for x in S})
    return d[len(d) // 2]


def rr(S):
    """頭数・1着の頭数・単・複・3着内。母数が少なくても数字は出し旗を立てる。"""
    n = len(S)
    if not n:
        return None
    w = sorted(((x.get('ptan') or 0) for x in S if x['f'] == 1), reverse=True)
    return dict(n=n, nw=len(w), w=w,
                tan=sum((x.get('ptan') or 0) for x in S) / n,
                fuku=sum((x.get('pfuku') or 0) for x in S) / n,
                top3=sum(1 for x in S if x['f'] <= 3) / n * 100,
                lo=min(x['ymd'] for x in S), hi=max(x['ymd'] for x in S))


def nomax(S, k=1):
    """上位k頭の単払戻を0にしたときの単勝回収（分母はそのまま）。"""
    o = rr(S)
    return (sum(o['w']) - sum(o['w'][:k])) / o['n']


def wtxt(w):
    if not w:
        return '1着0頭'
    return (f'1着{len(w)}頭（'
            + '＋'.join(f'{v:,.0f}' for v in w[:4])
            + ('…' if len(w) > 4 else '') + '円）')


def head(S, label, pad=18):
    o = rr(S)
    if o is None:
        print(f'  {label:<{pad}}0頭')
        return None
    s = (f'  {label:<{pad}}{o["n"]:>5}頭　3着内{o["top3"]:>5.1f}%　'
         f'{wtxt(o["w"])}　単{o["tan"]:>6.1f}%　複{o["fuku"]:>6.1f}%')
    if o['nw']:
        s += f'　｜最大1頭({o["w"][0]:>6,.0f}円)抜き 単{nomax(S):>6.1f}%'
    if o['n'] < MIN_N:
        s += '　※母数不足'
    print(s)
    return o


# ── 前後半（該当馬自身の中央で割る）──────────────────────────
def halves(S, pool, pad=4):
    """該当馬自身の中央で割り、同じ期間に絞った層と並べる。

    返すのは dict(ok=両期で層超え, valid=両期で1着3頭以上 かつ 20頭以上)
    """
    o = rr(S)
    if o is None or o['n'] < 2:
        print('      前後半　割れない')
        return dict(ok=False, valid=False)
    m = cutm(S)
    P = [x for x in pool if o['lo'] <= x['ymd'] <= o['hi']]
    A, B = cut(S)
    PA = [x for x in P if x['ymd'] < m]
    PB = [x for x in P if x['ymd'] >= m]
    pf = rr(P)
    sp = ' ' * pad
    print(f'{sp}期間 {o["lo"]}〜{o["hi"]}　分割日 {m}（該当馬自身の中央）　'
          f'同期間の層 {pf["n"]}頭 1着{pf["nw"]}頭 単{pf["tan"]:.1f}%')
    res = []
    for k, T, PT in (('前半', A, PA), ('後半', B, PB)):
        t, p = rr(T), rr(PT)
        if t is None or p is None:
            print(f'{sp}{k}　該当0頭')
            res.append((None, None))
            continue
        flag = ''
        if t['n'] < MIN_N:
            flag += '　※母数不足'
        if t['nw'] < MIN_W:
            flag += f'　※1着{t["nw"]}頭。検定として成立していない'
        print(f'{sp}{k}　該当 {t["n"]:>5}頭 1着{t["nw"]:>3}頭 '
              f'単{t["tan"]:>6.1f}% 複{t["fuku"]:>6.1f}%　｜'
              f'層 {p["n"]:>5}頭 1着{p["nw"]:>3}頭 単{p["tan"]:>6.1f}%'
              f'（差 {t["tan"]-p["tan"]:+.1f}pt）{flag}')
        res.append((t, p))
    (ta, pa), (tb, pb) = res
    if ta is None or tb is None:
        return dict(ok=False, valid=False)
    ok = ta['tan'] > pa['tan'] and tb['tan'] > pb['tan']
    dn = ta['tan'] < pa['tan'] and tb['tan'] < pb['tan']
    valid = (ta['n'] >= MIN_N and tb['n'] >= MIN_N
             and ta['nw'] >= MIN_W and tb['nw'] >= MIN_W)
    print(f'{sp}判定　両期で層超え {"はい" if ok else "いいえ"}　'
          f'両期で層以下 {"はい" if dn else "いいえ"}　／　'
          f'検定として成立 {"する" if valid else "しない"}'
          f'{"" if valid else "（1着の頭数が足りない）"}')
    return dict(ok=ok, dn=dn, valid=valid, a=ta, b=tb, pa=pa, pb=pb)


# ── 公平な集中度 ──────────────────────────────────────────────
def conc(S, pool, ks=(1, 2, 3, 5), pad=4):
    """該当の上位k頭を該当と層の両方から抜いて差を見る。"""
    sp = ' ' * pad
    o, p = rr(S), rr(pool)
    ids = []
    for x in sorted(S, key=lambda y: -(y.get('ptan') or 0)):
        if x['f'] == 1 and (x.get('ptan') or 0) > 0:
            ids.append(kx(x))
    print(f'{sp}公平な集中度（該当の上位k頭を該当と層の両方から抜く）')
    print(f'{sp}  抜く前　該当{o["tan"]:>7.1f}%　層{p["tan"]:>7.1f}%　'
          f'差{o["tan"]-p["tan"]:+7.1f}pt')
    out = {}
    for k in ks:
        if len(ids) < k:
            print(f'{sp}  {k}頭抜き　1着が{len(ids)}頭しかない')
            continue
        cutids = set(ids[:k])
        a = sum((x.get('ptan') or 0) for x in S
                if kx(x) not in cutids) / o['n']
        b = sum((x.get('ptan') or 0) for x in pool
                if kx(x) not in cutids) / p['n']
        out[k] = a - b
        print(f'{sp}  {k}頭抜き　該当{a:>7.1f}%　層{b:>7.1f}%　'
              f'差{a-b:+7.1f}pt')
    W = [x for x in S if x['f'] == 1]
    if W:
        nm = Counter(x['nm'] for x in W)
        dd = len({x['ymd'] for x in W})
        rep = [f'{k}×{v}' for k, v in nm.items() if v > 1]
        print(f'{sp}  1着{len(W)}頭の内訳　のべ馬名{len(nm)}頭　開催日{dd}日'
              + (f'　2勝以上 {"・".join(rep)}' if rep else '　重複なし'))
    tops = sorted(((x.get('ptan') or 0), x['nm'], x['ymd'], x['ba'], x['age'])
                  for x in S if x['f'] == 1)[::-1][:5]
    print(f'{sp}  該当の上位5頭　' + ' / '.join(
        f'{v:,.0f}円({nm} {y} {b} {a}歳)' for v, nm, y, b, a in tops))
    # 日単位の集中度。同じ開催日に2頭来ると、馬1頭ずつ抜くだけでは見えない。
    byd = defaultdict(float)
    for x in S:
        byd[x['ymd']] += (x.get('ptan') or 0)
    days = sorted(byd, key=lambda k: -byd[k])
    print(f'{sp}  日単位　該当の開催日 {len({x["ymd"] for x in S})}日　'
          + '　'.join(
              f'上位{k}日抜き 該当'
              f'{sum((x.get("ptan") or 0) for x in S if x["ymd"] not in set(days[:k]))/o["n"]:.1f}%'
              f'/層{sum((x.get("ptan") or 0) for x in pool if x["ymd"] not in set(days[:k]))/p["n"]:.1f}%'
              for k in (1, 2, 3) if len(days) > k))
    return out


# ── 偽薬 ──────────────────────────────────────────────────────
def draw(S, pool, k=K, excl=None, seed=SEED):
    """同じ鞍から同数を無作為に引く。excl にある馬は引かない。

    返すのは [引いた馬のリスト, ...]（k 本）。
    """
    need = Counter(x['rid'] for x in S)
    ex = excl or set()
    byr = defaultdict(list)
    for x in pool:
        if kx(x) not in ex:
            byr[x['rid']].append(x)
    out = []
    for t in range(k):
        rng = random.Random(seed + 1000 * (t + 1))
        T = []
        for rid, m in need.items():
            c = byr.get(rid, [])
            if c:
                T += rng.sample(c, min(m, len(c)))
        out.append(T)
    return out


def expect(S, pool, excl=None):
    """偽薬の厳密な期待値。Σ m_鞍×(その鞍の母集団の平均単払戻) ÷ Σ m_鞍。

    引ける馬がいない鞍は分母からも落とす（偽薬の引き方にそろえる）。
    """
    need = Counter(x['rid'] for x in S)
    ex = excl or set()
    byr = defaultdict(list)
    for x in pool:
        if kx(x) not in ex:
            byr[x['rid']].append(x)
    num = den = 0.0
    for rid, m in need.items():
        c = byr.get(rid, [])
        if not c:
            continue
        mm = min(m, len(c))
        num += mm * st.fmean((y.get('ptan') or 0) for y in c)
        den += mm
    return (num / den) if den else None


def placebo(S, pool, label, excl=None, k=K, pad=4):
    sp = ' ' * pad
    obs = rr(S)['tan']
    Ts = draw(S, pool, k=k, excl=excl)
    v = sorted(sum((y.get('ptan') or 0) for y in T) / len(T)
               for T in Ts if T)
    if not v:
        print(f'{sp}偽薬（{label}）　引ける馬がいない')
        return None
    n_mean = st.fmean(len(T) for T in Ts if T)
    over = sum(1 for z in v if z >= obs)
    e = expect(S, pool, excl=excl)
    print(f'{sp}偽薬{k}回（{label}）　1回あたり{n_mean:.0f}頭　'
          f'最小{v[0]:.1f} / 5%点{v[len(v)//20]:.1f} / 中央{v[len(v)//2]:.1f} / '
          f'95%点{v[int(len(v)*0.95)]:.1f} / 最大{v[-1]:.1f}%')
    print(f'{sp}  該当{obs:.1f}%以上が出た偽薬 {over}/{len(v)}回'
          f'（{over/len(v)*100:.1f}%）　厳密な期待値{e:.1f}%'
          f'（該当との差 {obs-e:+.1f}pt）')
    return dict(v=v, over=over, e=e, obs=obs)


# ── 人気帯をそろえる ──────────────────────────────────────────
def pops(S, pool, pad=4):
    sp = ' ' * pad
    print(f'{sp}人気帯をそろえる')
    for lab, lo, hi in POPB:
        a = [x for x in S if x['pop'] is not None and lo <= x['pop'] <= hi]
        b = [x for x in pool if x['pop'] is not None and lo <= x['pop'] <= hi]
        oa, ob = rr(a), rr(b)
        if oa is None or ob is None:
            print(f'{sp}  {lab:<12}該当0頭')
            continue
        flag = '　※母数不足' if oa['n'] < MIN_N else ''
        if oa['nw'] < MIN_W:
            flag += f'　※1着{oa["nw"]}頭'
        print(f'{sp}  {lab:<12}該当 {oa["n"]:>5}頭 1着{oa["nw"]:>3}頭 '
              f'単{oa["tan"]:>7.1f}% 複{oa["fuku"]:>6.1f}%　｜'
              f'層 {ob["n"]:>5}頭 1着{ob["nw"]:>3}頭 単{ob["tan"]:>6.1f}%'
              f'（差 {oa["tan"]-ob["tan"]:+.1f}pt）{flag}')


def months(S, pool, pad=4):
    """月ごとの内訳。前後半の2分割が「どの時期で出来ているか」を見るため。

    2分割は境目の置き方で見え方が変わる。月で並べると、ある時期だけで
    出来ている形が分かる（4帯すべてに同じように当てる。選んだ帯だけに
    当てる後付けの道具にしない）。
    """
    sp = ' ' * pad
    ms = sorted({x['ymd'][:6] for x in pool})
    out = []
    for m in ms:
        a = [x for x in S if x['ymd'][:6] == m]
        b = [x for x in pool if x['ymd'][:6] == m]
        if not b:
            continue
        if not a:
            out.append(f'{m[4:]}月 該当0頭')
            continue
        oa, ob = rr(a), rr(b)
        out.append(f'{m[4:]}月 {oa["n"]:>3}頭/1着{oa["nw"]}頭 '
                   f'{oa["tan"]:>5.1f}%(層{ob["tan"]:.1f})')
    print(f'{sp}月ごと　' + '　｜'.join(out))


def full(S, pool, label, ref_label, excl_self=True, k=K):
    """全部の関門を1か所で通す。"""
    print(f'\n── {label}（層は{ref_label}）──')
    o = head(S, '該当', pad=6)
    p = head(pool, '層　', pad=6)
    if o is None or p is None:
        return None
    print(f'      層との差　単{o["tan"]-p["tan"]:+.1f}pt　'
          f'複{o["fuku"]-p["fuku"]:+.1f}pt')
    h = halves(S, pool)
    c = conc(S, pool)
    ex = {kx(x) for x in S} if excl_self else None
    pl = placebo(S, pool, '該当馬を除いて引く', excl=ex, k=k)
    pops(S, pool)
    return dict(label=label, o=o, p=p, h=h, c=c, pl=pl)


# ── ③ 言い換えの点検 ─────────────────────────────────────────
def share(S, bands, key, label, pad=6):
    sp = ' ' * pad
    n = sum(1 for x in S if x[key] is not None)
    out = []
    for lab, fn in bands:
        c = sum(1 for x in S if x[key] is not None and fn(x[key]))
        out.append(f'{lab} {c/n*100:.1f}%' if n else f'{lab} ―')
    print(f'{sp}{label:<10}出せた{n:>5}頭　' + '　'.join(out))


def strat(S, T, pool, bands, key, label, pad=6):
    """帯をそろえてから、該当（6〜7歳）とそれ以外の単勝回収を比べる。"""
    sp = ' ' * pad
    print(f'{sp}{label}の帯をそろえて 6〜7歳 と それ以外 を比べる')
    for lab, fn in bands:
        a = [x for x in S if x[key] is not None and fn(x[key])]
        b = [x for x in T if x[key] is not None and fn(x[key])]
        oa, ob = rr(a), rr(b)
        if oa is None or ob is None:
            print(f'{sp}  {lab:<12}どちらかが0頭')
            continue
        fa = '' if oa['n'] >= MIN_N else '　※母数不足'
        if oa['nw'] < MIN_W:
            fa += f'　※1着{oa["nw"]}頭。検定として成立していない'
        print(f'{sp}  {lab:<12}6〜7歳 {oa["n"]:>5}頭 1着{oa["nw"]:>3}頭 '
              f'単{oa["tan"]:>7.1f}%　｜それ以外 {ob["n"]:>5}頭 '
              f'1着{ob["nw"]:>3}頭 単{ob["tan"]:>6.1f}%　'
              f'差{oa["tan"]-ob["tan"]:+7.1f}pt{fa}')


def main(path=BODY):
    rows, _ = load_body(path)
    pool = [x for x in rows if x['ptan'] is not None and x['n'] >= 6]
    und = [x for x in pool if x['pop'] is not None and x['pop'] >= 6]
    print(f'{len(rows)}頭を読んだ　層（払戻あり・完走6頭以上）{len(pool)}頭　'
          f'人気薄（6番人気以降）{len(und)}頭')
    o = rr(und)
    print(f'  人気薄　{o["n"]}頭　1着{o["nw"]}頭　単{o["tan"]:.1f}%　'
          f'複{o["fuku"]:.1f}%')

    FU = [x for x in und if x['ba'] == '船橋']
    o = rr(FU)
    print(f'  人気薄×船橋　{o["n"]}頭　1着{o["nw"]}頭　単{o["tan"]:.1f}%　'
          f'複{o["fuku"]:.1f}%　上位3頭抜き{nomax(FU,3):.1f}%')

    # ────────────────────────────────────────────────────────
    print('\n\n==================== ① 船橋 × 人気薄 × 年齢4帯 '
          '====================')
    for lab, lo, hi in AGE4:
        S = [x for x in FU if inage(x, lo, hi)]
        full(S, FU, f'船橋 × 人気薄 × {lab}', '船橋の人気薄')
        months(S, FU)

    print('\n  ◆船橋の年齢4帯の並び（南関全体と同じ形か）')
    for who, P in (('南関4場', und), ('船橋', FU)):
        s = []
        for lab, lo, hi in AGE4:
            S = [x for x in P if inage(x, lo, hi)]
            q = rr(S)
            s.append(f'{lab} {q["tan"]:.1f}%({q["n"]}頭/1着{q["nw"]})')
        print(f'    {who:<8}' + '　'.join(s))

    # ────────────────────────────────────────────────────────
    print('\n\n==================== ② 年齢1歳刻み ====================')
    for who, P, ref in (('南関4場', und, '人気薄'),
                        ('船橋', FU, '船橋の人気薄')):
        print(f'\n  ◆{who}の人気薄（1歳刻み）')
        base = rr(P)
        for a in range(2, 11):
            S = [x for x in P if x['age'] == a]
            q = rr(S)
            if q is None:
                continue
            fl = ''
            if q['n'] < MIN_N:
                fl += '　※母数不足'
            if q['nw'] < MIN_W:
                fl += f'　※1着{q["nw"]}頭。検定として成立していない'
            print(f'    {a}歳　{q["n"]:>5}頭　1着{q["nw"]:>3}頭　'
                  f'3着内{q["top3"]:>5.1f}%　単{q["tan"]:>7.1f}%　'
                  f'複{q["fuku"]:>6.1f}%　層差{q["tan"]-base["tan"]:+7.1f}pt　'
                  f'最大1頭抜き{nomax(S):>6.1f}%{fl}')
        for a in (6, 7):
            S = [x for x in P if x['age'] == a]
            full(S, P, f'{who} × 人気薄 × {a}歳', ref)

    # ────────────────────────────────────────────────────────
    print('\n\n==================== ③ 年齢は何の言い換えか '
          '====================')
    HPB = (('前1/3(hp<=1/3)', lambda v: v <= 1 / 3),
           ('中1/3', lambda v: 1 / 3 < v <= 2 / 3),
           ('後1/3', lambda v: v > 2 / 3))
    HNB = (('0〜4走', lambda v: v <= 4), ('5〜14走', lambda v: 5 <= v <= 14),
           ('15走以上', lambda v: v >= 15))
    DB = (('〜1200m', lambda v: v <= 1200),
          ('1300〜1500m', lambda v: 1300 <= v <= 1500),
          ('1600m〜', lambda v: v >= 1600))
    KB = (('〜53kg', lambda v: v <= 53.0),
          ('54kg', lambda v: 53.0 < v <= 54.0),
          ('55kg', lambda v: 54.0 < v <= 55.0),
          ('56kg以上', lambda v: v >= 55.5))
    SB = (('牡', lambda v: v == '牡'), ('牝', lambda v: v == '牝'),
          ('セ', lambda v: v == 'セ'))

    print('  ◆先に hn の中身を確かめる（「長く使われている馬」の代わりに'
          'なるか）')
    hn = [x['hn'] for x in und]
    print(f'    hn はこのデータ（2026年）の中の走数。最小{min(hn)}　'
          f'中央{st.median(hn):.0f}　最大{max(hn)}　'
          f'10走以上 {sum(1 for v in hn if v >= 10)}頭')
    print('    → 1年分しかないので、キャリアの長さの代わりにはならない。'
          '年齢の言い換え先として hn は使えない')

    print('\n  ◆鞍の年齢制限（2〜3歳戦があるので年齢は鞍の種類と絡む）')
    for who, P in (('南関4場', und), ('船橋', FU)):
        byr = defaultdict(list)
        for x in P:
            byr[x['rid']].append(x)
        has = sum(1 for r, g in byr.items() if any(inage(y, 6, 7) for y in g))
        y23 = sum(1 for r, g in byr.items()
                  if all(inage(y, 2, 3) for y in g))
        print(f'    {who:<8}人気薄がいる鞍 {len(byr)}　'
              f'6〜7歳の人気薄がいる鞍 {has}（{has/len(byr)*100:.1f}%）　'
              f'人気薄が全部2〜3歳の鞍 {y23}（{y23/len(byr)*100:.1f}%）')

    for who, P in (('南関4場', und), ('船橋', FU)):
        S = [x for x in P if inage(x, 6, 7)]
        T = [x for x in P if x['age'] is not None and not inage(x, 6, 7)]
        print(f'\n  ◆{who}の人気薄　6〜7歳 {len(S)}頭 / それ以外 {len(T)}頭')
        print('    分布を比べる')
        for nmv, G in (('6〜7歳', S), ('それ以外', T)):
            print(f'      〔{nmv}〕')
            share(G, HPB, 'hp', 'hp(ふだんの4角)', pad=8)
            share(G, HNB, 'hn', 'hn(走数)', pad=8)
            share(G, SB, 'sx_k', 'sx_k(性)', pad=8)
            share(G, DB, 'dist', 'dist(距離)', pad=8)
            share(G, KB, 'kin', 'kin(斤量)', pad=8)
            hn = [x['hn'] for x in G if x['hn'] is not None]
            hp = [x['hp'] for x in G if x['hp'] is not None]
            kn = [x['kin'] for x in G if x['kin'] is not None]
            pp = [x['pop'] for x in G if x['pop'] is not None]
            print(f'        中央値　hn {st.median(hn):.0f}走　'
                  f'hp {st.median(hp):.2f}（出せた{len(hp)}頭）　'
                  f'kin {st.median(kn):.1f}kg　人気 {st.median(pp):.0f}番人気')
        print('    帯をそろえてから回収を比べる')
        strat(S, T, P, HNB, 'hn', 'hn(走数)')
        strat(S, T, P, HPB, 'hp', 'hp(ふだんの4角位置)')
        strat(S, T, P, SB, 'sx_k', 'sx_k(性)')
        strat(S, T, P, DB, 'dist', 'dist(距離)')
        strat(S, T, P, KB, 'kin', 'kin(斤量)')

    # ────────────────────────────────────────────────────────
    print('\n\n==================== ④ 人気帯をそろえる（場ごと）'
          ' ====================')
    for ba in BA4:
        P = [x for x in und if x['ba'] == ba]
        S = [x for x in P if inage(x, 6, 7)]
        oa, ob = rr(S), rr(P)
        print(f'\n  ◆{ba}　6〜7歳 {oa["n"]}頭 1着{oa["nw"]}頭 '
              f'単{oa["tan"]:.1f}%（上位3頭抜き{nomax(S,3):.1f}%）　｜'
              f'層 {ob["n"]}頭 1着{ob["nw"]}頭 単{ob["tan"]:.1f}%'
              f'（上位3頭抜き{nomax(P,3):.1f}%）　'
              f'差{oa["tan"]-ob["tan"]:+.1f}pt')
        conc(S, P)
        pops(S, P)
    P = [x for x in und if x['ba'] != '浦和']
    S = [x for x in P if inage(x, 6, 7)]
    oa, ob = rr(S), rr(P)
    print(f'\n  ◆浦和を除く3場　6〜7歳 {oa["n"]}頭 1着{oa["nw"]}頭 '
          f'単{oa["tan"]:.1f}%（上位3頭抜き{nomax(S,3):.1f}%）　｜'
          f'層 {ob["n"]}頭 1着{ob["nw"]}頭 単{ob["tan"]:.1f}%'
          f'（上位3頭抜き{nomax(P,3):.1f}%）　差{oa["tan"]-ob["tan"]:+.1f}pt')
    conc(S, P)
    pops(S, P)

    print('\n  ◆比べるための全力検定（4場まとめ と 浦和を除く3場）')
    S = [x for x in und if inage(x, 6, 7)]
    full(S, und, '南関4場 × 人気薄 × 6〜7歳', '人気薄')
    P = [x for x in und if x['ba'] != '浦和']
    S = [x for x in P if inage(x, 6, 7)]
    full(S, P, '浦和を除く3場 × 人気薄 × 6〜7歳', '浦和を除く人気薄')

    # ────────────────────────────────────────────────────────
    print('\n\n==================== ⑤ 偽薬を年齢を無視した形で置く '
          '====================')
    for who, P in (('南関4場', und), ('船橋', FU),
                   ('浦和を除く3場', [x for x in und if x['ba'] != '浦和'])):
        S = [x for x in P if inage(x, 6, 7)]
        if len(S) < MIN_N:
            print(f'\n  ◆{who}　{len(S)}頭　母数不足')
            continue
        print(f'\n  ◆{who} × 人気薄 × 6〜7歳　{len(S)}頭　'
              f'1着{rr(S)["nw"]}頭　単{rr(S)["tan"]:.1f}%')
        ex_self = {kx(x) for x in S}
        placebo(S, P, '同じ鞍の人気薄から該当馬を除いて引く', excl=ex_self)
        ex_age = {kx(x) for x in P if inage(x, 6, 7)}
        placebo(S, P, '同じ鞍の人気薄のうち6〜7歳以外から引く', excl=ex_age)
        same = ex_self == ex_age
        print(f'    2つの偽薬の引ける馬の集合が同じか：'
              f'{"同じ" if same else "違う"}'
              + ('（該当が年齢だけで決まっているので、除く馬が一致する。'
                 'この2つは同じ引き方になる）' if same else ''))
        # 鞍の性質そのものを見る：該当がいる鞍の人気薄だけを層にする
        rids = {x['rid'] for x in S}
        Q = [x for x in P if x['rid'] in rids]
        oq = rr(Q)
        Qo = [x for x in Q if kx(x) not in ex_age]
        oo = rr(Qo)
        print(f'    該当がいる鞍の人気薄すべて　{oq["n"]}頭 1着{oq["nw"]}頭 '
              f'単{oq["tan"]:.1f}%　｜そのうち6〜7歳以外 {oo["n"]}頭 '
              f'1着{oo["nw"]}頭 単{oo["tan"]:.1f}%　｜'
              f'該当 単{rr(S)["tan"]:.1f}%')


if __name__ == '__main__':
    main(*(sys.argv[1:2] or []))
