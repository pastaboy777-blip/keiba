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

# ---- optional on-disk cache of the static layers (build/env_cache, auto-invalidated
#      whenever this file changes). Disable with ENV_NO_DISK_CACHE=1.
import pickle, hashlib
try:
    from config import BUILD as _BUILD
except Exception:
    _BUILD = os.path.join(os.path.dirname(_HERE), "build")
_DISK = os.environ.get("ENV_NO_DISK_CACHE", "") == ""
with open(os.path.abspath(__file__), "rb") as _f:
    _SRC_HASH = hashlib.md5(_f.read()).hexdigest()[:10]
_CDIR = os.path.join(_BUILD, "env_cache", _SRC_HASH)


def _disk_load(name):
    if not _DISK:
        return None
    meta = os.path.join(_CDIR, name + ".pkl")
    if not os.path.exists(meta):
        return None
    try:
        with open(meta, "rb") as f:
            d = pickle.load(f)
        for k in d.pop("__surfaces__", []):
            d[k] = cairo.ImageSurface.create_from_png(os.path.join(_CDIR, f"{name}.{k}.png"))
        return d
    except Exception:
        return None


def _disk_save(name, d):
    if not _DISK:
        return
    try:
        os.makedirs(_CDIR, exist_ok=True)
        plain, surfs = {}, []
        for k, v in d.items():
            if isinstance(v, cairo.ImageSurface):
                tmp = os.path.join(_CDIR, f"{name}.{k}.png.{os.getpid()}.tmp")
                v.write_to_png(tmp); os.replace(tmp, os.path.join(_CDIR, f"{name}.{k}.png"))
                surfs.append(k)
            else:
                plain[k] = v
        plain["__surfaces__"] = surfs
        tmp = os.path.join(_CDIR, f"{name}.pkl.{os.getpid()}.tmp")
        with open(tmp, "wb") as f:
            pickle.dump(plain, f)
        os.replace(tmp, os.path.join(_CDIR, name + ".pkl"))
    except Exception:
        pass


def _disk_dict(name, fn):
    """Build a dict of layers (surfaces + picklable data) once, reusing the disk cache."""
    d = _disk_load(name)
    if d is None:
        d = fn()
        _disk_save(name, d)
    return d


def _cached(key, fn):
    v = _CACHE.get(key)
    if v is None:
        v = _disk_dict(str(key).replace(" ", ""), lambda: {"s": fn()})["s"]
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
    ds = 3
    h4, w4 = SKY_CH // ds, SKY_CW // ds
    n = _fbm2(h4, w4, (16, 5), 7, seed=seed, gain=0.55)
    n2 = _fbm2(h4, w4, (30, 4), 4, seed=seed + 5)
    yy = np.arange(h4, dtype=np.float32)[:, None] * ds
    mask = np.zeros((h4, 1), np.float32)
    for (cy, hw, strength) in bands:           # cy = height above horizon
        d = (yy - (SKY_HZ - cy)) / hw
        mask += strength * np.exp(-d * d)
    dens = n * 0.7 + n2 * 0.3
    lo, hi = np.percentile(dens, 2), np.percentile(dens, 98)
    dens = np.clip((dens - lo) / (hi - lo), 0, 1)
    dens = np.clip((dens * np.minimum(mask, 1.2) - (1.0 - coverage)) * 4.0, 0, 1)
    dens = _ndi.gaussian_filter(dens, 0.6)
    below = np.roll(dens, -4, axis=0)
    above = np.roll(dens, 3, axis=0)
    under = np.clip(dens - below, 0, 1)        # bottom edges -> lit by city
    top = np.clip(dens - above, 0, 1)          # top edges -> moonlit
    hfac = np.clip(1.0 - (SKY_HZ - yy) / 1400.0, 0, 1)   # nearer horizon -> warmer
    body = np.zeros((h4, w4, 3), np.float32)
    body[..., 0] = 0.10 + 0.20 * hfac
    body[..., 1] = 0.08 + 0.07 * hfac
    body[..., 2] = 0.22 + 0.12 * hfac
    warm = np.array([1.0, 0.52, 0.55], np.float32)
    moon = np.array([0.62, 0.66, 0.95], np.float32)
    uw = np.clip(under * 3.0, 0, 1)[..., None] * (0.35 + 0.65 * hfac[..., None])
    tw = np.clip(top * 2.5, 0, 1)[..., None] * 0.5
    col = body * (1 - uw) + warm * uw
    col = col * (1 - tw) + moon * tw
    # interior variation
    col *= (0.85 + 0.3 * n2[..., None])
    rgba = np.concatenate([col, (dens ** 0.8)[..., None] * 0.92], axis=2)
    up = _ndi.zoom(rgba, (ds, ds, 1), order=1)[:SKY_CH, :SKY_CW]
    return _np_to_surface(up)


def _sky_clouds_a():
    return _cloud_layer(31, 0.5, [(120, 60, 1.0), (360, 90, 0.85), (780, 110, 0.7)])


def _sky_clouds_b():
    return _cloud_layer(47, 0.55, [(60, 45, 1.0), (240, 80, 0.9), (560, 140, 0.8), (1000, 180, 0.6)])


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
        if moon:   # moonlight bleeding over nearby clouds
            _glow(ctx, mx, my, mr * 4.5, (0.85, 0.88, 1.0), 0.22 * clamp(clouds * 2))


# ======================================================================
#  CITY SKYLINE (Tokyo bay side)
# ======================================================================
CITY_W, CITY_H = 3840, 520       # strip; base (ground) at row CITY_H - CITY_PAD
CITY_PAD = 40
_CITY = {}


def _city_build():
    """Returns dict(sil, sil_tower, win, beacons[list], mono_y)."""
    base = CITY_H - CITY_PAD
    r = rng(1234)
    rows = [  # (count-ish spacing, height range, width range, colour, window alpha, win density)
        dict(sp=(30, 80), h=(25, 110), w=(40, 120), col=(0.30, 0.18, 0.38), wa=0.35, wd=0.25),
        dict(sp=(40, 110), h=(50, 250), w=(35, 110), col=(0.17, 0.11, 0.28), wa=0.7, wd=0.4),
        dict(sp=(50, 140), h=(40, 190), w=(50, 150), col=(0.075, 0.06, 0.16), wa=1.0, wd=0.45),
    ]
    sil, c = _surf(CITY_W, CITY_H)
    silT, cT = _surf(CITY_W, CITY_H)       # rows 1-2 (in front of the towers)
    tows, cTow = _surf(CITY_W, CITY_H)
    win, cw = _surf(CITY_W, CITY_H)
    beacons = []
    tower_x, tree_x = 1320.0, 2980.0

    def building(cc, x, bw, bh, col, rowi, draw_w):
        top = base - bh
        cc.set_source_rgb(*col)
        kind = r.random()
        cc.rectangle(x, top, bw, bh + CITY_PAD)
        cc.fill()
        # rooftop details
        if kind < 0.25:           # stepped top
            cc.rectangle(x + bw * 0.2, top - bh * 0.08, bw * 0.6, bh * 0.08 + 1); cc.fill()
        elif kind < 0.35 and bh > 120:   # antenna
            cc.rectangle(x + bw * 0.5 - 1.5, top - 40, 3, 40); cc.fill()
            beacons.append((x + bw * 0.5, top - 40, rowi))
        elif kind < 0.45:         # slanted roof
            cc.move_to(x, top); cc.line_to(x + bw, top - bh * 0.1); cc.line_to(x + bw, top); cc.close_path(); cc.fill()
        if bh > 150 and r.random() < 0.6:
            beacons.append((x + r.uniform(4, bw - 4), top - 2, rowi))
        # faint lit edge (rim from city glow)
        cc.set_source_rgba(0.9, 0.5, 0.6, 0.08 + 0.05 * rowi)
        cc.rectangle(x, top, 2, bh); cc.fill()
        return top

    def windows(x, bw, bh, rowi, R):
        if not draw_windows:
            return
        top = base - bh
        cellw = r.choice([6, 7, 8, 10]) - rowi * 0
        cellh = r.choice([7, 9, 10])
        ww, wh = cellw * 0.55, cellh * 0.5
        style = r.random()
        dens = R["wd"] * r.uniform(0.5, 1.4)
        palette = [(1.0, 0.82, 0.52), (1.0, 0.9, 0.7), (0.85, 0.92, 1.0), (0.7, 0.85, 1.0)]
        pc = r.choice(palette)
        yy = top + 6
        while yy < base - 4:
            xx = x + 4
            rowlit = r.random() < 0.85
            while xx < x + bw - 4:
                if rowlit and r.random() < dens:
                    col = pc if r.random() < 0.8 else r.choice(palette)
                    cw.set_source_rgba(*col, R["wa"] * r.uniform(0.45, 1.0))
                    if style < 0.2:   # horizontal strip windows (offices)
                        cw.rectangle(xx, yy, cellw + 0.5, wh)
                    else:
                        cw.rectangle(xx, yy, ww, wh)
                    cw.fill()
                xx += cellw
            yy += cellh

    draw_windows = True
    for rowi, R in enumerate(rows):
        x = -20.0
        while x < CITY_W + 20:
            bw = r.uniform(*R["w"])
            bh = r.uniform(*R["h"])
            if r.random() < 0.08 and rowi > 0:
                bh *= 1.6        # occasional high-rise
            # tallest cluster around tower & a "Shiodome/Shinagawa" cluster
            for cx0, amp in ((700, 1.4), (2300, 1.5), (3500, 1.3)):
                bh *= 1 + (amp - 1) * math.exp(-((x - cx0) / 350) ** 2)
            building(c if rowi == 0 else cT, x, bw, bh, R["col"], rowi, True)
            windows(x, bw, bh, rowi, R)
            x += bw + r.uniform(-bw * 0.4, R["sp"][1] * 0.3)
        if rowi == 0:
            # ---- landmark towers (separate, non-repeating layer) ----
            _tokyo_tower(cTow, tower_x, base, 400)
            _skytree(cTow, tree_x, base, 330)
            # glow of tower into window layer (so it's affected by lights)
    # haze at the base of the skyline (light pollution / sea mist), painted over both
    for cc in (cT,):
        g = cairo.LinearGradient(0, base - 160, 0, CITY_H)
        g.add_color_stop_rgba(0, 0.9, 0.45, 0.55, 0)
        g.add_color_stop_rgba(0.7, 0.85, 0.45, 0.55, 0.22)
        g.add_color_stop_rgba(1, 0.9, 0.5, 0.55, 0.35)
        cc.rectangle(0, base - 160, CITY_W, 200); cc.set_source(g); cc.fill()
    # window glow bloom: blurred copy under sharp windows
    wblur = _blur_surface(win, 3.0)
    w2, cw2 = _surf(CITY_W, CITY_H)
    cw2.set_source_surface(wblur, 0, 0); cw2.paint_with_alpha(0.9)
    cw2.set_source_surface(win, 0, 0); cw2.paint()
    # neon signs on some roofs
    for i in range(14):
        x = r.uniform(0, CITY_W); y = base - r.uniform(40, 160)
        col = r.choice([PAL["neon_pink"], PAL["neon_cyan"], (1.0, 0.6, 0.2), (1, 1, 1)])
        _glow(cw2, x, y, 22, col, 0.35)
        cw2.set_source_rgba(*col, 0.9); cw2.rectangle(x - 8, y - 3, 16, 6); cw2.fill()
    # elevated expressway / monorail beam across the base (in front of everything)
    mono_y = base - 34
    for cc in (cT,):
        cc.set_source_rgb(0.05, 0.045, 0.1)
        cc.rectangle(0, mono_y, CITY_W, 7); cc.fill()
        for px in range(0, CITY_W, 90):
            cc.rectangle(px, mono_y + 7, 6, base - mono_y); cc.fill()
        # expressway lower with sodium lights
        cc.rectangle(0, base - 12, CITY_W, 5); cc.fill()
    for px in range(20, CITY_W, 46):
        _glow(cw2, px, base - 13, 10, (1.0, 0.7, 0.35), 0.5)
        cw2.set_source_rgba(1.0, 0.85, 0.6, 0.9); cw2.arc(px, base - 13, 1.4, 0, TAU); cw2.fill()
    return dict(far=sil, near=silT, tows=tows, win=w2, beacons=beacons, mono_y=mono_y, tower_x=tower_x, tree_x=tree_x)


def _tokyo_tower(c, x, base, h):
    """Tokyo Tower: orange-lit lattice with white top & glow."""
    orange = (1.0, 0.45, 0.12)
    _glow(c, x, base - h * 0.45, h * 0.75, (1.0, 0.45, 0.2), 0.22)
    c.save()
    top = base - h
    wb = h * 0.34
    # legs curves
    def leg_x(f, side):   # f 0 base .. 1 top
        return x + side * (wb * 0.5 * (1 - f) ** 2.1 + 3)
    for side in (-1, 1):
        c.move_to(leg_x(0, side), base)
        for i in range(1, 41):
            f = i / 40
            c.line_to(leg_x(f, side), base - f * (h - 60))
        c.set_line_width(4.5); c.set_source_rgb(*orange); c.stroke()
    # lattice
    c.set_line_width(1.2)
    for i in range(18):
        f0, f1 = i / 18 * 0.88, (i + 1) / 18 * 0.88
        y0, y1 = base - f0 * (h - 60), base - f1 * (h - 60)
        c.move_to(leg_x(f0, -1), y0); c.line_to(leg_x(f1, 1), y1)
        c.move_to(leg_x(f0, 1), y0); c.line_to(leg_x(f1, -1), y1)
    c.set_source_rgba(1.0, 0.62, 0.3, 0.85); c.stroke()
    # base arch
    c.set_source_rgb(*orange)
    c.move_to(leg_x(0, -1), base); c.curve_to(x - wb * 0.2, base - h * 0.14, x + wb * 0.2, base - h * 0.14, leg_x(0, 1), base)
    c.set_line_width(3); c.stroke()
    # decks
    for f, dw, dh in ((0.36, 0.13, 10), (0.62, 0.07, 7)):
        yy = base - f * h
        c.set_source_rgb(1.0, 0.9, 0.75)
        c.rectangle(x - h * dw * 0.5, yy - dh, h * dw, dh); c.fill()
        c.set_source_rgba(1.0, 0.95, 0.8, 0.6)
        c.rectangle(x - h * dw * 0.5 - 2, yy - dh - 2, h * dw + 4, 2); c.fill()
    # antenna
    c.set_source_rgb(1.0, 0.95, 0.9)
    c.move_to(x - 2.5, base - (h - 60)); c.line_to(x - 0.7, top); c.line_to(x + 0.7, top); c.line_to(x + 2.5, base - (h - 60))
    c.close_path(); c.fill()
    c.restore()


def _skytree(c, x, base, h):
    """Tokyo Skytree (distant, hazy) with blue/purple 'Iki' lighting."""
    col = (0.55, 0.62, 1.0)
    _glow(c, x, base - h * 0.6, h * 0.5, (0.5, 0.5, 1.0), 0.14)
    c.save()
    c.move_to(x - 16, base)
    c.curve_to(x - 9, base - h * 0.4, x - 4, base - h * 0.7, x - 2.5, base - h * 0.92)
    c.line_to(x + 2.5, base - h * 0.92)
    c.curve_to(x + 4, base - h * 0.7, x + 9, base - h * 0.4, x + 16, base)
    c.close_path()
    g = cairo.LinearGradient(0, base, 0, base - h)
    g.add_color_stop_rgba(0, 0.35, 0.3, 0.7, 0.8)
    g.add_color_stop_rgba(1, 0.75, 0.8, 1.0, 0.95)
    c.set_source(g); c.fill()
    for f, dw in ((0.54, 14), (0.76, 9)):
        c.set_source_rgba(0.9, 0.95, 1.0, 0.95)
        c.rectangle(x - dw, base - h * f - 5, dw * 2, 6); c.fill()
    c.set_source_rgba(*col, 0.9)
    c.rectangle(x - 1, base - h, 2, h * 0.09); c.fill()
    c.restore()


def _city():
    if not _CITY:
        _CITY.update(_disk_dict("city", _city_build))
    return _CITY


def draw_city(ctx, t, base_y, cam_x=0.0, parallax=0.05, scale=1.0, lights=1.0, tower=True,
              monorail=True, haze=1.0):
    """Tokyo skyline silhouette (tileable) with lit windows, blinking red aircraft
    beacons, Tokyo Tower & Skytree (tower=True), elevated monorail with a moving train.
    base_y = screen y of the skyline's ground line."""
    C = _city()
    off = cam_x * parallax
    top = base_y - (CITY_H - CITY_PAD) * scale

    # light pollution glow above skyline
    if haze > 0:
        g = cairo.LinearGradient(0, top - 60 * scale, 0, base_y)
        g.add_color_stop_rgba(0, 1.0, 0.55, 0.5, 0)
        g.add_color_stop_rgba(1, 1.0, 0.6, 0.5, 0.18 * haze)
        ctx.save(); ctx.rectangle(-200, top - 60 * scale, W + 400, base_y - top + 60 * scale)
        ctx.set_source(g); ctx.fill(); ctx.restore()
    _paint_strip(ctx, C["far"], off, top, scale)
    if tower:   # landmarks: one instance only (no tiling)
        _paint_strip(ctx, C["tows"], off, top, scale, extend=cairo.EXTEND_NONE)
    _paint_strip(ctx, C["near"], off, top, scale)
    if lights > 0:
        _paint_strip(ctx, C["win"], off, top, scale, alpha=clamp(lights))
    # beacons & monorail (dynamic)
    ctx.save()
    ctx.rectangle(-200, top - 200, W + 400, CITY_H * scale + 200); ctx.clip()
    if lights > 0:
        for i, (bx, by, row) in enumerate(C["beacons"]):
            ph = (t * 0.8 + _hash(i, 3)) % 1.0
            on = 1.0 if ph < 0.35 else 0.0
            if on <= 0:
                continue
            k = 1.0 - ph / 0.35
            sx = ((bx * scale - off) % (CITY_W * scale))
            for sxx in (sx, sx - CITY_W * scale, sx + CITY_W * scale):
                if -20 < sxx < W + 20:
                    sy = top + by * scale
                    a = lights * (0.5 + 0.5 * k) * (0.5 + 0.25 * row)
                    _glow(ctx, sxx, sy, 12 * scale + 4, (1.0, 0.12, 0.1), a * 0.8)
                    ctx.set_source_rgba(1, 0.35, 0.3, a); ctx.arc(sxx, sy, 1.6 * scale + 0.6, 0, TAU); ctx.fill()
        if tower:   # tower top beacons
            for k2, (tx, ty) in enumerate(((C["tower_x"], CITY_H - CITY_PAD - 400), (C["tree_x"], CITY_H - CITY_PAD - 330))):
                if (t * 0.7 + k2 * 0.5) % 1.0 < 0.4:
                    sx = tx * scale - off
                    for sxx in (sx,):
                        if -20 < sxx < W + 20:
                            _glow(ctx, sxx, top + ty * scale, 16 * scale + 4, (1, 0.15, 0.1), 0.9 * lights)
    if monorail:
        my = top + C["mono_y"] * scale
        sp = 160.0        # strip px / s
        for j, (dirn, ph0) in enumerate(((1, 0.1), (-1, 0.6))):
            tx = ((t * sp * dirn + ph0 * CITY_W) % CITY_W)
            for sxx in (tx * scale - off % (CITY_W * scale), tx * scale - off % (CITY_W * scale) + CITY_W * scale):
                if -300 < sxx < W + 300:
                    L = 150 * scale
                    hgt = 8 * scale
                    ctx.set_source_rgb(0.12, 0.13, 0.2)
                    ctx.rectangle(sxx, my - hgt - 1, L, hgt); ctx.fill()
                    ctx.set_source_rgba(0.95, 0.95, 0.85, 0.9 * lights)
                    for q in range(12):
                        ctx.rectangle(sxx + (4 + q * 12) * scale, my - hgt + 2 * scale, 7 * scale, 3 * scale)
                    ctx.fill()
                    _glow(ctx, sxx + (L if dirn > 0 else 0), my - hgt / 2, 16 * scale + 3, (1, 1, 0.9), 0.5 * lights)
    ctx.restore()


# ======================================================================
#  CROWD helpers
# ======================================================================
_CLOTH = [(0.16, 0.16, 0.24), (0.32, 0.13, 0.17), (0.12, 0.22, 0.28), (0.38, 0.36, 0.34),
          (0.08, 0.08, 0.1), (0.46, 0.40, 0.27), (0.62, 0.62, 0.66), (0.22, 0.28, 0.2),
          (0.55, 0.25, 0.2), (0.2, 0.22, 0.4)]
_HAIR = [(0.06, 0.05, 0.07), (0.12, 0.08, 0.06), (0.2, 0.14, 0.1), (0.35, 0.33, 0.33), (0.08, 0.07, 0.1)]


_HEADS = None


def _mute(col, tone, k):
    return tuple(col[i] * (1 - k) + tone[i] * k for i in range(3))


def _tiny_crowd_row(c, r, x0, x1, y, hr, light, dens=1.0, phones=None, tint=(1, 1, 1),
                    tone=(0.30, 0.22, 0.28), mute=0.55):
    """One row of tiny spectators (heads + shoulders). y = shoulder line."""
    x = x0 + r.uniform(0, hr * 2)
    while x < x1:
        if r.random() < dens:
            cl = _mute(r.choice(_CLOTH), tone, mute)
            lit = light * r.uniform(0.85, 1.1)
            cc = tuple(min(1, cl[i] * lit * tint[i]) for i in range(3))
            sh = hr * r.uniform(1.5, 1.9)
            c.set_source_rgb(*cc)
            c.move_to(x - sh, y + hr * 3)
            c.curve_to(x - sh, y - hr * 0.2, x + sh, y - hr * 0.2, x + sh, y + hr * 3)
            c.close_path(); c.fill()
            hy = y - hr * 0.9 + r.uniform(-0.4, 0.4) * hr
            if _HEADS is not None and r.random() < 0.2:
                _HEADS.append((x, hy))
            skin = _mute(PAL["skin"] if r.random() < 0.55 else PAL["skin_shadow"], tone, mute * 0.6)
            hc = r.choice(_HAIR)
            c.set_source_rgb(*(min(1, hc[i] * lit * 1.3) for i in range(3)))
            c.arc(x, hy - hr * 0.15, hr * 1.04, 0, TAU); c.fill()
            c.set_source_rgb(*(min(1, skin[i] * lit * 0.75 * tint[i]) for i in range(3)))
            c.arc(x, hy + hr * 0.18, hr * 0.82, 0, TAU); c.fill()
            if r.random() < 0.10:      # raised arm
                c.set_source_rgb(*cc)
                c.set_line_width(hr * 0.8)
                side = r.choice((-1, 1))
                c.move_to(x + side * sh * 0.7, y + hr)
                c.line_to(x + side * sh * 1.1, y - hr * 3.2); c.stroke()
                if phones is not None and r.random() < 0.6:
                    phones.append((x + side * sh * 1.1, y - hr * 3.5))
            elif phones is not None and r.random() < 0.05:
                phones.append((x + r.uniform(-hr, hr), y - hr * 0.2))
        x += hr * r.uniform(2.1, 2.9)


