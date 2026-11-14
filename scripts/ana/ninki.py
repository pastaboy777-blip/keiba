"""市場（人気・単勝）と、こちらの隊列の読みが食い違っている所を並べる。

  python3 ninki.py <card.json> --ven 大井 [--R 1-12] [--baba 重]

鞍ごとに1頭1行の表を標準出力に出すだけ。**買い目は出さない。点も付けない。**

  馬番 ／ 枠 ／ 馬名 ／ 騎手 ／ 人気 ／ 単勝 ／ 1角(pos) ／ gain ／ 4角 ／ 内度 ／ 終い順位 ／ 印

並びは **1角(pos) の小さい順**（＝隊列の前から）。過去走がなく pos が出ない馬は最後。
印の ◎ は **4角の相対が0.2以内**の馬（CLAUDE.md ルール33・36 ──「効いているのは4角の位置」）。

── 数字はぜんぶ `tenkai_zu.py` のものをそのまま出している

  pos / gain / 4角 / 内度 / 終い(l) は `tenkai_zu.row_of()` の返り値。ここでは計算しない。
  終い順位だけは `row_of` の外（`tenkai_zu.main()`）で付けているので、
  同じ並べ方（`l` の昇順＝水準との差が小さい順）をここで繰り返している。

  ★ `arrange()` は通していない。あれは pos が近い2頭を内度で**入れ替える**ので、
    表の「1角(pos)」の欄と値がずれる。表は素の中央値のまま並べる。
    拮抗している2頭の前後は、図（`tenkai_zu.py`）のほうが正しい。

── 人気と単勝は前日は空

  `syutuba.py` が拾う `odds` / `nin` は**前日は空で、当日に入る**（同ファイル冒頭）。
  空のときは列を `-` にして、表の上に「オッズ未発表」と出す。

── 鞍ごとのまとめ（1行ずつ）

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

FMT = '%4d %2d %s %s %s %s %s %s %s %s %s  %s %s'


def rw(s, n):
    """右詰め（数字の欄の見出し用）。幅は全角2・半角1で数える"""
    w = sum(2 if ud.east_asian_width(c) in 'FW' else 1 for c in s)
    return ' ' * max(0, n - w) + s


HEAD = ('馬番 枠 ' + T.w('馬名', 16) + ' ' + T.w('騎手', 8) + ' '
        + ' '.join(rw(s, n) for s, n in (('人気', 4), ('単勝', 6), ('1角', 5),
                                         ('gain', 5), ('4角', 5), ('内度', 5),
                                         ('終い', 4))) + '  ' + '印')


def num(x, f='%5.2f'):
    return (f % x) if x is not None else '    -'


def one(v, ven, baba):
    """1鞍ぶん。card.json の 1鞍 v をそのまま受ける"""
    # ★ row_of は人気・単勝を「オッズ頁（--odds）の dict」から読む作りなので、
    #   出馬表に入っている odds / nin をその形に詰めて渡す。row_of は触らない。
    od = {h['ub']: {'nin': h.get('nin'), 'odds': h.get('odds')} for h in v['horses']}
    rows = [Z.row_of(h, v['dist'], od) for h in v['horses']]
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
    print(HEAD)
    for r in rows:
        print(FMT % (
            r['ub'], r['waku'], T.w(r['name'], 16), T.w(r['jk'] or '', 8),
            ('%4d' % r['nin']) if r['nin'] else '   -',
            ('%6.1f' % r['odds']) if r['odds'] else '     -',
            num(r['pos']), num(r['gain'], '%+5.2f'), num(r['pos4']),
            num(r['uchi'], '%5.2f'), ('%4d' % r['srank']) if r['srank'] else '   -',
            '◎' if (r['pos4'] is not None and r['pos4'] <= MAE) else '  ',
            '過去走なし' if r['runs'] == 0 else ''))

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
