# -*- coding: utf-8 -*-
"""南関の「1行1頭」の土台を組み、払戻で測る。

  python3 -I scripts/ana/nankan_body.py build [raw.jsonl payout.jsonl out.jsonl]
  python3 -I scripts/ana/nankan_body.py check [body.jsonl]

build が出すのは1行1頭の JSONL。鞍の識別・馬体・性齢・4角の配置・
その日より前の履歴を並べる。**日付順に進めて、その日より前の情報だけで作る**
（CLAUDE.md「未来の情報を入れない」）。履歴（hn/hp/wt_prev/wt_diff/rest）は
その鞍を履歴に積む**前**に読むので、自分の走りは入らない。

鞍の中で順位をつける列（wt_norm）は、同点を乱数で崩してから並べる。
`e` は着順表なので、`sorted()` の安定ソートに任せると同点の馬が着順で
上下に分かれ、偽の相関が出る（CLAUDE.md「同点を乱数で崩してから並べる」）。
乱数は random.Random(SEED) で、何度流しても同じ並びになる。

── 回収率の出し方 ───────────────────────────────────────────
オッズは要らない。外れた馬の払戻は0なので、来た馬の払戻だけで正確に出る。

  単勝回収率 = Σ(その馬の単勝払戻。1着でなければ0) ÷ (100円 × 頭数) × 100
  複勝回収率 = Σ(その馬の複勝払戻。3着内でなければ0) ÷ (100円 × 頭数) × 100

ただし単勝回収は分散が大きい。1頭の大穴で化けるので、ev() は必ず
「最大1頭を抜いた単勝回収」も並べる（分母は抜く前の頭数のまま。
251頭で最大の12,620円を抜くと 163.5% → 113.2%）。

母数が20頭未満のときは数字を出さず「母数不足。判定しない」と出す。

── 土台の決めごと（測る人はここを読んでから使う）─────────────
・1行1頭。入れるのは着順が数字の馬だけ（中止・除外は入れない）。20,011頭。
・`n` は完走頭数。楽天の出走頭数（取消前）とは248鞍でずれる。
  c4 の正規化も wt_norm も wt_med も、この完走頭数の中で取る。
・層の母数は「払戻があって、完走6頭以上の鞍」= 19,889頭。
  既存スクリプトと同じ n>=6。6頭未満の122頭は鞍の中の相対が意味を持たない。
  6番人気以降は必ず n>=6 の鞍なので、絞っても人気薄の数字は変わらない。
・複勝が2着内までしか付かない鞍が、完走6〜7頭で104鞍ある。
  そこで3着だった104頭は f<=3 でも pfuku=0。3着内率と複勝回収はずれる。
・1着同着が3鞍、3着同着がある鞍もある。同着の馬はそれぞれ自分の払戻を持つ。
・`waku` は楽天が載せている枠を優先する（全頭にある）。waku() で計算すると
  取消があった鞍でずれるので、計算は枠が無いとき（カード）だけの保険。
・`hp` は直近8走の中央値、3走未満は None。`hn` は過去走の総数。
  どちらもその鞍を履歴に積む前に読むので、自分の走りは入らない。
・前半／後半の境目は、データ全体のレース開催日の中央値（load_body が返す）。
  条件ごとに境目を動かさないため、固定して使う。

groups() と waku() は scripts/ana/gait_join.py の実装をそのまま流用。
"""
import json
import os
import random
import re
import statistics as st
import sys
from collections import defaultdict
from datetime import date

SCR = ('/tmp/claude-0/-home-user-keiba/'
       'a716475a-b623-5ff0-8a6c-762d20462748/scratchpad')
RAW = os.path.join(SCR, 'nankan_raw.jsonl')
PAY = os.path.join(SCR, 'nankan_payout.jsonl')
BODY = os.path.join(SCR, 'nankan_body.jsonl')

SEED = 20261114          # 同点を崩す乱数。固定して再現できるようにする
HP_LAST = 8              # ふだんの4角位置は直近この走数の中央値
HP_MIN = 3               # 3走未満は判定しない
MIN_N = 20               # これ未満は母数不足


# ── gait_join.py からそのまま流用 ─────────────────────────────
def groups(s):
    """'(4,*10,13)(2,7)5' → [[4,10,13],[2,7],[5]] 並びは内→外"""
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == '(':
            j = s.find(')', i)
            g = [int(x) for x in re.findall(r'\d+', s[i:j + 1])]
            if g:
                out.append(g)
            i = j + 1
        elif c.isdigit():
            j = i
            while j < len(s) and s[j].isdigit():
                j += 1
            out.append([int(s[i:j])])
            i = j
        else:
            i += 1
    return out


