# -*- coding: utf-8 -*-
"""血統ペース理論 ── 4代ぶんの重なりで測る。

  python3 scripts/ana/ped_pace2.py [場名...]

ped_pace.py は父と母父の2代だけで一致を探したので、重なる馬が全体の
2.4%しか出ず判定できなかった。記事が言っているのはもっと広い単位。

  逃げ馬の持つ血統的特性から、サンデー系の種牡馬が台頭しやすい流れに
  なるのか、パワーがありタフなノーザンダンサー系向きの流れになるのか

記事の例（2018菊花賞）も、アイトーンとユーキャンスマイルの共通点は
父Kingmambo・母父Nijinskyで、3〜4代前にある。

祖先グラフ（anc.jsonl）を使う。父をたどれば系統まで登れる。
  その馬の祖先 ＝ 父から3代ぶん ∪ 母父から3代ぶん
  重なり       ＝ 先頭に立った馬の祖先との共通部分

ただし Northern Dancer や Mr. Prospector はほぼ全頭に入っているので、
重なりの数をそのまま見ても差が出ない。2つの直しを入れる。
  ① 珍しい祖先ほど重く数える（その祖先を持つ馬の割合の逆数で重みづけ）
  ② レースの中で順位にする（同じ鞍の馬どうしで比べる）

2段階で見る。①実際に先頭だった馬で効き目の有無 → ②前走から予想した先頭。

【結果：効いた】人気薄9,512頭（層9.5%・複勝の回収61%）
  先頭に似ている 上位1/4 11.8%・72% ／ 2/4 12.6%・92%
                 3/4  9.5%・56% ／ 下位1/4 5.8%・32%
4場すべて同じ向き。船橋も 13.6%／13.9% 対 5.7%。

【偽薬テストを通った】
「ありふれた血統かどうか」では勾配が出ない。
  レース全馬に似ている 上位1/4 10.0% … 下位1/4 9.1%
先頭馬を除いたほかの馬との似かたで切り分けても、効くのは先頭の軸だけ。
  先頭◎ほか◎ 12.4%・回収91%  先頭◎ほか× 11.2%・51%
  先頭×ほか◎  5.0%・34%      先頭×ほか×  6.6%・35%
ほかを固定して先頭を動かすと5.0→12.4・6.6→11.2と動く。
先頭を固定してほかを動かしてもそろわない。

【年齢も通った】年齢そのものに差がない（2歳7.8／3歳9.8／4歳9.9／5歳以上9.4）。
どの年齢でも同じ勾配が出る。
  3歳 11.9%／7.0%　4歳 12.4%／6.4%　5歳以上 11.7%／5.8%
先頭馬との年齢差にも差がない。

【前日に使える形】前走までの4角位置から先頭を予想する。
予想が当たるのは28%しかないが、それでも効く。
  予想先頭に似ている 上位1/3 13.2%・回収79% ／ 下位1/3 6.7%・44%

【レーティングと重ねる】点が上位3割のなかを血統で割ると
  似ている上位1/3 16.3%・回収79%（246頭）
  似ている下位1/3 10.7%・43%（290頭）
ただしこの区間（船橋大井・7月以降2,688頭）では血統だけだと+0.0ptで、
全体の13.2%／6.7%と食い違う。期間か場のどちらかで弱い可能性がある。
ここは材料を増やしてから見直すこと。

【さらに良くなった：同じ代数での重なりだけ数える】
MASA氏の「形相遺伝対象までの遺伝の深さも同じ関係にある」から。
記事のアイトーンとユーキャンスマイルも、父にKingmambo・母系にNijinsky と
位置がそろっていることが根拠だった。深さを無視して全部足すより良い。
  人気薄9,512頭（層9.5%・回収61%）
    重なりの合計      上位1/3 11.9%・回収78% ／ 下位1/3 6.1%・34%
    同じ代数での重なり  上位1/3 15.1%・回収102% ／ 下位1/3 4.1%・26%
前日に使える形（予想した先頭）でも残る。人気薄7,461頭（層9.3%・回収60%）
  上位1/3 14.7%・回収89%（幅74〜101%） ／ 下位1/3 4.4%・29%
4場すべて同じ向き。船橋14.5%／4.2%・浦和17.6%／4.8%・川崎15.7%／4.2%
期間を分けても同じ。前半15.4%・回収94% ／ 後半14.3%・85%

【効かなかった絞り方：父系×母父系の一致（Bランクの条件）】
  父系一致 9.2%／母父系一致 8.5%／両方一致 7.7%（220頭）
  どれも層9.5%を下回る。重なりと掛けると12.2%→7.6%でむしろ邪魔をする。
  ただし「系統が一致」の判定はこちらの実装なので、定義が違う可能性は残る。

【残っている弱点】
血統が引けるのは出走馬の61%。引けない馬（外国産や珍しい血統）を丸ごと
外しているので、そこに偏りがあるかもしれない。

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

BA = sys.argv[1:] or ['大井', '浦和', '川崎', '船橋']
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
DIVF = {'船橋': 'div_funabashi.json', '大井': 'div_year.json'}
DEPTH = 3

NM, SI = {}, {}
for l in open(f'{SP}/anc.jsonl', encoding='utf-8'):
    v = json.loads(l)
    SI[v['id']] = (v.get('s'), v.get('d'))
    if v.get('nm') and not v['nm'].isdigit():
        NM.setdefault(v['nm'], v['id'])

_c = {}


def anc(hid, depth=DEPTH):
    """その馬から depth 代ぶんの祖先（自分を含む）"""
    k = (hid, depth)
    if k in _c:
        return _c[k]
    out = {hid}
    if depth > 0 and hid in SI:
        for p in SI[hid]:
            if p:
                out |= anc(p, depth - 1)
    _c[k] = out
    return out


PED = {}
for fn in ('ped_all.jsonl', 'ped2026.jsonl', 'ped_extra.jsonl'):
    try:
        for l in open(f'{SP}/{fn}', encoding='utf-8'):
            v = json.loads(l)
            if v.get('nm') and v.get('sire'):
                PED[v['nm']] = (v['sire'], v.get('bms') or '')
    except FileNotFoundError:
        pass

ANC = {}
for nm, (s, b) in PED.items():
    a = set()
    for x in (s, b):
        if x and x in NM:
            a |= anc(NM[x])
    if a:
        ANC[nm] = a
print(f'祖先が引ける馬 {len(ANC)} / 血統の分かる馬 {len(PED)}')

# ① 珍しい祖先ほど重く
cnt = defaultdict(int)
for a in ANC.values():
    for x in a:
        cnt[x] += 1
N = len(ANC)
W = {x: math.log(N / c) for x, c in cnt.items()}


def sim(a, b):
    return sum(W.get(x, 0) for x in (a & b))


R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R.sort(key=lambda r: (r['ymd'], r['rid']))
HIST = defaultdict(list)
ROWS = []
for r in R:
    c = r.get('c3') or r.get('c4')
    if c and r['ba'] in BA:
        byu = {int(e['u']): e for e in r['e'] if e.get('f', '').isdigit()}
        led = byu.get(int(c[0]))
        pred, best = None, 9
        for e in r['e']:
            v = [x for x in HIST.get(e['nm'], []) if x[0] < r['ymd']][-5:]
            if len(v) >= 2:
                m = st.median(x[1] for x in v)
                if m < best:
                    best, pred = m, e
        for key, tgt in (('ov', led), ('ovp', pred)):
            pass
        if led and led['nm'] in ANC:
            la = ANC[led['nm']]
            pa = ANC.get(pred['nm']) if (pred and pred['nm'] in ANC) else None
            tmp = []
            for e in r['e']:
                if not e.get('f', '').isdigit() or e['nm'] not in ANC:
                    continue
                if e['nm'] == led['nm']:
                    continue
                pop = e.get('pop', '')
                tmp.append(dict(
                    ba=r['ba'], ymd=r['ymd'], R=r['R'], u=int(e['u']),
                    nm=e['nm'], hit=int(e['f']) <= 3,
                    pop=int(pop) if pop.isdigit() else None,
                    sim=sim(ANC[e['nm']], la),
                    simp=sim(ANC[e['nm']], pa) if pa else None,
                    same_pred=(pred is not None and pred['nm'] == led['nm'])))
            # ② レースの中で順位にする
            if len(tmp) >= 5:
                random.Random(hash(r['rid']) & 0xffff).shuffle(tmp)
                o = sorted(tmp, key=lambda x: -x['sim'])
                for i, x in enumerate(o):
                    x['rk'] = (i + 1) / len(o)
                if tmp[0]['simp'] is not None:
                    o2 = sorted(tmp, key=lambda x: -x['simp'])
                    for i, x in enumerate(o2):
                        x['rkp'] = (i + 1) / len(o2)
                ROWS += tmp
    i4 = {u: (i + 1) / len(r.get('c4') or [1])
          for i, u in enumerate(r.get('c4') or [])}
    for e in r['e']:
        if int(e['u']) in i4:
            HIST[e['nm']].append((r['ymd'], i4[int(e['u'])]))

D = {}
for ba, fn in DIVF.items():
    try:
        D[ba] = json.load(open(f'{SP}/{fn}', encoding='utf-8'))
    except Exception:
        pass
for x in ROWS:
    fk = dict((D.get(x['ba'], {}).get(x['ymd'], {})
               .get(str(x['R']), {})).get('複勝', []))
    x['fuku'] = fk.get(str(x['u']), 0)
    x['has'] = bool(fk)

sp = [x for x in ROWS if x.get('rkp') is not None]
print(f'材料 {len(ROWS)}頭')
if sp:
    print('  前走までの位置から当てた先頭が実際の先頭と一致 '
          f'{100*sum(x["same_pred"] for x in sp)/len(sp):.0f}%')


def blk(lab, P, key):
    if len(P) < 400:
        print(f'\n■ {lab} 材料不足（{len(P)}頭）')
        return
    base = 100 * sum(x['hit'] for x in P) / len(P)
    d = [x for x in P if x['has']]
    br = f'　複勝の回収 {sum(x["fuku"] for x in d)/len(d):.0f}%' if d else ''
    print(f'\n■ {lab}　{len(P)}頭　3着内 {base:.1f}%{br}')
    for nm, lo, hi in (('似ている 上位1/4', 0, .25), ('2/4', .25, .5),
                       ('3/4', .5, .75), ('似ていない 下位1/4', .75, 1.01)):
        v = [x for x in P if key in x and lo < x[key] <= hi]
        if len(v) < 80:
            print(f'    {nm:<20} 材料不足({len(v)})')
            continue
        i = sum(x['hit'] for x in v)
        dd = [x for x in v if x['has']]
        roi = f'  回収 {sum(x["fuku"] for x in dd)/len(dd):5.0f}%' if dd else ''
        print(f'    {nm:<20} {len(v):>5}頭  {100*i/len(v):5.1f}%{roi}'
              f' {100*i/len(v)-base:+5.1f}pt')


print('\n──① 実際に先頭だった馬と比べる（終わってから分かること）──')
blk('全馬', ROWS, 'rk')
blk('人気薄（6番人気以降）',
    [x for x in ROWS if x['pop'] and x['pop'] >= 6], 'rk')
for ba in BA:
    blk(f'{ba} 人気薄',
        [x for x in ROWS if x['ba'] == ba and x['pop'] and x['pop'] >= 6], 'rk')
print('\n──② 前走までの位置から先頭を予想して比べる（前日に分かること）──')
blk('人気薄（6番人気以降）',
    [x for x in ROWS if x['pop'] and x['pop'] >= 6 and 'rkp' in x], 'rkp')
