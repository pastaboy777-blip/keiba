"""s04 — the race, first part (global 20.0-33.0).

Beat sheet (global seconds)
  20.00-24.50  A  wide side tracking shot. Camera starts on the leaders and drifts back through the pack
                  to reveal ハルカゼ #14 dead last (L05 "ハルカゼは最後方!" 20.9). AI brackets lock on her.
  24.50-27.00  B  close-up 美月 riding, calm "whisper" focus, telephoto blurred stands (L06 25.2).
  27.00-28.10  C1 extreme low angle: ハルカゼ's hooves pounding the dirt, clods, dutch tilt.
  28.10-29.60  C2 pack enters the 4th corner: frame tilts, horses lean, ハルカゼ swings wide.
  29.60-30.80  D  IMPACT FRAME -> 美月 shouting "今だ、ハルカゼ!" on radial focus lines (L07).
  30.80-33.00  E  ハルカゼ kicks: longer, faster strides, motion blur, she sweeps past the pack on the
                  outside; camera shake, smeared background, prob panel ticking up.
"""
import math
import numpy as np
import cairo

from lib.common import *
from lib.horse import (draw_horse, HERO_JOCKEY, JOCKEY_PRESETS, COAT_PRESETS, STRIDE_LEN)
from lib.chars import draw_mizuki_riding
from lib.env import (draw_race_side_bg, draw_race_side_fg, dust_kick, speed_lines_radial, bokeh)
from lib.hud import draw_prob_panel, prob_curve, history_at, draw_brackets
from lib.lipsync import mouth

POST = dict(bloom=0.4, grain=0.35, vignette=0.5, aberration=0.0)

HZ = 2.34                      # strides / s (matches hoofbeats in the audio)
HORIZON, TRACK_Y = 520, 760
Y0_DIRT = HORIZON + 0.56 * (TRACK_Y - HORIZON) + 6      # where the dirt starts (env layout)
S_REF = 0.66                   # horse scale at track_y (p = 1)

T_A, T_B, T_C1, T_C2, T_D, T_E = 20.0, 24.5, 27.0, 28.1, 29.6, 30.8
GO = 29.6

CYAN = PAL["neon_cyan"]


def pdepth(y, horizon=HORIZON, track_y=TRACK_Y):
    """Dirt band parallax factor at screen row y (same formula as env.draw_race_side_bg)."""
    y0 = horizon + 0.56 * (track_y - horizon) + 6
    return 0.84 + 0.16 * (y - y0) / max(1.0, track_y - y0)


# ------------------------------------------------------------------ cast
def _j(i, **kw):
    d = dict(JOCKEY_PRESETS[i % len(JOCKEY_PRESETS)]); d.setdefault("crouch", 1.0); d.update(kw); return d

C = COAT_PRESETS
TEAL = dict(silk=(0.12, 0.62, 0.66), accent=(0.97, 0.97, 0.97), cap=(0.97, 0.97, 0.97), cap_star=False, crouch=1.0)
# (world X0 relative to ハルカゼ, lane y, number, jockey, coat, hz jitter, phase offset)
RIVALS = [
    (2560, 742, 3, _j(0, push=0.4), C["bay"], 0.012, 0.13),
    (2240, 812, 7, _j(1, push=0.3), C["dark_bay"], 0.004, 0.61),
    (1980, 718, 1, _j(2, push=0.2), C["grey"], 0.008, 0.37),
    (1720, 858, 11, _j(3, push=0.5), C["black"], 0.000, 0.84),
    (1430, 768, 5, _j(4, push=0.3), C["liver"], -0.004, 0.22),
    (1150, 830, 9, _j(5, push=0.4), C["bay"], 0.002, 0.52),
    (900, 728, 2, _j(6, push=0.2), C["dark_bay"], -0.006, 0.05),
    (640, 880, 12, _j(7, push=0.5), C["grey"], -0.002, 0.71),
    (380, 790, 6, dict(TEAL, push=0.3), C["black"], -0.008, 0.44),
]


