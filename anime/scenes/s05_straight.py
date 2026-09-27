"""s05 33.0-45.0 : the final straight — the climax.

Cut list (local t = gt - 33):
  C1 0.00-2.50  low perspective down the home straight, camera riding with ハルカゼ; she swings
                to the far outside and the pack sweeps past the right edge of frame.
  C2 2.50-3.85  side tracking: ハルカゼ huge in the foreground passing rival after rival.
  C3 3.85-4.70  insert: 美月 riding close-up (determined, jaw set).
  C4 4.70-5.30  side tracking again: last rival swept away, the grey leader ahead.
  C5 5.30-7.20  two-shot vs the grey leader, camera pushing in on the noses ("並ぶか、並ぶか").
  C6 7.20-7.33  impact frame (neck_and_neck 40.2 "並んだ!").
  C7 7.33-8.40  extreme intensity: noses, radial lines, strobing.
  C8 8.40-9.50  ai_glitch 41.4: the whole frame breaks, AI HUD reads ERROR / 計算不能.
  C9 9.50-12.0  slow motion: the last strides, dust hanging in the air, the finish post arrives.
"""
import math
import cairo
from lib.common import *
from lib.common import _hash
from lib.horse import draw_horse, HERO_JOCKEY, JOCKEY_PRESETS, COAT_PRESETS
from lib.env import (draw_track_straight_perspective, draw_race_side_bg, draw_race_side_fg,
                     draw_finish_post, speed_lines_radial, dust_kick, PS_F, PS_H)
from lib.chars import draw_mizuki_riding
from lib.hud import (draw_prob_panel, prob_curve, history_at, glitch_curve, glitch_frame,
                     draw_scanlines, draw_brackets)
from lib.lipsync import mouth

POST = dict(bloom=0.45, grain=0.3, vignette=0.5, aberration=0.0)

HZ = 2.45                      # gallop strides / s (matches the hoofbeats in the music)
GREY = COAT_PRESETS["grey"]
LEADER_J = dict(JOCKEY_PRESETS[0], crouch=1.0, push=1.0, whip=True)
HERO = dict(HERO_JOCKEY, push=1.0)
RIM = (0.75, 0.88, 1.0)

# pack for the perspective opener: (X m, Z0 m, coat, jockey idx, number, phase offset)
PACK = [   # (X, Z0, coat, jockey, number, phase offset, closing speed m/s)
    (-1.3, 9.0, "bay", 1, 5, 0.13, 1.9), (1.8, 7.5, "dark_bay", 2, 9, 0.61, 3.6), (4.2, 10.5, "black", 3, 2, 0.37, 3.8),
    (1.2, 13.0, "liver", 4, 11, 0.82, 3.3), (3.0, 16.0, "bay", 5, 6, 0.25, 3.0), (0.2, 19.0, "dark_bay", 6, 12, 0.5, 2.6),
    (5.0, 22.0, "black", 7, 8, 0.93, 3.0), (-1.8, 25.0, "bay", 3, 4, 0.71, 2.2), (2.0, 31.0, "grey", 0, 1, 0.05, 1.2),
]
# rivals passed in the side tracking shots: (screen x at t=2.5, coat, jockey idx, number, phase)
SIDE_RIVALS = [
    (1500, "dark_bay", 2, 9, 0.61), (2350, "black", 3, 2, 0.37), (3150, "liver", 4, 11, 0.82),
    (3900, "bay", 5, 6, 0.25),
]


def _jk(i, push=0.7, whip=False):
    return dict(JOCKEY_PRESETS[i % len(JOCKEY_PRESETS)], crouch=1.0, push=push, whip=whip)


def cam_begin(ctx, cx, cy, zoom=1.0, dx=0.0, dy=0.0, roll=0.0):
    """Zoom about (cx, cy) keeping it at screen centre+offset."""
    ctx.save()
    ctx.translate(W / 2 + dx, H / 2 + dy)
    if roll:
        ctx.rotate(roll)
    ctx.scale(zoom, zoom)
    ctx.translate(-cx, -cy)


