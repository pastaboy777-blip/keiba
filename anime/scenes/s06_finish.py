"""s06 — 写真判定 (photo finish).  global 45.0-50.0

Beat sheet (local t):
  0.00-2.40  FREEZE. Side view at the ゴール板, ハルカゼ (near lane, #14) and the grey #11 nose to nose.
             Photo-finish print look: slit-scan streaked background, silver monochrome with only the
             reds kept (美月's cap/sash, the finish-cam line). Slow drift zoom onto the noses, dust
             hanging in the air, heartbeat pulses (audio hits at 45.55 / 46.45), blinking 写真判定 label,
             timing ruler.  ハルカゼ's nose is past the line by a hair.
  2.40       WIN CALL (47.4): 2-frame ink impact frame, colour floods out from the noses, camera
             flashes burst over the stands, zoom pulls back, the horses start moving again —
             slow motion ramping to full speed as they gallop past the post.
  3.45-      Cut: close-up of 美月, goggles up, shouting with a raised fist, flashes + confetti + bokeh.
  4.30-5.80  Settle: fist comes down, relieved smile, flashes thin out, slow push-in (crossfade to s07).
"""
import math
import numpy as np
import cairo

from lib.common import *
from lib.common import _hash
from lib.horse import draw_horse, HERO_JOCKEY, JOCKEY_PRESETS, COAT_PRESETS, GALLOP_HZ, ground_speed
from lib.env import draw_race_side_bg, draw_race_side_fg, draw_finish_post, dust_kick, bokeh, confetti_light
from lib.chars import draw_mizuki_riding

POST = dict(bloom=0.2, grain=0.6, vignette=0.55, aberration=0.0)   # mutated per frame below

T_WIN = 2.40          # 47.4
T_CUT = 3.45          # cut to 美月
T_SETTLE = 4.05

# ---------------------------------------------------------------- layout (unzoomed world, screen px)
TRACK_Y = 760
POST_X = 1180.0
CAM0 = 5200.0
HERO_Y, HERO_S, HERO_PH = 950.0, 1.20, 0.375
RIV_Y, RIV_S, RIV_PH = 800.0, 1.02, 0.34
RIVAL_COAT = COAT_PRESETS["grey"]
RIVAL_J = dict(JOCKEY_PRESETS[0], crouch=1.0, push=0.9, whip=False)
HERO_J = dict(HERO_JOCKEY, push=0.9)


