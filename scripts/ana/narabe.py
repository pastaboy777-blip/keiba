"""1鞍の2枚（最初の角／直線）を、1枚に横並びで組み直す。

  python3 narabe.py <最初の角のzu.html> <直線のzu.html> [--out <dir|file>] [--png]

ユーザーの依頼（2026-11-16）── 他所の出力の画像を見せて「**この形にしたい**」。
その形は「**見出しは1つ・左（最初の角）を狭く・右（直線）を広く・間に大きい矢印**」。

★★ **真似するのはレイアウトだけ。図の中身は1つも変えていない。**
  `tenkai_zu.py` には**1行も手を入れていない**（既存の出力はバイト単位でそのまま）。
  このツールは **できあがった2枚のHTMLを読んで、枠を組み直すだけ**。
  - 馬の `left` / `top` ・馬番・馬名・札（終い順位・過去 外n/m・▲▼・先頭候補・
    過去走なし・道悪・調教）は**元の2枚からそのまま運ぶ**
  - **直線の図の向きは変えない** ── 左がゴール・上がラチ・馬の絵と矢印は左向き
    （CLAUDE.md ルール60。ユーザーが「素晴らしい」と確認した形）
  - 1枚目の向き・上下（`MIRROR` / `VFLIP`）も元のまま。「ラチ沿い」の文字が
    枠の上に出るか下に出るかも、読み込んだHTMLのとおり（ルール43・60★）
  - CSSは**元のものをそのまま使い**、横並びのための分だけ後ろに足している
    （後ろに足した分で `body` の幅だけ上書き。元の1行も書き換えていない）

── 1枚にまとめるときに1回だけにするもの（ユーザーの指示）

  見出し（2026.11.16 MON — 大井／馬場 重 ／ 展開予想）・鞍名・距離・頭数・ペースの帯・
  過去の傾向・見解。元は2枚ぶんで2回ずつ出ていたのを**全部1回**にする。
  見解だけは文が2枚で違う（「最初のコーナーで前に行くのは」／「直線で前にいるのは」）ので、
  **1つの欄に2行**入れる。文そのものは**元のまま**で、こちらで書き換えてはいない。

── 足したもの（レイアウトの部品）

  ・左右の小見出し …「最初のコーナー」（`--kado` で「3コーナー」などに差し替えられる）と
    「4コーナー（直線を向いたところ）」
  ・各図の中の進行方向 … 左は**読み込んだHTMLの1行そのまま**（`--no-pct` の判定）、
    右は「**← 左が前（ゴール）**」で固定（ルール60。向きは絶対に変えない）
  ・間の大きい黄色の三角
  ・下の2行 … 「前に行くのは ①⑨③⑮⑭」（1枚目の上位5頭）と
    「→ 4角で前目 ①⑨③」（直線の図の上位3頭）。並びは**図の並びそのまま**
    （`tenkai_zu.py` は pos の順に馬を書き出すので、書き出し順＝図の前からの順）

  ★ 黄色い囲み（狙う一帯）は**まだ入れていない**。`tenkai_zu.py --ana` の仕組みが
    あるので、入れるならそちら側で囲ってから読み込む（次の段でユーザーと決める）。

── 渡せるもの

  --out <dir|file>  出力先。ディレクトリなら `narabe.html`。既定は1枚目の隣
  --png <file>      PNGも出す（Chromium。`--out` を省くとPNGの隣にHTMLを置く）
  --sl 0.50         左（最初の角）の縮尺。既定 0.50
  --sr 1.00         右（直線）の縮尺。既定 1.00 ＝ **等倍**（1pxも拡げない）
                    左:右＝1:2 は既定のこの2つで出る
  --kado            左の小見出しを `tenkai_zu.kado()`（「3コーナー」など）にする。
                    既定は読み込んだHTMLの言い方（「最初のコーナー」）。
                    ★ ルール47で**角の名前は出さない**と決めた経緯があるので既定は off
  --R 1,5           この鞍だけ（既定は1枚目に入っている全鞍）

── 気をつける所

  ・2枚は**同じ鞍・同じ出馬表**から出したものを渡す。鞍番号（1R…）で突き合わせる
  ・縮尺は CSS の `transform:scale` でかけている。**HTMLの中の `left`/`top` は
    1文字も書き換えていない**ので、元の2枚と突き合わせれば完全一致する
  ・Chromium は `tojitsu.py` と同じやり方で探す（決め打ちしない）
"""
import sys, os, re, glob, html as H

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

