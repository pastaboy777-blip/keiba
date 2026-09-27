"""Environment / background art for 「最後の一完歩」.

大井競馬場 Twinkle night race + warm old stable.  All functions paint onto `ctx`
in the ctx's current user space (so scenes may pre-apply shake/zoom transforms).

Static layers are rendered lazily once per process (fixed seeds) and cached as
cairo ImageSurfaces; per-frame work is mostly surface blits + a few dynamic
lights (twinkles, flashes, beacons, trains, particles).

Public API (see each docstring):
    draw_sky, draw_city, draw_racecourse_establishing,
    draw_race_side_bg, draw_race_side_fg, draw_track_straight_perspective,
    draw_finish_post, draw_starting_gate (+ _back / _front),
    draw_stable, dust_kick, bokeh, confetti_light
Self-test:  python3 lib/env.py [outdir]
"""
import os, sys, math, random, time

_HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.dirname(_HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(_HERE))

import numpy as np
import cairo
from PIL import Image
from scipy import ndimage as _ndi

from lib.common import (W, H, FPS, PAL, TAU, clamp, lerp, invlerp, smoothstep, mix_color,
                        _hash, noise1, fbm1, rng, radial_glow, ease_out_back)

# ======================================================================
#  low-level helpers
# ======================================================================
_CACHE = {}


def _cached(key, fn):
    v = _CACHE.get(key)
    if v is None:
        v = fn()
        _CACHE[key] = v
    return v


def _surf(w, h):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(w), int(h))
    return s, cairo.Context(s)


