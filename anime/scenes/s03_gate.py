"""s03 — 15.0-20.0  goggles eye ECU -> starting gate -> CLANG -> burst.

Editing (global seconds; heartbeats in the audio at 15.25 / 16.17 / 17.00 / 17.745):
  A 15.00-17.00  extreme close-up of 美月's eyes through goggles. Eyes crack open, open fully on the
                 2nd heartbeat, pupils contract (focus); slow creep zoom + heartbeat pulses, then a
                 short anticipation push into the goggles before the cut.
  B 17.00-17.745 side 3/4 view of the floodlit gate, stalls receding up-left, ハルカゼ #14 in the
                 nearest (outer) stall, horses fidgeting; quick push-in toward #14.
  C 17.745-18.10 insert: 美月's hands tighten on the reins (on the heartbeat).
  D 18.10-18.50  insert: ハルカゼ's eye + ear through the stall bars; ear flicks forward at 18.36.
  E 18.50-19.10  CLANG (BEATS gate_clang): 2 impact frames, doors bang open, shake, burst, dust.
  F 19.10-20.00  low tracking shot: ハルカゼ explodes across frame and out right; whiteout into s04.
"""
from lib.common import *
from lib.common import _hash
from timeline import BEATS
from lib.horse import (draw_horse, draw_horse_head, HERO_JOCKEY, JOCKEY_PRESETS, COAT_PRESET_LIST,
                       gait_at, ground_speed, BURST_DURATION, GALLOP_HZ, STRIDE_LEN)
from lib.env import (draw_race_side_bg, draw_race_side_fg, draw_starting_gate, dust_kick, _door_angle)
from lib.chars import draw_mizuki_eyes, draw_hand, Light, SILK, SILK_S, RED, INK, taper

POST = dict(bloom=0.4, grain=0.4, vignette=0.55, aberration=0.0)

T0 = 15.0
CLANG = BEATS["gate_clang"]           # 18.5
HB = [15.25, 16.17, 17.00, 17.745]    # heartbeat hits (audio/sfx.heartbeat_layer)
CUT_B, CUT_C, CUT_D, CUT_F = 17.0, 17.745, 18.10, 19.10

HERO = dict(HERO_JOCKEY)
HARU = dict(coat=PAL["harukaze"], mane=PAL["harukaze_mane"])
RIM = (0.78, 0.88, 1.0)


def heart(gt):
    """Heartbeat envelope (lub + dub), 0..~1."""
    v = 0.0
    for b in HB:
        d = gt - b
        if d >= 0:
            v += math.exp(-d / 0.07)
        d2 = d - 0.19
        if d2 >= 0:
            v += 0.6 * math.exp(-d2 / 0.06)
    return v


def cam(ctx, fx, fy, z, sx=W / 2, sy=H / 2, rot=0.0):
    """Zoom z around world point (fx,fy) placed at screen (sx,sy)."""
    ctx.translate(sx, sy)
    if rot:
        ctx.rotate(rot)
    ctx.scale(z, z)
    ctx.translate(-fx, -fy)


def letterbox(ctx, h):
    ctx.set_source_rgb(0, 0, 0)
    ctx.rectangle(0, 0, W, h); ctx.fill()
    ctx.rectangle(0, H - h, W, h); ctx.fill()