def flash_fill(ctx, a, col=(1, 1, 1)):
    if a > 0.002:
        ctx.save(); ctx.identity_matrix()
        ctx.set_source_rgba(*col, clamp(a)); ctx.paint(); ctx.restore()


def grade(ctx, col, a, op=cairo.OPERATOR_SOFT_LIGHT):
    ctx.save(); ctx.identity_matrix(); ctx.set_operator(op)
    ctx.set_source_rgba(*col, a); ctx.paint(); ctx.restore()


def sfx(ctx, s, x, y, size, rot, col=(1, 1, 1), alpha=1.0):
    ctx.save(); ctx.translate(x, y); ctx.rotate(rot)
    text(ctx, s, 0, 0, size, font=FONT_IMPACT, color=col, alpha=alpha, outline=size * 0.14,
         outline_color=(0.05, 0.02, 0.06), outline_alpha=0.9)
    ctx.restore()


def hoof_dust(ctx, P, x, y, sc, t, seed, strength=1.0, speed=1.0):
    """Dirt spray from the planted hooves of a pose P drawn at (x,y,scale sc)."""
    for i, leg in enumerate(P["legs"]):
        if leg.get("ground"):
            hx = x + leg["hoof"][0][0] * sc
            dust_kick(ctx, t, hx, y, strength=strength * sc, seed=seed * 7 + i, speed=speed)


# ============================================================ C1 perspective opener
def c1_perspective(ctx, t, gt):
    swing = ease_in_out(clamp((t - 0.15) / 1.3))
    vx, vy = 1320.0 + 200 * swing, 392.0
    prog = 0.08 + 0.078 * t
    punch = 1.0 + 0.10 * (1 - ease_out_cubic(t / 0.35))          # hard-cut zoom punch
    sx, sy = shake(t, 7 + 6 * smoothstep(1.0, 2.5, t), 16, 3)
    cam_begin(ctx, W / 2, H / 2, punch, sx, sy, roll=-0.02 + 0.012 * math.sin(t * 2.1))
    draw_track_straight_perspective(ctx, gt, prog, vanish=(vx, vy), flash=0.35 + 0.4 * smoothstep(0.5, 2.5, t),
                                    blur=0.55 + 0.35 * smoothstep(0.8, 2.2, t))
    # horses: ハルカゼ rides with the camera at Z~5.4, swinging from X=-1.8 to the far outside
    swing = ease_in_out(clamp((t - 0.15) / 1.3))
    hx_m = lerp(-1.3, -4.3, swing)
    hz_m = 4.7 - 0.25 * swing + 0.10 * math.sin(t * TAU * HZ)
    items = []
    for i, (X, Z0, coat, ji, num, po, cs) in enumerate(PACK):
        Z = Z0 - cs * t
        items.append((Z, X, coat, ji, num, po, False))
    items.append((hz_m, hx_m, "chestnut", -1, 14, 0.0, True))
    items.sort(key=lambda a: -a[0])
    for (Z, X, coat, ji, num, po, hero) in items:
        if Z < 2.2:
            continue
        x = vx + PS_F * X / Z
        y = vy + PS_F * PS_H / Z
        sc = PS_F / Z * 1.6 / 330.0
        if x < -600 or x > W + 600:
            continue
        ph = (t * HZ + po) % 1.0
        # rotate a little toward the vanishing point (cheat 3/4 rear), foreshorten
        ang = math.atan2(vy - y, vx - x) * 0.12
        depth = clamp((Z - 6) / 30) + 0.5 * clamp((hz_m - Z) / 2.0)
        ctx.save()
        ctx.translate(x, y); ctx.rotate(ang); ctx.scale(0.9, 1.0)
        c = COAT_PRESETS[coat]
        P = draw_horse(ctx, 0, 0, sc, ph, coat=c["coat"], mane=c["mane"], blaze=hero,
                       socks=(False, False, True, False) if hero else (False, False, False, False),
                       jockey=HERO if hero else _jk(ji, 0.8, ji == 0), number=num, t=gt,
                       rim=RIM, rim_strength=1.0, shade=0.15 + 0.35 * depth if not hero else 0.0,
                       motion_blur=0.6 if hero else 0.35, line_width=3.0 / max(0.5, sc) ** 0.3)
        ctx.restore()
        hoof_dust(ctx, P, x, y, sc * 0.9, gt, 3 + num, strength=1.0 if hero else 0.6)
    ctx.restore()
    # overlay: crowd flashes, radial lines toward the vanish point
    speed_lines_radial(ctx, gt, vx, vy, 0.8 + 0.6 * smoothstep(1.0, 2.5, t), seed=21)
    grade(ctx, (1.0, 0.75, 0.5), 0.18)