def _hz_rival(k, gt):
    return HZ * (1 + RIVALS[k][5]) - 0.10 * smoothstep(30.0, 32.5, gt)


def _int_rival(k, gt):
    """Strides elapsed since 20.0 for rival k (analytic enough: linear + tiring integral)."""
    a = HZ * (1 + RIVALS[k][5]) * (gt - 20.0)
    return a - 0.10 * _ss_int(30.0, 32.5, gt)


def _ss_int(a, b, x):
    """Integral of smoothstep(a,b,s) ds from -inf to x."""
    if x <= a:
        return 0.0
    L = b - a
    if x >= b:
        return L * 0.5 + (x - b)
    u = (x - a) / L
    return L * (u ** 3 - 0.5 * u ** 4)


KICK_A, KICK_B, KICK_ADD = 29.55, 30.9, 0.95


def hero_hz(gt):
    return HZ + KICK_ADD * smoothstep(KICK_A, KICK_B, gt) + 0.04 * smoothstep(27.0, 29.0, gt)


def hero_strides(gt):
    return HZ * (gt - 20.0) + KICK_ADD * _ss_int(KICK_A, KICK_B, gt) + 0.04 * _ss_int(27.0, 29.0, gt)


def hero_lane(gt):
    return lerp(792, 700, smoothstep(28.0, 29.9, gt))


def world_state(gt):
    """List of horse dicts in world units (X: screen px at scale 1 per unit s_ref)."""
    out = []
    for k, (x0, y, num, jk, coat, jit, ph0) in enumerate(RIVALS):
        s = _int_rival(k, gt)
        far = clamp((830 - y) / 130.0)
        yy = y + 4 * math.sin(gt * 0.7 + k) + (34 + 30 * far) * smoothstep(28.6, 30.8, gt)   # pack hugs the rail
        out.append(dict(X=x0 + STRIDE_LEN * s, y=yy, num=num, jockey=jk, coat=coat,
                        phase=(ph0 + s) % 1.0, hero=False, k=k))
    s = hero_strides(gt)
    kick = smoothstep(GO, 31.2, gt)
    hj = dict(HERO_JOCKEY); hj["push"] = 0.15 + 0.85 * kick; hj["whip"] = False
    out.append(dict(X=STRIDE_LEN * s, y=hero_lane(gt), num=14, jockey=hj, coat=C["chestnut"],
                    phase=(0.30 + s) % 1.0, hero=True, k=99, kick=kick))
    return out


def cam_ref(gt):
    """Pack reference world X (moves with the nominal pack speed)."""
    return STRIDE_LEN * HZ * (gt - 20.0)