# ============================================================ A: eyes
def shot_eyes(ctx, gt):
    u = gt - T0
    ctx.set_source_rgb(0.02, 0.02, 0.05); ctx.paint()
    # eyelids: crack open, hold heavy, snap open on heartbeat 2
    op = 0.42 * smoothstep(0.25, 1.00, u)
    op += 0.58 * ease_out_cubic(invlerp(HB[1] - 0.02, HB[1] + 0.22, gt))
    op -= 0.08 * math.exp(-((u - 0.95) / 0.12) ** 2)          # heavy flutter
    focus = smoothstep(HB[1] + 0.1, HB[2] - 0.15, gt)
    look = ((noise1(u * 1.3, 4) - 0.5) * 0.35 * (1 - focus), (noise1(u * 1.1, 9) - 0.5) * 0.2 * (1 - focus) + 0.02)
    hp = heart(gt)
    z = 1.0 + 0.045 * u + 0.012 * hp
    z += 0.16 * ease_in_cubic(invlerp(16.78, 17.0, gt))       # anticipation push
    dx, dy = shake(gt, 1.5 + 3 * hp, 9, 3)
    ctx.save()
    cam(ctx, 960 + 250 * smoothstep(0.2, 2.0, u) * 0, 540, z, 960 + dx, 540 + dy)
    draw_mizuki_eyes(ctx, 960, 540, 1.0, t=gt, open=op, look=look, goggles=True, reflect_lights=True,
                     focus=focus, blush=0.2, light=(1.0, 0.93, 0.84))
    ctx.restore()
    # night grading: cool multiply, top shadow from the helmet brim, floodlight sheen sweeping the lens
    ctx.save()
    ctx.set_operator(cairo.OPERATOR_MULTIPLY)
    g = cairo.LinearGradient(0, 0, 0, H)
    g.add_color_stop_rgb(0, 0.35, 0.36, 0.55)
    g.add_color_stop_rgb(0.35, 0.78, 0.80, 0.96)
    g.add_color_stop_rgb(1, 0.62, 0.62, 0.82)
    ctx.set_source(g); ctx.paint()
    ctx.restore()
    sweep = invlerp(15.6, 16.9, gt)
    if 0 < sweep < 1:
        x = lerp(-500, W + 500, ease_in_out(sweep))
        ctx.save()
        ctx.set_operator(cairo.OPERATOR_ADD)
        g = cairo.LinearGradient(x - 220, 0, x + 220, 0)
        g.add_color_stop_rgba(0, 1, 0.95, 0.85, 0)
        g.add_color_stop_rgba(0.5, 1, 0.95, 0.85, 0.10)
        g.add_color_stop_rgba(1, 1, 0.95, 0.85, 0)
        ctx.set_source(g)
        ctx.move_to(x - 320, H); ctx.line_to(x + 80, 0); ctx.line_to(x + 520, 0); ctx.line_to(x + 120, H)
        ctx.close_path(); ctx.fill()
        ctx.restore()
    # heartbeat: edges darken on every beat
    if hp > 0.01:
        g = cairo.RadialGradient(W / 2, H / 2, 300, W / 2, H / 2, 1150)
        g.add_color_stop_rgba(0, 0, 0, 0, 0)
        g.add_color_stop_rgba(1, 0.04, 0, 0.02, clamp(0.55 * hp))
        ctx.set_source(g); ctx.paint()
    letterbox(ctx, 118)


# ============================================================ gate set (B, E)
GX, GY = 900.0, 880.0      # nearest stall ground point
GS = 1.5                  # gate scale
HS = 1.0                   # horse scale for the nearest stall
N_ST = 7
DXK, DYK, SCK = 140.0, 46.0, 0.925


def stall_geo(k):
    sc = SCK ** k
    x = GX - DXK * sum(SCK ** j for j in range(k))
    y = GY - DYK * sum(SCK ** j for j in range(k))
    return x, y, sc


def horse_x_offset(dt, sc):
    """Distance travelled after the break (px): accelerating to gallop speed."""
    if dt <= 0:
        return 0.0
    v = ground_speed(HS * sc) * 1.15
    B = BURST_DURATION
    if dt < B:
        return v * dt * dt / (2 * B)
    return v * (B / 2 + dt - B)


def jockey_for(k):
    if k == 0:
        return dict(HERO)
    J = dict(JOCKEY_PRESETS[(k * 3 + 1) % len(JOCKEY_PRESETS)])
    return J


def coat_for(k):
    if k == 0:
        return HARU
    c = COAT_PRESET_LIST[(k * 2 + 1) % len(COAT_PRESET_LIST)]
    return c


def burst_delay(k):
    return 0.0 if k == 0 else 0.015 + 0.07 * _hash(k, 71)