# ============================================================ side tracking (C2 / C4)
def side_track(ctx, t, gt, part):
    """Side tracking shot. ハルカゼ foreground right-of-centre, rivals in the far lane slide back."""
    sc_h = 1.3
    v = STRIDE * sc_h * HZ
    cam_x = 1500 + v * (t - 2.5)
    tl = t - 2.5
    k_int = smoothstep(2.5, 5.3, t)
    sx, sy = shake(t, 11 + 7 * k_int, 20, 7)
    zoom = 1.04 + 0.04 * math.sin(t * 1.7)
    cam_begin(ctx, W / 2, H / 2, zoom, sx, sy, roll=0.018 * math.sin(t * 3.3))
    flash = 0.6 + 0.4 * k_int
    draw_race_side_bg(ctx, gt, cam_x, horizon_y=470, track_y=820, crowd=1.0, flash=flash, blur=0.8)
    # rivals: far lane (y 830, scale 0.78) sliding back at rel speed
    rel = 820.0
    for i, (x0, coat, ji, num, po) in enumerate(SIDE_RIVALS):
        x = x0 - rel * tl
        if x < -700 or x > W + 700:
            continue
        c = COAT_PRESETS[coat]
        ph = (gt * HZ * 0.97 + po) % 1.0
        P = draw_horse(ctx, x, 842, 0.72, ph, coat=c["coat"], mane=c["mane"], blaze=False, socks=(0, 0, 0, 0),
                       jockey=_jk(ji, 0.9, i % 2 == 0), number=num, t=gt, rim=RIM, rim_strength=0.9,
                       shade=0.25, motion_blur=0.7)
        hoof_dust(ctx, P, x, 842, 0.72, gt, 40 + i, 0.7)
    # grey leader appears far ahead late in C4
    if part == "C4":
        xg = lerp(2300, 1500, ease_out_cubic((t - 4.7) / 0.6))
        P = draw_horse(ctx, xg, 842, 0.72, (gt * HZ + 0.05) % 1.0, coat=GREY["coat"], mane=GREY["mane"],
                       blaze=False, socks=(0, 0, 0, 0), jockey=LEADER_J, number=1, t=gt, rim=RIM,
                       rim_strength=1.0, shade=0.12, motion_blur=0.7)
        hoof_dust(ctx, P, xg, 842, 0.72, gt, 77, 0.8)
    # ハルカゼ
    xh = 820 + 40 * math.sin(t * 1.3) + (60 * ease_out_cubic((t - 4.7) / 0.6) if part == "C4" else 0)
    yh = 1030
    ph = (gt * HZ) % 1.0
    P = draw_horse(ctx, xh, yh, sc_h, ph, jockey=HERO, number=14, t=gt, rim=RIM, rim_strength=1.1,
                   motion_blur=0.9, mane_wind=1.4)
    hoof_dust(ctx, P, xh, yh, sc_h, gt, 14, 1.4)
    draw_race_side_fg(ctx, gt, cam_x, track_y=820, blur=0.9, clods=1.0, rail=False, grass=False)
    # a near-side rival whipping past the lens (foreground occlusion, C2 only)
    if part == "C2":
        xf = lerp(W + 900, -1300, (t - 2.95) / 0.55)
        if -1300 < xf < W + 900:
            c = COAT_PRESETS["bay"]
            draw_horse(ctx, xf, 1420, 1.9, (gt * HZ + 0.4) % 1.0, coat=c["coat"], mane=c["mane"], blaze=False,
                       socks=(0, 0, 0, 0), jockey=_jk(6, 0.8), number=3, t=gt, shade=0.82, motion_blur=1.0,
                       rim=RIM, rim_strength=0.4, ground_shadow=0)
    ctx.restore()
    horiz_speed_lines(ctx, gt, 0, H, n=34, speed=6500, color=(1, 0.95, 0.88), alpha=0.35, seed=55, length=(300, 1100))
    # camera flash pops
    fi = int(gt * FPS)
    if _hash(fi, 71) < 0.18:
        flash_fill(ctx, 0.10 + 0.12 * _hash(fi, 72))
    # manga SFX pounding with the hoofbeats
    beat = (gt * HZ) % 1.0
    if part == "C2" and beat < 0.35:
        sfx(ctx, "ドドドッ", 300 + 30 * _hash(int(gt * HZ), 3), 230, 120 + 40 * (0.35 - beat), -0.12,
            col=(1, 0.93, 0.8), alpha=0.85 * (1 - beat / 0.35))


