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
from lib.env import (draw_race_side_bg, draw_race_side_fg, draw_starting_gate, dust_kick)
from lib.chars import draw_mizuki_eyes, draw_hand, Light, SILK, SILK_S, RED, INK

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
    op = 0.42 * smoothstep(0.30, 1.00, u)
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
GS = 1.25                  # gate scale
HS = 1.0                   # horse scale for the nearest stall
N_ST = 7
DXK, DYK, SCK = 118.0, 40.0, 0.925


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
    step = 1 / 36.0
    n = int(dt / step) + 1
    for i in range(max(0, n - 40), n):
        te = i * step
        age = dt - te
        if age < 0:
            continue
        ex = hx0 + horse_x_offset(te, sc) - 130 * HS * sc
        amp = 0.6 + 0.8 * _hash(i, 90 + k)
        # initial explosion bigger
        big = 1.6 if te < 0.25 else 1.0
        r = (30 + 260 * (1 - math.exp(-age * 2.2))) * sc * big * amp
        px = ex - 60 * age * sc + (_hash(i, 91 + k) - 0.5) * 60 * sc
        py = gy - 20 * sc - 90 * (1 - math.exp(-age * 1.8)) * sc * amp
        a = 0.30 * math.exp(-age * 1.5) * clamp(age * 12) * (1 - 0.1 * k)
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


def impact_frames(ctx, gt):
    fi = int(round(gt * FPS)) - int(round(CLANG * FPS))
    if fi == 0:
        # inverted, desaturated, hard black focus lines
        ctx.save()
        ctx.set_operator(cairo.OPERATOR_HSL_SATURATION); ctx.set_source_rgb(0.5, 0.5, 0.5); ctx.paint()
        ctx.set_operator(cairo.OPERATOR_DIFFERENCE); ctx.set_source_rgb(1, 1, 1); ctx.paint()
        ctx.set_operator(cairo.OPERATOR_MULTIPLY); ctx.set_source_rgb(1.0, 0.86, 0.86); ctx.paint()
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
def shot_hands(ctx, gt):
    u = gt - CUT_C
    squeeze = smoothstep(0.08, 0.2, u)
    hp = heart(gt)
    z = 1.0 + 0.05 * u + 0.015 * squeeze
    dx, dy = shake(gt, 2 + 5 * squeeze, 20, 8)
    ctx.save()
    cam(ctx, 960, 540, z, 960 + dx, 540 + dy, -0.02)
    # chestnut neck filling the frame, lit from above
    g = cairo.LinearGradient(0, 0, 0, H)
    c = PAL["harukaze"]
    g.add_color_stop_rgb(0, *mix_color(c, (1, 0.9, 0.75), 0.25))
    g.add_color_stop_rgb(0.45, *c)
    g.add_color_stop_rgb(1, *(c[0] * 0.45, c[1] * 0.4, c[2] * 0.55))
    ctx.set_source(g); ctx.rectangle(-200, -200, W + 400, H + 400); ctx.fill()
    # neck muscle shading
    ctx.set_source_rgba(0.35, 0.12, 0.10, 0.35)
    ctx.move_to(-200, 760); ctx.curve_to(500, 640, 1300, 700, W + 200, 600); ctx.line_to(W + 200, H + 200)
    ctx.line_to(-200, H + 200); ctx.close_path(); ctx.fill()
    # flaxen mane locks along the top, wind-still
    mane = PAL["harukaze_mane"]
    for i in range(22):
        x0 = -150 + i * 100 + 30 * _hash(i, 3)
        sw = math.sin(gt * 2 + i) * 6
        ctx.move_to(x0, -60)
        ctx.curve_to(x0 + 40, 80, x0 + 10 + sw, 200, x0 + 60 + sw, 300 + 60 * _hash(i, 4))
        ctx.curve_to(x0 + 90 + sw, 200, x0 + 110, 80, x0 + 100, -60)
        ctx.close_path()
        fill_rgb(ctx, mix_color(mane, (0.6, 0.4, 0.3), 0.3 * _hash(i, 5)))
        ctx.fill_preserve()
        ctx.set_line_width(3); fill_rgb(ctx, INK, 0.7); ctx.stroke()
    # reins: leather strap diagonally across, tightening
    sag = 60 * (1 - squeeze)
    for off, col in ((0, (0.16, 0.09, 0.06)), (-10, (0.36, 0.22, 0.14))):
        ctx.move_to(-100, 720 + off); ctx.curve_to(600, 650 + sag + off, 1300, 560 + sag + off, W + 100, 360 + off)
        ctx.set_line_width(46 if off == 0 else 16); fill_rgb(ctx, col); ctx.stroke()
    lt = Light((1.0, 0.95, 0.88), -1, RIM, 0.8)
    # sleeves + gripping hands
    for hx, hy, ang, sc in ((700, 640 + 0.55 * sag * 0.7, -0.18, 360), (1260, 520 + 0.45 * sag * 0.7, -0.26, 340)):
        sq = 1 + 0.04 * squeeze
        # sleeve (white silk with red cuff)
        ctx.save(); ctx.translate(hx, hy); ctx.rotate(ang + math.pi)
        ctx.move_to(0, -95); ctx.line_to(700, -150); ctx.line_to(700, 150); ctx.line_to(0, 95); ctx.close_path()
        fill_rgb(ctx, lt.c(SILK, 0.2)); ctx.fill_preserve(); ctx.set_line_width(5); fill_rgb(ctx, INK); ctx.stroke()
        ctx.move_to(0, 20); ctx.line_to(700, 40); ctx.line_to(700, 150); ctx.line_to(0, 95); ctx.close_path()
        fill_rgb(ctx, SILK_S); ctx.fill()
        ctx.rectangle(10, -100, 60, 200); fill_rgb(ctx, RED); ctx.fill()
        # wrinkles
        for j in range(3):
            ctx.move_to(140 + j * 120, -70); ctx.curve_to(170 + j * 120, -10, 150 + j * 120, 30, 190 + j * 120, 80)
            ctx.set_line_width(3); fill_rgb(ctx, INK, 0.5); ctx.stroke()
        ctx.restore()
        draw_hand(ctx, hx - 10, hy, ang, sc * sq, lt, pose="grip", lw=5.0)
    ctx.restore()
    # knuckle tension lines (manga)
    if squeeze > 0.3:
        for i in range(6):
            a = -1.9 + i * 0.25
            for hx, hy in ((820, 560), (1390, 450)):
                r0 = 170 + 20 * math.sin(gt * 40 + i)
                ctx.move_to(hx + math.cos(a) * r0, hy + math.sin(a) * r0)
                ctx.line_to(hx + math.cos(a) * (r0 + 60), hy + math.sin(a) * (r0 + 60))
                ctx.set_line_width(5); ctx.set_source_rgba(1, 1, 1, 0.8 * squeeze); ctx.stroke()
    floodlight_grade(ctx, 1.5)
    ctx.save(); ctx.set_operator(cairo.OPERATOR_MULTIPLY); ctx.set_source_rgb(0.72, 0.74, 0.92); ctx.paint(); ctx.restore()
    letterbox(ctx, 90)


