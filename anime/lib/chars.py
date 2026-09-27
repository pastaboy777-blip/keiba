"""Character art for 「最後の一完歩」 — 美月 (Mizuki) and 源さん (Gen).

Procedural TV-anime cel style: flat base + one hard shadow tone + rim light + soft blush,
tapered ink lines, layered anime eyes, clumped hair with secondary motion.

Public API (all functions draw into an existing cairo context and restore its state):

  draw_mizuki(ctx, x, y, scale, *, view="3q_left", expr="soft", mouth=0.0, blink=0.0, look=(0,0),
              hair_wind=0.0, t=0.0, helmet=True, goggles="up", arm="down", arm_phase=0.0,
              light=(1,0.8,0.55), light_dir=-1, rim=(1,0.85,0.6), rim_strength=0.7, blush=0.3,
              tears=0.0, head_tilt=0.0, breath=1.0) -> anchors dict
      x,y = bottom-centre of the waist-up bust. scale 1 => head ~300px, bust ~900px tall.
      view: "3q_left" | "3q_right" | "front"
      expr: "soft" "smile" "determined" "shout" "whisper" "tender_eyes_closed" "teasing_smile"
      arm:  "down" | "stroke" (arm_phase 0..1 strokes up/down) | "hug"
      goggles: "up" | "down" | "none"
      light_dir: screen side the key light comes from (-1 left, +1 right). Rim appears on the far side.

  draw_mizuki_riding(ctx, x, y, scale, *, expr="determined", mouth=0.0, blink=0.0, t=0.0, wind=1.0,
              goggles="down", sweat=0.0, rim=(0.75,0.88,1.0), rim_strength=1.0, light_flash=0.0,
              shake=0.0, light=(1,0.93,0.85), dirt=1.0) -> anchors dict
      Racing close-up facing screen-right. x,y = centre of her head. scale 1 => head ~360px.

  draw_mizuki_eyes(ctx, cx, cy, scale, *, t=0.0, open=1.0, look=(0,0), goggles=True,
              reflect_lights=True, focus=0.0, blush=0.25)
      Extreme close-up eye band (front view). scale 1 => ~1920px wide, ~760px tall, centred on cx,cy.

  draw_gen(ctx, x, y, scale, *, view="3q_right", expr="gruff_smile", mouth=0.0, blink=0.0, look=(0,0),
              t=0.0, light=(1,0.8,0.55), light_dir=-1, rim=(1,0.85,0.6), rim_strength=0.6,
              arms="crossed", post=True, tears=0.0) -> anchors dict
      Same bust convention as Mizuki (he is bigger). expr: "gruff_smile" "neutral" "proud_tears" "laugh".
      arms: "crossed" | "down" | "lean" (forearm on a wooden post; post=False to let the scene draw it).

Anchors (returned, in screen coords): "head" (centre of head), "hand" (stroke/hug lead hand),
"hand2", "mouth", "eyes".
"""
import os, sys, math
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cairo
from lib.common import (PAL, TAU, clamp, lerp, smoothstep, noise1, fbm1, rng, mix_color,
                        smooth_path, fill_rgb)

INK = PAL["ink"]
SKIN = PAL["skin"]
SKIN_SH = PAL["skin_shadow"]
SKIN_SH2 = (0.80, 0.52, 0.50)
BLUSH = (1.0, 0.45, 0.50)
HAIR = PAL["mizuki_hair"]
HAIR_B = (0.20, 0.17, 0.27)        # rendered base (lifted so the forms read)
HAIR_S = (0.09, 0.07, 0.13)
HAIR_H = (0.46, 0.42, 0.62)
HAIR_LINE = (0.04, 0.03, 0.07)
SILK = PAL["silk_main"]
SILK_S = (0.70, 0.72, 0.86)
RED = PAL["silk_accent"]
RED_S = (0.58, 0.05, 0.16)
IRIS_M = ((0.26, 0.10, 0.06), (0.66, 0.34, 0.13), (1.00, 0.74, 0.34))   # top, mid, low
IRIS_G = ((0.10, 0.07, 0.06), (0.30, 0.20, 0.14), (0.52, 0.38, 0.26))
LASH = (0.10, 0.05, 0.08)
MOUTH_IN = (0.42, 0.10, 0.14)
TONGUE = (0.93, 0.47, 0.50)
BIG = 20000.0


# ============================================================ geometry helpers
def _cr(p0, p1, p2, p3, s, ten=0.5):
    # Catmull-Rom point (uniform) matching lib.common.smooth_path (tension 0.5 bezier form)
    c1 = (p1[0] + (p2[0] - p0[0]) * ten / 3, p1[1] + (p2[1] - p0[1]) * ten / 3)
    c2 = (p2[0] - (p3[0] - p1[0]) * ten / 3, p2[1] - (p3[1] - p1[1]) * ten / 3)
    u = 1 - s
    return (u * u * u * p1[0] + 3 * u * u * s * c1[0] + 3 * u * s * s * c2[0] + s * s * s * p2[0],
            u * u * u * p1[1] + 3 * u * u * s * c1[1] + 3 * u * s * s * c2[1] + s * s * s * p2[1])