def draw_gate_set(ctx, gt, open_, fog=0.10):
    """All stalls far->near with horses; returns screen-space info of the hero horse."""
    info = None
    # long floodlight shadow of the gate row falling to the lower right
    x_far, y_far, sc_far = stall_geo(N_ST - 1)
    Lg = 330 * GS
    ctx.move_to(x_far - Lg / 2 * sc_far, y_far); ctx.line_to(GX + Lg / 2 + 30, GY)
    ctx.line_to(GX + Lg / 2 + 420, GY + 120); ctx.line_to(GX - Lg / 2 + 260, GY + 150); ctx.close_path()
    g = cairo.LinearGradient(0, GY - 40, 0, GY + 150)
    g.add_color_stop_rgba(0, 0.0, 0.0, 0.04, 0.45); g.add_color_stop_rgba(1, 0.0, 0.0, 0.04, 0.0)
    ctx.set_source(g); ctx.fill()
    for k in range(N_ST - 1, -1, -1):
        sx, sy, sc = stall_geo(k)
        s_g = GS * sc
        L = 330 * s_g
        draw_starting_gate(ctx, gt, sx, sy, s_g, open=open_, n_stalls=1, view="side", part="back")
        hs = HS * sc
        hx0 = sx + L / 2 - 178 * hs
        t_b = CLANG + burst_delay(k)
        gait, ph = gait_at(gt, t_b)
        dt = gt - t_b
        J = jockey_for(k)
        # fidget in the stall
        fid = (noise1(gt * 1.6, 11 + k) - 0.5)
        if gait == "stand":
            ph = (gt * 0.45 + k * 0.37) % 1.0
            J["crouch"] = 0.55 + 0.1 * noise1(gt * 0.8, 30 + k)
            J["push"] = 0.0
            hx = hx0 + fid * 10 * hs
            hu = 0.25 + 0.35 * (noise1(gt * 1.1, 50 + k) - 0.5)
            mb = 0.0
        else:
            J["crouch"] = 1.0
            J["push"] = clamp(dt * 3.0)
            hx = hx0 + horse_x_offset(dt, sc)
            hu = 0.0
            mb = clamp((dt - 0.15) * 2.5) * 0.9
        cc = coat_for(k)
        shade = 0.12 * k if k else 0.0
        P = draw_horse(ctx, hx, sy, hs, ph, facing=1, coat=cc["coat"], mane=cc["mane"], jockey=J,
                       gait=gait, t=gt + k * 1.7, rim=RIM, rim_strength=0.9, shade=shade,
                       motion_blur=mb, head_up=hu, number=14 - k, mane_wind=0.3 if gait == "stand" else 1.0,
                       blaze=(k == 0 or k % 3 == 1), socks=(False, False, True, False) if k == 0 else (k % 2 == 0, False, k % 3 == 0, False))
        draw_starting_gate(ctx, gt, sx, sy, s_g, open=open_, n_stalls=1, view="side", part="front")
        if open_ > 0:     # tone the floodlit door panel down (it swings toward the camera and blows out)
            wv = 108 * s_g * math.sin(_door_angle(open_))
            xf = sx + L / 2
            dt_, db_ = sy - 236 * s_g, sy - 16 * s_g
            ctx.move_to(xf, dt_); ctx.line_to(xf + wv, dt_ - wv * 0.12); ctx.line_to(xf + wv, db_ + wv * 0.06)
            ctx.line_to(xf, db_); ctx.close_path()
            g = cairo.LinearGradient(xf, 0, xf + wv + 1, 0)
            g.add_color_stop_rgba(0, 0.05, 0.08, 0.18, 0.55); g.add_color_stop_rgba(1, 0.05, 0.08, 0.18, 0.25)
            ctx.set_source(g); ctx.fill()
        if dt > 0:
            burst_dust(ctx, gt, t_b, sx + L / 2 - 178 * hs, sy, sc, k)
        if k == 0:
            info = dict(x=hx, y=sy, hs=hs, dt=dt)
        elif fog > 0:
            ctx.set_source_rgba(0.04, 0.05, 0.13, fog)
            ctx.paint()
    return info


def burst_dust(ctx, gt, t_b, hx0, gy, sc, k):
    """World-space dust puffs left behind by the breaking horse (deterministic in gt)."""
    dt = gt - t_b
    step = 1 / 36.0 if k < 2 else 1 / 16.0
    n = int(dt / step) + 1
    for i in range(max(0, n - (40 if k < 2 else 16)), n):
        te = i * step
        age = dt - te
        if age < 0:
            continue
        ex = hx0 + horse_x_offset(te, sc) - 130 * HS * sc
        amp = 0.6 + 0.8 * _hash(i, 90 + k)
        # initial explosion bigger
        big = 1.9 if te < 0.25 else 1.0
        r = (30 + 260 * (1 - math.exp(-age * 2.2))) * sc * big * amp
        px = ex - 60 * age * sc + (_hash(i, 91 + k) - 0.5) * 60 * sc
        py = gy - 20 * sc - 90 * (1 - math.exp(-age * 1.8)) * sc * amp
        a = 0.45 * math.exp(-age * 1.3) * clamp(age * 12) * (1 - 0.1 * k)
        if a < 0.01:
            continue
        radial_glow(ctx, px, py, r, (0.78, 0.64, 0.52), a)
    # clods from the hooves
    if dt < 1.6:
        dust_kick(ctx, gt, hx0 + horse_x_offset(dt, sc) - 120 * HS * sc, gy, strength=clamp(1.4 - dt * 0.5) * sc,
                  seed=k + 3, direction=-1.0, speed=1.0)


def gate_background(ctx, gt):
    draw_race_side_bg(ctx, gt, 5200.0, horizon_y=430, track_y=760, crowd=1.0, flash=0.25, blur=0.0)


def floodlight_grade(ctx, strength=1.0):
    """Cool floodlit night grading + top-left light pool."""
    ctx.save()
    g = cairo.RadialGradient(620, 120, 100, 620, 120, 1500)
    g.add_color_stop_rgba(0, 1, 0.96, 0.86, 0.10 * strength)
    g.add_color_stop_rgba(1, 1, 0.96, 0.86, 0)
    ctx.set_operator(cairo.OPERATOR_ADD); ctx.set_source(g); ctx.paint()
    ctx.restore()


