"""展開図 ── 過去走の4コーナー通過順で隊列を組み、枠と騎手で位置を直す。

  python3 tenkai_zu.py <card.json> <out.html> --ven 川崎 --baba 不良 \
      --date "2026.11.10 TUE" --R 6-12 [--res res.json] [--odds odds.json] \
      --pace 6:S 7:M ... [--ana 6:7,1,8,13,5] [--swap 6:12-1] ["note:6=見解"]

★ 2026-11-11 にユーザーと詰めて確定した形
  （11/10 川崎6Rで「この展開図なんだよね」「逃げ馬合っていて、逃げ馬の後ろに①がいて、
    外⑬と笹川」と確認を得た。実際の4角は `7,13-(1,4),5,8,…` ＝
    ⑦1番手・⑬2番手(外)・①3番手(内)・⑧6番手で、図と合っていた。）

  ・段は**重なり避け**のまま。縦を内外の帯にしたり1頭1段にしたりしない。
    （どちらも勝手にやって「ちがう」と2回言われた。**形を作り替えない。**）
  ・ただし**枠で取れない位置に馬を置かない**。pos が近い2頭は、
    **内度（枠＋騎手）の高いほうを前**に置き替える。
    11/10 6Rは8枠の⑫が先頭列の2番目にいたのを1枠の①と入れ替えて正しくなった。
  ・**過去走のない馬も図に置く**（鞍の中央・札で明記）。
    11/10 7Rの⑦ルナティックブルーを「記録なし」欄に落として図から消していた。
    その馬が12番人気3着。
  ・狙う一帯は**ひとつの〇**で囲う。1頭ずつ囲わない。

★ 内度 ＝ 枠の内率 ＋ 騎手の内率（基準線44.7%との差）

  枠 1枠79.8 2枠71.1 3枠60.5 4枠50.9 5枠45.0 6枠34.6 7枠30.8 8枠21.9（南関12,244頭）
  騎手 jk_soto.json。併走60回以上のみ。減量記号（△▲◇☆★◎）は外して照合する。
  事前の帯 → 当日ほんとうに併走したとき内にいた割合は 内81.0% / 中50.0% / 外33.3%。

★ 前後（pos）の精度はここが限界（2026-11-11 に21,180件で測った）

  直近重みづけ 0.2200 → 枠・騎手・距離・頭数を足しても 0.2188。**ほぼ動かない。**
  枠と騎手は**内外には50ポイント効くが、前後にはほとんど効かない**
  （1-2枠0.455 / 3-6枠0.500 / 7-8枠0.455）。
  **位置は「だいたい」。当てにしすぎない。**
"""
import sys, os, json, re, html, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from horse_svg import HORSE, CHEV
import tenkai as T

W = {1: ('#ffffff', '#111'), 2: ('#1b1b1b', '#fff'), 3: ('#e03a30', '#fff'),
     4: ('#2d6fd0', '#fff'), 5: ('#f2d231', '#111'), 6: ('#2f9e57', '#fff'),
     7: ('#f08a24', '#111'), 8: ('#f29ab8', '#111')}
WK = {1: .798, 2: .711, 3: .605, 4: .509, 5: .450, 6: .346, 7: .308, 8: .219}
JK_BASE, JK_MIN = .447, 60
WID, LANE, PAD, GAP = 900, 92, 64, 136
SWAP_DP, SWAP_DU = 0.12, 0.15     # pos がこれだけ近く、内度がこれだけ違えば入れ替える
MB_MIN, MB_TH, MB_CAP = 3, 0.70, 0.12   # 馬の実績（併走回数・偏り・内度に足す上限）
LAB = {'s': ('S', 'スロー想定', '前に行った馬が<b>そのまま残る</b>'),
       'm': ('M', 'ミドル想定', '<b>中団から前へ出てくる馬</b>まで'),
       'h': ('H', 'ハイ想定', '前が<b>垂れる</b>。終いのある馬が届く')}
GP = {'s': 24, 'm': 50, 'h': 76}


def _load(fn):
    p = os.path.join(HERE, fn)
    return json.load(open(p)) if os.path.exists(p) else {}


JK = _load('jk_soto.json')
SOTO = _load('soto.json')
CSS = open(os.path.join(HERE, 'tenkai_zu.css')).read()


def jk_rate(name):
    n = re.sub(r'^[△▲◇☆★◎]+', '', (name or '').strip())
    a = JK.get(n)
    return n, (a[1] / a[0] if (a and a[0] >= JK_MIN) else None)