# ------------------------------------------------------------------ pack renderer
def draw_pack(ctx, gt, camX, *, s_ref=S_REF, cx=W / 2, blur=0.0, lean=0.0, mb_rival=0.0, dust=0.7,
              hero_boost=0.0, only_screen=True):
    """Draw every horse (far lanes first). Returns screen info about the hero."""
    hs = sorted(world_state(gt), key=lambda h: h["y"])
    hero_info = None
    for h in hs:
        y = h["y"]
        p = pdepth(y)
        sc = s_ref * p
        x = cx + (h["X"] - camX) * s_ref * p
        if only_screen and (x < -500 * sc - 50 or x > W + 500 * sc + 50):
            continue
        far = clamp((830 - y) / 130.0)
        if h["hero"]:
            kick = h["kick"]
            P = draw_horse(ctx, x, y, sc, h["phase"], coat=h["coat"]["coat"], mane=h["coat"]["mane"],
                           jockey=h["jockey"], t=gt, number=14, stride=1.0 + 0.35 * kick,
                           motion_blur=clamp(0.15 * blur + 0.85 * kick * hero_boost), mane_wind=1.0 + 0.6 * kick,
                           lean=lean, shade=0.0, rim_strength=1.0 + 0.3 * kick, ground_shadow=0.4)
            hero_info = dict(x=x, y=y, sc=sc, P=P)
        else:
            P = draw_horse(ctx, x, y, sc, h["phase"], coat=h["coat"]["coat"], mane=h["coat"]["mane"],
                           blaze=(h["k"] % 3 == 0), socks=(h["k"] % 2 == 0, False, h["k"] % 3 == 1, False),
                           jockey=h["jockey"], t=gt + h["k"] * 1.7, number=h["num"], stride=1.0,
                           motion_blur=mb_rival, lean=lean, shade=0.12 + 0.34 * far, rim_strength=0.8 * (1 - far * 0.4),
                           ground_shadow=0.3)
        if dust > 0:
            # dirt kicked back from grounded hind hooves
            for i in (2, 3):
                leg = P["legs"][i]
                if leg.get("ground"):
                    hx = x + leg["cr"][0] * sc
                    st = dust * sc * (1.4 if h["hero"] else 1.0) * (0.55 + 0.45 * (1 - far))
                    if h["hero"]:
                        st *= 1 + 1.2 * h["kick"] * hero_boost
                    dust_kick(ctx, gt, hx, y, strength=clamp(st, 0, 1.6), seed=h["k"] * 3 + i,
                              color=(0.74, 0.6, 0.48) if far < 0.5 else (0.55, 0.45, 0.4))
    return hero_info


def hero_screen(gt, camX, s_ref=S_REF, cx=W / 2):
    y = hero_lane(gt); p = pdepth(y)
    return cx + (STRIDE_LEN * hero_strides(gt) - camX) * s_ref * p, y, s_ref * p


def draw_tracking(ctx, gt, camX, *, s_ref=S_REF, blur=0.0, lean=0.0, mb_rival=0.0, hero_boost=0.0, fg_blur=None,
                  flash=0.0, dust=0.7):
    # camera px for the env layers: dirt at track_y moves 1:1 with the horses there
    cam_px = camX * s_ref
    draw_race_side_bg(ctx, gt, cam_px, horizon_y=HORIZON, track_y=TRACK_Y, crowd=1.0, flash=flash, blur=blur)
    info = draw_pack(ctx, gt, camX, s_ref=s_ref, blur=blur, lean=lean, mb_rival=mb_rival, hero_boost=hero_boost,
                     dust=dust)
    draw_race_side_fg(ctx, gt, cam_px, track_y=TRACK_Y, blur=blur if fg_blur is None else fg_blur, clods=0.8)
    return info


def hud_panel(ctx, gt, alpha=0.85):
    draw_prob_panel(ctx, gt, prob_curve(gt), x=1480, y=90, alpha=alpha, history=history_at(gt))


def hud_lock(ctx, t_lock, x, y, sc, color=CYAN, alpha=1.0, label="#14 ハルカゼ", sub="POS 14/14"):
    if t_lock <= 0:
        return
    w, h = 640 * sc, 520 * sc
    bx, by = x - w * 0.42, y - h * 1.02
    draw_brackets(ctx, bx, by, w, h, t_lock, color, alpha=alpha, size=24, width=2.0)
    a = alpha * clamp((t_lock - 0.25) / 0.2)
    if a > 0:
        text(ctx, label, bx, by - 34, 26, font=FONT_SANS, color=color, alpha=a, align="left",
             outline=5, outline_color=(0.01, 0.03, 0.06), outline_alpha=0.7)
        text(ctx, sub, bx, by - 8, 20, font="DejaVu Sans Mono", color=(0.92, 0.98, 1.0), alpha=a * 0.9, align="left",
             outline=4, outline_color=(0.01, 0.03, 0.06), outline_alpha=0.7)


def blinkv(gt, times, d=0.14):
    b = 0.0
    for tb in times:
        u = (gt - tb) / d
        if 0 <= u <= 1:
            b = max(b, math.sin(u * math.pi))
    return b


