"""過去の鞍を「展開図」の形で起こす ── 1角と4角の**実際の**通過順を上下2段に。

  python3 furikaeri_zu.py <races.json> <out.html> --date 2026-06-09 --R 7 \
      [--ven 大井] [--note "この鞍の中身"]

★ `tenkai_zu.py`（事前の予想図）とは**別のツール**。あちらは過去走から隊列を推定するが、
  こちらは**その鞍で実際にどう並んだか**を同じ見た目で描く。
  見た目（黒地・砂のトラック・馬の絵・枠色の馬番・赤い〇）は `tenkai_zu.css` を
  そのまま読んで使う。**既存のツールと css は1バイトも触っていない。**

★ 横は**実際の通過順の相対位置**（0.00＝先頭、1.00＝最後方）。縦は重なり避けだけ
  （`tenkai_zu.place()` と同じ考え。縦を内外の帯にしない ── CLAUDE.md ルール20）。

★ 向きは距離で決まる（ルール39・43）。大井1600/1800/2000m・川崎2000mは**図ごと鏡**で
  前が左・馬の絵も左向き。上下（段の順）を返すのは川崎2000m・大井1200m・1400mだけ。

★ 3着内の馬を**1頭ずつ赤い〇**で囲う（`tenkai_zu.ring(each=True)` と同じ形。
  ユーザーの指示「馬券になった馬に〇」＝答え合わせの図ではこちら）。

★ 入力は2つの形を読む
    ① 畳んだ json … {"races":[{date,R,dist,baba,pace,f3,base_f3,corner_raw,horses:[…]}]}
    ② harvest の res.json … {"7":{R,dist,baba,corner_raw,rows:[…]}}  （人気は入らない）
  **楽天・競馬ブックは叩かない。** 材料はローカルの json だけ。

★ 人気は畳んだ json の `nin`（結果頁の人気欄から取ったもの）。
  harvest の `nk` は人気ではない（CLAUDE.md ルール34）ので**使わない**。
"""
import sys, os, re, json, html, base64, io, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from horse_svg import HORSE, HORSE_L, CHEV, CHEV_L
try:
    import uma_img
except Exception:
    uma_img = None

W = {1: ('#ffffff', '#111'), 2: ('#1b1b1b', '#fff'), 3: ('#e03a30', '#fff'),
     4: ('#2d6fd0', '#fff'), 5: ('#f2d231', '#111'), 6: ('#2f9e57', '#fff'),
     7: ('#f08a24', '#111'), 8: ('#f29ab8', '#111')}
WID, PAD, GAP = 900, 64, 136
# ★ 段の高さだけ tenkai_zu（92px）より広げてある。こちらの札は
#   「着順＋人気」「◯コーナー◯番手」「上がり」「最初の角から±◯」の4行あって、
#   92pxだと下の段の馬の絵と重なった（116pxでもまだ4行目が重なる）。
#   横（WID/PAD/GAP）は tenkai_zu と同じ。
LANE = 142
# ★ ここは**想定ではなく実際**の鞍なので、`tenkai_zu.LAB` の「スロー想定」ではなく
#   そのまま「スロー」と出す。形・色（.pace / .pbar）は tenkai_zu.css のまま。
LAB = {'s': ('S', 'スロー', '前3Fが<b>水準より遅い</b>流れ'),
       'm': ('M', 'ミドル', '前3Fが<b>水準どおり</b>の流れ'),
       'h': ('H', 'ハイ', '前3Fが<b>水準より速い</b>流れ')}
GP = {'s': 24, 'm': 50, 'h': 76}
# ルール39・43。左右を返すのが MIRROR、上下（段の順）を返すのが VFLIP。
MIRROR = {('大井', 1600), ('大井', 1800), ('大井', 2000), ('川崎', 2000)}
VFLIP = {('川崎', 2000), ('大井', 1200), ('大井', 1400)}
# ルール45。最初に記録される角は場と距離でちがう。
KADO1 = {('大井', 1000): '3コーナー', ('大井', 1200): '3コーナー',
         ('大井', 1400): '2コーナー', ('川崎', 900): '3コーナー'}
