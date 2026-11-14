"""市場（人気・単勝）と、こちらの隊列の読みが食い違っている所を並べる。

  python3 ninki.py <card.json> --ven 大井 [--R 1-12] [--baba 重]

鞍ごとに1頭1行の表を標準出力に出すだけ。**買い目は出さない。点も付けない。**

  馬番 ／ 枠 ／ 馬名 ／ 騎手 ／ 人気 ／ 単勝 ／ 体重 ／ 平均差 ／ 増減
       ／ 1角(pos) ／ gain ／ 4角 ／ 内度 ／ 終い順位 ／ 印

並びは **1角(pos) の小さい順**（＝隊列の前から）。過去走がなく pos が出ない馬は最後。
印の ◎ は **4角の相対が0.2以内**の馬（CLAUDE.md ルール33・36 ──「効いているのは4角の位置」）。

── 数字はぜんぶ `tenkai_zu.py` のものをそのまま出している

  pos / gain / 4角 / 内度 / 終い(l) は `tenkai_zu.row_of()` の返り値。ここでは計算しない。
  終い順位だけは `row_of` の外（`tenkai_zu.main()`）で付けているので、
  同じ並べ方（`l` の昇順＝水準との差が小さい順）をここで繰り返している。

  ★ `arrange()` は通していない。あれは pos が近い2頭を内度で**入れ替える**ので、
    表の「1角(pos)」の欄と値がずれる。表は素の中央値のまま並べる。
    拮抗している2頭の前後は、図（`tenkai_zu.py`）のほうが正しい。

── 人気・単勝・馬体重は前日は空

  `syutuba.py` が拾う `odds` / `nin` / `w` / `dw` は**前日は空で、当日に入る**（同ファイル冒頭）。
  空のときは列を `-` にして、表の上に「オッズ未発表」「馬体重未発表」と出す。
  CLAUDE.md ルール3 ──「馬体重は発走30分前に取り直す」。

── 馬体重の3列（2026-11-14 に追加）

  体重   … `w` の実数（キロ）
  平均差 … **その鞍に出ている馬の馬体重の平均からの差**（CLAUDE.md ルール4
           ──「馬体重は絶対値でなく『そのレースの平均との差』で見る」）。四捨五入して整数で出す
  増減   … `dw`（前走からの増減）をそのまま

  ★ 一部の馬だけ `w` が無いときは、**その馬を除いて平均を出す**（頭数も入っている頭数）。
    その馬の3列は `-`。
  ★ ここも**数字を並べるだけ**。「+20kgは有利」のような評価は書かない。
    効くかどうかは分かっていない（「買う馬リストの組み方」の物差し5）。

── 鞍ごとのまとめ（1行ずつ）

  体重 … その鞍の平均と、平均より±15kg離れている馬（馬体重が未発表の鞍では出さない）
  ズレ … ◎（4角0.2以内）なのに人気5番手以下の馬。こちらが前めと読んで市場が買っていない
  逆   … 1〜3人気なのに4角0.4より後ろの馬。市場が買っていてこちらの読みでは後ろ
"""
import sys, os, json, unicodedata as ud

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tenkai_zu as Z
import tenkai as T

MAE = 0.20      # ◎ … 4角の相対がこれ以内（ルール33）
USHIRO = 0.40   # 逆 … 1〜3人気でこれより後ろ
NIN_LO = 5      # ズレ … 人気がこれ以下（5番手以下）
W_SA = 15       # 体重 … 鞍の平均からこれ以上離れている馬をまとめ行に出す（kg）

FMT = '%4d %2d %s %s %s %s %s %s %s %s %s %s %s %s  %s %s'


def rw(s, n):
    """右詰め（数字の欄の見出し用）。幅は全角2・半角1で数える"""
    w = sum(2 if ud.east_asian_width(c) in 'FW' else 1 for c in s)
    return ' ' * max(0, n - w) + s


HEAD = ('馬番 枠 ' + T.w('馬名', 16) + ' ' + T.w('騎手', 8) + ' '
        + ' '.join(rw(s, n) for s, n in (('人気', 4), ('単勝', 6),
                                         ('体重', 4), ('平均差', 6), ('増減', 4),
                                         ('1角', 5),
                                         ('gain', 5), ('4角', 5), ('内度', 5),
                                         ('終い', 4))) + '  ' + '印')


def num(x, f='%5.2f'):
    return (f % x) if x is not None else '    -'


def shisha(x):
    """四捨五入して整数に。負の側も絶対値で丸める（round() は銀行丸め）"""
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