STRIDE = 885.0


# ============================================================ C3 美月 insert
def c3_mizuki(ctx, t, gt):
    lt = t - 3.85
    cam_x = 3000 + 5200 * lt
    sx, sy = shake(t, 12, 22, 11)
    push = 1.0 + 0.06 * ease_out_cubic(lt / 0.85)
    ctx.save()
    ctx.translate(sx, sy)
    ctx.save(); ctx.translate(W / 2, H / 2); ctx.rotate(-0.08); ctx.scale(1.25, 1.25); ctx.translate(-W / 2, -H / 2 - 120)
    draw_race_side_bg(ctx, gt, cam_x, horizon_y=560, track_y=900, crowd=1.0, flash=1.0, blur=1.0)
    ctx.restore()
    grade(ctx, (0.05, 0.05, 0.18), 0.35, cairo.OPERATOR_OVER)
    horiz_speed_lines(ctx, gt, 0, H, n=50, speed=9000, color=(0.85, 0.92, 1.0), alpha=0.45, seed=91, length=(400, 1400))
    cam_begin(ctx, 1000, 560, push, 0, 0, roll=0.0)
    draw_mizuki_riding(ctx, 1080, 470, 1.3, expr="determined", mouth=0.0, blink=0.0, t=gt, wind=1.4,
                       goggles="down", sweat=0.6, rim=RIM, rim_strength=1.2,
                       light_flash=0.5 if _hash(int(gt * FPS), 5) < 0.25 else 0.0, shake=0.4, dirt=1.0,
                       look=(0.45, -0.05))
    ctx.restore()
    ctx.restore()
    # focus lines
    speed_lines(ctx, gt, 1080, 470, n=70, inner=520, outer=1500, color=(1, 1, 1), alpha=0.35, seed=8)
    if lt < 0.06:
        flash_fill(ctx, 0.6 * (1 - lt / 0.06))