FIXW = 982          # .race の中身の幅（body 1060 − padding 76 − border 2）。
                    # この中で .track が margin 16px を取るので中身は 950px ＝ 元と同じ
TRK_MG = 22         # .track の上下 margin（10 + 12）
ARW_W = 68          # 矢印の列の幅
SCALE = 2           # PNGの --force-device-scale-factor（tojitsu.py と同じ）
CROP_PAD = 40       # 下の余白（tojitsu.py と同じ）

COLH_R = '4コーナー（直線を向いたところ）'
KD_R = '← 左が前（ゴール）'

# 横並びのための CSS。**元の CSS は1文字も変えず、後ろに足すだけ。**
CSS = """
/* ───── narabe.py が足した分（横並びの枠組みだけ。図の中身には触っていない） ───── */
body{width:%(W)dpx}
.two{display:flex;align-items:stretch;margin:0 16px 0}
.col{position:relative}
.colh{font-size:13.5px;font-weight:800;color:#f2f2f4;margin:11px 2px 0;letter-spacing:.04em}
.col .kd{margin:3px 2px 4px}
.col .kd .ar{font-size:15px;font-weight:900;color:#dcdce4;margin-right:3px}
.col .rachi{margin:4px 2px 1px}
.col .rachi.d{margin:1px 2px 4px}
.zoom{position:relative}
.fix{position:absolute;left:0;top:0;width:%(FIXW)dpx;transform-origin:0 0}
.arw{flex:0 0 %(ARW)dpx;display:flex;align-items:center;justify-content:center}
.hint{margin:8px 18px 0;font-size:14px;font-weight:800;color:#e4e4ea}
.hint.b{margin:4px 18px 12px;color:#f5c84a}
.hint b{font-size:17px;color:#fff;letter-spacing:.05em;margin-left:3px}
.hint.b b{color:#f5c84a}
.view p+p{margin-top:3px}
"""

ARW = ('<svg width="46" height="60" viewBox="0 0 46 60" aria-hidden="true">'
       '<polygon points="4,4 42,30 4,56" fill="#f5c84a"/></svg>')


def die(msg, code=2):
    print("\n★ 止めました: %s" % msg)
    sys.exit(code)


def maru(n):
    """1→① … 20→⑳。21以上はそのまま数字で書く"""
    return chr(0x245F + n) if 1 <= n <= 20 else str(n)


# ───────────────────────── 読み取り ─────────────────────────

TAG = re.compile(r'</?div\b')


def blk(h, i):
    """h[i] が `<div` の先頭のとき、対応する `</div>` の直後までを返す"""
    d, j = 0, i
    while True:
        m = TAG.search(h, j)
        if not m:
            return h[i:], len(h)
        d += 1 if m.group(0) == '<div' else -1
        j = m.end()
        if d == 0:
            j = h.index('>', j) + 1
            return h[i:j], j


def pick(h, pat):
    """class が pat で始まる div を1つ取る（入れ子ごと）。無ければ ''"""
    m = re.search(pat, h)
    return blk(h, m.start())[0] if m else ''


def one(h, pat):
    """入れ子のない1行の div を取る（.kd / .rachi）。無ければ ''"""
    m = re.search(pat + r'[^>]*>.*?</div>', h)
    return m.group(0) if m else ''


def horses(track):
    """馬の並び（書き出し順＝図の前からの順）。left/top・馬番・馬名を拾う"""
    out, ms = [], list(re.finditer(
        r'<div class="horse" style="left:(-?\d+)px;top:(-?\d+)px"', track))
    for k, m in enumerate(ms):
        # ★ 馬の div は base64 の絵を抱えていて1万字を超える。
        #   次の馬の手前まで（最後は track の終わりまで）を丸ごと見る。
        s = track[m.end():ms[k + 1].start() if k + 1 < len(ms) else len(track)]
        nb = re.search(r'<span class="n"[^>]*>(\d+)</span>', s)
        nm = re.search(r'<span class="nm">(.*?)</span>', s)
        out.append((int(m.group(1)), int(m.group(2)),
                    int(nb.group(1)) if nb else 0, H.unescape(nm.group(1)) if nm else ''))
    return out


