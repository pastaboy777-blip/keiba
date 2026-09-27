"""s02 — warm stable at night (global 6.0-15.0).

Beats (global):
  6.0-7.35  establishing wide: slow push-in, lamp flicker, dust motes (crossfade in from s01 HUD)
  6.9-9.95  L02 源さん — from 7.35 a close framing on him (gruff smile, lipsync)
  9.95-10.6 reaction: two-shot 美月 + ハルカゼ, she turns her gaze from 源さん to the horse
  10.6-14.26 L03 美月 — soft "うん", then determined "行こう"; horse blinks slowly, ears forward,
            nuzzles her at 13.5 (snort SFX)
  14.3-15.0 she turns toward the stable door (cool floodlight spilling in), goggles down — anticipation
"""
import math
import cairo
from lib.common import *
from lib.common import _hash
from lib.env import draw_stable
from lib.horse import draw_horse_head
from lib.chars import draw_mizuki, draw_gen
from lib.lipsync import mouth

POST = dict(bloom=0.42, grain=0.3, vignette=0.55, aberration=0.0)

WARM = (1.0, 0.8, 0.55)
RIM = (1.0, 0.85, 0.6)
COOL = (0.75, 0.88, 1.0)

# world placement (stable background is 1920x1080 world space)
HORSE = (250.0, 1000.0, 1.5)
MIZ = (820.0, 1180.0, 0.95)
GEN = (1560.0, 1140.0, 0.9)

T_CLOSE_GEN = 7.35
T_REACT = 9.95
T_TURN = 14.3
T_NUZZLE = 13.5


def _blink(gt, times, dur=0.16):
    b = 0.0
    for c in times:
        d = abs(gt - c)
        if d < dur:
            b = max(b, 1 - d / dur)
    return b


def _cam(ctx, cx, cy, z):
    """Frame world point (cx,cy) at the screen centre with zoom z (>=1), clamped to the set."""
    hw, hh = W / 2 / z, H / 2 / z
    cx = clamp(cx, hw, W - hw); cy = clamp(cy, hh, H - hh)
    ctx.translate(W / 2, H / 2); ctx.scale(z, z); ctx.translate(-cx, -cy)


def _flicker(gt):
    # a couple of lamp stutters in the establishing shot, then a gentle living shimmer
    f = 1.0 - 0.04 * (fbm1(gt * 3.0, 11) - 0.5)
    for c, w, d in ((6.28, 0.07, 0.55), (6.47, 0.05, 0.35), (11.9, 0.05, 0.2)):
        f -= d * clamp(1 - abs(gt - c) / w)
    return clamp(f, 0.3, 1.1)


def _door_light(ctx, k, t):
    """Cool floodlight spilling in from the (off-screen right) stable door."""
    if k <= 0:
        return
    ctx.save(); ctx.set_operator(cairo.OPERATOR_ADD)
    g = cairo.LinearGradient(W, 0, W * 0.35, 0)
    g.add_color_stop_rgba(0, COOL[0] * 0.55, COOL[1] * 0.6, COOL[2] * 0.7, 0.55 * k)
    g.add_color_stop_rgba(0.5, COOL[0] * 0.3, COOL[1] * 0.35, COOL[2] * 0.45, 0.18 * k)
    g.add_color_stop_rgba(1, 0, 0, 0, 0)
    ctx.set_source(g); ctx.paint()
    # god rays through the door slats
    for i in range(7):
        y0 = 120 + i * 120 + 20 * math.sin(t * 0.7 + i)
        wd = 26 + 20 * _hash(i, 5)
        a = (0.10 + 0.08 * _hash(i, 6)) * k * (0.85 + 0.15 * math.sin(t * 3 + i * 2))
        g = cairo.LinearGradient(W, 0, W * 0.2, 0)
        g.add_color_stop_rgba(0, 0.8, 0.9, 1.0, a); g.add_color_stop_rgba(1, 0.8, 0.9, 1.0, 0)
        ctx.set_source(g)
        ctx.move_to(W + 10, y0); ctx.line_to(W + 10, y0 + wd)
        ctx.line_to(W * 0.25, y0 + wd * 4 + 380); ctx.line_to(W * 0.25, y0 + 300); ctx.close_path(); ctx.fill()
    ctx.restore()