def spline(pts, n=24):
    """Sample an open Catmull-Rom spline through pts into ~n points."""
    if len(pts) < 3:
        (ax, ay), (bx, by) = pts[0], pts[-1]
        return [(lerp(ax, bx, i / (n - 1)), lerp(ay, by, i / (n - 1))) for i in range(n)]
    P = [pts[0]] + list(pts) + [pts[-1]]
    segs = len(pts) - 1
    per = max(2, n // segs)
    out = []
    for i in range(1, len(P) - 2):
        for j in range(per):
            out.append(_cr(P[i - 1], P[i], P[i + 1], P[i + 2], j / per))
    out.append(pts[-1])
    return out


def lerp_pts(A, B, k):
    return [(lerp(a[0], b[0], k), lerp(a[1], b[1], k)) for a, b in zip(A, B)]


def ribbon(pts, wfun):
    """Offset a centreline into (left, right) point lists. wfun(s)->half-width."""
    n = len(pts)
    L, R = [], []
    for i, (x, y) in enumerate(pts):
        a = pts[max(0, i - 1)]; b = pts[min(n - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / d, dx / d
        w = wfun(i / (n - 1))
        L.append((x + nx * w, y + ny * w)); R.append((x - nx * w, y - ny * w))
    return L, R


def path_ribbon(ctx, pts, wfun):
    L, R = ribbon(pts, wfun)
    ctx.new_path()
    ctx.move_to(*L[0])
    for p in L[1:]: ctx.line_to(*p)
    for p in reversed(R): ctx.line_to(*p)
    ctx.close_path()
    return L, R


def taper(ctx, pts, w, col, a=1.0, n=20, prof="mid", w0=0.15, w1=0.0):
    """Fill a tapered brush stroke along spline pts. prof: mid|start|end."""
    S = spline(pts, n) if len(pts) > 2 else spline(pts, max(4, n // 3))
    if prof == "mid":
        f = lambda s: w * max(w0 * (1 - s) + w1 * s, math.sin(math.pi * s) ** 0.7)
    elif prof == "start":   # thick at start
        f = lambda s: w * max(w1, (1 - s) ** 0.8)
    else:                   # thick at end
        f = lambda s: w * max(w0, s ** 0.8)
    path_ribbon(ctx, S, f)
    fill_rgb(ctx, col, a); ctx.fill()


def line(ctx, pts, lw, col, a=1.0, closed=False):
    ctx.new_path(); smooth_path(ctx, pts, closed)
    ctx.set_line_width(lw); fill_rgb(ctx, col, a); ctx.stroke()


def ellipse(ctx, x, y, rx, ry, ang=0.0):
    ctx.save(); ctx.translate(x, y); ctx.rotate(ang); ctx.scale(max(rx, 1e-3), max(ry, 1e-3))
    ctx.arc(0, 0, 1, 0, TAU); ctx.restore()


def shape(ctx, pts, closed=True):
    ctx.new_path(); smooth_path(ctx, pts, closed)
    return ctx.copy_path()


def cel(ctx, path, base, shade=None, sh=(0, 0), rim=None, rimv=(0, 0), rim_a=0.8,
        ink=INK, lw=2.4, ink_a=1.0):
    """Flat base + hard shadow crescent (shape minus shape shifted by sh) + rim crescent + ink."""
    ctx.new_path(); ctx.append_path(path); fill_rgb(ctx, base); ctx.fill()
    if shade is not None or (rim is not None and rim_a > 0.01):
        ctx.save(); ctx.new_path(); ctx.append_path(path); ctx.clip()
        for col, v, a in ((shade, sh, 1.0), (rim, rimv, rim_a)):
            if col is None or a <= 0.01: continue
            ctx.new_path(); ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
            ctx.rectangle(-BIG, -BIG, 2 * BIG, 2 * BIG)
            ctx.save(); ctx.translate(*v); ctx.append_path(path); ctx.restore()
            fill_rgb(ctx, col, a); ctx.fill()
            ctx.set_fill_rule(cairo.FILL_RULE_WINDING)
        ctx.restore()
    if ink is not None and lw > 0:
        ctx.new_path(); ctx.append_path(path); ctx.set_line_width(lw)
        fill_rgb(ctx, ink, ink_a); ctx.stroke()


def clip_path(ctx, path):
    ctx.new_path(); ctx.append_path(path); ctx.clip()


def crescent(ctx, path, v, col, a=1.0):
    """Fill (path minus path shifted by v) — must already be clipped to path."""
    ctx.new_path(); ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    ctx.rectangle(-BIG, -BIG, 2 * BIG, 2 * BIG)
    ctx.save(); ctx.translate(*v); ctx.append_path(path); ctx.restore()
    fill_rgb(ctx, col, a); ctx.fill(); ctx.set_fill_rule(cairo.FILL_RULE_WINDING)


def tint(c, light, k=0.35):
    return tuple(clamp(ci * lerp(1.0, li, k) * (1 + 0.06 * k)) for ci, li in zip(c, light))


class Light:
    """Lighting in local (possibly mirrored) coordinates."""
    def __init__(self, light, ldx, rim, rim_strength):
        self.col = light; self.ldx = ldx; self.rim = rim; self.rs = rim_strength

    def sh(self, d):            # offset toward the key light (shadow ends up on far side, below)
        return (self.ldx * d, -0.55 * d)

    def rv(self, d):
        return (self.ldx * d, -0.25 * d)

    def c(self, col, k=0.35):
        return tint(col, self.col, k)

    def s(self, col, k=0.25):   # shadow tones lean cool/violet
        c = tint(col, self.col, k)
        return (c[0] * 0.97, c[1] * 0.95, min(1, c[2] * 1.04))


def star(ctx, x, y, r, sx=1.0, ang=-math.pi / 2):
    ctx.new_path()
    for i in range(10):
        a = ang + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        px, py = x + math.cos(a) * rr * sx, y + math.sin(a) * rr
        (ctx.move_to if i == 0 else ctx.line_to)(px, py)
    ctx.close_path()


# ============================================================ face feature projection
_XF = [-160, -52, 0, 52, 160]
_X3 = [-128, -24, 32, 74, 124]


def xmap(x, k):
    """Map a front-view head-local x to the 3/4 (facing +x) view, k=0 front .. 1 three-quarter."""
    if k <= 0: return x
    X, Y = _XF, _X3
    if x <= X[0]: v = Y[0] + (x - X[0]) * (Y[1] - Y[0]) / (X[1] - X[0])
    elif x >= X[-1]: v = Y[-1] + (x - X[-1]) * (Y[-1] - Y[-2]) / (X[-1] - X[-2])
    else:
        for i in range(len(X) - 1):
            if X[i] <= x <= X[i + 1]:
                v = Y[i] + (x - X[i]) * (Y[i + 1] - Y[i]) / (X[i + 1] - X[i]); break
    return lerp(x, v, k)


def xscale(x, k):
    return (xmap(x + 1, k) - xmap(x - 1, k)) / 2


def mp(p, k):
    return (xmap(p[0], k), p[1])


# ============================================================ eyes
def _bez(p0, p1, p2, p3, s):
    u = 1 - s
    return (u * u * u * p0[0] + 3 * u * u * s * p1[0] + 3 * u * s * s * p2[0] + s * s * s * p3[0],
            u * u * u * p0[1] + 3 * u * u * s * p1[1] + 3 * u * s * s * p2[1] + s * s * s * p3[1])


def _bez_pts(p0, p1, p2, p3, n):
    return [_bez(p0, p1, p2, p3, i / (n - 1)) for i in range(n)]


def draw_eye(ctx, cx, cy, w, h, o, *, open_=1.0, look=(0, 0), squint=0.0, lid_drop=0.0, tilt=0.0,
             closed_style="relaxed", iris=IRIS_M, hl=-1, detail=0, pupil=1.0, lash=1.0,
             tears=0.0, crease=True, lw=1.0, lower_lash=True, iris_r=1.0, t=0.0, reflect=0.0,
             lash_col=LASH):
    """Anime eye centred at (cx,cy). o=+1: outer corner toward +x, -1 toward -x. w,h: full size.
    hl = screen side of the key light (-1 left, +1 right) -> main highlight side."""
    ctx.save(); ctx.translate(cx, cy); ctx.rotate(tilt * o); ctx.scale(o, 1)
    hl = hl * o                     # into local (outer=+x) space
    lx = look[0] * o
    op = clamp(open_)
    # --- corner + lid control points (outer corner = +x)
    I = (-0.50 * w, 0.02 * h)
    O = (0.54 * w, -0.08 * h)
    up_c1 = (-0.36 * w, -0.44 * h); up_c2 = (0.44 * w, -0.54 * h)
    ld = lid_drop * 0.30 * h
    up_c1 = (up_c1[0], up_c1[1] + ld * 0.8); up_c2 = (up_c2[0], up_c2[1] + ld)
    sq = squint * 0.28 * h
    lo_c1 = (0.44 * w, 0.44 * h - sq * 1.1); lo_c2 = (-0.30 * w, 0.52 * h - sq * 0.8)
    if closed_style == "happy":
        cl_c1 = (-0.30 * w, -0.14 * h); cl_c2 = (0.25 * w, -0.18 * h)
        Ic, Oc = (-0.50 * w, 0.14 * h), (0.52 * w, 0.06 * h)
    else:
        cl_c1 = (-0.30 * w, 0.30 * h); cl_c2 = (0.28 * w, 0.30 * h)
        Ic, Oc = (-0.50 * w, 0.10 * h), (0.52 * w, 0.02 * h)
    if op < 0.12:
        pts = _bez_pts(Ic, cl_c1, cl_c2, Oc, 14)
        pts.append((Oc[0] + 0.10 * w, Oc[1] + (-0.02 if closed_style == "happy" else 0.06) * h))
        taper(ctx, pts, h * 0.05 * lash * lw + 1.0, lash_col, n=30, w0=0.25, w1=0.3)
        # two small lashes at the outer end
        for (dx_, dy_) in ((0.12, 0.10), (0.06, 0.16)):
            bx, by = Oc[0] - 0.02 * w, Oc[1]
            taper(ctx, [(bx - 0.08 * w, by), (bx + dx_ * w, by + dy_ * h * (1 if closed_style != "happy" else 0.6))],
                  h * 0.03 * lash * lw + 0.5, lash_col, prof="start", n=8)
        if tears > 0:
            _tear_drop(ctx, 0.36 * w, Oc[1] + 0.12 * h, h * 0.09 * tears, tears)
        ctx.restore(); return
    # openness: blend lid controls toward the closed line
    def mixp(a, b): return (lerp(b[0], a[0], op), lerp(b[1], a[1], op))
    uI, uO = mixp(I, Ic), mixp(O, Oc)
    u1, u2 = mixp(up_c1, cl_c1), mixp(up_c2, cl_c2)
    upper = _bez_pts(uI, u1, u2, uO, 18)
    lower = _bez_pts(O, lo_c1, lo_c2, I, 16)
    # keep lower lid below the upper lid
    ctx.new_path(); ctx.move_to(*uI); ctx.curve_to(*u1, *u2, *uO)
    ctx.line_to(*O); ctx.curve_to(*lo_c1, *lo_c2, *I); ctx.close_path()
    sclera = ctx.copy_path()
    ctx.set_source_rgb(0.99, 0.99, 1.0); ctx.fill()
    ctx.save(); clip_path(ctx, sclera)
    # iris
    ix = 0.03 * w + lx * w * 0.20
    iy = 0.06 * h + look[1] * h * 0.10
    rx, ry = w * 0.335 * iris_r, h * 0.43 * iris_r
    ellipse(ctx, ix, iy, rx, ry)
    ipath = ctx.copy_path()
    g = cairo.LinearGradient(0, iy - ry, 0, iy + ry)
    g.add_color_stop_rgb(0.0, *mix_color(iris[0], (0, 0, 0), 0.3)); g.add_color_stop_rgb(0.30, *iris[0])
    g.add_color_stop_rgb(0.62, *iris[1]); g.add_color_stop_rgb(1.0, *iris[2])
    ctx.set_source(g); ctx.fill()
    ctx.save(); clip_path(ctx, ipath)
    if detail:
        R = rng(7)
        for grp, c, al in ((0, iris[2], 0.35), (1, iris[0], 0.35), (2, mix_color(iris[2], (1, 1, 1), 0.3), 0.25)):
            ctx.new_path()
            for i in range(36):
                a = R.random() * TAU
                r0 = R.uniform(0.34, 0.5) * pupil
                r1 = R.uniform(0.7, 0.98)
                ctx.move_to(ix + math.cos(a) * rx * r0, iy + math.sin(a) * ry * r0)
                ctx.line_to(ix + math.cos(a) * rx * r1, iy + math.sin(a) * ry * r1)
            ctx.set_line_width(max(0.6, rx * 0.012))
            ctx.set_source_rgba(c[0], c[1], c[2], al); ctx.stroke()
    # soft lighter ring around the pupil
    ellipse(ctx, ix, iy + ry * 0.08, rx * 0.62, ry * 0.58)
    g2 = cairo.RadialGradient(ix, iy + ry * 0.1, 0, ix, iy + ry * 0.1, rx * 0.7)
    g2.add_color_stop_rgba(0.4, *iris[2], 0.0); g2.add_color_stop_rgba(0.8, *iris[2], 0.25); g2.add_color_stop_rgba(1, *iris[2], 0)
    ctx.set_source(g2); ctx.fill()
    # pupil
    pr = 0.40 * pupil
    ellipse(ctx, ix, iy + ry * 0.03, rx * pr, ry * pr * 1.05)
    fill_rgb(ctx, mix_color(iris[0], (0.02, 0.0, 0.02), 0.55), 0.95); ctx.fill()
    # bright crescent low in iris (hard-edged cel reflection)
    crescent(ctx, ipath, (0, -ry * 0.40), mix_color(iris[2], (1, 0.96, 0.82), 0.4), 0.7)
    ctx.restore()
    ctx.new_path(); ctx.append_path(ipath)
    ctx.set_line_width(max(1.0, w * 0.018) * lw); fill_rgb(ctx, mix_color(iris[0], INK, 0.6)); ctx.stroke()
    if detail:
        ellipse(ctx, ix, iy, rx * 0.955, ry * 0.955)
        ctx.set_line_width(rx * 0.05); fill_rgb(ctx, mix_color(iris[0], INK, 0.3), 0.55); ctx.stroke()
    # upper-lid cast shadow (hard band + soft falloff)
    ctx.new_path(); ctx.move_to(uI[0] - w, uI[1] + h * 0.14)
    ctx.line_to(uI[0], uI[1] + h * 0.14); ctx.curve_to(u1[0], u1[1] + h * 0.16, u2[0], u2[1] + h * 0.16, uO[0], uO[1] + h * 0.12)
    ctx.line_to(uO[0] + w, uO[1] + h * 0.12); ctx.line_to(uO[0] + w, -h * 2); ctx.line_to(uI[0] - w, -h * 2); ctx.close_path()
    fill_rgb(ctx, (0.28, 0.18, 0.34), 0.30); ctx.fill()
    # highlights
    ellipse(ctx, ix + hl * rx * 0.36, iy - ry * 0.36, rx * 0.30, ry * 0.21, -0.45 * hl)
    ctx.set_source_rgba(1, 1, 1, 0.98); ctx.fill()
    ellipse(ctx, ix - hl * rx * 0.40, iy + ry * 0.30, rx * 0.11, rx * 0.11)
    ctx.set_source_rgba(1, 1, 1, 0.9); ctx.fill()
    ellipse(ctx, ix + hl * rx * 0.02, iy - ry * 0.02, rx * 0.05, rx * 0.05)
    ctx.set_source_rgba(1, 1, 1, 0.75); ctx.fill()
    if reflect > 0:
        for i in range(6):
            px = ix - rx * 0.62 + i * rx * 0.24
            ctx.rectangle(px, iy - ry * 0.62 + abs(i - 2.5) * ry * 0.03, rx * 0.05, ry * 0.035)
        ctx.set_source_rgba(1, 1, 0.95, 0.85 * reflect); ctx.fill()
    if tears > 0:
        ctx.new_path(); smooth_path(ctx, [(p[0], p[1] - h * 0.03) for p in lower[2:-2]])
        ctx.set_line_width(h * 0.08 * tears); ctx.set_source_rgba(0.85, 0.95, 1.0, 0.6 * tears); ctx.stroke()
        ctx.new_path(); smooth_path(ctx, [(p[0], p[1] - h * 0.05) for p in lower[3:9]])
        ctx.set_line_width(h * 0.02); ctx.set_source_rgba(1, 1, 1, 0.8 * tears); ctx.stroke()
    ctx.restore()  # sclera clip
    lc = lash_col
    # lower lid: thin line from outer corner, fading toward the inner side
    if lower_lash:
        seg = lower[0:7]
        taper(ctx, seg, h * 0.02 * lw + 0.5, mix_color(lc, SKIN_SH2, 0.35), n=14, prof="start", w1=0.05)
        taper(ctx, lower[-5:-2], h * 0.010 * lw + 0.3, mix_color(lc, SKIN_SH2, 0.5), a=0.7, n=6)
    # upper lash band (thick at the outer half, winged past the corner)
    n = len(upper)
    thick = lambda s: h * lash * lw * (0.02 + 0.085 * smoothstep(0.0, 0.8, s))
    wing = (uO[0] + 0.14 * w, uO[1] - 0.07 * h)
    topE, botE = [], []
    for i, p in enumerate(upper):
        s = i / (n - 1)
        a = upper[max(0, i - 1)]; b = upper[min(n - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]; d = math.hypot(dx, dy) or 1
        nx, ny = dy / d, -dx / d            # points "up" (outward) for a left->right curve
        if ny > 0: nx, ny = -nx, -ny
        th = thick(s)
        topE.append((p[0] + nx * th, p[1] + ny * th))
        botE.append((p[0] - nx * h * 0.012, p[1] - ny * h * 0.012))
    ctx.new_path(); smooth_path(ctx, topE + [wing] + list(reversed(botE)), closed=True)
    fill_rgb(ctx, lc); ctx.fill()
    # lash clumps rising from the band's outer half
    for s_, ln, ang in ((0.78, 0.07, -0.9), (0.90, 0.10, -0.55), (1.0, 0.11, -0.2)):
        i = min(n - 1, int(s_ * (n - 1))); b = upper[i]; tp = topE[i]
        fl = ln * lash * 1.6 * min(1.0, 0.35 + 0.65 * w / (0.85 * h))
        tipp = (tp[0] + math.cos(ang) * fl * h, tp[1] + math.sin(ang) * fl * h)
        taper(ctx, [((b[0] + tp[0]) / 2 - 0.04 * w, (b[1] + tp[1]) / 2), (tp[0] + 0.02 * w, tp[1]), tipp],
              h * 0.05 * lash * lw + 0.5, lc, prof="start", n=10)
    # warm reddish-brown tint band inside the lash line (modern anime touch)
    taper(ctx, [((a[0] * 0.4 + b[0] * 0.6), (a[1] * 0.4 + b[1] * 0.6)) for a, b in zip(topE[6:-2], botE[6:-2])], h * 0.012 * lw,
          (0.55, 0.22, 0.18), a=0.6, n=14)
    if crease:
        cr = [(p[0] * 1.02, p[1] - h * 0.12 - h * 0.05 * (i / (n - 1))) for i, p in enumerate(upper[3:-1])]
        taper(ctx, cr, h * 0.018 * lw + 0.4, SKIN_SH2, a=0.9, n=14)
    if tears > 0:
        _tear_drop(ctx, 0.40 * w, 0.30 * h, h * 0.09 * tears, tears)
    ctx.restore()


def _tear_drop(ctx, x, y, r, a):
    ctx.new_path()
    ctx.move_to(x, y - r * 1.6)
    ctx.curve_to(x + r * 0.9, y - r * 0.2, x + r, y + r, x, y + r)
    ctx.curve_to(x - r, y + r, x - r * 0.9, y - r * 0.2, x, y - r * 1.6)
    ctx.set_source_rgba(0.80, 0.93, 1.0, 0.85 * a); ctx.fill_preserve()
    ctx.set_line_width(max(0.8, r * 0.18)); ctx.set_source_rgba(0.35, 0.55, 0.8, 0.7 * a); ctx.stroke()
    ellipse(ctx, x - r * 0.35, y + r * 0.1, r * 0.22, r * 0.3)
    ctx.set_source_rgba(1, 1, 1, 0.95 * a); ctx.fill()


def draw_brow(ctx, cx, cy, w, o, raise_in=0.0, raise_out=0.0, thick=1.0, col=HAIR_S, a=1.0, bushy=False, lw=1.0):
    """Brow above an eye centred at cx; o = outer direction."""
    p0 = (cx - o * w * 0.42, cy - raise_in * w * 0.28 + w * 0.03)
    p1 = (cx + o * w * 0.02, cy - w * 0.10 - (raise_in + raise_out) * w * 0.12)
    p2 = (cx + o * w * 0.48, cy + w * 0.04 - raise_out * w * 0.2)
    if not bushy:
        taper(ctx, [p0, p1, p2], w * 0.055 * thick * lw + 0.8, col, a=a, n=18, prof="mid", w0=0.8, w1=0.2)
    else:
        taper(ctx, [p0, p1, p2], w * 0.13 * thick * lw, col, a=a, n=18, prof="mid", w0=1.0, w1=0.45)
        R = rng(int(cx * 7) & 255)
        for i in range(9):
            s = i / 8
            bx = lerp(p0[0], p2[0], s); by = lerp(p0[1], p2[1], s) - math.sin(math.pi * s) * w * 0.1
            taper(ctx, [(bx - o * w * 0.06, by + w * 0.05), (bx + o * w * 0.1, by - w * R.uniform(0.04, 0.12))],
                  w * 0.035, mix_color(col, (1, 1, 1), 0.15), a=a, prof="start", n=6)
        taper(ctx, [p0, p1, p2], w * 0.03, mix_color(col, INK, 0.6), a=0.6 * a, n=12)


# ============================================================ mouths
def draw_mouth(ctx, mx, my, w, m, kind, k, lw=1.0, ink=INK, teeth=True):
    """Anime mouth. w = reference width; m 0..1 open; k 3/4-ness (far side is +x)."""
    m = clamp(m)
    def X(x):  # 3/4 compression (far side +x shorter)
        return mx + (x * lerp(1.0, 0.85, k) if x < 0 else x * lerp(1.0, 0.6, k))
    cfg = {
        "soft": (0.55, 0.30, 0.10, 0.0),        # (width factor, max open, corner lift, asym)
        "smile": (0.75, 0.42, 0.22, 0.0),
        "determined": (0.55, 0.50, -0.04, 0.0),
        "shout": (0.80, 1.05, 0.02, 0.0),
        "whisper": (0.38, 0.22, 0.02, 0.0),
        "tender": (0.62, 0.30, 0.20, 0.0),
        "tease": (0.62, 0.34, 0.16, 0.14),
        "gruff": (0.85, 0.35, 0.06, 0.05),
        "gentle": (0.62, 0.40, 0.09, 0.0),
        "neutral": (0.7, 0.35, -0.02, 0.0),
        "laugh": (0.9, 0.7, 0.2, 0.0),
    }
    wf, mo, lift, asym = cfg.get(kind, cfg["soft"])
    W = w * wf * (1 + 0.15 * m * (kind in ("shout", "laugh")))
    Hm = w * mo * m
    cl = (-W / 2, -lift * w - asym * w * 0.5)
    cr = (W / 2, -lift * w + asym * w * 0.9 - (asym * w * 1.2 if asym else 0))
    if kind == "tease":
        cl = (-W / 2, -lift * w * 0.4); cr = (W / 2, -lift * w * 1.6)
    if Hm < w * 0.05:
        # closed mouth line
        mid = (0, (0.02 if lift >= 0 else -0.02) * w + (0.04 * w if kind in ("smile", "tender") else 0))
        pts = [(X(cl[0]), my + cl[1]), (X(cl[0] * 0.5), my + mid[1] * 0.8), (X(0), my + mid[1]),
               (X(cr[0] * 0.5), my + mid[1] * 0.7 + cr[1] * 0.2), (X(cr[0]), my + cr[1])]
        taper(ctx, pts, w * 0.028 * lw + 0.5, ink, n=18, w0=0.3, w1=0.3)
        if kind == "tease":
            taper(ctx, [(X(cr[0]), my + cr[1]), (X(cr[0] + w * 0.06), my + cr[1] - w * 0.03)], w * 0.03 + 0.4, ink, n=6)
        # tiny lower-lip shade
        if kind not in ("gruff", "neutral"):
            ctx.new_path(); ellipse(ctx, X(0), my + w * 0.13, w * 0.12, w * 0.03)
            fill_rgb(ctx, SKIN_SH, 0.5); ctx.fill()
        return
    # open mouth shape
    up_mid = -Hm * (0.10 if kind != "shout" else 0.06) + (0.04 * w if kind in ("smile", "tender", "tease", "laugh") else 0)
    if kind in ("smile", "tender", "laugh", "tease"):
        up_mid = -lift * w * 0.3
    top = [(X(cl[0]), my + cl[1]), (X(cl[0] * 0.55), my + up_mid * 0.9 + cl[1] * 0.2), (X(0), my + up_mid),
           (X(cr[0] * 0.55), my + up_mid * 0.9 + cr[1] * 0.2), (X(cr[0]), my + cr[1])]
    if kind == "shout":
        bot = [(X(cr[0] * 0.75), my + Hm * 0.75), (X(0), my + Hm), (X(cl[0] * 0.75), my + Hm * 0.75)]
    elif kind == "whisper":
        bot = [(X(cr[0] * 0.6), my + Hm * 0.8), (X(0), my + Hm), (X(cl[0] * 0.6), my + Hm * 0.8)]
    else:
        bot = [(X(cr[0] * 0.6), my + Hm * 0.78 + cr[1] * 0.3), (X(0), my + Hm), (X(cl[0] * 0.6), my + Hm * 0.78 + cl[1] * 0.3)]
    ctx.new_path(); smooth_path(ctx, top + bot, closed=True)
    mpath = ctx.copy_path()
    fill_rgb(ctx, MOUTH_IN); ctx.fill()
    ctx.save(); clip_path(ctx, mpath)
    # tongue
    ellipse(ctx, X(W * 0.05), my + Hm * 1.02, W * 0.34, Hm * 0.42)
    fill_rgb(ctx, TONGUE); ctx.fill()
    # upper teeth
    if teeth and Hm > w * 0.16:
        ctx.new_path(); smooth_path(ctx, top); ctx.line_to(X(cr[0]), my + cr[1] + Hm * 0.16)
        ctx.line_to(X(cl[0]), my + cl[1] + Hm * 0.16); ctx.close_path()
        ctx.new_path()
        tt = [(x, y + Hm * 0.17) for x, y in reversed(top)]
        smooth_path(ctx, top); ctx.line_to(*tt[0])
        smooth_path_cont(ctx, tt); ctx.close_path()
        ctx.set_source_rgb(0.98, 0.97, 1.0); ctx.fill()
    ctx.restore()
    ctx.new_path(); ctx.append_path(mpath); ctx.set_line_width(w * 0.035 * lw + 0.5)
    fill_rgb(ctx, ink); ctx.stroke()
    # corner accents
    taper(ctx, top, w * 0.05 * lw + 0.4, ink, n=16, w0=0.6, w1=0.6)


def smooth_path_cont(ctx, pts):
    """Continue the current path through pts with a Catmull-Rom spline (line_to first point)."""
    P = [pts[0]] + list(pts) + [pts[-1]]
    ctx.line_to(*P[1])
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        ctx.curve_to(c1[0], c1[1], c2[0], c2[1], p2[0], p2[1])


# ============================================================ hair locks
def lock_shape(ctx, pts, w, n=16, tip=0.0, root_w=1.0, belly=0.25):
    """A pointed hair clump along centreline pts (root -> tip). Returns (path, side pts L, R)."""
    S = spline(pts, n)
    f = lambda s: w * 0.5 * (root_w * (1 - s) ** 0.6 * (1 + belly * math.sin(math.pi * s)) + tip * s)
    L, R = ribbon(S, f)
    ctx.new_path(); smooth_path(ctx, L + [S[-1]] + list(reversed(R)), closed=True)
    return ctx.copy_path(), L, R, S


def hair_lock(ctx, pts, w, lt, *, base=HAIR_B, shade=HAIR_S, hi=HAIR_H, lw=1.8, hi_band=(0.10, 0.55),
              hi_a=0.85, ink=HAIR_LINE, rim_a=None, n=16, tip=0.0, belly=0.25, strand=True):
    path, L, R, S = lock_shape(ctx, pts, w, n, tip=tip, belly=belly)
    rs = lt.rs if rim_a is None else rim_a
    cel(ctx, path, lt.c(base, 0.2), lt.s(shade, 0.1), lt.sh(w * 0.22), lt.rim, lt.rv(max(1.5, w * 0.06)),
        rim_a=0.45 * rs, ink=None)
    # highlight sliver along the lit side
    if hi is not None and hi_a > 0:
        a0, a1 = hi_band
        i0, i1 = int(a0 * (len(S) - 1)), max(int(a0 * (len(S) - 1)) + 2, int(a1 * (len(S) - 1)))
        side = L if lt.ldx * (L[len(L) // 2][0] - R[len(R) // 2][0]) > 0 else R
        seg = [(lerp(S[i][0], side[i][0], 0.42), lerp(S[i][1], side[i][1], 0.42)) for i in range(i0, min(i1, len(S) - 1))]
        if len(seg) >= 2:
            ctx.save(); clip_path(ctx, path)
            taper(ctx, seg, w * 0.13, lt.c(hi, 0.3), a=hi_a, n=14, w0=0.0)
            seg2 = [(lerp(S[i][0], side[i][0], 0.05), lerp(S[i][1], side[i][1], 0.05)) for i in range(i0 + 1, min(i1 + 2, len(S) - 1))]
            if len(seg2) >= 2:
                taper(ctx, seg2, w * 0.06, lt.c(hi, 0.3), a=hi_a * 0.7, n=10, w0=0.0)
            ctx.restore()
    if strand and len(S) > 6:
        seg = [(lerp(S[i][0], L[i][0], -0.25), lerp(S[i][1], L[i][1], -0.25)) for i in range(len(S) // 3, len(S) - 2)]
        taper(ctx, seg, max(0.6, w * 0.035), ink, a=0.55, n=10, prof="end", w0=0.3)
    if lw > 0:
        ctx.new_path(); smooth_path(ctx, L + [S[-1]] + list(reversed(R)))
        ctx.set_line_width(lw); fill_rgb(ctx, ink); ctx.stroke()
    return path


def sway(t, i, amp, speed=1.0, seed=3):
    return (noise1(t * 0.9 * speed + i * 0.37, seed) - 0.5) * 2 * amp + math.sin(t * 2.1 * speed + i) * amp * 0.35


# ============================================================ Mizuki expression table
MEXPR = {
    #                 brow_in brow_out squint lid_drop mouth  blush tilt  brow_y
    "soft":        dict(bi=0.15, bo=0.0, sq=0.18, ld=0.10, mouth="soft", bl=1.0, tilt=0.0),
    "smile":       dict(bi=0.20, bo=0.05, sq=0.50, ld=0.05, mouth="smile", bl=1.2, tilt=0.02),
    "determined":  dict(bi=-0.45, bo=0.10, sq=0.12, ld=0.28, mouth="determined", bl=0.8, tilt=0.06),
    "shout":       dict(bi=-0.55, bo=0.15, sq=0.25, ld=0.08, mouth="shout", bl=1.2, tilt=0.08),
    "whisper":     dict(bi=0.10, bo=-0.1, sq=0.15, ld=0.40, mouth="whisper", bl=0.9, tilt=0.03),
    "tender_eyes_closed": dict(bi=0.35, bo=0.0, sq=0.4, ld=0.0, mouth="tender", bl=1.6, tilt=0.0, closed=True),
    "teasing_smile": dict(bi=0.15, bo=0.0, sq=0.38, ld=0.22, mouth="tease", bl=1.2, tilt=0.03, asym=0.65),
}

# ------------------------------------------------------------ Mizuki head geometry (head-local units)
FACE_F = [(-110, -40), (-108, 20), (-100, 62), (-80, 100), (-44, 128), (0, 142), (44, 128), (80, 100),
          (100, 62), (108, 20), (110, -40), (80, -112), (0, -142), (-80, -112)]
FACE_3 = [(-102, -40), (-100, 20), (-92, 62), (-70, 96), (-26, 124), (48, 142), (80, 124), (100, 94),
          (112, 56), (114, 12), (106, -40), (74, -114), (-6, -144), (-86, -112)]
EYE_Y = 30
EYE_X = 52
EYE_W = 68
EYE_H = 80


def _mz_face_path(ctx, k):
    return shape(ctx, lerp_pts(FACE_F, FACE_3, k))


def _bangs_spec(helmet):
    y0 = -96 if helmet else -140
    return [  # root(front coords), mid bend, tip, width   (drawn back -> front)
        ((-106, y0 + 18), (-118, -30), (-116, 34), 48),
        ((106, y0 + 18), (118, -30), (118, 28), 48),
        ((-40, y0 - 2), (-42, -60), (-40, -34), 60),
        ((38, y0 - 2), (40, -60), (44, -36), 60),
        ((-88, y0 + 4), (-96, -52), (-98, -6), 60),
        ((84, y0 + 4), (94, -52), (102, -10), 58),
        ((56, y0 - 2), (62, -56), (68, -18), 60),
        ((-60, y0), (-66, -56), (-68, -14), 62),
        ((16, y0 - 6), (20, -58), (28, -24), 60),
        ((-22, y0 - 4), (-24, -54), (-16, -10), 58),
        ((2, y0 - 6), (4, -50), (6, 8), 30),
    ]


def _draw_bangs(ctx, k, lt, t, wind, helmet, shadow_only=False, flip_part=1.0):
    spec = _bangs_spec(helmet)
    paths = []
    for i, (r, c, tp, w) in enumerate(spec):
        if not helmet:   # roots converge toward the part so no hard root line shows
            r = (r[0] * 0.7 - 12, r[1] - 10 + abs(r[0]) * 0.25)
        sw = sway(t, i, 2.0 + 6 * wind) - wind * 7
        pts = [mp(r, k), (xmap(c[0], k) + sw * 0.4, c[1]), (xmap(tp[0], k) + sw, tp[1] - abs(sw) * 0.2)]
        ww = w * xscale((r[0] + tp[0]) / 2, k)
        if shadow_only:
            path, *_ = lock_shape(ctx, pts, ww)
            paths.append(path)
        else:
            hair_lock(ctx, pts, ww, lt, lw=1.6, rim_a=0.0)
    # a few fine loose strands (drawn as thin pointed locks)
    if not shadow_only:
        for i, (rx, tx, ty) in enumerate(((-40, -44, 22), (36, 46, 14))):
            sw = sway(t, i + 9, 3 + 8 * wind) - wind * 8
            hair_lock(ctx, [mp((rx, -70), k), (xmap(rx + (tx - rx) * 0.5, k) + sw * 0.5, -24), (xmap(tx, k) + sw, ty)],
                      9 * xscale(rx, k), lt, lw=1.2, hi=None, strand=False)
    return paths


def _sidelock(ctx, side, k, lt, t, wind, length=1.0):
    x0 = 104 * side
    sw = sway(t, 20 + side, 3 + 9 * wind) - wind * 10
    root = mp((x0 - side * 6, -50), k)
    mid = (xmap(x0 + side * 14, k) + sw * 0.4, 60)
    tip = (xmap(x0 - side * 2, k) + sw, 150 + 40 * length)
    w = 40 * xscale(x0, k) ** 0.6
    hair_lock(ctx, [root, mid, tip], w, lt, lw=1.8, hi_band=(0.12, 0.3), belly=0.35)
    # second thin lock in front
    tip2 = (xmap(x0 - side * 16, k) + sw * 1.2, 120 + 20 * length)
    hair_lock(ctx, [mp((x0 - side * 16, -30), k), (xmap(x0 - side * 6, k) + sw * 0.5, 50), tip2],
              w * 0.5, lt, lw=1.4, hi=None, belly=0.2)


def _ponytail(ctx, root, lt, t, wind, dirx=-1, length=1.0, thick=1.0, drop=1.0, riding=False):
    """Ponytail clumps from root streaming toward dirx."""
    rx, ry = root
    for j, (off, ww, ln, ph) in enumerate(((0, 64, 1.0, 0.0), (-16, 40, 0.86, 1.3), (18, 38, 0.9, 2.1), (4, 30, 0.72, 3.0))):
        pts = []
        n = 6
        for i in range(n + 1):
            s = i / n
            if riding:
                bx = rx + dirx * s * 560 * ln * length
                by = (ry + off * s * 2.2 - 60 * s + math.sin(t * 17 - s * 5.5 + ph) * 34 * s * wind
                      + math.sin(t * 9.3 - s * 3 + ph) * 14 * s)
            else:
                wv = sway(t * 1.2, j, 1.0) * 0
                swing = (math.sin(t * 1.4 + s * 1.7 + ph * 0.3) * 10 + (fbm1(t * 0.8 + s + ph, 11) - 0.5) * 30) * s * (1 + 2 * wind)
                bx = rx + dirx * (30 * math.sin(s * 2.2) + s * 40 + off * s * 0.8 + wind * 140 * s * s) + swing
                by = ry + s * 330 * ln * length * drop - wind * 80 * s * s + abs(off) * 0.2 * s
            pts.append((bx, by))
        hair_lock(ctx, pts, ww * thick, lt, lw=1.8, hi_band=(0.08, 0.32), n=22, belly=0.6 if j == 0 else 0.3)


def _helmet(ctx, k, lt, goggles, t, riding=False):
    """Jockey helmet w/ red silk cover + white star (+ goggles up)."""
    cx = xmap(0, k)
    # dome
    dome_f = [(-128, -30), (-126, -100), (-90, -158), (0, -178), (90, -158), (126, -100), (128, -30),
              (100, -62), (40, -80), (-40, -80), (-100, -62)]
    dome_3 = [(-140, 10), (-138, -80), (-100, -152), (-14, -178), (80, -160), (120, -106), (124, -52),
              (100, -66), (50, -80), (-40, -72), (-104, -40)]
    P = lerp_pts(dome_f, dome_3, k)
    path = shape(ctx, P)
    red = lt.c(RED, 0.25); reds = lt.s(RED_S, 0.2)
    cel(ctx, path, red, reds, lt.sh(26), lt.rim, lt.rv(4), rim_a=0.8 * lt.rs, lw=2.6)
    ctx.save(); clip_path(ctx, path)
    # panel seams (silk cap segments)
    for sx in (-0.45, 0.0, 0.45):
        x = xmap(sx * 120, k)
        pts = [(xmap(sx * 60, k), -176), (x + sx * 10, -120), (xmap(sx * 125, k), -60)]
        line(ctx, pts, 1.6, reds, 0.8)
    # gloss highlight
    ctx.new_path()
    ellipse(ctx, xmap(-30 * lt.ldx * 1.0, k) - lt.ldx * 10, -150, 46, 16, 0.25 * lt.ldx)
    ctx.set_source_rgba(1, 0.9, 0.9, 0.45); ctx.fill()
    # white star on the front of the cap
    sxk = xscale(10, k)
    star(ctx, xmap(10, k), -128, 26, sx=sxk)
    ctx.set_source_rgb(*lt.c((0.97, 0.97, 1.0), 0.2)); ctx.fill_preserve()
    ctx.set_line_width(1.4); fill_rgb(ctx, INK, 0.6); ctx.stroke()
    ctx.restore()
    # peak / visor
    pk_f = [(-78, -70), (0, -84), (78, -70), (60, -48), (0, -40), (-60, -48)]
    pk_3 = [(8, -80), (74, -86), (126, -60), (136, -40), (84, -42), (20, -58)]
    pk = shape(ctx, lerp_pts(pk_f, pk_3, k))
    cel(ctx, pk, red, reds, (0, -8), lt.rim, lt.rv(3), rim_a=0.6 * lt.rs, lw=2.4)
    # peak underside shadow line
    if goggles == "up":
        _goggles_up(ctx, k, lt)
    return path


def _goggle_lens(ctx, x, y, w, h, lt, tilt=0.0, frame=(0.14, 0.14, 0.19), glare=0.0, lens_a=1.0, thick=1.18):
    ctx.save(); ctx.translate(x, y); ctx.rotate(tilt)
    r = min(w, h) * 0.38
    def rr(ww, hh):
        ctx.new_path()
        ctx.move_to(-ww / 2 + r, -hh / 2)
        ctx.curve_to(ww * 0.2, -hh / 2 - hh * 0.08, ww / 2, -hh / 2, ww / 2, -hh / 2 + r)
        ctx.curve_to(ww / 2 + ww * 0.03, hh * 0.2, ww / 2 - r * 0.2, hh / 2, ww / 2 - r, hh / 2)
        ctx.curve_to(0, hh / 2 + hh * 0.05, -ww / 2 + r * 0.2, hh / 2, -ww / 2, hh / 2 - r)
        ctx.curve_to(-ww / 2 - ww * 0.03, -hh * 0.1, -ww / 2 + r * 0.2, -hh / 2, -ww / 2 + r, -hh / 2)
        ctx.close_path()
        return ctx.copy_path()
    outer = rr(w * thick, h * (thick + 0.06))
    inner = rr(w, h)
    # lens: clear with a cool tint, stronger toward the top edge
    ctx.new_path(); ctx.append_path(inner)
    g = cairo.LinearGradient(0, -h / 2, 0, h / 2)
    g.add_color_stop_rgba(0, 0.55, 0.72, 0.95, 0.42 * lens_a); g.add_color_stop_rgba(0.5, 0.75, 0.88, 1.0, 0.14 * lens_a)
    g.add_color_stop_rgba(1, 0.8, 0.92, 1.0, 0.22 * lens_a)
    ctx.set_source(g); ctx.fill()
    ctx.save(); clip_path(ctx, inner)
    for i, (off, ww, a) in enumerate(((-0.30, 0.16, 0.55), (-0.06, 0.05, 0.45), (0.34, 0.08, 0.25))):
        ctx.new_path(); ctx.move_to(-w * 0.6 + off * w, h * 0.7); ctx.line_to(-w * 0.2 + off * w, -h * 0.7)
        ctx.line_to(-w * 0.2 + (off + ww) * w, -h * 0.7); ctx.line_to(-w * 0.6 + (off + ww) * w, h * 0.7); ctx.close_path()
        ctx.set_source_rgba(1, 1, 1, clamp(a * (0.55 + 0.9 * glare))); ctx.fill()
    if glare > 0:
        ctx.new_path(); ctx.append_path(inner); ctx.set_source_rgba(1, 1, 1, 0.35 * glare); ctx.fill()
    ctx.restore()
    # frame ring
    ctx.new_path(); ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD); ctx.append_path(outer); ctx.append_path(inner)
    fill_rgb(ctx, frame); ctx.fill(); ctx.set_fill_rule(cairo.FILL_RULE_WINDING)
    ctx.save(); ctx.new_path(); ctx.append_path(outer); ctx.clip()
    ctx.new_path(); ctx.translate(0, -h * 0.06); ctx.append_path(outer); ctx.restore()
    ctx.set_line_width(max(1.5, h * 0.05)); ctx.set_source_rgba(0.55, 0.62, 0.8, 0.5); ctx.stroke()
    for pth in (outer, inner):
        ctx.new_path(); ctx.append_path(pth); ctx.set_line_width(1.8); fill_rgb(ctx, INK); ctx.stroke()
    ctx.restore()


def _goggles_up(ctx, k, lt):
    # strap around the helmet
    pts = [(xmap(-130, k), -64), (xmap(-60, k), -98), (xmap(0, k), -104), (xmap(60, k), -98), (xmap(128, k), -66)]
    taper(ctx, pts, 12, (0.14, 0.14, 0.2), n=24, w0=1.0, w1=1.0)
    for sx in (-1, 1):
        x = xmap(sx * 42, k); ws = xscale(sx * 42, k)
        if ws < 0.3: continue
        _goggle_lens(ctx, x, -100, 64 * ws, 36, lt, tilt=0.0)
    # bridge
    taper(ctx, [(xmap(-10, k), -100), (xmap(10, k), -100)], 5, (0.14, 0.14, 0.2), n=6, w0=1, w1=1)


def _goggles_down(ctx, k, lt, glare=0.0, ex=EYE_X, ey=EYE_Y, lens_w=104, lens_h=78, dirt=0.0, seed=1):
    pts = [(xmap(-150, k), ey - 16), (xmap(-100, k), ey - 12), (xmap(-60, k), ey - 8)]
    taper(ctx, pts, 16, (0.12, 0.12, 0.18), n=12, w0=1, w1=1)
    for sx in (-1, 1):
        x = xmap(sx * ex, k); ws = xscale(sx * ex, k)
        if ws < 0.25: continue
        _goggle_lens(ctx, x + sx * 2, ey + 4, lens_w * ws, lens_h, lt, glare=glare, tilt=-0.06 * sx, thick=1.11,
                     frame=(0.20, 0.21, 0.28))
    taper(ctx, [(xmap(-12, k), ey - 6), (xmap(12, k), ey - 6)], 8, (0.12, 0.12, 0.18), n=6, w0=1, w1=1)
    if dirt > 0:
        R = rng(seed)
        for i in range(int(26 * dirt)):
            sx = R.choice((-1, 1))
            x = xmap(sx * ex + R.uniform(-40, 40), k); y = ey + R.uniform(-34, 34)
            ellipse(ctx, x, y, R.uniform(1.5, 4.5), R.uniform(1.2, 3.5), R.random())
            ctx.set_source_rgba(0.35, 0.24, 0.16, R.uniform(0.5, 0.9)); ctx.fill()


def _mz_head(ctx, k, lt, *, expr, mouth, blink, look, t, wind, helmet, goggles, blush, tears,
             facing=1, riding=False, flash=0.0, dirt=0.0, sweat=0.0):
    """Mizuki's head at head-local origin (cranium centre). k: 0 front, 1 three-quarter (facing +x)."""
    E = MEXPR.get(expr, MEXPR["soft"])
    face = _mz_face_path(ctx, k)
    skin = lt.c(SKIN, 0.3); skin_s = lt.s(SKIN_SH, 0.2)
    if k > 0.5:
        # far sidelock peeks out behind cheek
        _sidelock(ctx, 1, k, lt, t, wind, length=0.8)
    # face
    cel(ctx, face, skin, skin_s, lt.sh(17), lt.rim, lt.rv(3.5), rim_a=0.9 * lt.rs, ink=None)
    ctx.save(); clip_path(ctx, face)
    # hair cast shadow on forehead and neck-side
    ctx.save(); ctx.translate(-lt.ldx * 6, 14)
    for p in _draw_bangs(ctx, k, lt, t, wind, helmet, shadow_only=True):
        ctx.new_path(); ctx.append_path(p); fill_rgb(ctx, skin_s); ctx.fill()
    ctx.restore()
    ctx.rectangle(-200, -200, 400, (-70 if helmet else -100) + 200 + 14); fill_rgb(ctx, skin_s); ctx.fill()
    # blush
    bl = clamp(blush * E["bl"])
    if bl > 0.01:
        for sx in (-1, 1):
            bx = xmap(sx * 60, k); ws = xscale(sx * 60, k)
            g = cairo.RadialGradient(bx, 74, 0, bx, 74, 40)
            g.add_color_stop_rgba(0, *BLUSH, 0.55 * bl); g.add_color_stop_rgba(1, *BLUSH, 0)
            ctx.save(); ctx.translate(bx, 74); ctx.scale(max(ws, 0.3) * 1.3, 0.7); ctx.translate(-bx, -74)
            ctx.set_source(g); ctx.arc(bx, 74, 40, 0, TAU); ctx.fill(); ctx.restore()
            if bl > 0.5:
                for j in range(3):
                    hx = bx + (j - 1) * 13 * ws
                    taper(ctx, [(hx + 5 * ws, 64), (hx - 5 * ws, 80)], 2.0, (0.9, 0.35, 0.42), a=(bl - 0.5) * 1.6, n=6)
    ctx.restore()
    # face ink contour (lower part)
    ctx.new_path(); smooth_path(ctx, lerp_pts(FACE_F, FACE_3, k)[1:10])
    ctx.set_line_width(2.6); fill_rgb(ctx, INK); ctx.stroke()
    # ---- eyes
    op = clamp(1 - blink)
    closed = E.get("closed", False)
    if closed: op = 0.0
    hl = -lt.ldx if lt.ldx != 0 else -1
    hl = -1 * (1 if lt.ldx < 0 else -1)
    for sx in (-1, 1):
        ex = xmap(sx * EYE_X, k); ws = xscale(sx * EYE_X, k)
        w = EYE_W * ws; h = EYE_H
        lk = (look[0], look[1])
        esq = E["sq"] + (E.get("asym", 0.0) * 0.5 if sx == 1 else 0.0)
        eld = E["ld"] + (E.get("asym", 0.0) * 0.3 if sx == 1 else 0.0)
        draw_eye(ctx, ex, EYE_Y, w, h, sx, open_=op, look=lk, squint=esq, lid_drop=eld,
                 tilt=E["tilt"], closed_style="happy" if closed else "relaxed", hl=hl,
                 tears=tears, lw=1.0, lash=1.25, t=t)
    # tears streaks
    if tears > 0.3:
        for sx in (-1, 1):
            ws = xscale(sx * EYE_X, k)
            if ws < 0.4: continue
            ex = xmap(sx * (EYE_X + 18), k)
            a = (tears - 0.3) / 0.7
            taper(ctx, [(ex, EYE_Y + 36), (ex + sx * 2, 70), (ex - sx * 4, 96 + 20 * a)], 4 * a + 1,
                  (0.8, 0.93, 1.0), a=0.7 * a, n=14, prof="start")
    # nose
    nx = xmap(0, k) + 52 * k
    if k < 0.5:
        taper(ctx, [(nx - 2, 64), (nx + 2, 72)], 2.4, SKIN_SH2, n=6)
        ellipse(ctx, nx + 5 * lt.ldx, 64, 3, 5); ctx.set_source_rgba(1, 1, 1, 0.5); ctx.fill()
    else:
        nx = xmap(0, k) + 62 * k
        taper(ctx, [(nx - 1, 63), (nx + 3, 70), (nx + 5, 76)], 2.4, INK, a=0.7, n=8, prof="end", w0=0.2)
        ellipse(ctx, nx - 7, 76, 7, 3); fill_rgb(ctx, skin_s, 0.8); ctx.fill()
    # mouth
    mx = xmap(0, k) + 26 * k
    draw_mouth(ctx, mx, 108, 40, mouth, E["mouth"], k)
    # front hair
    if k <= 0.5:
        _sidelock(ctx, 1, k, lt, t, wind)
    _sidelock(ctx, -1, k, lt, t, wind)
    # brows: drawn under the bangs, then ghosted over them (anime see-through convention)
    asym = E.get("asym", 0.0)
    def brows(alpha):
        for sx in (-1, 1):
            bx = xmap(sx * (EYE_X + 4), k); ws = xscale(sx * EYE_X, k)
            extra = asym if sx == 1 else 0.0
            draw_brow(ctx, bx, EYE_Y - 54 - extra * 10, EYE_W * 1.0 * ws, sx, raise_in=E["bi"] + extra * 0.6,
                      raise_out=E["bo"] + extra * 0.4, col=(0.22, 0.12, 0.14), a=alpha)
    brows(1.0)
    if not helmet:
        _hair_top(ctx, k, lt, t, wind)
    _draw_bangs(ctx, k, lt, t, wind, helmet)
    brows(0.5)
    if not helmet:
        x, y = xmap(-96, k), -60
        star(ctx, x, y, 15, sx=max(0.4, xscale(-96, k)), ang=-math.pi / 2 + 0.3)
        fill_rgb(ctx, lt.c(RED, 0.3)); ctx.fill_preserve(); ctx.set_line_width(1.8); fill_rgb(ctx, INK); ctx.stroke()
        ellipse(ctx, x - 3, y - 4, 3, 2.4); ctx.set_source_rgba(1, 1, 1, 0.8); ctx.fill()
    else:
        _helmet(ctx, k, lt, goggles if goggles != "down" else "none", t, riding=riding)
    if goggles == "down":
        _goggles_down(ctx, k, lt, glare=flash, dirt=dirt)
        brows_g = E.get("bi", 0)
        for sx in (-1, 1):
            bx = xmap(sx * (EYE_X + 4), k); ws = xscale(sx * EYE_X, k)
            draw_brow(ctx, bx, EYE_Y - 58, EYE_W * 1.0 * ws, sx, raise_in=E["bi"] * 1.3, raise_out=E["bo"],
                      col=(0.16, 0.09, 0.12), a=0.95, thick=1.3)
    if sweat > 0:
        R = rng(int(t * 6))
        for i in range(3):
            x = xmap(-100, k) - R.uniform(0, 60) - (t * 300 % 80)
            y = R.uniform(-40, 60)
            _tear_drop(ctx, x, y, 5 + 4 * R.random(), sweat)
    return face


def _mz_head_back(ctx, k, lt, t, wind, helmet, riding=False):
    """Layer drawn BEFORE the body: ponytail + back hair mass."""
    if riding:
        ctx.save(); ctx.rotate(0.14)
        _ponytail(ctx, (xmap(-100, k), 50), lt, t, wind, dirx=-1, length=1.0, riding=True)
        ctx.restore()
    elif helmet:
        root = (xmap(-92, k), 70) if k > 0.5 else (-50, 80)
        _ponytail(ctx, root, lt, t, wind, dirx=-1, length=0.95, drop=1.0)
    else:
        root = (xmap(-124, k), -50) if k > 0.5 else (-70, -40)
        _ponytail(ctx, root, lt, t, wind, dirx=-1, length=1.1)
    back_f = [(-124, -60), (-128, 30), (-116, 96), (-80, 124), (0, 110), (80, 124), (116, 96), (128, 30), (124, -60), (0, -150)]
    back_3 = [(-138, -60), (-142, 30), (-128, 96), (-96, 124), (-40, 112), (30, 90), (90, 60), (110, -20), (100, -80), (0, -150)]
    bp = shape(ctx, lerp_pts(back_f, back_3, k))
    cel(ctx, bp, lt.c(HAIR_B, 0.2), lt.s(HAIR_S, 0.1), lt.sh(30), lt.rim, lt.rv(3), rim_a=0.7 * lt.rs, ink=HAIR_LINE, lw=1.8)
    if helmet and not riding:
        # hair tie at the nape
        ellipse(ctx, xmap(-92, k) if k > 0.5 else -50, 72, 12, 14, 0.4)
        fill_rgb(ctx, lt.c(RED, 0.3)); ctx.fill_preserve(); ctx.set_line_width(1.6); fill_rgb(ctx, INK); ctx.stroke()


def _hair_top(ctx, k, lt, t, wind):
    """Top of the head when the helmet is off: skull mass + clumps flowing from a side part."""
    top_f = [(-122, -20), (-124, -100), (-84, -152), (0, -170), (84, -152), (124, -100), (122, -20), (60, -70), (-60, -70)]
    top_3 = [(-138, -10), (-140, -96), (-100, -156), (-10, -172), (80, -152), (116, -96), (112, -20), (60, -76), (-60, -70)]
    p = shape(ctx, lerp_pts(top_f, top_3, k))
    cel(ctx, p, lt.c(HAIR_B, 0.2), lt.s(HAIR_S, 0.1), lt.sh(24), lt.rim, lt.rv(3), rim_a=0.6 * lt.rs, ink=HAIR_LINE, lw=2.0)
    part = (-30, -146)
    tips = [(-132, -10, 74), (126, -24, 70), (-110, -70, 70), (100, -76, 70), (-70, -96, 62), (56, -100, 66), (-8, -104, 60)]
    for i, (tx, ty, w) in enumerate(tips):
        sw = sway(t, 30 + i, 1.5 + 5 * wind) - wind * 5
        mid = ((part[0] + tx) / 2 + (tx - part[0]) * 0.12, (part[1] + ty) / 2 - 16)
        pts = [mp(part, k), (xmap(mid[0], k) + sw * 0.3, mid[1]), (xmap(tx, k) + sw, ty)]
        hair_lock(ctx, pts, w * xscale((part[0] + tx) / 2, k) ** 0.7, lt, lw=1.6, hi_band=(0.36, 0.62), hi_a=0.9,
                  rim_a=0.3 * lt.rs, belly=0.5)


# ============================================================ bodies
TORSO_F = [(-40, -590), (-96, -574), (-128, -552), (-142, -470), (-138, -330), (-114, -190), (-124, 20), (-125, 40), (125, 40), (124, 20),
           (114, -190), (138, -330), (142, -470), (128, -552), (96, -574), (40, -590)]
TORSO_3 = [(-58, -588), (-112, -570), (-140, -546), (-150, -462), (-146, -320), (-124, -200), (-128, 20), (-129, 40), (109, 40), (108, 20),
           (106, -200), (124, -330), (124, -452), (108, -526), (72, -564), (20, -592)]
NECK_F = [(-36, -700), (-34, -610), (-42, -572), (42, -572), (34, -610), (36, -700)]
NECK_3 = [(-54, -700), (-50, -610), (-58, -575), (28, -580), (22, -612), (28, -694)]


def tube(ctx, pts, w0, w1, bulge=0.0, n=20):
    S = spline(pts, n)
    f = lambda s: lerp(w0, w1, s) * 0.5 * (1 + bulge * math.sin(math.pi * s))
    L, R = ribbon(S, f)
    ctx.new_path(); smooth_path(ctx, L + list(reversed(R)), closed=True)
    return ctx.copy_path(), S, L, R


def draw_hand(ctx, x, y, ang, s, lt, pose="open", skin=SKIN, skin_s=SKIN_SH, lw=2.0, curl=0.0):
    """Anime hand. Wrist at (x,y), fingers point along ang. s = hand length ~ palm+fingers."""
    ctx.save(); ctx.translate(x, y); ctx.rotate(ang); ctx.scale(s / 100.0, s / 100.0)
    sk = lt.c(skin, 0.3); sks = lt.s(skin_s, 0.2)
    if pose == "open":
        fingers = [(-14, 44, 0.10), (-4, 52, 0.02), (6, 50, -0.04), (15, 40, -0.12)]
        for i, (fy, ln, a) in enumerate(fingers):
            c = curl * (0.5 + 0.2 * i)
            pts = [(40, fy * 0.9), (40 + ln * 0.55, fy + math.sin(a) * ln * 0.5 + c * 8),
                   (40 + ln * math.cos(a + c * 0.8), fy + math.sin(a + c * 0.8) * ln + c * 14)]
            p, *_ = tube(ctx, pts, 12.5, 9.5, n=10)
            cel(ctx, p, sk, sks, (0, -4), ink=INK, lw=lw * 100 / s * 0.55)
        palm = shape(ctx, [(0, -16), (22, -20), (44, -18), (48, 0), (44, 20), (20, 20), (0, 15)])
        cel(ctx, palm, sk, sks, (0, -5), ink=INK, lw=lw * 100 / s * 0.55)
        thumb = [(14, -16), (30, -30), (46, -36)]
        p, *_ = tube(ctx, thumb, 14, 10, n=10)
        cel(ctx, p, sk, sks, (0, -3), ink=INK, lw=lw * 100 / s * 0.55)
    else:  # fist / grip
        palm = shape(ctx, [(0, -16), (26, -22), (50, -18), (58, 0), (52, 20), (24, 22), (0, 15)])
        cel(ctx, palm, sk, sks, (0, -6), ink=INK, lw=lw * 100 / s * 0.55)
        for i in range(3):
            fy = -12 + i * 11
            line(ctx, [(46, fy), (56, fy + 5)], lw * 100 / s * 0.4, INK, 0.8)
        p, *_ = tube(ctx, [(14, -16), (34, -24), (48, -18)], 13, 10, n=8)
        cel(ctx, p, sk, sks, (0, -3), ink=INK, lw=lw * 100 / s * 0.55)
    ctx.restore()


def _silk_arm(ctx, joints, w0, w1, lt, outer=1, top=None, pit=None, stripes=(0.35, 0.75),
              sleeve_col=SILK, bulge=0.2, lw=2.4, folds=True, shade_col=SILK_S, ball=True, ball_in=0.0, ball_r=1.0, end_round=0.25):
    """Loose sleeve along joints (shoulder -> elbow -> wrist), unioned with a round shoulder cap.
    Outline = union silhouette (double-width stroke under the fills). Returns the centreline samples."""
    S = spline(joints, 26)
    f = lambda s: lerp(w0, w1, s) * 0.5 * (1 + bulge * math.sin(math.pi * s))
    L, R = ribbon(S, f)
    O, I = (L, R) if outer > 0 else (R, L)
    ctx.new_path(); smooth_path(ctx, L)
    Rr = list(reversed(R))
    tx, ty = S[-1][0] - S[-2][0], S[-1][1] - S[-2][1]; tl = math.hypot(tx, ty) or 1
    ext = f(1.0) * 1.1 * end_round
    ctx.curve_to(L[-1][0] + tx / tl * ext, L[-1][1] + ty / tl * ext,
                 Rr[0][0] + tx / tl * ext, Rr[0][1] + ty / tl * ext, *Rr[0])
    smooth_path_cont(ctx, Rr); ctx.close_path()
    tubep = ctx.copy_path()
    paths = [tubep]
    if ball:
        sx, sy = joints[0]
        d0 = (S[2][0] - S[0][0], S[2][1] - S[0][1]); dl = math.hypot(*d0) or 1
        inx = -1 if outer < 0 else 1
        bx, by = sx - d0[0] / dl * w0 * 0.05, sy - d0[1] / dl * w0 * 0.05
        bx += ball_in * w0
        ctx.new_path(); ellipse(ctx, bx, by, w0 * 0.52 * ball_r, w0 * 0.5 * ball_r)
        paths.insert(0, ctx.copy_path())
    base = lt.c(sleeve_col, 0.25); sh = lt.s(shade_col, 0.2)
    for p in paths:
        ctx.new_path(); ctx.append_path(p); ctx.set_line_width(lw * 2); fill_rgb(ctx, INK); ctx.stroke()
    for p in paths:
        ctx.new_path(); ctx.append_path(p); fill_rgb(ctx, base); ctx.fill()
    for p in paths:
        ctx.save(); clip_path(ctx, p)
        crescent(ctx, p, lt.sh(w0 * 0.24), sh)
        if lt.rs > 0.01:
            crescent(ctx, p, lt.rv(3), lt.rim, 0.9 * lt.rs)
        ctx.restore()
    if ball:
        # re-shade the joint so the tube shading continues over the ball
        ctx.save(); clip_path(ctx, paths[0]); clip_path(ctx, tubep)
        ctx.new_path(); ctx.append_path(tubep); fill_rgb(ctx, base); ctx.fill()
        crescent(ctx, tubep, lt.sh(w0 * 0.24), sh)
        ctx.restore()
    ctx.save(); clip_path(ctx, tubep)
    # red hoops
    for st in stripes:
        i = int(st * (len(S) - 1))
        a = S[max(0, i - 1)]; b = S[min(len(S) - 1, i + 1)]
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        ctx.save(); ctx.translate(*S[i]); ctx.rotate(ang)
        ctx.new_path(); ctx.move_to(-13, -200); ctx.line_to(13, -200); ctx.line_to(17, 200); ctx.line_to(-9, 200); ctx.close_path()
        ctx.restore()
        band = ctx.copy_path()
        ctx.new_path(); ctx.append_path(band); fill_rgb(ctx, lt.c(RED, 0.25)); ctx.fill()
        ctx.save(); clip_path(ctx, band); crescent(ctx, tubep, lt.sh(w0 * 0.24), lt.s(RED_S, 0.2)); ctx.restore()
    # fold lines (soft silk creases)
    if folds:
        for i, fr in enumerate((0.3, 0.5, 0.64)):
            j = int(fr * (len(S) - 1))
            a = I[j]; b = O[min(len(O) - 1, j + 3)]
            taper(ctx, [a, (lerp(a[0], b[0], 0.35), lerp(a[1], b[1], 0.35) + 5), (lerp(a[0], b[0], 0.6), lerp(a[1], b[1], 0.6))],
                  3.0, sh, a=0.9, n=10, prof="start")
    ctx.restore()
    return S


def _mz_body(ctx, k, lt, t, breath, wind):
    """Silks torso (back parts) — arms are separate."""
    br = math.sin(t * TAU / 3.8) * breath
    ctx.save(); ctx.translate(0, 0); ctx.scale(1, 1 + 0.004 * br)
    # neck
    neck = shape(ctx, lerp_pts(NECK_F, NECK_3, k))
    skin = lt.c(SKIN, 0.3); skin_s = lt.s(SKIN_SH, 0.2)
    cel(ctx, neck, skin, skin_s, lt.sh(14), lt.rim, lt.rv(3), rim_a=0.8 * lt.rs, ink=INK, lw=2.2)
    ctx.save(); clip_path(ctx, neck)
    # jaw shadow on neck
    ctx.new_path(); ctx.move_to(-80, -700); ctx.line_to(80, -700); ctx.line_to(80, -640)
    ctx.curve_to(20, -610, -30, -615, -80, -650); ctx.close_path(); fill_rgb(ctx, skin_s); ctx.fill()
    ctx.restore()
    # torso
    P = lerp_pts(TORSO_F, TORSO_3, k)
    ripple = [(x + (math.sin(t * 5 + y * 0.02) * 3 * wind if abs(x) > 100 else 0), y) for x, y in P]
    torso = shape(ctx, ripple)
    cel(ctx, torso, lt.c(SILK, 0.35), lt.s(SILK_S, 0.25), lt.sh(38), lt.rim, lt.rv(4), rim_a=0.9 * lt.rs, ink=None)
    ctx.save(); clip_path(ctx, torso)
    # sash: from (viewer's) upper right shoulder to lower left hip
    a0 = (xmap(120, k * 0.8) - 10 * k, -560); a1 = (-170, -80)
    ctx.new_path()
    ang = math.atan2(a1[1] - a0[1], a1[0] - a0[0]); nx, ny = -math.sin(ang), math.cos(ang)
    sw = 44
    ctx.move_to(a0[0] + nx * sw, a0[1] + ny * sw); ctx.line_to(a1[0] + nx * sw, a1[1] + ny * sw)
    ctx.line_to(a1[0] - nx * sw, a1[1] - ny * sw); ctx.line_to(a0[0] - nx * sw, a0[1] - ny * sw); ctx.close_path()
    sash = ctx.copy_path()
    fill_rgb(ctx, lt.c(RED, 0.3)); ctx.fill()
    ctx.save(); clip_path(ctx, sash); crescent(ctx, torso, lt.sh(38), lt.s(RED_S, 0.2)); ctx.restore()
    ctx.new_path(); ctx.append_path(sash); ctx.set_line_width(2.0); fill_rgb(ctx, INK, 0.9); ctx.stroke()
    # chest / fold shading
    cxm = xmap(0, k) * 0.9
    for (pts, lw_, col) in (
        ([(cxm - 90, -400), (cxm - 60, -384), (cxm - 30, -390)], 1.2, SILK_S),
        ([(cxm + 40, -388), (cxm + 70, -384), (cxm + 96, -400)], 1.2, SILK_S),
        ([(-120, -300), (-100, -250), (-104, -180)], 1.3, SILK_S),
        ([(110, -300), (94, -240), (98, -170)], 1.3, SILK_S),
        ([(-50, -130), (-20, -104), (26, -112)], 1.2, SILK_S),
    ):
        taper(ctx, pts, lw_ * 3, lt.s(col, 0.2), a=0.9, n=12)
    # breeches (white) with elastic waistband at the bottom of the bust
    ctx.new_path(); ctx.move_to(-300, -64); ctx.curve_to(-100, -52, 100, -52, 300, -66); ctx.line_to(300, 100); ctx.line_to(-300, 100)
    ctx.close_path(); fill_rgb(ctx, lt.c((0.97, 0.97, 0.99), 0.25)); ctx.fill()
    crescent(ctx, torso, lt.sh(38), lt.s(SILK_S, 0.2), 0.6)
    ctx.new_path(); ctx.move_to(-300, -64); ctx.curve_to(-100, -52, 100, -52, 300, -66)
    ctx.set_line_width(2.0); fill_rgb(ctx, INK, 0.8); ctx.stroke()
    ctx.new_path(); ctx.move_to(-300, -44); ctx.curve_to(-100, -32, 100, -32, 300, -46)
    ctx.set_line_width(1.4); fill_rgb(ctx, SILK_S, 0.9); ctx.stroke()
    for i in range(7):
        gx = -110 + i * 36
        taper(ctx, [(gx, -60), (gx + 3, -40)], 1.4, SILK_S, a=0.8, n=4)
    # neck cast shadow on collar area
    ellipse(ctx, xmap(0, k) - 12 * k, -572, 64, 20); fill_rgb(ctx, lt.s(SILK_S, 0.25)); ctx.fill()
    ctx.restore()
    ctx.new_path(); ctx.append_path(torso); ctx.set_line_width(2.6); fill_rgb(ctx, INK); ctx.stroke()
    # collar (stand collar w/ red trim)
    cx0 = lerp(0, -16, k)
    col_pts = [(cx0 - 52, -598), (cx0 - 44, -566), (cx0, -552), (cx0 + 40, -566), (cx0 + 46, -598), (cx0 + 30, -584), (cx0, -576), (cx0 - 36, -584)]
    cp = shape(ctx, col_pts)
    cel(ctx, cp, lt.c(RED, 0.3), lt.s(RED_S, 0.2), (0, -6), lt.rim, lt.rv(2), rim_a=0.5 * lt.rs, lw=2.0)
    ctx.restore()


def _arm_pose(arm, phase, k, t, side):
    """Sleeve joints etc. for arm on screen side (-1 near/left, +1 far/right) in canonical (facing +x) coords.
    Returns dict(j=joints, top, pit, outer, hand, ang, pose, w0, w1, behind)."""
    bob = math.sin(t * TAU / 3.8) * 2
    if k < 0.5:
        shx = 150 * side; topx = 108 * side; pitx = 130 * side
    else:
        shx = -160 if side < 0 else 120; topx = -116 if side < 0 else 84; pitx = -138 if side < 0 else 102
    d = dict(top=(topx, -566), pit=(pitx, -424), outer=1 if side < 0 else -1, hand=None, ang=0, pose=None,
             w0=78, w1=64, behind=(k > 0.5 and side > 0))
    if k > 0.5 and side > 0:
        d.update(w0=72, w1=60)
    if arm == "down" or (arm == "stroke" and side > 0):
        d["j"] = [(shx - side * 4, -520), (shx + side * 22, -300 + bob), (shx + side * 12, -140 + bob), (shx - side * 22, 50)]
        return d
    if arm == "stroke":
        ph = math.sin(phase * TAU) * 0.5 + 0.5
        wr = (200 + ph * 14, -540 + ph * 70)
        d.update(j=[(shx, -504), (shx + 40, -380), (-10, -340 + ph * 12), wr], hand=wr, ang=-0.75 + ph * 0.3,
                 pose="open", outer=-1, w1=58)
        return d
    if arm == "hug":
        sq_ = math.sin(t * 1.3) * 4
        if side < 0:
            wr = (262, -575 + sq_)
            d.update(j=[(shx, -504), (-60, -440), (80, -452), wr], hand=wr, ang=-0.35, pose="open",
                     outer=-1, w1=58, curl=0.45, hand_rot=0.3)
        else:
            wr = (292, -716 + sq_)
            d.update(j=[(shx, -504), (190, -590), wr], hand=wr, ang=-0.8, pose="open",
                     outer=1, w1=56, behind=True, curl=0.45, hand_rot=0.4)
        return d
    d["j"] = [(shx, -504), (shx + side * 20, -270), (shx + side * 14, -20)]
    return d


def _draw_arm(ctx, d, lt):
    bi = 0.03 if d["j"][0][0] < 0 else -0.03
    S = _silk_arm(ctx, d["j"], d["w0"], d["w1"], lt, outer=d["outer"], ball_in=bi, ball_r=1.08)
    if d["hand"] is not None:
        a = S[-3]; b = S[-1]
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        draw_hand(ctx, b[0] - math.cos(ang) * 6, b[1] - math.sin(ang) * 6, ang + d.get("hand_rot", 0.15), 96, lt,
                  d["pose"], curl=d.get("curl", 0.25))
    return S


def draw_mizuki(ctx, x, y, scale, *, view="3q_left", expr="soft", mouth=0.0, blink=0.0, look=(0, 0),
                hair_wind=0.0, t=0.0, helmet=True, goggles="up", arm="down", arm_phase=0.0,
                light=(1, 0.8, 0.55), light_dir=-1, rim=(1, 0.85, 0.6), rim_strength=0.7, blush=0.3,
                tears=0.0, head_tilt=0.0, breath=1.0):
    flip = -1 if view == "3q_left" else 1
    k = 0.0 if view == "front" else 1.0
    lt = Light(light, (light_dir if light_dir else -1) * flip, rim, rim_strength)
    lookl = (look[0] * flip, look[1])
    ctx.save()
    ctx.translate(x, y); ctx.scale(scale * flip, scale)
    br = math.sin(t * TAU / 3.8) * breath
    swayr = (noise1(t * 0.35, 5) - 0.5) * 0.03 * breath
    ctx.translate(0, -br * 3)
    # head transform
    tilt = head_tilt + swayr + (0.10 if arm == "hug" else 0.0) + (0.04 if expr == "teasing_smile" else 0)
    hx, hy = (6 + (24 if arm == "hug" else 0)) * 1.0, -752 - br * 1.5
    pivot = (-8 * k, -640)
    def head_xform():
        ctx.translate(*pivot); ctx.rotate(tilt); ctx.translate(-pivot[0], -pivot[1]); ctx.translate(hx, hy)
    # ---- ponytail + back hair behind everything
    ctx.save(); head_xform()
    _mz_head_back(ctx, k, lt, t, hair_wind, helmet)
    ctx.restore()
    anchors = {}
    arms_ = [(side, _arm_pose(arm, arm_phase, k, t, side)) for side in (-1, 1)]
    for side, d in arms_:
        if d["behind"]:
            _draw_arm(ctx, d, lt)
            if d["hand"]: anchors["hand2" if side > 0 else "hand"] = d["hand"]
    _mz_body(ctx, k, lt, t, breath, hair_wind)
    for side, d in arms_:
        if not d["behind"] and d["hand"] is None:
            _draw_arm(ctx, d, lt)
    # head
    ctx.save(); head_xform()
    _mz_head(ctx, k, lt, expr=expr, mouth=mouth, blink=blink, look=lookl, t=t, wind=hair_wind,
             helmet=helmet, goggles=goggles, blush=blush, tears=tears)
    ctx.restore()
    # raised front arm (stroke / hug) crosses in front of the body
    for side, d in arms_:
        if not d["behind"] and d["hand"] is not None:
            _draw_arm(ctx, d, lt)
            anchors["hand" if side < 0 else "hand2"] = d["hand"]
    # anchors to screen space
    m = ctx.get_matrix()
    out = {}
    for name, p in anchors.items():
        out[name] = ctx.user_to_device(*p)
    ctx.save(); head_xform(); out["head"] = ctx.user_to_device(0, 0)
    out["mouth"] = ctx.user_to_device(xmap(0, k) + 26 * k, 104); out["eyes"] = ctx.user_to_device(xmap(0, k), EYE_Y)
    ctx.restore()
    ctx.restore()
    return out


# ============================================================ riding close-up
def draw_mizuki_riding(ctx, x, y, scale, *, expr="determined", mouth=0.0, blink=0.0, t=0.0, wind=1.0,
                       goggles="down", sweat=0.0, rim=(0.75, 0.88, 1.0), rim_strength=1.0, light_flash=0.0,
                       shake=0.0, light=(1.0, 0.93, 0.85), dirt=1.0, look=(0.35, 0.0), blush=0.6):
    """Racing close-up, crouched, facing screen-right. x,y = centre of the head; scale 1 => head ~360px."""
    lt = Light(light, 1, rim, rim_strength)   # key from ahead (screen-right), rim from behind
    ctx.save()
    sx_, sy_ = 0, 0
    if shake:
        sx_ = (noise1(t * 20, 1) - 0.5) * 2 * shake * 14; sy_ = (noise1(t * 20, 2) - 0.5) * 2 * shake * 14
    s = scale * 1.2
    ctx.translate(x + sx_, y + sy_); ctx.scale(s, s)
    gal = t * TAU * 2.2                       # gallop rhythm
    bob = math.sin(gal) * 5
    ctx.translate(0, bob)
    k = 1.0
    ang = 0.12 + math.sin(gal) * 0.012
    # ---- ponytail streaming back + back hair
    ctx.save(); ctx.rotate(ang)
    _ponytail(ctx, (xmap(-96, k), 56), lt, t, wind, dirx=-1, length=1.0, riding=True, thick=1.35)
    ctx.restore()
    # ---- torso: hunched jockey crouch. Body is drawn a bit smaller than the head (camera close to the face).
    ctx.save(); ctx.translate(-20, 150); ctx.scale(0.86, 0.86); ctx.translate(20, -150)
    def rip(u):
        a = smoothstep(-120, -800, u) * wind
        return (math.sin(gal * 3.1 - u * 0.03) * 9 + math.sin(t * 31 - u * 0.055) * 5) * a
    top = []
    for i in range(15):
        u = -40 - i * 75
        hump = -95 * math.exp(-((u + 250) / 150) ** 2)          # rounded, hunched shoulders/back
        top.append((u, 150 + hump + (-u) * 0.10 + rip(u)))
    belly = []
    for i in range(10):
        u = -1150 + i * 110
        belly.append((u, 520 - (-u) * 0.12 - rip(u) * 0.5))
    back = top + [(-1200, 280), (-1200, 390)] + belly + [(120, 760), (170, 560), (110, 330), (50, 205)]
    bp = shape(ctx, back)
    silk = lt.c(SILK, 0.25); silk_s = lt.s(SILK_S, 0.2)
    cel(ctx, bp, silk, silk_s, (40, -70), lt.rim, (26, -16), rim_a=0.95 * lt.rs, lw=3.2)
    ctx.save(); clip_path(ctx, bp)
    # shoulder-blade / spine cel shadow shapes that sell the hunch
    ctx.new_path(); smooth_path(ctx, [(-120, 150), (-260, 110), (-420, 150), (-600, 230), (-600, 300), (-400, 230), (-250, 200), (-140, 230)], closed=True)
    fill_rgb(ctx, silk_s, 0.55); ctx.fill()
    # sash diagonal across the back
    ctx.new_path(); ctx.move_to(-470, 60); ctx.line_to(-350, 40); ctx.line_to(-560, 700); ctx.line_to(-700, 700); ctx.close_path()
    sash = ctx.copy_path()
    fill_rgb(ctx, lt.c(RED, 0.25)); ctx.fill()
    ctx.save(); clip_path(ctx, sash); crescent(ctx, bp, (40, -70), lt.s(RED_S, 0.2)); ctx.restore()
    ctx.new_path(); ctx.append_path(sash); ctx.set_line_width(2.4); fill_rgb(ctx, INK, 0.9); ctx.stroke()
    # wind folds racing backward (tapered crease streaks + hard shadow pockets)
    for i in range(12):
        ph = (t * 3.0 + i / 12.0) % 1.0
        u0 = lerp(-160, -1150, ph)
        base_y = 150 - 95 * math.exp(-((u0 + 250) / 150) ** 2) + (-u0) * 0.10
        y0 = base_y + 40 + (i % 4) * 48
        pts = [(u0 + 150, y0 - 22 + rip(u0 + 150) * 0.7), (u0 + 60, y0 + rip(u0 + 60) * 0.7), (u0 - 70, y0 + 16 + rip(u0 - 70) * 0.7)]
        taper(ctx, pts, 9 + 4 * (i % 2), silk_s, a=0.95 * (1 - abs(ph - 0.5) * 1.6), n=12)
    ctx.restore()
    # trailing loose silk flaps at the hem (sharp, flickering)
    for i in range(3):
        u = -950 - i * 80
        L_ = 70 + 34 * math.sin(t * 23 + i * 2)
        yb = 520 - (-u) * 0.12
        ctx.new_path(); ctx.move_to(u + 60, yb - 12); ctx.line_to(u - L_, yb + 8 + math.sin(t * 31 + i) * 18); ctx.line_to(u + 30, yb + 18)
        ctx.close_path(); fill_rgb(ctx, silk_s); ctx.fill_preserve(); ctx.set_line_width(2.2); fill_rgb(ctx, INK); ctx.stroke()
    # ---- near arm: upper arm down from the shoulder, bent elbow, forearm forward to the reins
    elbow = (60 + math.sin(gal) * 6, 500)
    S = _silk_arm(ctx, [(-150, 250), (-60, 400), elbow], 124, 108, lt, outer=-1, stripes=(0.62,), bulge=0.12,
                  lw=3.0, ball_r=1.0, end_round=0.9)
    push = math.sin(gal) * 14                                     # hands pump with the stride
    wr = (270 + push, 470 - push * 0.4)
    S2 = _silk_arm(ctx, [elbow, (170 + push * 0.5, 490), wr], 104, 86, lt, outer=-1, stripes=(0.72,), bulge=0.08,
                   lw=3.0, ball_r=0.95)
    # glove fist + reins
    gl = lt.c((0.95, 0.95, 0.97), 0.2)
    draw_hand(ctx, wr[0] - 12, wr[1] + 4, -0.15, 150, lt, "fist", skin=(0.95, 0.95, 0.97), skin_s=SILK_S)
    ctx.new_path(); ctx.move_to(wr[0] + 70, wr[1] + 10); ctx.curve_to(wr[0] + 180, wr[1] + 30, wr[0] + 300, wr[1] + 90, wr[0] + 420, wr[1] + 180)
    ctx.set_line_width(9); fill_rgb(ctx, (0.30, 0.18, 0.10)); ctx.stroke()
    hand_dev = ctx.user_to_device(*wr)
    ctx.restore()
    # ---- neck + collar
    ctx.save(); ctx.rotate(ang * 0.5)
    neck = shape(ctx, [(-58, 70), (-64, 150), (-50, 200), (40, 196), (46, 150), (30, 90)])
    cel(ctx, neck, lt.c(SKIN, 0.3), lt.s(SKIN_SH, 0.2), (-10, -14), lt.rim, (6, -2), rim_a=0.8 * lt.rs, lw=2.4)
    ctx.save(); clip_path(ctx, neck)
    ctx.new_path(); ctx.move_to(-100, 60); ctx.line_to(100, 60); ctx.line_to(100, 150); ctx.curve_to(40, 170, -40, 150, -100, 110)
    ctx.close_path(); fill_rgb(ctx, lt.s(SKIN_SH, 0.2)); ctx.fill(); ctx.restore()
    cp = shape(ctx, [(-80, 164), (-40, 206), (48, 198), (66, 164), (36, 176), (-36, 182)])
    cel(ctx, cp, lt.c(RED, 0.25), lt.s(RED_S, 0.2), (0, -8), lw=2.2)
    ctx.restore()
    # ---- head
    ctx.save(); ctx.rotate(ang)
    _mz_head(ctx, k, lt, expr=expr, mouth=mouth, blink=blink, look=look, t=t, wind=wind * 1.4, helmet=True,
             goggles=goggles, blush=blush, tears=0, riding=True, flash=light_flash, dirt=dirt, sweat=0)
    hp = ctx.user_to_device(0, 0)
    ctx.restore()
    # ---- sweat drops flying back
    if sweat > 0:
        for i in range(4):
            ph = (t * 2.3 + i * 0.27) % 1.0
            px = lerp(-80, -520, ph) - i * 20; py = lerp(-10 + i * 30, -60 + i * 40, ph)
            _tear_drop(ctx, px, py, (7 + 3 * (i % 2)) * (1 - ph * 0.5), sweat * (1 - ph))
    # ---- flying dirt specks
    if dirt > 0:
        R = rng(int(t * FPS_GUESS))
        for i in range(int(16 * dirt)):
            px = R.uniform(-700, 450); py = R.uniform(-300, 600)
            ellipse(ctx, px, py, R.uniform(2, 7), R.uniform(2, 5), R.random())
            ctx.set_source_rgba(0.30, 0.20, 0.13, R.uniform(0.5, 0.95)); ctx.fill()
    if light_flash > 0:
        g = cairo.RadialGradient(150, -40, 0, 150, -40, 520)
        g.add_color_stop_rgba(0, 1, 1, 1, 0.55 * light_flash); g.add_color_stop_rgba(1, 1, 1, 1, 0)
        ctx.set_source(g); ctx.paint()
    out = {"head": hp, "hand": hand_dev}
    ctx.restore()
    return out


FPS_GUESS = 24


# ============================================================ eye close-up
_BOKEH = None


def _bokeh_sprite():
    global _BOKEH
    if _BOKEH is None:
        _BOKEH = cairo.ImageSurface(cairo.FORMAT_ARGB32, 64, 64)
        c = cairo.Context(_BOKEH)
        gg = cairo.RadialGradient(32, 32, 0, 32, 32, 32)
        gg.add_color_stop_rgba(0, 1, 1, 0.95, 0.85); gg.add_color_stop_rgba(0.3, 1, 0.95, 0.8, 0.35)
        gg.add_color_stop_rgba(1, 1, 0.9, 0.7, 0)
        c.set_source(gg); c.paint()
    return _BOKEH

def draw_mizuki_eyes(ctx, cx, cy, scale, *, t=0.0, open=1.0, look=(0, 0), goggles=True,
                     reflect_lights=True, focus=0.0, blush=0.25, light=(1.0, 0.95, 0.9)):
    lt = Light(light, -1, (0.75, 0.88, 1.0), 0.6)
    ctx.save(); ctx.translate(cx, cy); ctx.scale(scale, scale)
    # skin band
    ctx.rectangle(-1100, -620, 2200, 1240); fill_rgb(ctx, lt.c(SKIN, 0.2)); ctx.fill()
    g = cairo.LinearGradient(0, -420, 0, 600)
    g.add_color_stop_rgba(0, *SKIN_SH, 0.9); g.add_color_stop_rgba(0.3, *SKIN_SH, 0.0)
    g.add_color_stop_rgba(0.7, *BLUSH, 0.0); g.add_color_stop_rgba(1, *BLUSH, 0.45 * blush)
    ctx.set_source(g); ctx.rectangle(-1100, -620, 2200, 1240); ctx.fill()
    # nose bridge shade
    ctx.new_path(); ellipse(ctx, 40, 150, 40, 200); fill_rgb(ctx, SKIN_SH, 0.35); ctx.fill()
    op = clamp(open)
    pupil = lerp(1.25, 0.55, clamp(focus))
    for sx in (-1, 1):
        ex = sx * 440
        draw_eye(ctx, ex, 40, 600, 620, sx, open_=op, look=look, squint=0.1 + 0.1 * focus, lid_drop=0.15 + 0.25 * focus,
                 tilt=0.02, hl=-1, detail=1, pupil=pupil, lw=0.75, lash=0.95, reflect=1.0 if reflect_lights else 0)
        draw_brow(ctx, ex + sx * 10, -330 + 20 * focus, 520, sx, raise_in=-0.25 * focus + 0.1, raise_out=0.05,
                  col=HAIR_S, a=0.9, lw=0.6)
    # bangs from the top
    for i in range(9):
        x0 = -1000 + i * 250
        sw = sway(t, i, 10)
        pts = [(x0, -520), (x0 + 30 + sw * 0.5, -380), (x0 + 60 + sw, -250 + 60 * math.sin(i * 1.7))]
        hair_lock(ctx, pts, 230, lt, lw=3.0, n=14)
    # helmet brim
    ctx.new_path(); ctx.move_to(-1100, -420); ctx.curve_to(-400, -470, 400, -470, 1100, -420)
    ctx.line_to(1100, -600); ctx.line_to(-1100, -600); ctx.close_path()
    fill_rgb(ctx, lt.c(RED, 0.2)); ctx.fill_preserve(); ctx.set_line_width(4); fill_rgb(ctx, INK); ctx.stroke()
    if goggles:
        for sx in (-1, 1):
            ex = sx * 440
            ctx.save(); ctx.translate(ex, 20)
            ww, hh = 880, 860
            def rr(w_, h_, r_):
                ctx.new_path()
                ctx.move_to(-w_ / 2 + r_, -h_ / 2); ctx.line_to(w_ / 2 - r_, -h_ / 2)
                ctx.curve_to(w_ / 2, -h_ / 2, w_ / 2, -h_ / 2, w_ / 2, -h_ / 2 + r_)
                ctx.line_to(w_ / 2, h_ / 2 - r_); ctx.curve_to(w_ / 2, h_ / 2, w_ / 2, h_ / 2, w_ / 2 - r_, h_ / 2)
                ctx.line_to(-w_ / 2 + r_, h_ / 2); ctx.curve_to(-w_ / 2, h_ / 2, -w_ / 2, h_ / 2, -w_ / 2, h_ / 2 - r_)
                ctx.line_to(-w_ / 2, -h_ / 2 + r_); ctx.curve_to(-w_ / 2, -h_ / 2, -w_ / 2, -h_ / 2, -w_ / 2 + r_, -h_ / 2)
                ctx.close_path(); return ctx.copy_path()
            inner = rr(ww, hh, 240)
            # lens tint + reflections
            ctx.save(); clip_path(ctx, inner)
            g = cairo.LinearGradient(-ww / 2, -hh / 2, ww / 2, hh / 2)
            g.add_color_stop_rgba(0, 0.65, 0.82, 1.0, 0.18); g.add_color_stop_rgba(1, 0.4, 0.55, 0.9, 0.12)
            ctx.set_source(g); ctx.paint()
            if reflect_lights:
                R = rng(3 + sx)
                # floodlight bank reflections (curved row of bokeh)
                spr = _bokeh_sprite()
                for j in range(9):
                    u = j / 8
                    px = -ww * 0.38 + ww * 0.7 * u + math.sin(t * 0.7) * 10
                    py = -hh * 0.30 + 40 * (u - 0.5) ** 2 * 4
                    r_ = (18 + 6 * R.random()) * 3
                    ctx.save(); ctx.translate(px - r_, py - r_); ctx.scale(r_ / 32.0, r_ / 32.0)
                    ctx.set_source_surface(spr, 0, 0); ctx.paint(); ctx.restore()
                # diagonal glare streaks
                for off, w_, a in ((-0.35, 0.10, 0.25), (-0.18, 0.04, 0.18), (0.3, 0.06, 0.12)):
                    ctx.new_path(); ctx.move_to((off - 0.2) * ww, hh / 2); ctx.line_to((off + 0.1) * ww, -hh / 2)
                    ctx.line_to((off + 0.1 + w_) * ww, -hh / 2); ctx.line_to((off - 0.2 + w_) * ww, hh / 2); ctx.close_path()
                    ctx.set_source_rgba(1, 1, 1, a); ctx.fill()
            ctx.restore()
            # frame
            outer = rr(ww + 90, hh + 90, 280)
            ctx.new_path(); ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
            ctx.append_path(outer); ctx.append_path(inner)
            fill_rgb(ctx, (0.13, 0.13, 0.18)); ctx.fill_preserve()
            ctx.set_fill_rule(cairo.FILL_RULE_WINDING)
            ctx.set_line_width(5); fill_rgb(ctx, INK); ctx.stroke()
            # frame gloss
            ctx.new_path(); ctx.arc(0, 0, 1, 0, 0)
            ctx.new_path(); ctx.move_to(-ww / 2 + 60, -hh / 2 - 22); ctx.line_to(ww / 2 - 120, -hh / 2 - 22)
            ctx.set_line_width(10); ctx.set_source_rgba(0.6, 0.7, 0.9, 0.35); ctx.stroke()
            ctx.restore()
    ctx.restore()


# ============================================================ Gen
GFACE_F = [(-116, -40), (-122, 22), (-116, 76), (-98, 118), (-62, 150), (0, 162), (62, 150), (98, 118),
           (116, 76), (122, 22), (116, -40), (90, -118), (0, -144), (-90, -118)]
GFACE_3 = [(-110, -40), (-116, 22), (-108, 80), (-88, 124), (-40, 154), (46, 166), (94, 146), (116, 108),
           (128, 60), (126, 12), (120, -40), (84, -118), (-6, -146), (-96, -118)]
GSKIN = (0.99, 0.81, 0.67)
GSKIN_S = (0.88, 0.62, 0.55)
GSKIN_L = (0.74, 0.47, 0.42)          # wrinkle line tone
GHAIR = (0.78, 0.78, 0.80)
GHAIR_S = (0.52, 0.52, 0.58)
NAVY = (0.17, 0.23, 0.37)
NAVY_S = (0.09, 0.12, 0.23)
CAP = (0.46, 0.40, 0.33)
CAP_S = (0.29, 0.25, 0.21)
TOWEL = (0.95, 0.95, 0.91)
TOWEL_S = (0.72, 0.75, 0.82)
IRIS_GEN = ((0.16, 0.09, 0.06), (0.42, 0.25, 0.14), (0.78, 0.55, 0.32))

GEXPR = {
    "gruff_smile": dict(sq=0.95, ld=0.4, bi=0.2, bo=-0.1, mouth="gentle"),
    "neutral": dict(sq=0.2, ld=0.3, bi=-0.15, bo=-0.05, mouth="neutral"),
    "proud_tears": dict(sq=0.7, ld=0.3, bi=0.55, bo=-0.2, mouth="gruff", closed=True),
    "laugh": dict(sq=0.7, ld=0.0, bi=0.3, bo=0.0, mouth="laugh", closed=True),
}

_STUBBLE = None


def _stubble_pts():
    """Sparse stubble dots in front-view head coords (jaw, chin, upper lip)."""
    global _STUBBLE
    if _STUBBLE is None:
        R = rng(42); pts = []
        while len(pts) < 170:
            x = R.uniform(-118, 118); y = R.uniform(84, 156)
            if abs(x) < 36 and 108 < y < 132: continue          # mouth
            if y < 104 and abs(x) > 40 and abs(x) < 90: continue  # cheeks stay clean
            if y < 96 and abs(x) < 40: continue
            pts.append((x, y, R.uniform(0.8, 1.5), R.random()))
        _STUBBLE = pts
    return _STUBBLE


def _gen_head(ctx, k, lt, *, expr, mouth, blink, look, t, tears):
    E = GEXPR.get(expr, GEXPR["gruff_smile"])
    skin = lt.c(GSKIN, 0.3); skin_s = lt.s(GSKIN_S, 0.2)
    # back / side grey hair
    back_f = [(-130, -70), (-134, 10), (-124, 64), (-104, 40), (104, 40), (124, 64), (134, 10), (130, -70), (0, -130)]
    back_3 = [(-146, -70), (-150, 20), (-134, 90), (-104, 80), (60, 20), (112, 30), (122, -10), (118, -70), (0, -130)]
    bp = shape(ctx, lerp_pts(back_f, back_3, k))
    cel(ctx, bp, lt.c(GHAIR, 0.2), lt.s(GHAIR_S, 0.1), lt.sh(20), lt.rim, lt.rv(3), rim_a=0.6 * lt.rs, lw=2.0)
    ctx.save(); clip_path(ctx, bp)
    for i in range(8):   # short combed strands
        yy = -50 + i * 16
        line(ctx, [(lerp(-150, -60, 0) , yy), (-110, yy + 10), (-90, yy + 26)], 1.3, GHAIR_S, 0.8)
    ctx.restore()
    # ears
    ears = [-1] if k > 0.5 else [-1, 1]
    for sx in ears:
        ex = (-112 if k > 0.5 else 120 * sx)
        ep = shape(ctx, [(ex + sx * 2, -6), (ex + sx * 20, -20), (ex + sx * 30, 8), (ex + sx * 22, 48), (ex + sx * 6, 60), (ex - sx * 4, 40)])
        cel(ctx, ep, skin, skin_s, lt.sh(7), lt.rim, lt.rv(2), rim_a=0.7 * lt.rs, lw=2.2)
        line(ctx, [(ex + sx * 12, -4), (ex + sx * 20, 14), (ex + sx * 12, 38)], 1.8, GSKIN_L, 0.9)
    face = shape(ctx, lerp_pts(GFACE_F, GFACE_3, k))
    cel(ctx, face, skin, skin_s, lt.sh(16), lt.rim, lt.rv(3.5), rim_a=0.9 * lt.rs, ink=None)
    ctx.save(); clip_path(ctx, face)
    # cap shadow on forehead (hard cel)
    ctx.new_path(); ctx.move_to(-220, -220); ctx.line_to(220, -220); ctx.line_to(220, -44 - 6 * k)
    ctx.curve_to(60, -26, -60, -30, -220, -44); ctx.close_path()
    fill_rgb(ctx, skin_s); ctx.fill()
    # stubble tone (soft blue-grey over jaw + upper lip) then sparse dots
    jaw = lerp_pts([(-124, 84), (-70, 110), (-40, 100), (0, 98), (40, 100), (70, 110), (124, 84), (124, 180), (-124, 180)],
                   [(-118, 92), (-50, 116), (-10, 102), (40, 96), (80, 102), (110, 100), (136, 74), (136, 180), (-118, 180)], k)
    ctx.new_path(); smooth_path(ctx, jaw, closed=True)
    fill_rgb(ctx, (0.55, 0.52, 0.62), 0.10); ctx.fill()
    for (sx_, sy_, r_, a_) in _stubble_pts():
        ctx.new_path(); ctx.arc(xmap(sx_, k), sy_, r_, 0, TAU)
        ctx.set_source_rgba(0.45, 0.42, 0.46, 0.15 + 0.3 * a_); ctx.fill()
    # weathered cheeks
    for sx in (-1, 1):
        bx = xmap(sx * 70, k)
        g = cairo.RadialGradient(bx, 66, 0, bx, 66, 34)
        g.add_color_stop_rgba(0, 0.92, 0.46, 0.40, 0.28); g.add_color_stop_rgba(1, 0.92, 0.46, 0.40, 0)
        ctx.set_source(g); ctx.arc(bx, 66, 34, 0, TAU); ctx.fill()
    ctx.restore()
    ctx.new_path(); smooth_path(ctx, lerp_pts(GFACE_F, GFACE_3, k)[1:10]); ctx.set_line_width(2.8); fill_rgb(ctx, INK); ctx.stroke()
    # wrinkles: forehead, crow's feet, eye bags, nasolabial folds
    for j in range(2):
        taper(ctx, [(xmap(-46, k), -34 + j * 11), (xmap(0, k), -38 + j * 11), (xmap(46, k), -34 + j * 11)], 1.8, GSKIN_L, a=0.6, n=12)
    for sx in (-1, 1):
        ws = xscale(sx * 50, k)
        if ws < 0.3: continue
        ox = xmap(sx * 86, k)
        for j in range(3):
            taper(ctx, [(ox + sx * 4, 20 + j * 8), (ox + sx * 18 * ws, 12 + j * 12)], 1.5, GSKIN_L, a=0.75, n=6)
        taper(ctx, [(xmap(sx * 28, k), 56), (xmap(sx * 50, k), 62), (xmap(sx * 72, k), 55)], 1.6, GSKIN_L, a=0.5, n=10)
    for sx in (-1, 1):
        ws = xscale(sx * 40, k)
        if ws < 0.3 and sx > 0: pass
        taper(ctx, [(xmap(sx * 26, k) + 28 * k, 74), (xmap(sx * 42, k) + 24 * k, 102), (xmap(sx * 44, k) + 22 * k, 124)],
              2.8 * max(ws, 0.5), GSKIN_L, a=0.9, n=10)
    # eyes: narrow, kind, heavy lids
    op = clamp(1 - blink)
    if E.get("closed"): op = 0
    hl = -1 if lt.ldx < 0 else 1
    for sx in (-1, 1):
        ex = xmap(sx * 50, k); ws = xscale(sx * 50, k)
        draw_eye(ctx, ex, 28, 62 * ws, 40, sx, open_=op, look=look, squint=E["sq"], lid_drop=E["ld"],
                 iris=IRIS_GEN, hl=hl, lash=0.7, lw=1.2, iris_r=0.86, closed_style="happy", crease=True,
                 lower_lash=True, tears=tears, lash_col=(0.12, 0.08, 0.08))
    # bushy grey brows (low, drooping outward)
    for sx in (-1, 1):
        ws = xscale(sx * 52, k)
        draw_brow(ctx, xmap(sx * 52, k), -6, 80 * ws, sx, raise_in=E["bi"], raise_out=E["bo"] - 0.2,
                  col=lt.c(GHAIR, 0.2), bushy=True, a=1.0, thick=1.2)
    # nose (broad, weathered)
    nx = xmap(0, k) + 60 * k
    if k > 0.5:
        nx = xmap(0, k) + 76 * k
        taper(ctx, [(nx - 8, 62), (nx + 2, 78), (nx + 8, 88), (nx + 1, 94)], 2.8, INK, a=0.85, n=12, prof="end", w0=0.2)
        taper(ctx, [(nx - 24, 90), (nx - 14, 97), (nx - 4, 95)], 2.6, INK, a=0.8, n=8)
        taper(ctx, [(nx - 22, 60), (nx - 26, 80), (nx - 20, 90)], 3.0, skin_s, a=0.9, n=8)
    else:
        taper(ctx, [(nx - 16, 86), (nx - 6, 92), (nx + 6, 92), (nx + 16, 86)], 2.6, INK, a=0.8, n=10)
        taper(ctx, [(nx + 10, 30), (nx + 14, 78)], 2.6, GSKIN_L, a=0.8, n=8)
        ellipse(ctx, nx, 76, 12, 8); ctx.set_source_rgba(1, 0.9, 0.8, 0.3); ctx.fill()
    # moustache (short, clipped grey) + mouth
    mx = xmap(0, k) + 36 * k
    mst = [(mx - 38, 112), (mx - 18, 100), (mx, 102), (mx + 18, 100), (mx + 34 - 10 * k, 110), (mx + 14, 112), (mx - 14, 112)]
    mp_ = shape(ctx, mst)
    cel(ctx, mp_, lt.c(GHAIR, 0.2), lt.s(GHAIR_S, 0.1), (0, -4), ink=GHAIR_S, lw=1.2)
    draw_mouth(ctx, mx, 124, 60, mouth, E["mouth"], k, lw=1.2, teeth=True)
    # cap (flat cap / hunting cap)
    cap_f = [(-140, -36), (-138, -110), (-94, -166), (0, -184), (100, -168), (140, -112), (144, -40),
             (100, -58), (0, -70), (-100, -58)]
    cap_3 = [(-150, -20), (-152, -100), (-112, -166), (-12, -188), (90, -174), (134, -124), (148, -70),
             (110, -66), (40, -78), (-80, -56)]
    cp = shape(ctx, lerp_pts(cap_f, cap_3, k))
    cel(ctx, cp, lt.c(CAP, 0.3), lt.s(CAP_S, 0.2), lt.sh(28), lt.rim, lt.rv(4), rim_a=0.8 * lt.rs, lw=2.8)
    ctx.save(); clip_path(ctx, cp)
    R = rng(9)
    for i in range(70):  # tweed flecks
        px = R.uniform(-150, 150); py = R.uniform(-190, -40)
        ctx.new_path(); ctx.rectangle(px, py, 7, 2)
        ctx.set_source_rgba(0.22, 0.18, 0.15, 0.3); ctx.fill()
    line(ctx, [(xmap(-90, k), -148), (xmap(20, k), -176), (xmap(120, k), -128)], 2.0, CAP_S, 0.9)
    ctx.restore()
    brim_f = [(-104, -62), (0, -78), (104, -62), (112, -38), (0, -42), (-112, -38)]
    brim_3 = [(-36, -60), (60, -84), (150, -72), (186, -42), (104, -36), (-8, -44)]
    bp2 = shape(ctx, lerp_pts(brim_f, brim_3, k))
    cel(ctx, bp2, lt.c(CAP, 0.3), lt.s(CAP_S, 0.2), (0, -10), lt.rim, lt.rv(3), rim_a=0.6 * lt.rs, lw=2.6)
    # brim cast shadow line
    return face


def _navy_arm(ctx, joints, w0, w1, lt, outer, top=None, pit=None, lw=2.6, ball=True, end_round=0.25):
    bi = 0.1 if joints[0][0] < 0 else -0.1
    return _silk_arm(ctx, joints, w0, w1, lt, outer=outer, top=top, pit=pit, stripes=(), sleeve_col=NAVY,
                     shade_col=NAVY_S, bulge=0.12, lw=lw, ball=ball, ball_in=bi, ball_r=0.9, end_round=end_round)


def draw_gen(ctx, x, y, scale, *, view="3q_right", expr="gruff_smile", mouth=0.0, blink=0.0, look=(0, 0),
             t=0.0, light=(1, 0.8, 0.55), light_dir=-1, rim=(1, 0.85, 0.6), rim_strength=0.6,
             arms="crossed", post=True, tears=0.0, breath=1.0):
    flip = -1 if view == "3q_left" else 1
    k = 0.0 if view == "front" else 1.0
    lt = Light(light, (light_dir if light_dir else -1) * flip, rim, rim_strength)
    lookl = (look[0] * flip, look[1])
    if expr == "proud_tears" and tears == 0.0:
        tears = 0.8
    ctx.save(); ctx.translate(x, y); ctx.scale(scale * flip * 1.06, scale * 1.06)
    br = math.sin(t * TAU / 4.4) * breath
    ctx.translate(0, -br * 3)
    tilt = (noise1(t * 0.3, 8) - 0.5) * 0.025 + (0.05 if expr == "proud_tears" else 0) + (-0.04 if expr == "laugh" else 0)
    hx, hy = 8 + 6 * k, -736 - br * 1.5
    pivot = (0, -620)
    def head_xform():
        ctx.translate(*pivot); ctx.rotate(tilt); ctx.translate(-pivot[0], -pivot[1]); ctx.translate(hx, hy)
    skin = lt.c(GSKIN, 0.3); skin_s = lt.s(GSKIN_S, 0.2)
    navy = lt.c(NAVY, 0.3); navy_s = lt.s(NAVY_S, 0.2)
    anchors = {}
    # far arm behind torso in 3q (for down/lean)
    if k > 0.5 and arms in ("down",):
        _navy_arm(ctx, [(170, -500), (190, -270), (184, 40)], 104, 90, lt, -1, top=(120, -566), pit=(150, -420))
    # neck (thick)
    neck = shape(ctx, lerp_pts([(-56, -690), (-58, -600), (-70, -560), (70, -560), (58, -600), (56, -690)],
                               [(-66, -690), (-70, -600), (-80, -560), (54, -560), (48, -600), (48, -690)], k))
    cel(ctx, neck, skin, skin_s, lt.sh(16), lt.rim, lt.rv(3), rim_a=0.7 * lt.rs, lw=2.4)
    ctx.save(); clip_path(ctx, neck)
    ctx.new_path(); ctx.move_to(-100, -700); ctx.line_to(100, -700); ctx.line_to(100, -630); ctx.curve_to(30, -600, -30, -604, -100, -640)
    ctx.close_path(); fill_rgb(ctx, skin_s); ctx.fill(); ctx.restore()
    # torso: stocky navy work jacket, sloped heavy shoulders
    TF = [(-62, -592), (-140, -572), (-196, -540), (-214, -470), (-206, -330), (-196, -200), (-202, 20), (-203, 40),
          (203, 40), (202, 20), (196, -200), (206, -330), (214, -470), (196, -540), (140, -572), (62, -592)]
    T3 = [(-76, -590), (-158, -568), (-212, -530), (-224, -460), (-210, -320), (-196, -200), (-198, 20), (-199, 40),
          (171, 40), (170, 20), (166, -200), (182, -330), (186, -450), (172, -516), (116, -560), (40, -594)]
    torso = shape(ctx, lerp_pts(TF, T3, k))
    cel(ctx, torso, navy, navy_s, lt.sh(40), lt.rim, lt.rv(4), rim_a=0.8 * lt.rs, lw=2.8)
    ctx.save(); clip_path(ctx, torso)
    cxm = xmap(0, k) * 0.7
    # zipper placket + stitching
    line(ctx, [(cxm, -566), (cxm - 4, -300), (cxm - 6, 40)], 3.0, NAVY_S, 1.0)
    line(ctx, [(cxm + 6, -566), (cxm + 2, -300), (cxm, 40)], 1.3, (0.50, 0.55, 0.68), 0.6)
    # chest pockets with flaps
    for sx in (-1, 1):
        px = cxm + sx * 96 * xscale(sx * 96, k) ** 0.8
        pw = 84 * xscale(sx * 96, k) ** 0.8
        ctx.new_path(); ctx.rectangle(px - pw / 2, -430, pw, 92)
        ctx.set_line_width(1.8); fill_rgb(ctx, NAVY_S); ctx.stroke()
        flap = shape(ctx, [(px - pw / 2 - 4, -440), (px + pw / 2 + 4, -440), (px + pw / 2, -410), (px, -404), (px - pw / 2, -410)])
        cel(ctx, flap, navy, navy_s, (0, -6), lw=1.8)
    for pts in ([(-170, -300), (-130, -240), (-136, -150)], [(150, -300), (116, -230), (126, -140)],
                [(-80, -110), (-30, -86), (22, -104)]):
        taper(ctx, pts, 5, NAVY_S, a=0.9, n=10)
    ctx.restore()
    # towel around the neck: loop behind the neck + two hanging ends
    tw = lt.c(TOWEL, 0.3); tws = lt.s(TOWEL_S, 0.2)
    c0 = xmap(0, k) * 0.6 - 6 * k
    loop = shape(ctx, [(c0 - 96, -596), (c0 - 50, -640), (c0 + 50, -640), (c0 + 96, -596), (c0 + 60, -568), (c0, -560), (c0 - 60, -568)])
    cel(ctx, loop, tw, tws, lt.sh(10), lw=2.2)
    for sx in (-1, 1):
        ws = 1.0 if k < 0.5 else (1.0 if sx < 0 else 0.78)
        swing = math.sin(t * 1.3 + sx) * 3
        pts = [(c0 + sx * 64 * ws, -616), (c0 + sx * 92 * ws, -540), (c0 + sx * 84 * ws + swing, -430), (c0 + sx * 80 * ws + swing, -370)]
        p, S, L, R_ = tube(ctx, pts, 66 * ws, 58 * ws, bulge=0.08, n=16)
        cel(ctx, p, tw, tws, lt.sh(14), lt.rim, lt.rv(3), rim_a=0.6 * lt.rs, lw=2.2)
        ctx.save(); clip_path(ctx, p)
        for yy in (-404, -390):
            ctx.new_path(); ctx.rectangle(-400, yy, 800, 6); fill_rgb(ctx, lt.c((0.24, 0.44, 0.78), 0.3), 0.95); ctx.fill()
        for i in range(3):
            line(ctx, [lerp_pts([S[2]], [S[-2]], 0.2 + 0.3 * i)[0], S[-3]], 1.2, tws, 0.0)
        ctx.restore()
    # jacket collar (turned-down points)
    for sx in (-1, 1):
        ws = xscale(sx * 60, k)
        cp = shape(ctx, [(c0 + sx * 50 * ws, -604), (c0 + sx * 118 * ws, -588), (c0 + sx * 136 * ws, -548), (c0 + sx * 84 * ws, -516), (c0 + sx * 60 * ws, -560)])
        cel(ctx, cp, navy, navy_s, (0, -6), lt.rim, lt.rv(2), rim_a=0.6 * lt.rs, lw=2.2)
    # ---- arms
    if k < 0.5:
        shN, shF = (-186, -500), (186, -500)
        topN, topF, pitN, pitF = (-136, -566), (136, -566), (-168, -420), (168, -420)
    else:
        shN, shF = (-204, -496), (160, -494)
        topN, topF, pitN, pitF = (-150, -564), (112, -560), (-186, -420), (140, -420)
    if arms == "down":
        _navy_arm(ctx, [shN, (shN[0] - 18, -270), (shN[0] - 12, 40)], 110, 94, lt, 1, top=topN, pit=pitN)
        if k < 0.5:
            _navy_arm(ctx, [shF, (shF[0] + 18, -270), (shF[0] + 12, 40)], 110, 94, lt, -1, top=topF, pit=pitF)
    elif arms == "crossed":
        b = math.sin(t * TAU / 4.4) * 2 * breath
        # upper arms hanging at the sides
        _navy_arm(ctx, [shF, (shF[0] + 14, -380), (shF[0] + 4, -300 + b)], 108, 100, lt, -1, top=topF, pit=pitF, end_round=0.9)
        _navy_arm(ctx, [shN, (shN[0] - 14, -380), (shN[0] - 4, -300 + b)], 112, 104, lt, 1, top=topN, pit=pitN, end_round=0.9)
        # lower forearm (near arm) goes across to the far side, hand tucked away
        _navy_arm(ctx, [(shN[0] + 10, -268 + b), (xmap(0, k) * 0.6, -262 + b), (shF[0] - 10, -300 + b)], 100, 88, lt, -1, lw=2.6, ball=True, end_round=0.8)
        # upper forearm (far arm) crosses in front, its fist grips the near upper arm
        Sx = _navy_arm(ctx, [(shF[0] + 6, -318 + b), (xmap(0, k) * 0.6, -330 + b), (shN[0] + 26, -364 + b)], 102, 90, lt, 1, lw=2.6, ball=True)
        e = Sx[-1]
        draw_hand(ctx, e[0] + 8, e[1] + 2, math.pi + 0.35, 82, lt, "fist", skin=GSKIN, skin_s=GSKIN_S)
        # cuff lines
        ctx.new_path(); ctx.move_to(e[0] + 18, e[1] - 40); ctx.line_to(e[0] + 24, e[1] + 40)
        ctx.set_line_width(2.2); fill_rgb(ctx, NAVY_S); ctx.stroke()
    elif arms == "lean":
        _navy_arm(ctx, [shN, (shN[0] - 18, -270), (shN[0] - 12, 40)], 110, 94, lt, 1, top=topN, pit=pitN)
        if post:
            wood = lt.c((0.52, 0.36, 0.23), 0.3); wood_s = lt.s((0.33, 0.21, 0.14), 0.2)
            pp = shape(ctx, [(236, -330), (236, 40), (237, 42), (410, 42), (409, 40), (410, -340)])
            cel(ctx, pp, wood, wood_s, lt.sh(34), lw=2.6)
            ctx.save(); clip_path(ctx, pp)
            for i in range(5):
                line(ctx, [(260 + i * 32, -330), (256 + i * 34, -150), (262 + i * 32, 40)], 1.4, wood_s, 0.8)
            ctx.restore()
            top = shape(ctx, [(222, -356), (424, -366), (430, -324), (226, -316)])
            cel(ctx, top, lt.c((0.62, 0.44, 0.29), 0.3), wood_s, (0, -10), lw=2.4)
        S = _navy_arm(ctx, [shF, (shF[0] + 60, -420), (260, -366), (390, -364)], 108, 92, lt, 1, top=topF, pit=pitF)
        draw_hand(ctx, 382, -368, -0.05, 86, lt, "fist", skin=GSKIN, skin_s=GSKIN_S)
        anchors["hand"] = (390, -364)
    # ---- head
    ctx.save(); head_xform()
    _gen_head(ctx, k, lt, expr=expr, mouth=mouth, blink=blink, look=lookl, t=t, tears=tears)
    ctx.restore()
    out = {n: ctx.user_to_device(*p) for n, p in anchors.items()}
    ctx.save(); head_xform(); out["head"] = ctx.user_to_device(0, 0)
    out["mouth"] = ctx.user_to_device(xmap(0, k) + 36 * k, 122); ctx.restore()
    ctx.restore()
    return out


# ============================================================ self-test sheet
def _sheet(path):
    import time
    from lib.common import text as _text
    W_, H_ = 3840, 3900
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W_, H_)
    ctx = cairo.Context(surf)
    g = cairo.LinearGradient(0, 0, 0, H_)
    g.add_color_stop_rgb(0, 0.22, 0.18, 0.26); g.add_color_stop_rgb(1, 0.08, 0.08, 0.16)
    ctx.set_source(g); ctx.paint()
    times = []
    def T(fn, *a, **kw):
        t0 = time.perf_counter(); r = fn(*a, **kw)
        times.append((fn.__name__ + " " + str(kw.get("expr", kw.get("view", ""))), (time.perf_counter() - t0) * 1000)); return r
    def lab(sx, x, y):
        _text(ctx, sx, x, y, 26, color=(1, 1, 1), alpha=0.85)
    sc = 0.5
    views = [("3q_left", "soft", "down"), ("3q_right", "smile", "down"), ("front", "teasing_smile", "down"),
             ("3q_right", "determined", "stroke"), ("3q_left", "tender_eyes_closed", "hug"),
             ("front", "shout", "down"), ("3q_right", "whisper", "down"), ("front", "soft", "down")]
    for i, (v, e, a) in enumerate(views):
        x = 240 + i * 470; y = 520
        T(draw_mizuki, ctx, x, y, sc, view=v, expr=e, arm=a, mouth=0.6 if e in ("shout", "whisper") else 0.0,
          t=i * 0.7, helmet=(i != 7), goggles="up", hair_wind=0.3 if i == 3 else 0.0)
        lab(f"{v} / {e} / arm={a}", x, y + 40)
    for i, m in enumerate((0.0, 0.25, 0.5, 0.75, 1.0)):
        x = 240 + i * 470; y = 1100
        e = ["soft", "smile", "teasing_smile", "determined", "shout"][i]
        T(draw_mizuki, ctx, x, y, sc, view="front", expr=e, mouth=m, t=1.0 + i, helmet=True, goggles="up")
        lab(f"front {e} mouth={m}", x, y + 40)
    T(draw_mizuki, ctx, 240 + 5 * 470, 1100, sc, view="3q_right", expr="soft", blink=1.0, helmet=False, t=2)
    lab("blink=1 helmet=False", 240 + 5 * 470, 1140)
    T(draw_mizuki, ctx, 240 + 6 * 470, 1100, sc, view="3q_left", expr="smile", tears=0.8, helmet=False, t=3, hair_wind=0.6)
    lab("tears=0.8 hair_wind=0.6", 240 + 6 * 470, 1140)
    T(draw_mizuki, ctx, 240 + 7 * 470, 1100, sc, view="3q_right", expr="soft", goggles="down", t=4)
    lab("goggles=down", 240 + 7 * 470, 1140)
    for i, (e, m) in enumerate((("determined", 0.0), ("whisper", 0.5), ("shout", 1.0))):
        ctx.save(); ctx.rectangle(i * 1280, 1180, 1280, 900); ctx.clip()
        ctx.set_source_rgb(0.1, 0.12, 0.22); ctx.paint()
        T(draw_mizuki_riding, ctx, i * 1280 + 760, 1540, 0.9, expr=e, mouth=m, t=1.3 + i * 0.37, sweat=0.5, light_flash=0.2 * i)
        lab(f"draw_mizuki_riding {e} mouth={m}", i * 1280 + 640, 2060)
        ctx.restore()
    for i, (op, f) in enumerate(((0.45, 0.0), (1.0, 1.0))):
        ctx.save(); ctx.rectangle(i * 1920, 2100, 1920, 800); ctx.clip()
        T(draw_mizuki_eyes, ctx, i * 1920 + 960, 2500, 0.74, open=op, focus=f, t=1.0)
        lab(f"draw_mizuki_eyes open={op} focus={f}", i * 1920 + 960, 2880)
        ctx.restore()
    gens = (("3q_right", "gruff_smile", "crossed", 0.0), ("front", "neutral", "down", 0.0), ("3q_left", "proud_tears", "lean", 0.0),
            ("3q_right", "laugh", "crossed", 0.6), ("3q_right", "gruff_smile", "crossed", 0.8))
    for i, (v, e, a, m) in enumerate(gens):
        x = 380 + i * 760
        T(draw_gen, ctx, x, 3800, 0.8, view=v, expr=e, arms=a, mouth=m, t=i)
        lab(f"gen {v} / {e} / {a} / mouth={m}", x, 3860)
    surf.write_to_png(path)
    return times


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-0/-home-user-keiba/d53da140-107f-55e4-b8c0-8a92c9796981/scratchpad/chars_sheet.png"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    times = _sheet(out)
    print(out)
    for n, ms in sorted(times, key=lambda x: -x[1])[:8]:
        print(f"  {n:40s} {ms:6.1f} ms")