WD = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']

CSS_ADD = """
/* furikaeri_zu.py が足す分だけ。tenkai_zu.css は読むだけで触っていない。 */
.tcap{margin:12px 16px 0;font-size:12.5px;font-weight:800;color:#f2f2f4}
.tcap small{font-weight:600;color:#8c8c96;margin-left:8px;font-size:11px}
.fk{display:block;font-size:9.6px;color:#d7cfc2;white-space:nowrap}
.mv{display:block;font-size:9.6px;font-weight:800;white-space:nowrap}
.mu{color:#6fc0ff}.md{color:#e58b86}
.chx{display:block;font-size:10px;color:#9a9aa4;font-weight:800;margin-top:1px;white-space:nowrap}
"""

_UMA = {}


def uma_tag(waku, ub, h=40, left=True):
    """枠色のゼッケンに馬番を描いた馬の絵（tenkai_zu.uma_tag と同じ呼び方）。

    ★ `left` は名前と逆で、left=True が**右向き**（uma_img.horse の docstring）。
      鏡でない鞍は left=True、鏡の鞍は left=False。CLAUDE.md ルール39。"""
    k = (waku, ub, h, left)
    if k in _UMA:
        return _UMA[k]
    try:
        im = uma_img.horse(waku, ub, h * 2, left)
        b = io.BytesIO(); im.save(b, 'PNG')
        _UMA[k] = ('<img class="hv" src="data:image/png;base64,%s" height="%d" alt="">'
                   % (base64.b64encode(b.getvalue()).decode(), h))
    except Exception:
        _UMA[k] = None
    return _UMA[k]


def parse(raw):
    """通過順の生文字列 → [[内..外], …]（順位グループ）。kekka_zu.py と同じ読み方。"""
    out = []
    for m in re.finditer(r"\(([^)]*)\)|(\d+)", raw or ""):
        if m.group(1):
            out.append([int(x) for x in m.group(1).split(",")])
        else:
            out.append([int(m.group(2))])
    return out


def posmap(raw):
    """馬番 → (順位, 内外タグ)。括弧の中は内→外の順（kekka_zu.py の docstring）。

    ★ **括弧の中は同じ順位**にする（併走＝横に並んで通過したということ）。
      `(14,5,12)` が4番目のグループなら3頭とも「5番手」。
      `kekka_zu.py` は同じ括弧の中でも 5,6,7 と別の番号を振るが、こちらは
      **相対位置の横軸**に使うので、併走した馬は同じ x に置きたい（段が分かれて縦に並ぶ）。
      畳んだ json の `r1`/`r4`（別のワーカーが harvest から出した相対位置）とも
      この数え方で一致する。"""
    d, rank = {}, 1
    for g in parse(raw):
        for i, u in enumerate(g):
            d[u] = (rank,
                    '単' if len(g) == 1 else ('内' if i == 0 else
                                              '外' if i == len(g) - 1 else '中'))
        rank += len(g)
    return d


def place(rows):
    """重なり避けで段を作る（tenkai_zu.place と同じ）。"""
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
    """3着内を1頭ずつ囲う（tenkai_zu.ring(each=True) と同じ寸法）。"""
    return ''.join(
        '<div class="ring" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx"></div>'
        % (int(x - 52), int(ln * LANE + 2), 104, LANE - 4)
        for r, x, ln in cells if r['ub'] in ana)


def load(fn, date, R):
    """①畳んだ json ②harvest の res.json のどちらでも1鞍を取り出す。"""
    d = json.load(open(fn))
    if isinstance(d, dict) and 'races' in d:
        for v in d['races']:
            if (not date or v.get('date') == date) and int(v['R']) == R:
                return v
        raise SystemExit('その鞍が json にありません: %s %dR' % (date, R))
    v = dict(d[str(R)])
    v.setdefault('date', date)
    v['horses'] = [dict(x, nin=None) for x in v.get('rows') or []]
    v.setdefault('nhead', len(v['horses']))
    return v