def waku(u, n):
    if n < 8:
        return u            # 枠1〜nに1頭ずつ。空くのは外枠
    base, rem = divmod(n, 8)
    cnt = [base + (1 if (8 - i) < rem else 0) for i in range(1, 9)]
    s = 0
    for i, c in enumerate(cnt, 1):
        s += c
        if u <= s:
            return i
    return 8


# ── 小道具 ────────────────────────────────────────────────────
def inum(v):
    """'468' → 468。'-' や '' は None"""
    v = str(v if v is not None else '').strip()
    return int(v) if v.isdigit() else None


def fnum(v):
    """'55.0' → 55.0。数字でなければ None"""
    v = str(v if v is not None else '').strip()
    try:
        return float(v)
    except ValueError:
        return None


def d(ymd):
    """'20261113' → date(2026,11,13)"""
    return date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8]))


def sx_split(sx):
    """'牡2' → ('牡', 2)。'セ5' → ('セ', 5)"""
    sx = (sx or '').strip()
    m = re.match(r'^(.)(\d+)$', sx)
    return (m.group(1), int(m.group(2))) if m else (sx[:1] or None, None)


# ── 役割1：データセットを組む ─────────────────────────────────
def build(raw=RAW, pay=PAY, out=BODY, seed=SEED):
    """1行1頭の JSONL を書き出す。日付順に進めて履歴を積む。"""
    P = {}
    for l in open(pay, encoding='utf-8'):
        p = json.loads(l)
        P[p['rid']] = p

    # 日付順に並べる。同じ日はレースID順
    rows = sorted((json.loads(l) for l in open(raw, encoding='utf-8')),
                  key=lambda r: (r['ymd'], r['rid']))

    rng = random.Random(seed)
    HP = defaultdict(list)       # 馬名 → [4角の正規化位置]（古い順）
    LAST = {}                    # 馬名 → 直近走の (ymd, wt)
    nopay = nowt1 = 0
    f = open(out, 'w', encoding='utf-8')
    cnt = 0

    for r in rows:
        ent = [e for e in r['e'] if str(e.get('f', '')).isdigit()]
        n = len(ent)
        if n < 1:
            continue
        p = P.get(r['rid'])
        if p is None:
            nopay += 1
        tan = (p.get('tan') or {}) if p else {}
        fuku = (p.get('fuku') or {}) if p else {}

        # 4角：生順位・正規化・内外
        c4r, c4n, soto, rank = {}, {}, {}, 1
        for g in groups(r.get('c4') or ''):
            for i, u in enumerate(g):
                c4r[u] = rank
                c4n[u] = ((rank - 1) / (n - 1)) if n > 1 else None
                soto[u] = (i / (len(g) - 1)) if len(g) > 1 else None
            rank += len(g)

        # 馬体重：同点を乱数で崩してから鞍の中の順位をつける
        W = {}
        for e in ent:
            w = inum(e.get('wt'))
            if w is not None:
                W[int(e['u'])] = w
        wmed = st.median(W.values()) if W else None
        order = sorted(W, key=lambda u: (W[u], rng.random()))   # 軽い順
        wnorm = {}
        for i, u in enumerate(order):
            wnorm[u] = (i / (len(order) - 1)) if len(order) > 1 else None

        today = d(r['ymd'])
        batch = []
        for e in ent:
            u = int(e['u'])
            nm = e['nm']
            wt = W.get(u)
            kin = fnum(e.get('kin'))
            if wt is None:
                nowt1 += 1
            sk, age = sx_split(e.get('sx'))

            # ── 履歴はこの鞍を積む前に読む（未来の情報を入れない）──
            h = HP[nm][-HP_LAST:]
            hn = len(HP[nm])
            hp = st.median(h) if len(h) >= HP_MIN else None
            prev = LAST.get(nm)
            wt_prev = prev[1] if prev else None
            rest = (today - d(prev[0])).days if prev else None

            pop = inum(e.get('pop'))
            batch.append(dict(
                rid=r['rid'], ymd=r['ymd'], ba=r['ba'], R=r['R'], n=n,
                dist=r.get('dist'), surf=r.get('surf'), baba=r.get('baba'),
                u=u, nm=nm,
                f=int(e['f']), pop=pop,
                ptan=(tan.get(str(u), 0) if p else None),
                pfuku=(fuku.get(str(u), 0) if p else None),
                wt=wt, kin=kin,
                load=(round(kin / wt * 100, 2)
                      if (kin is not None and wt) else None),
                wt_norm=wnorm.get(u), wt_med=((wt - wmed) if wt is not None
                                              and wmed is not None else None),
                wt_prev=wt_prev,
                wt_diff=((wt - wt_prev) if (wt is not None
                                            and wt_prev is not None) else None),
                rest=rest,
                sx_k=sk, age=age,
                c4r=c4r.get(u), c4=c4n.get(u), soto=soto.get(u),
                waku=(inum(e.get('waku')) or waku(u, n)),
                hn=hn, hp=hp,
            ))

        # 書き出してから履歴を積む
        for b in batch:
            f.write(json.dumps(b, ensure_ascii=False) + '\n')
            cnt += 1
        for e in ent:
            u = int(e['u'])
            nm = e['nm']
            if c4n.get(u) is not None:
                HP[nm].append(c4n[u])
            LAST[nm] = (r['ymd'], W.get(u))
    f.close()
    print(f'{len(rows)}鞍 → {cnt}頭　{out}')
    if nopay:
        print(f'  払戻が無い鞍 {nopay}（その鞍の ptan/pfuku は None）')
    if nowt1:
        print(f'  馬体重が取れなかった頭数 {nowt1}')
    return out