def races(path):
    """zu.html から鞍ごとの部品を取り出す。**中身は切り出すだけで書き換えない。**"""
    h = open(path, encoding="utf-8").read()
    css = h.split("<style>", 1)[1].split("</style>", 1)[0] if "<style>" in h else ""
    head = pick(h, r'<div class="head">')
    tail = one(h, r'<div class="tail"')
    out = []
    for m in re.finditer(r'<div class="race">', h):
        b = blk(h, m.start())[0]
        trk = pick(b, r'<div class="track"')
        i = b.find(trk)
        rn = re.search(r'<span class="rn">(\d+)R</span>', b)
        out.append(dict(
            R=int(rn.group(1)) if rn else 0,
            rh=pick(b, r'<div class="rh">'),
            pbar=pick(b, r'<div class="pbar'),
            kd=one(b, r'<div class="kd"'),
            track=trk,
            rachi_u=one(b[:i], r'<div class="rachi"'),
            rachi_d=one(b[i:], r'<div class="rachi d"'),
            keiko=pick(b, r'<div class="keiko">'),
            view=pick(b, r'<div class="view">'),
            uma=horses(trk),
        ))
    return dict(css=css, head=head, tail=tail, R={r['R']: r for r in out},
                order=[r['R'] for r in out])


def kd_split(kd):
    """`<div class="kd">最初のコーナー　→ 右が前（…）</div>` を（名前, 向きの文）に割る"""
    t = re.sub(r'<[^>]+>', '', kd).strip()
    if '　' in t:
        a, b = t.split('　', 1)
        return a.strip(), b.strip()
    return '', t


def kd_html(txt):
    """向きの文。先頭の矢印だけ少し大きく出す（文字そのものは変えない）"""
    t = H.escape(txt)
    if t[:1] in '←→':
        return '<div class="kd"><span class="ar">%s</span>%s</div>' % (t[0], t[1:].lstrip())
    return '<div class="kd">%s</div>' % t


# ───────────────────────── 組み立て ─────────────────────────

def col(cls, colh, kd, r, s):
    hh = int(re.search(r'height:(\d+)px', r['track']).group(1)) + TRK_MG
    return ('<div class="col %s" style="width:%dpx">'
            '<div class="colh">%s</div>%s%s'
            '<div class="zoom" style="width:%dpx;height:%dpx">'
            '<div class="fix" style="transform:scale(%.4f)">%s</div></div>%s</div>'
            % (cls, int(round(FIXW * s)), H.escape(colh), kd, r['rachi_u'],
               int(round(FIXW * s)), int(round(hh * s)), s, r['track'], r['rachi_d']))


def race_html(a, b, sl, sr, kado1):
    """1鞍ぶん。見出し・ペース・過去の傾向・見解は**1回だけ**"""
    nm_a = kd_split(a['kd'])[0] or '最初のコーナー'
    mk = lambda xs, n: ''.join(maru(u[2]) for u in xs[:n])
    views = []
    for r in (a, b):
        p = re.search(r'<p>(.*?)</p>', r['view'], re.S)
        if p and p.group(1).strip():
            views.append(p.group(1))
    view = ('<div class="view"><h4>見解</h4>%s</div>'
            % ''.join('<p>%s</p>' % v for v in views)) if views else ''
    return ('<div class="race">%s%s<div class="two">%s'
            '<div class="arw">%s</div>%s</div>'
            '<div class="hint">前に行くのは<b>%s</b></div>'
            '<div class="hint b">→ 4角で前目<b>%s</b></div>'
            '%s%s</div>'
            % (a['rh'], a['pbar'],
               col('l', kado1 or nm_a, kd_html(kd_split(a['kd'])[1]), a, sl),
               ARW,
               col('r', COLH_R, kd_html(KD_R), b, sr),
               mk(a['uma'], 5), mk(b['uma'], 3),
               a['keiko'] or b['keiko'], view))


def build(pa, pb, sl, sr, only, kado1):
    A, B = races(pa), races(pb)
    if not A['order']:
        die("1枚目に鞍が見つかりません: %s" % pa)
    w = int(round(FIXW * sl)) + ARW_W + int(round(FIXW * sr)) + 32 + 76
    out = []
    for R in A['order']:
        if only and R not in only:
            continue
        if R not in B['R']:
            print("   ※ %dR は2枚目に無いので飛ばします" % R)
            continue
        out.append(race_html(A['R'][R], B['R'][R], sl, sr, kado1))
    if not out:
        die("組める鞍がありませんでした")
    return ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<title>展開予想</title><style>%s%s</style></head><body>%s%s%s</body></html>'
            % (A['css'], CSS % dict(W=w, FIXW=FIXW, ARW=ARW_W),
               A['head'], ''.join(out), A['tail'])), w, len(out)