def shot_gate_idle(ctx, gt):
    """B: tension wide, quick push-in on #14."""
    u = gt - CUT_B
    k = ease_out_cubic(invlerp(0.0, 0.55, u))
    z = lerp(1.0, 1.16, k) + 0.02 * u
    fx, fy = lerp(900, 980, k), lerp(560, 590, k)
    dx, dy = shake(gt, 1.2, 6, 5)
    ctx.save()
    cam(ctx, fx, fy, z, W / 2 + dx, H / 2 + dy)
    gate_background(ctx, gt)
    draw_gate_set(ctx, gt, 0.0)
    ctx.restore()
    floodlight_grade(ctx)
    letterbox(ctx, 60 * (1 - k))


def shot_gate_break(ctx, gt):
    """E: CLANG. doors open, horses burst, shake."""
    u = gt - CLANG
    open_ = clamp(u / 0.4)
    kick = math.exp(-u / 0.25)
    z = 1.22 - 0.10 * ease_out_cubic(invlerp(0.0, 0.5, u)) + 0.05 * kick
    amp = 26 * math.exp(-u / 0.22) + 5
    dx, dy = shake(gt, amp, 26, 7)
    rot = (noise1(gt * 20, 12) - 0.5) * 0.02 * math.exp(-u / 0.3)
    fx = 980 + 260 * ease_in_cubic(invlerp(0.1, 0.6, u))
    ctx.save()
    cam(ctx, fx, 600, z, W / 2 + dx, H / 2 + dy, rot)
    gate_background(ctx, gt)
    info = draw_gate_set(ctx, gt, open_)
    ctx.restore()
    floodlight_grade(ctx)
    # manga focus lines around the hero at the break
    sl = math.exp(-u / 0.35)
    if sl > 0.05:
        speed_lines(ctx, gt, W * 0.58, H * 0.52, n=110, inner=430, outer=1500, color=(1, 1, 1), alpha=0.5 * sl, seed=21)
    impact_frames(ctx, gt)


def _snapshot(ctx):
    tgt = ctx.get_target()
    snap = cairo.ImageSurface(cairo.FORMAT_ARGB32, tgt.get_width(), tgt.get_height())
    c2 = cairo.Context(snap); c2.set_source_surface(tgt, 0, 0); c2.paint()
    return snap


def impact_frames(ctx, gt):
    fi = int(round(gt * FPS)) - int(round(CLANG * FPS))
    if fi == 0:
        # inverted, desaturated, hard black focus lines
        ctx.save()
        ctx.set_operator(cairo.OPERATOR_HSL_SATURATION); ctx.set_source_rgb(0.5, 0.5, 0.5); ctx.paint()
        for _ in range(2):                       # contrast boost: hard-light the frame onto itself
            snap = _snapshot(ctx)
            ctx.set_operator(cairo.OPERATOR_HARD_LIGHT); ctx.set_source_surface(snap, 0, 0); ctx.paint()
        ctx.set_operator(cairo.OPERATOR_DIFFERENCE); ctx.set_source_rgb(1, 1, 1); ctx.paint()
        ctx.set_operator(cairo.OPERATOR_MULTIPLY); ctx.set_source_rgb(1.0, 0.80, 0.82); ctx.paint()
        ctx.restore()
        ctx.save()
        speed_lines(ctx, gt, W * 0.56, H * 0.5, n=150, inner=330, outer=1600, color=(0, 0, 0), alpha=0.95, seed=33)
        ctx.restore()
        POST["aberration"] = 6.0
    elif fi == 1:
        ctx.save()
        ctx.set_operator(cairo.OPERATOR_ADD)
        ctx.set_source_rgba(1, 0.95, 0.9, 0.45); ctx.paint()
        ctx.restore()
        speed_lines(ctx, gt, W * 0.56, H * 0.5, n=140, inner=380, outer=1600, color=(1, 1, 1), alpha=0.9, seed=34)
        POST["aberration"] = 4.0
    elif fi in (2, 3):
        POST["aberration"] = 2.0


# ============================================================ C: hands on reins
SKIN = PAL["skin"]
SKIN_D = (0.86, 0.60, 0.56)


