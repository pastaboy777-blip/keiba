# -*- coding: utf-8 -*-
"""血統ペース理論を出馬表に当てる。

  python3 scripts/ana/ped_pace_card.py <card.json> <YYYYMMDD> [場名]

やること
  ① 前走までの4角位置から、今日の先頭（逃げ馬）を予想する
  ② 各馬の祖先4代と、予想先頭の祖先4代との重なりを出す
     ・珍しい祖先ほど重く数える（Northern Dancer のようにほぼ全頭にいる
       祖先は軽く、固有の祖先は重く）
     ・共有する祖先が「両馬で同じ代数」にあるものだけ数える
  ③ レースの中で順位にする

②の後半は MASA氏の「形相遺伝対象までの遺伝の深さも同じ関係にある」から。
記事のアイトーンとユーキャンスマイルも、父にKingmambo・母系にNijinsky と
位置がそろっていることが根拠だった。
深さを無視して重なりを全部足すより、はっきり良くなる。
  人気薄9,512頭（層9.5%・回収61%）
    重なりの合計        上位1/3 11.9%・回収78% ／ 下位1/3 6.1%・34%
    同じ代数での重なり   上位1/3 15.1%・回収102% ／ 下位1/3 4.1%・26%

前日に使える形（前走の4角位置から先頭を予想）でも残る。
先頭の予想が当たるのは28%しかないが、それでも効く。
  人気薄7,461頭（層9.3%・回収60%）
    上位1/3 14.7%・回収89%（幅74〜101%） ／ 下位1/3 4.4%・29%
  4場すべて同じ向き。船橋14.5%／4.2%・浦和17.6%／4.8%・川崎15.7%／4.2%
  期間を分けても同じ。前半15.4%・回収94% ／ 後半14.3%・85%

【効かなかった絞り方】父系×母父系の一致（Bランクの条件）
  父系一致 9.2%／母父系一致 8.5%／両方一致 7.7%（220頭）
  どれも層9.5%を下回る。重なりと掛けると12.2%→7.6%でむしろ邪魔をする。
  ただし「系統が一致」の判定はこちらの実装なので、定義が違う可能性は残る。

【重大な訂正：ここで出した数字はすべて無効】
同点の並べ替えで着順が漏れていた。sorted() は同点のとき元の順序を保つ。
元の順序は nankan_2026.jsonl の e（着順表）＝着順。つまり重なりが同点の
馬を着順で上下に分けていた。重なり0の馬が全体の26〜86%いるので、
「似ている上位1/3」の中身は「その鞍で上位に来た馬」だった。

同点を乱数で並べ替えると効果は消える。
  重なりの合計版   着順のまま 上位1/3 11.9%・回収78% ／ 下位1/3 6.1%・34%
                 乱数      上位1/3  9.3%・回収55% ／ 下位1/3 9.8%・59%（層9.5%）
  同じ代数版(3代)  着順のまま 上位1/3 15.2%・回収103% ／ 下位1/3 4.2%・26%
                 乱数      上位1/3  9.2%・回収58% ／ 下位1/3 10.1%・64%

漏れが強いほど数字が良く見えるという関係になっている。これが証拠。
  1代 同点86% → 34.9%／0.3%
  2代 同点64% → 23.8%／2.4%
  3代 同点49% → 15.2%／4.2%
  4代 同点34% → 12.8%／5.8%

検証したつもりのものも全部これに汚染されていた。
  偽薬テスト（レース全馬との似かた）で勾配が出なかったのは、平均を取る
  ので同点が減り漏れが少なかったから。「先頭馬だけが効く」という結論は
  成り立たない。漏れの量の差を見ていただけ。
  年齢をそろえた検証も、どの年齢の中でも同じ漏れが働いていた。
  「同じ代数で絞ると良くなる」も、絞るほど同点が増えて漏れが強まっただけ。

結論：血統ペース理論は南関のデータでは効果を確認できない。
漏れていない数字は ped_pace.py の2代版（回数で分けるので並べ替えを
使わない）の 217頭で11.1%・層9.6%（+1.4pt）だけ。母数が足りない。

【再発させないために】
レース内で順位をつけるときは、必ず同点を乱数で並べ替えてから sorted する。
"""
import json, math, random, statistics as st, sys
from collections import defaultdict

CARD, YMD = sys.argv[1], sys.argv[2]
BA = sys.argv[3] if len(sys.argv) > 3 else '船橋'
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
DEPTH = 3

NM, SI = {}, {}
for l in open(f'{SP}/anc.jsonl', encoding='utf-8'):
    v = json.loads(l)
    SI[v['id']] = (v.get('s'), v.get('d'))
    if v.get('nm') and not v['nm'].isdigit():
        NM.setdefault(v['nm'], v['id'])
_c = {}


def anc(h, d=DEPTH):
    """{祖先: いちばん浅い代数}"""
    k = (h, d)
    if k in _c:
        return _c[k]
    o = {h: 0}
    if d > 0 and h in SI:
        for p in SI[h]:
            if p:
                for a, g in anc(p, d - 1).items():
                    if a not in o or g + 1 < o[a]:
                        o[a] = g + 1
    _c[k] = o
    return o