# ------------------------------------------------------------------ pixel FX on the target surface
def _arr(ctx):
    s = ctx.get_target(); s.flush()
    return s, np.ndarray((s.get_height(), s.get_width(), 4), np.uint8, s.get_data())


def impact_frame(ctx, mode):
    """Anime impact frame: posterised 2-tone. mode 0 = inverted (black figure glow on white), 1 = black/red/white."""
    s, a = _arr(ctx)
    f = a[..., :3].astype(np.float32)
    lum = (f[..., 0] * 0.11 + f[..., 1] * 0.59 + f[..., 2] * 0.30) / 255.0
    red = (f[..., 2] > 140) & (f[..., 2] > f[..., 1] * 1.8)
    out = np.empty_like(a[..., :3])
    if mode == 0:
        v = np.where(lum > 0.42, 0, 255).astype(np.uint8)
        out[..., 0] = v; out[..., 1] = v; out[..., 2] = v
        out[red] = (40, 20, 230)
    else:
        v = np.where(lum > 0.55, 255, 0).astype(np.uint8)
        out[..., 0] = v; out[..., 1] = v; out[..., 2] = v
        mid = (lum > 0.22) & (lum <= 0.55)
        out[mid] = (30, 20, 200)
    a[..., :3] = out
    s.mark_dirty()