def _nose_offset(scale, phase, **kw):
    """Rightmost head pixel relative to x (horse drawn at x=0) and its y, found by rasterising once."""
    s, c = new_surface(1400, 900)
    draw_horse(c, 500, 800, scale, phase, t=0.0, ground_shadow=0, **kw)
    s.flush()
    a = np.ndarray((900, s.get_stride() // 4, 4), np.uint8, s.get_data())[:, :1400, 3]
    top = a[: int(800 - 200 * scale)]
    cols = np.where(top.max(axis=0) > 128)[0]
    xr = int(cols.max())
    ys = np.where(top[:, xr] > 128)[0]
    return xr - 500, int(ys.mean()) - 800


_NOSE = {}
def _layout():
    if not _NOSE:
        hx, hy = _nose_offset(HERO_S, HERO_PH, jockey=HERO_J, number=14)
        rx, ry = _nose_offset(RIV_S, RIV_PH, coat=RIVAL_COAT["coat"], mane=RIVAL_COAT["mane"],
                              blaze=False, jockey=RIVAL_J, number=11)
        # ハルカゼ's nose a hair past the line, the grey's a hair short of it
        _NOSE["hero_x"] = POST_X + 9 - hx
        _NOSE["riv_x"] = POST_X - 7 - rx
        _NOSE["nose"] = (POST_X + 2, (HERO_Y + hy + RIV_Y + ry) * 0.5)
    return _NOSE


# ---------------------------------------------------------------- numpy helpers
_YY, _XX = np.mgrid[0:H, 0:W].astype(np.float32)

def _surf_rgb(s):
    s.flush()
    a = np.ndarray((H, s.get_stride() // 4, 4), np.uint8, s.get_data())[:, :W]
    return a[..., 2].astype(np.float32) / 255, a[..., 1].astype(np.float32) / 255, a[..., 0].astype(np.float32) / 255

def _write_rgb(s, r, g, b):
    a = np.ndarray((H, s.get_stride() // 4, 4), np.uint8, s.get_data())
    a[:, :W, 2] = np.clip(r * 255 + 0.5, 0, 255).astype(np.uint8)
    a[:, :W, 1] = np.clip(g * 255 + 0.5, 0, 255).astype(np.uint8)
    a[:, :W, 0] = np.clip(b * 255 + 0.5, 0, 255).astype(np.uint8)
    a[:, :W, 3] = 255
    s.mark_dirty()

PAPER = np.array((0.94, 0.94, 0.92), np.float32)
INKC = np.array((0.035, 0.04, 0.07), np.float32)
REDC = np.array((0.97, 0.10, 0.20), np.float32)

def _grade(s, colour_mask=None, invert=False, pulse=0.0):
    """Photo-finish print grade in place: silver mono + kept reds. colour_mask (HxW 0..1) restores colour."""
    r, g, b = _surf_rgb(s)
    L = 0.30 * r + 0.59 * g + 0.11 * b
    L = np.clip((L - 0.06) / 0.80, 0, 1)
    L = L * L * (3 - 2 * L)                         # contrast S-curve
    L = np.clip(L * (1.0 + 0.25 * pulse), 0, 1)
    mx = np.maximum(g, b)
    red = np.clip(((1.0 - mx / (r + 1e-3)) - 0.62) / 0.12, 0, 1) * np.clip((r - 0.25) / 0.2, 0, 1)
    if invert:
        L = 1.0 - L
    out = []
    for i, ch in enumerate((r, g, b)):
        mono = INKC[i] + (PAPER[i] - INKC[i]) * L
        mono = mono + (REDC[i] * (0.55 + 0.6 * ch) - mono) * red
        if colour_mask is not None:
            mono = mono + (ch - mono) * colour_mask
        out.append(mono)
    _write_rgb(s, *out)


# ---------------------------------------------------------------- pieces
def _time_warp(t):
    """Scene 'world' time: frozen until T_WIN, then slow motion ramping to real time."""
    if t <= T_WIN:
        return 0.004 * t                            # dust barely creeps
    u = t - T_WIN
    # speed factor s(u) = 0.12 -> 1.0 over 0.9 s (smooth), integrated
    ramp = 0.9
    if u < ramp:
        k = u / ramp
        return 0.004 * T_WIN + 0.12 * u + (1 - 0.12) * ramp * (k ** 3 - 0.5 * k ** 4)
    return 0.004 * T_WIN + 0.12 * ramp + (1 - 0.12) * ramp * 0.5 + (u - ramp)


def _flash_star(ctx, x, y, size, a):
    radial_glow(ctx, x, y, size * 2.2, (1, 1, 1), a * 0.5)
    ctx.save(); ctx.translate(x, y)
    for ang in (0, math.pi / 2):
        ctx.save(); ctx.rotate(ang + 0.2)
        g = cairo.LinearGradient(-size * 2.4, 0, size * 2.4, 0)
        g.add_color_stop_rgba(0, 1, 1, 1, 0); g.add_color_stop_rgba(0.5, 1, 1, 1, a); g.add_color_stop_rgba(1, 1, 1, 1, 0)
        ctx.set_source(g)
        ctx.move_to(-size * 2.4, 0); ctx.line_to(0, -size * 0.09); ctx.line_to(size * 2.4, 0); ctx.line_to(0, size * 0.09)
        ctx.close_path(); ctx.fill(); ctx.restore()
    ctx.set_source_rgba(1, 1, 1, a); ctx.arc(0, 0, size * 0.18, 0, TAU); ctx.fill()
    ctx.restore()


def _camera_flashes(ctx, t, t0, rate, area, seed=0, size=(18, 46)):
    """Burst of camera flashes starting at t0; density ~rate * exp decay."""
    if t < t0:
        return
    ax, ay, aw, ah = area
    n = 90
    for i in range(n):
        # flash i fires at t0 + exponential-ish offset
        ti = t0 + (-math.log(1 - 0.999 * _hash(i, seed + 1))) * rate
        d = t - ti
        if 0 <= d < 0.11:
            a = (1 - d / 0.11) ** 1.5
            x = ax + _hash(i, seed + 2) * aw
            y = ay + _hash(i, seed + 3) * ah
            _flash_star(ctx, x, y, lerp(size[0], size[1], _hash(i, seed + 4)), a)


def _draw_world(ctx, t, tau):
    """Side view: background, rival, hero, post, fg. Coordinates of the unzoomed layout."""
    Lo = _layout()
    moving = tau - 0.004 * T_WIN
    vgs = ground_speed(HERO_S)                      # px/s that keeps ハルカゼ's hooves planted
    cam_dx = moving * vgs * 0.92
    frozen = t < T_WIN
    flash = 0.0 if frozen else clamp(1.0 - (t - T_WIN) / 2.2) * 0.9 + 0.1
    draw_race_side_bg(ctx, tau + (1.7 if frozen else 0), CAM0 + cam_dx, track_y=TRACK_Y,
                      blur=0.85 if frozen else 0.85 * (1 - smoothstep(T_WIN, T_WIN + 0.3, t)) + 0.6 * smoothstep(T_WIN + 0.35, T_WIN + 0.9, t),
                      flash=flash)
    # finish post (world-fixed, slides left once the camera tracks)
    px = POST_X - cam_dx
    draw_finish_post(ctx, px, TRACK_Y + 4, 1.05, line=False, t=t, glow=1.0)
    # finish line painted on the dirt toward camera (straight, photo-finish geometry)
    ctx.save()
    g = cairo.LinearGradient(0, TRACK_Y, 0, H)
    g.add_color_stop_rgba(0, 1, 1, 1, 0.85); g.add_color_stop_rgba(1, 1, 1, 1, 0.6)
    ctx.set_source(g)
    ctx.move_to(px - 3, TRACK_Y + 4); ctx.line_to(px + 3, TRACK_Y + 4)
    ctx.line_to(px + 26 + 9, H + 40); ctx.line_to(px + 26 - 9, H + 40); ctx.close_path(); ctx.fill()
    ctx.restore()

    ph_run = moving * GALLOP_HZ * 1.03
    rel = moving                                     # the grey fades behind; hero draws away a touch
    rx = Lo["riv_x"] - rel * 95
    hx = Lo["hero_x"] + rel * 40
    mb = 0.0 if frozen else 0.35 * smoothstep(T_WIN + 0.3, T_WIN + 0.9, t)
    dt_dust = tau * 1.0 + 0.42
    dust_kick(ctx, dt_dust, rx - 170 * RIV_S, RIV_Y, strength=0.9, seed=3)
    draw_horse(ctx, rx, RIV_Y, RIV_S, (RIV_PH + ph_run * 0.98) % 1.0, coat=RIVAL_COAT["coat"],
               mane=RIVAL_COAT["mane"], blaze=False, socks=(False, False, False, False),
               jockey=RIVAL_J, number=11, t=tau, motion_blur=mb, shade=0.12, rim_strength=0.6)
    dust_kick(ctx, dt_dust + 0.3, hx - 180 * HERO_S, HERO_Y, strength=1.1, seed=7)
    draw_horse(ctx, hx, HERO_Y, HERO_S, (HERO_PH + ph_run) % 1.0, jockey=HERO_J, number=14, t=tau,
               motion_blur=mb, rim_strength=1.0, mane_wind=1.2)
    dust_kick(ctx, dt_dust + 0.6, hx + 150 * HERO_S, HERO_Y + 6, strength=0.55, seed=11)
    draw_race_side_fg(ctx, tau, CAM0 + cam_dx, track_y=TRACK_Y, blur=0.0 if frozen else mb * 1.4, clods=1.0)


def _frozen_motes(ctx, t):
    """Dust grains hanging in the air, catching the floodlight (screen space, slight parallax drift)."""
    for i in range(70):
        x = 300 + _hash(i, 71) * 1500 + t * 6 * (_hash(i, 72) - 0.5)
        y = 560 + _hash(i, 73) * 480 - t * 3 * _hash(i, 74)
        r_ = 1.5 + 5 * _hash(i, 75) ** 3
        ctx.set_source_rgba(0.9, 0.85, 0.78, 0.35 + 0.4 * _hash(i, 76))
        ctx.arc(x, y, r_, 0, TAU); ctx.fill()


def _hud_freeze(ctx, t, nose_sx):
    """Photo-finish graphics in screen space."""
    ctx.save()
    # finish-camera slit line through the post
    x = nose_sx
    for w_, a in ((14, 0.10), (6, 0.25), (2.2, 1.0)):
        ctx.set_source_rgba(1.0, 0.12, 0.22, a); ctx.rectangle(x - w_ / 2, 0, w_, H); ctx.fill()
    # little triangles marking the nose contact
    ctx.set_source_rgba(1, 0.12, 0.22, 0.95)
    for y0, d in ((0, 1), (H, -1)):
        ctx.move_to(x - 16, y0); ctx.line_to(x + 16, y0); ctx.line_to(x, y0 + d * 26); ctx.close_path(); ctx.fill()
    # corner brackets
    ctx.set_source_rgba(0.96, 0.96, 0.94, 0.85); ctx.set_line_width(4)
    m, L = 56, 90
    for cx, cy, sx, sy in ((m, m, 1, 1), (W - m, m, -1, 1), (m, H - m, 1, -1), (W - m, H - m, -1, -1)):
        ctx.move_to(cx, cy + sy * L); ctx.line_to(cx, cy); ctx.line_to(cx + sx * L, cy); ctx.stroke()
    # 写真判定 label (blinks)
    on = (t % 0.62) < 0.42 or t < 0.3
    if on:
        ctx.set_source_rgba(0.93, 0.10, 0.20, 0.95); ctx.rectangle(96, 92, 330, 92); ctx.fill()
        text(ctx, "写真判定", 96 + 165, 92 + 67, 60, font=FONT_SERIF, color=(1, 1, 1))
    text(ctx, "PHOTO FINISH  ●REC", 440, 132, 26, font=FONT_SANS_M, color=(0.96, 0.96, 0.94), align="left", alpha=0.9)
    text(ctx, "FINISH CAM 01 / 大井 11R", 440, 168, 22, font=FONT_SANS_M, color=(0.8, 0.8, 0.8), align="left", alpha=0.8)
    # timing ruler along the bottom (photo-finish time scale)
    y = H - 96
    ctx.set_source_rgba(0.96, 0.96, 0.94, 0.7); ctx.rectangle(96, y, W - 192, 2); ctx.fill()
    off = t * 14
    for k in range(-2, 60):
        xx = x + (k * 60 - (off % 60)) - 60 * 16
        if xx < 96 or xx > W - 96:
            continue
        idx = k - int(off // 60) - 16
        major = idx % 5 == 0
        ctx.rectangle(xx, y - (22 if major else 10), 2, 22 if major else 10); ctx.fill()
        if major:
            text(ctx, "1:58.%02d" % (40 + idx), xx, y - 30, 20, font=FONT_SANS_M, color=(0.96, 0.96, 0.94), alpha=0.75)
    text(ctx, "1:58.4", x, 238, 34, font=FONT_SANS, color=(1, 0.2, 0.3), outline=5, outline_color=(0.02, 0.02, 0.05))
    ctx.restore()


def _tube(ctx, p0, p1, w0, w1):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy) + 1e-6; nx, ny = -dy / L, dx / L
    ctx.new_path()
    ctx.move_to(p0[0] + nx * w0, p0[1] + ny * w0)
    ctx.curve_to(p0[0] + dx * 0.5 + nx * (w0 + w1) * 0.56, p0[1] + dy * 0.5 + ny * (w0 + w1) * 0.56,
                 p1[0] + nx * w1, p1[1] + ny * w1, p1[0] + nx * w1, p1[1] + ny * w1)
    ctx.arc(p1[0], p1[1], w1, math.atan2(ny, nx), math.atan2(ny, nx) + math.pi)
    ctx.curve_to(p1[0] - nx * w1, p1[1] - ny * w1,
                 p0[0] + dx * 0.5 - nx * (w0 + w1) * 0.5, p0[1] + dy * 0.5 - ny * (w0 + w1) * 0.5,
                 p0[0] - nx * w0, p0[1] - ny * w0)
    ctx.close_path()
    return (nx, ny)


def _cel_fill(ctx, base, shadow, n, off):
    """Fill current path with base, then a hard shadow band on the -n side, ink outline."""
    path = ctx.copy_path()
    ctx.set_source_rgb(*base); ctx.fill_preserve()
    ctx.save(); ctx.clip()
    ctx.new_path(); ctx.translate(n[0] * off, n[1] * off); ctx.append_path(path)
    ctx.restore()
    ctx.save(); ctx.append_path(path); ctx.clip()
    ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    ctx.new_path(); ctx.rectangle(-4000, -4000, 8000 + W, 8000 + H)
    ctx.translate(-n[0] * off, -n[1] * off); ctx.append_path(path)
    ctx.set_source_rgb(*shadow); ctx.fill()
    ctx.restore()
    ctx.new_path(); ctx.append_path(path)


def _raised_fist(ctx, S, E, F, s, t):
    """美月's far arm raised in triumph: shoulder S, elbow E, fist centre F (screen px)."""
    ink = PAL["ink"]
    silk, silk_s = PAL["silk_main"], (0.70, 0.72, 0.88)
    red = PAL["silk_accent"]
    ctx.save()
    ctx.set_line_join(cairo.LINE_JOIN_ROUND); ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    lw = 4.5 * s
    # upper arm, then forearm (forearm over the elbow)
    for p0, p1, w0, w1 in ((S, E, 62 * s, 50 * s), (E, F, 50 * s, 40 * s)):
        n = _tube(ctx, p0, p1, w0, w1)
        # shadow on the side away from the key light (light from screen-right/ahead)
        side = n if n[0] < 0 else (-n[0], -n[1])
        _cel_fill(ctx, silk, silk_s, (-side[0], -side[1]), 24 * s)
        ctx.set_source_rgb(*ink); ctx.set_line_width(lw); ctx.stroke()
    # red sleeve stripe on the forearm
    k = 0.55
    cx_, cy_ = lerp(E[0], F[0], k), lerp(E[1], F[1], k)
    n = _tube(ctx, E, F, 50 * s, 40 * s); ctx.new_path()
    ctx.save(); _tube(ctx, E, F, 50 * s, 40 * s); ctx.clip()
    ctx.set_line_width(22 * s); ctx.set_source_rgb(*red); ctx.set_line_cap(cairo.LINE_CAP_BUTT)
    ctx.move_to(cx_ + n[0] * 80 * s, cy_ + n[1] * 80 * s); ctx.line_to(cx_ - n[0] * 80 * s, cy_ - n[1] * 80 * s); ctx.stroke()
    ctx.restore()
    # fist (white glove), knuckles toward camera, along the forearm direction
    ang = math.atan2(F[1] - E[1], F[0] - E[0]) + math.pi / 2
    ctx.save(); ctx.translate(F[0], F[1]); ctx.rotate(ang); ctx.scale(s, s)
    def rr(x, y, w, h, r):
        ctx.new_path(); ctx.new_sub_path()
        ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0); ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi); ctx.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
        ctx.close_path()
    # cuff
    rr(-50, 10, 100, 34, 10); ctx.set_source_rgb(*red); ctx.fill_preserve()
    ctx.set_source_rgb(*ink); ctx.set_line_width(4); ctx.stroke()
    # fist body
    rr(-56, -84, 112, 100, 30); ctx.set_source_rgb(0.98, 0.98, 1.0); ctx.fill_preserve()
    ctx.set_source_rgb(*ink); ctx.set_line_width(5); ctx.stroke()
    # finger rolls (4 knuckles) along the top
    for i in range(4):
        x0 = -52 + i * 26
        rr(x0, -92, 26, 42, 12); ctx.set_source_rgb(0.98, 0.98, 1.0); ctx.fill_preserve()
        ctx.set_source_rgb(*ink); ctx.set_line_width(4); ctx.stroke()
    ctx.set_source_rgba(*silk_s, 1)
    rr(-50, -52, 100, 8, 4); ctx.fill()
    # thumb wrapping across
    ctx.new_path(); ctx.move_to(-54, -26); ctx.curve_to(-30, -48, 10, -50, 30, -40)
    ctx.curve_to(40, -34, 36, -22, 24, -22); ctx.curve_to(0, -22, -30, -10, -54, -6); ctx.close_path()
    ctx.set_source_rgb(0.94, 0.94, 0.98); ctx.fill_preserve()
    ctx.set_source_rgb(*ink); ctx.set_line_width(4); ctx.stroke()
    ctx.restore()
    ctx.restore()


# ---------------------------------------------------------------- shots
def _shot_side(ctx, t):
    Lo = _layout()
    nx_, ny_ = Lo["nose"]
    tau = _time_warp(t)
    frozen = t < T_WIN
    # --- camera
    if frozen:
        k = ease_in_out(t / T_WIN)
        z = lerp(1.08, 1.62, k)
        # heartbeat kicks (audio 45.55 / 46.45 plus the "dub")
        hb = 0.0
        for tb in (0.55, 1.45):
            for off, amp in ((0.0, 1.0), (0.22, 0.55)):
                d = t - tb - off
                if d >= 0:
                    hb += amp * math.exp(-d * 9) * min(1, d * 60)
        z *= 1 + 0.018 * hb
        cx, cy = nx_ + 0, ny_ + 10
        sx, sy = W * 0.5, H * 0.46
    else:
        u = t - T_WIN
        hb = 0.0
        z = lerp(1.62, 1.0, ease_out_cubic(u / 0.8)) * (1 + 0.05 * math.exp(-u * 10))
        cx = lerp(nx_, nx_ - 120, ease_in_out(u / 0.9)); cy = lerp(ny_ + 10, 640, ease_out_cubic(u / 0.8))
        sx, sy = W * 0.5, lerp(H * 0.46, H * 0.55, ease_out_cubic(u / 0.8))
        shx, shy = shake(t, 14 * math.exp(-u * 3) + 3, 16, 5)
        sx += shx; sy += shy
    s, c = new_surface()
    c.translate(sx, sy); c.scale(z, z); c.translate(-cx, -cy)
    _draw_world(c, t, tau)
    c.identity_matrix()
    if frozen:
        _frozen_motes(c, t)
    # screen position of the finish line / noses
    nose_sx = sx + (POST_X - cx) * z
    # --- grade
    if frozen:
        _grade(s, invert=False, pulse=hb)
    else:
        u = t - T_WIN
        if u < 2 / 24.0:
            _grade(s, invert=True)                   # ink impact frames
        elif u < 0.6:
            R = (u - 2 / 24.0) / (0.6 - 2 / 24.0)
            R = ease_out_cubic(R) * 2300
            d = np.sqrt((_XX - nose_sx) ** 2 + (_YY - H * 0.46) ** 2)
            m = np.clip((R - d) / 260.0, 0, 1)
            _grade(s, colour_mask=m)
    ctx.set_source_surface(s, 0, 0); ctx.paint()
    if frozen:
        # slit-scan striation + subtle paper vignette
        for i in range(0, H, 4):
            ctx.set_source_rgba(0, 0, 0, 0.06); ctx.rectangle(0, i, W, 1.5); ctx.fill()
        ctx.set_source_rgba(0, 0, 0, 0.25 * hb); ctx.paint()
        _hud_freeze(ctx, t, nose_sx)
        # opening "shutter" frames right after the render's white flash
        if t < 0.12:
            ctx.set_source_rgba(1, 1, 1, 0.5 * (1 - t / 0.12)); ctx.paint()
    else:
        u = t - T_WIN
        # radial focus lines on the win-call impact
        if u < 0.55:
            a = 0.55 * (1 - u / 0.55)
            speed_lines(ctx, t, nose_sx, H * 0.46, n=110, inner=520, outer=1500, color=(1, 1, 1), alpha=a, seed=31)
        # grandstand camera flashes (on top, bright)
        if u > 0.09:
            _camera_flashes(ctx, t, T_WIN + 0.08, 0.45, (0, 90, W, 560), seed=1)
        confetti_light(ctx, t, n=50, seed=4, area=(0, 0, W, H), alpha=smoothstep(T_WIN, T_WIN + 0.5, t) * 0.8)
        # win text flash
        if 0.09 < u < 1.0:
            a = smoothstep(0.09, 0.16, u) * (1 - smoothstep(0.75, 1.0, u))
            zz = 1 + 0.25 * math.exp(-u * 12)
            ctx.save(); ctx.translate(W * 0.5, 260); ctx.scale(zz, zz)
            text(ctx, "1着  14 ハルカゼ", 0, 0, 92, font=FONT_IMPACT, color=(1, 0.95, 0.75), alpha=a,
                 outline=14, outline_color=(0.75, 0.05, 0.15), outline_alpha=0.95)
            ctx.restore()
        # white pop at the call
        if u < 0.25:
            ctx.set_source_rgba(1, 1, 1, 0.45 * (1 - u / 0.25) ** 2); ctx.paint()


def _shot_mizuki(ctx, t):
    u = t - T_CUT
    # background: floodlit grandstand, blurred, drifting (camera tracks with her)
    ctx.save()
    z = 1.9 + 0.05 * u
    ctx.translate(W / 2, H / 2); ctx.scale(z, z); ctx.translate(-W / 2, -H / 2 + 170)
    speed = lerp(0.9, 0.2, smoothstep(0.0, 2.0, u))
    draw_race_side_bg(ctx, t, 9000 + u * 900 * speed, track_y=TRACK_Y, blur=lerp(1.0, 0.6, smoothstep(0, 2, u)),
                      flash=clamp(1.0 - u / 2.2) * 0.8 + 0.2)
    ctx.restore()
    # dim + warm/cool grade so she pops
    g = cairo.LinearGradient(0, 0, W, 0)
    g.add_color_stop_rgba(0, 0.02, 0.02, 0.08, 0.55); g.add_color_stop_rgba(0.6, 0.02, 0.02, 0.08, 0.15)
    g.add_color_stop_rgba(1, 0.05, 0.03, 0.08, 0.35)
    ctx.set_source(g); ctx.paint()
    bokeh(ctx, t, n=26, seed=3, alpha=0.5, size=(30, 110), drift=(-40 * speed, -10))
    _camera_flashes(ctx, t, T_CUT - 0.3, 0.8, (0, 40, W, 700), seed=9, size=(30, 70))
    horiz_speed_lines(ctx, t, 0, H, n=int(18 * speed), speed=2800 * speed, color=(1, 1, 1), alpha=0.18 * speed, seed=41)

    # performance: shout -> smile
    settle = smoothstep(T_SETTLE - 0.1, T_SETTLE + 0.4, t)
    shout = settle < 0.5
    hx = lerp(820, 860, ease_out_cubic(u / 2.0)); hy = 520 + 18 * math.sin(t * TAU * 1.1) * (1 - settle * 0.6)
    sc = 1.08 + 0.06 * ease_out_cubic(u / 2.2)
    # raised fist: pops up (ease_out_back), pumps, then comes down during the settle
    up = ease_out_back(clamp(u / 0.28)) * (1 - smoothstep(T_SETTLE + 0.25, T_SETTLE + 0.9, t))
    pump = math.sin(u * TAU * 2.4) * 0.5 + 0.5 if u < 0.85 else 0.0
    ctx.save()
    shx, shy = shake(t, 6 * (1 - settle), 14, 2)
    ctx.translate(shx, shy)
    # far arm drawn first (behind body)
    S = (hx + 120 * sc, hy + 330 * sc)
    E = (lerp(hx + 330 * sc, hx + 330 * sc, up), lerp(hy + 520 * sc, hy + 170 * sc, up))
    F = (lerp(hx + 420 * sc, hx + 380 * sc - 20 * pump * sc, up), lerp(H + 260, hy - 150 * sc - 40 * pump * sc, up))
    if up > 0.02:
        _raised_fist(ctx, S, E, F, sc * 0.95, t)
    if shout:
        m = 0.75 + 0.25 * math.sin(t * 13) if u < 0.8 else 0.6
        expr = "shout"
    else:
        m = 0.25
        expr = "smile"
    blink = 1.0 if (0.0 < t - 4.95 < 0.09) else 0.0
    draw_mizuki_riding(ctx, hx, hy, sc, expr=expr, mouth=m, blink=blink, t=t, wind=lerp(1.0, 0.4, settle),
                       goggles="up", sweat=0.6, rim_strength=1.2, light_flash=clamp(1 - u / 1.2) * 0.4,
                       look=(0.25, -0.15 if shout else 0.0), blush=0.8)
    ctx.restore()
    confetti_light(ctx, t, n=60, seed=8, area=(0, 0, W, H), alpha=0.9, size=1.3)
    # hard cut in: 1 frame white
    if u < 1 / 24.0:
        ctx.set_source_rgba(1, 1, 1, 0.6); ctx.paint()
    # settle: warm soft light washing in
    if settle > 0:
        radial_glow(ctx, W * 0.45, H * 0.35, 1300, (1.0, 0.82, 0.6), 0.14 * settle)


def draw(ctx, t, dur, gt):
    if t < T_WIN:
        POST.update(bloom=0.12, grain=0.9, vignette=0.7, aberration=0.0)
    elif t < T_CUT:
        u = t - T_WIN
        POST.update(bloom=0.5, grain=0.35, vignette=0.45, aberration=3.0 * math.exp(-u * 5))
    else:
        POST.update(bloom=0.45, grain=0.3, vignette=0.45, aberration=0.0)
    if t < T_CUT:
        _shot_side(ctx, t)
    else:
        _shot_mizuki(ctx, t)