# ============================================================ two-shot (C5, C7, C8, C9)
def duel(ctx, t, gt, *, gap, zoom, focus_dx=0.0, rate=1.0, cam_speed=1.0, shake_amp=10.0, slow_t=None,
         bg_blur=0.85, finish_x=None, dust_speed=1.0):
    """ハルカゼ (near) and the grey leader (far lane) side by side.
    gap = how far the grey nose is ahead (px, at scale 1). zoom about the noses."""
    tt = gt if slow_t is None else slow_t
    sc_h, sc_g = 1.0, 0.9
    yh, yg = 930, 852
    xh = 760
    xg = xh + 30 + gap
    nose = (xh + 315 * sc_h, yh - 285 * sc_h)
    cam_x = 1500 + STRIDE * sc_h * HZ * (tt - 38.0) * cam_speed
    sx, sy = shake(tt, shake_amp, 20, 5)
    cx = clamp(nose[0] - 380 / zoom + focus_dx, W / (2 * zoom) - 150, W - W / (2 * zoom) + 150)
    cy = min(nose[1] + 60 + 40 / zoom, H - H / (2 * zoom) + 14)
    cam_begin(ctx, cx, cy, zoom, sx, sy, roll=0.01 * math.sin(tt * 2.5))
    draw_race_side_bg(ctx, tt, cam_x, horizon_y=430, track_y=860, crowd=1.0, flash=1.0 if slow_t is None else 0.3,
                      blur=bg_blur)
    phg = (tt * HZ * rate + 0.47) % 1.0
    phh = (tt * HZ * rate) % 1.0
    P = draw_horse(ctx, xg, yg, sc_g, phg, coat=GREY["coat"], mane=GREY["mane"], blaze=False, socks=(0, 0, 0, 0),
                   jockey=LEADER_J, number=1, t=tt, rim=RIM, rim_strength=1.0, shade=0.1,
                   motion_blur=0.6 if slow_t is None else 0.15)
    hoof_dust(ctx, P, xg, yg, sc_g, tt, 88, 0.9, dust_speed)
    P = draw_horse(ctx, xh, yh, sc_h, phh, jockey=HERO, number=14, t=tt, rim=RIM, rim_strength=1.2,
                   motion_blur=0.8 if slow_t is None else 0.2, mane_wind=1.3)
    hoof_dust(ctx, P, xh, yh, sc_h, tt, 14, 1.3, dust_speed)
    if finish_x is not None:
        draw_finish_post(ctx, finish_x, 1010, scale=1.4, line=True, line_len=300, t=tt)
    draw_race_side_fg(ctx, tt, cam_x, track_y=860, blur=bg_blur, clods=1.0 if slow_t is None else 0.3,
                      rail=False, grass=False)
    ctx.restore()
    return nose


def c5_duel(ctx, t, gt):
    k = (t - 5.3) / 1.9
    gap = lerp(260, 0, ease_in_out(k))           # grey ahead by a neck -> level at 40.2
    # "並ぶか、並ぶか" : two push-in steps on the words, then the lunge
    z = 1.0 + 0.25 * smoothstep(5.1, 5.6, t) + 0.25 * smoothstep(6.0, 6.35, t) + 0.35 * smoothstep(6.7, 7.2, t)
    duel(ctx, t, gt, gap=gap, zoom=z, shake_amp=8 + 10 * k)
    horiz_speed_lines(ctx, gt, 0, H, n=26, speed=6000, color=(1, 0.95, 0.9), alpha=0.28, seed=61, length=(300, 1000))
    fi = int(gt * FPS)
    if _hash(fi, 33) < 0.15:
        flash_fill(ctx, 0.12)
    if t < 5.34:
        flash_fill(ctx, 0.5)