# ============================================================ D: eye + ear insert
def shot_ear(ctx, gt):
    u = gt - CUT_D
    ctx.set_source_rgb(0.02, 0.03, 0.08); ctx.paint()
    z = 1.0 + 0.10 * u
    dx, dy = shake(gt, 2.0, 10, 13)
    ear = lerp(-0.6, 1.0, ease_out_back(invlerp(18.34, 18.42, gt)))
    blink = math.exp(-((gt - 18.2) / 0.035) ** 2)
    ctx.save()
    cam(ctx, 1000, 460, z, 960 + dx, 540 + dy)
    # soft floodlit bokeh behind
    for i in range(10):
        radial_glow(ctx, 200 + i * 190 + 40 * _hash(i, 2), 150 + 180 * _hash(i, 3), 90, (1, 0.9, 0.7), 0.25)
    draw_horse_head(ctx, 520, 1250, 2.3, facing=1, blink=blink, ear=ear, nostril=0.6 + 0.4 * math.sin(gt * 9),
                    look=(0.5, 0.0), t=gt, light=(0.85, 0.92, 1.0), rim_strength=1.0, bridle=True)
    ctx.restore()
    # foreground stall bars (out-of-focus green/white), parallax
    ctx.save()
    ox = -40 * u
    for i in range(-1, 5):
        bx = 180 + i * 520 + ox
        ctx.set_source_rgba(0.94, 0.95, 0.96, 0.92); ctx.rectangle(bx, -50, 34, H + 100); ctx.fill()
        ctx.set_source_rgba(0.5, 0.55, 0.6, 0.6); ctx.rectangle(bx + 22, -50, 12, H + 100); ctx.fill()
    ctx.set_source_rgba(0.06, 0.34, 0.22, 0.97); ctx.rectangle(-50, 820, W + 100, 110); ctx.fill()
    ctx.set_source_rgba(1, 1, 1, 0.5); ctx.rectangle(-50, 820, W + 100, 4); ctx.fill()
    ctx.restore()
    # ear flick accent lines
    fl = invlerp(18.36, 18.40, gt) * (1 - invlerp(18.44, 18.5, gt))
    if fl > 0:
        for i in range(3):
            ctx.move_to(1180 + i * 30, 90 + i * 10); ctx.line_to(1250 + i * 40, 30 + i * 18)
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
    dist = horse_x_offset(dt, hs / HS) * 1.25
    d0 = horse_x_offset(CUT_F - CLANG, hs / HS) * 1.25
    cam_x = 0.30 * (dist - d0)
    hx = -150 + (dist - d0) - cam_x
    dx, dy = shake(gt, 10 * math.exp(-u / 0.4) + 4, 22, 17)
    ctx.save()
    ctx.translate(dx, dy)
    draw_race_side_bg(ctx, gt, 5200 + cam_x, horizon_y=430, track_y=F_TRACK_Y, crowd=1.0, flash=0.5, blur=0.35)
    # rivals further back (smaller, hazier), slightly ahead
    for k, (off, yk, sk) in enumerate(((380, 800, 0.95), (-120, 790, 0.88), (700, 805, 0.9))):
        g2, p2 = gait_at(gt, CLANG + 0.04 * (k + 1))
        rx = -150 + off + (horse_x_offset(dt, sk) - horse_x_offset(CUT_F - CLANG, sk)) * 1.25 - cam_x * 0.9
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
    for i in range(30):
        te = CUT_F - CLANG - 0.3 + i / 30.0
        if te > dt:
            break
        age = dt - te
        ex = -150 + (horse_x_offset(te, hs / HS) * 1.25 - d0) - cam_x - 170 * hs
        r = (40 + 300 * (1 - math.exp(-age * 2.5))) * (0.7 + 0.6 * _hash(i, 5))
        radial_glow(ctx, ex - 80 * age, hy - 40 - 120 * (1 - math.exp(-age * 2)), r, (0.82, 0.68, 0.55),
                    0.35 * math.exp(-age * 1.4) * clamp(age * 10))
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