def _fist(ctx, x, y, ang, s, squeeze, light=1.0):
    """Side view of a fist gripping a rein that runs along local +x."""
    ctx.save(); ctx.translate(x, y); ctx.rotate(ang); ctx.scale(s, s)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND); ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    sq = squeeze
    sk = mix_color(SKIN, (0.80, 0.62, 0.62), 0.25)
    # sleeve going up-left out of frame (white silk, red cuff)
    ctx.move_to(-150, -120); ctx.line_to(-640, -620); ctx.line_to(-330, -820); ctx.line_to(40, -190); ctx.close_path()
    fill_rgb(ctx, (0.90, 0.91, 0.97)); ctx.fill_preserve(); ctx.set_line_width(5); fill_rgb(ctx, INK); ctx.stroke()
    ctx.move_to(-10, -170); ctx.line_to(-400, -760); ctx.line_to(-330, -820); ctx.line_to(40, -190); ctx.close_path()
    fill_rgb(ctx, (0.62, 0.64, 0.80)); ctx.fill()
    for j in range(3):
        ctx.move_to(-230 - j * 90, -300 - j * 110); ctx.curve_to(-180 - j * 90, -330 - j * 110, -150 - j * 90, -380 - j * 110, -120 - j * 90, -420 - j * 110)
        ctx.set_line_width(4); fill_rgb(ctx, INK, 0.45); ctx.stroke()
    ctx.move_to(-150, -120); ctx.line_to(-200, -170); ctx.line_to(10, -230); ctx.line_to(40, -190); ctx.close_path()
    fill_rgb(ctx, RED); ctx.fill_preserve(); ctx.set_line_width(4); fill_rgb(ctx, INK); ctx.stroke()
    # back of the hand
    ctx.move_to(-150, -120); ctx.curve_to(-170, -60, -120, -20, -80, -14)
    ctx.line_to(90, -22); ctx.curve_to(110, -60, 80, -150, 40, -190); ctx.close_path()
    fill_rgb(ctx, sk); ctx.fill_preserve(); ctx.set_line_width(5); fill_rgb(ctx, INK); ctx.stroke()
    ctx.move_to(-60, -150); ctx.curve_to(-20, -120, 30, -110, 60, -40)
    ctx.set_line_width(3); fill_rgb(ctx, SKIN_D, 0.8); ctx.stroke()
    # curled fingers along the rein (index nearest the bit, +x)
    for i, fx in enumerate((-78, -34, 10, 54)):
        fy = 18 - 4 * sq + 3 * i
        ctx.new_path(); ctx.save(); ctx.translate(fx, fy); ctx.scale(1.0, 1.35 - 0.06 * sq)
        ctx.arc(0, 0, 25, 0, TAU); ctx.restore()
        fill_rgb(ctx, sk); ctx.fill_preserve(); ctx.set_line_width(4.5); fill_rgb(ctx, INK); ctx.stroke()
        # shadow on lower half + knuckle highlight
        ctx.save(); ctx.translate(fx, fy); ctx.scale(1.0, 1.35)
        ctx.arc(0, 0, 22, 0.2, math.pi - 0.2); ctx.restore()
        ctx.set_line_width(6); fill_rgb(ctx, SKIN_D, 0.9); ctx.stroke()
        ctx.save(); ctx.translate(fx - 6, fy - 20); ctx.scale(1, 0.6); ctx.arc(0, 0, 7, 0, TAU); ctx.restore()
        fill_rgb(ctx, (1, 1, 1), 0.55 * light); ctx.fill()
        # whitened knuckles when squeezing
        if sq > 0.1:
            ctx.save(); ctx.translate(fx, fy - 18); ctx.scale(1, 0.5); ctx.arc(0, 0, 12, 0, TAU); ctx.restore()
            fill_rgb(ctx, (1, 0.95, 0.92), 0.5 * sq); ctx.fill()
    # thumb pressing on top of the rein
    ctx.move_to(-40, -40); ctx.curve_to(10, -64 - 6 * sq, 70, -60, 98, -34)
    ctx.curve_to(112, -20, 100, -6, 84, -10); ctx.curve_to(50, -22, 10, -18, -30, -14); ctx.close_path()
    fill_rgb(ctx, sk); ctx.fill_preserve(); ctx.set_line_width(5); fill_rgb(ctx, INK); ctx.stroke()
    ctx.move_to(80, -38); ctx.curve_to(90, -34, 96, -28, 96, -22); ctx.set_line_width(3); fill_rgb(ctx, INK, 0.6); ctx.stroke()
    ctx.restore()


def _rein(ctx, pts, w, squeeze):
    ctx.new_path(); smooth_path(ctx, pts)
    path = ctx.copy_path()
    ctx.set_line_width(w + 8); fill_rgb(ctx, INK); ctx.stroke()
    ctx.new_path(); ctx.append_path(path); ctx.set_line_width(w); fill_rgb(ctx, (0.30, 0.17, 0.10)); ctx.stroke()
    ctx.new_path(); ctx.append_path(path); ctx.set_line_width(w * 0.25)
    ctx.set_dash([18, 14]); fill_rgb(ctx, (0.62, 0.42, 0.26), 0.8); ctx.stroke(); ctx.set_dash([])