# ───────────────────────── PNG（tojitsu.py と同じ作り） ─────────────────────────

def png(path_html, out_png, w, nraces):
    import subprocess
    from PIL import Image
    import tojitsu                      # find_chrome / bottom_of を読むだけ（1行も直していない）
    Image.MAX_IMAGE_PIXELS = None
    chrome = tojitsu.find_chrome()
    if not chrome:
        print("   ※ Chromium が見つからないので画像は作りません")
        return None
    raw = out_png + ".raw.png"
    h = min(max(900, 760 * max(1, nraces) + 300), 16000)
    im = None
    for _ in range(4):
        cmd = [chrome, "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
               "--force-device-scale-factor=%d" % SCALE,
               "--window-size=%d,%d" % (w, h),
               "--screenshot=" + raw, "file://" + os.path.abspath(path_html)]
        r = subprocess.run(cmd, capture_output=True, timeout=300)
        if not os.path.exists(raw):
            print("   ※ 画像化に失敗: %s"
                  % (r.stderr.decode("utf-8", "replace")[-300:] or "画像が出ませんでした"))
            return None
        im = Image.open(raw).convert("RGB")
        if tojitsu.bottom_of(im) < im.size[1] - 4 or h >= 30000:
            break
        h = min(int(h * 1.8), 30000)
        print("   ※ 下まで入らなかったので窓を %dpx に広げて撮り直します" % h)
    last = tojitsu.bottom_of(im)
    im.crop((0, 0, im.size[0], min(im.size[1], last + CROP_PAD))).save(out_png)
    try:
        os.remove(raw)
    except OSError:
        pass
    return out_png


# ───────────────────────── 本体 ─────────────────────────

def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    g = lambda k, d=None: a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else d
    VAL = ("--out", "--png", "--sl", "--sr", "--R")
    pos, i = [], 0
    while i < len(a):
        if a[i] in VAL:
            i += 2
            continue
        if not a[i].startswith("-"):
            pos.append(a[i])
        i += 1
    if len(pos) < 2:
        die("最初の角のHTMLと直線のHTMLを2つ渡してください（--help で使い方）")
    pa, pb = pos[0], pos[1]
    for p in (pa, pb):
        if not os.path.exists(p):
            die("ありません: %s" % p)
    sl, sr = float(g("--sl", 0.50)), float(g("--sr", 1.00))
    only = {int(x) for x in re.findall(r'\d+', g("--R", "") or "")}
    out_png = g("--png")
    out = g("--out")
    if out and os.path.isdir(out):
        out = os.path.join(out, "narabe.html")
    if not out:
        out = (os.path.splitext(out_png)[0] + ".html" if out_png
               else os.path.join(os.path.dirname(os.path.abspath(pa)), "narabe.html"))
    kado1 = ''
    if "--kado" in a:
        import tenkai_zu as TZ
        hd = races(pa)
        ven = re.search(r'—\s*([^／<]+)', hd['head'] or '')
        d = re.search(r'<b>(\d+)m</b>', (hd['R'].get(hd['order'][0], {}) or {}).get('rh', ''))
        if ven and d:
            kado1 = TZ.kado(ven.group(1).strip(), int(d.group(1))) or ''
        if not kado1:
            print("   ※ --kado … 角の名前が決まらないので読み込んだHTMLの言い方を使います")
    doc, w, n = build(pa, pb, sl, sr, only, kado1)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    open(out, "w", encoding="utf-8").write(doc)
    print("━━ 1枚にまとめました（%d鞍・幅 %dpx／左 %.2f倍・右 %.2f倍）" % (n, w, sl, sr))
    print("   HTML %s" % os.path.abspath(out))
    if out_png:
        os.makedirs(os.path.dirname(os.path.abspath(out_png)) or ".", exist_ok=True)
        p = png(out, out_png, w, n)
        if p:
            print("   PNG  %s" % os.path.abspath(p))
    print("   ※ 黄色い囲みは入れていません（`tenkai_zu.py --ana` で囲ってから読み込む）")


if __name__ == "__main__":
    main()
