#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""隊列図の精度を、その日1日だけで測る。

  python3 zu_kensho.py <カードjson> <結果ディレクトリ> --ven 浦和 [--half]

なぜ道具にしたか（2026-11-27）:
  毎日その場で python を書いて測っていたら、**図が描いている値と別の値を測る事故**を
  起こした。直線の図は `pos`（CHOKU=True のときの直近重みづけ）で並ぶのに、
  手書きでは `pos4`（中央値）を読んでいて、11/25 の「直線の先頭的中 1/12」は誤り
  （正しくは 5/12）。**図と同じ関数から値を取る**ことをコードで固定する。
  CLAUDE.md ルール77（自己改善）の①そのもの。

出すもの（その日だけ。★★★ 最優先 ── 過去開催とは並べない）:
  ① 4角／最初の角の相対位置 → 3着内率
  ② 位置 × 当日の上がり
  ③ 押し上げ（最初の角 − 4角）
  ④ 枠
  ⑤ ペース（前3F・勝ち時計 を その距離・その馬場の水準とくらべる）
  ⑥ **図の精度** … 1枚目／直線それぞれの先頭的中・上位2頭・位置のずれ
  ⑦ 図で隣どうしの2頭が3着内だった鞍（CLAUDE.md ルール76）
  ⑧ 1番人気
  ★ `--half` を付けると **前半と後半に割って出す**。
    2026-11-27 は10鞍まで前有利だったのに **11R・12Rで後ろから決まり**、
    10鞍ぶんの傾向をそのまま最終に当てたのがこの日いちばんの失点だった。