def c6_impact(ctx, t, gt):
    """3-frame impact: white paper, ink silhouettes, black focus lines, then inverted."""
    f = int((t - 7.2) * FPS)
    sc = 1.0
    xh, yh = 760, 960
    nose = (xh + 315, yh - 285)
    inv = f == 1
    bg = (0.02, 0.01, 0.04) if inv else (1, 0.98, 0.94)
    ink = (1, 0.97, 0.93) if inv else (0.02, 0.01, 0.04)
    ctx.set_source_rgb(*bg); ctx.paint()
    speed_lines(ctx, gt, nose[0] + 40, nose[1] + 40, n=140, inner=260, outer=2200, color=ink, alpha=0.9, seed=13 + f)
    cam_begin(ctx, nose[0] - 380 / 1.95, nose[1] + 60, 1.95 + 0.08 * f, 0, 0, roll=-0.03 + 0.02 * f)
    ctx.push_group()
    draw_horse(ctx, xh + 30, 880, 0.9, 0.55, coat=GREY["coat"], mane=GREY["mane"], jockey=LEADER_J, t=gt, shade=1.0,
               ground_shadow=0, rim_strength=0)
    draw_horse(ctx, xh, yh, sc, 0.55, jockey=HERO, number=14, t=gt, shade=1.0, ground_shadow=0, rim_strength=0)
    pat = ctx.pop_group()
    ctx.set_source_rgb(*ink); ctx.mask(pat)
    ctx.restore()
    if not inv:
        # a slash of red through the frame
        ctx.save(); ctx.translate(W / 2, H / 2); ctx.rotate(-0.35)
        ctx.rectangle(-W, -26, 2 * W, 52); ctx.set_source_rgba(*PAL["silk_accent"], 0.95); ctx.fill()
        ctx.restore()
    sfx(ctx, "ッ!!", 1500, 330, 230, 0.1, col=(1, 0.2, 0.3) if not inv else (1, 1, 1))


def c7_intense(ctx, t, gt):
    lt = t - 7.33
    z = 1.95 + 0.25 * ease_out_cubic(lt / 1.07)
    gap = -6 * math.sin(lt * 9)                  # noses bobbing, swapping the lead each stride
    nose = duel(ctx, t, gt, gap=gap, zoom=z, shake_amp=22 - 8 * clamp(lt), bg_blur=1.0)
    speed_lines(ctx, gt, W / 2 + 60, H / 2 - 40, n=110, inner=560, outer=1700, color=(1, 1, 1), alpha=0.55, seed=31)
    fi = int(gt * FPS)
    if fi % 4 == 0:
        flash_fill(ctx, 0.14)
    if fi % 6 == 3:
        grade(ctx, (1, 0.3, 0.4), 0.25)
    POST["aberration"] = 3.0


def c8_glitch(ctx, t, gt):
    lt = t - 8.4
    z = 1.5 - 0.25 * ease_out_cubic(lt / 1.1)
    duel(ctx, t, gt, gap=-4 * math.sin(lt * 7), zoom=z, shake_amp=14, bg_blur=0.9)
    # the AI's view: cool desaturated wash + scanlines + target brackets that can't lock
    grade(ctx, (0.1, 0.55, 0.7), 0.35)
    ctx.save(); ctx.identity_matrix(); ctx.set_source_rgba(0.0, 0.08, 0.12, 0.25); ctx.paint(); ctx.restore()
    draw_scanlines(ctx, alpha=0.12)
    r = rng(int(gt * FPS) * 13)
    for bx, by in ((520, 200), (980, 170)):
        jx, jy = r.uniform(-60, 60), r.uniform(-40, 40)
        draw_brackets(ctx, bx + jx, by + jy, 420, 360, gt, PAL["neon_pink"], alpha=0.9, size=34, width=3)
    p = prob_curve(gt)
    draw_prob_panel(ctx, gt, p, x=1440 + r.uniform(-8, 8) * (lt < 0.5), y=80, alpha=1.0, glitch=glitch_curve(gt),
                    history=history_at(gt))
    # big central warning while the AI speaks
    if 0.05 < lt < 1.1:
        s = "計算不能" if gt >= 42.2 else "ERROR"
        a = 0.9 if int(gt * 12) % 3 else 0.4
        text(ctx, s, W / 2 + r.uniform(-10, 10), H / 2 + 40, 170 if s == "ERROR" else 150,
             font=FONT_SANS if s != "ERROR" else "DejaVu Sans Mono", color=PAL["neon_pink"], alpha=a,
             outline=6, outline_color=(0.1, 0, 0.05), outline_alpha=0.8)
    amt = glitch_curve(gt) * (1.0 if lt < 0.15 else 0.8)
    if lt < 0.08:
        amt = 1.0
        flash_fill(ctx, 0.35, PAL["neon_pink"])
    glitch_frame(ctx, amt, seed=int(gt * FPS) * 7 + 1)
    POST["aberration"] = 4.0 * amt + 1