def kado(ven, dist, key):
    if key == '4':
        return '4コーナー'
    if (ven, dist) in KADO1:
        return KADO1[(ven, dist)]
    if (ven == '大井' and dist >= 1600) or (ven == '川崎' and dist >= 1400):
        return '1コーナー'
    return '%sコーナー' % key


def band(v, ven, M, key, kname, sub, flip, vf, uma_ok, agari=False, M1=None):
    """1段ぶん（ある角の隊列）を組む。"""
    n = v.get('nhead') or len(v['horses'])
    rows = []
    for h in v['horses']:
        p = M.get(h['ub'])
        rows.append(dict(h, rank=(p[0] if p else None), lane=(p[1] if p else None),
                         pos=((p[0] - 1) / max(1, n - 1) if p else .5), norec=not p))
    cells, NL = place(rows)
    if flip or vf:
        cells = [(r, (WID - x) if flip else x, (NL - 1 - ln) if vf else ln)
                 for r, x, ln in cells]
    hh = []
    for r, x, ln in cells:
        lead = (r.get('chaku') or 99) <= 3
        col = '#f2d231' if lead else '#d8c7ae'
        cc = col if lead else '#b9b9c4'
        wc = W.get(r.get('waku'), ('#15110d', '#f2f2f4'))
        fig = (uma_tag(r.get('waku') or 4, r['ub'], 40, not flip) if uma_ok else None)
        uma = fig or (HORSE_L if flip else HORSE).format(c=col)
        cv = (CHEV_L if flip else CHEV).format(c=cc)
        ch = ('%d着' % r['chaku']) if r.get('chaku') else '―'
        nin = ('　%s人気' % r['nin']) if r.get('nin') else ''
        so = ('<span class="sm">%s%s</span>' % (ch, nin) if lead
              else '<span class="chx">%s%s</span>' % (ch, nin))
        if r['norec']:
            so += '<span class="nopast">この角の記録なし</span>'
        else:
            so += '<span class="fk">%s%d番手%s</span>' % (
                kname, r['rank'], '（%s）' % r['lane'] if r['lane'] != '単' else '')
        if agari and r.get('agari'):
            so += '<span class="fk">上がり%s</span>' % r['agari']
        if M1 and not r['norec']:
            p1 = M1.get(r['ub'])
            mv = (p1[0] - r['rank']) if p1 else 0
            if mv:
                # ★ 地点名は「1角」と決め打ちしない（ルール45）。最初に記録された角は
                #   場と距離でちがうので、見出しと同じ言い方に揃える。
                so += ('<span class="mv %s">最初の角から%+d</span>'
                       % ('mu' if mv > 0 else 'md', mv))
        hh.append('<div class="horse" style="left:%dpx;top:%dpx"><div class="fig">%s</div>'
                  '<div class="lab"><span class="n" style="background:%s;color:%s">%d</span>'
                  '<span class="nm">%s</span></div>%s</div>'
                  % (int(x), 14 + ln * LANE, (cv + uma) if flip else (uma + cv),
                     wc[0], wc[1], r['ub'], html.escape(r.get('name') or ''), so))
    ana = {h['ub'] for h in v['horses'] if (h.get('chaku') or 99) <= 3}
    return ('<div class="tcap">%s<small>%s</small></div>'
            '<div class="track" style="height:%dpx"><div class="goal%s"></div>%s%s</div>'
            % (kname + 'の隊列（実際の通過順）', sub, NL * LANE + 24,
               ' l' if flip else '', ring(cells, ana), '\n'.join(hh)))