def rel(p, k):
    if not p.get(k) or not p.get('n'):
        return None
    return (p[k] - 1) / max(1, p['n'] - 1)


def row_of(h, dist, od):
    P = h.get('past') or []
    # ★ 隊列は1コーナーで組む（2026-11-11・CLAUDE.md ルール23）。
    #   4角の中央値で組むと「前に行って下がる馬」が中団に描かれる。
    #   11/10 11Rの⑩ヒーローコールは1角0.00（5走中3走ハナ）の逃げ馬なのに
    #   4角中央値0.40で中団に置き、「▼下がる」と札まで付けて逃げ切られた。
    #   南関803鞍でも1角のほうが上（先頭の的中43.5%対40.2%）。
    c1 = [rel(p, 'c1') for p in P]
    c1 = [x for x in c1 if x is not None]
    c4 = [rel(p, 'c4') for p in P]
    c4 = [x for x in c4 if x is not None]
    per = []
    for p in P:
        a, b = rel(p, 'c1'), rel(p, 'c4')
        if a is not None and b is not None:
            per.append(a - b)
    e, l, _c, n, ext = T.prof(h, dist)
    o = od.get(h['ub']) or {}
    waku = h.get('waku') or o.get('waku') or 4
    # ★ 騎手は出馬表（syutuba.py が拾う jk）を優先。オッズ頁は発走の数時間前まで開かない
    jn, jr = jk_rate(h.get('jk') or o.get('jk'))
    s = SOTO.get(h['name'])
    # ★ 馬自身の実績（2026-11-11 に追加・CLAUDE.md ルール25）
    #   ユーザーの指摘 ──「③　外じゃないの？？」。9R③チェリストは併走4回**全部外**なのに
    #   3枠(60.5%)＋岡村健(45.9%)だけで内度.62 を付け、内に置いていた。
    #   札（過去の事実）はルール16で出してよい。内度への反映は**偏りきった馬だけ**、
    #   ±MB_CAP に抑える。順は 枠 → 騎手 → 馬（ルール21）なので、
    #   1枠や8枠はこれでは帯をまたがない（9R①サラサは外3/3でも.80→.68で内のまま）。
    mb, mbtag = 0.0, None
    if s and s['grp'] >= MB_MIN:
        ro, ri = s['out'] / s['grp'], s['in'] / s['grp']
        if ro >= MB_TH:
            mb, mbtag = -MB_CAP, '外%d/%d' % (s['out'], s['grp'])
        elif ri >= MB_TH:
            mb, mbtag = +MB_CAP, '内%d/%d' % (s['in'], s['grp'])
    return dict(ub=h['ub'], name=h['name'], waku=waku, jk=jn, jr=jr, mbtag=mbtag,
                uchi=WK.get(waku, .45) + ((jr - JK_BASE) if jr is not None else 0.0) + mb,
                pos=(st.median(c1) if c1 else (st.median(c4) if c4 else None)),
                pos4=(st.median(c4) if c4 else None), nopos=False,
                gain=(st.median(per) if per else None), l=l, runs=len(P),
                soto=((s['out'] / s['grp']) if s and s['grp'] >= 3 else None),
                tr=(h.get('tr') or o.get('tr')),
                chaku=o.get('chaku'), nin=o.get('nin'), odds=o.get('odds'))


def arrange(rows, swap=()):
    """pos を決めて、枠と騎手で位置を直す。過去走なしは鞍の中央。

    ★ 自動の入れ替えは「pos が近い隣どうし」しか直せない。
      11/10 6Rの⑫(8枠)と①(1枠)は pos では①が前なのに、段を詰める都合で
      ⑫が先頭列の2番目、①が5段下に描かれた。**段の割り当てのほうが問題**で、
      これは隣どうしの入れ替えでは直らない。だから `--swap 6:12-1` で
      馬番を指定して入れ替えられるようにしてある。ユーザーが鞍ごとに指名する。"""
    return _arrange(rows, swap)


def _arrange(rows, swap=()):
    """pos を決めて、枠と騎手で近い2頭を入れ替える。過去走なしは鞍の中央に置く。"""
    ps = [r['pos'] for r in rows if r['pos'] is not None]
    mid = st.median(ps) if ps else .5
    for r in rows:
        if r['pos'] is None:
            r['pos'], r['nopos'] = mid, True
    by = {r['ub']: r for r in rows}
    for u1, u2 in swap:
        if u1 in by and u2 in by:
            by[u1]['pos'], by[u2]['pos'] = by[u2]['pos'], by[u1]['pos']
    rows.sort(key=lambda r: r['pos'])
    for i in range(len(rows) - 1):
        a, b = rows[i], rows[i + 1]
        if (b['pos'] - a['pos']) <= SWAP_DP and (b['uchi'] - a['uchi']) >= SWAP_DU:
            a['pos'], b['pos'] = b['pos'], a['pos']
            rows[i], rows[i + 1] = b, a
    return rows