def c9_slowmo(ctx, t, gt):
    lt = t - 9.5                                 # 0 .. 2.5
    # slow-motion clock: ramps from full speed down to ~0.28x
    k = 0.28
    ramp = 0.25
    if lt < ramp:
        st = lt - (1 - k) * lt * lt / (2 * ramp)
    else:
        st = ramp - (1 - k) * ramp / 2 + k * (lt - ramp)
    slow_t = 42.5 + st
    # the finish post comes in from the right; noses hit the line at 45.0
    fx = lerp(3000, 1060, (lt / 2.5) ** 0.9)
    z = 1.35 + 0.3 * ease_in_out(lt / 2.5)
    duel(ctx, t, gt, gap=0.0, zoom=z, focus_dx=60, shake_amp=2.5, slow_t=slow_t, bg_blur=0.35, finish_x=fx,
         dust_speed=0.35)
    # hanging dust motes (almost frozen)
    ctx.save()
    for i in range(90):
        x = (_hash(i, 1) * (W + 400) - lt * (30 + 60 * _hash(i, 2))) % (W + 400) - 200
        y = 560 + 520 * _hash(i, 3) - lt * 12 * _hash(i, 4)
        rr = 2 + 7 * _hash(i, 5) ** 2
        ctx.arc(x, y, rr, 0, TAU)
        ctx.set_source_rgba(1, 0.86, 0.66, 0.35 + 0.4 * _hash(i, 6))
        ctx.fill()
    ctx.restore()
    for i in range(8):
        radial_glow(ctx, (_hash(i, 9) * W - lt * 25) % W, 700 + 300 * _hash(i, 10), 90 + 60 * _hash(i, 11),
                    (1, 0.85, 0.65), 0.12)
    # residual glitch dying out (the AI has gone quiet)
    amt = glitch_curve(gt) * (1 - smoothstep(0.0, 0.7, lt))
    if amt > 0.02:
        glitch_frame(ctx, amt * 0.6, seed=int(gt * FPS) * 5 + 3)
    # time stretched: cool, desaturated, letterboxed, then light building to the white flash at 45.0
    grade(ctx, (0.55, 0.65, 0.9), 0.3)
    lb = 70 * smoothstep(0.0, 0.5, lt)
    ctx.set_source_rgb(0, 0, 0); ctx.rectangle(0, 0, W, lb); ctx.rectangle(0, H - lb, W, lb); ctx.fill()
    flash_fill(ctx, 0.55 * smoothstep(2.1, 2.5, lt) ** 2)
    POST["aberration"] = 1.0 + 3 * amt


def draw(ctx, t, dur, gt):
    POST["aberration"] = 0.0
    POST["bloom"] = 0.45
    if t < 2.5:
        c1_perspective(ctx, t, gt)
    elif t < 3.85:
        side_track(ctx, t, gt, "C2")
    elif t < 4.7:
        c3_mizuki(ctx, t, gt)
    elif t < 5.3:
        side_track(ctx, t, gt, "C4")
    elif t < 7.2:
        c5_duel(ctx, t, gt)
    elif t < 7.33:
        c6_impact(ctx, t, gt)
    elif t < 8.4:
        c7_intense(ctx, t, gt)
    elif t < 9.5:
        c8_glitch(ctx, t, gt)
    else:
        POST["bloom"] = 0.6
        c9_slowmo(ctx, t, gt)