def shot_hands(ctx, gt):
    u = gt - CUT_C
    squeeze = ease_out_cubic(invlerp(0.04, 0.16, u))
    z = 1.04 + 0.06 * u
    dx, dy = shake(gt, 1.5 + 5 * squeeze * math.exp(-(u - 0.12) * 6 if u > 0.12 else 0), 24, 8)
    ctx.save()
    cam(ctx, 960, 560, z, 960 + dx, 540 + dy, -0.035)
    # dark floodlit night behind (out of focus)
    vgradient(ctx, -300, -300, W + 600, H + 600, [(0, (0.05, 0.06, 0.16)), (1, (0.12, 0.08, 0.14))])
    for i in range(8):
        radial_glow(ctx, 120 + i * 260 + 60 * _hash(i, 8), 80 + 120 * _hash(i, 9), 110, (1, 0.92, 0.75), 0.32)
    # soft stall bars behind (out of focus)
    for bx in (1450, 1760):
        ctx.set_source_rgba(0.08, 0.36, 0.25, 0.8); ctx.rectangle(bx, -300, 70, 900); ctx.fill()
        ctx.set_source_rgba(0.7, 0.8, 0.8, 0.25); ctx.rectangle(bx + 8, -300, 8, 900); ctx.fill()
    # chestnut neck from lower right, crest rising to the right
    c = PAL["harukaze"]
    crest = [(-300, 790), (400, 670), (1000, 545), (1600, 410), (2300, 260)]
    ctx.new_path(); smooth_path(ctx, crest); ctx.line_to(2300, 1500); ctx.line_to(-300, 1500); ctx.close_path()
    neck = ctx.copy_path()
    g = cairo.LinearGradient(0, 380, 0, 1300)
    g.add_color_stop_rgb(0, *mix_color(c, (1, 0.93, 0.8), 0.18))
    g.add_color_stop_rgb(0.5, *c)
    g.add_color_stop_rgb(1, c[0] * 0.5, c[1] * 0.42, c[2] * 0.6)
    ctx.set_source(g); ctx.fill_preserve(); ctx.set_line_width(5); fill_rgb(ctx, INK); ctx.stroke()
    # neck muscle band shadow
    ctx.save(); ctx.new_path(); ctx.append_path(neck); ctx.clip()
    ctx.move_to(-300, 1100); ctx.curve_to(500, 950, 1300, 860, 2300, 700); ctx.line_to(2300, 1500); ctx.line_to(-300, 1500)
    ctx.close_path(); fill_rgb(ctx, (0.45, 0.2, 0.2), 0.35); ctx.fill()
    ctx.restore()
    # flaxen mane falling over the near side of the crest (tapered strands, two layers)
    mane = PAL["harukaze_mane"]
    for layer in (0, 1):
        n = 46
        for i in range(n):
            f = (i + 0.5 * layer + 0.3 * _hash(i, 6 + layer)) / n
            bx = lerp(-250, 2250, f); by = lerp(785, 268, f) - 25 * math.sin(f * 3) - 10
            L = (150 + 150 * _hash(i, 4 + layer)) * (0.8 if layer == 0 else 1.0)
            sw = math.sin(gt * 2.2 + i * 1.3) * 6
            curl = (_hash(i, 12 + layer) - 0.5) * 50
            pts = [(bx, by - 15), (bx - 12 + curl * 0.3, by + L * 0.35), (bx - 30 + curl + sw, by + L * 0.7),
                   (bx - 50 + curl * 1.4 + sw, by + L)]
            col = mix_color(mane, (0.70, 0.44, 0.28), 0.45 if layer == 0 else 0.15 * _hash(i, 5))
            taper(ctx, pts, 30 + 22 * _hash(i, 7), INK, 0.8, n=14, prof="start")
            taper(ctx, pts, 24 + 18 * _hash(i, 7), col, 1.0, n=14, prof="start")
            if layer:
                hl = [(p[0] + 4, p[1]) for p in pts[:3]]
                taper(ctx, hl, 7, (1, 0.94, 0.78), 0.55, n=10, prof="mid")
    # reins: from each fist toward the bit (off right), sag goes out as she takes hold
    sag = 50 * (1 - squeeze)
    h1, h2 = (640, 560), (1180, 450)
    _rein(ctx, [(h1[0] - 260, h1[1] + 90), h1, (h1[0] + 420, h1[1] - 20 + sag), (h1[0] + 900, h1[1] - 160 + sag * 0.5), (2300, 180)], 30, squeeze)
    _rein(ctx, [(h2[0] - 200, h2[1] + 70), h2, (h2[0] + 420, h2[1] - 60 + sag), (2300, 120)], 30, squeeze)
    sq_s = 1.0 + 0.03 * squeeze
    _fist(ctx, h1[0], h1[1], -0.10, 1.35 * sq_s, squeeze)
    _fist(ctx, h2[0], h2[1], -0.18, 1.25 * sq_s, squeeze)
    ctx.restore()
    # tension accent lines around the fists
    if squeeze > 0.2:
        a0 = 0.9 * squeeze * (0.6 + 0.4 * math.sin(gt * 50))
        for hx, hy in ((700, 520), (1240, 410)):
            for i in range(5):
                a = -2.3 + i * 0.28
                r0 = 200
                ctx.move_to(hx + math.cos(a) * r0, hy + math.sin(a) * r0)
                ctx.line_to(hx + math.cos(a) * (r0 + 70), hy + math.sin(a) * (r0 + 70))
                ctx.set_line_width(6); ctx.set_source_rgba(1, 1, 1, a0); ctx.stroke()
    ctx.save(); ctx.set_operator(cairo.OPERATOR_MULTIPLY)
    g = cairo.LinearGradient(0, 0, W, H)
    g.add_color_stop_rgb(0, 0.95, 0.93, 0.95); g.add_color_stop_rgb(1, 0.55, 0.58, 0.82)
    ctx.set_source(g); ctx.paint(); ctx.restore()
    floodlight_grade(ctx, 1.2)
    letterbox(ctx, 90)