def _person(c, r, x, base, hgt, light=1.0, tint=(1, 1, 1), phones=None, arms_p=0.25, rim=(1.0, 0.85, 0.65)):
    """Standing spectator silhouette (waist-up visible above a rail). base = feet line."""
    cl = _mute(r.choice(_CLOTH), (0.16, 0.12, 0.2), 0.5)
    lit = light * r.uniform(0.85, 1.1)
    cc = tuple(min(1, cl[i] * lit * tint[i]) for i in range(3))
    hr = hgt * 0.11
    sw = hgt * r.uniform(0.17, 0.22)
    neck = base - hgt + hr * 2.1
    c.set_source_rgb(*cc)
    c.move_to(x - sw, base)
    c.line_to(x - sw, neck + hr * 1.2)
    c.curve_to(x - sw, neck, x - sw * 0.5, neck - hr * 0.1, x, neck - hr * 0.1)
    c.curve_to(x + sw * 0.5, neck - hr * 0.1, x + sw, neck, x + sw, neck + hr * 1.2)
    c.line_to(x + sw, base); c.close_path(); c.fill()
    hy = neck - hr * 0.9
    skin = _mute(PAL["skin"] if r.random() < 0.6 else PAL["skin_shadow"], (0.3, 0.2, 0.3), 0.35)
    hc = r.choice(_HAIR)
    c.set_source_rgb(*(min(1, hc[i] * lit * 1.2) for i in range(3)))
    c.arc(x, hy - hr * 0.12, hr * 1.06, 0, TAU); c.fill()
    c.set_source_rgb(*(min(1, skin[i] * lit * 0.62 * tint[i]) for i in range(3)))
    c.save(); c.translate(x, hy + hr * 0.2); c.scale(0.86, 0.9); c.arc(0, 0, hr, 0, TAU); c.restore(); c.fill()
    if r.random() < 0.2:   # cap
        c.set_source_rgb(*_mute(r.choice(_CLOTH), (0.2, 0.15, 0.25), 0.3))
        c.arc(x, hy - hr * 0.1, hr * 1.1, math.pi, TAU); c.fill()
        c.rectangle(x - hr * 1.1, hy - hr * 0.2, hr * 2.2, hr * 0.3); c.fill()
    # rim light on the top edge (floodlights)
    c.set_source_rgba(*rim, 0.55 * light)
    c.set_line_width(max(1.0, hr * 0.28))
    c.arc(x, hy, hr * 0.95, math.pi * 1.1, math.pi * 1.7); c.stroke()
    c.move_to(x - sw * 0.9, neck + hr * 0.4); c.curve_to(x - sw * 0.6, neck, x - sw * 0.3, neck, x - hr * 0.6, neck); c.stroke()
    if r.random() < arms_p:
        side = r.choice((-1, 1))
        c.set_source_rgb(*cc)
        c.set_line_width(hr * 0.9); c.set_line_cap(cairo.LINE_CAP_ROUND)
        ex = x + side * sw * r.uniform(0.9, 1.6)
        ey = neck - hgt * r.uniform(0.35, 0.55)
        c.move_to(x + side * sw * 0.8, neck + hr * 0.6)
        c.curve_to(x + side * sw * 1.3, neck, ex, ey + hr * 2, ex, ey); c.stroke()
        c.set_source_rgb(*(min(1, skin[i] * lit * 0.6) for i in range(3)))
        c.arc(ex, ey, hr * 0.55, 0, TAU); c.fill()
        if phones is not None and r.random() < 0.55:
            phones.append((ex, ey - hr * 0.9, hr))
        c.set_line_cap(cairo.LINE_CAP_BUTT)


# ======================================================================
#  RACE SIDE TRACKING SHOT  (bg + fg)
# ======================================================================
GS_W, GS_H, GS_BASE = 5760, 600, 580     # grandstand strip, ground row
P_CITY, P_FARTOW, P_GS, P_TOW, P_CROWD, P_ORAIL = 0.03, 0.18, 0.5, 0.64, 0.72, 0.82
_SIDE = {}


def _gs_main(c, r, x0, x1, hgt, phones, sign=None):
    base = GS_BASE
    top = base - hgt
    w = x1 - x0
    # structural back mass
    c.set_source_rgb(0.07, 0.06, 0.13)
    c.rectangle(x0 + 10, top + 20, w - 20, hgt - 20); c.fill()
    # ---- upper tier (under roof) ----
    ut0, ut1 = top + 34, top + 34 + hgt * 0.32
    g = _lin(c, 0, ut0, 0, ut1, [(0, (0.55, 0.36, 0.28)), (0.5, (0.42, 0.28, 0.25)), (1, (0.26, 0.18, 0.2))])
    c.set_source(g); c.rectangle(x0 + 14, ut0, w - 28, ut1 - ut0); c.fill()
    rows = int((ut1 - ut0 - 6) / 11)
    for k in range(rows):
        y = ut0 + 12 + k * 11
        light = 0.75 + 0.55 * k / max(1, rows - 1)
        _tiny_crowd_row(c, r, x0 + 18, x1 - 18, y, 2.6, light, 0.9, phones, tint=(1.15, 0.95, 0.85),
                        tone=(0.34, 0.22, 0.24), mute=0.6)
    _terrace_structure(c, r, x0 + 14, x1 - 14, ut0, ut1, 11, rows, 0.5)
    # upper tier front parapet
    c.set_source_rgb(0.85, 0.82, 0.8)
    c.rectangle(x0 + 12, ut1, w - 24, 5); c.fill()
    c.set_source_rgb(0.25, 0.2, 0.28)
    c.rectangle(x0 + 12, ut1 + 5, w - 24, 10); c.fill()
    # ---- glass band ----
    gb0, gb1 = ut1 + 15, ut1 + 15 + hgt * 0.24
    g = _lin(c, 0, gb0, 0, gb1, [(0, (1.0, 0.86, 0.6)), (0.6, (1.0, 0.72, 0.45)), (1, (0.85, 0.5, 0.35))])
    c.set_source(g); c.rectangle(x0 + 14, gb0, w - 28, gb1 - gb0); c.fill()
    # interior silhouettes
    xx = x0 + 20
    while xx < x1 - 20:
        if r.random() < 0.55:
            hh = r.uniform(22, 32)
            c.set_source_rgba(0.35, 0.2, 0.18, r.uniform(0.35, 0.7))
            c.arc(xx, gb1 - hh, 4.2, 0, TAU); c.fill()
            c.rectangle(xx - 5.5, gb1 - hh + 4, 11, hh - 4); c.fill()
        xx += r.uniform(8, 26)
    # ceiling lights inside
    for xx in np.arange(x0 + 30, x1 - 20, 44):
        c.set_source_rgba(1, 1, 0.95, 0.9); c.rectangle(xx, gb0 + 3, 18, 2.5); c.fill()
    # mullions
    c.set_source_rgba(0.12, 0.09, 0.14, 0.85)
    for xx in np.arange(x0 + 14, x1 - 14, 62):
        c.rectangle(xx, gb0, 3, gb1 - gb0); c.fill()
    c.rectangle(x0 + 14, gb0 + (gb1 - gb0) * 0.42, w - 28, 2); c.fill()
    # glass reflections (diagonal sheen)
    c.save(); c.rectangle(x0 + 14, gb0, w - 28, gb1 - gb0); c.clip()
    for xx in np.arange(x0 - 200, x1, 420):
        g = _lin(c, xx, 0, xx + 140, 0, [(0, (1, 1, 1, 0)), (0.5, (1, 1, 1, 0.16)), (1, (1, 1, 1, 0))])
        c.set_source(g)
        c.move_to(xx, gb1); c.line_to(xx + 90, gb0); c.line_to(xx + 190, gb0); c.line_to(xx + 100, gb1); c.fill()
    c.restore()
    # floor slab
    c.set_source_rgb(0.9, 0.88, 0.86); c.rectangle(x0 + 8, gb1, w - 16, 6); c.fill()
    c.set_source_rgb(0.2, 0.16, 0.24); c.rectangle(x0 + 8, gb1 + 6, w - 16, 8); c.fill()
    # ---- lower terraces ----
    lt0, lt1 = gb1 + 14, base - 34
    g = _lin(c, 0, lt0, 0, lt1, [(0, (0.5, 0.36, 0.34)), (1, (0.66, 0.5, 0.42))])
    c.set_source(g); c.rectangle(x0 + 10, lt0, w - 20, lt1 - lt0); c.fill()
    rows = int((lt1 - lt0 - 8) / 13)
    for k in range(rows):
        y = lt0 + 14 + k * 13
        _tiny_crowd_row(c, r, x0 + 12, x1 - 12, y, 3.2, 1.1 + k * 0.05, 0.93, phones, tint=(1.05, 1.0, 0.95),
                        tone=(0.42, 0.32, 0.36), mute=0.55)
    _terrace_structure(c, r, x0 + 10, x1 - 10, lt0, lt1, 13, rows, 0.35)
    # apron wall with ad boards
    c.set_source_rgb(0.12, 0.1, 0.18); c.rectangle(x0, lt1, w, base - lt1 + 30); c.fill()
    _led_ribbon(c, r, x0 + 6, x1 - 6, lt1 + 6, 20)
    # ---- roof ----
    c.set_source_rgb(0.05, 0.045, 0.09)
    c.move_to(x0 - 30, top + 10); c.line_to(x1 + 30, top + 10); c.line_to(x1 + 20, top + 36); c.line_to(x0 - 20, top + 36)
    c.close_path(); c.fill()
    c.set_source_rgb(0.1, 0.09, 0.16); c.rectangle(x0 + 30, top - 10, w - 60, 22); c.fill()   # upper roof block
    # roof edge highlight
    c.set_source_rgba(0.95, 0.92, 1.0, 0.9); c.rectangle(x0 - 30, top + 9, w + 60, 2.5); c.fill()
    c.set_source_rgba(0.8, 0.75, 0.9, 0.5); c.rectangle(x0 + 30, top - 10, w - 60, 1.5); c.fill()
    # downlights under roof
    for xx in np.arange(x0 - 10, x1 + 10, 34):
        _glow(c, xx, top + 38, 18, (1.0, 0.85, 0.6), 0.55)
        c.set_source_rgb(1, 0.97, 0.9); c.rectangle(xx - 4, top + 35, 8, 2.5); c.fill()
    # columns
    c.set_source_rgb(0.1, 0.09, 0.15)
    for xx in np.arange(x0 + 60, x1 - 30, 240):
        c.rectangle(xx, top + 36, 6, ut1 - top - 36); c.fill()
    if sign:
        _neon_text(c, sign, (x0 + x1) / 2, top - 22, 44)


def _led_ribbon(c, r, x0, x1, y, h):
    """Glowing LED ribbon board (cyan/white text-like dashes on dark)."""
    c.set_source_rgb(0.03, 0.03, 0.07); c.rectangle(x0, y, x1 - x0, h); c.fill()
    g = _lin(c, 0, y, 0, y + h, [(0, (0.2, 0.6, 1.0, 0.25)), (0.5, (0.2, 0.6, 1.0, 0.05)), (1, (0.2, 0.6, 1.0, 0.25))])
    c.set_source(g); c.rectangle(x0, y, x1 - x0, h); c.fill()
    xx = x0 + 10
    while xx < x1 - 30:
        seg = r.uniform(18, 60)
        col = r.choice([(0.45, 0.95, 1.0), (1, 1, 1), (0.45, 0.95, 1.0), (1.0, 0.75, 0.35)])
        c.set_source_rgba(*col, 0.9)
        c.rectangle(xx, y + h * 0.3, seg, h * 0.4); c.fill()
        xx += seg + r.uniform(5, 16)
        if r.random() < 0.08:
            xx += 40
    c.set_source_rgba(0.8, 0.9, 1, 0.8); c.rectangle(x0, y, x1 - x0, 1.2); c.rectangle(x0, y + h - 1.2, x1 - x0, 1.2); c.fill()


def _neon_text(c, s, x, y, size, col=None):
    col = col or PAL["neon_pink"]
    c.save()
    c.select_font_face("AnimeDela"); c.set_font_size(size)
    xb, yb, tw, th, xa, ya = c.text_extents(s)
    # sign backing frame
    c.set_source_rgba(0.06, 0.05, 0.1, 1); c.rectangle(x - xa / 2 - 18, y - size * 0.95, xa + 36, size * 1.2); c.fill()
    for w_, a_ in ((16, 0.10), (9, 0.18), (4, 0.4)):
        c.move_to(x - xa / 2, y); c.text_path(s)
        c.set_line_width(w_); c.set_source_rgba(*col, a_); c.stroke()
    c.move_to(x - xa / 2, y); c.text_path(s)
    c.set_source_rgba(1, 0.85, 0.92, 1); c.fill()
    c.restore()


def _terrace_structure(c, r, x0, x1, t0, t1, row_h, rows, shade_top=0.45):
    """Aisles, walkways and under-roof shading over a crowd block."""
    # horizontal walkways
    for k in range(5, rows, 6):
        y = t0 + 12 + k * row_h - row_h * 0.35
        c.set_source_rgba(0.12, 0.08, 0.14, 0.8); c.rectangle(x0, y + 2, x1 - x0, 5); c.fill()
        c.set_source_rgba(0.95, 0.85, 0.8, 0.55); c.rectangle(x0, y, x1 - x0, 2.2); c.fill()
    # vertical aisles (stairs)
    xx = x0 + r.uniform(60, 160)
    while xx < x1 - 40:
        g = _lin(c, 0, t0, 0, t1, [(0, (0.45, 0.36, 0.38)), (1, (0.78, 0.68, 0.62))])
        c.set_source(g); c.rectangle(xx, t0, 9, t1 - t0); c.fill()
        c.set_source_rgba(0.2, 0.14, 0.2, 0.6)
        for yy in np.arange(t0 + 3, t1, 4.0):
            c.rectangle(xx, yy, 9, 1.0)
        c.fill()
        c.set_source_rgba(1, 0.95, 0.85, 0.4); c.rectangle(xx - 1, t0, 1.2, t1 - t0); c.fill()
        xx += r.uniform(200, 280)
    # shading: darker under the roof
    g = _lin(c, 0, t0, 0, t1, [(0, (0.06, 0.03, 0.1, shade_top)), (0.45, (0.06, 0.03, 0.1, shade_top * 0.25)), (1, (0.06, 0.03, 0.1, 0))])
    c.set_source(g); c.rectangle(x0, t0, x1 - x0, t1 - t0); c.fill()


def _gs_wing(c, r, x0, x1, hgt, phones):
    base = GS_BASE
    top = base - hgt
    w = x1 - x0
    c.set_source_rgb(0.08, 0.07, 0.14); c.rectangle(x0, top + 20, w, hgt); c.fill()
    # curved roof
    c.set_source_rgb(0.06, 0.05, 0.1)
    c.move_to(x0 - 20, top + 30); c.curve_to(x0 + w * 0.3, top - 16, x1 - w * 0.3, top - 16, x1 + 20, top + 30)
    c.line_to(x1 + 20, top + 44); c.curve_to(x1 - w * 0.3, top + 2, x0 + w * 0.3, top + 2, x0 - 20, top + 44)
    c.close_path(); c.fill()
    c.move_to(x0 - 20, top + 30); c.curve_to(x0 + w * 0.3, top - 16, x1 - w * 0.3, top - 16, x1 + 20, top + 30)
    c.set_source_rgba(0.9, 0.9, 1.0, 0.8); c.set_line_width(2.2); c.stroke()
    for xx in np.arange(x0, x1, 30):
        f = (xx - x0) / w
        yy = top + 36 - 18 * math.sin(math.pi * f)
        _glow(c, xx, yy + 4, 14, (1.0, 0.85, 0.6), 0.5)
    t0, t1 = top + 48, base - 30
    g = _lin(c, 0, t0, 0, t1, [(0, (0.58, 0.40, 0.32)), (1, (0.62, 0.48, 0.42))])
    c.set_source(g); c.rectangle(x0 + 8, t0, w - 16, t1 - t0); c.fill()
    rows = int((t1 - t0 - 6) / 12)
    for k in range(rows):
        _tiny_crowd_row(c, r, x0 + 10, x1 - 10, t0 + 12 + k * 12, 3.0, 1.0 + 0.04 * k, 0.9, phones,
                        tone=(0.4, 0.3, 0.36), mute=0.55)
    _terrace_structure(c, r, x0 + 8, x1 - 8, t0, t1, 12, rows, 0.6)
    c.set_source_rgb(0.12, 0.1, 0.18); c.rectangle(x0, t1, w, 60); c.fill()
    c.set_source_rgb(0.85, 0.85, 0.9); c.rectangle(x0, t1, w, 3); c.fill()


def _tree_clump(c, r, cx, base, th, lamp_side=0):
    """Painterly dark tree: many small leaf blobs, cool top light + warm lamp rim."""
    blobs = []
    for k in range(26):
        f = r.random()
        bx = cx + r.gauss(0, 26) * (1 - f * 0.5)
        by = base - th * (0.25 + f * 0.75) + r.uniform(-8, 8)
        blobs.append((bx, by, r.uniform(9, 20) * (1.1 - f * 0.4)))
    blobs.sort(key=lambda b: -b[1])
    c.set_source_rgb(0.03, 0.04, 0.07)
    c.rectangle(cx - 3, base - th * 0.35, 6, th * 0.35); c.fill()
    for (bx, by, br) in blobs:
        g = cairo.RadialGradient(bx - br * 0.3, by - br * 0.5, 0, bx, by, br)
        g.add_color_stop_rgb(0, 0.10, 0.16, 0.19)
        g.add_color_stop_rgb(1, 0.035, 0.05, 0.08)
        c.set_source(g); c.arc(bx, by, br, 0, TAU); c.fill()
    for (bx, by, br) in blobs[-8:]:
        c.set_source_rgba(0.45, 0.55, 0.7, 0.28); c.set_line_width(1.6)
        c.arc(bx, by, br - 1, math.pi * 1.15, math.pi * 1.75); c.stroke()
    if lamp_side:
        for (bx, by, br) in blobs[:10]:
            c.set_source_rgba(1.0, 0.7, 0.4, 0.3); c.set_line_width(1.6)
            a0 = 0 if lamp_side > 0 else math.pi * 0.6
            c.arc(bx, by, br - 1, a0 - 0.6, a0 + 0.6); c.stroke()


def _gs_gap(c, r, x0, x1):
    base = GS_BASE
    lamps = list(np.arange(x0 + 40, x1 - 20, 110))
    xx = x0 - 10
    while xx < x1 + 10:
        side = 0
        for lx in lamps:
            if abs(lx - xx) < 60:
                side = 1 if lx > xx else -1
        _tree_clump(c, r, xx, base - 8, r.uniform(80, 150), side)
        xx += r.uniform(38, 64)
    c.set_source_rgb(0.04, 0.05, 0.08); c.rectangle(x0 - 40, base - 20, x1 - x0 + 80, 60); c.fill()
    for xx in lamps:
        c.set_source_rgb(0.1, 0.1, 0.15); c.rectangle(xx, base - 120, 3, 120); c.fill()
        _glow(c, xx + 1.5, base - 122, 46, (1.0, 0.8, 0.5), 0.6)
        c.set_source_rgb(1, 0.95, 0.85); c.arc(xx + 1.5, base - 122, 3, 0, TAU); c.fill()


def _build_grandstand():
    global _HEADS
    s, c = _surf(GS_W, GS_H)
    r = rng(2024)
    phones = []
    _HEADS = []
    layout = [("main", 1850, 470, "TWINKLE"), ("gap", 270, 0, None), ("wing", 1000, 330, None),
              ("gap", 330, 0, None), ("main", 1480, 430, None), ("gap", 230, 0, None), ("wing", 600, 300, None)]
    x = 0
    for kind, w, h, sign in layout:
        if kind == "main":
            _gs_main(c, r, x + 20, x + w - 20, h, phones, sign)
        elif kind == "wing":
            _gs_wing(c, r, x + 15, x + w - 15, h, phones)
        else:
            _gs_gap(c, r, x, x + w)
        x += w
    # phone screens (static, small)
    for p in phones:
        _glow(c, p[0], p[1], 7, (0.8, 0.9, 1.0), 0.6)
        c.set_source_rgb(0.9, 0.95, 1.0); c.rectangle(p[0] - 1.2, p[1] - 1.8, 2.4, 3.2); c.fill()
    # atmospheric haze: stands are ~100m away -> slight purple veil, stronger at base
    g = _lin(c, 0, 0, 0, GS_H, [(0, (0.35, 0.25, 0.5, 0.05)), (0.75, (0.45, 0.3, 0.5, 0.10)), (1, (0.6, 0.4, 0.5, 0.25))])
    c.set_operator(cairo.OPERATOR_ATOP)
    c.set_source(g); c.paint()
    c.set_operator(cairo.OPERATOR_OVER)
    heads = _HEADS; _HEADS = None
    s = _blur_surface(s, 0.85)       # depth of field: stands are ~100 m away
    return s, (phones, heads)


