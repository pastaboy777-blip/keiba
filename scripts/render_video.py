"""`scripts/show.py` の出力を SNS 投稿用の縦型 mp4 に描画する。

show.py を色付きで実行して出力を取り込み、ターミナル画面を1フレームずつ
画像として描き起こして ffmpeg で mp4 にする。実際の端末が無い環境でも
「動いている映像」を生成できる。

必要:
    pip install pillow imageio-ffmpeg

実行:
    python3 scripts/render_video.py --out out/nankeiba.mp4
    python3 scripts/render_video.py --place 船橋 --fps 30
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]

# 半角用(記号・罫線・ブロック)と全角用(日本語)を1文字ずつ使い分ける。
FONT_ASCII = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_ASCII_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
FONT_CJK = "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"

BG = (8, 8, 10)
FG = (222, 222, 226)

# show.py の Style が使う 256 色番号 -> RGB
ANSI256 = {
    203: (255, 95, 95),      # red
    114: (135, 215, 135),    # green
    221: (255, 215, 95),     # yellow
    75: (95, 175, 255),      # blue
    176: (215, 135, 215),    # magenta
    80: (95, 215, 215),      # cyan
    244: (138, 138, 145),    # gray
    255: (240, 240, 245),    # white
}
DIM = (120, 120, 128)

SGR = re.compile(r"\033\[([0-9;]*)m")


# ---------------------------------------------------------------- ANSI 解析

def parse_ansi(text: str) -> list[list[tuple[tuple[int, int, int], bool, str]]]:
    """ANSI 付きテキストを 行 -> [(色, 太字, 文字列)] に変換する。"""
    lines: list[list[tuple[tuple[int, int, int], bool, str]]] = []
    color, bold = FG, False
    for raw in text.split("\n"):
        segs: list[tuple[tuple[int, int, int], bool, str]] = []
        pos = 0
        for m in SGR.finditer(raw):
            if m.start() > pos:
                segs.append((color, bold, raw[pos:m.start()]))
            for code in (m.group(1) or "0").split(";"):
                pass
            params = [p for p in (m.group(1) or "0").split(";")]
            if params[:2] == ["38", "5"] and len(params) >= 3:
                color = ANSI256.get(int(params[2]), FG)
            elif params[0] == "0":
                color, bold = FG, False
            elif params[0] == "1":
                bold = True
            elif params[0] == "2":
                color = DIM
            pos = m.end()
        if pos < len(raw):
            segs.append((color, bold, raw[pos:]))
        lines.append(segs)
    return lines


def visible_text(segs) -> str:
    return "".join(t for _, _, t in segs)


def visible_text_all(lines) -> str:
    return "\n".join(visible_text(segs) for segs in lines)


def truncate(segs, n_cells: int):
    """行頭から n_cells 桁ぶんだけ残す(タイプライタ演出用)。"""
    out, used = [], 0
    for color, bold, text in segs:
        buf = ""
        for ch in text:
            w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
            if used + w > n_cells:
                if buf:
                    out.append((color, bold, buf))
                return out
            buf += ch
            used += w
        if buf:
            out.append((color, bold, buf))
    return out


def cell_len(segs) -> int:
    total = 0
    for _, _, text in segs:
        for ch in text:
            total += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return total


# ---------------------------------------------------------------- 描画

# 罫線・ブロックはフォント任せにすると隙間が出るので図形で描く。
# 値は (左, 右, 上, 下) の各方向に腕があるか、と太さ("t"=細/"h"=太)。
BOX_ARMS = {
    "─": (1, 1, 0, 0, "t"), "━": (1, 1, 0, 0, "h"),
    "│": (0, 0, 1, 1, "t"), "┃": (0, 0, 1, 1, "h"),
    "┌": (0, 1, 0, 1, "t"), "┐": (1, 0, 0, 1, "t"),
    "└": (0, 1, 1, 0, "t"), "┘": (1, 0, 1, 0, "t"),
    "┏": (0, 1, 0, 1, "h"), "┓": (1, 0, 0, 1, "h"),
    "┗": (0, 1, 1, 0, "h"), "┛": (1, 0, 1, 0, "h"),
    "├": (0, 1, 1, 1, "t"), "┤": (1, 0, 1, 1, "t"),
}
# ブロック要素: セル高さに対する充填率(下寄せ)と色の減衰率
BLOCKS = {"█": (1.0, 1.0), "▇": (0.875, 1.0), "▆": (0.75, 1.0),
          "▅": (0.625, 1.0), "░": (1.0, 0.22), "▒": (1.0, 0.42)}
# 丸数字は半角幅の字形がどのフォントにも無いので、円+数字で描く
CIRCLED = {ch: str(i) for i, ch in enumerate("①②③④⑤⑥⑦⑧⑨", 1)}


class Renderer:
    def __init__(self, cols: int, rows: int, cell_w: int, cell_h: int,
                 margin_x: int, margin_y: int):
        self.cols, self.rows = cols, rows
        self.cell_w, self.cell_h = cell_w, cell_h
        self.mx, self.my = margin_x, margin_y
        self.size = (cols * cell_w + margin_x * 2, rows * cell_h + margin_y * 2)
        # IPAGothic は半角=cell_w・全角=cell_w*2 に正確に収まるので基準にする。
        self.f_jp = ImageFont.truetype(FONT_CJK, cell_w * 2)
        size_ascii = cell_w * 2
        while ImageFont.truetype(FONT_ASCII, size_ascii).getlength("M") > cell_w:
            size_ascii -= 1
        self.f_ascii = ImageFont.truetype(FONT_ASCII, size_ascii)
        self.baseline = int(cell_h * 0.78)
        self._font_cache: dict[str, ImageFont.FreeTypeFont] = {}
        self._notdef: dict[int, object] = {}
        self._digit = ImageFont.truetype(FONT_ASCII, max(8, int(cell_w * 0.95)))

    @staticmethod
    def _mask_sig(font, ch: str):
        m = font.getmask(ch)
        return (m.size, bytes(m) if m.size[0] and m.size[1] else b"")

    def _has(self, font, ch: str) -> bool:
        """字形を持つか。豆腐(.notdef)は「無い」と判定する。"""
        key = id(font)
        if key not in self._notdef:
            self._notdef[key] = self._mask_sig(font, "\ue0ff")
        try:
            return self._mask_sig(font, ch) != self._notdef[key]
        except Exception:
            return False

    def _font_for(self, ch: str, cells: int):
        """セル幅に収まり、かつ字形を持つフォントを選ぶ。"""
        cached = self._font_cache.get(ch)
        if cached is not None:
            return cached
        target = cells * self.cell_w + 0.5
        for font in (self.f_jp, self.f_ascii):
            if self._has(font, ch) and font.getlength(ch) <= target:
                self._font_cache[ch] = font
                return font
        # どちらも幅超過なら IPAGothic を縮めて収める(●▲ などの曖昧幅文字)
        base = self.f_jp if self._has(self.f_jp, ch) else self.f_ascii
        adv = base.getlength(ch) or target
        shrunk = ImageFont.truetype(
            base.path, max(6, int(base.size * target / adv)))
        self._font_cache[ch] = shrunk
        return shrunk

    def _draw_cell(self, d, ch: str, x: int, y: int, color) -> None:
        cw, ch_h = self.cell_w, self.cell_h
        if ch in BOX_ARMS:
            left, right, up, down, weight = BOX_ARMS[ch]
            t = max(2, cw // 8) if weight == "h" else max(1, cw // 12)
            cx, cy = x + cw // 2, y + ch_h // 2
            half = t // 2
            if left:
                d.rectangle([x, cy - half, cx + half, cy - half + t - 1], fill=color)
            if right:
                d.rectangle([cx - half, cy - half, x + cw, cy - half + t - 1], fill=color)
            if up:
                d.rectangle([cx - half, y, cx - half + t - 1, cy + half], fill=color)
            if down:
                d.rectangle([cx - half, cy - half, cx - half + t - 1, y + ch_h], fill=color)
            return
        if ch in CIRCLED:
            r = min(cw * 0.72, ch_h * 0.34)
            cx, cy = x + cw / 2, y + ch_h * 0.52
            d.ellipse([cx - r, cy - r, cx + r, cy + r],
                      outline=color, width=max(1, cw // 12))
            d.text((cx, cy + 1), CIRCLED[ch], font=self._digit,
                   fill=color, anchor="mm")
            return
        if ch in BLOCKS:
            frac, fade = BLOCKS[ch]
            h = int(ch_h * frac)
            col = tuple(int(c * fade) for c in color)
            d.rectangle([x, y + ch_h - h, x + cw - 1, y + ch_h - 1], fill=col)
            return
        cells = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        d.text((x, y + self.baseline), ch, font=self._font_for(ch, cells),
               fill=color, anchor="ls")

    def render(self, lines) -> Image.Image:
        img = Image.new("RGB", self.size, BG)
        d = ImageDraw.Draw(img)
        for row, segs in enumerate(lines[-self.rows:]):
            y = self.my + row * self.cell_h
            col = 0
            for color, bold, text in segs:
                for ch in text:
                    if col >= self.cols:
                        break
                    if ch != " ":
                        self._draw_cell(d, ch, self.mx + col * self.cell_w, y, color)
                    col += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        return img

    def card(self, headline: list[tuple[str, tuple[int, int, int], float]],
             gap: float = 1.35) -> Image.Image:
        """中央寄せのカード。headline は (文字列, 色, 文字サイズ倍率)。"""
        img = Image.new("RGB", self.size, BG)
        d = ImageDraw.Draw(img)
        unit = self.cell_w * 2
        heights = [unit * scale * gap for _, _, scale in headline]
        y = self.size[1] / 2 - sum(heights) / 2
        for (text, color, scale), h in zip(headline, heights):
            font = ImageFont.truetype(FONT_CJK, int(unit * scale))
            d.text((self.size[0] / 2, y + h / 2), text,
                   font=font, fill=color, anchor="mm")
            y += h
        return img


# ---------------------------------------------------------------- 演出タイミング

BOX_CHARS = set("┌┐└┘─│┏┓┗┛━┃")


def plan(lines, fps: int):
    """(行リストのスナップショット, 表示フレーム数) を順に生成する。

    行の性質に応じて表示時間を変え、プログレスバーは充填を、
    強調行はタイプライタをフレームに展開する。
    """
    screen: list = []
    out: list[tuple[list, int]] = []

    def emit(frames: int) -> None:
        out.append((list(screen), max(1, frames)))

    for segs in lines:
        text = visible_text(segs)
        stripped = text.strip()

        if not stripped:
            screen.append(segs)
            emit(fps // 12)
            continue

        # プログレスバー: 空バーから徐々に埋める
        if "█" in text and "✓" in text:
            bar = "█" * text.count("█")
            steps = 14
            for i in range(steps + 1):
                filled = round(len(bar) * i / steps)
                shown = "█" * filled + "░" * (len(bar) - filled)
                frame = [
                    (c, b, t.replace(bar, shown) if bar in t else t)
                    for c, b, t in segs
                ]
                if i < steps:
                    frame = [
                        (c, b, t.replace("✓", " ")) for c, b, t in frame
                    ]
                screen.append(frame)
                emit(max(1, fps // 20))
                screen.pop()
            screen.append(segs)
            emit(fps // 6)
            continue

        # 枠線はまとめて素早く
        if stripped and all(ch in BOX_CHARS for ch in stripped):
            screen.append(segs)
            emit(fps // 12)
            continue

        # 強調行は1文字ずつ
        if any(k in text for k in ("ズブ穴検出", "差 ", "的中率ではなく", "$ python3")):
            n = cell_len(segs)
            for i in range(1, n + 1):
                screen.append(truncate(segs, i))
                emit(1)
                screen.pop()
            screen.append(segs)
            emit(fps // 2)
            continue

        screen.append(segs)
        # 回収率の大きな数字は長めに見せる
        emit(int(fps * 0.9) if "回収率" in text else max(2, fps // 7))

    emit(fps * 2)  # 最後の画面を保持
    return out


# ---------------------------------------------------------------- メイン

def main() -> None:
    ap = argparse.ArgumentParser(description="show.py を mp4 に描画する")
    ap.add_argument("--out", default="out/nankeiba.mp4")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--cols", type=int, default=64)
    ap.add_argument("--rows", type=int, default=52)
    ap.add_argument("--cell-w", type=int, default=16)
    ap.add_argument("--cell-h", type=int, default=35)
    ap.add_argument("--margin-x", type=int, default=28)
    ap.add_argument("--margin-y", type=int, default=50)
    ap.add_argument("--place", default="川崎")
    ap.add_argument("--races", type=int, default=600)
    ap.add_argument("--no-title-card", action="store_true")
    args = ap.parse_args()

    cmd = [sys.executable, str(ROOT / "scripts" / "show.py"), "--instant",
           "--place", args.place, "--races", str(args.races),
           "--width", str(args.cols)]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    if proc.returncode != 0:
        sys.exit(f"show.py が失敗しました:\n{proc.stderr}")

    lines = parse_ansi(proc.stdout.rstrip("\n"))
    r = Renderer(args.cols, args.rows, args.cell_w, args.cell_h,
                 args.margin_x, args.margin_y)
    frames = plan(lines, args.fps)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    import imageio_ffmpeg
    ff = [
        imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{r.size[0]}x{r.size[1]}", "-r", str(args.fps), "-i", "-",
        "-c:v", "libx264", "-preset", "slow", "-crf", "20",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out),
    ]
    pipe = subprocess.Popen(ff, stdin=subprocess.PIPE)
    assert pipe.stdin is not None

    def hold(image, seconds: float) -> int:
        buf = image.tobytes()
        n = int(args.fps * seconds)
        for _ in range(n):
            pipe.stdin.write(buf)
        return n

    total = 0
    if not args.no_title_card:
        total += hold(r.card([
            ("AIに南関競馬を", (240, 240, 245), 3.2),
            ("予想させたら", (240, 240, 245), 3.2),
            ("", BG, 0.6),
            ("Claude Code で自作した予想エンジン", ANSI256[80], 1.25),
        ]), 2.2)

    for i, (snapshot, count) in enumerate(frames):
        buf = r.render(snapshot).tobytes()
        for _ in range(count):
            pipe.stdin.write(buf)
            total += 1
        if i % 25 == 0:
            print(f"\r  描画 {i + 1}/{len(frames)} 画面  {total} フレーム",
                  end="", flush=True)

    # エンドカード: 動画で一番効く「対比」をもう一度大きく出す
    roi = re.search(r"回収率\s+([0-9.]+%)", visible_text_all(lines))
    naive = re.search(r"人気順に4点買い\s+([0-9.]+%)", visible_text_all(lines))
    if roi and naive and not args.no_title_card:
        total += hold(r.card([
            ("人気順に買う", (150, 150, 158), 1.5),
            (naive.group(1), ANSI256[203], 4.2),
            ("", BG, 0.5),
            ("期待値プラスだけ買う", (150, 150, 158), 1.5),
            (roi.group(1), ANSI256[114], 5.2),
            ("", BG, 0.8),
            ("※合成データによるロジック検証", (110, 110, 118), 0.95),
        ]), 3.2)

    pipe.stdin.close()
    pipe.wait()
    print(f"\r  完了: {out}  {total} フレーム / {total / args.fps:.1f} 秒"
          f"  {r.size[0]}x{r.size[1]}" + " " * 12)


if __name__ == "__main__":
    main()