# ============================================================ D: eye + ear insert
def shot_ear(ctx, gt):
    u = gt - CUT_D
    ear_k = ease_out_back(invlerp(18.34, 18.42, gt))
    ear = lerp(-0.7, 1.0, ear_k)
    blink = math.exp(-((gt - 18.2) / 0.035) ** 2)
    z = 1.0 + 0.10 * u + 0.05 * ear_k
    dx, dy = shake(gt, 1.5 + 4 * ear_k * (1 - ear_k * 0.7), 14, 13)
    ctx.save()
    cam(ctx, 900, 480, z, 960 + dx, 540 + dy)
    # beyond the gate: dark floodlit track, soft bokeh
    vgradient(ctx, -200, -200, W + 400, H + 400, [(0, (0.03, 0.04, 0.12)), (0.55, (0.10, 0.09, 0.20)),
                                                 (0.7, (0.24, 0.17, 0.16)), (1, (0.12, 0.08, 0.07))])
    for i in range(12):
        radial_glow(ctx, 700 + i * 120 + 50 * _hash(i, 2), 80 + 260 * _hash(i, 3), 60 + 50 * _hash(i, 4),
                    (1, 0.9, 0.7), 0.35)
    # gate front door (closed) + frame post
    ctx.set_source_rgb(0.05, 0.28, 0.19); ctx.rectangle(1330, -200, 60, H + 400); ctx.fill()
    ctx.set_source_rgba(0.7, 0.9, 0.8, 0.5); ctx.rectangle(1338, -200, 8, H + 400); ctx.fill()
    ctx.set_source_rgb(0.80, 0.82, 0.86); ctx.rectangle(1390, 560, 700, 560); ctx.fill()
    ctx.set_source_rgb(0.05, 0.28, 0.19); ctx.rectangle(1390, 560, 700, 16); ctx.fill()
    ctx.set_source_rgba(0.05, 0.28, 0.19, 0.5)
    for k in range(1, 9):
        ctx.rectangle(1390, 560 + k * 60, 700, 3)
    ctx.fill()
    draw_horse_head(ctx, 330, 1330, 2.25, facing=1, blink=blink, ear=ear, nostril=0.6 + 0.4 * math.sin(gt * 9),
                    look=(0.6, 0.0), t=gt, light=(0.85, 0.92, 1.0), rim_strength=1.0, bridle=True)
    ctx.restore()
    # foreground side-panel bar + rail (out of focus, parallax)
    ctx.save()
    ox = -60 * u
    for bx in (60 + ox, 1560 + ox):
        g = cairo.LinearGradient(bx - 30, 0, bx + 70, 0)
        g.add_color_stop_rgba(0, 0.9, 0.92, 0.95, 0); g.add_color_stop_rgba(0.3, 0.9, 0.92, 0.95, 0.9)
        g.add_color_stop_rgba(0.7, 0.55, 0.6, 0.7, 0.9); g.add_color_stop_rgba(1, 0.55, 0.6, 0.7, 0)
        ctx.set_source(g); ctx.rectangle(bx - 30, -50, 100, H + 100); ctx.fill()
    g = cairo.LinearGradient(0, 900, 0, 1040)
    g.add_color_stop_rgba(0, 0.06, 0.34, 0.22, 0); g.add_color_stop_rgba(0.2, 0.06, 0.34, 0.22, 0.97)
    g.add_color_stop_rgba(1, 0.03, 0.18, 0.12, 0.97)
    ctx.set_source(g); ctx.rectangle(-50, 900, W + 100, 200); ctx.fill()
    ctx.restore()
    # ear flick accent lines
    fl = invlerp(18.36, 18.40, gt) * (1 - invlerp(18.44, 18.5, gt))
    if fl > 0:
        for i in range(3):
            ctx.move_to(610 + i * 34, 110 - i * 6); ctx.line_to(670 + i * 44, 40 - i * 12)
            ctx.set_line_width(6); ctx.set_source_rgba(1, 1, 1, 0.9 * fl); ctx.stroke()
    ctx.save(); ctx.set_operator(cairo.OPERATOR_MULTIPLY); ctx.set_source_rgb(0.8, 0.82, 0.96); ctx.paint(); ctx.restore()
    letterbox(ctx, 90)