def one(v, ven, baba):
    """1鞍ぶん。card.json の 1鞍 v をそのまま受ける"""
    # ★ row_of は人気・単勝を「オッズ頁（--odds）の dict」から読む作りなので、
    #   出馬表に入っている odds / nin をその形に詰めて渡す。row_of は触らない。
    od = {h['ub']: {'nin': h.get('nin'), 'odds': h.get('odds')} for h in v['horses']}
    rows = [Z.row_of(h, v['dist'], od) for h in v['horses']]
    # ★ 馬体重は row_of が返さない（tenkai_zu.py は触らない）。出馬表から直に引く。
    #   平均は **w が入っている馬だけ**で出す（頭数もその数）。
    WT = {h['ub']: (h.get('w'), h.get('dw')) for h in v['horses']}
    ws = [w for w, _ in WT.values() if w]
    wavg = (sum(ws) / len(ws)) if ws else None
    # 終い順位 … tenkai_zu.main() と同じ並べ方（l は水準との差で、小さいほど速い）
    for i, r in enumerate(sorted([x for x in rows if x['l'] is not None],
                                 key=lambda x: x['l']), 1):
        r['srank'] = i
    for r in rows:
        r.setdefault('srank', None)
    rows.sort(key=lambda r: (r['pos'] is None, r['pos'] if r['pos'] is not None else 0))

    b = T.sui(ven, v['dist'], baba)
    print('━━ %dR  ダ%dm ／ %d頭 ／ %s%s%s' % (
        v['R'], v['dist'] or 0, len(v['horses']), v.get('cls') or '',
        ('　発走 %s' % v['start']) if v.get('start') else '',
        ('　前3Fの水準 %.1f秒' % b['f3']) if b else ''))
    if not any(r['nin'] for r in rows):
        print('   ※ オッズ未発表（人気・単勝は当日に入る）')
    if wavg is None:
        print('   ※ 馬体重未発表（体重・平均差・増減は当日に入る）')
    print(HEAD)
    for r in rows:
        w, dw = WT.get(r['ub'], (None, None))
        print(FMT % (
            r['ub'], r['waku'], T.w(r['name'], 16), T.w(r['jk'] or '', 8),
            ('%4d' % r['nin']) if r['nin'] else '   -',
            ('%6.1f' % r['odds']) if r['odds'] else '     -',
            ('%4d' % w) if w else '   -',
            ('%+6d' % shisha(w - wavg)) if (w and wavg is not None) else '     -',
            ('%4s' % dw) if dw else '   -',
            num(r['pos']), num(r['gain'], '%+5.2f'), num(r['pos4']),
            num(r['uchi'], '%5.2f'), ('%4d' % r['srank']) if r['srank'] else '   -',
            '◎' if (r['pos4'] is not None and r['pos4'] <= MAE) else '  ',
            '過去走なし' if r['runs'] == 0 else ''))

    # 馬体重のまとめ（未発表の鞍は出さない）。平均との差だけを並べる ── 評価はしない
    if wavg is not None:
        omo = [r['ub'] for r in rows
               if WT.get(r['ub'], (None,))[0]
               and shisha(WT[r['ub']][0] - wavg) >= W_SA]
        karu = [r['ub'] for r in rows
                if WT.get(r['ub'], (None,))[0]
                and shisha(WT[r['ub']][0] - wavg) <= -W_SA]
        print('   体重: 平均 %.1fkg（%d頭）／ 平均より+%dkg以上 = %d頭%s'
              '／ -%dkg以下 = %d頭%s' % (
                  wavg, len(ws),
                  W_SA, len(omo),
                  ('（馬番 %s）' % ','.join(str(x) for x in omo)) if omo else '',
                  W_SA, len(karu),
                  ('（馬番 %s）' % ','.join(str(x) for x in karu)) if karu else ''))

    if not any(r['nin'] for r in rows):
        print('   ズレ／逆 … オッズ未発表のため出せません')
        return
    zure = [r['ub'] for r in rows
            if r['pos4'] is not None and r['pos4'] <= MAE and r['nin'] and r['nin'] >= NIN_LO]
    gyaku = [r['ub'] for r in rows
             if r['nin'] and r['nin'] <= 3 and r['pos4'] is not None and r['pos4'] > USHIRO]
    print('   ズレ: ◎のうち人気%d番手以下 = %d頭%s' % (
        NIN_LO, len(zure), ('（馬番 %s）' % ','.join(str(x) for x in zure)) if zure else ''))
    print('   逆: 1〜3人気のうち4角%.1fより後ろ = %d頭%s' % (
        USHIRO, len(gyaku), ('（馬番 %s）' % ','.join(str(x) for x in gyaku)) if gyaku else ''))


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    g = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    ven, baba = g('--ven', '大井'), g('--baba')
    lo, _, hi = g('--R', '1-12').partition('-')
    lo, hi = int(lo), int(hi or lo)
    C = json.load(open(a[0]))
    for key in sorted(C, key=lambda x: C[x]['R']):
        v = C[key]
        if lo <= v['R'] <= hi:
            one(v, ven, baba)
            print()


if __name__ == '__main__':
    main()