def _build_rail_crowd():
    RC_W, RC_H = 3000, 190
    base = 170
    s, c = _surf(RC_W, RC_H)
    r = rng(77)
    phones = []
    for row, (hgt, light, sp, dy) in enumerate(((62, 0.75, 17, -16), (70, 0.95, 19, -6), (78, 1.15, 22, 4))):
        x = r.uniform(0, 10)
        while x < RC_W:
            _person(c, r, x, base + dy + 10, hgt * r.uniform(0.88, 1.1), light, phones=phones, arms_p=0.22 + row * 0.04)
            x += sp * r.uniform(0.7, 1.4)
    # wrap seam: repeat left edge figures near right? simple fade trick: draw the leftmost 60px again at the right
    tmp = _surface_to_np(s)
    blend = np.linspace(0, 1, 60, dtype=np.float32)[None, :, None]
    tmp[:, -60:] = tmp[:, -60:] * (1 - blend) + tmp[:, :60] * blend
    s = _np_premul_to_surface(tmp)
    c = cairo.Context(s)
    for p in phones:
        x, y, hr = p
        _glow(c, x, y, hr * 3.5, (0.8, 0.9, 1.0), 0.7)
        c.set_source_rgb(0.92, 0.96, 1.0); c.rectangle(x - hr * 0.35, y - hr * 0.6, hr * 0.7, hr * 1.1); c.fill()
    return s, phones, base


def _build_outer_rail():
    OW, OH = 1500, 70
    s, c = _surf(OW, OH)
    top = 20
    # posts
    for px in range(0, OW, 150):
        g = _lin(c, px, 0, px + 7, 0, [(0, (0.98, 0.98, 1.0)), (1, (0.62, 0.62, 0.75))])
        c.set_source(g); c.rectangle(px, top + 6, 7, OH - top - 6); c.fill()
    # rail bar (rounded top)
    g = _lin(c, 0, top, 0, top + 12, [(0, (1, 1, 1)), (0.45, (0.94, 0.94, 0.98)), (1, (0.55, 0.55, 0.7))])
    c.set_source(g); c.rectangle(0, top, OW, 12); c.fill()
    c.set_source_rgba(1, 1, 1, 0.9); c.rectangle(0, top + 1, OW, 1.6); c.fill()
    # glow halo around bar (floodlit white rail pops)
    g = _lin(c, 0, top - 14, 0, top + 26, [(0, (1, 1, 1, 0)), (0.4, (1, 0.97, 0.9, 0.18)), (0.6, (1, 0.97, 0.9, 0.18)), (1, (1, 1, 1, 0))])
    c.set_source(g); c.rectangle(0, top - 14, OW, 40); c.fill()
    return s, top


