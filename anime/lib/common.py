"""Shared drawing / math helpers. Import as: from lib.common import *"""
import math, random
import cairo
from config import W, H, FPS, PAL, FONT_SANS, FONT_SANS_M, FONT_SERIF, FONT_IMPACT

TAU = math.tau

# ---------- math / easing ----------
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x

def lerp(a, b, t):
    return a + (b - a) * t

def invlerp(a, b, x):
    return clamp((x - a) / (b - a)) if b != a else 0.0

def remap(x, a, b, c, d, clip=True):
    t = (x - a) / (b - a) if b != a else 0.0
    if clip:
        t = clamp(t)
    return c + (d - c) * t

def smoothstep(a, b, x):
    t = invlerp(a, b, x)
    return t * t * (3 - 2 * t)

def ease_in_out(t):
    t = clamp(t); return t * t * (3 - 2 * t)

def ease_out_cubic(t):
    t = clamp(t); return 1 - (1 - t) ** 3

def ease_in_cubic(t):
    t = clamp(t); return t ** 3

def ease_out_back(t, s=1.70158):
    t = clamp(t) - 1; return t * t * ((s + 1) * t + s) + 1

def ease_out_elastic(t):
    t = clamp(t)
    if t in (0.0, 1.0): return t
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (TAU / 3)) + 1

def mix_color(c1, c2, t):
    return tuple(lerp(a, b, t) for a, b in zip(c1, c2))

