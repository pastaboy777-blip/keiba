"""縦横に意味を持たせた「帯の図」の最小の型。

  python3 band.py out.html

対象を **横＝順序のある量**、**縦＝別の軸（または重なり避け）** で置き、
注目させたい範囲を帯で囲う。印は色ではなく**札**で足す。

── 作るときに守ること（痛い目を見て決めたもの）

  1. **縦に意味が無いなら、縦に帯を引かない。**
     「重なりを避けて並べただけ」の軸に帯を引いて説明すると、
     図が言っていないことを言葉で足すことになる。
  2. **強さを色で表さない。**色が付いた対象は「強い」と読まれる。
     色は**状態**（動きの向きなど）に使い、強弱は位置と札に任せる。
  3. **測れないものは、図から外して別に書く。**
     無理に置くと、置いた位置が意味を持ってしまう。
  4. 札は2つまで。3つ以上付くと、どれが効いているか読めなくなる。
"""
import sys, os, html

HERE = os.path.dirname(os.path.abspath(__file__))
W, LANE, PAD, GAP = 900, 92, 64, 136


def layout(items, key):
    """key は 0.0（右端）〜1.0（左端）。重なる対象だけ下の段へ逃がす。"""
    out, lanes = [], []
    for it in sorted(items, key=key):
        x = PAD + (1 - key(it)) * (W - 2 * PAD)
        for i, last in enumerate(lanes):
            if x < last - GAP:
                lanes[i] = x; out.append((it, x, i)); break
        else:
            lanes.append(x); out.append((it, x, len(lanes) - 1))
    return out, max(1, len(lanes))


def render(items, key, label, tags=None, zone=None, title="", sub=""):
    """items … 任意の dict のリスト
    key   … それぞれの横位置（0〜1、0が右端）を返す関数
    label … 表示名を返す関数
    tags  … 札のリストを返す関数（文字列のHTML、2つまで）
    zone  … (上から何段目, 何段ぶん, ラベル) か None
    """
    cells, NL = layout(items, key)
    body = []
    for it, x, lane in cells:
        t = ''.join((tags(it) or [])[:2]) if tags else ''
        body.append('<div class="item" style="left:%dpx;top:%dpx">'
                    '<div class="dot"></div><div class="lb">%s</div>%s</div>'
                    % (int(x), 16 + lane * LANE, html.escape(label(it)), t))
    z = ''
    if zone:
        top, n, zl = zone
        z = ('<div class="zone" style="top:%dpx;height:%dpx">'
             '<div class="zlab">%s</div></div>'
             % (8 + top * LANE, n * LANE - 10, html.escape(zl)))
    return ('<div class="race"><div class="rh"><span class="rn">%s</span>'
            '<span class="rd">%s</span></div>'
            '<div class="board"><div class="ylab"><span></span><span></span></div>'
            '<div class="track" style="height:%dpx">%s%s</div></div>'
            '<div class="xlab"><span>小さい</span><span></span><span>大きい　→</span></div></div>'
            % (html.escape(title), html.escape(sub), NL * LANE + 26, z, '\n'.join(body)))


def page(blocks, head="帯の図", sub=""):
    css = open(os.path.join(HERE, 'band.css')).read()
    extra = ('.item{position:absolute;transform:translate(-50%,0);text-align:center;width:128px}'
             '.dot{width:16px;height:16px;border-radius:50%;background:#d8c7ae;margin:0 auto 4px}'
             '.lb{font-size:11px;color:#f6f1e8;font-weight:700}')
    return ('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>%s</title>'
            '<style>%s\n%s</style></head><body>'
            '<div class="head"><div class="kicker">帯の図</div><h1>%s</h1>'
            '<div class="sub">%s</div></div>%s</body></html>'
            % (html.escape(head), css, extra, html.escape(head), sub, '\n'.join(blocks)))


if __name__ == '__main__':
    demo = [{'n': '対象%d' % i, 'v': i / 9} for i in range(10)]
    b = render(demo, key=lambda d: d['v'], label=lambda d: d['n'],
               tags=lambda d: ['<span class="sm">上位</span>'] if d['v'] < 0.25 else [],
               zone=(0, 2, '注目する範囲'),
               title='例', sub='横＝順序のある量（右が大きい）')
    out = sys.argv[1] if len(sys.argv) > 1 else 'band_demo.html'
    open(out, 'w').write(page([b], '帯の図の最小例',
        '横に意味を、縦は重なり避け。<b>縦に意味が無いなら縦に帯を引かないこと。</b>'))
    print(out)