def _np_to_surface(rgba):
    """float32 HxWx4 straight-alpha (0..1) -> cairo ImageSurface."""
    h, w = rgba.shape[:2]
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    stride = s.get_stride()
    buf = np.ndarray((h, stride // 4, 4), np.uint8, s.get_data())
    a = np.clip(rgba[..., 3:4], 0, 1)
    pm = np.clip(rgba[..., :3], 0, 1) * a
    out = np.empty((h, w, 4), np.uint8)
    out[..., 0] = (pm[..., 2] * 255 + 0.5)
    out[..., 1] = (pm[..., 1] * 255 + 0.5)
    out[..., 2] = (pm[..., 0] * 255 + 0.5)
    out[..., 3] = (a[..., 0] * 255 + 0.5)
    buf[:, :w] = out
    s.mark_dirty()
    return s


def _surface_to_np(s):
    """cairo ARGB32 -> float32 premultiplied HxWx4 in BGRA order."""
    s.flush()
    h, w, stride = s.get_height(), s.get_width(), s.get_stride()
    return np.ndarray((h, stride // 4, 4), np.uint8, s.get_data())[:, :w].astype(np.float32) / 255.0


def _np_premul_to_surface(pm):
    """float32 premultiplied BGRA HxWx4 -> new surface."""
    h, w = pm.shape[:2]
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    stride = s.get_stride()
    buf = np.ndarray((h, stride // 4, 4), np.uint8, s.get_data())
    buf[:, :w] = (np.clip(pm, 0, 1) * 255 + 0.5).astype(np.uint8)
    s.mark_dirty()
    return s


def _hblur_surface(s, radius, wrap=True):
    """Horizontal motion-blur copy of a surface (box blur x3 ~ gaussian-ish streak)."""
    a = _surface_to_np(s)
    mode = "wrap" if wrap else "nearest"
    r = max(1, int(radius))
    for _ in range(2):
        a = _ndi.uniform_filter1d(a, size=r, axis=1, mode=mode)
    return _np_premul_to_surface(a)


def _blur_surface(s, sigma):
    a = _surface_to_np(s)
    a = _ndi.gaussian_filter(a, sigma=(sigma, sigma, 0))
    return _np_premul_to_surface(a)


def _value_noise(h, w, cells_y, cells_x, seed, order=3):
    r = np.random.default_rng(seed)
    g = r.random((cells_y + 3, cells_x + 3)).astype(np.float32)
    zy = (cells_y + 3) / (cells_y + 0.0)
    out = _ndi.zoom(g, (h / cells_y, w / cells_x), order=order, mode="grid-wrap", grid_mode=True)
    return out[:h, :w]


def _fbm2(h, w, base_cells=(4, 8), octaves=5, seed=0, gain=0.5):
    s = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    cy, cx = base_cells
    for o in range(octaves):
        s += amp * _value_noise(h, w, int(cy), int(cx), seed + o * 31)
        tot += amp
        amp *= gain
        cy *= 2; cx *= 2
        if cy > h / 2 or cx > w / 2:
            break
    return s / tot


def _paint_strip(ctx, surf, x_off, y, scale=1.0, alpha=1.0, x0=-200, x1=W + 200, h=None,
                 extend=cairo.EXTEND_REPEAT, filt=cairo.FILTER_BILINEAR):
    """Paint horizontally-tiling strip `surf` so strip-x = (screen_x + x_off)/scale, top at y."""
    hh = surf.get_height() * scale if h is None else h
    pat = cairo.SurfacePattern(surf)
    pat.set_extend(extend)
    pat.set_filter(filt)
    m = cairo.Matrix(1.0 / scale, 0, 0, 1.0 / scale, x_off / scale, -y / scale)
    pat.set_matrix(m)
    ctx.save()
    ctx.rectangle(x0, y, x1 - x0, hh)
    ctx.clip()
    ctx.set_source(pat)
    if alpha >= 0.999:
        ctx.paint()
    else:
        ctx.paint_with_alpha(alpha)
    ctx.restore()


def _blit(ctx, surf, x, y, alpha=1.0, scale=1.0):
    ctx.save()
    ctx.translate(x, y)
    if scale != 1.0:
        ctx.scale(scale, scale)
    ctx.set_source_surface(surf, 0, 0)
    ctx.get_source().set_filter(cairo.FILTER_BILINEAR)
    if alpha >= 0.999:
        ctx.paint()
    else:
        ctx.paint_with_alpha(alpha)
    ctx.restore()


def _glow(ctx, x, y, r, c, a=1.0, core=0.0):
    """Soft glow (smoother falloff than common.radial_glow)."""
    if r <= 0.5 or a <= 0.003:
        return
    g = cairo.RadialGradient(x, y, 0, x, y, r)
    g.add_color_stop_rgba(0, c[0], c[1], c[2], a)
    g.add_color_stop_rgba(0.12 + core, c[0], c[1], c[2], a * 0.55)
    g.add_color_stop_rgba(0.4, c[0], c[1], c[2], a * 0.16)
    g.add_color_stop_rgba(0.7, c[0], c[1], c[2], a * 0.04)
    g.add_color_stop_rgba(1, c[0], c[1], c[2], 0)
    ctx.set_source(g)
    ctx.arc(x, y, r, 0, TAU)
    ctx.fill()


def _star_flare(ctx, x, y, size, c, a=1.0, rays=4, rot=0.0):
    """Cross-shaped lens sparkle."""
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(rot)
    for k in range(rays):
        ang = k * math.pi / rays * 2 / 2 if rays == 4 else k * TAU / rays
        ang = k * (math.pi / (rays / 2))
        ctx.save()
        ctx.rotate(ang)
        L = size * (1.0 if k % 2 == 0 else 0.7)
        g = cairo.LinearGradient(0, 0, L, 0)
        g.add_color_stop_rgba(0, c[0], c[1], c[2], a)
        g.add_color_stop_rgba(1, c[0], c[1], c[2], 0)
        ctx.set_source(g)
        ctx.move_to(0, -size * 0.035 - 0.6)
        ctx.line_to(L, 0)
        ctx.line_to(0, size * 0.035 + 0.6)
        ctx.close_path()
        ctx.fill()
        ctx.restore()
    ctx.restore()


def _lin(ctx, x0, y0, x1, y1, stops):
    g = cairo.LinearGradient(x0, y0, x1, y1)
    for p, c in stops:
        if len(c) == 3:
            g.add_color_stop_rgb(p, *c)
        else:
            g.add_color_stop_rgba(p, *c)
    return g


def _rgba(ctx, c, a=1.0):
    ctx.set_source_rgba(c[0], c[1], c[2], a if len(c) == 3 else c[3] * a)


WARM = PAL["lamp_warm"]
COOL = PAL["light_cool"]
FLOOD = (1.0, 0.93, 0.78)      # floodlight amber-white
FLOOD_CORE = (1.0, 0.99, 0.95)


# ======================================================================
#  SKY
# ======================================================================
SKY_HZ = 1700          # horizon row inside sky canvas
SKY_CW, SKY_CH = 2160, 2150
SKY_X0 = -120


def _sky_base():
    s, c = _surf(SKY_CW, SKY_CH)
    hz = SKY_HZ
    g = cairo.LinearGradient(0, 0, 0, SKY_CH)
    stops = [
        (hz - 1700, (0.008, 0.012, 0.05)),
        (hz - 1050, (0.02, 0.03, 0.105)),
        (hz - 620, (0.05, 0.06, 0.20)),
        (hz - 380, (0.10, 0.085, 0.28)),
        (hz - 200, (0.19, 0.11, 0.33)),
        (hz - 80, (0.30, 0.15, 0.36)),
        (hz - 10, (0.42, 0.22, 0.38)),
        (hz + 60, (0.36, 0.20, 0.33)),
        (SKY_CH, (0.20, 0.12, 0.24)),
    ]
    for y, col in stops:
        g.add_color_stop_rgb(clamp(y / SKY_CH), *col)
    c.set_source(g)
    c.paint()
    # subtle painterly large-scale colour variation
    h4, w4 = SKY_CH // 8, SKY_CW // 8
    n = _fbm2(h4, w4, (3, 5), 4, seed=11)
    n2 = _fbm2(h4, w4, (2, 4), 3, seed=12)
    yy = (np.arange(h4)[:, None] * 8 - hz) / 900.0
    m = np.clip(1.0 + yy, 0, 1)   # stronger in upper mid sky
    rgba = np.zeros((h4, w4, 4), np.float32)
    rgba[..., 0] = 0.35 + 0.3 * n2
    rgba[..., 1] = 0.18
    rgba[..., 2] = 0.55
    rgba[..., 3] = np.clip((n - 0.45) * 0.35, 0, 0.09) * m
    tex = _np_to_surface(np.repeat(np.repeat(rgba, 8, 0), 8, 1)[:SKY_CH, :SKY_CW])
    tex = _blur_surface(tex, 6)
    c.set_source_surface(tex, 0, 0)
    c.paint()
    return s


def _sky_glow():
    s, c = _surf(SKY_CW, SKY_CH)
    hz = SKY_HZ
    # warm city light pollution band
    g = cairo.LinearGradient(0, hz - 520, 0, hz + 120)
    g.add_color_stop_rgba(0, 1.0, 0.45, 0.45, 0)
    g.add_color_stop_rgba(0.45, 0.95, 0.42, 0.50, 0.10)
    g.add_color_stop_rgba(0.78, 1.0, 0.55, 0.42, 0.32)
    g.add_color_stop_rgba(0.86, 1.0, 0.68, 0.46, 0.45)
    g.add_color_stop_rgba(1, 1.0, 0.60, 0.45, 0.0)
    c.rectangle(0, hz - 520, SKY_CW, 640)
    c.set_source(g)
    c.fill()
    # hot spots (districts) along horizon
    r = rng(5)
    for i in range(9):
        x = r.uniform(0, SKY_CW)
        c.save()
        c.translate(x, hz)
        c.scale(1.0, 0.33)
        _glow(c, 0, 0, r.uniform(380, 700), (1.0, r.uniform(0.5, 0.7), 0.45), r.uniform(0.18, 0.3))
        c.restore()
    return s


def _sky_stars():
    s, c = _surf(SKY_CW, SKY_CH)
    hz = SKY_HZ
    # faint milky band (diagonal)
    h4, w4 = SKY_CH // 4, SKY_CW // 4
    n = _fbm2(h4, w4, (6, 10), 5, seed=21)
    yy, xx = np.mgrid[0:h4, 0:w4].astype(np.float32) * 4
    d = (yy - (hz - 1150) - (xx - 1000) * 0.45) / 330.0
    band = np.exp(-d * d) * np.clip((hz - 250 - yy) / 500, 0, 1)
    rgba = np.zeros((h4, w4, 4), np.float32)
    rgba[..., 0] = 0.62 + 0.2 * n
    rgba[..., 1] = 0.55
    rgba[..., 2] = 0.95
    rgba[..., 3] = np.clip(band * (n - 0.3) * 0.35, 0, 0.14)
    tex = _np_to_surface(np.repeat(np.repeat(rgba, 4, 0), 4, 1))
    c.set_source_surface(_blur_surface(tex, 3), 0, 0)
    c.paint()
    r = rng(7)
    for i in range(1500):
        x = r.uniform(0, SKY_CW)
        y = r.uniform(0, hz - 60)
        # density in dark upper sky, thin near glowing horizon
        fade = clamp((hz - 120 - y) / 700.0)
        if r.random() > fade * 0.95 + 0.05:
            continue
        # cluster more in milky band
        dd = (y - (hz - 1150) - (x - 1000) * 0.45) / 330.0
        if r.random() > 0.45 + 0.55 * math.exp(-dd * dd) and r.random() < 0.5:
            continue
        m = r.random() ** 3
        rad = 0.45 + m * 1.5
        col = r.choice([(1, 1, 1), (0.8, 0.88, 1.0), (1.0, 0.9, 0.78), (0.9, 0.85, 1.0)])
        a = (0.3 + 0.7 * r.random()) * (0.4 + 0.6 * fade)
        if rad > 1.2:
            _glow(c, x, y, rad * 5, col, a * 0.35)
        c.set_source_rgba(*col, a)
        c.arc(x, y, rad, 0, TAU)
        c.fill()
    return s


_BRIGHT_STARS = None


def _bright_stars():
    global _BRIGHT_STARS
    if _BRIGHT_STARS is None:
        r = rng(9)
        L = []
        while len(L) < 34:
            x = r.uniform(0, SKY_CW); y = r.uniform(0, SKY_HZ - 300)
            L.append((x, y, r.uniform(2.5, 7.0), r.uniform(0.7, 2.6), r.uniform(0, TAU),
                      r.choice([(1, 1, 1), (0.8, 0.9, 1.0), (1.0, 0.92, 0.8)])))
        _BRIGHT_STARS = L
    return _BRIGHT_STARS


def _cloud_layer(seed, coverage, bands):
    """Painterly night clouds: dark violet bodies, pink city-lit undersides, moonlit tops."""
    ds = 4
    h4, w4 = SKY_CH // ds, SKY_CW // ds
    n = _fbm2(h4, w4, (5, 4), 6, seed=seed, gain=0.55)
    n2 = _fbm2(h4, w4, (10, 3), 4, seed=seed + 5)
    yy = np.arange(h4, dtype=np.float32)[:, None] * ds
    mask = np.zeros((h4, 1), np.float32)
    for (cy, hw, strength) in bands:           # cy = height above horizon
        d = (yy - (SKY_HZ - cy)) / hw
        mask += strength * np.exp(-d * d)
    dens = n * 0.7 + n2 * 0.3
    lo, hi = np.percentile(dens, 2), np.percentile(dens, 98)
    dens = np.clip((dens - lo) / (hi - lo), 0, 1)
    dens = np.clip((dens * np.minimum(mask, 1.2) - (1.0 - coverage)) * 3.0, 0, 1)
    dens = _ndi.gaussian_filter(dens, 0.8)
    below = np.roll(dens, -6, axis=0)
    above = np.roll(dens, 5, axis=0)
    under = np.clip(dens - below, 0, 1)        # bottom edges -> lit by city
    top = np.clip(dens - above, 0, 1)          # top edges -> moonlit
    hfac = np.clip(1.0 - (SKY_HZ - yy) / 1400.0, 0, 1)   # nearer horizon -> warmer
    body = np.zeros((h4, w4, 3), np.float32)
    body[..., 0] = 0.10 + 0.20 * hfac
    body[..., 1] = 0.08 + 0.07 * hfac
    body[..., 2] = 0.22 + 0.12 * hfac
    warm = np.array([1.0, 0.52, 0.55], np.float32)
    moon = np.array([0.62, 0.66, 0.95], np.float32)
    uw = np.clip(under * 5.0, 0, 1)[..., None] * (0.35 + 0.65 * hfac[..., None])
    tw = np.clip(top * 4.0, 0, 1)[..., None] * 0.55
    col = body * (1 - uw) + warm * uw
    col = col * (1 - tw) + moon * tw
    # interior variation
    col *= (0.85 + 0.3 * n2[..., None])
    rgba = np.concatenate([col, (dens ** 0.8)[..., None] * 0.92], axis=2)
    up = _ndi.zoom(rgba, (ds, ds, 1), order=1)[:SKY_CH, :SKY_CW]
    return _np_to_surface(up)


def _sky_clouds_a():
    return _cloud_layer(31, 0.36, [(120, 60, 1.0), (360, 90, 0.85), (780, 110, 0.7)])


def _sky_clouds_b():
    return _cloud_layer(47, 0.42, [(60, 45, 1.0), (240, 80, 0.9), (560, 140, 0.8), (1000, 180, 0.6)])


def _moon_sprite(r):
    r = int(r)
    R = r * 7
    s, c = _surf(2 * R, 2 * R)
    cx = cy = R
    _glow(c, cx, cy, R, (0.75, 0.78, 1.0), 0.35)
    _glow(c, cx, cy, r * 2.6, (0.95, 0.93, 1.0), 0.45)
    # halo ring
    g = cairo.RadialGradient(cx, cy, r * 2.9, cx, cy, r * 3.6)
    g.add_color_stop_rgba(0, 0.8, 0.85, 1, 0)
    g.add_color_stop_rgba(0.5, 0.8, 0.85, 1, 0.06)
    g.add_color_stop_rgba(1, 0.8, 0.85, 1, 0)
    c.set_source(g); c.arc(cx, cy, r * 3.6, 0, TAU); c.fill()
    # disc
    g = cairo.RadialGradient(cx - r * 0.3, cy - r * 0.3, r * 0.1, cx, cy, r)
    g.add_color_stop_rgb(0, 1.0, 0.99, 0.94)
    g.add_color_stop_rgb(0.75, 0.97, 0.95, 0.88)
    g.add_color_stop_rgb(1, 0.88, 0.86, 0.85)
    c.set_source(g); c.arc(cx, cy, r, 0, TAU); c.fill()
    # maria
    c.save(); c.arc(cx, cy, r, 0, TAU); c.clip()
    rr = rng(3)
    for i in range(6):
        a = rr.uniform(0, TAU); d = rr.uniform(0.1, 0.6) * r
        _glow(c, cx + math.cos(a) * d, cy + math.sin(a) * d, rr.uniform(0.35, 0.6) * r,
              (0.78, 0.76, 0.84), 0.3)
    c.restore()
    return s


def draw_sky(ctx, t, horizon_y=700, stars=1.0, moon=(1500, 180, 55), clouds=0.5, glow=1.0):
    """Night sky: indigo->purple gradient, painterly clouds lit by city from below,
    twinkling stars, moon with halo. horizon_y may be animated (tilts): stars &
    clouds are fixed relative to the horizon."""
    oy = horizon_y - SKY_HZ
    if oy > 0:
        ctx.save(); ctx.set_source_rgb(0.008, 0.012, 0.05)
        ctx.rectangle(-400, -400, W + 800, oy + 402); ctx.fill(); ctx.restore()
    base = _cached("sky_base", _sky_base)
    _blit(ctx, base, SKY_X0, oy)
    if oy + SKY_CH < H + 400:
        ctx.save(); ctx.set_source_rgb(0.20, 0.12, 0.24)
        ctx.rectangle(-400, oy + SKY_CH - 1, W + 800, H + 800); ctx.fill(); ctx.restore()
    if stars > 0:
        _blit(ctx, _cached("sky_stars", _sky_stars), SKY_X0, oy, alpha=clamp(stars))
        for (x, y, sz, fr, ph, col) in _bright_stars():
            sx, sy = x + SKY_X0, y + oy
            if -30 < sx < W + 30 and -30 < sy < H + 30:
                tw = 0.55 + 0.45 * math.sin(t * fr * 2.2 + ph) * math.sin(t * fr * 1.3 + ph * 2)
                a = stars * (0.5 + 0.5 * tw)
                _glow(ctx, sx, sy, sz * 3.2, col, a * 0.5)
                _star_flare(ctx, sx, sy, sz * (2.2 + tw), col, a * 0.8)
                ctx.set_source_rgba(1, 1, 1, a)
                ctx.arc(sx, sy, 1.2, 0, TAU); ctx.fill()
    if moon:
        mx, my, mr = moon
        spr = _cached(("moon", int(mr)), lambda: _moon_sprite(mr))
        R = int(mr) * 7
        _blit(ctx, spr, mx - R, my - R)
    if glow > 0:
        _blit(ctx, _cached("sky_glow", _sky_glow), SKY_X0, oy, alpha=clamp(glow))
    if clouds > 0:
        _blit(ctx, _cached("sky_cl_a", _sky_clouds_a), SKY_X0, oy, alpha=clamp(clouds * 2))
        if clouds > 0.5:
            _blit(ctx, _cached("sky_cl_b", _sky_clouds_b), SKY_X0, oy, alpha=clamp(clouds * 2 - 1))