def place(rows):
    """重なり避けで段を作る。

    ★ 「x が近い馬の段を内度順に並べ替える」後処理を一度入れたが**失敗した**
      （2026-11-11）。同じ段に x の近い馬が同居して重なる。
      段の割り当てを内外に合わせたいなら、段そのものを内外の帯にするしかないが、
      それはユーザーに「ちがう」と言われた形。**ここは重なり避けのままにする。**
      ずれている鞍は `--swap` で馬番を指定して直す。"""
    out, lanes = [], []
    for r in sorted(rows, key=lambda r: r['pos']):
        x = PAD + (1 - r['pos']) * (WID - 2 * PAD)
        for i, last in enumerate(lanes):
            if x < last - GAP:
                lanes[i] = x
                out.append((r, x, i))
                break
        else:
            lanes.append(x)
            out.append((r, x, len(lanes) - 1))
    return out, max(1, len(lanes))


def ring(cells, ana):
    pts = [(x, ln) for r, x, ln in cells if r['ub'] in ana]
    if not pts:
        return ''
    xs = [p[0] for p in pts]
    ls = [p[1] for p in pts]
    return ('<div class="ring" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx"></div>'
            % (int(min(xs) - 80), int(min(ls) * LANE + 2),
               int(max(xs) - min(xs) + 160), int((max(ls) - min(ls) + 1) * LANE - 4)))


def kv(a, key):
    out = {}
    if key in a:
        for tok in a[a.index(key) + 1:]:
            if tok.startswith('--') or tok.startswith('note:') or ':' not in tok:
                break
            k, v = tok.split(':', 1)
            out[k] = v
    return out


