"""展開図を描く ── 想定ペースごとに「狙う帯」を囲う。

  python3 zu.py <card.json> <出力.html> --pace 1:S 2:M 3:H ...
  python3 zu.py <card.json> out.html --pace 7:M 10:S 12:H --res res.json

── 帯の決め方（2026-11-09 にユーザーと詰めた形）

  スロー想定 … ラチ沿い一列（いちばん内の1段）
  ミドル想定 … 内から2頭目まで（上2段）
  ハイ想定  … いちばん外の一列（下1段）

── ★★ 事前の図にこの帯を引いてはいけない（2026-11-09 にやってしまった）

  この図の縦は**重なりを避けて並べているだけで内外ではない**。
  それを承知で囲いを引き、「穴は帯の中にいた」と説明した。**成立していない。**
  10R の実際の4角は `3,13,(6,10),7,12,(2,4,8,14),(5,9,11),1` で、
  ③ハナノウタゲは**先頭・単独**。併走していないので内外は記録されておらず、
  ラチ沿いだったとは言えない。「後方の内」と言えるのは⑤だけだった。

  **内外の帯を引いてよいのは、結果の通過順から起こした図だけ**（括弧が内→外）。
  事前の図に引けるのは、外率（soto.py）の母数が足りてから。
  それまで zone は描かない。

── ★ 縦軸について（必ず読むこと）

  この図の縦は**重なりを避けて並べているだけ**で、内外ではない。
  内外を事前に描くには外率（soto.py）が要るが、11/9 の48頭中
  **出せたのは8頭だけ**だった。枠順も測ったが効かない
  （1-2枠の3着内24.3% 対 7-8枠24.8%、ペースを問わず差なし）。
  **外率の母数が増えるまで、縦は「内外のつもり」で見るしかない。**
  結果の通過順から起こす図は括弧が内→外なので、そちらは本物の内外にできる。

── ★ 終い順位を必ず出すこと

  11/9 7R で、過去走の上がりが鞍で1位だった②キチョウが10番人気で2着。
  終い1位・2位・3位がそのまま 2着・3着・1着だった。
  tenkai.py は終い速度を計算していたのに図にも見解にも出しておらず、
  この馬を一行も書けなかった。**終い上位3頭には必ず札を付ける。**
"""
import sys, os, json, html

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from horse_svg import HORSE, CHEV
import tenkai as T

WAKU = {1: ('#ffffff', '#111'), 2: ('#1b1b1b', '#fff'), 3: ('#e03a30', '#fff'),
        4: ('#2d6fd0', '#fff'), 5: ('#f2d231', '#111'), 6: ('#2f9e57', '#fff'),
        7: ('#f08a24', '#111'), 8: ('#f29ab8', '#111')}
# 想定 → (表示, 段数, 上下, 帯のラベル, 色クラス)
ZONE = {'S': ('S', 'スロー想定', 1, 'top', 'ラチ沿い一列', 'slow'),
        'M': ('M', 'ミドル想定', 2, 'top', '内から2頭目まで', 'mid'),
        'H': ('H', 'ハイ想定', 1, 'bottom', 'いちばん外の一列', 'high')}
# ★ WID は body(1060) - padding76 - board margin32 - ylab78 - gap8 = 866 に収まること。
#   900 のままだと右端の馬（相対0.00）の名札が .race の overflow:hidden で切れる。
WID, LANE, PAD, GAP = 840, 88, 64, 130


def rel_pos(h):
    import statistics as st
    c1, c4 = [], []
    for p in (h.get('past') or []):
        if p.get('c4') and p.get('n'):
            c4.append((p['c4'] - 1) / max(1, p['n'] - 1))
        if p.get('c1') and p.get('n'):
            c1.append((p['c1'] - 1) / max(1, p['n'] - 1))
    return (st.median(c4) if c4 else None,
            (st.median(c1) - st.median(c4)) if c1 and c4 else None)