# ============================================================ F: low tracking burst
F_TRACK_Y = 780


def shot_track(ctx, gt):
    u = gt - CUT_F
    dt = gt - CLANG
    hs = 1.45
    gait, ph = gait_at(gt, CLANG)
    dist = horse_x_offset(dt, hs / HS) * 1.5
    d0 = horse_x_offset(CUT_F - CLANG, hs / HS) * 1.5
    cam_x = 0.45 * (dist - d0)             # background pan (the camera can't keep up)
    hx = -300 + (dist - d0)
    dx, dy = shake(gt, 10 * math.exp(-u / 0.4) + 4, 22, 17)
    ctx.save()
    ctx.translate(dx, dy)
    draw_race_side_bg(ctx, gt, 5200 + cam_x, horizon_y=430, track_y=F_TRACK_Y, crowd=1.0, flash=0.5, blur=0.35)
    # rivals further back (smaller, hazier), slightly ahead
    for k, (off, yk, sk) in enumerate(((380, 800, 0.95), (-120, 790, 0.88), (700, 805, 0.9))):
        g2, p2 = gait_at(gt, CLANG + 0.04 * (k + 1))
        rx = -300 + off + (horse_x_offset(dt, sk) - horse_x_offset(CUT_F - CLANG, sk)) * 1.5 * 0.92
        J = dict(JOCKEY_PRESETS[(k * 2 + 3) % 8]); J["crouch"] = 1.0; J["push"] = 0.8
        cc = COAT_PRESET_LIST[(k * 3 + 1) % len(COAT_PRESET_LIST)]
        draw_horse(ctx, rx, yk, sk, (p2 + 0.1 * k) % 1.0 if g2 == "gallop" else p2, facing=1, coat=cc["coat"],
                   mane=cc["mane"], jockey=J, gait=g2, t=gt, rim=RIM, shade=0.35, motion_blur=0.8, number=[9, 12, 5][k])
        dust_kick(ctx, gt, rx - 110 * sk, yk, strength=0.8, seed=40 + k)
    ctx.set_source_rgba(0.05, 0.06, 0.14, 0.18); ctx.paint()
    # hero
    J = dict(HERO); J["crouch"] = 1.0; J["push"] = 1.0
    hy = 990
    # dust trail in world space
    for i in range(48):
        te = CUT_F - CLANG - 0.4 + i / 40.0
        if te > dt:
            break
        age = dt - te
        ex = -300 + (horse_x_offset(te, hs / HS) * 1.5 - d0) - 0.45 * (horse_x_offset(dt, hs / HS) * 1.5 - horse_x_offset(te, hs / HS) * 1.5) - 170 * hs
        r = (40 + 300 * (1 - math.exp(-age * 2.5))) * (0.7 + 0.6 * _hash(i, 5))
        radial_glow(ctx, ex - 80 * age, hy - 40 - 150 * (1 - math.exp(-age * 2)), r * 1.3, (0.86, 0.72, 0.58),
                    0.55 * math.exp(-age * 1.2) * clamp(age * 10))
    draw_horse(ctx, hx, hy, hs, ph, facing=1, coat=HARU["coat"], mane=HARU["mane"], jockey=J, gait=gait, t=gt,
               rim=RIM, rim_strength=1.0, motion_blur=1.0, number=14, mane_wind=1.2)
    dust_kick(ctx, gt, hx - 150 * hs, hy, strength=1.8, seed=7, speed=1.3)
    dust_kick(ctx, gt, hx + 120 * hs, hy, strength=1.0, seed=8, speed=1.3)
    draw_race_side_fg(ctx, gt, 5200 + cam_x, track_y=F_TRACK_Y + 120, rail=False, blur=0.6, clods=1.0, grass=False)
    ctx.restore()
    horiz_speed_lines(ctx, gt, 120, H - 120, n=26, speed=3200, alpha=0.35, seed=19)
    floodlight_grade(ctx)
    # whiteout into s04's flash
    w = ease_in_cubic(invlerp(19.80, 20.0, gt))
    if w > 0:
        ctx.set_source_rgba(1, 1, 1, 0.85 * w); ctx.paint()


# ============================================================ main
def draw(ctx, t, dur, gt):
    POST["aberration"] = 0.0
    if gt < CUT_B:
        shot_eyes(ctx, gt)
    elif gt < CUT_C:
        shot_gate_idle(ctx, gt)
    elif gt < CUT_D:
        shot_hands(ctx, gt)
    elif gt < CLANG - 1e-6:
        shot_ear(ctx, gt)
    elif gt < CUT_F:
        shot_gate_break(ctx, gt)
    else:
        shot_track(ctx, gt)