def _build_dirt():
    TW, TH = 2400, 560
    rr = np.random.default_rng(5)
    yy = np.linspace(0, 1, TH, dtype=np.float32)[:, None]
    far = np.array([0.68, 0.53, 0.43], np.float32)
    mid = np.array([0.56, 0.41, 0.31], np.float32)
    near = np.array([0.34, 0.235, 0.18], np.float32)
    k = yy[..., None]
    base = np.where(k < 0.3, far + (mid - far) * (k / 0.3), mid + (near - mid) * ((k - 0.3) / 0.7))
    base = np.broadcast_to(base, (TH, TW, 3)).copy()
    ds = 2
    blot = _fbm2(TH // ds, TW // ds, (5, 18), 5, seed=51)
    streak = _fbm2(TH // ds, TW // ds, (90, 5), 3, seed=52)       # groomed harrow streaks along x
    blot = _ndi.zoom(blot, ds, order=1, mode="grid-wrap", grid_mode=True)[:TH, :TW]
    streak = _ndi.zoom(streak, ds, order=1, mode="grid-wrap", grid_mode=True)[:TH, :TW]
    # speckle: sparse dark clumps + light grains, softly blurred, scale grows toward viewer
    sp = rr.random((TH, TW)).astype(np.float32)
    dark = (sp < 0.05).astype(np.float32)
    lite = (sp > 0.965).astype(np.float32)
    dark = _ndi.gaussian_filter(dark, (0.9, 1.6), mode="wrap")
    lite = _ndi.gaussian_filter(lite, (0.6, 1.0), mode="wrap")
    fine = rr.random((TH, TW)).astype(np.float32)
    v = (0.9 + 0.22 * (blot - 0.5) + 0.16 * (streak - 0.5) + 0.07 * (fine - 0.5)
         - 0.9 * dark * (0.4 + 0.6 * yy) + 0.8 * lite * (1.0 - 0.5 * yy))
    img = base * v[..., None]
    rgba = np.concatenate([img, np.ones((TH, TW, 1), np.float32)], 2)
    return _np_to_surface(rgba), TW, TH


def _build_tower_sprite(scale=1.0):
    """Floodlight tower: lattice mast + lamp bank. Anchor: (AX, AY) = lamp-bank centre."""
    Wt, Ht = 900, 1500
    AX, AY = 450, 300
    s, c = _surf(Wt, Ht)
    # light cone (volumetric) down-right & down-left
    for ang, a in ((0.0, 0.07),):
        g = cairo.LinearGradient(AX, AY, AX, Ht)
        g.add_color_stop_rgba(0, 1, 0.95, 0.8, 0.16)
        g.add_color_stop_rgba(1, 1, 0.95, 0.8, 0.0)
        c.move_to(AX - 60, AY + 30); c.line_to(AX + 60, AY + 30); c.line_to(AX + 420, Ht); c.line_to(AX - 420, Ht)
        c.close_path(); c.set_source(g); c.fill()
    # mast (tapered lattice)
    mb = 22; mt = 9
    def mx(f, side):
        return AX + side * (mt + (mb - mt) * f)
    c.set_source_rgb(0.2, 0.19, 0.26)
    c.move_to(mx(0, -1), AY + 40); c.line_to(mx(1, -1), Ht); c.line_to(mx(1, 1), Ht); c.line_to(mx(0, 1), AY + 40); c.close_path()
    c.fill()
    c.set_source_rgba(0.55, 0.52, 0.6, 0.9); c.set_line_width(1.3)
    ys = np.linspace(AY + 40, Ht, 40)
    for i in range(len(ys) - 1):
        f0 = (ys[i] - AY - 40) / (Ht - AY - 40); f1 = (ys[i + 1] - AY - 40) / (Ht - AY - 40)
        c.move_to(mx(f0, -1), ys[i]); c.line_to(mx(f1, 1), ys[i + 1])
        c.move_to(mx(f0, 1), ys[i]); c.line_to(mx(f1, -1), ys[i + 1])
    c.stroke()
    c.set_source_rgba(1, 0.9, 0.75, 0.35); c.set_line_width(2)
    c.move_to(mx(0, 1), AY + 40); c.line_to(mx(1, 1), Ht); c.stroke()
    # big halo
    _glow(c, AX, AY, 440, FLOOD, 0.4)
    _glow(c, AX, AY, 220, FLOOD, 0.5)
    # god-ray spokes
    rr_ = rng(99)
    for i in range(22):
        a = rr_.uniform(0, TAU); L = rr_.uniform(180, 430); wdt = rr_.uniform(0.01, 0.03)
        g = cairo.RadialGradient(AX, AY, 40, AX, AY, L)
        g.add_color_stop_rgba(0, 1, 0.95, 0.85, 0.22); g.add_color_stop_rgba(1, 1, 0.95, 0.85, 0)
        c.set_source(g)
        c.move_to(AX, AY); c.arc(AX, AY, L, a - wdt, a + wdt); c.close_path(); c.fill()
    # lamp bank frame (slightly tilted down toward the track)
    bw, bh = 176, 100
    c.save(); c.translate(AX, AY); c.rotate(-0.04)
    c.set_source_rgb(0.1, 0.09, 0.14)
    c.rectangle(-bw / 2 - 7, -bh / 2 - 7, bw + 14, bh + 14); c.fill()
    c.set_source_rgba(0.6, 0.55, 0.6, 0.8); c.rectangle(-bw / 2 - 7, -bh / 2 - 7, bw + 14, 2); c.fill()
    for i in range(6):
        for j in range(4):
            lx = -bw / 2 + 15 + i * (bw - 30) / 5
            ly = -bh / 2 + 13 + j * (bh - 26) / 3
            c.set_source_rgb(0.2, 0.18, 0.2); c.arc(lx, ly, 12, 0, TAU); c.fill()
            g = cairo.RadialGradient(lx - 2, ly - 2, 0, lx, ly, 10)
            g.add_color_stop_rgb(0, 1, 1, 1); g.add_color_stop_rgb(0.6, 1.0, 0.97, 0.88); g.add_color_stop_rgb(1, 1.0, 0.8, 0.5)
            c.set_source(g); c.arc(lx, ly, 10, 0, TAU); c.fill()
    c.restore()
    for i in range(6):
        for j in range(4):
            lx = AX - bw / 2 + 15 + i * (bw - 30) / 5
            ly = AY - bh / 2 + 13 + j * (bh - 26) / 3
            _glow(c, lx, ly, 34, FLOOD_CORE, 0.35)
    _glow(c, AX, AY, 130, FLOOD_CORE, 0.55)
    # anamorphic streak
    g = cairo.LinearGradient(AX - 450, 0, AX + 450, 0)
    g.add_color_stop_rgba(0, 0.8, 0.85, 1, 0); g.add_color_stop_rgba(0.5, 0.95, 0.95, 1, 0.55); g.add_color_stop_rgba(1, 0.8, 0.85, 1, 0)
    c.set_source(g); c.rectangle(AX - 450, AY - 2.5, 900, 5); c.fill()
    return s, AX, AY


def _side():
    if not _SIDE:
        def build():
            gs, gph = _build_grandstand()
            rc, rph, rc_base = _build_rail_crowd()
            orl, orl_top = _build_outer_rail()
            dirt, TW, TH = _build_dirt()
            tow, AX, AY = _build_tower_sprite()
            return dict(gs=gs, gs_ph=gph, rc=rc, rc_ph=rph, rc_base=rc_base, orl=orl, orl_top=orl_top,
                        dirt=dirt, TW=TW, TH=TH, tow=tow, AX=AX, AY=AY)
        _SIDE.update(_disk_dict("side", build))
    return _SIDE


def _side_blur(key, radius):
    S = _side()
    k = key + "_b"
    if k not in S:
        S[k] = _cached(("sideblur", key, radius), lambda: _hblur_surface(S[key], radius, wrap=True))
    return S[k]


def _paint_blurmix(ctx, key, radius, blur, x_off, y, **kw):
    S = _side()
    if blur < 0.62:
        _paint_strip(ctx, S[key], x_off, y, **kw)
    if blur > 0.38:
        a = clamp((blur - 0.38) / 0.24)
        _paint_strip(ctx, _side_blur(key, radius), x_off, y, alpha=a * kw.pop("alpha", 1.0), **kw)


TOW_SP = 1350.0      # floodlight tower spacing (layer px)


def _side_layout(horizon_y, track_y):
    y_or = horizon_y + 0.56 * (track_y - horizon_y)
    return y_or


def draw_race_side_bg(ctx, t, cam_x, *, horizon_y=520, track_y=760, crowd=1.0, flash=0.0, blur=0.0,
                      moon=(1590, 96, 36), sky=True):
    """Side tracking-shot background (horses run right; cam_x in px, ~1400 px/s).
    Layers: sky -> city -> distant towers -> grandstand w/ crowd -> floodlight towers ->
    rail-side crowd -> outer rail -> scrolling dirt with floodlight sheen."""
    S = _side()
    blur = clamp(blur)
    y_or = _side_layout(horizon_y, track_y)
    if sky:
        draw_sky(ctx, t, horizon_y=horizon_y, stars=0.7, moon=moon, clouds=0.45, glow=1.0)
    draw_city(ctx, t, horizon_y, cam_x=cam_x, parallax=P_CITY, scale=0.5, lights=1.0, tower=True)
    # distant floodlight towers across the course (visible in stand gaps)
    ctx.save()
    tow = S["tow"]
    off = cam_x * P_FARTOW
    sp = 900.0
    for k in range(int((off - 400) // sp), int((off + W + 400) // sp) + 1):
        sx = k * sp - off + 200 * _hash(k, 8)
        sy = horizon_y - 150
        _blit(ctx, tow, sx - S["AX"] * 0.28, sy - S["AY"] * 0.28, alpha=0.8, scale=0.28)
    ctx.restore()
    # grandstand
    gs_y = y_or - 10 - GS_BASE
    _paint_blurmix(ctx, "gs", 50, blur, cam_x * P_GS, gs_y)
    # stand life: flickering flashes / phone lights
    _stand_sparkles(ctx, t, cam_x, gs_y, crowd, flash)
    # floodlight towers
    off = cam_x * P_TOW
    for k in range(int((off - 600) // TOW_SP), int((off + W + 600) // TOW_SP) + 1):
        sx = k * TOW_SP - off + 260
        base_y = y_or - 10
        flick = 0.97 + 0.03 * noise1(t * 7 + k, 4)
        if blur < 0.62:
            _blit(ctx, tow, sx - S["AX"], base_y - 600 - S["AY"], alpha=flick * (1 - clamp((blur - 0.38) / 0.24)))
        if blur > 0.38:
            if "tow_b" not in S:
                S["tow_b"] = _cached("tow_blur", lambda: _hblur_surface(S["tow"], 46, wrap=False))
            _blit(ctx, S["tow_b"], sx - S["AX"], base_y - 600 - S["AY"], alpha=flick * clamp((blur - 0.38) / 0.24))
    # rail-side crowd with bobbing (cheering)
    if crowd > 0:
        rc = S["rc"] if blur < 0.5 else _side_blur("rc", 34)
        off = cam_x * P_CROWD
        rc_top = y_or - S["rc_base"] + 6
        seg = 96
        for i in range(-1, W // seg + 2):
            x0 = i * seg - (off % seg)
            wi = (i + int(off // seg))
            bob = -abs(math.sin(t * (6.5 + 3 * _hash(wi, 2)) + _hash(wi, 5) * 6)) * 5 * crowd * (1 - blur)
            pat = cairo.SurfacePattern(rc); pat.set_extend(cairo.EXTEND_REPEAT); pat.set_filter(cairo.FILTER_BILINEAR)
            pat.set_matrix(cairo.Matrix(1, 0, 0, 1, off, -(rc_top + bob)))
            ctx.save(); ctx.rectangle(x0, rc_top + bob, seg + 0.5, S["rc"].get_height()); ctx.clip()
            ctx.set_source(pat); ctx.paint_with_alpha(clamp(crowd)); ctx.restore()
        # phones sparkle
        for j, (px, py, hr) in enumerate(S["rc_ph"][::3]):
            RCW = S["rc"].get_width()
            sx = (px - off) % RCW
            if sx < W + 20:
                tw = 0.5 + 0.5 * math.sin(t * 3 + j)
                _glow(ctx, sx, rc_top + py, 16, (0.8, 0.9, 1.0), 0.25 * tw * crowd)
    # outer rail
    _paint_blurmix(ctx, "orl", 40, blur, cam_x * P_ORAIL, y_or - S["orl_top"] - 6)
    # dirt: bands with increasing parallax (pseudo-perspective)
    dirt = S["dirt"] if blur < 0.5 else _side_blur("dirt", 70)
    y0 = int(y_or + 6)
    band = 5
    TH = S["TH"]
    y = y0
    pat = cairo.SurfacePattern(dirt); pat.set_extend(cairo.EXTEND_REPEAT); pat.set_filter(cairo.FILTER_BILINEAR)
    while y < H + 40:
        f = (y - y0) / max(1.0, (track_y - y0))
        p = 0.84 + 0.16 * f
        ty = (y - y0) / max(1.0, H - y0) * (TH - band)
        pat.set_matrix(cairo.Matrix(1, 0, 0, 1, cam_x * p, ty - y))
        ctx.save(); ctx.rectangle(-200, y, W + 400, band + 0.6); ctx.clip(); ctx.set_source(pat); ctx.paint(); ctx.restore()
        y += band
    # dirt top edge shadow (rail foot) & haze
    g = _lin(ctx, 0, y0 - 4, 0, y0 + 26, [(0, (0.1, 0.06, 0.1, 0.55)), (1, (0.1, 0.06, 0.1, 0))])
    ctx.set_source(g); ctx.rectangle(-200, y0 - 4, W + 400, 30); ctx.fill()
    # floodlight sheen on dirt (under each tower)
    off = cam_x * P_TOW
    ctx.save()
    ctx.set_operator(cairo.OPERATOR_ADD)
    for k in range(int((off - 900) // TOW_SP), int((off + W + 900) // TOW_SP) + 1):
        sx = k * TOW_SP - off + 260 + (cam_x * (1 - P_TOW)) * 0.0
        for (dy, rx, ry, a) in ((26, 560, 34, 0.2), (70, 760, 70, 0.1), ((track_y - y0) + 30, 950, 120, 0.07)):
            ctx.save(); ctx.translate(sx, y0 + dy); ctx.scale(1, ry / rx)
            _glow(ctx, 0, 0, rx, (1.0, 0.85, 0.62), a)
            ctx.restore()
    ctx.restore()
    # low haze over the far side of the track (atmosphere)
    g = _lin(ctx, 0, y_or - 120, 0, y_or + 60, [(0, (0.7, 0.55, 0.7, 0)), (0.7, (0.75, 0.6, 0.65, 0.12)), (1, (0.75, 0.6, 0.65, 0))])
    ctx.set_source(g); ctx.rectangle(-200, y_or - 120, W + 400, 180); ctx.fill()
    # near-bottom darkening
    g = _lin(ctx, 0, track_y + 60, 0, H, [(0, (0.05, 0.02, 0.06, 0)), (1, (0.05, 0.02, 0.06, 0.45))])
    ctx.set_source(g); ctx.rectangle(-200, track_y + 60, W + 400, H - track_y); ctx.fill()
    if blur > 0.05:
        from lib.common import horiz_speed_lines
        horiz_speed_lines(ctx, t, 60, y_or - 20, n=int(26 * blur), speed=3200, color=(1, 0.95, 0.9), alpha=0.22 * blur, seed=17,
                          length=(300, 900))
        horiz_speed_lines(ctx, t, y_or + 20, H, n=int(30 * blur), speed=5200, color=(1, 0.9, 0.75), alpha=0.18 * blur, seed=18,
                          length=(400, 1200))


def _stand_sparkles(ctx, t, cam_x, gs_y, crowd, flash):
    """Camera flashes & shimmering phones over the grandstand."""
    if crowd <= 0 and flash <= 0:
        return
    fi = int(t * FPS)
    S = _side()
    off = cam_x * P_GS
    ph, heads = S["gs_ph"]
    # shimmering phones (subset)
    n = len(ph)
    for j in range(0, n, 7):
        px, py = ph[j]
        sx = (px - off) % GS_W
        if sx > W + 10:
            continue
        tw = 0.5 + 0.5 * math.sin(t * (2 + _hash(j, 1) * 3) + j)
        _glow(ctx, sx, gs_y + py, 9, (0.85, 0.92, 1.0), 0.35 * tw * crowd)
    # camera flashes: short-lived bursts
    nfl = int(4 + 46 * flash) if crowd > 0 else int(46 * flash)
    for f_ in (fi, fi - 1):
        age = fi - f_
        nh = len(heads)
        for k in range(nfl):
            h1 = _hash(f_ * 131 + k, 71)
            hx, hy = heads[int(h1 * nh) % nh]
            # choose a head currently on screen: shift by whole strip multiples & window
            sx = (hx - off) % GS_W
            if sx > W + 40:
                sx = (off + _hash(f_ * 131 + k, 73) * W)   # remap into visible window
                hx, hy = heads[int(_hash(f_ * 131 + k, 74) * nh) % nh]
                sx = (hx - off) % GS_W
                if sx > W + 40:
                    continue
            x, y = sx, gs_y + hy
            a = (1.0 if age == 0 else 0.35)
            _glow(ctx, x, y, 34, (0.95, 0.97, 1.0), 0.55 * a)
            _star_flare(ctx, x, y, 22 * a + 6, (1, 1, 1), 0.9 * a)
            ctx.set_source_rgba(1, 1, 1, a); ctx.arc(x, y, 2.4, 0, TAU); ctx.fill()


def _inner_rail_y(track_y):
    return track_y + 0.62 * (H - track_y)


P_IRAIL = 1.3
IRAIL_SP = 360.0


def draw_race_side_fg(ctx, t, cam_x, *, track_y=760, rail=True, blur=0.0, clods=1.0, grass=True):
    """Foreground in front of the horses: inner white rail (parallax 1.3) with posts
    whipping past, infield grass verge, flying dirt clods. blur 0..1 = speed smear."""
    blur = clamp(blur)
    yr = _inner_rail_y(track_y)
    off = cam_x * P_IRAIL
    if grass:
        gy = yr + 40
        g = _lin(ctx, 0, gy, 0, H, [(0, (0.10, 0.16, 0.13)), (1, (0.03, 0.05, 0.06))])
        ctx.set_source(g); ctx.rectangle(-200, gy, W + 400, H - gy + 200); ctx.fill()
        # grass tufts scrolling (streaked when blurred)
        for i in range(int((off - 60) // 23), int((off + W + 60) // 23) + 1):
            x = i * 23 - off + _hash(i, 41) * 20
            hgt = 12 + 26 * _hash(i, 42)
            ctx.set_source_rgba(0.2, 0.32, 0.22, 0.7)
            if blur > 0.3:
                ctx.rectangle(x - 30 * blur, gy - hgt * 0.4, 60 * blur, 3); ctx.fill()
            else:
                ctx.move_to(x - 3, gy + 4); ctx.line_to(x + 1 + 4 * _hash(i, 43), gy - hgt); ctx.line_to(x + 3, gy + 4); ctx.fill()
        g = _lin(ctx, 0, gy - 8, 0, gy + 30, [(0, (1, 0.9, 0.7, 0.0)), (0.3, (1, 0.9, 0.7, 0.10)), (1, (1, 0.9, 0.7, 0))])
        ctx.set_source(g); ctx.rectangle(-200, gy - 8, W + 400, 38); ctx.fill()
    if rail:
        # posts
        pw = 15
        for i in range(int((off - 400) // IRAIL_SP), int((off + W + 400) // IRAIL_SP) + 1):
            x = i * IRAIL_SP - off
            smear = 150 * blur
            if smear > 4:
                g = _lin(ctx, x - smear, 0, x + pw + smear * 0.3, 0,
                         [(0, (0.95, 0.95, 1, 0)), (0.6, (0.95, 0.95, 1, 0.5 * (1 - 0.4 * blur))), (1, (0.95, 0.95, 1, 0))])
                ctx.set_source(g); ctx.rectangle(x - smear, yr, pw + smear * 1.3, H - yr + 100); ctx.fill()
            else:
                g = _lin(ctx, x, 0, x + pw, 0, [(0, (1, 1, 1)), (0.55, (0.88, 0.88, 0.94)), (1, (0.55, 0.55, 0.68))])
                ctx.set_source(g); ctx.rectangle(x, yr, pw, H - yr + 100); ctx.fill()
                ctx.set_source_rgba(0.1, 0.05, 0.12, 0.35); ctx.rectangle(x + pw, yr + 14, 5, H - yr); ctx.fill()
        # lower bar
        g = _lin(ctx, 0, yr + 62, 0, yr + 72, [(0, (0.98, 0.98, 1)), (1, (0.6, 0.6, 0.72))])
        ctx.set_source(g); ctx.rectangle(-200, yr + 62, W + 400, 9); ctx.fill()
        # top bar (big rounded pipe) with floodlit sheen
        th = 22
        g = _lin(ctx, 0, yr - th / 2, 0, yr + th / 2,
                 [(0, (0.82, 0.82, 0.9)), (0.25, (1, 1, 1)), (0.55, (0.92, 0.92, 0.97)), (1, (0.5, 0.48, 0.62))])
        ctx.set_source(g); ctx.rectangle(-200, yr - th / 2, W + 400, th); ctx.fill()
        g = _lin(ctx, 0, yr - th * 1.6, 0, yr + th * 1.2,
                 [(0, (1, 0.95, 0.85, 0)), (0.45, (1, 0.95, 0.85, 0.22)), (0.6, (1, 0.95, 0.85, 0.22)), (1, (1, 0.95, 0.85, 0))])
        ctx.set_source(g); ctx.rectangle(-200, yr - th * 1.6, W + 400, th * 2.8); ctx.fill()
        # travelling specular glints on the pipe (from floodlights, parallax of towers)
        toff = cam_x * P_TOW
        for k in range(int((toff - 900) // TOW_SP), int((toff + W + 900) // TOW_SP) + 1):
            sx = k * TOW_SP - toff + 260
            ctx.save(); ctx.translate(sx, yr - th * 0.22); ctx.scale(1, 0.04)
            _glow(ctx, 0, 0, 420, (1, 1, 1), 0.9)
            ctx.restore()
    if clods > 0:
        _fg_clods(ctx, t, track_y, clods, blur)


def _fg_clods(ctx, t, track_y, amount, blur):
    """Dirt clods flung toward camera, streaking left across the lower frame."""
    n = int(10 * amount)
    for i in range(n):
        per = 0.9 + _hash(i, 61) * 0.8
        ph = (t / per + _hash(i, 62)) % 1.0
        cyc = int(t / per + _hash(i, 62))
        x = W * (1.15 - ph * 1.5) + (_hash(i + cyc * 13, 63) - 0.5) * 400
        y0 = track_y + 40 + _hash(i + cyc * 7, 64) * (H - track_y)
        y = y0 - math.sin(ph * math.pi) * 160 * _hash(i, 65)
        sz = 3 + 9 * _hash(i + cyc, 66)
        L = sz * (2 + 14 * blur)
        ctx.save()
        g = _lin(ctx, x, 0, x + L, 0, [(0, (0.22, 0.15, 0.12, 0.9)), (1, (0.22, 0.15, 0.12, 0))])
        ctx.set_source(g)
        ctx.move_to(x, y - sz / 2); ctx.line_to(x + L, y - sz * 0.2); ctx.line_to(x + L, y + sz * 0.2); ctx.line_to(x, y + sz / 2)
        ctx.close_path(); ctx.fill()
        ctx.set_source_rgba(0.3, 0.21, 0.16, 0.95); ctx.arc(x, y, sz / 2, 0, TAU); ctx.fill()
        ctx.set_source_rgba(1, 0.85, 0.65, 0.5); ctx.arc(x - sz * 0.1, y - sz * 0.15, sz * 0.22, 0, TAU); ctx.fill()
        ctx.restore()


# ======================================================================
#  ESTABLISHING SHOT (high angle over the whole oval)
# ======================================================================
EST_F, EST_H = 900.0, 260.0          # focal (px) and camera height (m)
EST_CW, EST_CH, EST_CX = 2600, 1000, 1300   # ground canvas; horizon at row 0
OVAL_L, OVAL_R, OVAL_Z0, TRACK_WD = 200.0, 128.0, 520.0, 24.0
_EST = {}


def _eproj(X, Z, Y=0.0):
    return EST_CX + EST_F * X / Z, EST_F * (EST_H - Y) / Z


def _oval_pt(s, off=0.0):
    """Point on the oval: s in [0,1) param along perimeter (clockwise from the finish on
    the far/home straight), off = lateral offset outward in m."""
    L, R = OVAL_L, OVAL_R + off
    per = 4 * L + 2 * math.pi * R
    d = (s % 1.0) * per
    # home straight: far side (Z0+R), running from X=+L to X=-L (right->left as seen)... use clockwise
    if d < 2 * L:
        return (L - d, OVAL_Z0 + R)
    d -= 2 * L
    if d < math.pi * R:
        a = d / R
        return (-L - R * math.sin(a), OVAL_Z0 + R * math.cos(a))
    d -= math.pi * R
    if d < 2 * L:
        return (-L + d, OVAL_Z0 - R)
    d -= 2 * L
    a = d / R
    return (L + R * math.sin(a), OVAL_Z0 - R * math.cos(a))


def _oval_poly(ctx, off, n=240):
    for i in range(n + 1):
        X, Z = _oval_pt(i / n, off)
        u, v = _eproj(X, Z)
        if i == 0:
            ctx.move_to(u, v)
        else:
            ctx.line_to(u, v)
    ctx.close_path()


def _est_build():
    s, c = _surf(EST_CW, EST_CH)
    r = rng(808)
    f, h = EST_F, EST_H
    # ---- ground base: far urban land fading to horizon ----
    g = _lin(c, 0, 0, 0, EST_CH, [(0, (0.26, 0.15, 0.28)), (0.06, (0.12, 0.08, 0.17)), (0.3, (0.06, 0.05, 0.11)),
                                   (1, (0.035, 0.03, 0.07))])
    c.set_source(g); c.paint()
    # Tokyo bay / canal water band right below the skyline
    WB = 34
    g = _lin(c, 0, 0, 0, WB, [(0, (0.22, 0.14, 0.26)), (1, (0.07, 0.06, 0.13))])
    c.set_source(g); c.rectangle(0, 0, EST_CW, WB); c.fill()
    c.move_to(0, WB); 
    for i in range(0, EST_CW + 40, 40):
        c.line_to(i, WB + 6 * math.sin(i * 0.01) + 4 * math.sin(i * 0.037))
    c.line_to(EST_CW, WB + 20); c.line_to(0, WB + 20); c.close_path()
    c.set_source_rgb(0.08, 0.06, 0.12); c.fill()
    # streets converging to the vanishing point with sodium lights
    for i in range(40):
        X = r.uniform(-4000, 4000)
        Z0 = 760 * (1 + r.random() * 4); Z1 = Z0 * r.uniform(1.5, 4)
        u0, v0 = _eproj(X, Z0); u1, v1 = _eproj(X, Z1)
        c.set_source_rgba(1.0, 0.62, 0.3, r.uniform(0.08, 0.2)); c.set_line_width(1.0)
        c.move_to(u0, v0); c.line_to(u1, v1); c.stroke()
    for i in range(16):     # cross streets (horizontal segments)
        Z = 760 * (1.0 + r.random() ** 1.5 * 10)
        v = f * h / Z
        x0 = r.uniform(0, EST_CW); L = r.uniform(200, 900)
        c.set_source_rgba(1.0, 0.7, 0.4, r.uniform(0.08, 0.2)); c.set_line_width(max(0.6, 1.2 * 760 / Z))
        c.move_to(x0, v); c.line_to(x0 + L, v); c.stroke()
    # expressways: bright light rivers curving through the city
    for k in range(3):
        c.new_path()
        pts = []
        Zb = 760 + k * 500
        for j in range(60):
            X = -3500 + j * 120
            Z = Zb + 400 * math.sin(j * 0.12 + k * 2) + j * 8 * (k - 1)
            pts.append(_eproj(X, max(700, Z)))
        for w_, a_, col in ((5, 0.12, (1, 0.6, 0.3)), (1.6, 0.6, (1, 0.8, 0.5))):
            c.move_to(*pts[0])
            for p_ in pts[1:]:
                c.line_to(*p_)
            c.set_line_width(w_); c.set_source_rgba(*col, a_); c.stroke()
    # far buildings blocks with windows (Z 780..3200)
    vmax = f * h / 760.0
    dens_map = _fbm2(64, 128, (3, 6), 4, seed=77)
    def dens_at(u, v):
        return dens_map[int(clamp(v / vmax) * 63), int(clamp(u / EST_CW) * 127)]
    blocks = []
    for i in range(1400):
        Z = 770 + (r.random() ** 1.4) * 3000
        X = r.uniform(-1.4, 1.4) * Z
        u, v = _eproj(X, Z)
        if r.random() > dens_at(u, v) * 1.6 - 0.2:
            continue
        blocks.append((Z, X))
    blocks.sort(key=lambda b: -b[0])
    for (Z, X) in blocks:
        u, v = _eproj(X, Z)
        bw = r.uniform(14, 50) * f / Z
        bh = r.uniform(6, 45) * f / Z
        dd = clamp((Z - 770) / 3000)
        c.set_source_rgb(0.04 + 0.12 * dd, 0.035 + 0.07 * dd, 0.08 + 0.14 * dd)
        c.rectangle(u - bw / 2, v - bh, bw, bh); c.fill()
        c.set_source_rgba(0.9, 0.55, 0.65, 0.12 + 0.1 * dd)       # rim from city glow
        c.rectangle(u - bw / 2, v - bh, bw, 1.2); c.fill()
        nwx = max(1, int(bw / 2.6)); nwy = max(1, int(bh / 3.0))
        pc = r.choice([(1, 0.85, 0.6), (0.85, 0.92, 1), (1, 0.75, 0.45)])
        for a in range(nwx):
            for b in range(nwy):
                if r.random() < 0.4:
                    c.set_source_rgba(*pc, r.uniform(0.45, 1.0))
                    c.rectangle(u - bw / 2 + 0.8 + a * 2.6, v - bh + 1.2 + b * 3.0, 1.2, 1.3); c.fill()
    # carpet of city lights (clustered)
    n_ok = 0
    while n_ok < 14000:
        v = 1 + (r.random() ** 1.8) * (vmax - 1)
        u = r.uniform(0, EST_CW)
        if r.random() > dens_at(u, v) * 1.7 - 0.25:
            continue
        n_ok += 1
        Z = f * h / v
        sz = clamp(700 / Z, 0.35, 1.3)
        col = r.choice([(1, 0.8, 0.5), (1, 0.8, 0.5), (1, 0.65, 0.35), (0.85, 0.92, 1), (1, 1, 1)])
        c.set_source_rgba(*col, r.uniform(0.3, 1.0))
        c.arc(u, v, sz, 0, TAU); c.fill()
    # atmospheric haze toward horizon
    g = _lin(c, 0, 0, 0, 200, [(0, (0.85, 0.5, 0.6, 0.6)), (0.2, (0.6, 0.35, 0.5, 0.3)), (1, (0.3, 0.2, 0.4, 0))])
    c.set_source(g); c.rectangle(0, 0, EST_CW, 200); c.fill()

    # ---- racecourse grounds (dark lawn around the oval) ----
    c.save()
    _oval_poly(c, TRACK_WD + 70)
    c.set_source_rgb(0.05, 0.07, 0.09); c.fill()
    c.restore()
    # ---- grandstands (far side, beyond home straight), facing camera ----
    Zs = OVAL_Z0 + OVAL_R + TRACK_WD + 16
    for (X0, X1, hgt, dz, kind) in ((-250, 60, 34, 0, "main"), (60, 200, 26, 6, "wing"), (-340, -250, 22, 8, "wing")):
        _est_stand(c, r, X0, X1, Zs + dz, hgt, kind)
    # ---- dirt track ring ----
    c.save()
    _oval_poly(c, TRACK_WD); _oval_poly(c, 0)
    c.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    g = _lin(c, 0, _eproj(0, OVAL_Z0 + OVAL_R + TRACK_WD)[1], 0, _eproj(0, OVAL_Z0 - OVAL_R - TRACK_WD)[1],
             [(0, (0.8, 0.63, 0.48)), (0.5, (0.66, 0.5, 0.37)), (1, (0.6, 0.45, 0.33))])
    c.set_source(g); c.fill_preserve()
    c.clip()
    # grooming lines along the track (concentric)
    for k in range(1, 12):
        _oval_poly(c, TRACK_WD * k / 12)
        c.set_source_rgba(0.3, 0.2, 0.15, 0.18); c.set_line_width(0.8); c.stroke()
    # shading: outer part of the ring darker, lit patches
    for k in range(40):
        X, Z = _oval_pt(r.random(), TRACK_WD * r.uniform(0.2, 0.8))
        u, v = _eproj(X, Z)
        c.save(); c.translate(u, v); c.scale(1, 0.35)
        _glow(c, 0, 0, r.uniform(40, 120) * f / Z, (0.35, 0.22, 0.15) if r.random() < 0.5 else (1, 0.9, 0.75), 0.18)
        c.restore()
    c.restore()
    # ---- infield ----
    c.save()
    _oval_poly(c, -2)
    g = _lin(c, 0, _eproj(0, OVAL_Z0 + OVAL_R)[1], 0, _eproj(0, OVAL_Z0 - OVAL_R)[1],
             [(0, (0.09, 0.15, 0.16)), (0.5, (0.065, 0.12, 0.13)), (1, (0.05, 0.09, 0.11))])
    c.set_source(g); c.fill_preserve(); c.clip()
    # mowing stripes
    for k in range(-14, 15):
        X = k * 26
        u0, v0 = _eproj(X - 13, OVAL_Z0 - OVAL_R); u1, v1 = _eproj(X - 13, OVAL_Z0 + OVAL_R)
        u2, v2 = _eproj(X, OVAL_Z0 + OVAL_R); u3, v3 = _eproj(X, OVAL_Z0 - OVAL_R)
        c.move_to(u0, v0); c.line_to(u1, v1); c.line_to(u2, v2); c.line_to(u3, v3); c.close_path()
        c.set_source_rgba(0.3, 0.45, 0.4, 0.07); c.fill()
    # pond with reflections
    c.save()
    pu, pv = _eproj(-90, OVAL_Z0 + 30)
    c.translate(pu, pv); c.scale(1.0, 0.42)
    c.arc(0, 0, 70, 0, TAU)
    g = cairo.RadialGradient(0, -30, 5, 0, 0, 70)
    g.add_color_stop_rgb(0, 0.16, 0.16, 0.32); g.add_color_stop_rgb(1, 0.03, 0.04, 0.1)
    c.set_source(g); c.fill()
    c.restore()
    for i in range(10):
        x = pu + r.uniform(-50, 50); y = pv + r.uniform(-18, 18)
        c.set_source_rgba(1, 0.9, 0.7, 0.4); c.rectangle(x, y, r.uniform(4, 12), 1); c.fill()
    # lit walkways with lamps across the infield
    for (Xa, Za, Xb, Zb) in ((-150, OVAL_Z0 - 60, 150, OVAL_Z0 - 60), (0, OVAL_Z0 - 100, 0, OVAL_Z0 + 100),
                             (-120, OVAL_Z0 + 60, 120, OVAL_Z0 + 60)):
        ua, va = _eproj(Xa, Za); ub, vb = _eproj(Xb, Zb)
        c.set_source_rgba(0.55, 0.5, 0.45, 0.35); c.set_line_width(2.2); c.move_to(ua, va); c.line_to(ub, vb); c.stroke()
        for k in range(9):
            fk = k / 8
            X = Xa + (Xb - Xa) * fk; Z = Za + (Zb - Za) * fk
            u, v = _eproj(X, Z)
            _glow(c, u, v, 9, (1, 0.8, 0.5), 0.55)
            c.set_source_rgb(1, 0.92, 0.75); c.arc(u, v, 1.1, 0, TAU); c.fill()
    # inner track (training) : thin sand loop
    _oval_poly(c, -34)
    c.set_source_rgba(0.5, 0.4, 0.32, 0.55); c.set_line_width(5); c.stroke()
    # big screen in infield (back side dark, facing stand)
    su, sv = _eproj(20, OVAL_Z0 + OVAL_R - 30)
    c.set_source_rgb(0.04, 0.04, 0.07); c.rectangle(su - 90, sv - 42, 180, 38); c.fill()
    c.rectangle(su - 3, sv - 6, 6, 8); c.fill()
    c.restore()
    # ---- rails (white) ----
    for off, wmul in ((TRACK_WD, 1.0), (0, 1.0)):
        n = 360
        for i in range(n):
            X0, Z0 = _oval_pt(i / n, off); X1, Z1 = _oval_pt((i + 1) / n, off)
            u0, v0 = _eproj(X0, Z0, 1.2); u1, v1 = _eproj(X1, Z1, 1.2)
            c.move_to(u0, v0); c.line_to(u1, v1)
            c.set_line_width(max(0.9, 1500 / Z0 * wmul * 0.9))
            c.set_source_rgba(0.97, 0.97, 1.0, 0.95); c.stroke()
    # floodlight wash over the whole course
    c.save(); c.set_operator(cairo.OPERATOR_ADD)
    cu, cv = _eproj(0, OVAL_Z0 + 20)
    c.translate(cu, cv); c.scale(1, 0.42)
    _glow(c, 0, 0, 900, (0.55, 0.42, 0.3), 0.35)
    c.restore()
    # finish post on home straight
    fu, fv = _eproj(-60, OVAL_Z0 + OVAL_R + TRACK_WD + 2)
    c.set_source_rgb(1, 1, 1); c.rectangle(fu - 1, fv - 14, 2, 14); c.fill()
    c.arc(fu, fv - 16, 3.2, 0, TAU); c.fill()
    # ---- near-side grounds (foreground): trees, lamps, parking with car lights ----
    Zn = OVAL_Z0 - OVAL_R - TRACK_WD - 40
    trees = []
    for i in range(700):
        Z = r.uniform(200, Zn)
        X = r.uniform(-1.0, 1.0) * Z * 1.3
        if abs(X) < 380 and Z > Zn - 30:
            continue
        trees.append((Z, X))
    for rowZ in (Zn - 5, Zn - 60, 250):       # tree lines along paths
        for X in np.arange(-900, 900, 9):
            trees.append((rowZ + r.uniform(-4, 4), X + r.uniform(-3, 3)))
    trees.sort(key=lambda a: -a[0])
    for (Z, X) in trees:
        u, v = _eproj(X, Z)
        if not (-50 < u < EST_CW + 50):
            continue
        _tree_clump_est(c, r, u, v, 4.2 * f / Z)
    for i in range(70):     # lamp posts
        Z = r.uniform(250, Zn); X = r.uniform(-1.0, 1.0) * Z * 1.3
        u, v = _eproj(X, Z); u2, v2 = _eproj(X, Z, 8)
        c.set_source_rgba(0.12, 0.12, 0.16, 1); c.set_line_width(1); c.move_to(u, v); c.line_to(u2, v2); c.stroke()
        _glow(c, u2, v2, 14, (1, 0.8, 0.5), 0.6)
    # road along the bottom with car lights
    for Z, colr in ((300, (1, 0.25, 0.2)), (292, (1, 0.95, 0.85))):
        v = f * h / Z
        for i in range(90):
            u = r.uniform(0, EST_CW)
            c.set_source_rgba(*colr, 0.85)
            c.arc(u, v, 1.6, 0, TAU); c.fill()
            _glow(c, u, v, 8, colr, 0.35)
    # atmospheric light dome over the course (floodlight scatter in the haze)
    c.save(); c.set_operator(cairo.OPERATOR_ADD)
    cu, cv = _eproj(0, OVAL_Z0 + 40, 30)
    c.translate(cu, cv); c.scale(1, 0.5)
    _glow(c, 0, 0, 1000, (0.5, 0.36, 0.3), 0.3)
    c.restore()
    # ---- floodlight towers ring (drawn last, far to near) ----
    towers = []
    for i in range(22):
        X, Z = _oval_pt((i + 0.5) / 22, TRACK_WD + 14)
        towers.append((Z, X))
    for i in range(6):
        X, Z = _oval_pt((i + 0.25) / 6, -20)
        towers.append((Z, X))
    towers.sort(key=lambda a: -a[0])
    heads = []
    for (Z, X) in towers:
        u, v = _eproj(X, Z); u2, v2 = _eproj(X, Z, 42)
        sc = f / Z
        c.set_source_rgba(0.18, 0.17, 0.22, 1); c.set_line_width(max(1.0, 0.9 * sc))
        c.move_to(u, v); c.line_to(u2, v2); c.stroke()
        # light cone toward the track centre
        cx_, cz_ = 0.0, OVAL_Z0
        dx_, dz_ = cx_ - X, cz_ - Z
        dl = math.hypot(dx_, dz_) or 1
        tx_, tz_ = X + dx_ / dl * 60, Z + dz_ / dl * 60
        ut, vt = _eproj(tx_, tz_)
        px_, pz_ = -dz_ / dl * 22, dx_ / dl * 22
        ul, vl = _eproj(tx_ + px_, tz_ + pz_); ur, vr = _eproj(tx_ - px_, tz_ - pz_)
        g = cairo.LinearGradient(u2, v2, ut, vt)
        g.add_color_stop_rgba(0, 1, 0.92, 0.75, 0.16); g.add_color_stop_rgba(1, 1, 0.92, 0.75, 0)
        c.save(); c.set_operator(cairo.OPERATOR_ADD)
        c.move_to(u2, v2); c.line_to(ul, vl); c.line_to(ur, vr); c.close_path(); c.set_source(g); c.fill()
        c.restore()
        # light pool on the ground
        c.save(); c.translate(u, v); c.scale(1, 0.33)
        _glow(c, 0, 0, 50 * sc, (1, 0.9, 0.7), 0.3)
        c.restore()
        heads.append((u2, v2, sc))
    for (u2, v2, sc) in heads:
        _glow(c, u2, v2, 22 * sc, FLOOD, 0.45)
        c.set_source_rgb(0.15, 0.14, 0.18); c.rectangle(u2 - 3.5 * sc, v2 - 2 * sc, 7 * sc, 4 * sc); c.fill()
        c.set_source_rgb(*FLOOD_CORE); c.rectangle(u2 - 3 * sc, v2 - 1.5 * sc, 6 * sc, 3 * sc); c.fill()
    return dict(surf=s, heads=heads)


def _tree_clump_est(c, r, u, v, sz):
    for k in range(5):
        x = u + r.uniform(-sz, sz) * 0.8; y = v - sz * r.uniform(0.6, 1.5)
        rr_ = sz * r.uniform(0.45, 0.8)
        g = cairo.RadialGradient(x - rr_ * 0.3, y - rr_ * 0.5, 0, x, y, rr_)
        g.add_color_stop_rgb(0, 0.10, 0.17, 0.19); g.add_color_stop_rgb(1, 0.03, 0.05, 0.07)
        c.set_source(g); c.arc(x, y, rr_, 0, TAU); c.fill()


def _est_stand(c, r, X0, X1, Z, hgt, kind):
    f = EST_F
    ua, va = _eproj(X0, Z); ub, vb = _eproj(X1, Z)
    top = va - hgt * f / Z
    # roof (seen from above): trapezoid back into depth
    ua2, va2 = _eproj(X0, Z + 22, hgt); ub2, vb2 = _eproj(X1, Z + 22, hgt)
    c.set_source_rgb(0.1, 0.09, 0.15)
    c.move_to(ua, top); c.line_to(ub, top); c.line_to(ub2, vb2); c.line_to(ua2, va2); c.close_path(); c.fill()
    c.set_source_rgba(0.9, 0.9, 1.0, 0.85); c.set_line_width(1.2); c.move_to(ua, top); c.line_to(ub, top); c.stroke()
    # face: warm glowing tiers
    g = _lin(c, 0, top, 0, va, [(0, (0.55, 0.38, 0.34)), (0.3, (1.0, 0.85, 0.62)), (0.5, (0.75, 0.55, 0.45)),
                                (0.72, (1.0, 0.9, 0.7)), (1, (0.7, 0.55, 0.5))])
    c.set_source(g); c.rectangle(ua, top, ub - ua, va - top); c.fill()
    # crowd stipple
    for i in range(int((ub - ua) * (va - top) * 0.35)):
        x = r.uniform(ua, ub); y = r.uniform(top + 2, va - 1)
        col = r.choice(_CLOTH)
        c.set_source_rgba(*_mute(col, (0.4, 0.3, 0.3), 0.5), 0.8)
        c.rectangle(x, y, 1.2, 1.2); c.fill()
    for yy in np.linspace(top + 3, va - 2, 5):
        c.set_source_rgba(1, 0.95, 0.85, 0.5); c.rectangle(ua, yy, ub - ua, 0.8); c.fill()
    for x in np.arange(ua, ub, 7):
        _glow(c, x, top + 2, 5, (1, 0.9, 0.7), 0.5)
    c.save(); c.translate((ua + ub) / 2, (top + va) / 2); c.scale(1, 0.35)
    _glow(c, 0, 0, (ub - ua) * 0.62, (1, 0.8, 0.55), 0.3)
    c.restore()


def _est():
    if not _EST:
        _EST.update(_disk_dict("est", _est_build))
    return _EST


def draw_racecourse_establishing(ctx, t, cam=0.0, *, horses=False, race_s=0.0, flash=0.3):
    """High-angle wide shot of 大井 at night. cam 0 -> looking up at the sky (course
    below frame), cam 1 -> tilted down & pushed in on the glowing oval.
    horses: draw a tiny pack of glowing dots at oval param race_s (0..1)."""
    E_ = _est()
    k = smoothstep(0, 1, cam)
    hz = lerp(1250, 250, k)
    zoom = lerp(0.92, 1.1, cam)
    draw_sky(ctx, t, horizon_y=hz, stars=1.0, moon=(1480, hz - 830 + 120 * k, 60), clouds=0.55, glow=1.0)
    draw_city(ctx, t, hz + 1, cam_x=0, parallax=0, scale=0.36 * zoom, lights=1.0, tower=True)
    ox = 960 - EST_CX * zoom
    ctx.save()
    ctx.translate(ox, hz); ctx.scale(zoom, zoom)
    ctx.set_source_surface(E_["surf"], 0, 0)
    ctx.get_source().set_filter(cairo.FILTER_BILINEAR)
    ctx.paint()
    ctx.restore()
    # skyline reflection on the water
    ctx.save()
    ctx.rectangle(-200, hz, W + 400, 34 * zoom); ctx.clip()
    ctx.translate(0, 2 * hz + 2); ctx.scale(1, -1)
    ctx.push_group()
    draw_city(ctx, t, hz + 1, cam_x=0, parallax=0, scale=0.36 * zoom, lights=1.0, tower=True, monorail=False, haze=0)
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(0.35)
    ctx.restore()
    ctx.save()
    for i in range(18):      # ripple lines
        yy = hz + 2 + (i / 18) ** 1.3 * 32 * zoom
        ctx.set_source_rgba(0.06, 0.05, 0.12, 0.5); ctx.rectangle(-200, yy, W + 400, 0.8 + i * 0.08); ctx.fill()
    ctx.restore()
    ctx.save()
    ctx.translate(ox, hz); ctx.scale(zoom, zoom)
    # dynamic: floodlight shimmer, horse dots, stand flashes
    for i, (u, v, sc) in enumerate(E_["heads"]):
        a = 0.3 + 0.08 * math.sin(t * 3 + i)
        _glow(ctx, u, v, 80 * sc, FLOOD, a)
        _glow(ctx, u, v, 14 * sc, FLOOD_CORE, 0.9)
        _star_flare(ctx, u, v, 26 * sc, (1, 1, 1), 0.65, rot=0.0)
    if horses:
        for j in range(12):
            s_ = race_s - j * 0.0035 - 0.002 * _hash(j, 3)
            X, Z = _oval_pt(s_, 4 + 16 * _hash(j, 4))
            u, v = _eproj(X, Z, 1.5)
            _glow(ctx, u, v, 7, (1, 0.95, 0.85), 0.6)
            ctx.set_source_rgb(0.2, 0.1, 0.08); ctx.arc(u, v, 1.6, 0, TAU); ctx.fill()
    fi = int(t * FPS)
    Zs = OVAL_Z0 + OVAL_R + TRACK_WD + 16
    for q in range(int(3 + 12 * flash)):
        X = -340 + 540 * _hash(fi * 17 + q, 5)
        u, v = _eproj(X, Zs, 4 + 26 * _hash(fi * 17 + q, 6))
        _glow(ctx, u, v, 9, (1, 1, 1), 0.8)
    ctx.restore()


# ======================================================================
#  FINISH POST (ゴール板)
# ======================================================================
def draw_finish_post(ctx, x, y, scale=1.0, *, line=True, line_len=340, t=0.0, glow=1.0):
    """ゴール板: tall white pole with a round disc mirror on top at (x, y=ground).
    line=True also paints the finish line across the dirt (going toward camera)."""
    s = scale
    ctx.save()
    if line:
        g = _lin(ctx, 0, y, 0, y + line_len * s, [(0, (1, 1, 1, 0.85)), (1, (1, 1, 1, 0.55))])
        ctx.set_source(g)
        ctx.move_to(x - 3 * s, y); ctx.line_to(x + 3 * s, y)
        ctx.line_to(x + (14 + 60) * s, y + line_len * s); ctx.line_to(x + (60 - 14) * s, y + line_len * s)
        ctx.close_path(); ctx.fill()
        ctx.save(); ctx.translate(x + 30 * s, y + line_len * s * 0.5); ctx.scale(0.3, 1)
        _glow(ctx, 0, 0, line_len * s * 0.6, (1, 1, 1), 0.12 * glow)
        ctx.restore()
    ph = 560 * s
    top = y - ph
    # shadow on ground
    ctx.save(); ctx.translate(x + 30 * s, y + 6 * s); ctx.scale(1, 0.18)
    _glow(ctx, 0, 0, 60 * s, (0, 0, 0), 0.5); ctx.restore()
    # pole (white, rounded shading) with red bands near the base
    pw = 16 * s
    g = _lin(ctx, x - pw / 2, 0, x + pw / 2, 0, [(0, (0.7, 0.7, 0.8)), (0.35, (1, 1, 1)), (1, (0.55, 0.55, 0.66))])
    ctx.set_source(g); ctx.rectangle(x - pw / 2, top + 60 * s, pw, ph - 60 * s); ctx.fill()
    for k in range(3):
        yy = y - (40 + k * 34) * s
        ctx.set_source_rgb(0.85, 0.12, 0.2); ctx.rectangle(x - pw / 2, yy - 12 * s, pw, 12 * s); ctx.fill()
    # base
    g = _lin(ctx, x - 26 * s, 0, x + 26 * s, 0, [(0, (0.6, 0.6, 0.7)), (0.4, (0.98, 0.98, 1)), (1, (0.5, 0.5, 0.6))])
    ctx.set_source(g); ctx.rectangle(x - 22 * s, y - 20 * s, 44 * s, 20 * s); ctx.fill()
    # disc (mirror) on top
    R = 78 * s
    cx, cy = x, top + 10 * s
    _glow(ctx, cx, cy, R * 2.6, (1, 0.95, 0.85), 0.35 * glow)
    ctx.set_source_rgb(0.2, 0.2, 0.26); ctx.arc(cx, cy, R + 6 * s, 0, TAU); ctx.fill()
    g = cairo.LinearGradient(cx - R, cy - R, cx + R, cy + R)
    g.add_color_stop_rgb(0, 1, 1, 1); g.add_color_stop_rgb(0.5, 0.92, 0.92, 0.96); g.add_color_stop_rgb(1, 0.7, 0.7, 0.8)
    ctx.set_source(g); ctx.arc(cx, cy, R, 0, TAU); ctx.fill()
    # mirror face reflecting the night & lights
    Ri = R * 0.78
    g = cairo.LinearGradient(cx, cy - Ri, cx, cy + Ri)
    g.add_color_stop_rgb(0, 0.12, 0.12, 0.3); g.add_color_stop_rgb(0.55, 0.35, 0.25, 0.5); g.add_color_stop_rgb(0.62, 0.95, 0.75, 0.55)
    g.add_color_stop_rgb(1, 0.45, 0.33, 0.28)
    ctx.set_source(g); ctx.arc(cx, cy, Ri, 0, TAU); ctx.fill()
    ctx.save(); ctx.arc(cx, cy, Ri, 0, TAU); ctx.clip()
    # sheen diagonal
    sh = 0.5 + 0.5 * math.sin(t * 1.5)
    g = _lin(ctx, cx - Ri, cy - Ri, cx + Ri, cy + Ri, [(0, (1, 1, 1, 0)), (0.42 + 0.1 * sh, (1, 1, 1, 0)),
                                                     (0.5 + 0.1 * sh, (1, 1, 1, 0.55)), (0.58 + 0.1 * sh, (1, 1, 1, 0))])
    ctx.set_source(g); ctx.paint()
    for k in range(5):   # reflected floodlights
        _glow(ctx, cx - Ri * 0.6 + k * Ri * 0.3, cy + Ri * 0.12, 10 * s, (1, 0.95, 0.8), 0.9)
    ctx.restore()
    # red ring + white star-ish mark (classic ゴール板 look)
    ctx.set_source_rgb(0.88, 0.1, 0.18); ctx.set_line_width(5 * s); ctx.arc(cx, cy, R * 0.88, 0, TAU); ctx.stroke()
    ctx.set_source_rgba(1, 1, 1, 0.9); ctx.set_line_width(1.5 * s); ctx.arc(cx, cy, R, math.pi * 1.1, math.pi * 1.5); ctx.stroke()
    ctx.restore()


# ======================================================================
#  STARTING GATE
# ======================================================================
GATE_GREEN = (0.08, 0.42, 0.28)
GATE_GREEN_D = (0.04, 0.22, 0.16)
GATE_WHITE = (0.94, 0.95, 0.96)
_FRAME_COLS = [(0.97, 0.97, 0.97), (0.08, 0.08, 0.1), (0.88, 0.12, 0.16), (0.12, 0.3, 0.85),
               (0.98, 0.85, 0.1), (0.1, 0.6, 0.3), (1.0, 0.55, 0.1), (1.0, 0.55, 0.7)]


def _door_angle(open_):
    """0..1 -> door angle (0 closed .. ~1.45 rad) with overshoot bounce."""
    o = clamp(open_)
    if o <= 0:
        return 0.0
    a = 1 - math.exp(-7 * o) * math.cos(11 * o)
    return 1.35 * a / (1 - math.exp(-7) * math.cos(11)) if o < 1 else 1.35


def _gate_front_geo(x, y, s, n):
    SW = 118 * s
    total = n * SW
    x0 = x - total / 2
    return SW, total, x0


def draw_starting_gate_back(ctx, t, x, y, scale=1.0, open=0.0, n_stalls=8, view="front"):
    """Rear part of the gate (drawn before horses)."""
    s = scale
    ctx.save()
    if view == "front":
        SW, total, x0 = _gate_front_geo(x, y, s, n_stalls)
        # shadow on ground
        ctx.save(); ctx.translate(x, y + 4 * s); ctx.scale(1, 0.06)
        _glow(ctx, 0, 0, total * 0.65, (0, 0, 0), 0.6); ctx.restore()
        # back frame (smaller, higher: further away)
        bk = 0.86
        bx0 = x - total * bk / 2
        by = y - 26 * s
        ctx.set_source_rgb(*GATE_GREEN_D)
        ctx.rectangle(bx0, by - 330 * s * bk, total * bk, 26 * s); ctx.fill()
        for i in range(n_stalls):
            sx = bx0 + i * SW * bk
            # interior: dark back doors
            g = _lin(ctx, 0, by - 300 * s * bk, 0, by, [(0, (0.10, 0.16, 0.15)), (0.5, (0.07, 0.1, 0.11)), (1, (0.2, 0.15, 0.13))])
            ctx.set_source(g); ctx.rectangle(sx + 4 * s, by - 304 * s * bk, SW * bk - 8 * s, 300 * s * bk - 20 * s); ctx.fill()
            ctx.set_source_rgba(0.3, 0.5, 0.4, 0.5); ctx.set_line_width(1.2 * s)
            for k in range(6):
                yy = by - (40 + k * 40) * s * bk
                ctx.move_to(sx + 6 * s, yy); ctx.line_to(sx + SW * bk - 6 * s, yy)
            ctx.stroke()
        for i in range(n_stalls + 1):
            sx = bx0 + i * SW * bk
            ctx.set_source_rgb(*GATE_GREEN_D); ctx.rectangle(sx - 5 * s, by - 330 * s * bk, 10 * s, 330 * s * bk); ctx.fill()
        # side partitions receding (perspective trapezoids between back & front posts)
        for i in range(n_stalls + 1):
            fx = x0 + i * SW; bxx = bx0 + i * SW * bk
            ctx.set_source_rgba(*GATE_GREEN, 0.95)
            ctx.move_to(bxx, by - 250 * s * bk); ctx.line_to(fx, y - 250 * s)
            ctx.line_to(fx, y - 110 * s); ctx.line_to(bxx, by - 110 * s * bk); ctx.close_path(); ctx.fill()
            ctx.set_source_rgba(1, 1, 1, 0.5); ctx.set_line_width(1.5 * s)
            ctx.move_to(bxx, by - 250 * s * bk); ctx.line_to(fx, y - 250 * s); ctx.stroke()
        # dirt inside stalls darker
        ctx.set_source_rgba(0.1, 0.06, 0.05, 0.35)
        ctx.move_to(bx0, by); ctx.line_to(bx0 + total * bk, by); ctx.line_to(x0 + total, y); ctx.line_to(x0, y); ctx.close_path(); ctx.fill()
    else:
        _gate_side(ctx, t, x, y, s, open, n_stalls, part="back")
    ctx.restore()


def draw_starting_gate_front(ctx, t, x, y, scale=1.0, open=0.0, n_stalls=8, view="front"):
    """Front part of the gate (drawn after horses): posts, truss, number plates, doors."""
    s = scale
    ctx.save()
    if view == "front":
        SW, total, x0 = _gate_front_geo(x, y, s, n_stalls)
        th = 360 * s
        ang = _door_angle(open)
        # doors
        for i in range(n_stalls):
            sx = x0 + i * SW
            half = SW / 2 - 6 * s
            for side in (-1, 1):
                hx = sx + 6 * s if side < 0 else sx + SW - 6 * s     # hinge at the posts
                dirn = 1 if side < 0 else -1
                wv = half * math.cos(ang)
                grow = half * math.sin(ang) * 0.16                  # perspective: swinging toward camera
                dt, db = y - 232 * s, y - 14 * s
                ex = hx + dirn * wv
                ctx.move_to(hx, dt); ctx.line_to(ex, dt - grow); ctx.line_to(ex, db + grow * 0.6); ctx.line_to(hx, db); ctx.close_path()
                shade = 0.75 + 0.25 * math.cos(ang)
                ctx.set_source_rgb(GATE_WHITE[0] * shade, GATE_WHITE[1] * shade, GATE_WHITE[2] * shade)
                ctx.fill_preserve()
                ctx.set_source_rgb(*GATE_GREEN); ctx.set_line_width(5 * s); ctx.stroke()
                # mesh lines
                if abs(wv) > 6 * s:
                    ctx.set_source_rgba(*GATE_GREEN, 0.55); ctx.set_line_width(1.2 * s)
                    for k in range(1, 8):
                        f = k / 8
                        ctx.move_to(hx, dt + (db - dt) * f); ctx.line_to(ex, dt - grow + (db + grow * 0.6 - dt + grow) * f)
                    ctx.stroke()
                    # green lower kick panel
                    ctx.set_source_rgb(*GATE_GREEN)
                    kf = 0.72
                    ctx.move_to(hx, dt + (db - dt) * kf); ctx.line_to(ex, dt - grow + (db + grow * 0.6 - dt + grow) * kf)
                    ctx.line_to(ex, db + grow * 0.6); ctx.line_to(hx, db); ctx.close_path(); ctx.fill()
        # posts
        for i in range(n_stalls + 1):
            px = x0 + i * SW
            g = _lin(ctx, px - 7 * s, 0, px + 7 * s, 0, [(0, GATE_GREEN_D), (0.4, (0.2, 0.62, 0.45)), (1, GATE_GREEN_D)])
            ctx.set_source(g); ctx.rectangle(px - 7 * s, y - th, 14 * s, th); ctx.fill()
            ctx.set_source_rgb(0.12, 0.12, 0.14); ctx.rectangle(px - 9 * s, y - 8 * s, 18 * s, 8 * s); ctx.fill()
        # top truss
        g = _lin(ctx, 0, y - th - 10 * s, 0, y - th + 70 * s, [(0, (0.22, 0.62, 0.45)), (0.2, GATE_GREEN), (1, GATE_GREEN_D)])
        ctx.set_source(g); ctx.rectangle(x0 - 14 * s, y - th - 10 * s, total + 28 * s, 76 * s); ctx.fill()
        ctx.set_source_rgba(1, 1, 1, 0.85); ctx.rectangle(x0 - 14 * s, y - th - 10 * s, total + 28 * s, 3 * s); ctx.fill()
        ctx.set_source_rgb(*GATE_WHITE); ctx.rectangle(x0 - 14 * s, y - th + 52 * s, total + 28 * s, 6 * s); ctx.fill()
        # number plates
        for i in range(n_stalls):
            cx = x0 + (i + 0.5) * SW
            col = _FRAME_COLS[i % 8]
            ctx.set_source_rgb(*col)
            ctx.rectangle(cx - 26 * s, y - th + 4 * s, 52 * s, 42 * s); ctx.fill()
            ctx.set_source_rgba(0.1, 0.1, 0.12, 0.8); ctx.set_line_width(2 * s)
            ctx.rectangle(cx - 26 * s, y - th + 4 * s, 52 * s, 42 * s); ctx.stroke()
            ctx.select_font_face("AnimeSans"); ctx.set_font_size(36 * s)
            txt = str(i + 1)
            xb, yb, tw, th_, xa, ya = ctx.text_extents(txt)
            lum = sum(col) / 3
            ctx.set_source_rgb(*((0.05, 0.05, 0.08) if lum > 0.55 or col == _FRAME_COLS[4] else (1, 1, 1)))
            ctx.move_to(cx - xa / 2, y - th + 39 * s); ctx.show_text(txt)
        # gate lamps (the red/green signal lamps on top)
        for side in (-1, 1):
            lx = x + side * (total / 2 + 4 * s)
            on = open > 0.02
            col = (0.2, 1.0, 0.4) if on else (1.0, 0.25, 0.2)
            _glow(ctx, lx, y - th - 22 * s, 30 * s, col, 0.7)
            ctx.set_source_rgb(*col); ctx.arc(lx, y - th - 22 * s, 7 * s, 0, TAU); ctx.fill()
        # floodlit rim on the truss top
        ctx.save(); ctx.translate(x, y - th - 8 * s); ctx.scale(1, 0.05)
        _glow(ctx, 0, 0, total * 0.6, (1, 0.95, 0.85), 0.5); ctx.restore()
    else:
        _gate_side(ctx, t, x, y, s, open, n_stalls, part="front")
    ctx.restore()


def _gate_side(ctx, t, x, y, s, open_, n, part):
    """Side view: nearest stall full size, further stalls receding up-left (3/4 feel).
    Horses run to the right; front doors on the right end swing toward +x."""
    L = 330 * s; Ht = 350 * s
    ang = _door_angle(open_)
    if part == "back":
        for k in range(n - 1, 0, -1):
            dx, dy, sc = -k * 16 * s, -k * 10 * s, 1 - 0.035 * k
            _gate_side_stall(ctx, x + dx, y + dy, s * sc, L * sc, Ht * sc, ang, dark=0.55 + 0.45 * (1 - k / n), near=False)
        # nearest stall's far side panel
        ctx.set_source_rgba(*GATE_GREEN_D, 0.95)
        ctx.rectangle(x - L / 2 + 10 * s, y - 250 * s - 8 * s, L - 20 * s, 150 * s); ctx.fill()
    else:
        _gate_side_stall(ctx, x, y, s, L, Ht, ang, dark=1.0, near=True)


def _gate_side_stall(ctx, x, y, s, L, Ht, ang, dark=1.0, near=True):
    col = tuple(c * dark for c in GATE_GREEN)
    cold = tuple(c * dark for c in GATE_GREEN_D)
    wht = tuple(c * (0.55 + 0.45 * dark) for c in GATE_WHITE)
    xb, xf = x - L / 2, x + L / 2
    # posts
    for px in (xb, xf):
        g = _lin(ctx, px - 8 * s, 0, px + 8 * s, 0, [(0, cold), (0.4, col), (1, cold)])
        ctx.set_source(g); ctx.rectangle(px - 8 * s, y - Ht, 16 * s, Ht); ctx.fill()
    # top beam
    ctx.set_source_rgb(*col); ctx.rectangle(xb - 20 * s, y - Ht - 8 * s, L + 40 * s, 46 * s); ctx.fill()
    ctx.set_source_rgb(*wht); ctx.rectangle(xb - 20 * s, y - Ht + 30 * s, L + 40 * s, 5 * s); ctx.fill()
    ctx.set_source_rgba(1, 1, 1, 0.8 * dark); ctx.rectangle(xb - 20 * s, y - Ht - 8 * s, L + 40 * s, 2.5 * s); ctx.fill()
    if near:
        # padded side panel with bars (horse visible through the gaps)
        py0, py1 = y - 262 * s, y - 108 * s
        ctx.set_source_rgba(*col, 0.96)
        ctx.rectangle(xb + 8 * s, py0, L - 16 * s, 26 * s); ctx.fill()
        ctx.rectangle(xb + 8 * s, py1 - 26 * s, L - 16 * s, 26 * s); ctx.fill()
        ctx.set_source_rgb(*wht)
        for k in range(1, 6):
            bx = xb + k * L / 6
            ctx.rectangle(bx - 3 * s, py0 + 26 * s, 6 * s, py1 - py0 - 52 * s); ctx.fill()
        ctx.set_source_rgba(1, 1, 1, 0.6); ctx.rectangle(xb + 8 * s, py0, L - 16 * s, 2.5 * s); ctx.fill()
        # wheel / base rail
        ctx.set_source_rgb(0.1, 0.1, 0.12); ctx.rectangle(xb - 20 * s, y - 14 * s, L + 40 * s, 10 * s); ctx.fill()
        for wx in (xb - 6 * s, xf + 6 * s):
            ctx.set_source_rgb(0.08, 0.08, 0.1); ctx.arc(wx, y - 12 * s, 16 * s, 0, TAU); ctx.fill()
            ctx.set_source_rgb(0.5, 0.5, 0.55); ctx.arc(wx, y - 12 * s, 6 * s, 0, TAU); ctx.fill()
    # front door: edge-on when closed; swings toward +x (toward camera-right)
    dw = 108 * s
    wv = dw * math.sin(ang)
    dt, db = y - 236 * s, y - 16 * s
    ctx.move_to(xf, dt); ctx.line_to(xf + wv, dt - wv * 0.12); ctx.line_to(xf + wv, db + wv * 0.06); ctx.line_to(xf, db); ctx.close_path()
    ctx.set_source_rgb(*wht); ctx.fill_preserve()
    ctx.set_source_rgb(*col); ctx.set_line_width(max(4 * s, 1)); ctx.stroke()
    if wv < 4 * s:
        ctx.set_source_rgb(*wht); ctx.rectangle(xf - 3 * s, dt, 6 * s, db - dt); ctx.fill()


def draw_starting_gate(ctx, t, x, y, scale=1.0, open=0.0, n_stalls=8, view="front", part="all"):
    """Green/white starting gate at ground point (x, y). part: 'back' | 'front' | 'all'.
    Draw order for horses: gate(part='back') -> horses -> gate(part='front')."""
    if part in ("back", "all"):
        draw_starting_gate_back(ctx, t, x, y, scale, open, n_stalls, view)
    if part in ("front", "all"):
        draw_starting_gate_front(ctx, t, x, y, scale, open, n_stalls, view)


# ======================================================================
#  STABLE (厩舎) interior
# ======================================================================
LAMP_PIVOT = (1010.0, 0.0)
LAMP_LEN = 250.0
WIN_RECT = (1440, 250, 280, 230)      # x, y, w, h of the small window
_STB = {}


def _wood_planks(h, w, board_w=(70, 110), seed=0, vertical=True, base=(0.42, 0.26, 0.15)):
    """numpy RGB albedo of weathered wooden boards."""
    r = np.random.default_rng(seed)
    if not vertical:
        return np.transpose(_wood_planks(w, h, board_w, seed, True, base), (1, 0, 2))
    img = np.zeros((h, w, 3), np.float32)
    grain = _fbm2(h, w, (6, 90), 4, seed=seed + 1)
    fine = _fbm2(h, w, (30, 300), 2, seed=seed + 2)
    x = 0
    boards = []
    while x < w:
        bw = int(r.integers(*board_w))
        boards.append((x, min(w, x + bw), r.uniform(0.75, 1.2), r.uniform(-0.04, 0.04)))
        x += bw
    b = np.array(base, np.float32)
    for (x0, x1, tone, hue) in boards:
        seg = slice(x0, x1)
        g = grain[:, seg]; f = fine[:, seg]
        v = tone * (0.8 + 0.35 * (g - 0.5) + 0.25 * (f - 0.5))
        img[:, seg] = b * v[..., None]
        img[:, seg, 0] *= 1 + hue
        # gap/shadow between boards
        img[:, x0:x0 + 3] *= 0.35
        img[:, x0 + 3:x0 + 5] *= 0.7
        if x1 - 2 > x0:
            img[:, x1 - 2:x1] = np.minimum(1, img[:, x1 - 2:x1] * 1.25)   # lit edge
        # knots
        for k in range(int(r.integers(0, 3))):
            ky = int(r.integers(10, h - 10)); kx = int(r.integers(x0 + 8, max(x0 + 9, x1 - 8)))
            yy, xx = np.ogrid[-12:13, -8:9]
            m = np.exp(-(yy ** 2 / 60.0 + xx ** 2 / 14.0))
            ys = slice(max(0, ky - 12), min(h, ky + 13)); xs = slice(max(0, kx - 8), min(w, kx + 9))
            mm = m[:ys.stop - ys.start, :xs.stop - xs.start]
            img[ys, xs] *= (1 - 0.45 * mm)[..., None]
    return img


def _stable_build():
    Wc, Hc = W, H
    floor_y = 800
    # ---------- albedo pass (numpy wood + cairo objects) ----------
    wall = _wood_planks(Hc, Wc, (80, 120), seed=3, base=(0.46, 0.29, 0.17))
    alb = np.concatenate([wall, np.ones((Hc, Wc, 1), np.float32)], 2)
    s = _np_to_surface(alb)
    c = cairo.Context(s)
    r = rng(31)
    # horizontal wall rails / beams
    for yb, hb in ((150, 44), (560, 22)):
        beam = _wood_planks(hb, Wc, (400, 700), seed=yb, vertical=False, base=(0.36, 0.22, 0.13))
        bs = _np_to_surface(np.concatenate([beam, np.ones((hb, Wc, 1), np.float32)], 2))
        c.set_source_surface(bs, 0, yb); c.paint()
        c.set_source_rgba(0, 0, 0, 0.35); c.rectangle(0, yb + hb, Wc, 8); c.fill()
    # ceiling: dark rafters
    g = _lin(c, 0, 0, 0, 150, [(0, (0.08, 0.05, 0.04)), (1, (0.2, 0.12, 0.08))])
    c.set_source(g); c.rectangle(0, 0, Wc, 150); c.fill()
    for i in range(-2, 12):
        x0 = i * 190
        c.set_source_rgb(0.12, 0.075, 0.05)
        c.move_to(x0, 150); c.line_to(x0 + 28, 150); c.line_to(x0 + 28 + (x0 - 960) * 0.35, 0); c.line_to(x0 + (x0 - 960) * 0.35, 0)
        c.close_path(); c.fill()
    c.set_source_rgb(0.18, 0.11, 0.07); c.rectangle(0, 40, Wc, 30); c.fill()
    # ---- window frame (glass painted later as emissive) ----
    wx, wy, ww, wh = WIN_RECT
    c.set_source_rgb(0.30, 0.19, 0.11)
    c.rectangle(wx - 22, wy - 22, ww + 44, wh + 44); c.fill()
    c.set_source_rgb(0.5, 0.33, 0.2); c.rectangle(wx - 30, wy + wh + 14, ww + 60, 16); c.fill()    # sill
    # ---- floor ----
    fl = _wood_planks(Hc - floor_y, Wc, (140, 220), seed=9, vertical=False, base=(0.34, 0.24, 0.16))
    fs = _np_to_surface(np.concatenate([fl * 0.9, np.ones((Hc - floor_y, Wc, 1), np.float32)], 2))
    c.set_source_surface(fs, 0, floor_y); c.paint()
    c.set_source_rgba(0.05, 0.03, 0.02, 0.6); c.rectangle(0, floor_y - 4, Wc, 10); c.fill()   # skirting shadow
    # straw scattered
    for i in range(2600):
        x = r.uniform(-20, Wc); y = floor_y + r.random() ** 0.7 * (Hc - floor_y)
        L = r.uniform(8, 30) * (0.6 + (y - floor_y) / 400)
        a = r.uniform(-0.5, 0.5) + (math.pi if r.random() < 0.5 else 0)
        col = r.choice([(0.85, 0.7, 0.35), (0.75, 0.58, 0.28), (0.95, 0.82, 0.5), (0.6, 0.45, 0.22)])
        c.set_source_rgba(*col, r.uniform(0.5, 0.95)); c.set_line_width(r.uniform(1.0, 2.2))
        c.move_to(x, y); c.line_to(x + math.cos(a) * L, y + math.sin(a) * L * 0.3); c.stroke()
    # ---- left: stall front (horse's stall) ----
    sx0, sx1 = -10, 640
    front = _wood_planks(Hc, sx1 - sx0, (60, 90), seed=21, base=(0.40, 0.24, 0.14))
    fs = _np_to_surface(np.concatenate([front, np.ones((Hc, sx1 - sx0, 1), np.float32)], 2))
    c.save(); c.rectangle(sx0, 0, sx1 - sx0, 1000); c.clip(); c.set_source_surface(fs, sx0, 0); c.paint(); c.restore()
    # stall opening (upper half open, dark interior)
    ox0, ox1, oy0, oy1 = 60, 560, 250, 640
    g = _lin(c, 0, oy0, 0, oy1, [(0, (0.05, 0.035, 0.03)), (0.7, (0.1, 0.07, 0.05)), (1, (0.16, 0.11, 0.07))])
    c.set_source(g); c.rectangle(ox0, oy0, ox1 - ox0, oy1 - oy0); c.fill()
    inner = _wood_planks(oy1 - oy0, ox1 - ox0, (70, 100), seed=41, base=(0.2, 0.12, 0.07))
    ins = _np_to_surface(np.concatenate([inner, np.full((oy1 - oy0, ox1 - ox0, 1), 0.55, np.float32)], 2))
    c.set_source_surface(ins, ox0, oy0); c.paint()
    g = _lin(c, ox0, 0, ox1, 0, [(0, (0, 0, 0, 0.55)), (0.5, (0, 0, 0, 0.15)), (1, (0, 0, 0, 0.45))])
    c.set_source(g); c.rectangle(ox0, oy0, ox1 - ox0, oy1 - oy0); c.fill()
    c.set_source_rgba(0.12, 0.07, 0.04, 0.9); c.rectangle(ox0 + 40, oy0 + 60, 200, 14); c.fill()   # hay rack
    for k in range(10):
        c.rectangle(ox0 + 44 + k * 20, oy0 + 74, 4, 60); c.fill()
    for i in range(60):   # hay glimpses inside
        x = r.uniform(ox0, ox1); y = r.uniform(oy1 - 60, oy1)
        c.set_source_rgba(0.6, 0.45, 0.2, 0.25); c.set_line_width(1.2)
        c.move_to(x, y); c.line_to(x + r.uniform(-14, 14), y - r.uniform(2, 8)); c.stroke()
    # lower Dutch door
    dy0, dy1 = 640, 985
    door = _wood_planks(dy1 - dy0, ox1 - ox0, (55, 75), seed=23, base=(0.46, 0.28, 0.16))
    ds = _np_to_surface(np.concatenate([door, np.ones((dy1 - dy0, ox1 - ox0, 1), np.float32)], 2))
    c.set_source_surface(ds, ox0, dy0); c.paint()
    c.set_source_rgb(0.3, 0.18, 0.1)
    for (xa, ya, xb, yb) in ((ox0, dy0, ox1, dy0 + 24), (ox0, dy1 - 24, ox1, dy1)):
        c.rectangle(xa, ya, xb - xa, yb - ya); c.fill()
    c.set_line_width(24); c.set_line_cap(cairo.LINE_CAP_BUTT)
    c.move_to(ox0 + 12, dy0 + 24); c.line_to(ox1 - 12, dy1 - 24); c.stroke()
    c.move_to(ox1 - 12, dy0 + 24); c.line_to(ox0 + 12, dy1 - 24); c.stroke()
    c.set_source_rgba(1, 0.85, 0.6, 0.25); c.set_line_width(2)
    c.move_to(ox0, dy0 + 1); c.line_to(ox1, dy0 + 1); c.stroke()
    # iron latch & hinges
    c.set_source_rgb(0.12, 0.12, 0.13)
    for yy in (dy0 + 50, dy1 - 60):
        c.rectangle(ox0 - 4, yy, 70, 12); c.fill()
    c.rectangle(ox1 - 60, dy0 + 150, 50, 10); c.fill()
    # name plate
    c.set_source_rgb(0.86, 0.78, 0.6); c.rectangle(ox0 + 150, dy0 + 60, 200, 64); c.fill()
    c.set_source_rgb(0.35, 0.22, 0.12); c.set_line_width(4); c.rectangle(ox0 + 150, dy0 + 60, 200, 64); c.stroke()
    c.select_font_face("AnimeSerif"); c.set_font_size(38)
    xb_, yb_, tw, th, xa, ya = c.text_extents("ハルカゼ")
    c.set_source_rgb(0.15, 0.08, 0.05); c.move_to(ox0 + 250 - xa / 2, dy0 + 106); c.show_text("ハルカゼ")
    # posts & top beam of stall front
    c.set_source_rgb(0.3, 0.18, 0.1)
    for px in (ox0 - 40, ox1):
        c.rectangle(px, 170, 40, 830); c.fill()
        c.set_source_rgba(1, 0.8, 0.55, 0.2); c.rectangle(px + 34, 170, 5, 830); c.fill(); c.set_source_rgb(0.3, 0.18, 0.1)
    c.rectangle(ox0 - 40, oy0 - 40, ox1 - ox0 + 80, 40); c.fill()
    # horseshoe above stall opening
    c.set_source_rgb(0.5, 0.48, 0.45); c.set_line_width(9)
    c.arc_negative(310, oy0 - 70, 22, math.pi * 0.15, math.pi * 0.85); c.stroke()
    # halter rope on the post
    c.set_source_rgb(0.7, 0.2, 0.18); c.set_line_width(6)
    c.move_to(ox1 + 20, 420); c.curve_to(ox1 + 70, 520, ox1 + 30, 620, ox1 + 60, 700); c.stroke()
    c.arc(ox1 + 20, 420, 8, 0, TAU); c.set_source_rgb(0.2, 0.2, 0.2); c.fill()
    # ---- tack on the back wall ----
    for i, bx in enumerate((830, 930, 1330)):
        _bridle(c, bx, 380 + i * 12, 1.0 if i != 2 else 0.9, r)
    _saddle(c, 1120, 640)
    _poster(c, 1105, 225, 150, 200)
    _bucket(c, 740, 960)
    # ---- hay bales right ----
    for (bx, by, bw, bh) in ((1560, 770, 330, 150), (1460, 880, 330, 160), (1780, 880, 330, 160), (1640, 660, 300, 120)):
        _hay_bale(c, r, bx, by, bw, bh)
    s.flush()
    albedo = _surface_to_np(s)       # premul BGRA
    # ---------- lighting ----------
    yy, xx = np.mgrid[0:Hc, 0:Wc].astype(np.float32)
    lx, ly = LAMP_PIVOT[0], LAMP_PIVOT[1] + LAMP_LEN + 40
    d2 = ((xx - lx) ** 2 + ((yy - ly) * 1.15) ** 2)
    lamp = 2.1 / (1 + d2 / (400.0 ** 2)) ** 1.25
    # the lamp shade blocks light going up: darker ceiling
    lamp *= np.clip(0.35 + (yy - (ly - 60)) / 200.0, 0.35, 1.0)
    warm = np.array([1.0, 0.72, 0.42], np.float32)
    amb = np.array([0.36, 0.27, 0.33], np.float32)
    # warm bounce light from the floor / hay (fills the left stall a little)
    bounce = 0.45 * np.exp(-(((xx - 700) / 900) ** 2 + ((yy - 900) / 500) ** 2))
    amb = amb + bounce[..., None] * np.array([0.5, 0.32, 0.16], np.float32)
    L = amb + lamp[..., None] * warm
    # cool moonlight shaft from the window going down-left
    wx, wy, ww, wh = WIN_RECT
    t_ = (yy - wy) / 600.0
    shaft = ((xx > wx - t_ * 380) & (xx < wx + ww - t_ * 380) & (yy > wy)).astype(np.float32)
    shaft = _ndi.gaussian_filter(shaft, 18) * np.clip(1 - t_, 0, 1)
    L = L + shaft[..., None] * np.array([0.22, 0.3, 0.55], np.float32)
    # vignette / falloff at the far edges
    vig = np.clip(1.15 - 0.45 * (((xx - 960) / 1100) ** 2 + ((yy - 520) / 700) ** 2), 0.45, 1)
    L = L * vig[..., None]
    lit = albedo.copy()
    lit[..., 0] *= L[..., 2]; lit[..., 1] *= L[..., 1]; lit[..., 2] *= L[..., 0]
    # soft tone curve (keeps highlights warm, not clipped)
    lit[..., :3] = 1 - np.exp(-lit[..., :3] * 1.25)
    out = _np_premul_to_surface(lit)
    c = cairo.Context(out)
    # ---------- emissive: window with night sky ----------
    _stable_window(c)
    return dict(surf=out)


def _bridle(c, x, y, s, r):
    c.save()
    c.set_source_rgb(0.25, 0.25, 0.27); c.arc(x, y, 7 * s, 0, TAU); c.fill()   # peg
    c.set_source_rgb(0.32, 0.17, 0.09); c.set_line_width(7 * s); c.set_line_cap(cairo.LINE_CAP_ROUND)
    c.move_to(x, y); c.curve_to(x - 40 * s, y + 60 * s, x - 36 * s, y + 140 * s, x - 10 * s, y + 190 * s); c.stroke()
    c.move_to(x, y); c.curve_to(x + 40 * s, y + 60 * s, x + 36 * s, y + 140 * s, x + 10 * s, y + 190 * s); c.stroke()
    c.move_to(x - 34 * s, y + 90 * s); c.line_to(x + 34 * s, y + 90 * s); c.stroke()      # browband
    c.set_source_rgb(0.75, 0.72, 0.68); c.set_line_width(4 * s)
    c.arc(x - 12 * s, y + 200 * s, 12 * s, 0, TAU); c.stroke(); c.arc(x + 12 * s, y + 200 * s, 12 * s, 0, TAU); c.stroke()
    c.set_source_rgb(0.32, 0.17, 0.09); c.set_line_width(5 * s)
    c.move_to(x - 12 * s, y + 212 * s); c.curve_to(x - 30 * s, y + 300 * s, x + 30 * s, y + 300 * s, x + 12 * s, y + 212 * s); c.stroke()
    c.restore()


def _poster(c, x, y, w, h):
    """Faded Twinkle race poster pinned on the wall."""
    c.save()
    c.translate(x + w / 2, y + h / 2); c.rotate(-0.03); c.translate(-w / 2, -h / 2)
    c.set_source_rgba(0, 0, 0, 0.35); c.rectangle(4, 6, w, h); c.fill()
    g = _lin(c, 0, 0, 0, h, [(0, (0.12, 0.14, 0.38)), (0.6, (0.55, 0.3, 0.55)), (1, (0.95, 0.6, 0.45))])
    c.set_source(g); c.rectangle(0, 0, w, h); c.fill()
    for k in range(12):
        c.set_source_rgba(1, 1, 0.9, 0.8); c.arc(10 + (k * 37) % (w - 20), 10 + (k * 23) % 70, 1.5, 0, TAU); c.fill()
    # big star + horseshoe emblem
    c.save(); c.translate(w * 0.5, h * 0.5)
    c.set_source_rgba(1, 0.85, 0.5, 0.9); c.set_line_width(9)
    c.arc_negative(0, 6, 34, math.pi * 0.2, math.pi * 0.8); c.stroke()
    c.set_source_rgb(1, 0.95, 0.8)
    for k in range(10):
        a_ = -math.pi / 2 + k * math.pi / 5
        rr_ = 20 if k % 2 == 0 else 8
        (c.move_to if k == 0 else c.line_to)(math.cos(a_) * rr_, -4 + math.sin(a_) * rr_)
    c.close_path(); c.fill()
    c.restore()
    c.select_font_face("AnimeDela"); c.set_font_size(22)
    xb, yb, tw, th, xa, ya = c.text_extents("TWINKLE")
    c.set_source_rgb(1, 0.85, 0.9); c.move_to(w / 2 - xa / 2, h - 18); c.show_text("TWINKLE")
    c.set_source_rgba(1, 0.95, 0.85, 0.15); c.rectangle(0, 0, w, h); c.fill()      # fading
    c.set_source_rgb(0.7, 0.7, 0.72)
    for (px, py) in ((6, 6), (w - 6, 6)):
        c.arc(px, py, 3, 0, TAU); c.fill()
    c.restore()


def _saddle(c, x, y):
    c.save()
    c.set_source_rgb(0.25, 0.25, 0.27); c.rectangle(x - 8, y - 20, 16, 60); c.fill()       # rack arm
    # saddle cloth (white with red trim - Mizuki's colours) with number 14
    c.set_source_rgb(0.9, 0.9, 0.92)
    c.move_to(x - 125, y - 30); c.line_to(x + 115, y - 40); c.line_to(x + 110, y + 90); c.line_to(x - 118, y + 96); c.close_path(); c.fill()
    c.set_source_rgb(*PAL["silk_accent"])
    c.move_to(x - 118, y + 82); c.line_to(x + 110, y + 76); c.line_to(x + 110, y + 90); c.line_to(x - 118, y + 96); c.close_path(); c.fill()
    c.set_source_rgba(0.1, 0.1, 0.12, 0.85); c.select_font_face("AnimeSans"); c.set_font_size(38)
    c.move_to(x + 30, y + 64); c.show_text("14")
    # flap
    g = _lin(c, 0, y - 40, 0, y + 60, [(0, (0.5, 0.28, 0.13)), (1, (0.32, 0.17, 0.08))])
    c.set_source(g)
    c.move_to(x - 70, y - 40); c.line_to(x + 10, y - 40); c.curve_to(x + 20, y + 10, x + 10, y + 50, x - 10, y + 62)
    c.line_to(x - 60, y + 62); c.curve_to(x - 80, y + 40, x - 82, y - 10, x - 70, y - 40); c.close_path(); c.fill()
    c.set_source_rgba(1, 0.8, 0.55, 0.25); c.set_line_width(2)
    c.move_to(x - 66, y - 34); c.curve_to(x - 76, y - 5, x - 74, y + 36, x - 58, y + 56); c.stroke()
    # seat, pommel & cantle
    g = _lin(c, 0, y - 90, 0, y - 30, [(0, (0.7, 0.42, 0.2)), (1, (0.42, 0.23, 0.1))])
    c.set_source(g)
    c.move_to(x - 120, y - 30); c.curve_to(x - 118, y - 62, x - 104, y - 74, x - 92, y - 70)
    c.curve_to(x - 60, y - 48, x - 10, y - 44, x + 30, y - 52)
    c.curve_to(x + 70, y - 62, x + 88, y - 92, x + 104, y - 88); c.curve_to(x + 116, y - 70, x + 118, y - 50, x + 112, y - 36)
    c.close_path(); c.fill()
    c.set_source_rgba(1, 0.85, 0.6, 0.5); c.set_line_width(2.5)
    c.move_to(x - 104, y - 72); c.curve_to(x - 60, y - 50, x - 10, y - 46, x + 30, y - 54); c.curve_to(x + 70, y - 64, x + 88, y - 92, x + 104, y - 88)
    c.stroke()
    c.restore()


def _bucket(c, x, y):
    g = _lin(c, x - 50, 0, x + 50, 0, [(0, (0.3, 0.32, 0.36)), (0.4, (0.62, 0.64, 0.68)), (1, (0.25, 0.26, 0.3))])
    c.set_source(g)
    c.move_to(x - 55, y - 100); c.line_to(x + 55, y - 100); c.line_to(x + 44, y); c.line_to(x - 44, y); c.close_path(); c.fill()
    c.set_source_rgb(0.7, 0.72, 0.75); c.save(); c.translate(x, y - 100); c.scale(1, 0.25); c.arc(0, 0, 55, 0, TAU); c.restore()
    c.set_line_width(3); c.stroke()
    c.set_source_rgba(0, 0, 0, 0.4); c.save(); c.translate(x, y); c.scale(1, 0.2); c.arc(0, 0, 60, 0, TAU); c.restore(); c.fill()


def _hay_bale(c, r, x, y, w, h):
    def rr_path():
        rad = 16
        c.new_path()
        c.arc(x + rad, y + rad, rad, math.pi, 1.5 * math.pi); c.arc(x + w - rad, y + rad, rad, 1.5 * math.pi, 0)
        c.arc(x + w - rad, y + h - rad, rad, 0, 0.5 * math.pi); c.arc(x + rad, y + h - rad, rad, 0.5 * math.pi, math.pi)
        c.close_path()
    rr_path()
    g = _lin(c, 0, y, 0, y + h, [(0, (0.98, 0.84, 0.5)), (0.25, (0.88, 0.7, 0.36)), (1, (0.5, 0.36, 0.17))])
    c.set_source(g); c.fill()
    c.save(); rr_path(); c.clip()
    for i in range(int(w * h / 22)):
        px = r.uniform(x - 10, x + w); py = r.uniform(y, y + h)
        f = (py - y) / h
        col = r.choice([(1.0, 0.92, 0.62), (0.72, 0.55, 0.25), (0.9, 0.76, 0.42), (0.55, 0.4, 0.18)])
        a = r.uniform(0.35, 0.75)
        c.set_source_rgba(col[0] * (1 - 0.4 * f), col[1] * (1 - 0.4 * f), col[2] * (1 - 0.4 * f), a)
        c.set_line_width(r.uniform(0.9, 2.0))
        c.move_to(px, py); c.line_to(px + r.uniform(8, 26), py + r.uniform(-4, 4)); c.stroke()
    g = _lin(c, 0, y, 0, y + 24, [(0, (1, 0.95, 0.75, 0.5)), (1, (1, 0.95, 0.75, 0))])
    c.set_source(g); c.rectangle(x, y, w, 24); c.fill()
    c.restore()
    c.set_source_rgba(0.35, 0.18, 0.08, 0.85); c.set_line_width(4)
    for f in (0.28, 0.72):
        c.move_to(x + w * f, y + 2); c.curve_to(x + w * f + 4, y + h * 0.4, x + w * f - 4, y + h * 0.7, x + w * f, y + h - 2); c.stroke()
    for i in range(60):   # stray straws on the edges
        px = x + r.uniform(0, w); py = y + r.choice((0, 0, h))
        c.set_source_rgba(0.95, 0.82, 0.5, 0.8); c.set_line_width(1.4)
        c.move_to(px, py); c.line_to(px + r.uniform(-14, 14), py + r.uniform(-12, 8)); c.stroke()


def _stable_window(c):
    wx, wy, ww, wh = WIN_RECT
    c.save()
    c.rectangle(wx, wy, ww, wh); c.clip()
    g = _lin(c, 0, wy, 0, wy + wh, [(0, (0.04, 0.05, 0.16)), (0.6, (0.14, 0.1, 0.3)), (1, (0.45, 0.25, 0.38))])
    c.set_source(g); c.paint()
    r = rng(12)
    for i in range(40):
        c.set_source_rgba(1, 1, 1, r.uniform(0.3, 0.9)); c.arc(wx + r.uniform(0, ww), wy + r.uniform(0, wh * 0.6), r.uniform(0.6, 1.4), 0, TAU); c.fill()
    # distant floodlights & grandstand glow on the horizon
    _glow(c, wx + ww * 0.55, wy + wh * 0.95, 180, (1.0, 0.8, 0.55), 0.55)
    for k, fx in enumerate((0.25, 0.6, 0.88)):
        px, py = wx + ww * fx, wy + wh * (0.62 + 0.04 * k)
        c.set_source_rgba(0.1, 0.1, 0.15, 1); c.rectangle(px - 1, py, 2, wh); c.fill()
        _glow(c, px, py, 46, FLOOD, 0.7)
        c.set_source_rgb(1, 1, 0.95); c.rectangle(px - 6, py - 3, 12, 6); c.fill()
    # tree silhouettes
    c.set_source_rgb(0.03, 0.04, 0.07)
    for i in range(14):
        c.arc(wx + r.uniform(-20, ww + 20), wy + wh + r.uniform(-50, 0), r.uniform(18, 36), 0, TAU); c.fill()
    c.restore()
    # muntins
    c.set_source_rgb(0.24, 0.15, 0.09)
    c.rectangle(wx + ww / 2 - 6, wy, 12, wh); c.fill()
    c.rectangle(wx, wy + wh / 2 - 6, ww, 12); c.fill()
    # glass sheen
    c.save(); c.rectangle(wx, wy, ww, wh); c.clip()
    g = _lin(c, wx, wy, wx + ww, wy + wh, [(0, (1, 1, 1, 0)), (0.35, (1, 1, 1, 0.1)), (0.45, (1, 1, 1, 0)), (1, (1, 1, 1, 0))])
    c.set_source(g); c.paint(); c.restore()


def _stable():
    if not _STB:
        _STB.update(_disk_dict("stable", _stable_build))
    return _STB


def draw_stable(ctx, t, *, lamp_swing=0.0, dust=1.0, night_window=True, lamp_on=1.0):
    """Warm old wooden stable interior. Left third: stall opening (horse head enters
    from the left); centre/right: aisle for characters. lamp_swing = swing amplitude
    (0..1, ~0.12 rad max); dust = amount of floating dust motes."""
    S = _stable()
    _blit(ctx, S["surf"], 0, 0)
    if night_window:
        wx, wy, ww, wh = WIN_RECT
        for k, fx in enumerate((0.25, 0.6, 0.88)):      # twinkle of distant floodlights
            px, py = wx + ww * fx, wy + wh * (0.62 + 0.04 * k)
            ctx.save(); ctx.rectangle(wx, wy, ww, wh); ctx.clip()
            _glow(ctx, px, py, 30, FLOOD, 0.25 + 0.15 * math.sin(t * 5 + k))
            ctx.restore()
    ang = lamp_swing * 0.12 * math.sin(t * 1.9)
    px, py = LAMP_PIVOT
    lx = px + math.sin(ang) * LAMP_LEN
    ly = py + math.cos(ang) * LAMP_LEN
    # dynamic light shift (small, follows the swing)
    dx = lx - px
    if abs(dx) > 0.5:
        ctx.save(); ctx.set_operator(cairo.OPERATOR_ADD)
        _glow(ctx, lx + dx * 2.0, ly + 260, 700, (0.35, 0.22, 0.1), 0.35 * min(1, abs(dx) / 30))
        ctx.restore()
    # cord
    ctx.set_source_rgb(0.08, 0.06, 0.05); ctx.set_line_width(3)
    ctx.move_to(px, py); ctx.line_to(lx, ly); ctx.stroke()
    # lamp: enamel shade + bulb
    ctx.save(); ctx.translate(lx, ly); ctx.rotate(-ang)
    _glow(ctx, 0, 40, 420, WARM, 0.35 * lamp_on)
    _glow(ctx, 0, 40, 150, (1.0, 0.85, 0.6), 0.6 * lamp_on)
    g = _lin(ctx, -70, 0, 70, 0, [(0, (0.12, 0.2, 0.18)), (0.45, (0.28, 0.42, 0.36)), (1, (0.08, 0.14, 0.13))])
    ctx.set_source(g)
    ctx.move_to(-12, 0); ctx.line_to(12, 0); ctx.line_to(72, 38); ctx.line_to(-72, 38); ctx.close_path(); ctx.fill()
    ctx.set_source_rgba(1, 0.85, 0.6, 0.9 * lamp_on); ctx.save(); ctx.scale(1, 0.18); ctx.arc(0, 38 / 0.18, 72, 0, math.pi); ctx.restore()
    ctx.set_line_width(3); ctx.stroke()
    ctx.set_source_rgb(0.2, 0.18, 0.16); ctx.rectangle(-8, -10, 16, 14); ctx.fill()
    g = cairo.RadialGradient(0, 46, 0, 0, 46, 22)
    g.add_color_stop_rgb(0, 1, 1, 0.95); g.add_color_stop_rgb(0.6, 1, 0.9, 0.6); g.add_color_stop_rgb(1, 1, 0.7, 0.35)
    ctx.set_source(g); ctx.arc(0, 46, 20, 0, TAU); ctx.fill()
    ctx.restore()
    # light cone under the lamp (volumetric)
    ctx.save(); ctx.set_operator(cairo.OPERATOR_ADD)
    ca, sa = math.cos(-ang), math.sin(-ang)
    def rot(x, y):
        return lx + x * ca - y * sa, ly + x * sa + y * ca
    for k, (wt, wb, a) in enumerate(((66, 600, 0.035), (60, 480, 0.04), (52, 360, 0.045), (40, 240, 0.05))):
        g = cairo.LinearGradient(lx, ly + 40, lx, ly + 780)
        g.add_color_stop_rgba(0, 1, 0.78, 0.5, a * lamp_on); g.add_color_stop_rgba(0.6, 1, 0.78, 0.5, a * 0.5 * lamp_on)
        g.add_color_stop_rgba(1, 1, 0.75, 0.45, 0)
        ctx.set_source(g)
        ctx.move_to(*rot(-wt, 38)); ctx.line_to(*rot(wt, 38)); ctx.line_to(*rot(wb, 780)); ctx.line_to(*rot(-wb, 780)); ctx.close_path(); ctx.fill()
    ctx.restore()
    if dust > 0:
        _dust_motes(ctx, t, lx, ly + 40, dust)


def _dust_motes(ctx, t, lx, ly, amount):
    n = int(160 * amount)
    for i in range(n):
        bx = _hash(i, 81) * W
        by = _hash(i, 82) * H * 0.9
        sp = 6 + 14 * _hash(i, 83)
        x = bx + math.sin(t * 0.35 + i) * 30 + t * sp * 0.3
        y = (by - t * sp * 0.5 + 40 * math.sin(t * 0.5 + i * 1.7)) % (H * 0.9)
        x = x % W
        d = math.hypot(x - lx, (y - ly) * 1.2)
        lit = clamp(1.35 - d / 700)
        if lit <= 0.02:
            continue
        rad = 1.0 + 2.8 * _hash(i, 84)
        tw = 0.6 + 0.4 * math.sin(t * 2 + i * 3.1)
        a = lit * tw * amount * 0.8
        if rad > 2.6:
            _glow(ctx, x, y, rad * 5, (1, 0.85, 0.6), a * 0.4)
        ctx.set_source_rgba(1, 0.92, 0.75, a)
        ctx.arc(x, y, rad * 0.6, 0, TAU); ctx.fill()


# ======================================================================
#  HOME STRAIGHT PERSPECTIVE (low 3/4 view toward the finish)
# ======================================================================
PS_F, PS_H = 950.0, 2.4            # focal px, camera height m
PS_LEN = 300.0                    # progress 0..1 covers the last 300 m
PS_XO, PS_XI, PS_XS = -16.0, 9.0, -27.0   # outer rail, inner rail, stand face (m)
_PS = {}


def _ps_tex():
    if not _PS:
        _PS.update(_disk_dict("persp", _ps_tex_build))
    return _PS


def _ps_tex_build():
    _PS = {}
    # crowd tile for stand faces (tileable horizontally)
    TWc, THc = 600, 300
    s, c = _surf(TWc, THc)
    g = _lin(c, 0, 0, 0, THc, [(0, (0.45, 0.3, 0.3)), (1, (0.7, 0.52, 0.44))])
    c.set_source(g); c.paint()
    r = rng(606)
    for k in range(16):
        _tiny_crowd_row(c, r, -10, TWc + 10, 12 + k * 18.5, 5.2, 1.0 + 0.02 * k, 0.95, None,
                        tone=(0.42, 0.3, 0.34), mute=0.55)
    for k in range(5, 16, 6):
        c.set_source_rgba(0.95, 0.85, 0.8, 0.5); c.rectangle(0, 12 + k * 18.5 - 4, TWc, 3); c.fill()
    _PS["crowd"] = _blur_surface(s, 0.6)
    # glass band tile
    s2, c2 = _surf(600, 120)
    g = _lin(c2, 0, 0, 0, 120, [(0, (1.0, 0.9, 0.66)), (0.6, (1.0, 0.72, 0.45)), (1, (0.85, 0.5, 0.35))])
    c2.set_source(g); c2.paint()
    for xx in range(0, 600, 75):
        c2.set_source_rgba(0.15, 0.1, 0.14, 0.9); c2.rectangle(xx, 0, 5, 120); c2.fill()
    for i in range(40):
        x = r.uniform(0, 600); hh = r.uniform(40, 60)
        c2.set_source_rgba(0.35, 0.2, 0.18, 0.6); c2.arc(x, 120 - hh, 8, 0, TAU); c2.fill()
        c2.rectangle(x - 10, 120 - hh + 8, 20, hh); c2.fill()
    _PS["glass"] = s2
    s3, c3 = _surf(600, 140)
    r3 = rng(612)
    for i in range(70):
        x = r3.uniform(-20, 620); y = r3.uniform(20, 110); rr_ = r3.uniform(20, 42)
        g = cairo.RadialGradient(x - rr_ * 0.3, y - rr_ * 0.4, 0, x, y, rr_)
        g.add_color_stop_rgb(0, 0.12, 0.18, 0.2); g.add_color_stop_rgb(1, 0.04, 0.06, 0.08)
        c3.set_source(g); c3.arc(x, y, rr_, 0, TAU); c3.fill()
    c3.set_source_rgb(0.04, 0.06, 0.08); c3.rectangle(0, 100, 600, 40); c3.fill()
    _PS["trees"] = s3
    # top-down dirt texture (tileable)
    TD = 512
    rr = np.random.default_rng(66)
    blot = _fbm2(TD, TD, (4, 4), 5, seed=67)
    streak = _fbm2(TD, TD, (3, 60), 3, seed=68)
    sp = rr.random((TD, TD)).astype(np.float32)
    dark = _ndi.gaussian_filter((sp < 0.04).astype(np.float32), 1.3, mode="wrap")
    lite = _ndi.gaussian_filter((sp > 0.97).astype(np.float32), 0.8, mode="wrap")
    v = 0.92 + 0.25 * (blot - 0.5) + 0.2 * (streak - 0.5) - 1.6 * dark + 1.0 * lite
    base = np.array([0.62, 0.47, 0.36], np.float32)
    img = base * v[..., None]
    _PS["dirt"] = _np_to_surface(np.concatenate([img, np.ones((TD, TD, 1), np.float32)], 2))
    return _PS


def _inv(m):
    m = cairo.Matrix(*m)
    m.invert()
    return m


def _pp(X, Z, Y, vx, vy):
    return vx + PS_F * X / Z, vy + PS_F * (PS_H - Y) / Z


def _ps_wall(ctx, tex, X, Y0, Y1, za, zb, tex_u0, tex_u1, vx, vy, alpha=1.0):
    """Paint a texture on a vertical wall plane X=const between depths za<zb (screen Z)."""
    xa, ya0 = _pp(X, za, Y0, vx, vy); _, ya1 = _pp(X, za, Y1, vx, vy)
    xb, yb0 = _pp(X, zb, Y0, vx, vy); _, yb1 = _pp(X, zb, Y1, vx, vy)
    tw, th = tex.get_width(), tex.get_height()
    ctx.save()
    ctx.move_to(xa, ya1); ctx.line_to(xb, yb1); ctx.line_to(xb, yb0); ctx.line_to(xa, ya0); ctx.close_path()
    ctx.clip()
    # affine: u -> x (xa..xb), v -> y ; use mid-height slope approximation
    du = tex_u1 - tex_u0
    sx_ = (xb - xa) / du
    hA = ya0 - ya1; hB = yb0 - yb1
    hm = (hA + hB) / 2
    shear = ((yb1 + yb0) / 2 - (ya1 + ya0) / 2) / du
    m = cairo.Matrix(sx_, shear, 0, hm / th, xa - tex_u0 * sx_, (ya1 + ya0) / 2 - hm / 2 - shear * tex_u0)
    ctx.transform(m)
    pat = cairo.SurfacePattern(tex); pat.set_extend(cairo.EXTEND_REPEAT); pat.set_filter(cairo.FILTER_BILINEAR)
    ctx.set_source(pat)
    ctx.paint_with_alpha(alpha)
    ctx.restore()


def draw_track_straight_perspective(ctx, t, progress, *, vanish=(960, 430), flash=0.0, blur=0.0, finish=True):
    """Low 3/4 view down the home straight: rails converging to `vanish`, glowing
    grandstand on the left, floodlights rushing past, the finish post approaching
    (progress 0 = 300 m out, 1 = at the post)."""
    T = _ps_tex()
    S = _side()
    vx, vy = vanish
    camz = clamp(progress, 0, 1.2) * PS_LEN
    f = PS_F
    draw_sky(ctx, t, horizon_y=vy, stars=0.6, moon=(vx + 520, vy - 300, 34), clouds=0.4, glow=1.0)
    draw_city(ctx, t, vy + 2, cam_x=0, parallax=0, scale=0.3, lights=1.0, tower=True)
    # distant glow at the vanishing point (finish area floodlights)
    ctx.save(); ctx.translate(vx, vy); ctx.scale(1, 0.4)
    _glow(ctx, 0, 0, 700, (1, 0.8, 0.6), 0.35); ctx.restore()
    # ---- ground ----
    zn = 1.2
    tex = T["dirt"]
    TD = tex.get_width()
    mt = 12.0                 # metres per texture tile
    pat = cairo.SurfacePattern(tex); pat.set_extend(cairo.EXTEND_REPEAT); pat.set_filter(cairo.FILTER_BILINEAR)
    y = int(vy) + 1
    while y < H + 2:
        bh = 3 if y < vy + 60 else (6 if y < vy + 200 else 10)
        ym = y + bh / 2
        zm = f * PS_H / (ym - vy)
        dzdy = -f * PS_H / (ym - vy) ** 2
        a_ = mt / TD * f / zm
        d_ = (mt / TD) / dzdy
        x0_ = vx + PS_XO * f / zm
        y0_ = ym - (camz + zm) / dzdy
        pat.set_matrix(cairo.Matrix(a_, 0, 0, d_, x0_, y0_).multiply(cairo.Matrix()) if False else _inv(cairo.Matrix(a_, 0, 0, d_, x0_, y0_)))
        ctx.save(); ctx.rectangle(-200, y, W + 400, bh); ctx.clip(); ctx.set_source(pat)
        ctx.paint(); ctx.restore()
        y += bh
    # distance tint & near darkening
    ctx.set_source(_lin(ctx, 0, vy, 0, H, [(0, (0.95, 0.72, 0.62, 0.75)), (0.08, (0.8, 0.6, 0.5, 0.3)), (0.3, (0.6, 0.45, 0.35, 0.0)),
                                           (1, (0.12, 0.06, 0.06, 0.45))]))
    ctx.rectangle(-200, vy, W + 400, H - vy + 200); ctx.fill()
    # infield (right of inner rail) & apron (left of outer rail)
    xi, yi = _pp(PS_XI + 0.3, zn, 0, vx, vy)
    ctx.move_to(vx, vy); ctx.line_to(xi, yi); ctx.line_to(W + 4000, H + 4000); ctx.line_to(W + 4000, vy); ctx.close_path()
    ctx.set_source(_lin(ctx, 0, vy, 0, H, [(0, (0.16, 0.22, 0.24)), (0.2, (0.1, 0.17, 0.17)), (1, (0.04, 0.08, 0.08))])); ctx.fill()
    xa, ya = _pp(PS_XO - 0.3, zn, 0, vx, vy)
    ctx.move_to(vx, vy); ctx.line_to(xa, ya); ctx.line_to(-4000, H + 4000); ctx.line_to(-4000, vy); ctx.close_path()
    ctx.set_source(_lin(ctx, 0, vy, 0, H, [(0, (0.35, 0.3, 0.36)), (1, (0.2, 0.17, 0.2))])); ctx.fill()
    # infield treeline + big screen
    for k in range(int(camz // 20), int((camz + 500) // 20) + 1):
        za, zb = max(zn, k * 20 - camz), (k + 1) * 20 - camz
        if zb > za:
            _ps_wall(ctx, T["trees"], PS_XI + 55, 0, 7, za, zb, (k % 4) * 150.0, (k % 4) * 150.0 + 150, vx, vy)
    Zs = PS_LEN + 80 - camz
    if Zs > 5:
        sx0, sy0 = _pp(PS_XI + 40, Zs, 8, vx, vy); sx1, sy1 = _pp(PS_XI + 40, Zs + 40, 20, vx, vy)
        _ps_quad(ctx, PS_XI + 40, 6, 20, Zs, Zs + 40, vx, vy, (0.05, 0.05, 0.08))
        _ps_quad(ctx, PS_XI + 39.8, 7, 19, Zs + 1, Zs + 39, vx, vy, (0.3, 0.8, 1.0))
        cxm, cym = _pp(PS_XI + 40, Zs + 20, 13, vx, vy)
        _glow(ctx, cxm, cym, f * 30 / Zs + 30, (0.4, 0.8, 1.0), 0.35)
    # floodlight sheen on dirt
    ctx.save(); ctx.set_operator(cairo.OPERATOR_ADD)
    for k in range(int(camz // 60) - 1, int((camz + 600) // 60) + 1):
        Z = k * 60 + 20 - camz
        if Z < 2:
            continue
        xm, ym = _pp(-4, Z, 0, vx, vy)
        ctx.save(); ctx.translate(xm, ym); ctx.scale(1, 0.25)
        _glow(ctx, 0, 0, f * 14 / Z, (1, 0.85, 0.65), 0.22); ctx.restore()
    ctx.restore()
    # ---- grandstand (left) ----
    Ls = 6.0
    zmax = 520.0
    k0 = int(camz // Ls)
    secs = []
    for k in range(k0, int((camz + zmax) // Ls) + 1):
        za, zb = k * Ls - camz, (k + 1) * Ls - camz
        za = max(za, zn)
        if zb <= za:
            continue
        secs.append((k, za, zb))
    for (k, za, zb) in reversed(secs):
        u0 = (k % 5) * 120.0
        # apron wall LED ribbon
        _ps_quad(ctx, PS_XS, 0, 1.3, za, zb, vx, vy, (0.05, 0.05, 0.1))
        _ps_quad(ctx, PS_XS + 0.01, 0.45, 0.85, za, zb, vx, vy, (0.35, 0.85, 1.0) if k % 3 else (1, 0.8, 0.4))
        _ps_wall(ctx, T["crowd"], PS_XS, 1.3, 12.0, za, zb, u0, u0 + 120, vx, vy)
        _ps_quad(ctx, PS_XS, 12.0, 12.6, za, zb, vx, vy, (0.9, 0.88, 0.86))
        _ps_wall(ctx, T["glass"], PS_XS - 0.5, 12.6, 16.0, za, zb, u0, u0 + 120, vx, vy)
        _ps_quad(ctx, PS_XS - 0.5, 16.0, 16.6, za, zb, vx, vy, (0.9, 0.88, 0.86))
        _ps_wall(ctx, T["crowd"], PS_XS - 1.0, 16.6, 25.0, za, zb, u0 + 300, u0 + 420, vx, vy, alpha=0.85)
        # roof underside (seen from below): dark with downlights
        xa0, ya0 = _pp(PS_XS - 1, za, 25.0, vx, vy); xb0, yb0 = _pp(PS_XS - 1, zb, 25.0, vx, vy)
        xa1, ya1 = _pp(PS_XS + 7, za, 27.0, vx, vy); xb1, yb1 = _pp(PS_XS + 7, zb, 27.0, vx, vy)
        ctx.move_to(xa0, ya0); ctx.line_to(xb0, yb0); ctx.line_to(xb1, yb1); ctx.line_to(xa1, ya1); ctx.close_path()
        ctx.set_source_rgb(0.07, 0.06, 0.11); ctx.fill()
        for q in range(2):
            zz = za + (zb - za) * (q + 0.5) / 2
            lx_, ly_ = _pp(PS_XS + 2, zz, 25.6, vx, vy)
            _glow(ctx, lx_, ly_, f * 1.6 / zz, (1, 0.88, 0.65), 0.55)
        # roof edge line
        ctx.move_to(xa1, ya1); ctx.line_to(xb1, yb1); ctx.set_source_rgba(0.95, 0.92, 1, 0.9)
        ctx.set_line_width(max(1, f * 0.12 / za)); ctx.stroke()
        # columns every 3rd section
        if k % 3 == 0:
            xc0, yc0 = _pp(PS_XS + 0.2, za, 0, vx, vy); xc1, yc1 = _pp(PS_XS + 0.2, za, 25, vx, vy)
            ctx.set_source_rgb(0.1, 0.09, 0.15); ctx.rectangle(xc0 - f * 0.25 / za, yc1, f * 0.5 / za, yc0 - yc1); ctx.fill()
    # stand haze
    # ---- rail-side crowd on the apron (people standing at the outer rail) ----
    rc = S["rc"]
    for (k, za, zb) in reversed(secs):
        if za > 160:
            continue
        u0 = (k % 5) * 600.0
        _ps_wall(ctx, rc, PS_XO - 1.6, 0.0, 1.9, za, zb, u0, u0 + 600, vx, vy)
    # ---- rails & posts ----
    for X in (PS_XO, PS_XI):
        xe, ye = _pp(X, zn, 1.0, vx, vy)
        ctx.move_to(vx, vy + (PS_F * (PS_H - 1.0) / 1e6)); ctx.line_to(xe, ye)
        ctx.set_source_rgba(1, 1, 1, 0.95); ctx.set_line_width(2)
        # thicker near: draw as a wedge
        ctx.new_path()
        xe1, ye1 = _pp(X, zn, 1.08, vx, vy); xe2, ye2 = _pp(X, zn, 0.92, vx, vy)
        ctx.move_to(vx, vy); ctx.line_to(xe1, ye1); ctx.line_to(xe2, ye2); ctx.close_path()
        ctx.set_source_rgb(0.97, 0.97, 1.0); ctx.fill()
        for kk in range(int(camz // 2.5), int((camz + 200) // 2.5) + 1):
            Z = kk * 2.5 - camz
            if Z < zn:
                continue
            px0, py0 = _pp(X, Z, 0, vx, vy); px1, py1 = _pp(X, Z, 1.0, vx, vy)
            wdt = max(0.8, f * 0.08 / Z)
            ctx.set_source_rgba(0.95, 0.95, 1, 0.9); ctx.rectangle(px0 - wdt / 2, py1, wdt, py0 - py1); ctx.fill()
    # ---- floodlight towers both sides, far to near ----
    towers = []
    for kk in range(int(camz // 55), int((camz + 700) // 55) + 1):
        for side, X in ((0, PS_XS - 12), (1, PS_XI + 14)):
            Z = kk * 55 + side * 27 - camz
            if Z > 1.5:
                towers.append((Z, X))
    towers.sort(key=lambda a: -a[0])
    for (Z, X) in towers:
        bx, by = _pp(X, Z, 0, vx, vy); hx, hy = _pp(X, Z, 42, vx, vy)
        wdt = max(1.0, f * 0.6 / Z)
        ctx.set_source_rgb(0.16, 0.15, 0.2); ctx.rectangle(bx - wdt / 2, hy, wdt, by - hy); ctx.fill()
        sc = f / Z
        _glow(ctx, hx, hy, 18 * sc + 20, FLOOD, 0.5)
        _glow(ctx, hx, hy, 5 * sc + 6, FLOOD_CORE, 0.9)
        ctx.set_source_rgb(0.12, 0.11, 0.15); ctx.rectangle(hx - 3 * sc, hy - 1.6 * sc, 6 * sc, 3.2 * sc); ctx.fill()
        for i in range(5):
            for j in range(3):
                ctx.set_source_rgb(*FLOOD_CORE)
                ctx.arc(hx - 2.4 * sc + i * 1.2 * sc, hy - 1.0 * sc + j * 1.0 * sc, 0.42 * sc, 0, TAU); ctx.fill()
        _star_flare(ctx, hx, hy, 14 * sc + 40, (1, 1, 1), 0.6)
    # ---- finish post ----
    if finish:
        Zf = PS_LEN - camz + 4
        if Zf > 1.5:
            fx, fy = _pp(PS_XI + 0.6, Zf, 0, vx, vy)
            draw_finish_post(ctx, fx, fy, scale=f * 6.5 / (Zf * 560), line=False, t=t)
    # ---- camera flashes on stand ----
    fi = int(t * FPS)
    nfl = int(5 + 50 * flash)
    for q in range(nfl):
        Z = 6 + 300 * _hash(fi * 97 + q, 7) ** 1.5
        Y = 2 + 22 * _hash(fi * 97 + q, 8)
        x_, y_ = _pp(PS_XS + 0.3, Z, Y, vx, vy)
        a = 0.9
        _glow(ctx, x_, y_, 12 + 300 / Z, (1, 1, 1), 0.6 * a)
        _star_flare(ctx, x_, y_, 10 + 200 / Z, (1, 1, 1), a)
    # atmospheric depth haze toward the vanishing point
    ctx.save(); ctx.translate(vx, vy); ctx.scale(1.6, 0.5)
    _glow(ctx, 0, 0, 500, (0.85, 0.65, 0.7), 0.35); ctx.restore()
    if blur > 0.05:
        speed_lines_radial(ctx, t, vx, vy, blur)


def _ps_quad(ctx, X, Y0, Y1, za, zb, vx, vy, col, a=1.0):
    xa, ya0 = _pp(X, za, Y0, vx, vy); _, ya1 = _pp(X, za, Y1, vx, vy)
    xb, yb0 = _pp(X, zb, Y0, vx, vy); _, yb1 = _pp(X, zb, Y1, vx, vy)
    ctx.move_to(xa, ya1); ctx.line_to(xb, yb1); ctx.line_to(xb, yb0); ctx.line_to(xa, ya0); ctx.close_path()
    ctx.set_source_rgba(*col, a); ctx.fill()


def speed_lines_radial(ctx, t, vx, vy, amount=1.0, seed=9):
    """Perspective speed streaks radiating from the vanishing point."""
    fi = int(t * FPS)
    n = int(60 * amount)
    for i in range(n):
        a = _hash(i + fi * 7, seed) * TAU
        r0 = 200 + 900 * _hash(i + fi * 7, seed + 1)
        L = 200 + 700 * _hash(i + fi * 7, seed + 2)
        ca, sa = math.cos(a), math.sin(a)
        g = _lin(ctx, vx + ca * r0, vy + sa * r0, vx + ca * (r0 + L), vy + sa * (r0 + L),
                 [(0, (1, 1, 1, 0)), (0.5, (1, 0.97, 0.9, 0.25 * amount)), (1, (1, 1, 1, 0))])
        ctx.set_source(g)
        w = 1.5 + 3 * _hash(i, seed + 3)
        ctx.move_to(vx + ca * r0 - sa * w, vy + sa * r0 + ca * w)
        ctx.line_to(vx + ca * (r0 + L), vy + sa * (r0 + L))
        ctx.line_to(vx + ca * r0 + sa * w, vy + sa * r0 - ca * w)
        ctx.close_path(); ctx.fill()


# ======================================================================
#  PARTICLES
# ======================================================================
def dust_kick(ctx, t, x, y, strength=1.0, seed=0, color=None, direction=-1.0, speed=1.0):
    """Dirt spray kicked back from a hoof at (x, y). direction=-1 sprays to the left
    (horse running right). Deterministic in t; call every frame at the hoof position.
    color = base dirt colour (default: floodlit 大井 sand)."""
    if strength <= 0:
        return
    col = color or (0.80, 0.64, 0.50)
    lite = tuple(min(1, v * 1.25 + 0.08) for v in col)
    dark = (col[0] * 0.42, col[1] * 0.36, col[2] * 0.34)
    st = strength
    # soft billowing dust cloud (lit from above)
    for i in range(int(8 * st) + 1):
        P = 0.8 + 0.5 * _hash(i, seed * 7 + 1)
        a = ((t * speed + _hash(i, seed * 7 + 2) * P) % P) / P
        px = x + direction * (30 + 300 * a) * st * (0.6 + 0.6 * _hash(i, seed * 7 + 3))
        py = y - 14 - 110 * a * (0.5 + _hash(i, seed * 7 + 4)) + 20 * a * a
        rr = (18 + 100 * a) * (0.6 + 0.5 * st)
        al = 0.42 * (1 - a) ** 1.5 * clamp(a * 8) * st
        _glow(ctx, px, py, rr, lite, al)
    # clods and grains (ballistic, with short motion streaks)
    n = int(30 * st)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    for i in range(n):
        P = 0.32 + 0.36 * _hash(i, seed * 13 + 5)
        ph = _hash(i, seed * 13 + 6) * P
        age = (t * speed + ph) % P
        k = age / P
        vx_ = (220 + 700 * _hash(i, seed * 13 + 7)) * st
        vy_ = (220 + 620 * _hash(i, seed * 13 + 8))
        px = x + direction * vx_ * age
        py = y - vy_ * age + 1500 * age * age
        if py > y + 30:
            continue
        sz = 2.0 + 6.5 * _hash(i, seed * 13 + 9) ** 2
        al = (1 - k ** 2) * 0.95
        c_ = dark if _hash(i, seed * 13 + 10) < 0.6 else col
        dxs = -direction * vx_ * 0.02; dys = (vy_ - 3000 * age) * 0.02
        ctx.set_source_rgba(c_[0], c_[1], c_[2], al * 0.45)
        ctx.set_line_width(sz * 0.8)
        ctx.move_to(px, py); ctx.line_to(px + dxs, py + dys); ctx.stroke()
        ctx.set_source_rgba(c_[0], c_[1], c_[2], al)
        ctx.arc(px, py, sz * 0.55, 0, TAU); ctx.fill()
        ctx.set_source_rgba(lite[0], lite[1], lite[2], al * 0.8)      # floodlit top
        ctx.arc(px - sz * 0.12, py - sz * 0.2, sz * 0.22, 0, TAU); ctx.fill()
    ctx.set_line_cap(cairo.LINE_CAP_BUTT)


_BOKEH_SPR = {}


def _bokeh_sprite(R):
    R = int(R)
    if R not in _BOKEH_SPR:
        s, c = _surf(2 * R + 4, 2 * R + 4)
        cx = cy = R + 2
        g = cairo.RadialGradient(cx, cy, 0, cx, cy, R)
        g.add_color_stop_rgba(0, 1, 1, 1, 0.45)
        g.add_color_stop_rgba(0.7, 1, 1, 1, 0.55)
        g.add_color_stop_rgba(0.9, 1, 1, 1, 0.85)       # brighter rim (anime bokeh)
        g.add_color_stop_rgba(0.97, 1, 1, 1, 0.5)
        g.add_color_stop_rgba(1, 1, 1, 1, 0)
        c.set_source(g); c.arc(cx, cy, R, 0, TAU); c.fill()
        _BOKEH_SPR[R] = s
    return _BOKEH_SPR[R]


def bokeh(ctx, t, n=40, colors=None, seed=0, alpha=0.6, area=(0, 0, W, H), size=(20, 90), drift=(8, -14)):
    """Soft drifting bokeh discs (for epilogue / emotional beats)."""
    colors = colors or [(1.0, 0.78, 0.45), (1.0, 0.55, 0.65), (0.6, 0.85, 1.0), (1.0, 0.92, 0.75), (0.9, 0.6, 1.0)]
    ax, ay, aw, ah = area
    ctx.save()
    ctx.set_operator(cairo.OPERATOR_ADD)
    for i in range(n):
        R = lerp(size[0], size[1], _hash(i, seed * 5 + 1) ** 1.5)
        Rq = max(4, int(R / 4) * 4)
        spr = _bokeh_sprite(Rq)
        x = ax + ((_hash(i, seed * 5 + 2) * aw + t * drift[0] * (0.5 + _hash(i, seed * 5 + 3))) % (aw + 2 * Rq)) - Rq
        y = ay + ((_hash(i, seed * 5 + 4) * ah + t * drift[1] * (0.5 + _hash(i, seed * 5 + 5))) % (ah + 2 * Rq)) - Rq
        pul = 0.65 + 0.35 * math.sin(t * (0.6 + _hash(i, seed * 5 + 6)) * 2 + i)
        col = colors[i % len(colors)]
        ctx.set_source_rgba(col[0], col[1], col[2], alpha * pul * (0.5 + 0.5 * _hash(i, seed * 5 + 7)))
        ctx.mask_surface(spr, x - Rq - 2, y - Rq - 2)
    ctx.restore()


def confetti_light(ctx, t, n=70, seed=0, area=(0, 0, W, H), color=None, rise=45.0, size=1.0, alpha=1.0):
    """Floating light particles / sparkles rising gently with twinkle."""
    ax, ay, aw, ah = area
    for i in range(n):
        col = color or [(1, 0.9, 0.6), (1, 0.7, 0.8), (0.7, 0.9, 1), (1, 1, 1)][i % 4]
        sp = rise * (0.5 + _hash(i, seed + 21))
        x = ax + (_hash(i, seed + 22) * aw + 25 * math.sin(t * (0.5 + _hash(i, seed + 23)) + i * 1.3)) % aw
        y = ay + ah - ((_hash(i, seed + 24) * ah + t * sp) % ah)
        tw = 0.5 + 0.5 * math.sin(t * (2 + 3 * _hash(i, seed + 25)) + i * 2.1)
        r_ = (1.5 + 3.5 * _hash(i, seed + 26) ** 2) * size
        a = alpha * (0.3 + 0.7 * tw)
        _glow(ctx, x, y, r_ * 7, col, a * 0.35)
        if r_ > 3.2 * size:
            _star_flare(ctx, x, y, r_ * 5, col, a * 0.8, rot=0.3)
        ctx.set_source_rgba(1, 1, 1, a); ctx.arc(x, y, r_ * 0.55, 0, TAU); ctx.fill()


# ======================================================================
#  SELF TEST
# ======================================================================
def _selftest(outdir):
    os.makedirs(outdir, exist_ok=True)
    try:
        import render as _R
        post = lambda rgb, i: _R.post(rgb, {}, i)
    except Exception:
        post = None

    def save(name, fn, t=1.0):
        s, c = _surf(W, H)
        c.set_source_rgb(0, 0, 0); c.paint()
        fn(c, t)                       # warm-up (builds caches)
        s, c = _surf(W, H)
        c.set_source_rgb(0, 0, 0); c.paint()
        t0 = time.time(); fn(c, t); dt = (time.time() - t0) * 1000
        p = os.path.join(outdir, name + ".png")
        s.write_to_png(p)
        if post is not None:
            s.flush()
            a = np.ndarray((H, W, 4), np.uint8, s.get_data())
            rgb = a[:, :, [2, 1, 0]].astype(np.float32) / 255.0
            out = (np.clip(post(rgb, 7), 0, 1) * 255 + 0.5).astype(np.uint8)
            Image.fromarray(out).save(os.path.join(outdir, name + "_post.png"))
        print(f"{name:28s} {dt:7.1f} ms  -> {p}")

    save("stable", lambda c, t: (draw_stable(c, t, lamp_swing=1.0, dust=1.0)), 2.3)
    for cx, b in ((0, 0.0), (6000, 0.3), (14000, 0.85)):
        def side(c, t, cx=cx, b=b):
            draw_race_side_bg(c, t, cx, blur=b, flash=0.4)
            draw_race_side_fg(c, t, cx, blur=b)
            dust_kick(c, t, 900, 780, 1.0, seed=1)
        save(f"side_cam{cx}_blur{int(b * 100)}", side, 3.0 + cx / 1400)
    for cam in (0.0, 0.5, 1.0):
        save(f"establishing_cam{int(cam * 100)}", lambda c, t, cam=cam: draw_racecourse_establishing(c, t, cam, horses=True, race_s=0.12), 1.0)
    def gate(c, t, o=0.0):
        draw_race_side_bg(c, t, 800, horizon_y=470, track_y=720)
        draw_starting_gate(c, t, 960, 940, 1.35, open=o, n_stalls=8, view="front", part="back")
        draw_starting_gate(c, t, 960, 940, 1.35, open=o, n_stalls=8, view="front", part="front")
    save("gate_front_closed", lambda c, t: gate(c, t, 0.0))
    save("gate_front_open", lambda c, t: gate(c, t, 0.35))
    def gate_side(c, t):
        draw_race_side_bg(c, t, 800)
        draw_starting_gate(c, t, 900, 860, 1.2, open=0.6, n_stalls=8, view="side")
    save("gate_side_open", gate_side)
    for p_ in (0.2, 0.92):
        save(f"straight_perspective_{int(p_ * 100)}", lambda c, t, p_=p_: draw_track_straight_perspective(c, t, p_, flash=0.4, blur=0.3 if p_ > 0.5 else 0.0))
    def fin(c, t):
        draw_race_side_bg(c, t, 3000)
        draw_finish_post(c, 1150, 690, 1.0, t=t)
        draw_race_side_fg(c, t, 3000)
    save("finish_post", fin)
    def epi(c, t):
        draw_race_side_bg(c, t, 2000, blur=0.0)
        c.set_source_rgba(0.05, 0.03, 0.1, 0.45); c.paint()
        bokeh(c, t, 45, seed=2)
        confetti_light(c, t, 80)
    save("bokeh_confetti", epi, 4.0)
    city = lambda c, t: (draw_sky(c, t, horizon_y=820), draw_city(c, t, 820, scale=1.0))
    save("sky_city", city)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
        "ENV_TEST_OUT", "/tmp/claude-0/-home-user-keiba/d53da140-107f-55e4-b8c0-8a92c9796981/scratchpad/env_test")
    _selftest(out)
