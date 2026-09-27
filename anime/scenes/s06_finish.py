"""PLACEHOLDER — to be replaced by the scene agent."""
from lib.common import *

def draw(ctx, t, dur, gt):
    vgradient(ctx, 0, 0, W, H, [(0, PAL["night_top"]), (1, PAL["night_low"])])
    text(ctx, "s06_finish  t=%.2f" % t, W / 2, H / 2, 60)
