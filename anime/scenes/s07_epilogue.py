"""s07 — Epilogue (global 50.0-60.0).

50.0-54.6  A: warm close two-shot. 美月 (cap off, goggles up) presses her cheek to ハルカゼ's face,
           eyes closed; horse eyes half-closed, ears soft. AI update panel boots (one-shot glitch ~50.8)
           and speaks L12, drifting cyan -> gold.
54.6-57.4  B: cut to 美月 turning to camera, teasing smile, L13 lip-synced; slow push-in; 源さん small in
           the soft background with proud tears; blink/wink at the end.
57.4-60.0  C: title card over the darkened scene (hud.draw_title_card fades to black by 60.0).
"""
import numpy as np
from PIL import Image, ImageFilter
from lib.common import *
from lib import env, hud
from lib.horse import draw_horse_head
from lib.chars import draw_mizuki, draw_gen
from lib.lipsync import mouth

POST = dict(bloom=0.55, grain=0.28, vignette=0.5, aberration=0.0)

WARM = (1.0, 0.80, 0.52)
ROSE = (1.0, 0.62, 0.66)
T_CUT = 4.6
T_TITLE = 7.4

# ------------------------------------------------------------------ cached defocused background
_BG = {}


def _surface_from_rgb(arr):
    h, w, _ = arr.shape
    a = np.empty((h, w, 4), np.uint8)
    a[..., 0] = arr[..., 2]; a[..., 1] = arr[..., 1]; a[..., 2] = arr[..., 0]; a[..., 3] = 255
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    buf = np.ndarray((h, s.get_stride() // 4, 4), np.uint8, s.get_data())
    buf[:, :w] = a
    s.mark_dirty()
    return s


def _bg(kind):
    """Floodlit racecourse at night, rendered once, heavily defocused, with a warm grade."""
    if kind in _BG:
        return _BG[kind]
    M = 160  # margin for camera drift
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W + 2 * M, H + 2 * M)
    c = cairo.Context(s)
    c.translate(M, M)
    if kind == "A":
        env.draw_race_side_bg(c, 3.0, 5200.0, horizon_y=560, track_y=820, crowd=1.0, flash=0.0, blur=0.0)
    else:
        env.draw_race_side_bg(c, 3.0, 6100.0, horizon_y=600, track_y=860, crowd=1.0, flash=0.0, blur=0.0)
    s.flush()
    a = np.ndarray((H + 2 * M, s.get_stride() // 4, 4), np.uint8, s.get_data())[:, :W + 2 * M]
    rgb = a[..., [2, 1, 0]].copy()
    im = Image.fromarray(rgb)
    sm = im.resize((im.width // 4, im.height // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(5 if kind == "A" else 4))
    im = sm.resize(im.size, Image.BICUBIC)
    f = np.asarray(im, np.float32) / 255.0
    # warm grade: lift shadows toward plum, push highlights to amber
    lum = f.mean(axis=2, keepdims=True)
    f = f * np.array([1.05, 0.92, 0.82], np.float32) + (1 - lum) * np.array([0.05, 0.02, 0.06], np.float32)
    f = np.clip(f * 0.82, 0, 1)
    _BG[kind] = (_surface_from_rgb((f * 255).astype(np.uint8)), M)
    return _BG[kind]


def _paint_bg(ctx, kind, dx, dy, zoom=1.0):
    s, M = _bg(kind)
    ctx.save()
    ctx.translate(W / 2 + dx, H / 2 + dy); ctx.scale(zoom, zoom); ctx.translate(-W / 2 - M, -H / 2 - M)
    ctx.set_source_surface(s, 0, 0); ctx.paint()
    ctx.restore()


def _floodlight_bokeh(ctx, t, seed, area, n, size, alpha):
    env.bokeh(ctx, t, n=n, seed=seed, alpha=alpha, area=area, size=size, drift=(6, -8),
              colors=[(1.0, 0.80, 0.50), (1.0, 0.90, 0.72), (1.0, 0.62, 0.62), (0.95, 0.72, 0.45), (0.8, 0.85, 1.0)])


def _warm_light(ctx, x, y, r, a):
    ctx.save(); ctx.set_operator(cairo.OPERATOR_ADD)
    radial_glow(ctx, x, y, r, (1.0, 0.72, 0.42), a)
    ctx.restore()


# ------------------------------------------------------------------ shot A: the embrace
def _shot_a(ctx, t, gt):
    k = clamp(t / T_CUT)
    push = 1.0 + 0.06 * ease_in_out(k)
    drift = lerp(-30, 20, ease_in_out(k))
    # background (moves less = parallax)
    _paint_bg(ctx, "A", drift * 0.35, -10, 1.0 + 0.02 * k)
    _floodlight_bokeh(ctx, t, 3, (-100, -60, W + 200, 760), 26, (40, 130), 0.55)
    # warm key glow from floodlight upper-left behind them
    _warm_light(ctx, 520, 160, 900, 0.22)

    ctx.save()
    ctx.translate(W / 2, H / 2); ctx.scale(push, push); ctx.translate(-W / 2 + drift, -H / 2 + 20)
    # ハルカゼ head from the left, facing right, nuzzling down toward her
    breath = math.sin(t * TAU / 3.6)
    blinkh = 0.62 + 0.08 * math.sin(t * 0.9)
    if 2.9 < t < 3.25:
        blinkh = 1.0
    draw_horse_head(ctx, 560, H + 110, 1.7, facing=1, blink=blinkh, ear=-0.55, nostril=0.25 + 0.2 * max(0, breath),
                    look=(0.3, 0.25), t=t + 2.0, nuzzle=0.85, light=WARM, rim_strength=1.0, shade=0.05)
    # 美月: 3q_left, hugging his face, cheek pressed in
    draw_mizuki(ctx, 1030, H + 385, 1.2, view="3q_left", expr="tender_eyes_closed", arm="hug", t=t + 1.0,
                helmet=False, goggles="up", light=WARM, light_dir=-1, rim=(1.0, 0.82, 0.55), rim_strength=1.0,
                blush=0.7, tears=0.35, head_tilt=0.05, hair_wind=0.15)
    ctx.restore()

    # atmosphere in front: soft light particles
    env.confetti_light(ctx, t + 40, n=38, seed=11, area=(0, 0, W, H), rise=30, size=1.1, alpha=0.7)
    _floodlight_bokeh(ctx, t * 0.7, 21, (-100, 700, W + 200, 500), 5, (120, 200), 0.18)

    # AI update panel (right, away from faces)
    ta = gt - 50.0
    hud.draw_update_panel(ctx, ta, cx=1540, cy=300)
    # one-shot boot glitch just after the dissolve
    if 0.80 <= ta < 0.93:
        hud.glitch_frame(ctx, 0.35 if ta < 0.86 else 0.15, seed=int(gt * FPS))


# ------------------------------------------------------------------ shot B: to camera
def _shot_b(ctx, t, gt):
    tb = t - T_CUT
    kp = ease_out_cubic(clamp(tb / 2.6)) * 0.6 + 0.4 * clamp(tb / 5.4)
    push = 1.0 + 0.07 * kp
    _paint_bg(ctx, "B", -20 * kp, -8 * kp, 1.0 + 0.02 * kp)
    _floodlight_bokeh(ctx, t, 5, (-100, -60, W + 200, 800), 28, (40, 140), 0.55)
    _warm_light(ctx, 1500, 140, 900, 0.20)

    # 源さん, small and soft in the background (right), proud tears
    ctx.save()
    ctx.translate(W / 2, H / 2); ctx.scale(1 + 0.03 * kp, 1 + 0.03 * kp); ctx.translate(-W / 2, -H / 2)
    ctx.push_group()
    draw_gen(ctx, 1520, 1010, 0.42, view="3q_left", expr="proud_tears", arms="down", t=t, light=WARM, light_dir=1,
             rim=(1.0, 0.85, 0.6), rim_strength=0.9)
    ctx.pop_group_to_source(); ctx.paint_with_alpha(0.82)
    ctx.restore()
    # haze over him to push him back
    ctx.save(); ctx.set_source_rgba(0.35, 0.22, 0.26, 0.18); ctx.rectangle(1300, 560, 460, 520); ctx.fill(); ctx.restore()

    ctx.save()
    ctx.translate(W / 2, H * 0.42); ctx.scale(push, push); ctx.translate(-W / 2, -H * 0.42)
    # ハルカゼ muzzle, soft, entering frame left (foreground-ish)
    draw_horse_head(ctx, 90, H + 360, 1.5, facing=1, blink=0.55, ear=-0.3, t=t + 5, nuzzle=0.6, light=WARM,
                    rim_strength=0.9, shade=0.25)
    # turn: 3q_left -> front happens on the cut; small head settle
    settle = (1 - ease_out_back(clamp(tb / 0.45))) * 0.12
    m = mouth("MIZUKI", gt)
    blink = 0.0
    tl = gt - 57.25
    if 0.0 < tl < 0.35:  # end-of-line wink-ish blink
        blink = math.sin(clamp(tl / 0.35) * math.pi)
    elif 1.2 < tb < 1.32:
        blink = 1.0
    draw_mizuki(ctx, 960, H + 520, 1.28, view="front", expr="teasing_smile", mouth=m * 0.85, blink=blink,
                look=(0, 0), t=t + 3, helmet=False, goggles="up", light=WARM, light_dir=1, rim=(1.0, 0.82, 0.55),
                rim_strength=1.0, blush=0.6, head_tilt=-settle, hair_wind=0.12)
    ctx.restore()
    env.confetti_light(ctx, t + 80, n=40, seed=13, area=(0, 0, W, H), rise=30, size=1.1, alpha=0.7)


# ------------------------------------------------------------------ contract
def draw(ctx, t, dur, gt):
    ctx.set_source_rgb(0.03, 0.02, 0.05); ctx.paint()
    if t < T_CUT:
        _shot_a(ctx, t, gt)
    else:
        _shot_b(ctx, t, gt)
    # warm grade overlay (soft light from floodlights)
    ctx.save(); ctx.set_operator(cairo.OPERATOR_SOFT_LIGHT)
    g = cairo.LinearGradient(0, 0, 0, H)
    g.add_color_stop_rgba(0, 1.0, 0.75, 0.45, 0.35); g.add_color_stop_rgba(1, 0.35, 0.15, 0.35, 0.35)
    ctx.set_source(g); ctx.paint(); ctx.restore()
    if t >= T_TITLE - 0.05:
        hud.draw_title_card(ctx, gt - 57.4)
