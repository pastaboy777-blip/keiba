"""KEIBA-AI heads-up display / motion graphics for 「最後の一完歩」.

Every draw_* function paints onto `ctx` over an already painted scene.  `t` is seconds
local to the effect start unless noted.  All functions leave the ctx state unchanged.

Public API
----------
draw_boot(ctx, t, *, target=None, alpha=1.0)
    s01 (t = shot-local 0..6). Boot logo 0.3-1.5, data streams 1.2-3.0, target-lock
    panel 2.5-6 ("0.8%" settles at 3.3, "推奨: 見送り" stamps at 5.0).  `target=(x, y)`
    makes the reticle fly in and lock onto that screen point (lock at ~3.0); None = no
    reticle, panel docks centre-right.
draw_prob_panel(ctx, t, prob, *, x=1480, y=90, alpha=1.0, glitch=0.0,
                label="ハルカゼ 勝率", history=None)
    Compact live readout (380x250 box, top-left at x,y).  prob: float percent (may be
    >100 or negative) or a string ("ERROR" / "計算不能").  history: list of floats/None.
    glitch 0..1 corrupts it.  `t` only drives small animations (use global time).
prob_curve(gt) -> float | str
    Canonical win probability (percent) over GLOBAL time.  0.8 until 29.6, ~3 by 33,
    5/12/27/52/78 through 40, then jitter/overflow (>100, negative) until 41.4, then
    "ERROR" (41.4-42.2) and "計算不能" (>= 42.2).
history_at(gt, n=40, dt=0.12) -> list
    Last n samples of prob_curve (oldest first); non-numeric samples are None.
glitch_curve(gt) -> float
    Suggested `glitch` amount for s05 (0 before 39.6, ramps to 1 at 41.4, settles ~0.35).
glitch_frame(surface_or_ctx, amount, seed=0)
    In-place full-frame digital glitch on an ARGB32 ImageSurface (numpy; ~10-25 ms).
draw_update_panel(ctx, t, *, alpha=1.0, cx=1440, cy=300)
    s07 (t = 0 at global 50.0).  Calm model-update panel; cyan -> warm gold.
draw_title_card(ctx, t, *, alpha=1.0, fade_out=True)
    t = 0 at global 57.4 .. 2.6 at 60.0.  Draws its own translucent dark backdrop.
    With fade_out=True (default) the whole frame fades to BLACK over t 2.2-2.6
    (the film ends on black); pass fade_out=False to handle the fade yourself.
draw_scanlines(ctx, alpha=0.1, spacing=3)
draw_brackets(ctx, x, y, w, h, t, color, *, alpha=1.0, size=26, width=2.0)
"""
import math
import os as _os
import random
import sys as _sys
import cairo

_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
import numpy as np

from config import W, H, FPS, PAL, FONT_SANS, FONT_SANS_M, FONT_SERIF, FONT_IMPACT
from lib.common import (clamp, lerp, invlerp, smoothstep, ease_out_cubic, ease_in_out,
                        ease_out_back, mix_color, noise1, TAU)

MONO = "DejaVu Sans Mono"
CYAN = PAL["neon_cyan"]
PINK = PAL["neon_pink"]
GOLD = (1.00, 0.80, 0.42)
WHITE = (0.92, 0.98, 1.0)
DARK = (0.01, 0.03, 0.06)

_GLYPHS = "0123456789ABCDEF#%&$@<>/\\=+*!?"
_JGLYPHS = "0123456789アイウカキクケコサシセタチツテナニヌハヒフホマミムメヤユヨラリルレロワン#%&"


# ============================================================ low level helpers
def _hot(c, k=0.55):
    """Brighter core colour for neon strokes."""
    return tuple(min(1.0, v + k * (1 - v) + 0.1) for v in c)


def _txt(ctx, s, x, y, size, *, font=MONO, color=CYAN, alpha=1.0, align="left",
         glow=0.6, bold=False, spacing=0.0, hot=True):
    """Neon text: soft stroked halo + bright fill. Returns advance width."""
    if not s or alpha <= 0.003:
        return 0.0
    ctx.save()
    ctx.select_font_face(font, cairo.FONT_SLANT_NORMAL,
                         cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)
    if spacing:
        widths = [ctx.text_extents(ch)[4] for ch in s]
        total = sum(widths) + spacing * (len(s) - 1)
    else:
        total = ctx.text_extents(s)[4]
    if align == "center":
        x -= total / 2
    elif align == "right":
        x -= total
    ctx.new_path()
    if spacing:
        cx = x
        for ch, w_ in zip(s, widths):
            ctx.move_to(cx, y); ctx.text_path(ch); cx += w_ + spacing
    else:
        ctx.move_to(x, y); ctx.text_path(s)
    if glow > 0:
        path = ctx.copy_path()
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)
        for k, a in ((0.28, 0.05), (0.16, 0.09), (0.08, 0.16)):
            ctx.new_path(); ctx.append_path(path)
            ctx.set_line_width(size * k)
            ctx.set_source_rgba(*color[:3], alpha * a * glow)
            ctx.stroke()
        ctx.new_path(); ctx.append_path(path)
    ctx.set_source_rgba(*(_hot(color, 0.35) if hot else color[:3]), alpha)
    ctx.fill()
    ctx.restore()
    return total


def _measure(ctx, s, size, font=MONO, bold=False):
    ctx.save()
    ctx.select_font_face(font, cairo.FONT_SLANT_NORMAL,
                         cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)
    w = ctx.text_extents(s)[4]
    ctx.restore()
    return w


def _line(ctx, x0, y0, x1, y1, color, alpha=1.0, width=1.2, glow=True):
    ctx.save()
    ctx.set_line_cap(cairo.LINE_CAP_BUTT)
    if glow:
        ctx.move_to(x0, y0); ctx.line_to(x1, y1)
        ctx.set_line_width(width * 5); ctx.set_source_rgba(*color, alpha * 0.10); ctx.stroke()
    ctx.move_to(x0, y0); ctx.line_to(x1, y1)
    ctx.set_line_width(width); ctx.set_source_rgba(*_hot(color, 0.3), alpha); ctx.stroke()
    ctx.restore()


def _chamfer_path(ctx, x, y, w, h, c=14):
    ctx.new_path()
    ctx.move_to(x + c, y); ctx.line_to(x + w, y); ctx.line_to(x + w, y + h - c)
    ctx.line_to(x + w - c, y + h); ctx.line_to(x, y + h); ctx.line_to(x, y + c)
    ctx.close_path()


def _panel_bg(ctx, x, y, w, h, color, alpha=1.0, c=14, fill=0.55):
    """Dark glass panel with chamfered corners, thin border and inner hairline grid."""
    ctx.save()
    _chamfer_path(ctx, x, y, w, h, c)
    g = cairo.LinearGradient(x, y, x, y + h)
    g.add_color_stop_rgba(0, 0.02, 0.07, 0.11, fill * alpha)
    g.add_color_stop_rgba(1, 0.01, 0.02, 0.05, fill * 0.85 * alpha)
    ctx.set_source(g); ctx.fill_preserve()
    ctx.clip_preserve()
    # faint inner tint
    ctx.set_source_rgba(*color, 0.035 * alpha); ctx.fill()
    # micro grid
    ctx.set_line_width(1)
    ctx.set_source_rgba(*color, 0.045 * alpha)
    for gx in range(int(x) + 20, int(x + w), 20):
        ctx.move_to(gx + 0.5, y); ctx.line_to(gx + 0.5, y + h)
    ctx.stroke()
    ctx.reset_clip()
    _chamfer_path(ctx, x + 0.5, y + 0.5, w - 1, h - 1, c)
    ctx.set_line_width(4); ctx.set_source_rgba(*color, 0.08 * alpha); ctx.stroke_preserve()
    ctx.set_line_width(1.1); ctx.set_source_rgba(*color, 0.65 * alpha); ctx.stroke()
    # tick marks along top edge
    for i in range(6):
        tx = x + w - 20 - i * 7
        ctx.rectangle(tx, y - 5, 4, 2)
    ctx.set_source_rgba(*color, 0.8 * alpha); ctx.fill()
    ctx.restore()


def _bar(ctx, x, y, w, h, frac, color, alpha=1.0, segments=0, back=0.14):
    ctx.save()
    ctx.rectangle(x, y, w, h); ctx.set_source_rgba(*color, back * alpha); ctx.fill()
    frac = clamp(frac)
    if segments:
        sw = w / segments
        n = int(frac * segments + 1e-6)
        for i in range(n):
            ctx.rectangle(x + i * sw + 1, y, sw - 2, h)
        ctx.set_source_rgba(*_hot(color, 0.25), alpha); ctx.fill()
    else:
        ctx.rectangle(x, y, w * frac, h)
        ctx.set_source_rgba(*_hot(color, 0.25), alpha); ctx.fill()
        # leading glow head
        ctx.rectangle(x + w * frac - 2, y - 2, 3, h + 4)
        ctx.set_source_rgba(1, 1, 1, alpha * 0.8 * (0 < frac < 1)); ctx.fill()
    ctx.restore()


def _scramble(s, reveal, seed, keep=" .:/-%()―…・"):
    """Type-on with random glyphs resolving left to right. reveal 0..1."""
    if reveal >= 1:
        return s
    r = random.Random(seed)
    n = len(s)
    glyphs = _JGLYPHS if any(ord(c) > 0x2FFF for c in s) else _GLYPHS
    out = []
    for i, ch in enumerate(s):
        p = reveal * (n + 3) - i
        if p >= 3 or ch in keep:
            out.append(ch if p > 0 else "")
        elif p > 0:
            out.append(r.choice(glyphs))
    return "".join(out)


def _corrupt(s, amount, r):
    if amount <= 0:
        return s
    out = []
    for ch in s:
        out.append(r.choice(_GLYPHS) if r.random() < amount * 0.45 else ch)
    return "".join(out)