def main():
    a = sys.argv[1:]
    if len(a) < 2:
        print(__doc__)
        return
    card, out = a[0], a[1]
    g = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    ven, baba, date = g('--ven', '川崎'), g('--baba'), g('--date', '')
    lo, _, hi = g('--R', '1-12').partition('-')
    lo, hi = int(lo), int(hi or lo)
    od_all = json.load(open(g('--odds'))) if g('--odds') else {}
    res = json.load(open(g('--res'))) if g('--res') else {}
    pace = {k: v.lower() for k, v in kv(a, '--pace').items()}
    ana_sp = {k: {int(x) for x in v.split(',') if x} for k, v in kv(a, '--ana').items()}
    swap_sp = {k: v.split(',') for k, v in kv(a, '--swap').items()}
    note = {}
    for tok in a:
        if tok.startswith('note:'):
            k, _, t = tok[5:].partition('=')
            note[k] = t
    C = json.load(open(card))
    body = []
    for key in sorted(C, key=lambda x: C[x]['R']):
        v = C[key]
        if not (lo <= v['R'] <= hi):
            continue
        R = str(v['R'])
        od = {o['ub']: o for o in (od_all.get(R) or [])}
        rv = res.get(R) or {}
        if rv.get('rows'):
            for x in rv['rows']:
                od.setdefault(x['ub'], {}).update(
                    {k2: x[k2] for k2 in ('jk', 'waku', 'chaku') if x.get(k2) is not None})
        rows = [row_of(h, v['dist'], od) for h in v['horses']]
        for i, r in enumerate(sorted([x for x in rows if x['l'] is not None],
                                     key=lambda x: x['l']), 1):
            r['srank'] = i
        for r in rows:
            r.setdefault('srank', None)
        sw = [tuple(int(y) for y in p_.split('-')) for p_ in swap_sp.get(R, [])]
        cells, NL = place(arrange(rows, sw))
        pc = pace.get(R, 'm')
        tag, nm, eff = LAB.get(pc, LAB['m'])
        b = T.sui(ven, v['dist'], baba)
        hh = []
        for r, x, ln in cells:
            lead = (r['chaku'] or 99) <= 3
            up = (r['gain'] or 0) >= .20
            col = '#f2d231' if lead else ('#6fc0ff' if up else '#d8c7ae')
            cc = col if lead else ('#6fc0ff' if up else '#b9b9c4')
            # gain は 1角−4角。プラスが押し上げ、マイナスが4角までに下がる
            t = ('<span class="upq">▲押し上げ</span>' if up else
                 ('<span class="dn">▼4角までに下がる</span>' if (r['gain'] or 0) <= -.20 else ''))
            so = ''
            if r['chaku']:
                so += '<span class="sm">%d着</span>' % r['chaku']
            if r['srank'] and r['srank'] <= 3:
                so += '<span class="sm">終い%d位</span>' % r['srank']
            if r['jr'] is not None and r['jr'] >= .53:
                so += '<span class="jin">%s 内%.0f%%</span>' % (html.escape(r['jk']), r['jr'] * 100)
            elif r['jr'] is not None and r['jr'] <= .40:
                so += '<span class="jout">%s 内%.0f%%</span>' % (html.escape(r['jk']), r['jr'] * 100)
            if r['mbtag']:
                so += '<span class="%s">過去 %s</span>' % (
                    'jin' if r['mbtag'][0] == '内' else 'jout', r['mbtag'])
            if r['nopos']:
                so += '<span class="nopast">過去走なし</span>'
            wc = W.get(r['waku'], ('#15110d', '#f2f2f4'))
            hh.append('<div class="horse" style="left:%dpx;top:%dpx"><div class="fig">%s%s</div>'
                      '<div class="lab"><span class="n" style="background:%s;color:%s">%d</span>'
                      '<span class="nm">%s</span></div>%s%s</div>'
                      % (int(x), 14 + ln * LANE, HORSE.format(c=col), CHEV.format(c=cc),
                         wc[0], wc[1], r['ub'], html.escape(r['name']), t, so))
        body.append(
            '<div class="race"><div class="rh"><span class="rn">%dR</span>'
            '<span class="rt">%s</span>'
            '<span class="rd">ダ<b>%dm</b> ／ %d頭 ／ %s</span>'
            '<span class="pace p-%s"><b>%s</b> %s</span></div>'
            '<div class="pbar p-%s"><div class="gauge"><div class="gz z1">ゆっくり</div>'
            '<div class="gz z2">ふつう</div><div class="gz z3">速い</div>'
            '<div class="gmark" style="left:%d%%"></div></div>'
            '<div class="peff">→ %s<span class="pnum">%s</span></div></div>'
            '<div class="track" style="height:%dpx"><div class="goal"></div>%s%s</div>%s</div>'
            % (v['R'], v.get('start') or '', v['dist'], len(v['horses']),
               html.escape(v.get('cls') or ''), pc, tag, nm, pc, GP.get(pc, 50), eff,
               ('この鞍の前3Fの水準 %.1f秒' % b['f3']) if b else '',
               NL * LANE + 24, ring(cells, ana_sp.get(R, set())), '\n'.join(hh),
               ('<div class="view"><h4>見解</h4><p>%s</p></div>' % note[R]) if R in note else ''))
    page = ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<title>展開予想</title><style>@@CSS@@</style></head><body>'
            '<div class="head"><div class="kicker">@@DATE@@ — @@VEN@@@@BABA@@</div>'
            '<h1>展開予想</h1>'
            '<div class="sub">過去走の<b>4コーナー通過順</b>で隊列を組み、'
            '<b>枠と騎手</b>で位置を直しています。<b>右が前</b>、馬番は枠の色。<br>'
            '内外は枠と騎手から —— 1枠79.8% / 2枠71.1% / 3枠60.5% / 4枠50.9% / '
            '5枠45.0% / 6枠34.6% / 7枠30.8% / 8枠21.9%（4コーナーで併走したとき内にいた割合・'
            '南関12,244頭）。騎手は併走60回以上の人だけ、基準線44.7%との差を足しています。<br>'
            '<b>縦の並びは重なりを避けただけです。</b>'
            '位置の予想は平均で0.21ずれます（南関803鞍で測定）。'
'<b>▼は1角から4コーナーまでに下がる馬</b>で、前にいないという意味ではありません。</div></div>'
            '@@BODY@@<div class="tail">印は買い目の保証ではありません。</div></body></html>')
    page = (page.replace('@@CSS@@', CSS).replace('@@DATE@@', date).replace('@@VEN@@', ven)
            .replace('@@BABA@@', ('／馬場 ' + baba) if baba else '')
            .replace('@@BODY@@', '\n'.join(body)))
    open(out, 'w').write(page)
    print('%d鞍 → %s' % (len(body), out))


if __name__ == '__main__':
    main()