def load_body(path=BODY):
    """body.jsonl を読んで、期間の中央（前半／後半の境目）も決める。"""
    rows = [json.loads(l) for l in open(path, encoding='utf-8')]
    days = sorted({x['ymd'] for x in rows})
    mid = days[len(days) // 2] if days else None
    return rows, mid


# ── 役割2：評価関数 ───────────────────────────────────────────
def ev(S, mid=None):
    """該当馬のリストから、的中率・回収率・前後半・最大1頭抜きを出す。

    返すのは dict。母数が MIN_N 未満なら {'n':..,'short':True} だけ返す。
    「最大1頭を抜いた単勝回収」の分母は抜く前の頭数のまま
    （251頭のうち1頭の払戻を0にしたときの回収、という意味）。
    """
    n = len(S)
    if n < MIN_N:
        return dict(n=n, short=True)
    tan = [(x.get('ptan') or 0) for x in S]
    fuku = [(x.get('pfuku') or 0) for x in S]
    o = dict(n=n, short=False,
             top3=sum(1 for x in S if x['f'] <= 3) / n * 100,
             win=sum(1 for x in S if x['f'] == 1) / n * 100,
             tan=sum(tan) / n, fuku=sum(fuku) / n,
             tan_nomax=((sum(tan) - max(tan)) / n), nomax=max(tan))
    if mid:
        A = [x for x in S if x['ymd'] < mid]
        B = [x for x in S if x['ymd'] >= mid]
        for k, T in (('a', A), ('b', B)):
            o[k + '_n'] = len(T)
            o[k + '_tan'] = (sum((x.get('ptan') or 0) for x in T) / len(T)
                             if T else None)
            o[k + '_fuku'] = (sum((x.get('pfuku') or 0) for x in T) / len(T)
                              if T else None)
    return o


def show(S, label, mid=None):
    """ev() の結果を1行で出す。"""
    o = ev(S, mid)
    if o['short']:
        print(f'  {label}　{o["n"]}頭　母数不足。判定しない')
        return o
    s = (f'  {label}　{o["n"]}頭　3着内{o["top3"]:.1f}%　1着{o["win"]:.1f}%　'
         f'単{o["tan"]:.1f}%　複{o["fuku"]:.1f}%')
    if mid:
        def q(v):
            return f'{v:.1f}' if v is not None else '―'
        s += (f'　｜前半{o["a_n"]}頭 単{q(o["a_tan"])}/複{q(o["a_fuku"])}　'
              f'後半{o["b_n"]}頭 単{q(o["b_tan"])}/複{q(o["b_fuku"])}')
    s += f'　｜最大1頭({o["nomax"]:,.0f}円)抜き 単{o["tan_nomax"]:.1f}%'
    print(s)
    return o


def placebo(S, pool, k=5, mid=None, seed=SEED):
    """偽薬。該当馬と同じ鞍から、条件を無視して同数を無作為に取る。

    各鞍ごとに「該当が何頭いたか」だけを守り、どの馬かは乱数で選ぶ。
    seed を変えて k 回。返すのは [(単回収, 複回収, 最大1頭抜きの単), ...]。
    """
    need = defaultdict(int)
    for x in S:
        need[x['rid']] += 1
    byr = defaultdict(list)
    for x in pool:
        byr[x['rid']].append(x)
    out = []
    for t in range(k):
        rng = random.Random(seed + 1000 * (t + 1))
        T = []
        for rid, m in need.items():
            c = byr.get(rid, [])
            T += rng.sample(c, min(m, len(c)))
        o = ev(T, mid)
        out.append(o)
    return out


def by_pop(S, pool, mid=None):
    """人気帯（6〜7／8〜10／11番人気以降）をそろえて層と並べる。

    全体の差は人気の構成の差かもしれない（CLAUDE.md）。
    pool は比べたい層をあらかじめ絞って渡す（例：川崎だけ）。
    返すのは [(帯の名前, 該当の ev, 層の ev), ...]。
    """
    bands = (('6〜7番人気', 6, 7), ('8〜10番人気', 8, 10),
             ('11番人気以降', 11, 99))
    out = []
    for lab, lo, hi in bands:
        def inb(x, lo=lo, hi=hi):
            return x['pop'] is not None and lo <= x['pop'] <= hi
        a = [x for x in S if inb(x)]
        b = [x for x in pool if inb(x)]
        out.append((lab, ev(a, mid), ev(b, mid)))
    return out


# ── 検算 ──────────────────────────────────────────────────────
def check(path=BODY):
    rows, mid = load_body(path)
    print(f'{len(rows)}頭を読んだ　前半／後半の境目 {mid}')

    # 払戻が取れて、6頭以上が走った鞍（既存スクリプトと同じ n>=6）
    pool = [x for x in rows if x['ptan'] is not None and x['n'] >= 6]
    allp = [x for x in rows if x['ptan'] is not None]

    def line(S, lab, tgt):
        n = len(S)
        t = sum(x['ptan'] for x in S) / n
        fk = sum(x['pfuku'] for x in S) / n
        print(f'  {lab:<16}{n:>6}頭　単{t:>6.1f}%　複{fk:>6.1f}%'
              f'　（予定 {tgt}）')

    print('\n── 南関4場の層（払戻が取れて6頭以上立った鞍）──')
    line(pool, '全体', '19889頭 68.9 / 71.6')
    line([x for x in pool if x['pop'] <= 3], '1〜3番人気', '5236頭 77.8 / 81.9')
    line([x for x in pool if 4 <= x['pop'] <= 5], '4〜5番人気',
         '3496頭 67.1 / 71.6')
    line([x for x in pool if x['pop'] >= 6], '6番人気以降',
         '11157頭 65.4 / 66.7')
    line([x for x in pool if x['pop'] >= 10], '10番人気以降',
         '4511頭 54.2 / 63.7')
    print(f'  ※6頭未満の鞍を入れると {len(allp)}頭（+{len(allp)-len(pool)}）')

    print('\n── 場ごとの人気薄（6番人気以降）の単勝回収 ──')
    for ba, tgt in (('川崎', '2823頭 74.2'), ('大井', '3822頭 54.2'),
                    ('船橋', '2941頭 56.5'), ('浦和', '1571頭 93.3')):
        S = [x for x in pool if x['ba'] == ba and x['pop'] >= 6]
        print(f'  {ba}　{len(S):>5}頭　単{sum(x["ptan"] for x in S)/len(S):>6.1f}%'
              f'　複{sum(x["pfuku"] for x in S)/len(S):>6.1f}%　（予定 {tgt}）')

    print('\n── 川崎 人気薄 × ふだんの4角位置が上位1/3（hp<=1/3, hn>=3）──')
    kw = [x for x in pool if x['ba'] == '川崎' and x['pop'] >= 6]
    S = [x for x in kw if x['hn'] >= HP_MIN and x['hp'] is not None
         and x['hp'] <= 1 / 3]
    show(S, '該当', mid)
    print('  （予定 251頭 単163.5 複85.9 1着4.8 前半201.0/後半158.4 '
          '最大1頭12,620円抜き113.2）')

    print('\n  偽薬（同じ鞍から同数を無作為に5回）')
    for i, o in enumerate(placebo(S, kw, k=5, mid=mid), 1):
        if o['short']:
            print(f'    {i}回目　母数不足。判定しない')
        else:
            print(f'    {i}回目　{o["n"]}頭　単{o["tan"]:>6.1f}%　'
                  f'複{o["fuku"]:>6.1f}%　最大1頭抜き 単{o["tan_nomax"]:>6.1f}%')

    print('\n  人気帯をそろえて比べる（層は川崎の6番人気以降）')
    for lab, a, b in by_pop(S, kw, mid=mid):
        def fmt(o):
            if o['short']:
                return f'{o["n"]:>5}頭　母数不足'
            return (f'{o["n"]:>5}頭　3着内{o["top3"]:>5.1f}%　'
                    f'単{o["tan"]:>6.1f}%　複{o["fuku"]:>6.1f}%')
        print(f'    {lab:<14}該当 {fmt(a)}')
        print(f'    {"":<14}層　 {fmt(b)}')

    dist(rows)


def dist(rows):
    """体重まわりの素の分布。中身を目で確かめるため。"""
    print('\n── 馬体重 ──')
    w = [x for x in rows if x['wt'] is not None]
    print(f'  取れた {len(w)}頭　取れなかった {len(rows)-len(w)}頭')
    if w:
        v = sorted(x['wt'] for x in w)
        print(f'  最小{v[0]}　中央{st.median(v):.0f}　最大{v[-1]}')

    print('\n── 前走からの増減 wt_diff ──')
    dd = [x['wt_diff'] for x in rows if x['wt_diff'] is not None]
    print(f'  出せた {len(dd)}頭　出せなかった {len(rows)-len(dd)}頭')
    if dd:
        B = (('−10kg以下', lambda v: v <= -10), ('−9〜−5', lambda v: -9 <= v <= -5),
             ('−4〜+4', lambda v: -4 <= v <= 4), ('+5〜+9', lambda v: 5 <= v <= 9),
             ('+10以上', lambda v: v >= 10))
        for lab, fn in B:
            c = sum(1 for v in dd if fn(v))
            print(f'  {lab:<10}{c:>6}頭　{c/len(dd)*100:>5.1f}%')
        print(f'  最小{min(dd)}　中央{st.median(dd):+.0f}　最大{max(dd):+d}')

    print('\n── 前走からの日数 rest ──')
    rr = [x['rest'] for x in rows if x['rest'] is not None]
    print(f'  出せた {len(rr)}頭　出せなかった {len(rows)-len(rr)}頭')
    if rr:
        B = (('7日以内', lambda v: v <= 7), ('8〜20', lambda v: 8 <= v <= 20),
             ('21〜45', lambda v: 21 <= v <= 45), ('46〜90', lambda v: 46 <= v <= 90),
             ('91日以上', lambda v: v >= 91))
        for lab, fn in B:
            c = sum(1 for v in rr if fn(v))
            print(f'  {lab:<10}{c:>6}頭　{c/len(rr)*100:>5.1f}%')
        print(f'  最小{min(rr)}　中央{st.median(rr):.0f}　最大{max(rr)}')

    print('\n── 負担率 load（斤量÷馬体重×100）──')
    ld = sorted(x['load'] for x in rows if x['load'] is not None)
    if ld:
        print(f'  出せた {len(ld)}頭　最小{ld[0]:.2f}　'
              f'中央{st.median(ld):.2f}　最大{ld[-1]:.2f}')

    print('\n── 年齢 age ──')
    A = defaultdict(int)
    for x in rows:
        A[x['age']] += 1
    for k in sorted(A, key=lambda v: (v is None, v)):
        print(f'  {k if k is not None else "不明":>4}歳　{A[k]:>6}頭　'
              f'{A[k]/len(rows)*100:>5.1f}%')

    print('\n── 性 sx_k ──')
    K = defaultdict(int)
    for x in rows:
        K[x['sx_k']] += 1
    for k in sorted(K, key=lambda v: -K[v]):
        print(f'  {k if k else "不明":>4}　{K[k]:>6}頭　{K[k]/len(rows)*100:>5.1f}%')

    print('\n── ふだんの4角位置 hp ──')
    hp = [x for x in rows if x['hp'] is not None]
    print(f'  出せた {len(hp)}頭（{HP_MIN}走以上）　'
          f'出せなかった {len(rows)-len(hp)}頭')
    print('\n── 4角の生順位 c4r ──')
    c = sum(1 for x in rows if x['c4r'] is not None)
    print(f'  取れた {c}頭　取れなかった {len(rows)-c}頭')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    a = sys.argv[2:]
    if cmd == 'build':
        build(*(a or []))
    elif cmd == 'check':
        check(*(a or []))
    else:
        print(__doc__)
