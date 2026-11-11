"""展開図の馬の絵 ── ユーザーからもらった8枠ぶんのイラストを切り出して、
ゼッケンの数字を馬番に描き替える。

  python3 uma_img.py --build <元画像.png>   # uma/ に uma1.png 〜 uma8.png を作る
  python3 uma_img.py --sheet <出力.png>      # 確認用に並べて出す

★ 2026-11-11、ユーザーから「それでこれを使ってくれない？？ 馬の絵」。
  3×3に9頭並んだ画像で、左上から 1白 2黒 3赤 4青 5黄 6緑 7橙 8桃、9頭目は8枠と同じ桃。
  背景は透明（アルファ0）。

★ ゼッケンの数字は**元絵では枠番**。南関のゼッケンは**馬番**なので描き替える。
  やり方は「布の色の行ごとに左端と右端を取って、その間を布の色で塗りつぶす」。
  数字は布の内側にあるので、これで消える。消したあとに馬番を中央に描く。

★ 10頭以上の鞍では同じ枠色が2頭出る。**見分けるのはゼッケンの数字（＝馬番）。**
"""
import os, sys, json
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "uma")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
# 枠ごとの布の色（元絵から拾った実測値）と、その上に乗せる数字の色
CLOTH = {1: ((235, 235, 235), (34, 34, 34)), 2: ((36, 36, 36), (255, 255, 255)),
         3: ((237, 55, 55), (255, 255, 255)), 4: ((46, 49, 146), (255, 255, 255)),
         5: ((252, 202, 20), (34, 34, 34)), 6: ((0, 130, 61), (255, 255, 255)),
         7: ((247, 130, 20), (34, 34, 34)), 8: ((255, 123, 172), (34, 34, 34))}


def _near(p, c, t=26):
    return abs(p[0] - c[0]) <= t and abs(p[1] - c[1]) <= t and abs(p[2] - c[2]) <= t


def _cloth_box(im, col):
    """布の色の塊のうち、いちばん大きいものの bbox。帽子も同じ色なので塊で選ぶ。"""
    w, h = im.size
    px = im.load()
    seen = [[False] * w for _ in range(h)]
    best = None
    for y in range(h):
        for x in range(w):
            if seen[y][x] or px[x, y][3] < 120 or not _near(px[x, y], col):
                continue
            st = [(x, y)]
            seen[y][x] = True
            xs = [x]; ys = [y]
            while st:
                cx, cy = st.pop()
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h and not seen[ny][nx] \
                            and px[nx, ny][3] >= 120 and _near(px[nx, ny], col):
                        seen[ny][nx] = True
                        st.append((nx, ny)); xs.append(nx); ys.append(ny)
            if best is None or len(xs) > best[0]:
                best = (len(xs), min(xs), min(ys), max(xs), max(ys))
    return best[1:] if best else None


def build(src):
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    cw, ch = w // 3, h // 3
    os.makedirs(OUT, exist_ok=True)
    meta = {}
    for k in range(1, 9):
        r, c = divmod(k - 1, 3)
        cell = im.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))
        cell = cell.crop(cell.getbbox())
        col, _ = CLOTH[k]
        bb = _cloth_box(cell, col)
        if not bb:
            print("枠%d 布が見つからない" % k); continue
        x0, y0, x1, y1 = bb
        px = cell.load()
        # 行ごとに布の色の左端〜右端を塗りつぶす＝中の数字が消える
        for y in range(y0, y1 + 1):
            xs = [x for x in range(x0, x1 + 1)
                  if px[x, y][3] >= 120 and _near(px[x, y], col)]
            if len(xs) < 3:
                continue
            for x in range(min(xs), max(xs) + 1):
                if px[x, y][3] >= 120:
                    px[x, y] = (col[0], col[1], col[2], 255)
        cell.save(os.path.join(OUT, "uma%d.png" % k))
        meta[k] = [x0, y0, x1, y1, list(cell.size)]
        print("枠%d → uma%d.png %s  布 (%d,%d)-(%d,%d)" % (k, k, cell.size, x0, y0, x1, y1))
    json.dump(meta, open(os.path.join(OUT, "cloth.json"), "w"))


def horse(waku, ub, px=78, left=True):
    """枠と馬番 → その馬のPNG（PIL Image）。ゼッケンに馬番を描く。

    ★ left=True で**左向き**（2026-11-11、ユーザーの指示 ──「この絵を左向きに出来ない？」）。
      絵を先に反転してから数字を描く。順番を逆にすると数字まで裏返る。
    """
    meta = json.load(open(os.path.join(OUT, "cloth.json")))
    im = Image.open(os.path.join(OUT, "uma%d.png" % waku)).convert("RGBA")
    x0, y0, x1, y1, _ = meta[str(waku)]
    if left:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
        x0, x1 = im.size[0] - x1, im.size[0] - x0
    d = ImageDraw.Draw(im)
    _, tc = CLOTH[waku]
    s = int((y1 - y0) * (0.86 if ub < 10 else 0.74))
    f = ImageFont.truetype(FONT, s)
    t = str(ub)
    bb = d.textbbox((0, 0), t, font=f)
    d.text(((x0 + x1) / 2 - (bb[0] + bb[2]) / 2, (y0 + y1) / 2 - (bb[1] + bb[3]) / 2),
           t, font=f, fill=tc + (255,))
    k = px / im.size[1]
    return im.resize((max(1, int(im.size[0] * k)), px), Image.LANCZOS)


def sheet(out):
    ims = [horse(w, w * 2, 120) for w in range(1, 9)]
    cw = max(i.size[0] for i in ims) + 10
    sh = Image.new("RGBA", (cw * 4, 280), (255, 255, 255, 255))
    for i, im in enumerate(ims):
        sh.paste(im, ((i % 4) * cw + 5, (i // 4) * 140 + 10), im)
    sh.save(out)
    print(out, sh.size)


def main():
    a = sys.argv[1:]
    if "--build" in a:
        build(a[a.index("--build") + 1])
    elif "--sheet" in a:
        sheet(a[a.index("--sheet") + 1])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
