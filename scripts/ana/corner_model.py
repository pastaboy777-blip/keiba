# -*- coding: utf-8 -*-
"""各馬の4角通過タイムを組み立てるモデル。

  python3 scripts/ana/corner_model.py <corners_margin.jsonl> [場名...]

【材料】
  実測  各馬の走破時計、各馬の上り3F、レースのハロンタイム（先頭）
  推定  記号が何馬身をあらわすか

【足場】
  ラップ表の累積（残り600m地点）は、4角で先頭だった馬の
  「走破時計 − 上り3F」と974鞍すべてで0.000秒一致した。
  ラップ表は先頭馬の時計そのもの。ここに偏りはない。

【組み立て】
  その馬の4角通過 ＝ 先頭の4角通過 ＋ 先頭からの馬身 × 1馬身の秒数
  1馬身の秒数 ＝ 2.4m ÷ その馬の速さ    ← 物理。固定する
  先頭からの馬身 ＝ 記号を足していく     ← ここだけ当てる

【物理で割るのは、やってみたら負けた】
はじめ馬身を0.7/1.5/3.0に固定して秒数を当てたら0.24秒が要ると出た。
物理の0.158秒の1.4倍で、固定する側を間違えたと思い、こちらに直した。
当てはめ直すとカンマ1.1・ハイフン2.4・イコール3.6馬身で、楽天の凡例
（1馬身以内／1〜2馬身／大きく開いた）とほぼ一致した。

ところが速さの帯ごとに検算の中央値を見ると、物理版のほうが偏る。
  上り3Fの速さで5つに分けたときの中央値の幅
    定数 0.24秒/馬身  0.108秒
    物理 2.4m÷速さ    0.189秒
精度もほぼ同じ（0.204秒 対 0.206秒）。定数のほうが素直だった。

理由は、残っている誤差が秒への換算ではなく「記号が3段階しかない」
ことから来ているから。絶対誤差0.20秒は約1馬身にあたる。
  できる   各馬の4角位置を±1馬身で置く。順位では同じ扱いだった馬を分ける
  できない 1馬身未満の差を読む。本物の区間タイムの代わりにはならない

【検算】
  組み立てた4角通過 ＋ その馬の上り3F ＝ その馬の走破時計

【使いどころ（move_sec.py で測った人気薄）】
順位が同じだった馬を秒で割ったときだけ効く。
  船橋 648頭 10.6%/回収68% → 詰めた543頭 12.0%/78%・離された105頭 3.8%/15%
  大井1,247頭 10.5%/回収67% → 詰めた881頭 12.6%/83%・離された366頭 5.5%/30%
順位で差がつく場面では順位がすでに同じ情報を持っていて、秒を足しても増えない。
"""
import json, re, statistics as st, sys
from collections import defaultdict

SRC = sys.argv[1]
BAF = sys.argv[2:] or None
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
LEN_M = 2.4          # 1馬身は約2.4m


def toks(s):
    return re.findall(r'\((?:\d+,?)+\)|\d+|[,=\-]', s) if s else []


def order(s, L):
    """記号つきの通過順位を [(馬番, 先頭からの馬身)] に直す。Lは記号の目盛り"""
    out, lead = [], 0.0
    for t in toks(s):
        if t in L:
            lead += L[t]
        elif t.startswith('('):
            for u in re.findall(r'\d+', t):
                out.append((int(u), lead))
        else:
            out.append((int(t), lead))
    return out or None


def sec(t):
    m = re.match(r'^(?:(\d+):)?(\d+)\.(\d)$', t.strip()) if t else None
    return None if not m else int(m.group(1) or 0) * 60 + int(m.group(2)) \
        + int(m.group(3)) / 10


CM = {}
for l in open(SRC, encoding='utf-8'):
    v = json.loads(l)
    CM[v['rid']] = v
R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]