結果ディレクトリは `kekka.py --json` が吐いた `r01.json` … `r12.json` を置いた場所。
カードjsonは `syutuba.py` が吐いたもの（人気が空なら結果ページの人気で埋める）。
"""
import sys, os, json, glob, collections, itertools
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tenkai as T
import tenkai_zu as TZ

BK = [(0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1.01)]


def rel(x, n):
    return None if (x is None or n < 2) else (x - 1) / (n - 1)


def rows_of(card, R, ven, choku):
    """**図が描いている値**をそのまま取る。`pos` が図の横位置を決めている値。"""
    TZ.CHOKU = choku
    try:
        return [TZ.row_of(h, card[str(R)]['dist'], {}, ven) for h in card[str(R)]['horses']]
    finally:
        TZ.CHOKU = False


def load(resdir):
    out = {}
    for p in sorted(glob.glob(os.path.join(resdir, 'r*.json'))):
        d = json.load(open(p))
        if any(v.get('chaku') for v in d['horses'].values()):
            out[d['R']] = d
    return out


def bars(title, pairs):
    print('  %s' % title)
    for (a, b), (n, k) in pairs:
        print('    %.1f-%.1f  %5.1f%%  (%d頭中%d)' % (a, b, 100 * k / n if n else 0, n, k))


def run(card, rs, ven, Rs, lab):
    if not Rs:
        return
    tot = sum(len([v for v in rs[R]['horses'].values() if v.get('chaku')]) for R in Rs)
    print('\n===== %s … %d鞍・完走のべ%d頭' % (lab, len(Rs), tot))

    c4 = [[0, 0] for _ in BK]
    c1 = [[0, 0] for _ in BK]
    cells = collections.Counter(); hit = collections.Counter()
    gcnt = collections.Counter(); ghit = collections.Counter()
    nw = collections.Counter(); dw = collections.Counter()
    for R in Rs:
        d = rs[R]
        hs = [v for v in d['horses'].values() if v.get('chaku')]
        n = len(hs)
        ag = sorted([v for v in hs if v.get('agari')], key=lambda v: v['agari'])
        ar = {v['ub']: i + 1 for i, v in enumerate(ag)}
        fc = {}
        if d.get('corner'):
            sq = [u for g in d['corner'][0]['seq'] for u in g]
            fc = {u: i + 1 for i, u in enumerate(sq)}
        for v in hs:
            in3 = v['chaku'] <= 3
            w = v.get('waku')
            if w:
                dw[w] += 1
                nw[w] += in3
            p = rel(v.get('c4'), n)
            p1 = rel(fc.get(v['ub']), n)
            for arr, val in ((c4, p), (c1, p1)):
                if val is None:
                    continue
                for i, (a, b) in enumerate(BK):
                    if a <= val < b:
                        arr[i][0] += 1
                        arr[i][1] += in3
                        break
            if p is not None and ar.get(v['ub']):
                k = ('4角0.2以内' if p < 0.2 else '0.2超',
                     '上がり3位以内' if ar[v['ub']] <= 3 else '上がり4位以下')
                cells[k] += 1
                hit[k] += in3
            if p is not None and p1 is not None:
                kk = '上げた' if p1 - p > .02 else ('変わらず' if p1 - p >= -.02 else '下げた')
                gcnt[kk] += 1
                ghit[kk] += in3

    bars('■ 4角の相対位置 → 3着内率', list(zip(BK, c4)))
    bars('■ 最初に記録された角', list(zip(BK, c1)))
    print('  ■ 位置 × 当日の上がり')
    for k in sorted(cells):
        print('    %-9s × %-11s %5.1f%%  (%d頭中%d)' % (k[0], k[1], 100 * hit[k] / cells[k], cells[k], hit[k]))
    print('  ■ 押し上げ（最初の角 − 4角）')
    for k in ('上げた', '変わらず', '下げた'):
        if gcnt[k]:
            print('    %-6s %5.1f%%  (%d頭中%d)' % (k, 100 * ghit[k] / gcnt[k], gcnt[k], ghit[k]))
    a = sum(nw[w] for w in (1, 2, 3, 4)); b = sum(dw[w] for w in (1, 2, 3, 4))
    c = sum(nw[w] for w in (5, 6, 7, 8)); e = sum(dw[w] for w in (5, 6, 7, 8))
    if b and e:
        print('  ■ 枠  1-4枠 %.1f%% (%d中%d) ／ 5-8枠 %.1f%% (%d中%d)' % (100 * a / b, b, a, 100 * c / e, e, c))

    df = []; dt = []
    for R in Rs:
        d = rs[R]
        lap = d.get('lap') or []
        f3 = (round(sum(lap[1:4]), 1) if (len(lap) >= 4 and lap[0] < 8)
              else (round(sum(lap[:3]), 1) if len(lap) >= 3 else None))
        s = T.sui(ven, d['dist'], d.get('baba'))
        w = min((v['t'] for v in d['horses'].values() if v.get('t')), default=None)
        if f3 and s and s.get('f3'):
            df.append(f3 - s['f3'])
        if w and s and s.get('t'):
            dt.append(w - s['t'])
    if df:
        print('  ■ ペース  前3F 対水準 中央値 %+.2f（速いほう %d/%d）／ 勝ち時計 %+.2f（%d/%d）' % (
            st.median(df), sum(1 for x in df if x < 0), len(df),
            st.median(dt), sum(1 for x in dt if x < 0), len(dt)))

    # ── 図の精度。**図と同じ関数から値を取る**（この取り違えで一度まちがえた）
    h1 = h2 = t1 = n2 = ton = 0
    e1 = []; e2 = []
    detail = []
    for R in Rs:
        d = rs[R]
        if not d.get('corner'):
            continue
        p1 = sorted([r for r in rows_of(card, R, ven, False) if r.get('pos') is not None],
                    key=lambda r: r['pos'])
        p4 = sorted([r for r in rows_of(card, R, ven, True) if r.get('pos') is not None],
                    key=lambda r: r['pos'])
        if len(p1) < 2 or len(p4) < 2:
            continue
        f = [u for g in d['corner'][0]['seq'] for u in g]
        l = [u for g in d['corner'][-1]['seq'] for u in g]
        n2 += 1
        ok1 = p1[0]['ub'] == f[0]; ok2 = p4[0]['ub'] == l[0]
        h1 += ok1; h2 += ok2
        t1 += f[0] in (p1[0]['ub'], p1[1]['ub'])
        r1 = {u: i / (len(f) - 1) for i, u in enumerate(f)}
        r4 = {u: i / (len(l) - 1) for i, u in enumerate(l)}
        for i, r in enumerate(p1):
            if r['ub'] in r1:
                e1.append(abs(i / (len(p1) - 1) - r1[r['ub']]))
        for i, r in enumerate(p4):
            if r['ub'] in r4:
                e2.append(abs(i / (len(p4) - 1) - r4[r['ub']]))
        idx = {r['ub']: i for i, r in enumerate(p1)}
        in3 = {int(u) for u, v in d['horses'].items() if v.get('chaku') and v['chaku'] <= 3}
        ad = [(x, y) for x, y in itertools.combinations(in3, 2)
              if x in idx and y in idx and abs(idx[x] - idx[y]) == 1]
        ton += bool(ad)
        detail.append('%2dR 1枚目 %2d→%2d %s  直線 %2d→%2d %s  隣 %s' % (
            R, p1[0]['ub'], f[0], '○' if ok1 else '×',
            p4[0]['ub'], l[0], '○' if ok2 else '×',
            ' '.join('%d-%d' % p for p in ad) or 'なし'))
    if n2:
        print('  ■ 図の精度')
        for x in detail:
            print('    ' + x)
        print('    1枚目の先頭 %d/%d（上位2頭 %d/%d）  ずれ %.4f' % (h1, n2, t1, n2, sum(e1) / len(e1)))
        print('    直線の先頭   %d/%d                ずれ %.4f' % (h2, n2, sum(e2) / len(e2)))
        print('    図で隣どうしが3着内 … %d/%d鞍' % (ton, n2))

    w1 = i3 = nn = 0
    for R in Rs:
        nin = {h['ub']: h.get('nin') for h in card[str(R)]['horses']}
        f = [v for u, v in rs[R]['horses'].items()
             if (v.get('nin') or nin.get(int(u))) == 1 and v.get('chaku')]
        if f:
            nn += 1
            w1 += f[0]['chaku'] == 1
            i3 += f[0]['chaku'] <= 3
    if nn:
        print('  ■ 1番人気  勝ち%d・3着内%d（%d鞍）' % (w1, i3, nn))


def main():
    a = sys.argv[1:]
    if len(a) < 2:
        print(__doc__)
        return
    cardp, resdir = a[0], a[1]
    ven = a[a.index('--ven') + 1] if '--ven' in a else '大井'
    card = json.load(open(os.path.expanduser(cardp)))
    rs = load(os.path.expanduser(resdir))
    Rs = sorted(rs)
    if not Rs:
        print('結果が1鞍も無い'); return
    run(card, rs, ven, Rs, '1日ぜんぶ')
    if '--half' in a:
        h = len(Rs) // 2
        run(card, rs, ven, Rs[:h], '前半（%dR〜%dR）' % (Rs[0], Rs[h - 1]))
        run(card, rs, ven, Rs[h:], '後半（%dR〜%dR）' % (Rs[h], Rs[-1]))


main()
