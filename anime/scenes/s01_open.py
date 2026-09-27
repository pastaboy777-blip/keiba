"""s01 0-6s: KEIBA-AI boots over night Tokyo; camera tilts down onto 大井競馬場."""
from lib.common import *
from lib.env import draw_racecourse_establishing
from lib.hud import draw_boot, draw_scanlines

POST = dict(bloom=0.45, grain=0.3, vignette=0.5)

def draw(ctx, t, dur, gt):
    cam = ease_in_out(clamp(t / 6.0))
    draw_racecourse_establishing(ctx, t, cam=cam, horses=True, race_s=t)
    # dim the world while the HUD is dense, so text reads
    dim = 0.35 * smoothstep(0.3, 1.2, t) * (1 - 0.5 * smoothstep(4.8, 6.0, t))
    ctx.set_source_rgba(0.01, 0.02, 0.06, dim); ctx.paint()
    draw_boot(ctx, t, target=(1300, 700))
    draw_scanlines(ctx, alpha=0.06)
    # open from black
    if t < 0.5:
        ctx.set_source_rgba(0, 0, 0, 1 - t / 0.5); ctx.paint()