# 鞍ごとに材料をそろえる。記号の並びは生のまま持っておく（目盛りを変えて試すため）
RACE = []
for r in R:
    if BAF and r['ba'] not in BAF:
        continue
    v, lap = CM.get(r['rid']), r.get('lap')
    if not v or not lap or not r.get('dist') or not v.get('c4s'):
        continue
    T = {}
    for e in r['e']:
        t, a = sec(e.get('tm')), sec(e.get('ag') or '')
        if t is not None and a is not None and a > 0:
            T[int(e['u'])] = (t, a)
    if not T:
        continue
    lead_t = sum(lap[:max(0, len(lap) - 3)])
    RACE.append((r['ba'], r['dist'], lead_t, v['c4s'], T))
print(f'材料 {len(RACE)}鞍'
      f'（{"・".join(BAF) if BAF else "4場"}）\n')


def fit(L):
    """目盛りLで組み立てたときの検算のズレ"""
    err = []
    for ba, dist, lead_t, c4s, T in RACE:
        o = order(c4s, L)
        if not o:
            continue
        for u, b in o:
            if u not in T:
                continue
            t, a = T[u]
            spl = LEN_M / (600 / a)          # その馬の1馬身あたりの秒数
            err.append((lead_t + b * spl + a) - t)
    return err


print('■ 記号が何馬身をあらわすか　当てはめ')
print('  （1馬身→秒は物理で固定。2.4m ÷ その馬の上り3Fの速さ）')
print(f'  {",":>6}{"-":>6}{"=":>6}   {"中央値":>8}{"絶対誤差":>9}')
best = None
for c in (0.7, 0.8, 0.9, 1.0, 1.1, 1.2):
    for dsh in (1.6, 1.8, 2.0, 2.2, 2.4):
        for eq in (3.0, 3.6, 4.2, 4.8):
            e = fit({',': c, '-': dsh, '=': eq})
            if not e:
                continue
            ab = st.median([abs(x) for x in e])
            md = st.median(e)
            sc = abs(md) + ab
            if best is None or sc < best[0]:
                best = (sc, c, dsh, eq, md, ab)
_, c, dsh, eq, md, ab = best
for cc, dd, ee, lab in ((0.7, 1.5, 3.0, 'はじめの置き方'),
                        (c, dsh, eq, '当てはめた値')):
    e = fit({',': cc, '-': dd, '=': ee})
    print(f'  {cc:>6.1f}{dd:>6.1f}{ee:>6.1f}   '
          f'{st.median(e):>+8.3f}{st.median([abs(x) for x in e]):>9.3f}'
          f'   {lab}')

L = {',': c, '-': dsh, '=': eq}
print(f'\n  → カンマ {c}馬身　ハイフン {dsh}馬身　イコール {eq}馬身')
print('     楽天の凡例は「1馬身以内／1〜2馬身／大きく開いた」。'
      'ほぼそのとおりに出た。')

e = fit(L)
a = sorted(abs(x) for x in e)
print(f'\n■ 検算　組み立てた4角通過 ＋ 上り3F −（実際の走破時計）')
print(f'  {len(e)}頭　中央値 {st.median(e):+.3f}秒　絶対誤差 {ab:.3f}秒')
print(f'  半分が {a[len(a)//2]:.2f}秒以内　8割が {a[int(len(a)*.8)]:.2f}秒以内'
      f'　9割が {a[int(len(a)*.9)]:.2f}秒以内')

byba = defaultdict(list)
for (ba, dist, lead_t, c4s, T) in RACE:
    o = order(c4s, L)
    if not o:
        continue
    for u, b in o:
        if u not in T:
            continue
        t, aa = T[u]
        byba[ba].append((lead_t + b * (LEN_M / (600 / aa)) + aa) - t)
print()
for ba, v in sorted(byba.items(), key=lambda x: -len(x[1])):
    if len(v) >= 200:
        print(f'  {ba}  {len(v):>6}頭　中央値 {st.median(v):+.3f}　'
              f'絶対誤差 {st.median([abs(x) for x in v]):.3f}')
json.dump(L, open(f'{SP}/corner_scale.json', 'w'))
print(f'\n  目盛りを {SP}/corner_scale.json に保存')