def main():
    a = sys.argv[1:]
    if len(a) < 2:
        print(__doc__)
        return
    src, out = a[0], a[1]
    g = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    ven = g('--ven', '大井')
    date = g('--date')
    R = int(g('--R', '1'))
    v = load(src, date, R)
    dist, baba = v['dist'], v.get('baba') or ''
    n = v.get('nhead') or len(v['horses'])
    raw = v.get('corner_raw') or {}
    k1 = next((c for c in ('1', '2', '3') if raw.get(c)), None)
    M1 = posmap(raw.get(k1)) if k1 else {}
    M4 = posmap(raw.get('4'))
    flip = (ven, dist) in MIRROR
    vf = (ven, dist) in VFLIP
    uma_ok = ('--svg' not in a) and uma_img is not None
    k1n = kado(ven, dist, k1 or '1')
    b1 = band(v, ven, M1, k1 or '1', k1n,
              'スタート後いちばん最初に記録された角', flip, vf, uma_ok)
    b4 = band(v, ven, M4, '4', '4コーナー', '直線に向くところ', flip, vf, uma_ok,
              agari=True, M1=M1)
    pc = (v.get('pace') or 'M').lower()
    tag, nm, eff = LAB.get(pc, LAB['m'])
    f3, bf3 = v.get('f3'), v.get('base_f3')
    pnum = []
    if f3:
        pnum.append('この鞍の前3F %.1f秒' % f3)
    if bf3:
        pnum.append('水準 %.1f秒（%s・%s鞍）'
                    % (bf3, v.get('base_src') or '―', v.get('base_n') or '―'))
    if f3 and bf3:
        d_ = f3 - bf3
        pnum.append('水準より%.1f秒%s' % (abs(d_), '遅い' if d_ > 0 else '速い')
                    if abs(d_) >= .05 else '水準どおり')
    try:
        dt = datetime.date(*[int(x) for x in (date or v.get('date')).split('-')])
        kick = '%s — %s' % (dt.strftime('%Y.%m.%d') + ' ' + WD[dt.weekday()], ven)
    except Exception:
        kick = '%s — %s' % (date or '', ven)
    note = g('--note', '')
    muki = '左が前' if flip else '右が前'
    css = open(os.path.join(HERE, 'tenkai_zu.css')).read() + CSS_ADD
    page = (
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<title>実際の隊列</title><style>%s</style></head><body>'
        '<div class="head"><div class="kicker">%s%s</div>'
        '<h1>実際の隊列 ── %dR ダ%dm</h1>'
        '<div class="sub"><b>これは予想ではなく、その鞍で実際にどう並んだか</b>です。'
        '上が%s、下が4コーナー。<b>横は本物の通過順の相対位置</b>'
        '（0.00＝先頭、1.00＝最後方）で、<b>%s</b>。馬番は枠の色。<br>'
        '<b>赤い〇が3着内に来た馬。</b>'
        '札の「（内）（外）」はその角で<b>併走したとき</b>の内外で、'
        '<b>単独だった馬は内外が記録されていません</b>（書いていない馬がそれ）。<br>'
        '<b>縦の並びは重なりを避けただけ</b>で、内外とは関係ありません。</div></div>'
        '<div class="race"><div class="rh"><span class="rn">%dR</span>'
        '<span class="rt">%s</span>'
        '<span class="rd">ダ<b>%dm</b> ／ %d頭 ／ 馬場 <b>%s</b></span>'
        '<span class="pace p-%s"><b>%s</b> %s</span></div>'
        '<div class="pbar p-%s"><div class="gauge"><div class="gz z1">ゆっくり</div>'
        '<div class="gz z2">ふつう</div><div class="gz z3">速い</div>'
        '<div class="gmark" style="left:%d%%"></div></div>'
        '<div class="peff">→ %s<span class="pnum">%s</span></div></div>'
        '%s%s%s</div>'
        '<div class="tail">印は買い目の保証ではありません。</div></body></html>'
        % (css, kick, ('／馬場 ' + baba) if baba else '', R, dist,
           k1n, muki, R, v.get('date') or '', dist, n, baba or '―',
           pc, tag, nm, pc, GP.get(pc, 50), eff, '　／　'.join(pnum),
           b1, b4,
           ('<div class="view"><h4>この鞍の中身</h4><p>%s</p></div>' % note) if note else ''))
    open(out, 'w').write(page)
    print('%s %dR → %s' % (v.get('date') or '', R, out))


if __name__ == '__main__':
    main()