def hsmear(ctx, amount, rows=None):
    """Cheap horizontal motion smear of the whole frame (average of shifted copies)."""
    if amount <= 0.01:
        return
    s, a = _arr(ctx)
    f = a[..., :3].astype(np.uint16)
    acc = f.copy()
    n = 4
    for i in range(1, n):
        k = int(amount * 26 * i)
        sh = np.empty_like(f); sh[:, k:] = f[:, :-k] if k else f; sh[:, :k] = f[:, :1] if k else 0
        acc += sh
    a[..., :3] = (acc // n).astype(np.uint8)
    s.mark_dirty()


# ------------------------------------------------------------------ shots
def shot_A(ctx, t, gt):
    """Wide tracking: leaders -> reveal ハルカゼ at the back."""
    u = gt - T_A
    # focus world X on screen centre: leaders (2000) -> back of the pack (720)
    k = ease_in_out(smoothstep(0.1, 2.7, u))
    focus = lerp(2050, 800, k) + 40 * math.sin(u * 0.9)
    camX = cam_ref(gt) + focus
    zoom = 1.08 + 0.07 * smoothstep(1.2, 4.5, u)
    hx, hy, hsc = hero_screen(gt, camX)
    ctx.save()
    dx, dy = shake(gt, 3.0, 9, 4)
    zx, zy = lerp(W / 2, hx, 0.6), 820
    ctx.translate(zx + dx, zy + dy); ctx.scale(zoom, zoom); ctx.translate(-zx, -zy)
    info = draw_tracking(ctx, gt, camX, blur=0.12)
    ctx.restore()
    # HUD lock onto the hero after the camera arrives
    if info:
        sx = zx + (info["x"] - zx) * zoom + dx; sy = zy + (info["y"] - zy) * zoom + dy
        hud_lock(ctx, gt - 21.3, sx, sy, info["sc"] * zoom, alpha=0.9 * clamp((T_B - 0.05 - gt) / 0.2))
    hud_panel(ctx, gt)


def shot_B(ctx, t, gt):
    """美月 close-up, calm focus. Telephoto: blurred stands whipping past behind her."""
    u = gt - T_B
    ctx.save()
    # telephoto background: scaled-up heavily blurred side background, low camera
    ctx.save()
    ctx.translate(W / 2, H / 2); ctx.scale(1.9, 1.9); ctx.translate(-W / 2, -H / 2 - 160)
    draw_race_side_bg(ctx, gt, 2600 * u + 4000, horizon_y=HORIZON, track_y=TRACK_Y, crowd=1.0, blur=0.9)
    ctx.restore()
    # cool night grade + depth haze
    ctx.set_source_rgba(0.05, 0.06, 0.2, 0.35); ctx.paint()
    bokeh(ctx, gt * 3.0, n=26, colors=[(1, 0.85, 0.6), (0.8, 0.9, 1.0), (1, 0.6, 0.7)], seed=41, alpha=0.45,
          area=(0, 0, W, 620), size=(30, 110), drift=(-700, 0))
    # ハルカゼ's neck and mane rising in front-right, under her hands
    ph = (0.30 + hero_strides(gt)) % 1.0
    bob = math.sin(gt * TAU * 2.2) * 6
    ctx.save()
    draw_horse(ctx, 1000, 1950 + bob, 2.9, ph, coat=C["chestnut"]["coat"], mane=C["chestnut"]["mane"], jockey=None,
               t=gt, mane_wind=1.6, rim_strength=1.1, ground_shadow=0.0, line_width=2.4)
    ctx.restore()
    # 美月
    sway = 10 * math.sin(u * 1.3)
    push = 1.0 + 0.04 * smoothstep(0.0, 2.5, u)
    ctx.save()
    ctx.translate(1120, 430); ctx.scale(push, push); ctx.translate(-1120, -430)
    draw_mizuki_riding(ctx, 1120 + sway, 420, 1.22, expr="whisper", mouth=mouth("MIZUKI", gt),
                       blink=blinkv(gt, (24.9, 26.75)), t=gt, wind=1.0, goggles="down",
                       look=(0.45, 0.02), dirt=0.6, rim_strength=1.1)
    ctx.restore()
    # wind streaks in the foreground
    horiz_speed_lines(ctx, gt, 60, H - 60, n=16, speed=5200, color=(1, 1, 1), alpha=0.22, seed=7, length=(300, 900))
    ctx.restore()


def shot_C1(ctx, t, gt):
    """Extreme low angle hooves."""
    u = gt - T_C1
    ctx.save()
    ang = math.radians(-4.0 - 1.5 * u)
    dx, dy = shake(gt, 7.0, 14, 8)
    ctx.translate(W / 2 + dx, H / 2 + dy); ctx.rotate(ang); ctx.scale(1.08, 1.08); ctx.translate(-W / 2, -H / 2)
    hz_y, tr_y = 800, 880           # camera right on the ground: low horizon
    sc = 2.35
    gy = 1030
    p = pdepth(gy, hz_y, tr_y)
    cam_px = STRIDE_LEN * sc * hero_strides(gt) / p      # no-slip scroll at the hooves' row
    draw_race_side_bg(ctx, gt, cam_px, horizon_y=hz_y, track_y=tr_y, crowd=1.0, blur=0.75)
    # a rival galloping just behind (farther, darker)
    ph2 = (0.71 + _int_rival(7, gt)) % 1.0
    draw_horse(ctx, 1500 - 120 * u, 905, 1.25, ph2, coat=C["dark_bay"]["coat"], mane=C["dark_bay"]["mane"],
               jockey=_j(7, push=0.5), t=gt, number=12, shade=0.45, motion_blur=0.3, ground_shadow=0.3)
    dust_kick(ctx, gt, 1300 - 120 * u, 905, strength=1.0, seed=31)
    # ハルカゼ: legs fill the frame, body cropped at the top
    ph = (0.30 + hero_strides(gt)) % 1.0
    P = draw_horse(ctx, 860 + 40 * math.sin(u * 2), gy, sc, ph, coat=C["chestnut"]["coat"], mane=C["chestnut"]["mane"],
                   jockey=HERO_JOCKEY, t=gt, number=14, motion_blur=0.35, ground_shadow=0.5, rim_strength=1.2)
    for i in range(4):
        leg = P["legs"][i]
        if leg.get("ground"):
            dust_kick(ctx, gt, 860 + leg["cr"][0] * sc, gy, strength=1.5, seed=50 + i, speed=1.3)
    # flying clods towards the lens
    rr = rng(int(gt * FPS))
    for i in range(10):
        x = rr.uniform(-100, W); y = rr.uniform(700, H + 50); r_ = rr.uniform(6, 26)
        ctx.set_source_rgba(0.2, 0.14, 0.11, rr.uniform(0.5, 0.9))
        ctx.save(); ctx.translate(x, y); ctx.scale(2.6, 1); ctx.arc(0, 0, r_, 0, TAU); ctx.restore(); ctx.fill()
    ctx.restore()
    horiz_speed_lines(ctx, gt, 0, H, n=22, speed=7000, color=(1, 0.95, 0.85), alpha=0.25, seed=9, length=(400, 1300))


def shot_C2(ctx, t, gt):
    """Pack entering the 4th corner: tilted frame, horses leaning, ハルカゼ swings wide."""
    u = gt - T_C2
    camX = cam_ref(gt) + lerp(1000, 900, u / 1.5)
    ang = math.radians(-2.0 - 4.0 * ease_in_out(u / 1.5))
    zoom = 1.12 + 0.05 * u
    ctx.save()
    dx, dy = shake(gt, 4.0, 11, 12)
    ctx.translate(W / 2 + dx, 640 + dy); ctx.rotate(ang); ctx.scale(zoom, zoom); ctx.translate(-W / 2, -640)
    info = draw_tracking(ctx, gt, camX, blur=0.3, lean=0.55, mb_rival=0.1)
    ctx.restore()
    if info:
        m = cairo.Matrix(); m.translate(W / 2 + dx, 640 + dy); m.rotate(ang); m.scale(zoom, zoom); m.translate(-W / 2, -640)
        sx, sy = m.transform_point(info["x"], info["y"])
        hud_lock(ctx, gt - T_C2 + 0.2, sx, sy, info["sc"] * zoom, alpha=0.85, sub="4TH CORNER  POS 14/14")
    # corner caption
    a = clamp(u / 0.2) * clamp((1.5 - u) / 0.2)
    text(ctx, "4コーナー", 110, 170, 54, font=FONT_IMPACT, color=(1, 1, 1), alpha=a * 0.9, align="left",
         outline=8, outline_color=(0.05, 0.02, 0.1), outline_alpha=0.8)
    hud_panel(ctx, gt)


def shot_D(ctx, t, gt):
    """IMPACT: 美月 shouting."""
    u = gt - T_D
    fi = int(round(u * FPS))
    # background: hot radial field
    cx, cy = 1040, 430
    g = cairo.RadialGradient(cx, cy, 40, cx, cy, 1300)
    g.add_color_stop_rgb(0, 1.0, 0.92, 0.75)
    g.add_color_stop_rgb(0.25, 0.95, 0.42, 0.25)
    g.add_color_stop_rgb(0.6, 0.45, 0.06, 0.16)
    g.add_color_stop_rgb(1, 0.10, 0.02, 0.08)
    ctx.set_source(g); ctx.paint()
    speed_lines(ctx, gt, cx, cy, n=150, inner=460, outer=1700, color=(1, 1, 1), alpha=0.75, seed=13)
    zoom = 1.0 + 0.22 * (1 - ease_out_cubic(u / 0.35))
    ctx.save()
    dx, dy = shake(gt, 14.0 * (1 - 0.6 * smoothstep(0, 1.1, u)), 22, 21)
    ctx.translate(cx + dx, cy + dy); ctx.scale(zoom, zoom); ctx.translate(-cx, -cy)
    draw_mizuki_riding(ctx, 1040, 440, 1.38, expr="shout", mouth=max(mouth("MIZUKI", gt), 0.25 if u < 1.0 else 0),
                       blink=0.0, t=gt, wind=1.6, goggles="down", look=(0.6, 0.0), dirt=1.0, sweat=0.8,
                       light_flash=0.6 * (1 - smoothstep(0, 0.4, u)), shake=0.4, rim_strength=1.3)
    ctx.restore()
    # foreground focus lines (thin, white) closer in
    speed_lines(ctx, gt + 0.5, cx, cy, n=60, inner=700, outer=1700, color=(1, 1, 1), alpha=0.5, seed=17)
    # impact frames on the hit
    if fi == 0:
        impact_frame(ctx, 0)
    elif fi == 1:
        impact_frame(ctx, 1)
    elif fi == 2:
        ctx.set_source_rgba(1, 1, 1, 0.5); ctx.paint()


def shot_E(ctx, t, gt):
    """The kick: camera tracks ハルカゼ as she sweeps past the pack on the outside."""
    u = gt - T_E
    D = 33.0 - T_E
    y = hero_lane(gt); p = pdepth(y)
    target = lerp(430, 1010, ease_in_out(u / D))           # hero screen x (she surges forward in frame)
    camX = STRIDE_LEN * hero_strides(gt) - (target - W / 2) / (S_REF * p)
    zoom = 1.22 + 0.08 * ease_in_out(u / D)
    blur = 0.55 + 0.35 * smoothstep(0, 0.8, u)
    ctx.save()
    amp = 9.0 + 6 * math.exp(-u * 3)
    dx, dy = shake(gt, amp, 16, 31)
    dy += math.sin(gt * TAU * hero_hz(gt)) * 4
    ctx.translate(target + dx, 700 + dy); ctx.rotate(math.radians(-1.2)); ctx.scale(zoom, zoom); ctx.translate(-target, -700)
    info = draw_tracking(ctx, gt, camX, blur=blur, mb_rival=0.25, hero_boost=1.0, fg_blur=1.0, flash=0.4, dust=0.85)
    ctx.restore()
    # burst of dust at the moment of the kick
    ki = clamp(1 - u / 0.6)
    if ki > 0 and info:
        m = cairo.Matrix(); m.translate(target + dx, 700 + dy); m.rotate(math.radians(-1.2)); m.scale(zoom, zoom)
        m.translate(-target, -700)
        sx, sy = m.transform_point(info["x"], info["y"])
        dust_kick(ctx, gt, sx - 120, sy, strength=1.6 * ki, seed=77, speed=1.6)
        radial_glow(ctx, sx, sy - 180, 420, (1, 0.9, 0.7), 0.35 * ki)
    # speed smear over everything but a little: sells velocity
    horiz_speed_lines(ctx, gt, 40, H - 40, n=28, speed=8000, color=(1, 0.97, 0.9), alpha=0.28, seed=23, length=(500, 1500))
    if info:
        m = cairo.Matrix(); m.translate(target + dx, 700 + dy); m.rotate(math.radians(-1.2)); m.scale(zoom, zoom)
        m.translate(-target, -700)
        sx, sy = m.transform_point(info["x"], info["y"])
        # overtake counter
        pos = 1 + sum(1 for h in world_state(gt) if not h["hero"] and h["X"] > STRIDE_LEN * hero_strides(gt))
        hud_lock(ctx, gt - T_E + 0.5, sx, sy, info["sc"] * zoom, color=mix_color(CYAN, PAL["neon_pink"], 0.4),
                 alpha=0.9, sub="POS %d/14  ▲ ACCEL" % pos)
    # panel pulses as it starts climbing
    hud_panel(ctx, gt, alpha=0.9)
    pul = 0.5 + 0.5 * math.sin(gt * 14)
    ctx.save(); ctx.set_source_rgba(*PAL["neon_pink"], 0.25 * pul)
    ctx.set_line_width(3); ctx.rectangle(1474, 84, 392, 262); ctx.stroke(); ctx.restore()


def draw(ctx, t, dur, gt):
    ctx.set_source_rgb(0.02, 0.02, 0.06); ctx.paint()
    if gt < T_B:
        shot_A(ctx, t, gt)
    elif gt < T_C1:
        shot_B(ctx, t, gt)
    elif gt < T_C2:
        shot_C1(ctx, t, gt)
    elif gt < T_D:
        shot_C2(ctx, t, gt)
    elif gt < T_E:
        shot_D(ctx, t, gt)
    else:
        shot_E(ctx, t, gt)