def _hash(i, seed=0):
    x = (i * 374761393 + seed * 668265263) & 0xFFFFFFFF
    x = ((x ^ (x >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((x ^ (x >> 16)) & 0xFFFFFF) / float(0xFFFFFF)

def noise1(x, seed=0):
    """Smooth 1D value noise in [0,1]."""
    i = math.floor(x); f = x - i
    u = f * f * (3 - 2 * f)
    return lerp(_hash(i, seed), _hash(i + 1, seed), u)

def fbm1(x, seed=0, octaves=3):
    s, a, n = 0.0, 0.5, 0.0
    for o in range(octaves):
        s += a * noise1(x * (2 ** o), seed + o * 17); n += a; a *= 0.5
    return s / n

def shake(t, amp, freq=18.0, seed=0):
    """Camera shake offset (dx, dy)."""
    return ((noise1(t * freq, seed) - 0.5) * 2 * amp, (noise1(t * freq, seed + 99) - 0.5) * 2 * amp)

def rng(seed):
    return random.Random(seed)

# ---------- cairo helpers ----------
def new_surface(w=W, h=H):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    return s, cairo.Context(s)

def fill_rgb(ctx, c, a=1.0):
    if len(c) == 4:
        ctx.set_source_rgba(*c)
    else:
        ctx.set_source_rgba(c[0], c[1], c[2], a)

def vgradient(ctx, x, y, w, h, stops):
    """stops: list of (pos, (r,g,b) or (r,g,b,a))."""
    g = cairo.LinearGradient(x, y, x, y + h)
    for p, c in stops:
        if len(c) == 3: g.add_color_stop_rgb(p, *c)
        else: g.add_color_stop_rgba(p, *c)
    ctx.rectangle(x, y, w, h); ctx.set_source(g); ctx.fill()

def radial_glow(ctx, x, y, r, color, alpha=1.0, r0=0.0):
    g = cairo.RadialGradient(x, y, r0, x, y, r)
    g.add_color_stop_rgba(0, color[0], color[1], color[2], alpha)
    g.add_color_stop_rgba(0.35, color[0], color[1], color[2], alpha * 0.35)
    g.add_color_stop_rgba(1, color[0], color[1], color[2], 0)
    ctx.save(); ctx.set_source(g); ctx.arc(x, y, r, 0, TAU); ctx.fill(); ctx.restore()

def stroke_glow(ctx, color, width, alpha=1.0, layers=4, spread=3.0):
    """Stroke the current path with a soft neon glow (path is preserved then cleared)."""
    path = ctx.copy_path()
    ctx.save()
    ctx.set_line_cap(cairo.LINE_CAP_ROUND); ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    for i in range(layers, 0, -1):
        ctx.new_path(); ctx.append_path(path)
        ctx.set_line_width(width * (1 + spread * i / layers))
        ctx.set_source_rgba(color[0], color[1], color[2], alpha * 0.12)
        ctx.stroke()
    ctx.new_path(); ctx.append_path(path)
    ctx.set_line_width(width)
    ctx.set_source_rgba(min(1, color[0] + .5), min(1, color[1] + .5), min(1, color[2] + .5), alpha)
    ctx.stroke()
    ctx.restore()

def smooth_path(ctx, pts, closed=False, tension=0.5):
    """Catmull-Rom spline through pts -> cairo curves."""
    n = len(pts)
    if n < 2: return
    P = list(pts)
    if closed:
        P = [pts[-1]] + list(pts) + [pts[0], pts[1]]
    else:
        P = [pts[0]] + list(pts) + [pts[-1]]
    ctx.move_to(*P[1])
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        c1 = (p1[0] + (p2[0] - p0[0]) * tension / 3, p1[1] + (p2[1] - p0[1]) * tension / 3)
        c2 = (p2[0] - (p3[0] - p1[0]) * tension / 3, p2[1] - (p3[1] - p1[1]) * tension / 3)
        ctx.curve_to(c1[0], c1[1], c2[0], c2[1], p2[0], p2[1])
    if closed: ctx.close_path()

def text(ctx, s, x, y, size, font=FONT_SANS, color=(1, 1, 1), alpha=1.0, align="center",
         outline=0.0, outline_color=(0, 0, 0), outline_alpha=1.0, valign="baseline"):
    """Draw text. align: left|center|right. Returns (width, height)."""
    ctx.save()
    ctx.select_font_face(font); ctx.set_font_size(size)
    xb, yb, tw, th, xa, ya = ctx.text_extents(s)
    if align == "center": x -= xa / 2
    elif align == "right": x -= xa
    if valign == "middle": y += size * 0.35
    ctx.move_to(x, y); ctx.text_path(s)
    if outline > 0:
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)
        ctx.set_line_width(outline)
        ctx.set_source_rgba(*outline_color, outline_alpha * alpha)
        ctx.stroke_preserve()
    ctx.set_source_rgba(*color[:3], alpha); ctx.fill()
    ctx.restore()
    return xa, th

def speed_lines(ctx, t, cx, cy, n=90, inner=380, outer=1400, color=(1, 1, 1), alpha=0.6, seed=3):
    """Manga-style radial focus lines around (cx,cy)."""
    r = rng(seed + int(t * FPS) // 2)
    ctx.save()
    for i in range(n):
        a = r.random() * TAU
        w = r.uniform(0.004, 0.018)
        ri = inner * r.uniform(0.85, 1.35)
        ctx.move_to(cx + math.cos(a) * outer, cy + math.sin(a) * outer)
        ctx.line_to(cx + math.cos(a - w) * ri * 1.0, cy + math.sin(a - w) * ri)
        ctx.line_to(cx + math.cos(a + w) * outer, cy + math.sin(a + w) * outer)
        ctx.close_path()
        ctx.set_source_rgba(*color, alpha * r.uniform(0.4, 1.0)); ctx.fill()
    ctx.restore()

def horiz_speed_lines(ctx, t, y0, y1, n=40, speed=4000, color=(1, 1, 1), alpha=0.5, seed=5, length=(200, 700)):
    """Horizontal motion streaks moving left (for side tracking shots)."""
    r = rng(seed)
    ctx.save()
    for i in range(n):
        y = r.uniform(y0, y1); L = r.uniform(*length); sp = speed * r.uniform(0.6, 1.4)
        x = (r.uniform(0, W + L) - t * sp) % (W + L * 2) - L
        th = r.uniform(1.5, 5)
        g = cairo.LinearGradient(x, 0, x + L, 0)
        g.add_color_stop_rgba(0, *color, 0); g.add_color_stop_rgba(0.7, *color, alpha); g.add_color_stop_rgba(1, *color, 0)
        ctx.set_source(g); ctx.rectangle(x, y, L, th); ctx.fill()
    ctx.restore()