def _group_begin(ctx):
    ctx.save()
    ctx.push_group()


def _group_end(ctx, alpha):
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(clamp(alpha))
    ctx.restore()


# ============================================================ utilities (public)
_SCAN_CACHE = {}


def draw_scanlines(ctx, alpha=0.1, spacing=3):
    """Full-frame CRT scanlines (dark lines every `spacing` px) plus a faint rolling band."""
    if alpha <= 0:
        return
    key = spacing
    if key not in _SCAN_CACHE:
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, 4, spacing)
        c = cairo.Context(s)
        c.rectangle(0, 0, 4, 1); c.set_source_rgba(0, 0, 0, 1); c.fill()
        pat = cairo.SurfacePattern(s); pat.set_extend(cairo.EXTEND_REPEAT)
        _SCAN_CACHE[key] = (s, pat)
    ctx.save()
    ctx.set_source(_SCAN_CACHE[key][1])
    ctx.paint_with_alpha(clamp(alpha * 2.2))
    ctx.restore()


def draw_brackets(ctx, x, y, w, h, t, color, *, alpha=1.0, size=26, width=2.0):
    """Animated corner brackets around (x, y, w, h). They fly in from outside over
    t 0..0.45 (ease-out-back), then breathe slightly."""
    k = ease_out_back(clamp(t / 0.45))
    a = alpha * clamp(t / 0.15)
    if a <= 0:
        return
    breathe = 3.0 * math.sin(t * 3.1)
    off = (1 - k) * 60 + breathe
    L = size * (0.4 + 0.6 * k)
    ctx.save()
    ctx.set_line_cap(cairo.LINE_CAP_SQUARE)
    corners = [(x - off, y - off, 1, 1), (x + w + off, y - off, -1, 1),
               (x - off, y + h + off, 1, -1), (x + w + off, y + h + off, -1, -1)]
    for pass_w, pass_a, col in ((width * 4, 0.12, color), (width, 1.0, _hot(color, 0.35))):
        ctx.new_path()
        for cx, cy, sx, sy in corners:
            ctx.move_to(cx, cy + sy * L); ctx.line_to(cx, cy); ctx.line_to(cx + sx * L, cy)
        ctx.set_line_width(pass_w); ctx.set_source_rgba(*col, a * pass_a); ctx.stroke()
    # tiny corner dots
    for cx, cy, sx, sy in corners:
        ctx.rectangle(cx + sx * 5 - 1.5, cy + sy * 5 - 1.5, 3, 3)
    ctx.set_source_rgba(*color, a * 0.9); ctx.fill()
    ctx.restore()


def _reticle(ctx, x, y, t, lockk, color, alpha=1.0):
    """Targeting reticle. lockk 0 (searching, large, spinning) .. 1 (locked, tight)."""
    ctx.save()
    ctx.translate(x, y)
    R = lerp(150, 62, ease_out_back(lockk))
    spin = t * lerp(2.4, 0.35, lockk)
    ctx.set_line_cap(cairo.LINE_CAP_BUTT)
    # outer dashed rotating ring
    for w_, a_ in ((6, 0.10), (1.4, 0.9)):
        ctx.save(); ctx.rotate(spin)
        ctx.set_dash([18, 10, 4, 10])
        ctx.arc(0, 0, R, 0, TAU)
        ctx.set_line_width(w_); ctx.set_source_rgba(*(_hot(color) if w_ < 3 else color), alpha * a_)
        ctx.stroke(); ctx.restore()
    # counter-rotating arc segments
    ctx.save(); ctx.rotate(-spin * 1.7)
    for i in range(3):
        a0 = i * TAU / 3
        ctx.arc(0, 0, R * 0.72, a0, a0 + 0.9)
        ctx.new_sub_path()
    ctx.set_line_width(3); ctx.set_source_rgba(*_hot(color, 0.3), alpha * 0.8); ctx.stroke()
    ctx.restore()
    # cross ticks
    for ang in range(4):
        ctx.save(); ctx.rotate(ang * TAU / 4)
        ctx.move_to(R + 6, 0); ctx.line_to(R + 26 + 20 * (1 - lockk), 0)
        ctx.move_to(R * 0.35, 0); ctx.line_to(R * 0.55, 0)
        ctx.set_line_width(1.6); ctx.set_source_rgba(*_hot(color, 0.3), alpha); ctx.stroke()
        ctx.restore()
    # inner diamond (appears on lock)
    d = 12 * lockk
    if d > 0.5:
        ctx.move_to(0, -d); ctx.line_to(d, 0); ctx.line_to(0, d); ctx.line_to(-d, 0); ctx.close_path()
        ctx.set_line_width(1.5); ctx.set_source_rgba(*_hot(color, 0.4), alpha * lockk); ctx.stroke()
    ctx.arc(0, 0, 2.2, 0, TAU); ctx.set_source_rgba(1, 1, 1, alpha); ctx.fill()
    # degree scale arc
    ctx.save(); ctx.rotate(spin * 0.3)
    for i in range(36):
        a0 = i * TAU / 36
        r0 = R + 34 + 20 * (1 - lockk)
        r1 = r0 + (8 if i % 9 == 0 else 3)
        ctx.move_to(math.cos(a0) * r0, math.sin(a0) * r0); ctx.line_to(math.cos(a0) * r1, math.sin(a0) * r1)
    ctx.set_line_width(1); ctx.set_source_rgba(*color, alpha * 0.45); ctx.stroke()
    ctx.restore()
    ctx.restore()