def _world(ctx, t, gt, *, flick, door=0.0, miz_over=None):
    """Paint the whole stable set + characters in world space."""
    draw_stable(ctx, t, lamp_swing=0.35, dust=1.0, lamp_on=flick)
    # ---------------- horse
    nz = smoothstep(T_NUZZLE - 0.35, T_NUZZLE + 0.25, gt) * (1 - smoothstep(14.15, 14.7, gt))
    ear = 0.2 + 0.8 * smoothstep(11.6, 12.3, gt) - 0.5 * nz
    if gt < T_REACT:
        ear += 0.5 * smoothstep(7.2, 7.6, gt) * (1 - smoothstep(8.4, 9.2, gt))   # flick toward Gen's voice
    hblink = max(_blink(gt, (6.6, 8.8, 10.3)),
                 smoothstep(12.35, 12.6, gt) * (1 - smoothstep(12.95, 13.25, gt)),   # the slow, trusting blink
                 0.55 * nz)
    snort = clamp(1 - abs(gt - T_NUZZLE - 0.05) / 0.25)
    hx, hy, hs = HORSE
    draw_horse_head(ctx, hx, hy, hs, facing=1, t=t, blink=hblink, ear=ear, nuzzle=nz,
                    nostril=0.3 + 0.7 * snort, look=(0.6, 0.1), light=(1.0, 0.78, 0.45), rim_strength=0.8)
    # ---------------- Mizuki
    m = mouth("MIZUKI", gt)
    if gt < 10.9:
        expr = "soft"
    elif gt < 11.55:
        expr = "smile"          # "うん。"
    elif gt < T_TURN:
        expr = "soft" if gt < 12.1 else "determined"
    else:
        expr = "determined"
    if 13.35 < gt < 13.9 and expr == "determined" and m < 0.1:
        expr = "tender_eyes_closed"   # the nuzzle lands
    look_at_gen = gt < T_REACT + 0.1
    look = (0.6, -0.05) if look_at_gen else (-0.8, 0.15)
    mb = _blink(gt, (7.9, 10.05, 11.7, 12.95))
    if T_REACT - 0.1 < gt < T_REACT + 0.1:
        mb = max(mb, 0.8)
    tilt = -0.05 * smoothstep(T_REACT, T_REACT + 0.5, gt) - 0.06 * nz
    turn = gt >= T_TURN
    mx, my, ms = MIZ
    if not turn:
        draw_mizuki(ctx, mx, my, ms, view="3q_left", expr=expr, mouth=m, blink=mb, look=look, t=t,
                    helmet=True, goggles="up", arm="stroke", arm_phase=t * 0.32,
                    light=WARM, light_dir=1, rim=RIM, rim_strength=0.7 + 0.2 * door, blush=0.35,
                    head_tilt=tilt)
    else:
        draw_mizuki(ctx, mx + 30, my, ms, view="3q_right", expr="determined", mouth=0.0,
                    blink=_blink(gt, (14.75,)), look=(0.7, -0.05), t=t, helmet=True, goggles="down",
                    arm="down", light=WARM, light_dir=-1, rim=COOL, rim_strength=0.6 + 0.6 * door, blush=0.25)
    # ---------------- Gen
    gx, gy, gs = GEN
    gm = mouth("GEN", gt)
    gexpr = "gruff_smile" if gm < 0.55 or gt > 9.2 else "neutral"
    glook = (-0.7, 0.05) if gt < 9.4 else (-1.0, 0.25)   # to Mizuki, then down to the horse
    draw_gen(ctx, gx, gy, gs, view="3q_left", expr=gexpr, mouth=gm, blink=_blink(gt, (6.45, 8.3, 9.7, 12.2)),
             look=glook, t=t, light=WARM, light_dir=-1, rim=RIM, rim_strength=0.65, arms="crossed")
    _door_light(ctx, door, t)


def draw(ctx, t, dur, gt):
    flick = _flicker(gt)
    door = smoothstep(T_TURN - 0.25, T_TURN + 0.4, gt)
    ctx.save()
    if gt < T_CLOSE_GEN:
        # establishing: slow push-in toward the trio
        k = ease_in_out(invlerp(5.4, T_CLOSE_GEN, gt))
        _cam(ctx, lerp(960, 1000, k), lerp(560, 600, k), lerp(1.0, 1.1, k))
    elif gt < T_REACT:
        # close on 源さん (slow push)
        k = ease_in_out(invlerp(T_CLOSE_GEN, T_REACT, gt))
        _cam(ctx, lerp(1450, 1470, k), lerp(560, 540, k), lerp(1.75, 1.88, k))
    elif gt < T_TURN:
        # two-shot 美月 + ハルカゼ, slow drift in
        k = ease_in_out(invlerp(T_REACT, T_TURN, gt))
        _cam(ctx, lerp(640, 660, k), lerp(560, 560, k), lerp(1.55, 1.75, k))
    else:
        # she turns toward the door: push toward her face
        k = ease_out_cubic(invlerp(T_TURN, 15.1, gt))
        _cam(ctx, lerp(900, 880, k), lerp(480, 470, k), lerp(1.9, 2.2, k))
    _world(ctx, t, gt, flick=flick, door=door)
    ctx.restore()
    # global lamp brightness (flicker darkens the whole set a little)
    if flick < 1.0:
        ctx.set_source_rgba(0.02, 0.01, 0.03, clamp((1 - flick) * 0.6)); ctx.paint()
    # warm grade + soft top darkening
    ctx.save(); ctx.set_operator(cairo.OPERATOR_SOFT_LIGHT)
    ctx.set_source_rgba(1.0, 0.7, 0.4, 0.18); ctx.paint(); ctx.restore()
    vgradient(ctx, 0, 0, W, 260, [(0, (0.02, 0.01, 0.03, 0.45)), (1, (0.02, 0.01, 0.03, 0.0))])