def build(card, pace, soto=None, zone=False, note=None):
    D = json.load(open(card))
    SO = json.load(open(soto)) if soto and os.path.exists(soto) else {}
    out = []
    for k in sorted(D, key=lambda x: D[x]['R']):
        v = D[k]
        R = str(v['R'])
        if R not in pace:
            continue
        rows = []
        for h in v['horses']:
            pos, gain = rel_pos(h)
            e, l, c, n, ext = T.prof(h, v['dist'])
            s = SO.get(h['name'])
            rows.append({'ub': h['ub'], 'waku': h.get('waku'), 'name': h['name'],
                         'pos': pos, 'gain': gain, 'l': l,
                         'sr': (s['out'] / s['grp']) if s and s['grp'] >= 3 else None,
                         'sn': s['grp'] if s else 0})
        # ★ 終い（l）は 2026-11-10 から「水準との差・小さいほど速い」に変わった。
        #   ここは -l で降順に並べたままで、**終い順位が逆に出ていた**。昇順が正しい。
        #   `if r['l']` も l==0.0 を落とすので is not None にする。
        rk = {r['ub']: i + 1 for i, r in
              enumerate(sorted([r for r in rows if r['l'] is not None], key=lambda r: r['l']))}
        hs = sorted([r for r in rows if r['pos'] is not None], key=lambda r: r['pos'])
        cells, lanes = [], []
        for r in hs:
            x = PAD + (1 - r['pos']) * (WID - 2 * PAD)
            for i, last in enumerate(lanes):
                if x < last - GAP:
                    lanes[i] = x; cells.append((r, x, i)); break
            else:
                lanes.append(x); cells.append((r, x, len(lanes) - 1))
        NL = max(1, len(lanes)); HT = NL * LANE + 24
        note = note or {}
        tag_, name_, nz, side, zlab, pcls = ZONE[pace[R]]
        nz = min(nz, NL)
        ztop = 6 if side == 'top' else (NL - nz) * LANE + 6
        hh = []
        for r, x, lane in cells:
            ok = r['sr'] is not None and r['sn'] >= 3
            col, cc, t = '#d8c7ae', '#b9b9c4', ''
            if r['gain'] is not None and r['gain'] >= 0.20:
                if ok and r['sr'] >= 0.50: col = cc = '#ff9f52'; t = '<span class="upo">▲外から押し上げ</span>'
                elif ok and r['sr'] <= 0.34: col = cc = '#5fe07a'; t = '<span class="upi">▲内のまま押し上げ</span>'
                else: col = cc = '#6fc0ff'; t = '<span class="upq">▲押し上げ</span>'
            elif r['gain'] is not None and r['gain'] <= -0.20:
                t = '<span class="dn">▼下がる</span>'
            so = ''
            if rk.get(r['ub'], 99) <= 3:
                so += '<span class="sm">終い%d位</span>' % rk[r['ub']]
            if not t and ok:
                if r['sr'] >= 0.60: so += '<span class="so">外に出せる</span>'
                elif r['sr'] <= 0.25: so += '<span class="sin">内に入りがち</span>'
            wc = WAKU.get(r['waku'], ('#15110d', '#f2f2f4'))
            hh.append('<div class="horse" style="left:%dpx;top:%dpx"><div class="fig">%s%s</div>'
                '<div class="lab"><span class="n" style="background:%s;color:%s;border-color:%s">%d</span>'
                '<span class="nm">%s</span></div>%s%s</div>'
                % (int(x), 14 + lane * LANE, HORSE.format(c=col), CHEV.format(c=cc),
                   wc[0], wc[1], '#00000055' if r['waku'] == 1 else 'rgba(255,255,255,.45)',
                   r['ub'], html.escape(r['name']), t, so))
        out.append(
          '<div class="race"><div class="rh"><span class="rn">%dR</span>'
          '<span class="rd">ダ%dm %d頭 %s</span>'
          '<span class="pace p-%s"><b>%s</b> %s</span></div>'
          '%s'
          '<div class="board"><div class="ylab"><span>%s</span><span>%s</span></div>'
          '<div class="track" style="height:%dpx"><div class="goal"></div>%s%s</div></div>'
          '<div class="xlab"><span>後方</span><span>中団</span>'
          '<span>前　→　ゴール</span></div></div>'
          % (v['R'], v['dist'], len(v['horses']), html.escape(v.get('cls', '')),
             pcls, tag_, name_,
             ('<div class="note">%s</div>' % html.escape(note[R])) if note.get(R) else '',
             '内（ラチ沿い）' if zone else '　',
             '外' if zone else '重なり避け',
             HT,
             ('<div class="zone" style="top:%dpx;height:%dpx"><div class="zlab">%s</div></div>'
              % (ztop, nz * LANE - 8, zlab)) if zone else '',
             '\n'.join(hh)))
    return out


CSS = open(os.path.join(HERE, 'zu.css')).read() if os.path.exists(os.path.join(HERE, 'zu.css')) else ''


TITLE_K = '4コーナー前後の位置どり'
SUB_ZONE = ('金色の囲いが、その想定で狙う帯です —— '
            '<b>スローはラチ沿い一列</b>、<b>ミドルは内から2頭目まで</b>、'
            '<b>ハイはいちばん外の一列</b>。横は4コーナーの前後で<b>右が前</b>、馬番は枠の色。')
SUB_PLAIN = ('横は4コーナーの前後で<b>右が前</b>。過去走の4コーナー相対位置の中央値で置いています。'
             '馬番は枠の色。<b>縦は重なりを避けて並べているだけで、内外ではありません。</b>'
             '▲は1コーナーから4コーナーで前へ出られる馬、▼は下がる馬。'
             '「終い◯位」は今日と同じ距離帯・その走の馬場の水準と比べた上がりの順です。')


def main():
    a = sys.argv[1:]
    if len(a) < 2 or '--pace' not in a:
        print(__doc__); return
    i = a.index('--pace')
    pace = {}
    for tok in a[i + 1:]:
        if tok.startswith('--'):
            break
        r, p = tok.split(':')
        pace[r] = p.upper()
    soto = a[a.index('--soto') + 1] if '--soto' in a else os.path.join(HERE, 'soto.json')
    # ★ 内外の帯は --zone を付けたときだけ。事前の図には引かない（縦は内外ではない）
    zone = '--zone' in a
    note = {}
    for tok in a:
        if tok.startswith('note:'):
            r, _, txt = tok[5:].partition('=')
            note[r] = txt
    body = build(a[0], pace, soto, zone, note)
    open(a[1], 'w').write(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<title>%s</title><style>%s</style></head><body>'
        '<div class="head"><div class="kicker">%s</div><h1>%s</h1>'
        '<div class="sub">%s</div></div>'
        '%s<div class="tail">印は買い目の保証ではありません。</div></body></html>'
        % (('展開想定別 穴の狙い方' if zone else '展開隊列図'), CSS,
           ('展開想定別' if zone else TITLE_K), ('穴の狙い方' if zone else '展開隊列図'),
           (SUB_ZONE if zone else SUB_PLAIN), '\n'.join(body)))
    print('%d鞍 → %s' % (len(body), a[1]))


if __name__ == '__main__':
    main()