def _screen_frame(ctx, t, color, alpha, label_left="KEIBA-PREDICT v2.3", label_right=None):
    """Full-screen HUD chrome: corner marks, top ruler, bottom status line, timecode."""
    if alpha <= 0:
        return
    m = 36
    draw_brackets(ctx, m, m, W - 2 * m, H - 2 * m, t, color, alpha=alpha * 0.8, size=46, width=1.5)
    ctx.save()
    # top ruler
    ctx.set_line_width(1)
    ctx.set_source_rgba(*color, 0.35 * alpha)
    x0 = 640; x1 = W - 640
    for i, gx in enumerate(np.linspace(x0, x1, 61)):
        hh = 10 if i % 10 == 0 else 4
        ctx.move_to(gx + 0.5, m + 4); ctx.line_to(gx + 0.5, m + 4 + hh)
    ctx.stroke()
    # moving caret on ruler
    cx = lerp(x0, x1, 0.5 + 0.5 * math.sin(t * 0.9))
    ctx.move_to(cx, m + 20); ctx.line_to(cx - 5, m + 28); ctx.line_to(cx + 5, m + 28); ctx.close_path()
    ctx.set_source_rgba(*_hot(color), 0.8 * alpha); ctx.fill()
    ctx.restore()
    _txt(ctx, label_left, m + 18, m + 26, 15, color=color, alpha=0.8 * alpha, glow=0.3)
    tc = t + 0.0
    _txt(ctx, "T+%02d:%02d:%02d" % (int(tc) // 60, int(tc) % 60, int((tc % 1) * FPS)),
         W - m - 18, m + 26, 15, color=color, alpha=0.8 * alpha, align="right", glow=0.3)
    if label_right:
        _txt(ctx, label_right, W - m - 18, m + 46, 12, color=color, alpha=0.55 * alpha, align="right", glow=0)
    # blinking REC-like dot
    if int(t * 2) % 2 == 0:
        ctx.save(); ctx.arc(m + 8, m + 21, 3.2, 0, TAU); ctx.set_source_rgba(*PINK, alpha); ctx.fill(); ctx.restore()
    _txt(ctx, "NANKAN ROI MODEL  //  PLACKETT-LUCE PROB  //  BUY IF EV > 1.00  //  TAKEOUT 27.5%",
         m + 18, H - m - 14, 12, color=color, alpha=0.5 * alpha, glow=0)
    _txt(ctx, "SECTOR 大井 TCK  35.59N 139.74E", W - m - 18, H - m - 14, 12, font=FONT_SANS_M,
         color=color, alpha=0.5 * alpha, align="right", glow=0)


# ============================================================ BOOT (s01)
_ODDS_NAMES = ["SAKURA-BOLT", "TOKYO-NIGHT", "KAWASAKI-K", "FUNABASHI-7", "URAWA-STAR",
               "MIDNIGHT-RUN", "GOLD-GATE", "OI-FALCON", "RED-COMET", "BLUE-SPARK",
               "IRON-HOOF", "SILVER-RAIN", "SHINOBI", "HARUKAZE", "KUROGANE", "YOZAKURA"]

_FEATS = [("ability", "地力"), ("interval_fit", "出走間隔"), ("toughness", "タフネス"),
          ("tatakii", "叩き良化"), ("senkou", "先行力/脚質"), ("agari", "末脚"),
          ("baba_fit", "馬場適性"), ("jockey_change", "乗り替わり"), ("jockey_power", "騎手"),
          ("trainer", "厩舎仕上げ"), ("place_fit", "競馬場替わり"), ("distance_fit", "距離適性"),
          ("fatigue", "使い込み疲労")]
# ハルカゼ's (bad) feature vector as the model sees it
_HARU_FEATS = [-0.62, -0.35, 0.18, -0.48, -0.91, 0.72, -0.20, -0.30, -0.55, -0.12, 0.05, -0.08, -0.40]


def _odds_line(i):
    r = random.Random(i * 7919 + 13)
    place = r.choice(["OI", "OI", "KW", "FN", "UR"])
    num = r.randint(1, 16)
    name = _ODDS_NAMES[num - 1]
    odds = round(math.exp(r.uniform(0.3, 5.2)), 1)
    p = min(0.6, 1 / odds * r.uniform(0.55, 1.12))
    ev = p * odds
    return "%s%02dR #%02d %-12s %6.1f  p=%.3f EV %.2f" % (place, r.randint(1, 12), num, name, odds, p, ev), ev


def _data_stream(ctx, x, y, w, h, t, alpha, speed=34.0, size=13, seed=0):
    """Scrolling odds / EV table (clipped to box)."""
    ctx.save()
    ctx.rectangle(x, y, w, h); ctx.clip()
    lh = size * 1.45
    scroll = t * speed
    first = int(scroll / lh)
    for k in range(int(h / lh) + 2):
        i = first + k
        yy = y + h - (k * lh - (scroll % lh)) - 4
        s, ev = _odds_line(i + seed * 1000)
        fade = clamp((yy - y) / 80) * clamp((y + h - yy + 10) / 30)
        col = PINK if ev > 1.0 else CYAN
        _txt(ctx, s, x + 4, yy, size, color=col, alpha=alpha * fade * (0.95 if ev > 1 else 0.6), glow=0.25)
    ctx.restore()


def _hex_rain(ctx, x, y, w, h, t, alpha, cols=5, seed=3):
    r = random.Random(seed)
    ctx.save()
    ctx.rectangle(x, y, w, h); ctx.clip()
    for c in range(cols):
        sp = r.uniform(60, 180); off = r.uniform(0, h)
        cx = x + c * (w / cols)
        for j in range(18):
            yy = y + ((off + t * sp + j * 22) % (h + 40)) - 20
            hv = "%02X" % int(_h(c * 131 + j * 17 + int(t * 12)) * 255)
            a = alpha * (0.15 + 0.5 * (j == 17)) * (0.6 + 0.4 * _h(j + c))
            _txt(ctx, hv, cx, yy, 12, color=CYAN, alpha=a, glow=0)
    ctx.restore()


def _h(i):
    x = (int(i) * 2654435761) & 0xFFFFFFFF
    x ^= x >> 15
    return (x * 2246822519 & 0xFFFFFFFF) / 4294967296.0


def _feature_panel(ctx, x, y, t, alpha, color=CYAN):
    """Feature-vector bars (the repo's 13 特徴量) filling in."""
    w, h = 400, 470
    _panel_bg(ctx, x, y, w, h, color, alpha)
    _txt(ctx, "特徴量ベクトル", x + 18, y + 34, 19, font=FONT_SANS_M, color=color, alpha=alpha)
    _txt(ctx, "FEATURE VECTOR  dim=13", x + w - 16, y + 32, 11, color=color, alpha=0.6 * alpha, align="right", glow=0)
    _line(ctx, x + 16, y + 46, x + w - 16, y + 46, color, 0.5 * alpha, 1, glow=False)
    for i, ((en, jp), v) in enumerate(zip(_FEATS, _HARU_FEATS)):
        k = clamp((t - i * 0.06) / 0.35)
        if k <= 0:
            continue
        yy = y + 76 + i * 30
        _txt(ctx, _scramble(en, k * 1.6, i), x + 18, yy, 12, color=color, alpha=alpha * 0.9, glow=0.2)
        _txt(ctx, jp, x + 150, yy, 11, font=FONT_SANS_M, color=color, alpha=alpha * 0.55, glow=0)
        bx, bw = x + 250, 110
        mid = bx + bw / 2
        ctx.save()
        ctx.rectangle(bx, yy - 9, bw, 9); ctx.set_source_rgba(*color, 0.1 * alpha); ctx.fill()
        vv = v * ease_out_cubic(k) + 0.04 * math.sin(t * 9 + i) * (1 - clamp((t - 1.2) / 0.5))
        col = PINK if vv < -0.5 else color
        ctx.rectangle(min(mid, mid + vv * bw / 2), yy - 9, abs(vv) * bw / 2, 9)
        ctx.set_source_rgba(*_hot(col, 0.2), alpha * 0.9); ctx.fill()
        ctx.rectangle(mid - 0.5, yy - 12, 1, 15); ctx.set_source_rgba(1, 1, 1, alpha * 0.5); ctx.fill()
        ctx.restore()
        _txt(ctx, "%+.2f" % vv, x + w - 14, yy, 11, color=col, alpha=alpha * 0.8, align="right", glow=0)


def _logo(ctx, t, cx, cy, scale, alpha, dock=0.0):
    """KEIBA-PREDICT logo. t local to boot start (0 = 0.3s)."""
    if alpha <= 0:
        return
    ctx.save()
    ctx.translate(cx, cy); ctx.scale(scale, scale)
    title = "KEIBA-PREDICT"
    rev = clamp(t / 0.55)
    s = _scramble(title, rev, int(t * FPS))
    # emblem: hexagon + horse-shoe arc
    k = ease_out_cubic(clamp(t / 0.5))
    ctx.save(); ctx.translate(-395, -22); ctx.rotate((1 - k) * 2.0)
    ctx.new_path()
    for i in range(6):
        a = i * TAU / 6 + TAU / 12
        ctx.line_to(math.cos(a) * 40 * k, math.sin(a) * 40 * k)
    ctx.close_path()
    ctx.set_line_width(2.2); ctx.set_source_rgba(*_hot(CYAN), alpha); ctx.stroke()
    ctx.arc(0, 2, 20 * k, math.radians(150), math.radians(390))
    ctx.set_line_width(5); ctx.set_source_rgba(*CYAN, alpha * 0.9); ctx.stroke()
    ctx.restore()
    _txt(ctx, s, -335, 0, 76, font=FONT_SANS, color=CYAN, alpha=alpha, glow=1.0, spacing=6)
    _txt(ctx, "v2.3", 402, -40, 22, color=PINK, alpha=alpha * clamp((t - 0.4) / 0.2), glow=0.8, bold=True)
    # underline wipe
    lk = ease_out_cubic(clamp((t - 0.25) / 0.5))
    _line(ctx, -335, 22, -335 + 740 * lk, 22, CYAN, alpha, 1.5)
    ctx.rectangle(-335 + 740 * lk - 30, 20, 30, 4); ctx.set_source_rgba(1, 1, 1, alpha * (lk < 1)); ctx.fill()
    sub = "南関競馬 回収率特化モデル"
    sk = clamp((t - 0.45) / 0.45)
    _txt(ctx, _scramble(sub, sk, 99 + int(t * 12)), -335, 64, 30, font=FONT_SANS_M, color=WHITE,
         alpha=alpha * clamp(sk * 3), glow=0.4, spacing=4)
    _txt(ctx, "NANKAN KEIBA  /  ROI-OPTIMIZED  /  3-RENTAN · 3-RENPUKU", -333, 96, 13, color=CYAN,
         alpha=alpha * 0.6 * clamp(sk * 2) * (1 - dock), glow=0, spacing=1)
    ctx.restore()


_MODULES = [("scraping", "データ収集 netkeiba/地方"), ("features", "特徴量 13 dims"),
            ("probability", "Plackett-Luce 確率変換"), ("betting", "期待値判定 EV>1.00"),
            ("backtest", "回収率検証 no-leak")]


def _loading(ctx, t, x, y, alpha):
    for i, (mod, jp) in enumerate(_MODULES):
        t0 = 0.32 + i * 0.08
        k = clamp((t - t0) / 0.34)
        if t < t0:
            continue
        yy = y + i * 30
        a = alpha * clamp((t - t0) / 0.1)
        _txt(ctx, "> load core.%-11s" % mod, x, yy, 14, color=CYAN, alpha=a * 0.9, glow=0.2)
        _txt(ctx, jp, x + 250, yy, 13, font=FONT_SANS_M, color=WHITE, alpha=a * 0.6, glow=0)
        _bar(ctx, x + 470, yy - 10, 200, 8, ease_in_out(k), CYAN, a, segments=20)
        _txt(ctx, "OK" if k >= 1 else "%3d%%" % int(k * 100), x + 740, yy, 14,
             color=(CYAN if k >= 1 else WHITE), alpha=a, align="right", glow=0.4, bold=k >= 1)


def draw_boot(ctx, t, *, target=None, alpha=1.0):
    """s01 boot sequence. t = seconds since shot start (0..6)."""
    if alpha <= 0 or t < 0.3:
        return
    _group_begin(ctx)
    tb = t - 0.3                                   # boot-local time
    on = clamp(tb / 0.12)
    # --- boot flash: horizontal line opening like a CRT
    if tb < 0.25:
        k = ease_out_cubic(tb / 0.25)
        ctx.save()
        ctx.rectangle(W / 2 - W / 2 * k, H / 2 - 1.5, W * k, 3)
        ctx.set_source_rgba(*_hot(CYAN), 0.9 * (1 - tb / 0.25) + 0.1); ctx.fill()
        ctx.restore()
    # dark veil for readability
    veil = 0.35 * on * (1 - 0.35 * smoothstep(2.7, 4.0, tb))
    ctx.save(); ctx.set_source_rgba(0, 0.015, 0.03, veil); ctx.paint(); ctx.restore()

    _screen_frame(ctx, tb, CYAN, on * 0.9, label_right="MODEL nankeiba.core  |  WEIGHTS learn.py 2026-09")

    # --- logo: centre 0..1.25, then docks top-left 1.25..1.7
    dock = ease_in_out(clamp((tb - 0.95) / 0.45))
    lcx = lerp(W / 2 - 30, 380, dock)
    lcy = lerp(H / 2 - 40, 118, dock)
    lsc = lerp(1.0, 0.42, dock)
    _logo(ctx, tb, lcx, lcy, lsc, on, dock)
    # loading list under the logo (fades as it docks)
    la = 1 - clamp((tb - 0.95) / 0.2)
    if la > 0:
        _loading(ctx, tb, W / 2 - 400, H / 2 + 90, la)

    # --- data phase (global-ish 1.2 - 3.0, persists dimmed)
    td = t - 1.2
    if td > 0:
        da = clamp(td / 0.3) * lerp(1.0, 0.28, smoothstep(2.8, 3.6, t))
        # left odds stream
        lx, ly, lw, lh = 70, 200, 560, 560
        _panel_bg(ctx, lx, ly, lw, lh, CYAN, da * 0.9, fill=0.45)
        _txt(ctx, "ODDS STREAM", lx + 18, ly + 30, 16, color=CYAN, alpha=da, bold=True)
        _txt(ctx, "リアルタイムオッズ / 期待値", lx + 170, ly + 30, 14, font=FONT_SANS_M, color=WHITE, alpha=da * 0.7, glow=0)
        _txt(ctx, "%05d pkts" % int(td * 4130), lx + lw - 16, ly + 30, 12, color=CYAN, alpha=da * 0.6, align="right", glow=0)
        _line(ctx, lx + 16, ly + 44, lx + lw - 16, ly + 44, CYAN, 0.5 * da, 1, glow=False)
        _data_stream(ctx, lx + 10, ly + 52, lw - 20, lh - 64, td, da, speed=46 + 30 * clamp(td), size=13)
        draw_brackets(ctx, lx, ly, lw, lh, td, CYAN, alpha=da * 0.8, size=18)
        # right feature panel
        fx, fy = W - 70 - 400, 200
        _feature_panel(ctx, fx, fy, td, da)
        draw_brackets(ctx, fx, fy, 400, 470, td - 0.1, CYAN, alpha=da * 0.8, size=18)
        # hex rain strips at far edges
        _hex_rain(ctx, 70, 780, 560, 150, t, da * 0.8)
        # throughput mini bars under feature panel
        for i in range(24):
            hh = 8 + 50 * fbm(t * 3 + i * 0.37)
            ctx.rectangle(fx + i * 16.5, fy + 560 - hh, 11, hh)
        ctx.set_source_rgba(*CYAN, 0.35 * da); ctx.fill()
        _txt(ctx, "INFERENCE LOAD", fx, fy + 582, 11, color=CYAN, alpha=da * 0.6, glow=0)
        _txt(ctx, "%.1f TFLOPS" % (3.2 + 2 * fbm(t * 2)), fx + 400, fy + 582, 11, color=CYAN,
             alpha=da * 0.6, align="right", glow=0)

    # --- target lock (2.5 - 6)
    if t >= 2.5:
        _target_phase(ctx, t, target)

    draw_scanlines(ctx, 0.06 * on)
    _group_end(ctx, alpha)


def fbm(x):
    return 0.6 * noise1(x, 3) + 0.4 * noise1(x * 2.3, 7)


def _target_phase(ctx, t, target):
    tl = t - 2.5
    lock_t = 3.0
    k_fly = ease_out_cubic(clamp(tl / 0.5))
    locked = t >= lock_t
    lockk = smoothstep(lock_t - 0.12, lock_t + 0.25, t)
    reject = t >= 5.0
    col = mix_color(CYAN, PINK, smoothstep(5.0, 5.25, t))

    # panel placement
    if target is not None:
        tx, ty = target
        sx, sy = W / 2, H / 2
        rx = lerp(sx, tx, k_fly) + (1 - lockk) * 26 * math.sin(t * 13)
        ry = lerp(sy, ty, k_fly) + (1 - lockk) * 18 * math.cos(t * 11)
        # ensure the panel sits beside the target on the roomier side
        pw, ph = 560, 440
        if tx > W / 2:
            px = tx - 150 - pw
        else:
            px = tx + 150
        px = clamp(px, 70, W - 70 - pw)
        py = clamp(ty - ph / 2, 110, H - 200 - ph)
    else:
        pw, ph = 560, 440
        px, py = (630 + 1450) / 2 - pw / 2, H / 2 - ph / 2 - 30
    pa = clamp((t - 2.55) / 0.2)

    if target is not None:
        ra = clamp(tl / 0.15)
        _reticle(ctx, rx, ry, t, lockk, col, ra)
        # leader line reticle -> panel
        if lockk > 0.3:
            ex = px + pw if tx > px + pw else px
            ey = py + 60
            lk = ease_out_cubic(clamp((t - lock_t) / 0.3))
            mx_, my_ = lerp(rx, ex, 0.55), ry
            ctx.save()
            ctx.move_to(rx + (70 if ex > rx else -70), ry)
            ctx.line_to(lerp(rx, mx_, lk), lerp(ry, my_, lk))
            if lk >= 1:
                ctx.line_to(ex, ey)
            ctx.set_line_width(1.2); ctx.set_source_rgba(*_hot(col, 0.3), 0.8); ctx.stroke()
            ctx.restore()
        # lock flash text
        if locked and t < 3.9:
            fl = 1 if int((t - lock_t) * 10) % 2 == 0 or t > 3.4 else 0.2
            _txt(ctx, "TARGET LOCKED", rx, ry - 100, 18, color=col, alpha=fl * (1 - clamp((t - 3.6) / 0.3)),
                 align="center", bold=True, glow=0.9, spacing=3)
            if t - lock_t < 0.2:
                ctx.save(); ctx.arc(rx, ry, 70 + 400 * (t - lock_t), 0, TAU)
                ctx.set_line_width(2); ctx.set_source_rgba(*_hot(col), 1 - (t - lock_t) / 0.2); ctx.stroke(); ctx.restore()
        _txt(ctx, "#14", rx + 58, ry + 72, 16, color=col, alpha=ra * 0.9, bold=True)
        _txt(ctx, "X%04d Y%04d" % (int(rx), int(ry)), rx + 58, ry + 90, 11, color=col, alpha=ra * 0.6, glow=0)

    if pa <= 0:
        return
    # panel opens vertically
    ok = ease_out_cubic(clamp((t - 2.55) / 0.3))
    ctx.save()
    ctx.rectangle(px - 20, py + ph / 2 - ph / 2 * ok - 20, pw + 40, ph * ok + 40); ctx.clip()
    _panel_bg(ctx, px, py, pw, ph, col, pa, fill=0.62)
    # header strip
    ctx.rectangle(px + 1, py + 1, pw - 2, 40); ctx.set_source_rgba(*col, 0.14 * pa); ctx.fill()
    _txt(ctx, "TARGET ANALYSIS", px + 20, py + 28, 15, color=col, alpha=pa, bold=True, spacing=2)
    _txt(ctx, "対象馬 解析", px + 220, py + 28, 14, font=FONT_SANS_M, color=WHITE, alpha=pa * 0.7, glow=0)
    _txt(ctx, "ID 2026-OI-11-14", px + pw - 18, py + 27, 11, color=col, alpha=pa * 0.6, align="right", glow=0)

    # line 1: race
    k1 = clamp((t - 2.7) / 0.3)
    _txt(ctx, _scramble("大井 第11R  ダ1600m", k1, 11 + int(t * 20)), px + 22, py + 80, 24,
         font=FONT_SANS_M, color=WHITE, alpha=pa * clamp(k1 * 4), glow=0.35)
    _txt(ctx, "TCK / DIRT / 良 / NIGHT", px + pw - 20, py + 80, 12, font=FONT_SANS_M, color=col, alpha=pa * 0.6 * k1, align="right", glow=0)
    # line 2: horse
    k2 = clamp((t - 2.9) / 0.3)
    if k2 > 0:
        ctx.save()
        ctx.rectangle(px + 22, py + 102, 58, 52); ctx.set_source_rgba(*col, 0.85 * pa * clamp(k2 * 3)); ctx.fill()
        ctx.restore()
        _txt(ctx, "14", px + 51, py + 142, 38, font=FONT_SANS, color=DARK, alpha=pa * clamp(k2 * 3), align="center", glow=0, hot=False)
        _txt(ctx, _scramble("ハルカゼ", k2, 21 + int(t * 20)), px + 96, py + 144, 44, font=FONT_SANS,
             color=WHITE, alpha=pa * clamp(k2 * 3), glow=0.5, spacing=4)
        _txt(ctx, "HARUKAZE  栗毛 牝4  脚質: 追込", px + 98, py + 170, 13, font=FONT_SANS_M, color=col,
             alpha=pa * 0.7 * k2, glow=0)
    _line(ctx, px + 20, py + 190, px + pw - 20, py + 190, col, 0.4 * pa, 1, glow=False)

    # line 3: win probability, rolls down and settles at 3.3
    k3 = clamp((t - 3.0) / 0.1)
    if k3 > 0:
        _txt(ctx, "勝率", px + 22, py + 232, 20, font=FONT_SANS_M, color=WHITE, alpha=pa * 0.85, glow=0.2)
        _txt(ctx, "WIN PROB", px + 22, py + 252, 11, color=col, alpha=pa * 0.6, glow=0)
        if t < 3.3:
            r = random.Random(int(t * FPS * 2))
            v = lerp(r.uniform(1.0, 9.9), 0.8, smoothstep(3.0, 3.3, t) ** 0.5)
            numc = WHITE
        else:
            v = 0.8
            numc = PINK if reject else col
        pop = 1 + 0.18 * (1 - clamp((t - 3.3) / 0.25)) * (t >= 3.3)
        ctx.save(); ctx.translate(px + 110, py + 262); ctx.scale(pop, pop)
        ww = _txt(ctx, "%.1f" % v, 0, 0, 78, color=numc, alpha=pa, glow=1.0, bold=True)
        _txt(ctx, "%", ww + 6, 0, 36, color=numc, alpha=pa, glow=0.8, bold=True)
        ctx.restore()
        # probability gauge (log-ish)
        gx, gy, gw = px + 330, py + 222, 200
        _txt(ctx, "RANK 14/14", gx, gy - 8, 11, color=col, alpha=pa * 0.7, glow=0)
        _bar(ctx, gx, gy, gw, 8, clamp(v / 25), PINK if t >= 3.3 else col, pa, segments=25)
        _txt(ctx, "市場 1.1%  /  model 0.8%", gx, gy + 30, 11, font=FONT_SANS_M, color=WHITE,
             alpha=pa * 0.55 * clamp((t - 3.4) / 0.3), glow=0)

    # line 4: expected value
    k4 = clamp((t - 3.9) / 0.3)
    if k4 > 0:
        _txt(ctx, "期待値", px + 330, py + 298, 16, font=FONT_SANS_M, color=WHITE, alpha=pa * 0.85 * k4, glow=0.2)
        _txt(ctx, "EV", px + 390, py + 298, 11, color=col, alpha=pa * 0.6 * k4, glow=0)
        ev = 0.41 * ease_out_cubic(k4) if k4 < 1 else 0.41
        _txt(ctx, "%.2f" % ev, px + pw - 22, py + 300, 30, color=PINK, alpha=pa * k4, align="right", bold=True, glow=0.8)
        # EV bar with threshold marker
        bx, by, bw = px + 330, py + 312, 200
        _bar(ctx, bx, by, bw, 6, ev / 1.6, PINK, pa * k4)
        th = bx + bw / 1.6
        ctx.save(); ctx.rectangle(th - 0.5, by - 6, 1.5, 18); ctx.set_source_rgba(1, 1, 1, pa * k4); ctx.fill(); ctx.restore()
        _txt(ctx, "1.00", th, by + 26, 10, color=WHITE, alpha=pa * 0.6 * k4, align="center", glow=0)
    # small spec lines
    k5 = clamp((t - 4.2) / 0.4)
    if k5 > 0:
        specs = ["odds 122.0  (単勝 14人気)", "馬場適性 C-  /  距離適性 B", "特徴量 13 dims  score −1.84 SD"]
        for i, s in enumerate(specs):
            kk = clamp((t - 4.2 - i * 0.12) / 0.3)
            _txt(ctx, _scramble(s, kk, i + 70), px + 22, py + 300 + i * 21, 13, font=FONT_SANS_M,
                 color=col, alpha=pa * 0.75 * clamp(kk * 3), glow=0)
    # recommendation stamp at 5.0
    if t >= 4.85:
        k6 = clamp((t - 4.85) / 0.15)
        _line(ctx, px + 20, py + 368, px + pw - 20, py + 368, col, 0.4 * pa, 1, glow=False)
        _txt(ctx, "推奨:", px + 22, py + 416, 22, font=FONT_SANS_M, color=WHITE, alpha=pa * k6, glow=0.2)
        if t >= 5.0:
            ks = ease_out_back(clamp((t - 5.0) / 0.22))
            fl = 0.55 + 0.45 * (int((t - 5.0) * 8) % 2 == 0 or t > 5.5)
            ctx.save()
            bx, by, bw, bh = px + 100, py + 384, 160, 44
            ctx.translate(bx + bw / 2, by + bh / 2); sc = lerp(1.8, 1.0, ks); ctx.scale(sc, sc)
            ctx.rectangle(-bw / 2, -bh / 2, bw, bh)
            ctx.set_source_rgba(*PINK, 0.25 * pa * fl); ctx.fill_preserve()
            ctx.set_line_width(2); ctx.set_source_rgba(*_hot(PINK, 0.3), pa * fl); ctx.stroke()
            _txt(ctx, "見送り", 0, 14, 34, font=FONT_SANS, color=PINK, alpha=pa * fl, align="center", glow=1.0, spacing=4)
            ctx.restore()
            _txt(ctx, "PASS  //  NO BET  EV < 1.00", px + pw - 22, py + 414, 13, color=PINK,
                 alpha=pa * clamp((t - 5.15) / 0.2), align="right", bold=True, glow=0.6)
    ctx.restore()
    draw_brackets(ctx, px, py, pw, ph, t - 2.55, col, alpha=pa, size=22)


# ============================================================ probability curve
_KEYS = [(33.0, 3.0), (34.4, 5.0), (35.8, 12.0), (37.2, 27.0), (38.6, 52.0), (40.0, 78.0)]


def _pchip(xs, ys, x):
    """Monotone cubic (Fritsch-Carlson) interpolation for a short key list."""
    n = len(xs)
    d = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
    m = [d[0]] + [0.0] * (n - 2) + [d[-1]]
    for i in range(1, n - 1):
        m[i] = 0.0 if d[i - 1] * d[i] <= 0 else 2 / (1 / d[i - 1] + 1 / d[i])
    for i in range(n - 1):
        if xs[i] <= x <= xs[i + 1]:
            h = xs[i + 1] - xs[i]; s = (x - xs[i]) / h
            h00 = 2 * s ** 3 - 3 * s ** 2 + 1; h10 = s ** 3 - 2 * s ** 2 + s
            h01 = -2 * s ** 3 + 3 * s ** 2; h11 = s ** 3 - s ** 2
            return h00 * ys[i] + h10 * h * m[i] + h01 * ys[i + 1] + h11 * h * m[i + 1]
    return ys[-1]


def prob_curve(gt):
    """Canonical ハルカゼ win probability (percent) at GLOBAL time gt.
    Returns float, or the strings "ERROR" (41.4 <= gt < 42.2) / "計算不能" (gt >= 42.2)."""
    if gt < 29.6:
        return 0.8
    if gt < 33.0:
        k = (gt - 29.6) / 3.4
        return 0.8 + 2.2 * (k ** 1.8)
    if gt < 40.0:
        jit = 0.25 * (noise1(gt * 9, 5) - 0.5) * (gt - 33) / 7
        return _pchip([k for k, _ in _KEYS], [v for _, v in _KEYS], gt) * (1 + jit * 0.2)
    if gt < 41.4:
        k = (gt - 40.0) / 1.4                 # 0..1 chaos
        base = 78 + 25 * k + 30 * k * k      # climbs through 100
        f = int(gt * FPS)
        r = random.Random(f * 31 + 7)
        amp = 2 + 160 * k ** 2
        v = base + r.uniform(-1, 1) * amp
        if k > 0.55 and r.random() < k * 0.5:
            v = r.choice([-1, 1]) * r.uniform(100, 999.9)   # overflow spikes
        return round(v, 1)
    if gt < 42.2:
        return "ERROR"
    return "計算不能"


def history_at(gt, n=40, dt=0.12):
    """Last n samples of prob_curve up to gt (oldest first). Non-numeric -> None."""
    out = []
    for i in range(n - 1, -1, -1):
        v = prob_curve(gt - i * dt)
        out.append(v if isinstance(v, (int, float)) else None)
    return out


def glitch_curve(gt):
    """Suggested glitch amount for the probability panel / frame over GLOBAL time."""
    if gt < 39.6:
        return 0.0
    if gt < 41.4:
        return 0.55 * smoothstep(39.6, 41.4, gt) ** 2
    return 0.35 + 0.65 * math.exp(-(gt - 41.4) * 2.2)


# ============================================================ probability panel (s04/s05)
def _sparkline(ctx, x, y, w, h, history, color, alpha):
    ctx.save()
    ctx.rectangle(x, y, w, h); ctx.set_source_rgba(*color, 0.06 * alpha); ctx.fill()
    # grid
    ctx.set_line_width(1); ctx.set_source_rgba(*color, 0.12 * alpha)
    for i in range(1, 4):
        ctx.move_to(x, y + h * i / 4 + 0.5); ctx.line_to(x + w, y + h * i / 4 + 0.5)
    ctx.stroke()
    vals = [v for v in history if v is not None]
    if len(vals) >= 2:
        top = max(10.0, max(min(v, 110) for v in vals) * 1.1)
        n = len(history)
        pts = []
        for i, v in enumerate(history):
            if v is None:
                continue
            vv = max(-5, min(v, 115))
            pts.append((x + w * i / (n - 1), y + h - h * clamp(vv / top, -0.05, 1.05)))
        # filled area
        ctx.move_to(pts[0][0], y + h)
        for p in pts:
            ctx.line_to(*p)
        ctx.line_to(pts[-1][0], y + h); ctx.close_path()
        g = cairo.LinearGradient(0, y, 0, y + h)
        g.add_color_stop_rgba(0, *color, 0.35 * alpha); g.add_color_stop_rgba(1, *color, 0.0)
        ctx.set_source(g); ctx.fill()
        ctx.new_path()
        for p in pts:
            ctx.line_to(*p)
        ctx.set_line_width(5); ctx.set_source_rgba(*color, 0.15 * alpha); ctx.stroke_preserve()
        ctx.set_line_width(1.6); ctx.set_source_rgba(*_hot(color, 0.3), alpha); ctx.stroke()
        ctx.arc(pts[-1][0], pts[-1][1], 3, 0, TAU); ctx.set_source_rgba(1, 1, 1, alpha); ctx.fill()
    ctx.restore()


def draw_prob_panel(ctx, t, prob, *, x=1480, y=90, alpha=1.0, glitch=0.0, label="ハルカゼ 勝率",
                    history=None):
    """Compact live win-probability readout, box 380x250 with top-left at (x, y)."""
    if alpha <= 0:
        return
    pw, ph = 380, 250
    numeric = isinstance(prob, (int, float))
    g = clamp(glitch)
    fi = int(t * FPS)
    r = random.Random(fi * 977 + 1)
    if numeric:
        heat = smoothstep(3.0, 35.0, prob)
        col = mix_color(CYAN, PINK, heat)
        if prob > 70 and int(t * 6) % 2 == 0:
            col = mix_color(col, WHITE, 0.25)
    else:
        heat = 1.0
        col = PINK
    # ---------- content rendered into a group so glitch can slice / split it
    ctx.save()
    ctx.push_group()
    _panel_bg(ctx, x, y, pw, ph, col, 1.0, fill=0.6)
    ctx.rectangle(x + 1, y + 1, pw - 2, 34); ctx.set_source_rgba(*col, 0.13); ctx.fill()
    lab = _corrupt(label, g * 0.6, r)
    _txt(ctx, lab, x + 16, y + 25, 18, font=FONT_SANS_M, color=WHITE, alpha=0.95, glow=0.25)
    _txt(ctx, _corrupt("WIN PROB // LIVE", g, r), x + pw - 14, y + 24, 11, color=col, alpha=0.75,
         align="right", glow=0)
    # live dot
    if int(t * 3) % 2 == 0:
        ctx.arc(x + pw - 136, y + 20, 3.5, 0, TAU); ctx.set_source_rgba(*PINK, 1); ctx.fill()

    # big number
    if numeric:
        if prob >= 100 or prob < 0:
            s = "%.1f" % prob
        elif prob >= 10:
            s = "%.1f" % prob
        else:
            s = "%.1f" % prob
        s = _corrupt(s, g, r)
        size = 84 if len(s) <= 4 else 70
        ww = _txt(ctx, s, x + 18, y + 125, size, color=col, alpha=1, glow=1.0, bold=True)
        _txt(ctx, "%", x + 24 + ww, y + 125, size * 0.42, color=col, alpha=1, glow=0.8, bold=True)
        # delta
        dv = None
        if history:
            prev = [v for v in history[-6:-1] if v is not None]
            if prev:
                dv = prob - prev[0]
        if dv is not None and abs(dv) > 0.05:
            arrow = "▲" if dv > 0 else "▼"
            _txt(ctx, "%s %+.1f" % (arrow, dv), x + pw - 16, y + 80, 16, font=FONT_SANS_M,
                 color=PINK if dv > 0 else col, alpha=0.95, align="right", glow=0.6)
        status = "NOMINAL" if prob < 5 else "ANOMALY" if prob < 50 else "CRITICAL" if prob <= 100 else "OVERFLOW"
        _txt(ctx, _corrupt(status, g, r), x + pw - 16, y + 104, 12, color=col, alpha=0.85, align="right",
             bold=True, glow=0.4)
        # level bar
        _bar(ctx, x + 18, y + 142, pw - 36, 6, clamp(prob / 100), col, 1.0, segments=38)
    else:
        big = str(prob)
        if r.random() < 0.3 + 0.4 * g:
            big = _corrupt(big, 0.8, r)
        jp = any(ord(ch) > 0x3000 for ch in big)
        _txt(ctx, big, x + pw / 2, y + 122, 62 if jp else 74, font=FONT_SANS if jp else MONO,
             color=PINK, alpha=1, align="center", glow=1.2, bold=True, spacing=4 if jp else 2)
        _txt(ctx, "0x%08X  STACK OVERFLOW" % r.getrandbits(32), x + pw / 2, y + 146, 11, color=PINK,
             alpha=0.8, align="center", glow=0)
    # sparkline
    hist = history if history else ([prob] * 2 if numeric else [])
    _sparkline(ctx, x + 18, y + 162, pw - 36, 58, hist, col, 1.0)
    _txt(ctx, "t-%.1fs" % (len(hist) * 0.12), x + 18, y + 238, 10, color=col, alpha=0.6, glow=0)
    _txt(ctx, "PL-MODEL v2.3  σ=%.2f" % (0.12 + heat * 2.4 + g * r.random() * 9), x + pw - 18, y + 238, 10,
         color=col, alpha=0.6, align="right", glow=0)
    pat = ctx.pop_group()
    ctx.restore()

    # ---------- composite with glitch
    ctx.save()
    if g <= 0.01:
        ctx.set_source(pat); ctx.paint_with_alpha(alpha)
    else:
        split = 2 + 14 * g * (0.4 + r.random())
        # chromatic ghosts (masking the content with pure colours)
        for (cr, cg, cb), dx in (((1, 0.1, 0.35), -split), ((0.1, 0.9, 1), split)):
            ctx.save(); ctx.translate(dx, r.uniform(-2, 2) * g)
            ctx.set_source_rgba(cr, cg, cb, 0.55 * alpha)
            ctx.mask(pat); ctx.restore()
        # horizontal slices with offsets
        yy = y - 10
        while yy < y + ph + 10:
            sh = r.uniform(6, 40)
            off = 0 if r.random() > 0.35 + 0.5 * g else r.gauss(0, 30 * g)
            ctx.save()
            ctx.rectangle(x - 80, yy, pw + 160, sh); ctx.clip()
            ctx.translate(off, 0)
            ctx.set_source(pat)
            ctx.paint_with_alpha(alpha * (0.35 if r.random() < 0.15 * g else 1.0))
            ctx.restore()
            yy += sh
        # noise bars
        for i in range(int(2 + 8 * g)):
            ctx.rectangle(x + r.uniform(-40, pw), y + r.uniform(0, ph), r.uniform(20, 180 * g + 20), r.uniform(1, 4))
            ctx.set_source_rgba(*(PINK if r.random() < 0.5 else WHITE), alpha * r.uniform(0.3, 0.9))
            ctx.fill()
        # ERR flashes
        if r.random() < g * 0.8:
            ex, ey = x + r.uniform(20, pw - 140), y + r.uniform(40, ph - 20)
            ctx.rectangle(ex - 6, ey - 20, 118, 28); ctx.set_source_rgba(*PINK, 0.85 * alpha); ctx.fill()
            _txt(ctx, r.choice(["ERR", "ERR 0x3F", "NaN", "OVERFLOW", "ERR!!"]), ex, ey, 20, color=DARK,
                 alpha=alpha, glow=0, bold=True)
    ctx.restore()
    draw_brackets(ctx, x - 6, y - 6, pw + 12, ph + 12, 1.0 + t, col, alpha=alpha * 0.9, size=16, width=1.6)


# ============================================================ full-frame glitch
def glitch_frame(target, amount, seed=0):
    """Digital glitch applied IN PLACE to a cairo ImageSurface (or ctx's target surface).
    amount 0..1. Block displacement, RGB channel offset, scanline tear, colour quantize,
    noise lines. Alpha channel preserved."""
    if amount <= 0:
        return
    surf = target.get_target() if isinstance(target, cairo.Context) else target
    surf.flush()
    w, h, stride = surf.get_width(), surf.get_height(), surf.get_stride()
    buf = np.ndarray((h, stride // 4, 4), np.uint8, surf.get_data())[:, :w]
    r = np.random.default_rng(seed & 0xFFFFFFFF)
    a = float(clamp(amount))

    # 1) RGB channel offset (BGRA order: 2 = R, 0 = B)
    k = int(2 + 22 * a * r.uniform(0.6, 1.2))
    ky = int(r.integers(-2, 3) * a)
    buf[:, k:, 2] = buf[:, :-k, 2]
    buf[:, :-k, 0] = buf[:, k:, 0]
    if ky:
        buf[:, :, 2] = np.roll(buf[:, :, 2], ky, axis=0)

    # 2) horizontal band displacement
    for _ in range(int(3 + 16 * a)):
        y0 = int(r.integers(0, h)); bh = int(r.integers(3, 12 + 110 * a))
        dx = int(r.normal(0, 25 + 160 * a))
        if dx:
            band = buf[y0:y0 + bh]
            band[:] = np.roll(band, dx, axis=1)

    # 3) block copies (macroblock smear)
    for _ in range(int(2 + 14 * a)):
        bw = int(r.integers(40, 80 + 420 * a)); bh = int(r.integers(8, 20 + 120 * a))
        sx = int(r.integers(0, max(1, w - bw))); sy = int(r.integers(0, max(1, h - bh)))
        dx = int(np.clip(sx + r.normal(0, 200 * a), 0, w - bw)); dy = int(np.clip(sy + r.normal(0, 30), 0, h - bh))
        buf[dy:dy + bh, dx:dx + bw] = buf[sy:sy + bh, sx:sx + bw].copy()

    # 4) scanline tear (sine-sheared region)
    if r.random() < 0.4 + 0.6 * a:
        th = int(30 + 260 * a); y0 = int(r.integers(0, max(1, h - th)))
        rows = np.arange(th)
        off = (np.sin(rows / r.uniform(6, 30) + r.uniform(0, 6.28)) * (10 + 70 * a)
               + (rows > th * 0.6) * r.normal(0, 60 * a)).astype(np.int64)
        v32 = buf.view(np.uint32)[..., 0] if buf.shape[2] == 4 else None
        for i in range(min(th, h - y0)):
            o = int(off[i])
            if o:
                row = v32[y0 + i]
                row[:] = np.roll(row, o)

    # 5) colour quantize / tint blocks
    for _ in range(int(1 + 6 * a)):
        bw = int(r.integers(60, 200 + 600 * a)); bh = int(r.integers(10, 40 + 160 * a))
        x0 = int(r.integers(0, max(1, w - bw))); y0 = int(r.integers(0, max(1, h - bh)))
        blk = buf[y0:y0 + bh, x0:x0 + bw, :3]
        mode = r.random()
        if mode < 0.35:
            blk &= np.uint8(0xE0)                        # posterize
        elif mode < 0.6:
            blk[:] = blk[..., ::-1]                      # R<->B swap: violet / orange shift
        elif mode < 0.8:                                 # pink wash
            blk[:] = (blk >> 1) + np.array([70, 38, 127], np.uint8)
        else:                                            # cyan wash
            blk[:] = (blk >> 1) + np.array([127, 120, 30], np.uint8)

    # 6) noise lines
    for _ in range(int(2 + 10 * a)):
        y0 = int(r.integers(0, h)); lh = int(r.integers(1, 3))
        x0 = int(r.integers(0, w)); lw = int(r.integers(100, w))
        buf[y0:y0 + lh, x0:x0 + lw, :3] = r.integers(150, 256, size=(1, 1, 3), dtype=np.uint8)
    surf.mark_dirty()


# ============================================================ update panel (s07)
def draw_update_panel(ctx, t, *, alpha=1.0, cx=1440, cy=300):
    """s07 model-update panel. t = 0 at global 50.0; L12 is spoken at t 1.0-4.6.
    Panel is 640x380 centred on (cx, cy). Colour drifts cyan -> warm gold (t 2.4-4.6)."""
    if alpha <= 0 or t < 0:
        return
    pw, ph = 640, 420
    px, py = cx - pw / 2, cy - ph / 2
    warm = smoothstep(2.4, 4.6, t)
    col = mix_color(CYAN, GOLD, warm)
    open_k = ease_out_cubic(clamp((t - 0.2) / 0.5))
    pa = clamp((t - 0.2) / 0.3)
    _group_begin(ctx)
    # soft glow behind panel
    g = cairo.RadialGradient(cx, cy, 20, cx, cy, pw * 0.75)
    g.add_color_stop_rgba(0, *col, 0.10 * pa); g.add_color_stop_rgba(1, *col, 0)
    ctx.set_source(g); ctx.paint()

    ctx.save()
    ctx.rectangle(px - 30, cy - ph / 2 * open_k - 30, pw + 60, ph * open_k + 60); ctx.clip()
    _panel_bg(ctx, px, py, pw, ph, col, pa, c=18, fill=0.58)
    ctx.rectangle(px + 1, py + 1, pw - 2, 42); ctx.set_source_rgba(*col, 0.12 * pa); ctx.fill()
    _txt(ctx, "KEIBA-PREDICT", px + 22, py + 29, 15, color=col, alpha=pa, bold=True, spacing=2)
    ver = "v2.3 → v2.4" if t > 4.2 else "v2.3 → v2.4-rc"
    _txt(ctx, ver, px + 200, py + 29, 14, font=FONT_SANS_M, color=WHITE, alpha=pa * 0.75, glow=0)
    _txt(ctx, "MODEL UPDATE", px + pw - 22, py + 28, 12, color=col, alpha=pa * 0.7, align="right", glow=0)

    # title line with animated dots / completion
    k0 = clamp((t - 0.45) / 0.4)
    done = t >= 4.3
    head = "予測モデルを更新中" + "…" if not done else "予測モデル 更新完了"
    _txt(ctx, _scramble(head, k0, 5 + int(t * 16)), px + 26, py + 96, 32, font=FONT_SANS,
         color=WHITE, alpha=pa * clamp(k0 * 3), glow=0.4, spacing=2)
    if not done and k0 >= 1:
        # spinner
        ctx.save(); ctx.translate(px + pw - 50, py + 84)
        for i in range(8):
            ang = i * TAU / 8 + t * 4
            ctx.arc(math.cos(ang) * 12, math.sin(ang) * 12, 2.2, 0, TAU)
            ctx.set_source_rgba(*col, pa * (0.15 + 0.85 * ((i / 8 + t * 0.64) % 1))); ctx.fill()
        ctx.restore()
    else:
        _txt(ctx, "✓", px + pw - 50, py + 96, 30, font="DejaVu Sans", color=col, alpha=pa * k0,
             align="center", glow=1.0)
    _txt(ctx, "UPDATING PREDICTION MODEL  //  learn.py --append", px + 28, py + 122, 12, color=col,
         alpha=pa * 0.6 * k0, glow=0)

    # progress bar
    prog = ease_in_out(clamp((t - 0.6) / 3.7))
    bx, by, bw = px + 26, py + 142, pw - 130
    _bar(ctx, bx, by, bw, 10, prog, col, pa, segments=48)
    _txt(ctx, "%3d%%" % int(prog * 100), px + pw - 26, by + 11, 18, color=col, alpha=pa, align="right", bold=True, glow=0.7)

    # data lines
    rows = [
        (1.4, "新規学習データ", "1件", "NEW TRAINING SAMPLE", WHITE),
        (2.3, "ハルカゼ", "差し切り", "大井11R #14  1着  ハナ差", WHITE),
    ]
    yy = py + 206
    for t0, k_, v_, en, c_ in rows:
        kk = clamp((t - t0) / 0.35)
        if kk > 0:
            _txt(ctx, "▸", px + 26, yy, 18, font="DejaVu Sans", color=col, alpha=pa * kk, glow=0.6)
            w1 = _txt(ctx, _scramble(k_, kk, int(t0 * 10)), px + 52, yy, 24, font=FONT_SANS_M, color=c_,
                      alpha=pa * clamp(kk * 3), glow=0.25)
            sep = ": " if k_ == "新規学習データ" else " ― "
            w2 = _txt(ctx, sep, px + 52 + w1, yy, 24, font=FONT_SANS_M, color=c_, alpha=pa * kk * 0.8, glow=0)
            _txt(ctx, _scramble(v_, clamp(kk * 1.5 - 0.3), int(t0 * 10) + 3), px + 52 + w1 + w2, yy, 24,
                 font=FONT_SANS, color=col, alpha=pa * clamp(kk * 2), glow=0.6)
            _txt(ctx, en, px + pw - 26, yy, 11, font=FONT_SANS_M, color=col, alpha=pa * 0.55 * kk,
                 align="right", glow=0)
        yy += 46

    # the element that cannot be quantified
    kk = clamp((t - 3.25) / 0.5)
    if kk > 0:
        _line(ctx, px + 26, yy - 22, px + 26 + (pw - 52) * ease_out_cubic(kk), yy - 22, col, 0.5 * pa, 1, glow=False)
        _txt(ctx, "数値化できない要素:", px + 52, yy + 22, 22, font=FONT_SANS_M, color=WHITE,
             alpha=pa * clamp(kk * 2), glow=0.25)
        # 絆 — blooms gently in warm gold, right after the label
        bk = ease_out_cubic(clamp((t - 3.55) / 0.8))
        if bk > 0:
            lw_ = _measure(ctx, "数値化できない要素:", 22, FONT_SANS_M)
            gx = px + 52 + lw_ + 62            # glyph centre
            gy = yy + 8                        # glyph optical centre
            halo = cairo.RadialGradient(gx, gy, 4, gx, gy, 95)
            halo.add_color_stop_rgba(0, *GOLD, 0.40 * pa * bk); halo.add_color_stop_rgba(1, *GOLD, 0)
            ctx.set_source(halo); ctx.arc(gx, gy, 95, 0, TAU); ctx.fill()
            ctx.save(); ctx.translate(gx, gy); s_ = lerp(1.3, 1.0, bk); ctx.scale(s_, s_)
            _txt(ctx, "絆", 0, 26, 72, font=FONT_SERIF, color=GOLD, alpha=pa * bk, align="center", glow=1.4)
            ctx.restore()
            _txt(ctx, "KIZUNA", gx + 70, gy - 4, 16, color=GOLD, alpha=pa * 0.9 * clamp((t - 3.9) / 0.4),
                 bold=True, glow=0.6, spacing=3)
            _txt(ctx, "weight: N/A   value: ∞", gx + 70, gy + 18, 12, color=GOLD,
                 alpha=pa * 0.7 * clamp((t - 4.0) / 0.4), glow=0.3)
            # the 14th feature slot being added
            _txt(ctx, "feature[13] = kizuna   未定義 / UNDEFINED", px + 52, yy + 72, 12, font=FONT_SANS_M,
                 color=GOLD, alpha=pa * 0.6 * clamp((t - 4.3) / 0.4), glow=0)
    ctx.restore()
    draw_brackets(ctx, px, py, pw, ph, t - 0.2, col, alpha=pa, size=24)
    # rising soft motes when warm
    if warm > 0:
        rr = random.Random(41)
        for i in range(26):
            sx = px + rr.uniform(0, pw); sp = rr.uniform(14, 40); ph_ = rr.uniform(0, 10)
            sy = py + ph - ((t * sp + ph_ * 40) % (ph + 60))
            a = warm * pa * 0.6 * (0.5 + 0.5 * math.sin(t * 3 + i))
            ctx.arc(sx, sy, rr.uniform(1, 2.4), 0, TAU); ctx.set_source_rgba(*GOLD, a); ctx.fill()
    _group_end(ctx, alpha)


def _title_glyph(ctx, ch, size, a):
    """One title character centred at origin baseline: warm gold halo + cream->gold gradient fill."""
    ctx.save()
    ctx.select_font_face(FONT_SERIF); ctx.set_font_size(size)
    adv = ctx.text_extents(ch)[4]
    ctx.new_path(); ctx.move_to(-adv / 2, 0); ctx.text_path(ch)
    path = ctx.copy_path()
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    for wk, al in ((0.30, 0.035), (0.18, 0.06), (0.09, 0.10), (0.04, 0.16)):
        ctx.new_path(); ctx.append_path(path)
        ctx.set_line_width(size * wk); ctx.set_source_rgba(*GOLD, al * a); ctx.stroke()
    ctx.new_path(); ctx.append_path(path)
    g = cairo.LinearGradient(0, -size * 0.85, 0, size * 0.1)
    g.add_color_stop_rgba(0, 1.0, 0.98, 0.92, a)
    g.add_color_stop_rgba(0.55, 1.0, 0.90, 0.68, a)
    g.add_color_stop_rgba(1, 0.92, 0.66, 0.32, a)
    ctx.set_source(g); ctx.fill()
    ctx.restore()


# ============================================================ title card
def draw_title_card(ctx, t, *, alpha=1.0, fade_out=True):
    """t: 0 at global 57.4 .. 2.6 at 60.0.  Draws its own dark backdrop.
    fade_out=True: everything (scene included) fades to black over t 2.2-2.6."""
    if alpha <= 0 or t < 0:
        return
    _group_begin(ctx)
    # backdrop: vertical gradient darkening, strongest through the centre band
    bk = smoothstep(0.0, 0.5, t)
    g = cairo.LinearGradient(0, 0, 0, H)
    g.add_color_stop_rgba(0, 0.0, 0.0, 0.02, 0.45 * bk)
    g.add_color_stop_rgba(0.5, 0.01, 0.01, 0.04, 0.78 * bk)
    g.add_color_stop_rgba(1, 0.0, 0.0, 0.02, 0.55 * bk)
    ctx.set_source(g); ctx.paint()
    cx, cy = W / 2, H / 2 - 30
    # warm central glow
    halo = cairo.RadialGradient(cx, cy, 10, cx, cy, 700)
    halo.add_color_stop_rgba(0, *GOLD, 0.12 * bk); halo.add_color_stop_rgba(1, *GOLD, 0)
    ctx.set_source(halo); ctx.paint()

    # particles (gold dust drifting up)
    rr = random.Random(2026)
    for i in range(90):
        px = rr.uniform(0, W); py0 = rr.uniform(0, H); sp = rr.uniform(8, 40); sz = rr.uniform(0.8, 2.8)
        py = (py0 - t * sp) % H
        px += 12 * math.sin(t * 0.8 + i)
        dist = abs(py - cy) / H
        tw = 0.5 + 0.5 * math.sin(t * rr.uniform(2, 5) + i)
        a = bk * tw * (0.25 + 0.75 * (1 - dist)) * 0.7
        if sz > 2.2:
            rg = cairo.RadialGradient(px, py, 0, px, py, sz * 5)
            rg.add_color_stop_rgba(0, *GOLD, a * 0.6); rg.add_color_stop_rgba(1, *GOLD, 0)
            ctx.set_source(rg); ctx.arc(px, py, sz * 5, 0, TAU); ctx.fill()
        ctx.arc(px, py, sz * 0.6, 0, TAU); ctx.set_source_rgba(1, 0.93, 0.75, a); ctx.fill()

    # gold line wipe (from centre outward) 0.15-0.95
    lk = ease_out_cubic(clamp((t - 0.15) / 0.8))
    half = 520 * lk
    ly = cy + 88
    for yy_, a_ in ((ly, 1.0),):
        gl = cairo.LinearGradient(cx - half, 0, cx + half, 0)
        gl.add_color_stop_rgba(0, *GOLD, 0); gl.add_color_stop_rgba(0.5, *_hot(GOLD, 0.4), 0.95 * a_)
        gl.add_color_stop_rgba(1, *GOLD, 0)
        # glow line
        ctx.rectangle(cx - half, yy_ - 4, half * 2, 8)
        g2 = cairo.LinearGradient(cx - half, 0, cx + half, 0)
        g2.add_color_stop_rgba(0, *GOLD, 0); g2.add_color_stop_rgba(0.5, *GOLD, 0.18); g2.add_color_stop_rgba(1, *GOLD, 0)
        ctx.set_source(g2); ctx.fill()
        ctx.rectangle(cx - half, yy_ - 0.9, half * 2, 1.8); ctx.set_source(gl); ctx.fill()
    # travelling sparks at line ends
    if 0 < lk < 1:
        for sx in (cx - half, cx + half):
            radial = cairo.RadialGradient(sx, ly, 0, sx, ly, 26)
            radial.add_color_stop_rgba(0, 1, 0.95, 0.8, 0.9); radial.add_color_stop_rgba(1, *GOLD, 0)
            ctx.set_source(radial); ctx.arc(sx, ly, 26, 0, TAU); ctx.fill()
    # small diamond centre ornament
    dk = clamp((t - 0.7) / 0.3)
    if dk > 0:
        ctx.save(); ctx.translate(cx, ly); ctx.rotate(math.pi / 4); s = 5 * ease_out_back(dk)
        ctx.rectangle(-s, -s, 2 * s, 2 * s); ctx.set_source_rgba(*_hot(GOLD, 0.4), dk); ctx.fill(); ctx.restore()

    # title characters: soft focus-in one by one
    title = "最後の一完歩"
    size = 150
    ctx.save()
    ctx.select_font_face(FONT_SERIF); ctx.set_font_size(size)
    adv = [ctx.text_extents(ch)[4] for ch in title]
    ctx.restore()
    gap = 18
    tw = sum(adv) + gap * (len(title) - 1)
    x = cx - tw / 2
    for i, ch in enumerate(title):
        t0 = 0.35 + i * 0.13
        k = clamp((t - t0) / 0.55)
        if k > 0:
            e = ease_out_cubic(k)
            ccx = x + adv[i] / 2
            ctx.save()
            ctx.translate(ccx, cy + 40 + (1 - e) * 18)
            sc = lerp(1.12, 1.0, e); ctx.scale(sc, sc)
            # blur-in: several offset faint copies collapsing together
            spread = (1 - e) * 10
            if spread > 0.5:
                for dx, dy in ((-spread, 0), (spread, 0), (0, -spread), (0, spread)):
                    _txt(ctx, ch, dx, dy, size, font=FONT_SERIF, color=(1, 0.95, 0.85), alpha=0.18 * e,
                         align="center", glow=0)
            _title_glyph(ctx, ch, size, e)
            ctx.restore()
        x += adv[i] + gap
    # shimmer sweep across title 1.4-2.0
    sk = clamp((t - 1.35) / 0.7)
    if 0 < sk < 1:
        ctx.save()
        ctx.select_font_face(FONT_SERIF); ctx.set_font_size(size)
        x = cx - tw / 2
        ctx.new_path()
        for i, ch in enumerate(title):
            ctx.move_to(x, cy + 40); ctx.text_path(ch); x += adv[i] + gap
        ctx.clip()
        sx = lerp(cx - tw / 2 - 200, cx + tw / 2 + 200, ease_in_out(sk))
        sg = cairo.LinearGradient(sx - 120, 0, sx + 120, 0)
        sg.add_color_stop_rgba(0, 1, 1, 1, 0); sg.add_color_stop_rgba(0.5, 1, 1, 0.95, 0.7); sg.add_color_stop_rgba(1, 1, 1, 1, 0)
        ctx.set_source(sg); ctx.paint()
        ctx.restore()

    # English subtitle
    ek = clamp((t - 1.1) / 0.6)
    if ek > 0:
        sp = lerp(26, 16, ease_out_cubic(ek))
        _txt(ctx, "THE LAST STRIDE", cx, ly + 52, 26, font="DejaVu Sans", color=GOLD, alpha=ek * 0.95,
             align="center", glow=0.5, spacing=sp)
    ek2 = clamp((t - 1.5) / 0.5)
    if ek2 > 0:
        _txt(ctx, "OI RACECOURSE  ·  TWINKLE RACE", cx, ly + 88, 13, font="DejaVu Sans", color=GOLD,
             alpha=ek2 * 0.5, align="center", glow=0, spacing=6)
    _group_end(ctx, alpha)
    if fade_out:
        f = smoothstep(2.2, 2.6, t)
        if f > 0:
            ctx.save(); ctx.set_source_rgba(0, 0, 0, f * clamp(alpha)); ctx.paint(); ctx.restore()


# ============================================================ self test
if __name__ == "__main__":
    import os, sys, time
    from lib.common import vgradient, radial_glow
    OUT = "/tmp/claude-0/-home-user-keiba/d53da140-107f-55e4-b8c0-8a92c9796981/scratchpad"
    os.makedirs(OUT, exist_ok=True)

    def bg(ctx, kind="night"):
        vgradient(ctx, 0, 0, W, H, [(0, PAL["night_top"]), (0.6, PAL["night_mid"]), (1, PAL["night_low"])])
        rr = random.Random(5)
        for i in range(160):   # city lights
            x = rr.uniform(0, W); y = rr.uniform(H * 0.62, H)
            radial_glow(ctx, x, y, rr.uniform(4, 16), PAL["lamp_warm"] if i % 3 else PAL["light_cool"], 0.5)
        if kind == "track":
            ctx.rectangle(0, H * 0.7, W, H * 0.3); ctx.set_source_rgb(*PAL["track_dirt"]); ctx.fill()

    def save(s, name):
        p = os.path.join(OUT, name); s.write_to_png(p); print(p)

    def frame():
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H); c = cairo.Context(s); return s, c

    for tt in [0.45, 0.9, 1.4, 2.0, 2.8, 3.1, 3.5, 4.4, 5.3]:
        s, c = frame(); bg(c)
        t0 = time.time(); draw_boot(c, tt, target=(1300, 700)); dt = time.time() - t0
        save(s, "boot_%.2f.png" % tt); print("  boot %.1f ms" % (dt * 1000))
    s, c = frame(); bg(c); draw_boot(c, 5.5, target=None); save(s, "boot_notarget_5.50.png")

    for gt in [25.0, 32.0, 36.0, 38.8, 40.6, 41.1, 41.6, 43.0]:
        s, c = frame(); bg(c, "track")
        p = prob_curve(gt)
        t0 = time.time()
        draw_prob_panel(c, gt, p, glitch=glitch_curve(gt), history=history_at(gt))
        dt = time.time() - t0
        save(s, "prob_%.1f.png" % gt); print("  prob", p, "%.1f ms" % (dt * 1000))

    s, c = frame(); bg(c, "track"); draw_prob_panel(c, 41.5, "ERROR", glitch=1.0, history=history_at(41.5))
    t0 = time.time(); glitch_frame(s, 1.0, 1234); print("  glitch_frame 1.0: %.1f ms" % ((time.time() - t0) * 1000))
    save(s, "glitch_1.0.png")
    s, c = frame(); bg(c, "track"); draw_prob_panel(c, 40.5, prob_curve(40.5), glitch=0.3, history=history_at(40.5))
    t0 = time.time(); glitch_frame(c, 0.3, 77); print("  glitch_frame 0.3: %.1f ms" % ((time.time() - t0) * 1000))
    save(s, "glitch_0.3.png")

    for tt in [0.8, 2.6, 3.6, 4.8]:
        s, c = frame(); bg(c)
        draw_update_panel(c, tt); save(s, "update_%.1f.png" % tt)
    for tt in [0.5, 1.0, 1.6, 2.1, 2.45]:
        s, c = frame(); bg(c)
        draw_title_card(c, tt); save(s, "title_%.2f.png" % tt)
    print("curve:", [(g, prob_curve(g)) for g in (20, 29.6, 31, 33, 34.4, 35.8, 37.2, 38.6, 40, 40.7, 41.3, 41.5, 42.5)])