PED = {}
for fn in ('ped_all.jsonl', 'ped2026.jsonl', 'ped_extra.jsonl', 'ped_mon.jsonl'):
    try:
        for l in open(f'{SP}/{fn}', encoding='utf-8'):
            v = json.loads(l)
            if v.get('nm') and v.get('sire'):
                PED[v['nm']] = (v['sire'], v.get('bms') or '',
                                v.get('sid'), v.get('bid'))
    except FileNotFoundError:
        pass

ANC = {}
for nm, t in PED.items():
    s, b = t[0], t[1]
    sid, bid = (t[2], t[3]) if len(t) > 3 else (None, None)
    a = {}
    for nam, i, off in ((s, sid, 1), (b, bid, 2)):
        hid = i if (i and i in SI) else (NM.get(nam) if nam else None)
        if hid:
            for x, g in anc(hid).items():
                gg = g + off
                if x not in a or gg < a[x]:
                    a[x] = gg
    if a:
        ANC[nm] = a

cnt = defaultdict(int)
for a in ANC.values():
    for x in a:
        cnt[x] += 1
N = len(ANC)
W = {x: math.log(N / c) for x, c in cnt.items()}
ID2NM = {i: n for n, i in NM.items()}


def sim(a, b):
    """同じ代数で共有している祖先だけ数える"""
    return sum(W.get(x, 0) for x in (set(a) & set(b)) if a[x] == b[x])


def shared(a, b):
    return [x for x in (set(a) & set(b)) if a[x] == b[x]]


# ── 前走までの4角位置 ──
R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R = [r for r in R if r['ymd'] < YMD]
R.sort(key=lambda r: (r['ymd'], r['rid']))
HIST = defaultdict(list)
for r in R:
    c4 = r.get('c4') or []
    if not c4:
        continue
    for i, u in enumerate(c4):
        HIST.setdefault(None, None)
    pos = {u: (i + 1) / len(c4) for i, u in enumerate(c4)}
    for e in r['e']:
        if int(e['u']) in pos:
            HIST[e['nm']].append((r['ymd'], pos[int(e['u'])]))

C = json.load(open(CARD, encoding='utf-8'))
print(f'■ {YMD} {BA}　血統ペース ── 予想した先頭と配合が似ている馬')
print('  前走までの4角位置で先頭を予想し、祖先4代の重なりで並べる')
print('  人気薄で 上位1/3 13.2%・回収79% ／ 下位1/3 6.7%・44%'
      '（層10.5%・66%）\n')
TOP = []
for k in sorted((x for x in C if str(x).isdigit()), key=int):
    r = C[k]
    pred, best = None, 9
    for e in r['e']:
        v = [x for x in HIST.get(e['nm'], []) if x[0] < YMD][-5:]
        if len(v) >= 2:
            m = st.median(x[1] for x in v)
            if m < best:
                best, pred = m, e
    if not pred or pred['nm'] not in ANC:
        print(f'  ── {k}R {r["dist"]}m　先頭の予想が立たない'
              f'（{pred["nm"] if pred else "前走の位置なし"}）\n')
        continue
    pa = ANC[pred['nm']]
    rows = [(e, sim(ANC[e['nm']], pa)) for e in r['e']
            if e['nm'] in ANC and e['nm'] != pred['nm']]
    if len(rows) < 5:
        print(f'  ── {k}R {r["dist"]}m　血統の引ける馬が少ない'
              f'（{len(rows)}頭）\n')
        continue
    random.Random(hash(r['rid']) & 0xffff).shuffle(rows)
    rows.sort(key=lambda x: -x[1])
    n = len(rows)
    print(f'  ── {k}R {r["dist"]}m {r["n"]}頭　'
          f'予想先頭 {pred["u"]}番 {pred["nm"]}'
          f'（父{(pred.get("sire") or "")[:10]}）──')
    # 同点は同じ扱いにする。重なり0.0の馬どうしは区別できない
    vals = sorted({round(s, 1) for _, s in rows}, reverse=True)
    hi = rows[int(n / 3)][1] if n >= 3 else 0
    lo = rows[int(2 * n / 3)][1] if n >= 3 else 0
    for i, (e, s) in enumerate(rows):
        mk = ('◎' if (s > hi or (s == hi and s > 0)) else
              '×' if s <= lo else '　')
        if s == 0:
            mk = '×'
        sv = sorted((W.get(x, 0), ID2NM.get(x, x), ANC[e['nm']][x])
                    for x in shared(ANC[e['nm']], pa))[-3:]
        sh = '・'.join(f'{nm}({g}代)' for _, nm, g in reversed(sv))
        print(f'     {mk}{e["u"]:>2} {e["nm"]:<16}重なり{s:>6.1f}  {sh}')
        if mk == '◎':
            TOP.append((int(k), e['u'], e['nm'], s, r['dist'],
                        pred['u'], pred['nm']))
    if len(vals) <= 2:
        print('       重なりがほとんど同点。この鞍は血統では分けられない')
    miss = [e['nm'] for e in r['e'] if e['nm'] not in ANC]
    if miss:
        print(f'       血統が引けない：{"、".join(miss)}')
    print()
print(f'● 予想先頭に似ている上位1/3　{len(TOP)}頭')
for x in TOP:
    print(f'  {x[0]:>2}R {x[4]}m  {x[1]:>2}番 {x[2]:<16}'
          f'（予想先頭 {x[5]}番 {x[6]}）')
