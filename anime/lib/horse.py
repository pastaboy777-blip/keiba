"""Procedural anime thoroughbred for 「最後の一完歩」.

Public API
----------
GALLOP_HZ   strides / second at race speed (2.3)
STRIDE_LEN  ground travelled per gallop stride in px at scale 1 (scroll the ground at
            STRIDE_LEN*scale*GALLOP_HZ*stride px/s for zero hoof slip)
draw_horse(ctx, x, y, scale, phase, *, facing=1, coat, mane, blaze, socks, jockey, gait,
           stride, mane_wind, t, rim, rim_strength, shade, motion_blur, lean, head_up, ...)
draw_horse_stand(...)  == draw_horse(gait="stand")
draw_horse_head(ctx, x, y, scale, *, facing=-1, ...)   close-up head & neck
JOCKEY_PRESETS, COAT_PRESETS, HERO_JOCKEY

Coordinates: local horse space, +x = forward, y down (cairo), ground at y=0,
origin under the centre of mass. scale 1 => withers ~330px, nose..tail-root ~525px.
socks = (near fore, far fore, near hind, far hind)   ("near" = side facing camera)
"""
import math, os, sys
import cairo

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import PAL
from lib.common import (TAU, clamp, lerp, smoothstep, mix_color, noise1, fbm1, smooth_path,
                        radial_glow)

GALLOP_HZ = 2.3

INK = PAL["ink"]
_SIL = (0.035, 0.04, 0.10)        # silhouette target for shade=1

# ----------------------------------------------------------------------------- presets
COAT_PRESETS = {
    "chestnut": dict(coat=(0.78, 0.38, 0.16), mane=(0.95, 0.72, 0.42)),
    "bay":      dict(coat=(0.55, 0.28, 0.14), mane=(0.10, 0.07, 0.08)),
    "dark_bay": dict(coat=(0.30, 0.16, 0.10), mane=(0.07, 0.05, 0.06)),
    "black":    dict(coat=(0.13, 0.12, 0.15), mane=(0.06, 0.05, 0.08)),
    "grey":     dict(coat=(0.74, 0.75, 0.80), mane=(0.88, 0.88, 0.92)),
    "liver":    dict(coat=(0.45, 0.20, 0.10), mane=(0.38, 0.17, 0.09)),
}
COAT_PRESET_LIST = [COAT_PRESETS[k] for k in ("bay", "dark_bay", "black", "grey", "chestnut", "liver")]

JOCKEY_PRESETS = [
    dict(silk=(0.10, 0.22, 0.62), accent=(1.00, 0.84, 0.10), cap=(1.00, 0.84, 0.10), cap_star=False),  # royal blue / yellow
    dict(silk=(0.08, 0.50, 0.28), accent=(0.97, 0.97, 0.97), cap=(0.08, 0.50, 0.28), cap_star=False),  # green / white
    dict(silk=(0.95, 0.80, 0.10), accent=(0.10, 0.10, 0.12), cap=(0.10, 0.10, 0.12), cap_star=False),  # yellow / black
    dict(silk=(0.45, 0.14, 0.52), accent=(0.95, 0.60, 0.15), cap=(0.95, 0.60, 0.15), cap_star=False),  # purple / orange
    dict(silk=(0.08, 0.08, 0.12), accent=(0.95, 0.30, 0.55), cap=(0.95, 0.30, 0.55), cap_star=False),  # black / pink
    dict(silk=(0.55, 0.78, 0.95), accent=(0.10, 0.18, 0.45), cap=(0.10, 0.18, 0.45), cap_star=True),   # light blue / navy
    dict(silk=(0.92, 0.40, 0.10), accent=(0.97, 0.97, 0.97), cap=(0.97, 0.97, 0.97), cap_star=False),  # orange / white
    dict(silk=(0.70, 0.08, 0.12), accent=(0.95, 0.85, 0.30), cap=(0.10, 0.10, 0.12), cap_star=False),  # maroon / gold
]
HERO_JOCKEY = dict(silk=PAL["silk_main"], accent=PAL["silk_accent"], cap=PAL["silk_accent"],
                   cap_star=True, hair=PAL["mizuki_hair"], ponytail=True, crouch=1.0, push=0.0)

# ----------------------------------------------------------------------------- vec utils
def _add(a, b): return (a[0] + b[0], a[1] + b[1])
def _sub(a, b): return (a[0] - b[0], a[1] - b[1])
def _mul(a, k): return (a[0] * k, a[1] * k)
def _lerp2(a, b, t): return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
def _len(a): return math.hypot(a[0], a[1])
def _norm(a):
    l = math.hypot(a[0], a[1]) or 1e-9
    return (a[0] / l, a[1] / l)
def _rot(v, a):
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)
def _perp(v):  # rotate +90deg in screen space: forward->down, down->back
    return (-v[1], v[0])
def _ang(v): return math.atan2(v[1], v[0])
def _dir(a): return (math.cos(a), math.sin(a))
R = math.radians


def _ik2(root, target, l1, l2, side):
    """2-bone IK. Returns (joint, reached_target). side=+1 bends to the _perp() side."""
    v = _sub(target, root)
    D = _len(v)
    D = max(abs(l1 - l2) + 1e-3, min(D, l1 + l2 - 1e-3))
    u = _norm(v)
    ca = clamp((l1 * l1 + D * D - l2 * l2) / (2 * l1 * D), -1, 1)
    sa = math.sqrt(1 - ca * ca)
    n = _perp(u)
    j = (root[0] + (u[0] * ca + side * n[0] * sa) * l1, root[1] + (u[1] * ca + side * n[1] * sa) * l1)
    end = (root[0] + u[0] * D, root[1] + u[1] * D)
    end = _add(j, _mul(_norm(_sub(end, j)), l2))
    return j, end


def _herm(keys, u, periodic=True):
    """keys: list of (u, v0, v1, ...) sorted by u in [0,1). Cubic Hermite, Catmull-Rom tangents."""
    n = len(keys)
    if periodic:
        u = u % 1.0
        ext = [(k[0] - 1.0,) + tuple(k[1:]) for k in keys[-2:]] + list(keys) + \
              [(k[0] + 1.0,) + tuple(k[1:]) for k in keys[:2]]
    else:
        u = clamp(u, keys[0][0], keys[-1][0])
        a, b = keys[0], keys[-1]
        ext = [(2 * a[0] - keys[1][0],) + tuple(2 * x - y for x, y in zip(a[1:], keys[1][1:]))] + list(keys) + \
              [(2 * b[0] - keys[-2][0],) + tuple(2 * x - y for x, y in zip(b[1:], keys[-2][1:]))]
    i = 1
    while i < len(ext) - 3 and ext[i + 1][0] <= u:
        i += 1
    p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
    h = p2[0] - p1[0]
    s = (u - p1[0]) / h if h > 1e-9 else 0.0
    s2, s3 = s * s, s * s * s
    h00, h10, h01, h11 = 2 * s3 - 3 * s2 + 1, s3 - 2 * s2 + s, -2 * s3 + 3 * s2, s3 - s2
    out = []
    for k in range(1, len(p1)):
        m1 = (p2[k] - p0[k]) / (p2[0] - p0[0]) * h
        m2 = (p3[k] - p1[k]) / (p3[0] - p1[0]) * h
        out.append(h00 * p1[k] + h10 * m1 + h01 * p2[k] + h11 * m2)
    return out


def _signed_area(pts):
    a = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]; x1, y1 = pts[(i + 1) % len(pts)]
        a += x0 * y1 - x1 * y0
    return a


# ----------------------------------------------------------------------------- skeleton
# rest landmarks (body frame, facing +x, y down)
B_W = (55.0, -332.0)          # withers
B_BACK = (-15.0, -314.0)
B_GIRTH = (38.0, -178.0)
B_BELLY = (-45.0, -181.0)
B_CHEST = (157.0, -278.0)     # neck base, front
B_NECK0 = (92.0, -300.0)      # neck pivot
B_SCAP = (50.0, -300.0)       # scapula pivot
B_SHOULDER = (136.0, -252.0)  # point of shoulder (rest)
B_SADDLE = (18.0, -328.0)
B_COM = (0.0, -240.0)

H_PIV = (-70.0, -292.0)       # loin pivot for spine flex
H_LOIN = (-90.0, -318.0)
H_CROUP = (-138.0, -329.0)
H_TAIL = (-194.0, -311.0)
H_BUTT = (-212.0, -272.0)
H_HAM = (-206.0, -232.0)
H_FLANK = (-100.0, -210.0)
H_HIP = (-140.0, -262.0)

FORE_L = (78.0, 100.0, 58.0, 24.0)   # humerus, forearm, cannon, pastern
HIND_L = (95.0, 100.0, 62.0, 24.0)   # femur, tibia, cannon, pastern
PAST_REST = R(60.0)                  # screen angle of fetlock->coronet at rest
PAST_REL = R(-30.0)                  # pastern relative to cannon at rest

# hoof in local frame (sole centre origin, x fwd, y down)
_HOOF = [(15.0, 0.0), (-11.0, 0.0), (-12.5, -9.0), (-9.0, -15.0), (4.0, -18.5)]
_HOOF_CR = (-2.0, -16.5)
_HOOF_TOE = (15.0, 0.0)

# ----------------------------------------------------------------------------- gaits
GAITS = {
    # td order: far fore, near fore, far hind, near hind (touchdown phase), stance fraction
    "gallop": dict(td=(0.33, 0.45, 0.00, 0.10), st=0.26, fore=(236.0, 6.0), hind=(-40.0, -270.0)),
    "canter": dict(td=(0.22, 0.44, 0.00, 0.22), st=0.34, fore=(215.0, 35.0), hind=(-50.0, -230.0)),
}
_G = GAITS["gallop"]
STRIDE_LEN = (_G["fore"][0] - _G["fore"][1]) / _G["st"]   # ~ 896 px at scale 1

# stance: (s, pastern angle deg, flex deg)
FORE_STANCE = [(0.0, 57.0, 4.0), (0.3, 36.0, 0.0), (0.55, 27.0, 0.0), (0.8, 44.0, 2.0), (1.0, 92.0, 14.0)]
HIND_STANCE = [(0.0, 57.0, 38.0), (0.3, 36.0, 50.0), (0.55, 30.0, 46.0), (0.8, 45.0, 30.0), (1.0, 90.0, 24.0)]
# swing: (s, Fx, Fy, flex deg, pastern-rel deg)
FORE_SWING = [(0.12, 2.0, -78.0, 72.0, 55.0), (0.30, 48.0, -142.0, 138.0, 70.0), (0.50, 150.0, -168.0, 112.0, 45.0),
              (0.68, 252.0, -132.0, 45.0, 12.0), (0.85, 284.0, -80.0, 6.0, -14.0)]
HIND_SWING = [(0.14, -298.0, -82.0, 60.0, 45.0), (0.34, -252.0, -132.0, 88.0, 62.0), (0.55, -162.0, -128.0, 98.0, 50.0),
              (0.75, -84.0, -88.0, 72.0, 22.0), (0.90, -46.0, -52.0, 46.0, 2.0)]

# body keys over phase: (phase, dy, pitch_deg(nose up +), flex(0..1 gathered), neck_deg, head_deg)
GALLOP_BODY = [(0.00, 2.0, 1.5, 0.55, 4.0, -3.0), (0.15, 7.0, 3.0, 0.25, 5.0, -2.0), (0.32, 3.0, 0.5, 0.0, 1.0, 1.0),
               (0.48, 11.0, -3.0, 0.15, -7.0, 5.0), (0.64, 4.0, 2.5, 0.45, -3.0, 2.0), (0.82, -8.0, 0.8, 1.0, 3.0, -2.0)]


class _Body:
    """Rigid transform (pitch about COM + vertical offset) and spine flex for hindquarters."""
    def __init__(self, dx, dy, pitch_deg, flex, lean=0.0):
        a = -R(pitch_deg)
        self.c, self.s = math.cos(a), math.sin(a)
        self.dx, self.dy = dx, dy
        g = -R(flex * 10.0 - 3.0)
        self.hc, self.hs = math.cos(g), math.sin(g)

    def f(self, p):   # forehand/trunk point
        x, y = p[0] - B_COM[0], p[1] - B_COM[1]
        return (x * self.c - y * self.s + B_COM[0] + self.dx, x * self.s + y * self.c + B_COM[1] + self.dy)

    def h(self, p):   # hindquarter point (flexed about loin pivot first)
        x, y = p[0] - H_PIV[0], p[1] - H_PIV[1]
        q = (x * self.hc - y * self.hs + H_PIV[0], x * self.hs + y * self.hc + H_PIV[1])
        return self.f(q)


def _hoof_world(anchor, rot, mode):
    """Return list of hoof polygon points + coronet point. mode 'toe': anchor is sole centre at rot=0 and
    hoof pivots about toe; 'cr': anchor is coronet centre."""
    if mode == "toe":
        toe = (anchor[0] + _HOOF_TOE[0], anchor[1] + _HOOF_TOE[1])
        pts = [_add(toe, _rot(_sub(p, _HOOF_TOE), rot)) for p in _HOOF]
        cr = _add(toe, _rot(_sub(_HOOF_CR, _HOOF_TOE), rot))
    else:
        pts = [_add(anchor, _rot(_sub(p, _HOOF_CR), rot)) for p in _HOOF]
        cr = anchor
    return pts, cr


def _solve_leg(root, F, flex, L, s1, s2):
    """Solve root->j1->j2->F with lower pair flex (deg). s1/s2 bend sides."""
    l1, l2, l3 = L[0], L[1], L[2]
    k = R(flex)
    d = math.sqrt(max(1.0, l2 * l2 + l3 * l3 + 2 * l2 * l3 * math.cos(k)))
    j1, Fr = _ik2(root, F, l1, d, s1)
    j2, _ = _ik2(j1, Fr, l2, l3, s2)
    return j1, j2, Fr


def _leg_state(kind, u, gait, stride, B, root_fn, extra):
    """Compute one leg. kind 'fore'|'hind'. u = time since touchdown in [0,1)."""
    g = GAITS.get(gait, _G)
    st = g["st"]
    tdx, lox = g[kind]
    cx = (tdx + lox) * 0.5
    sw = stride
    tdx = cx + (tdx - cx) * sw
    lox = cx + (lox - cx) * sw
    L = FORE_L if kind == "fore" else HIND_L
    s1, s2 = (1, -1) if kind == "fore" else (-1, 1)
    SK = FORE_STANCE if kind == "fore" else HIND_STANCE
    WK = FORE_SWING if kind == "fore" else HIND_SWING
    lift = 0.45 + 0.55 * clamp(stride, 0, 1.2)

    def stance(s):
        pa, fl = _herm(SK, s, periodic=False)
        pa = R(pa)
        H = (lerp(tdx, lox, s), 0.0)
        rot = max(0.0, pa - PAST_REST)
        hoof, cr = _hoof_world((H[0] - 1.0, 0.0), rot, "toe")
        F = (cr[0] - math.cos(pa) * L[3], cr[1] - math.sin(pa) * L[3])
        return F, fl, pa, hoof, cr

    root = root_fn(u)
    if u < st:
        F, fl, pa, hoof, cr = stance(u / st)
        j1, j2, Fr = _solve_leg(root, F, fl + extra, L, s1, s2)
        return dict(root=root, j1=j1, j2=j2, F=F, cr=cr, hoof=hoof, ground=True)
    # swing: build keys with boundary values from stance
    s = (u - st) / (1 - st)
    keys = []
    for (ss, ok) in ((0.0, 1.0), (1.0, 0.0)):
        F, fl, pa, hoof, cr = stance(ok)
        rt = root_fn(st if ok == 1.0 else 1.0)
        j1, j2, Fr = _solve_leg(rt, F, fl, L, s1, s2)
        rel = (pa - _ang(_sub(Fr, j2))) - PAST_REL
        rel = (rel + math.pi) % TAU - math.pi
        keys.append((ss, F[0], F[1], fl, math.degrees(rel)))
    mid = [(k[0], cx + (k[1] - cx) * sw, k[2] * lift, k[3], k[4]) for k in WK]
    allk = [keys[0]] + mid + [keys[1]]
    Fx, Fy, fl, rel = _herm(allk, s, periodic=False)
    F = (Fx, Fy)
    j1, j2, Fr = _solve_leg(root, F, fl + extra, L, s1, s2)
    pa = _ang(_sub(Fr, j2)) + PAST_REL + R(rel)
    cr = (Fr[0] + math.cos(pa) * L[3], Fr[1] + math.sin(pa) * L[3])
    hoof, cr = _hoof_world(cr, pa - PAST_REST, "cr")
    return dict(root=root, j1=j1, j2=j2, F=Fr, cr=cr, hoof=hoof, ground=False)


def _stand_leg(kind, Hx, B, root, rot_extra=0.0, cock=0.0):
    L = FORE_L if kind == "fore" else HIND_L
    s1, s2 = (1, -1) if kind == "fore" else (-1, 1)
    pa = PAST_REST + R(4.0)
    if cock > 0:   # resting hind: toe tipped, fetlock forward
        pa = lerp(pa, R(100), cock)
    rot = max(0.0, pa - PAST_REST)
    hoof, cr = _hoof_world((Hx, 0.0), rot, "toe")
    if cock > 0:
        hoof = [(p[0], p[1] - 4 * cock) for p in hoof]; cr = (cr[0], cr[1] - 4 * cock)
    F = (cr[0] - math.cos(pa) * L[3], cr[1] - math.sin(pa) * L[3])
    fl = (2.0 if kind == "fore" else 40.0) + cock * 35
    j1, j2, Fr = _solve_leg(root, F, fl, L, s1, s2)
    return dict(root=root, j1=j1, j2=j2, F=F, cr=cr, hoof=hoof, ground=True)


def horse_pose(phase, gait="gallop", stride=1.0, t=0.0, head_up=0.0):
    """Compute the full pose (all in local horse coordinates)."""
    P = {}
    extra_pitch = 0.0
    extra_dy = 0.0
    neck_extra = 0.0
    if gait == "burst":
        p = clamp(phase)
        g_ph = 2.6 * (0.55 * p + 0.45 * p * p) + 0.02
        stride = stride * (0.5 + 0.5 * smoothstep(0.0, 0.8, p))
        bump = (1 - smoothstep(0.0, 0.5, p)) * smoothstep(-0.12, 0.06, p)
        extra_pitch = 10.0 * bump
        extra_dy = 10.0 * (1 - smoothstep(0, 0.25, p))
        neck_extra = 3.0 * bump
        phase = g_ph % 1.0
        gname = "gallop"
    else:
        gname = gait
    if gname in ("gallop", "canter"):
        dy, pitch, flex, neck, head = _herm(GALLOP_BODY, phase if gname == "gallop" else (phase * 1.0))
        amp = 0.35 + 0.65 * clamp(stride, 0, 1.3)
        if gname == "canter":
            amp *= 1.2
        B = _Body(0.0, dy * amp + extra_dy, pitch * amp + extra_pitch, flex * clamp(stride, 0, 1), 0)
        P["neck_a"] = 24.0 + neck * amp + neck_extra + 16.0 * head_up
        P["head_a"] = 52.0 + head * amp - 8.0 * head_up
        g = GAITS[gname]
        td = g["td"]
        legs = []
        for i, kind in enumerate(("fore", "fore", "hind", "hind")):
            u0 = (phase - td[i]) % 1.0
            def root_fn(uu, kind=kind, i=i):
                ph = (td[i] + uu) % 1.0
                if abs(ph - phase) > 1e-6:
                    dy2, p2, f2, _, _ = _herm(GALLOP_BODY, ph)
                    B2 = _Body(0.0, dy2 * amp + extra_dy, p2 * amp + extra_pitch, f2 * clamp(stride, 0, 1))
                else:
                    B2 = B
                if kind == "fore":
                    return _scap_point(B2, uu, g)
                return B2.h(H_HIP)
            legs.append(_leg_state(kind, u0, gname, stride, B, root_fn, 0.0))
        P["legs"] = legs
        P["scap"] = [_scap_point(B, (phase - td[i]) % 1.0, g) for i in range(2)]
    else:  # stand
        br = math.sin(TAU * phase)
        shift = (fbm1(t * 0.25, 7) - 0.5) * 8
        B = _Body(shift * 0.3, -br * 1.2, 0.3 * br, 0.35, 0)
        P["neck_a"] = 37.0 + 2.0 * br + 12.0 * head_up + (fbm1(t * 0.3, 3) - 0.5) * 6
        P["head_a"] = 64.0 - 6.0 * head_up + (fbm1(t * 0.3, 5) - 0.5) * 4
        S = B.f(B_SHOULDER)
        hip = B.h(H_HIP)
        cock = smoothstep(0.55, 0.75, fbm1(t * 0.15, 11))
        legs = [_stand_leg("fore", 108, B, S), _stand_leg("fore", 94, B, S),
                _stand_leg("hind", -128, B, hip), _stand_leg("hind", -150 + 10 * cock, B, hip, cock=cock)]
        P["legs"] = legs
        P["scap"] = [S, S]
        P["breath"] = br
    P["B"] = B
    return P


def _scap_point(B, u, g):
    """Point of shoulder, rotating with scapula protraction depending on leg time u."""
    st = g["st"]
    if u < st:
        s = u / st
        a = lerp(-4.0, 12.0, s)
    else:
        s = (u - st) / (1 - st)
        a = _herm([(0.0, 12.0), (0.35, 6.0), (0.7, -12.0), (1.0, -4.0)], s, periodic=False)[0]
    v = _sub(B_SHOULDER, B_SCAP)
    return B.f(_add(B_SCAP, _rot(v, R(a))))


# ----------------------------------------------------------------------------- drawing helpers
def _col(c, shade):
    return mix_color(c[:3], _SIL, shade) if shade > 0 else tuple(c[:3])

def _shadow_of(c):
    return (c[0] * 0.62 + 0.02, c[1] * 0.50 + 0.02, c[2] * 0.62 + 0.07)

def _set(ctx, c, a=1.0):
    ctx.set_source_rgba(c[0], c[1], c[2], a)


def _band(ctx, path, dx, dy, color, alpha=1.0, op=cairo.OPERATOR_OVER, union=False):
    """Fill region of `path` NOT covered by `path` shifted by (dx,dy) (cel shading bands).
    union=True for paths made of several overlapping subpaths (slower, uses a group)."""
    ctx.save()
    ctx.new_path(); ctx.append_path(path)
    x0, y0, x1, y1 = ctx.path_extents()
    ctx.clip()
    if union:
        ctx.push_group()
        ctx.new_path(); ctx.append_path(path)
        _set(ctx, color, 1.0); ctx.fill()
        ctx.set_operator(cairo.OPERATOR_DEST_OUT)
        ctx.translate(dx, dy)
        ctx.new_path(); ctx.append_path(path); ctx.set_source_rgba(0, 0, 0, 1); ctx.fill()
        ctx.pop_group_to_source()
        ctx.set_operator(op)
        ctx.paint_with_alpha(alpha)
    else:
        ctx.new_path()
        ctx.rectangle(x0 - 2, y0 - 2, x1 - x0 + 4, y1 - y0 + 4)
        ctx.translate(dx, dy)
        ctx.append_path(path)
        ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        ctx.set_operator(op)
        _set(ctx, color, alpha)
        ctx.fill()
    ctx.restore()


def _limb_outline(chain, widths):
    """chain: list of centre points; widths: list of (front, back) half widths. Returns (front_pts, back_pts)
    where 'front' is the -perp side (forward for a limb pointing down)."""
    fr, bk = [], []
    n = len(chain)
    for i in range(n):
        if i == 0:
            d = _norm(_sub(chain[1], chain[0]))
        elif i == n - 1:
            d = _norm(_sub(chain[-1], chain[-2]))
        else:
            d = _norm(_add(_norm(_sub(chain[i], chain[i - 1])), _norm(_sub(chain[i + 1], chain[i]))))
        nrm = _perp(d)  # back side
        wf, wb = widths[i]
        fr.append((chain[i][0] - nrm[0] * wf, chain[i][1] - nrm[1] * wf))
        bk.append((chain[i][0] + nrm[0] * wb, chain[i][1] + nrm[1] * wb))
    return fr, bk


def _fore_shape(leg, far=False):
    S, E, K, F, cr = leg["root"], leg["j1"], leg["j2"], leg["F"], leg["cr"]
    chain = [_lerp2(S, E, 0.4), _lerp2(S, E, 0.85), _lerp2(E, K, 0.1), _lerp2(E, K, 0.38), _lerp2(E, K, 0.68),
             _lerp2(E, K, 0.9), K, _lerp2(K, F, 0.3), _lerp2(K, F, 0.78), F, _lerp2(F, cr, 0.5), cr]
    widths = [(16, 26), (24, 28), (25, 22), (21, 15), (16, 12), (13.5, 11), (15, 13),
              (10.5, 11), (9.5, 10.5), (12, 14.5), (9, 9.5), (11, 11.5)]
    if far:
        chain, widths = chain[1:], [(18, 22)] + widths[2:]
    return _limb_outline(chain, widths)


def _hind_shape(leg, far=False):
    Hj, St, Hk, F, cr = leg["root"], leg["j1"], leg["j2"], leg["F"], leg["cr"]
    chain = [_lerp2(Hj, St, 0.3), _lerp2(Hj, St, 0.75), St, _lerp2(St, Hk, 0.35), _lerp2(St, Hk, 0.72),
             _lerp2(St, Hk, 0.92), Hk, _lerp2(Hk, F, 0.3), _lerp2(Hk, F, 0.75), F, _lerp2(F, cr, 0.5), cr]
    widths = [(40, 60), (28, 62), (20, 56), (21, 33), (15, 20), (12.5, 14), (13, 16),
              (10.5, 12), (9.5, 11), (12, 14.5), (9, 9.5), (11, 11.5)]
    if far:
        chain = [_lerp2(Hj, St, 0.55)] + chain[2:]
        widths = [(24, 40), (18, 46)] + widths[3:]
    fr, bk = _limb_outline(chain, widths)
    hk = 6 if not far else 5
    bk[hk] = _add(bk[hk], _mul(_norm(_sub(St, Hk)), 6))   # point of hock
    return fr, bk


def _path_closed(ctx, fr, bk, tension=0.5):
    pts = fr + bk[::-1]
    smooth_path(ctx, pts, closed=True, tension=tension)


# ----------------------------------------------------------------------------- neck & head geometry
HEAD_TOP = [(6, -7), (38, -8.5), (72, -5), (98, 0), (112, 6), (120, 14), (122, 24), (116, 31),
            (108, 33), (104, 41), (90, 42.5), (70, 40), (46, 46), (27, 55), (9, 52), (-3, 40), (-7, 27)]


def _head_frame(poll, ha, k=1.0):
    c, s = math.cos(ha) * k, math.sin(ha) * k
    def hf(p):
        return (poll[0] + p[0] * c - p[1] * s, poll[1] + p[0] * s + p[1] * c)
    return hf


def _neck_geom(P, t, mane_wind):
    B = P["B"]
    na = R(P["neck_a"])
    N0 = B.f(B_NECK0)
    pitch_a = math.atan2(B.s, B.c)
    ang = -na + pitch_a
    poll = (N0[0] + 182 * math.cos(ang), N0[1] + 182 * math.sin(ang))
    ha = R(P["head_a"]) + pitch_a
    hf = _head_frame(poll, ha)
    W = B.f(B_W)
    v = _sub(poll, W)
    up = _norm((v[1], -v[0]))
    crest = [_add(_add(W, _mul(v, f)), _mul(up, o)) for f, o in ((0.22, 15), (0.5, 23), (0.78, 17), (0.93, 8))]
    return dict(poll=poll, ha=ha, hf=hf, crest=crest, W=W)


def _silhouette(P, NG):
    B = P["B"]
    legs = P["legs"]
    nf, nh = legs[1], legs[3]
    S = P["scap"][1]
    E = nf["j1"]
    St = nh["j1"]
    hf = NG["hf"]
    thr = hf((-7, 27))
    chest = B.f(B_CHEST)
    dv = _sub(chest, thr)
    dn = _norm((-dv[1], dv[0]))
    throat = [_add(_add(thr, _mul(dv, 0.35)), _mul(dn, -4)), _add(_add(thr, _mul(dv, 0.72)), _mul(dn, -9))]
    breath = P.get("breath", 0.0)
    pts = []
    pts += [B.h(H_TAIL), B.h(H_CROUP), _lerp2(B.h(H_LOIN), B.f(H_LOIN), 0.5), B.f(B_BACK), NG["W"]]
    pts += NG["crest"]
    pts += [hf(p) for p in HEAD_TOP]
    pts += throat
    pts += [chest, _add(S, (15, 4)), _add(_lerp2(S, E, 0.55), (8, 8)),
            _add(E, (-14, 14)), _add(B.f(B_GIRTH), (0, 2 * breath)), _add(B.f(B_BELLY), (0, 3 * breath)),
            _add(B.h(H_FLANK), (0, 1.5 * breath)), _add(St, (10, -12)), _add(St, (-30, -6)),
            B.h((-170.0, -205.0)), B.h(H_HAM), B.h(H_BUTT)]
    return pts


# ----------------------------------------------------------------------------- tail & mane
def _tail_pts(P, t, wind, gait, phase, stride):
    B = P["B"]
    root = B.h(H_TAIL)
    body_a = _ang(_sub(B.h(H_TAIL), B.h(H_CROUP)))        # croup slope, pointing back-down
    run = gait != "stand"
    segs = 7
    pts = [root]
    cur = root
    if run:
        L = 205.0 * (0.9 + 0.1 * wind)
        a0 = math.pi + R(22 + 8 * wind)                     # dock lifts up/back
        a1 = math.pi - R(14 - 10 * wind)                    # hair streams back, slightly falling
        for i in range(1, segs + 1):
            f = i / segs
            wave = math.sin(TAU * (phase - f * 0.55)) * R(7) * f
            flow = (fbm1(t * 1.9 - f * 1.8, 21) - 0.5) * R(22) * f * wind
            aa = lerp(a0, a1, smoothstep(0.0, 0.55, f)) + wave + flow
            cur = _add(cur, _mul(_dir(aa), L / segs))
            pts.append(cur)
    else:
        L = 215.0
        sw = (fbm1(t * 0.55, 31) - 0.5) * 2
        a0 = body_a + R(10)
        for i in range(1, segs + 1):
            f = i / segs
            aa = lerp(a0, R(92) + sw * R(10), smoothstep(0.0, 0.5, f)) + (fbm1(t * 1.1 - f * 1.5, 33) - 0.5) * R(8) * f
            cur = _add(cur, _mul(_dir(aa), L / segs))
            pts.append(cur)
    return pts


def _tail_shape(pts):
    """Tail outline with three pointed hair locks at the end."""
    n = len(pts)
    widths = [8, 13, 19, 24, 27, 28, 26, 22]
    up, dn = [], []
    for i, p in enumerate(pts[:-1]):
        d = _norm(_sub(pts[min(i + 1, n - 1)], pts[max(i - 1, 0)]))
        nr = _perp(d)
        w = widths[min(i, len(widths) - 1)]
        up.append(_sub(p, _mul(nr, w * 0.85)))
        dn.append(_add(p, _mul(nr, w * 1.15)))
    end = pts[-1]
    d = _norm(_sub(pts[-1], pts[-2])); nr = _perp(d)
    w = widths[-1]
    tips = [_add(_add(end, _mul(nr, -w * 0.9)), _mul(d, 10)),
            _add(_add(pts[-2], _mul(d, 18)), _mul(nr, -w * 0.25)),
            _add(_add(end, _mul(nr, w * 0.1)), _mul(d, 46)),
            _add(_add(pts[-2], _mul(d, 22)), _mul(nr, w * 0.55)),
            _add(_add(end, _mul(nr, w * 1.2)), _mul(d, 20))]
    return up + tips, dn


def _mane_shape(NG, t, wind, run, phase):
    """Mane as one mass: root line along the crest (poll->withers), free edge of pointed locks."""
    hf = NG["hf"]
    crest = [hf((8, -5))] + NG["crest"][::-1] + [NG["W"]]
    # resample crest polyline
    segl = [_len(_sub(crest[i + 1], crest[i])) for i in range(len(crest) - 1)]
    tot = sum(segl)
    def at(f):
        d = f * tot
        for i, l in enumerate(segl):
            if d <= l or i == len(segl) - 1:
                u = d / l if l else 0
                p = _lerp2(crest[i], crest[i + 1], min(u, 1.0))
                return p, _norm(_sub(crest[i + 1], crest[i]))
            d -= l
    n = 9
    roots, tips = [], []
    for i in range(n + 1):
        f = i / n
        p, tg = at(f * 0.96)
        down = _mul(_perp(tg), -1)   # tangent runs poll->withers; this points onto the neck side
        roots.append(_add(p, _mul(down, 4)))
    for i in range(n):
        f = (i + 0.5) / n
        p, tg = at(f * 0.96)
        up = (tg[1], -tg[0])
        flow = (fbm1(t * 2.4 + i * 0.63, 41) - 0.5) * 2
        L = (40 + 16 * math.sin(i * 2.1 + 0.5) + 14 * math.sin(f * 3.1)) * (0.85 if run else 1.0)
        if run:
            ang = _ang(tg) + R(-14 - 12 * wind) + R(10) * flow * wind + R(7) * math.sin(TAU * phase - i * 0.7)
            L *= 0.8 + 0.35 * wind
        else:
            ang = R(100) + R(12) * f + R(6) * flow
        tip = _add(p, _mul(_dir(ang), L))
        notch = _add(p, _mul(_dir(ang), L * 0.35))
        tips.append((tip, notch))
    edge = []
    for i in range(n - 1, -1, -1):
        tip, notch = tips[i]
        edge.append(tip)
        if i > 0:
            edge.append(_lerp2(notch, tips[i - 1][1], 0.5))
    return roots, edge


# ----------------------------------------------------------------------------- main draw
def draw_horse(ctx, x, y, scale, phase, *, facing=1, coat=PAL["harukaze"], mane=PAL["harukaze_mane"], blaze=True,
               socks=(False, False, True, False), jockey=None, gait="gallop", stride=1.0, mane_wind=1.0, t=0.0,
               rim=(0.75, 0.88, 1.0), rim_strength=0.8, shade=0.0, motion_blur=0.0, lean=0.0, head_up=0.0,
               rim_dir=(-0.55, -0.83), ground_shadow=0.35, number=None, saddlecloth=None, line_width=3.0,
               hoof_color=None, eye_open=1.0):
    """Draw a full horse. See module doc. Extra kwargs:
    rim_dir: screen-space direction TOWARD the rim light; ground_shadow: alpha of contact shadow (0 = none);
    number: saddle-cloth number (int/str) or None; saddlecloth: cloth colour (default white if number);
    line_width: ink width at scale 1; eye_open 0..1."""
    P = horse_pose(phase, gait, stride, t, head_up)
    run = gait != "stand"
    NG = _neck_geom(P, t, mane_wind)
    sh = clamp(shade)
    base = _col(coat, sh)
    shad = _col(_shadow_of(coat), sh)
    far_mul = (0.62, 0.60, 0.72)
    mane_c = _col(mane, sh)
    mane_s = _col(_shadow_of(mane), sh)
    ink = _col(INK, sh * 0.5)
    rs = rim_strength * (1 - sh * 0.85)
    rimc = mix_color(rim, (1, 1, 1), 0.2)
    lw = line_width
    white = _col((0.97, 0.95, 0.93), sh)
    hoofc = _col(hoof_color or (0.20, 0.16, 0.17), sh)
    hoof_light = _col((0.75, 0.68, 0.58), sh)

    ctx.save()
    ctx.translate(x, y)
    ctx.scale(scale * facing, scale)
    if lean:
        ctx.rotate(R(lean * 10.0))
    rdx, rdy = rim_dir[0] * facing, rim_dir[1]
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)

    # ground contact shadow
    if ground_shadow > 0:
        ctx.save()
        ctx.scale(1.0, 0.09)
        g = cairo.RadialGradient(10, 0, 0, 10, 0, 300)
        g.add_color_stop_rgba(0, 0, 0, 0.03, ground_shadow)
        g.add_color_stop_rgba(0.6, 0, 0, 0.03, ground_shadow * 0.5)
        g.add_color_stop_rgba(1, 0, 0, 0.03, 0)
        ctx.set_source(g); ctx.arc(10, 0, 300, 0, TAU); ctx.fill()
        ctx.restore()

    # speed streaks behind
    if motion_blur > 0 and run:
        _speed_streaks(ctx, P, t, motion_blur, mix_color(rim, base, 0.4), sh)

    # ghost legs (motion blur)
    if motion_blur > 0 and run:
        for k in (3, 2, 1):
            Pg = horse_pose((phase - k * 0.028) % 1.0 if gait != "burst" else max(0, phase - k * 0.01),
                            gait, stride, t, head_up)
            a = 0.16 * motion_blur * (1 - k / 4.0)
            for i in (0, 2, 1, 3):
                leg = Pg["legs"][i]
                fr, bk = _fore_shape(leg) if i < 2 else _hind_shape(leg)
                ctx.new_path(); _path_closed(ctx, fr, bk)
                _set(ctx, mix_color(base, rim, 0.3), a); ctx.fill()

    # far legs
    far_col = tuple(b * m for b, m in zip(base, far_mul))
    for i in (2, 0):
        _draw_leg(ctx, P["legs"][i], i < 2, far_col, _shadow_of(far_col), ink, lw, socks[1 if i == 0 else 3],
                  white, hoofc, hoof_light, rimc, rs * 0.35, (rdx, rdy), sh, far=True)

    # tail (behind body)
    tp = _tail_pts(P, t, mane_wind, gait, phase, stride)
    _draw_tail(ctx, tp, mane_c, mane_s, ink, lw, rimc, rs, (rdx, rdy), t)

    # far ear
    hf = NG["hf"]
    _draw_ear(ctx, hf, far=True, base=far_col, ink=ink, lw=lw, run=run, t=t)

    # ---- main union: silhouette + near legs
    sil = _silhouette(P, NG)
    ctx.new_path(); smooth_path(ctx, sil, closed=True, tension=0.55)
    sil_path = ctx.copy_path()
    nf_fr, nf_bk = _fore_shape(P["legs"][1])
    nh_fr, nh_bk = _hind_shape(P["legs"][3])
    ctx.new_path()
    smooth_path(ctx, sil, closed=True, tension=0.55)
    for fr, bk in ((nh_fr, nh_bk), (nf_fr, nf_bk)):
        pts = fr + bk[::-1]
        if (_signed_area(pts) > 0) != (_signed_area(sil) > 0):
            pts = pts[::-1]
        smooth_path(ctx, pts, closed=True, tension=0.5)
    union = ctx.copy_path()
    # base gradient
    lg = cairo.LinearGradient(0, -420, 0, 0)
    lg.add_color_stop_rgb(0, *mix_color(base, (1, 1, 1), 0.07))
    lg.add_color_stop_rgb(0.55, *base)
    lg.add_color_stop_rgb(1, *mix_color(base, shad, 0.35))
    ctx.new_path(); ctx.append_path(union); ctx.set_source(lg); ctx.fill()

    # markings: blaze + socks (clipped into union)
    ctx.save(); ctx.new_path(); ctx.append_path(union); ctx.clip()
    if blaze:
        bl = [(18, -12), (60, -13), (100, -8), (124, 6), (127, 22), (121, 27), (110, 16), (84, 3), (52, 1.5), (26, 3)]
        ctx.new_path(); smooth_path(ctx, [hf(p) for p in bl], closed=True, tension=0.5)
        _set(ctx, white); ctx.fill()
    for i, fr, bk in ((1, nf_fr, nf_bk), (3, nh_fr, nh_bk)):
        if socks[0 if i == 1 else 2]:
            _sock(ctx, P["legs"][i], i < 2, white)
    ctx.restore()

    # cel shadow (multiply): big vertical band on the body, narrow sideways band on the near legs
    mulc = (0.66, 0.58, 0.80)
    _band(ctx, sil_path, 7, -32, mulc, 1.0, cairo.OPERATOR_MULTIPLY)
    ctx.save()
    ctx.new_path(); ctx.rectangle(-3000, -3000, 6000, 6000); ctx.append_path(sil_path)
    ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD); ctx.clip(); ctx.set_fill_rule(cairo.FILL_RULE_WINDING)
    for fr, bk in ((nh_fr, nh_bk), (nf_fr, nf_bk)):
        ctx.new_path(); _path_closed(ctx, fr, bk)
        _band(ctx, ctx.copy_path(), 9, -7, mulc, 1.0, cairo.OPERATOR_MULTIPLY)
    ctx.restore()
    ctx.save(); ctx.new_path(); ctx.append_path(union); ctx.clip()
    _anatomy_shadows(ctx, P, NG, (0.74, 0.66, 0.84))
    ctx.restore()
    if rs > 0:
        _band(ctx, union, -rdx * 6.5, -rdy * 6.5, rimc, 0.85 * rs, union=True)

    # outline
    ctx.set_source_rgb(*ink); ctx.set_line_width(lw)
    ctx.new_path(); ctx.append_path(sil_path)
    ctx.save(); ctx.new_path()
    # stroke silhouette except where near legs cover: clip away leg interiors
    ctx.restore()
    ctx.new_path(); ctx.append_path(sil_path)
    ctx.save()
    _clip_out(ctx, [(nf_fr, nf_bk, 0.35), (nh_fr, nh_bk, 0.30)], sil_path)
    ctx.set_source_rgb(*ink); ctx.set_line_width(lw); ctx.stroke()
    ctx.restore()
    # near leg edges
    for fr, bk, cut in ((nh_fr, nh_bk, 2), (nf_fr, nf_bk, 1)):
        _stroke_leg_edges(ctx, fr, bk, cut, ink, lw)
    _anatomy_lines(ctx, P, NG, ink, lw)

    # hooves near
    for i in (3, 1):
        leg = P["legs"][i]
        sock = socks[0 if i == 1 else 2]
        _draw_hoof(ctx, leg, hoof_light if sock else hoofc, ink, lw)

    # head details
    _head_details(ctx, NG, base, shad, ink, lw, run, t, eye_open, sh)
    _draw_ear(ctx, hf, far=False, base=base, ink=ink, lw=lw, run=run, t=t, rim=(rimc, rs, (rdx, rdy)))
    # mane
    _draw_mane(ctx, NG, t, mane_wind, run, phase, mane_c, mane_s, ink, lw, rimc, rs, (rdx, rdy))

    # saddle cloth & jockey
    if jockey is not None:
        _draw_tack(ctx, P, NG, number, saddlecloth, ink, lw, sh, sil_path)
        _draw_jockey(ctx, P, NG, jockey, phase, t, ink, lw, rimc, rs, (rdx, rdy), sh, gait)
    elif number is not None:
        _draw_tack(ctx, P, NG, number, saddlecloth, ink, lw, sh, sil_path)

    ctx.restore()
    return P


def draw_horse_stand(ctx, x, y, scale, phase=0.0, **kw):
    kw.setdefault("gait", "stand")
    return draw_horse(ctx, x, y, scale, phase, **kw)


# ----------------------------------------------------------------------------- parts
def _speed_streaks(ctx, P, t, mb, col, sh):
    B = P["B"]
    ctx.save()
    for i in range(9):
        yy = -330 + i * 36 + (noise1(i * 3.1 + t * 3, 5) - 0.5) * 20
        x0 = -150 + (noise1(i * 1.7, 9)) * 60
        L = (180 + 260 * noise1(i * 2.3 + t * 5, 7)) * mb
        g = cairo.LinearGradient(x0, 0, x0 - L, 0)
        g.add_color_stop_rgba(0, col[0], col[1], col[2], 0.0)
        g.add_color_stop_rgba(0.2, col[0], col[1], col[2], 0.35 * mb)
        g.add_color_stop_rgba(1, col[0], col[1], col[2], 0)
        ctx.set_source(g)
        ctx.rectangle(x0 - L, yy, L, 2.0 + 3 * noise1(i * 5.1, 3))
        ctx.fill()
    ctx.restore()


def _clip_out(ctx, shapes, sil_path):
    """Clip to everything except the interior of the given leg shapes, but only below a cut along leg."""
    ctx.new_path()
    ctx.rectangle(-2000, -2000, 4000, 4000)
    for fr, bk, f in shapes:
        pts = fr + bk[::-1]
        if _signed_area(pts) > 0:
            pts = pts[::-1]
        # shrink slightly so silhouette line meets leg edge
        smooth_path(ctx, pts, closed=True, tension=0.5)
    ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    ctx.clip()
    ctx.set_fill_rule(cairo.FILL_RULE_WINDING)
    ctx.new_path(); ctx.append_path(sil_path)


def _stroke_leg_edges(ctx, fr, bk, cut, ink, lw):
    ctx.set_source_rgb(*ink); ctx.set_line_width(lw)
    ctx.new_path()
    pts = fr[cut:] + bk[::-1][:len(bk) - cut]
    smooth_path(ctx, pts, closed=False, tension=0.5)
    ctx.stroke()


def _draw_leg(ctx, leg, fore, base, shad, ink, lw, sock, white, hoofc, hoof_light, rimc, rs, rd, sh, far=False):
    fr, bk = _fore_shape(leg, far) if fore else _hind_shape(leg, far)
    ctx.new_path(); _path_closed(ctx, fr, bk)
    path = ctx.copy_path()
    _set(ctx, base); ctx.fill()
    if sock:
        ctx.save(); ctx.new_path(); ctx.append_path(path); ctx.clip()
        _sock(ctx, leg, fore, mix_color(white, (0.5, 0.5, 0.62), 0.45 if far else 0.0))
        ctx.restore()
    _band(ctx, path, 9, -7, (0.70, 0.62, 0.80), 1.0, cairo.OPERATOR_MULTIPLY)
    if rs > 0:
        _band(ctx, path, -rd[0] * 5, -rd[1] * 5, rimc, 0.7 * rs)
    ctx.new_path(); ctx.append_path(path)
    ctx.set_source_rgb(*ink); ctx.set_line_width(lw); ctx.stroke()
    _draw_hoof(ctx, leg, (hoof_light if sock else hoofc) if not far else
               tuple(c * 0.7 for c in (hoof_light if sock else hoofc)), ink, lw)


def _sock(ctx, leg, fore, white):
    j2, F, cr = leg["j2"], leg["F"], leg["cr"]
    top = _lerp2(j2, F, 0.45)
    d = _norm(_sub(F, j2)); n = _perp(d)
    pts = [_add(top, _mul(n, 30)), _add(_add(top, _mul(n, -30)), _mul(d, 8)),
           _add(cr, _mul(n, -40)), _add(_add(cr, _mul(d, 30)), _mul(n, -40)), _add(_add(cr, _mul(d, 30)), _mul(n, 40))]
    ctx.new_path()
    ctx.move_to(*pts[0])
    ctx.curve_to(*_lerp2(pts[0], pts[1], 0.3), *_add(_lerp2(pts[0], pts[1], 0.6), _mul(d, 10)), *pts[1])
    for p in pts[2:]:
        ctx.line_to(*p)
    ctx.close_path()
    _set(ctx, white); ctx.fill()


def _draw_hoof(ctx, leg, col, ink, lw):
    h = leg["hoof"]
    ctx.new_path()
    ctx.move_to(*h[0]); ctx.line_to(*h[1])
    ctx.curve_to(*_lerp2(h[1], h[2], 0.5), *h[2], *h[2])
    ctx.line_to(*h[3]); ctx.line_to(*h[4]); ctx.close_path()
    _set(ctx, col); ctx.fill_preserve()
    ctx.set_source_rgb(*ink); ctx.set_line_width(lw * 0.9); ctx.stroke()
    # hoof highlight
    ctx.new_path(); ctx.move_to(*_lerp2(h[4], h[0], 0.2)); ctx.line_to(*_lerp2(h[4], h[0], 0.7))
    ctx.set_source_rgba(1, 1, 1, 0.25); ctx.set_line_width(lw * 0.8); ctx.stroke()


def _anatomy_shadows(ctx, P, NG, mulc):
    """Hard-edged secondary cel shadows (behind the elbow, under jaw, gaskin, stifle)."""
    B = P["B"]; legs = P["legs"]; hf = NG["hf"]
    nf, nh = legs[1], legs[3]
    ctx.save()
    ctx.set_operator(cairo.OPERATOR_MULTIPLY)
    _set(ctx, mulc)
    # jowl / under jaw shadow
    ctx.new_path(); smooth_path(ctx, [hf(p) for p in [(70, 40), (46, 46), (27, 55), (9, 52), (-3, 40), (-7, 27), (8, 36), (30, 42), (55, 38)]], closed=True)
    ctx.fill()
    # throat under neck
    thr = hf((-7, 27)); ch = B.f(B_CHEST)
    ctx.new_path(); smooth_path(ctx, [thr, _lerp2(thr, ch, 0.5), ch, _add(ch, (-24, 6)), _add(_lerp2(thr, ch, 0.5), (-10, -10)), _add(thr, (-14, -6))], closed=True)
    ctx.fill()
    ctx.restore()


def _anatomy_lines(ctx, P, NG, ink, lw):
    B = P["B"]; legs = P["legs"]
    nf, nh = legs[1], legs[3]
    S = nf["root"]; E = nf["j1"]
    Hj, St, Hk = nh["root"], nh["j1"], nh["j2"]
    ctx.save()
    ctx.set_source_rgba(ink[0], ink[1], ink[2], 0.5)
    ctx.set_line_width(lw * 0.5)
    # scapula line (withers to point of shoulder)
    sc = B.f(B_SCAP)
    ctx.new_path(); smooth_path(ctx, [_add(sc, (-4, -18)), _lerp2(sc, S, 0.55), _add(S, (-8, 12))]); ctx.stroke()
    # elbow/triceps line
    ctx.new_path(); smooth_path(ctx, [_add(_lerp2(S, E, 0.3), (-40, -12)), _add(E, (-18, -18)), _add(E, (-10, 8))]); ctx.stroke()
    # ribs / girth hint
    g = B.f(B_GIRTH)
    ctx.new_path(); smooth_path(ctx, [_add(g, (-40, -70)), _add(g, (-58, -34)), _add(g, (-60, -8))]); ctx.stroke()
    # stifle / thigh line
    ctx.new_path(); smooth_path(ctx, [_add(Hj, (30, -26)), _add(Hj, (40, 10)), _add(St, (0, -14))]); ctx.stroke()
    # hamstring line
    bt = B.h(H_BUTT)
    ctx.new_path(); smooth_path(ctx, [_add(bt, (8, 8)), _lerp2(bt, Hk, 0.45), _add(_lerp2(St, Hk, 0.75), (8, -2))]); ctx.stroke()
    # hip point
    ctx.new_path(); ctx.arc(*_add(B.h((-118.0, -300.0)), (0, 0)), 9, R(200), R(330)); ctx.stroke()
    ctx.restore()


def _draw_tail(ctx, pts, c, cs, ink, lw, rimc, rs, rd, t):
    up, dn = _tail_shape(pts)
    ctx.new_path(); smooth_path(ctx, up + dn[::-1], closed=True, tension=0.42)
    path = ctx.copy_path()
    _set(ctx, c); ctx.fill()
    _band(ctx, path, 5, -12, (0.72, 0.62, 0.78), 1.0, cairo.OPERATOR_MULTIPLY)
    if rs > 0:
        _band(ctx, path, -rd[0] * 5, -rd[1] * 5, rimc, 0.8 * rs)
    ctx.new_path(); ctx.append_path(path)
    ctx.set_source_rgb(*ink); ctx.set_line_width(lw); ctx.stroke()
    # strand lines
    ctx.set_line_width(lw * 0.5)
    ctx.set_source_rgba(ink[0], ink[1], ink[2], 0.6)
    m = min(len(up), len(dn)) - 1
    for k in (0.3, 0.62):
        ln = [_lerp2(u, d, k) for u, d in zip(up[1:m], dn[1:m])]
        ln.append(up[m + (1 if k < 0.5 else 3)])
        ctx.new_path(); smooth_path(ctx, ln); ctx.stroke()


def _draw_ear(ctx, hf, far, base, ink, lw, run, t, rim=None):
    # ear in head frame: base at poll; pointing up/back (run) or forward (alert)
    if far:
        b0, b1, tipd = (14, -6), (2, -4), (-2, -46)
    else:
        b0, b1, tipd = (10, -7), (-6, -3), (-14, -48)
    tw = (fbm1(t * 0.8 + (3 if far else 0), 51) - 0.5) * 6
    tip = (tipd[0] + tw, tipd[1])
    mid0 = _lerp2(b0, tip, 0.5); mid0 = (mid0[0] + 7, mid0[1])
    mid1 = _lerp2(b1, tip, 0.5); mid1 = (mid1[0] - 6, mid1[1])
    pts = [hf(b0), hf(mid0), hf(tip), hf(mid1), hf(b1)]
    ctx.new_path(); smooth_path(ctx, pts, closed=True, tension=0.5)
    _set(ctx, base); ctx.fill_preserve()
    ctx.set_source_rgb(*ink); ctx.set_line_width(lw * 0.9); ctx.stroke()
    if not far:
        inner = [hf(_lerp2(b0, b1, 0.3)), hf(_lerp2(mid0, mid1, 0.35)), hf((tip[0] + 1, tip[1] + 8)), hf(_lerp2(mid0, mid1, 0.75))]
        ctx.new_path(); smooth_path(ctx, inner, closed=True)
        ctx.set_source_rgba(0.25, 0.12, 0.12, 0.6); ctx.fill()


def _head_details(ctx, NG, base, shad, ink, lw, run, t, eye_open, sh):
    hf = NG["hf"]
    # nostril
    ctx.new_path(); smooth_path(ctx, [hf((106, 12)), hf((113, 14)), hf((114, 21)), hf((109, 19))], closed=True)
    ctx.set_source_rgb(*mix_color(ink, base, 0.2)); ctx.fill()
    # mouth line
    ctx.new_path(); smooth_path(ctx, [hf((119, 29)), hf((110, 32)), hf((98, 32))])
    ctx.set_source_rgb(*ink); ctx.set_line_width(lw * 0.6); ctx.stroke()
    # cheek line
    ctx.new_path(); smooth_path(ctx, [hf((66, 30)), hf((46, 34)), hf((24, 32)), hf((12, 22))])
    ctx.set_source_rgba(ink[0], ink[1], ink[2], 0.6); ctx.set_line_width(lw * 0.5); ctx.stroke()
    # eye (almond, with catchlight)
    e = hf((36, 7))
    ha = NG["ha"]
    ctx.save(); ctx.translate(*e); ctx.rotate(ha - R(8))
    open_ = clamp(eye_open)
    ctx.new_path()
    ctx.move_to(-9, 0); ctx.curve_to(-4, -7 * open_, 5, -7 * open_, 9, -0.5); ctx.curve_to(5, 4 * open_, -4, 4 * open_, -9, 0)
    ctx.close_path()
    ctx.set_source_rgb(0.10, 0.05, 0.06); ctx.fill_preserve()
    ctx.set_source_rgb(*ink); ctx.set_line_width(lw * 0.7); ctx.stroke()
    if open_ > 0.3:
        ctx.arc(-2.5, -2.5, 2.4, 0, TAU); ctx.set_source_rgba(1, 1, 1, 0.95); ctx.fill()
        ctx.arc(3, 1.2, 1.0, 0, TAU); ctx.set_source_rgba(1, 1, 1, 0.6); ctx.fill()
    # lashes/brow
    ctx.new_path(); ctx.move_to(-11, -3); ctx.curve_to(-5, -11, 5, -11, 11, -4)
    ctx.set_source_rgba(ink[0], ink[1], ink[2], 0.7); ctx.set_line_width(lw * 0.5); ctx.stroke()
    ctx.restore()


def _draw_mane(ctx, NG, t, wind, run, phase, c, cs, ink, lw, rimc, rs, rd):
    roots, edge = _mane_shape(NG, t, wind, run, phase)
    hf = NG["hf"]
    pts = roots + edge
    ctx.new_path(); smooth_path(ctx, pts, closed=True, tension=0.35)
    path = ctx.copy_path()
    _set(ctx, c); ctx.fill()
    _band(ctx, path, 6, -12, (0.76, 0.66, 0.80), 1.0, cairo.OPERATOR_MULTIPLY)
    if rs > 0:
        _band(ctx, path, -rd[0] * 4.5, -rd[1] * 4.5, rimc, 0.8 * rs)
    ctx.new_path(); ctx.append_path(path)
    ctx.set_source_rgb(*ink); ctx.set_line_width(lw * 0.85); ctx.stroke()
    # inner strand lines
    ctx.set_source_rgba(ink[0], ink[1], ink[2], 0.55); ctx.set_line_width(lw * 0.45)
    for i in range(1, len(edge), 4):
        r = roots[min(len(roots) - 1, len(roots) - 1 - i // 2)]
        ctx.new_path(); ctx.move_to(*_lerp2(r, edge[i], 0.15)); ctx.line_to(*_lerp2(r, edge[i], 0.7)); ctx.stroke()
    # forelock
    if run:
        tip = (-16 + (fbm1(t * 2.5, 61) - 0.5) * 10, -24 - 4 * wind)
        fore = [hf((6, -9)), hf((22, -11)), hf((6, -16)), hf(tip), hf((-2, -6))]
    else:
        sw = (fbm1(t * 0.8, 61) - 0.5) * 5
        fore = [hf((4, -9)), hf((16, -12)), hf((42 + sw, -6)), hf((34, -1)), hf((12, -2))]
    ctx.new_path(); smooth_path(ctx, fore, closed=True, tension=0.45)
    _set(ctx, c); ctx.fill_preserve(); ctx.set_source_rgb(*ink); ctx.set_line_width(lw * 0.7); ctx.stroke()


def _draw_tack(ctx, P, NG, number, cloth, ink, lw, sh, clip=None):
    B = P["B"]
    ctx.save()
    if clip is not None:
        ctx.new_path(); ctx.append_path(clip); ctx.clip()
    cl = _col(cloth or (0.96, 0.96, 0.97), sh)
    pts = [B.f((48.0, -322.0)), B.f((-40.0, -316.0)), B.f((-52.0, -250.0)), B.f((-10.0, -244.0)), B.f((40.0, -250.0))]
    ctx.new_path(); smooth_path(ctx, pts, closed=True, tension=0.3)
    _set(ctx, cl); ctx.fill_preserve()
    ctx.set_source_rgb(*ink); ctx.set_line_width(lw * 0.8); ctx.stroke()
    if number is not None:
        c = B.f((-8.0, -283.0))
        ctx.save(); ctx.translate(*c)
        ctx.select_font_face("AnimeSans"); ctx.set_font_size(36)
        s = str(number)
        xb, yb, tw, th, xa, ya = ctx.text_extents(s)
        ctx.move_to(-xa / 2, th / 2)
        ctx.set_source_rgb(*_col((0.08, 0.08, 0.1), sh)); ctx.show_text(s)
        ctx.restore()
    # girth strap
    g0, g1 = B.f((30.0, -250.0)), B.f((34.0, -182.0))
    ctx.new_path(); ctx.move_to(*g0); ctx.line_to(*g1)
    ctx.set_source_rgb(*_col((0.22, 0.20, 0.26), sh)); ctx.set_line_width(12); ctx.stroke()
    # saddle
    sp = [B.f((40.0, -330.0)), B.f((-20.0, -326.0)), B.f((-24.0, -312.0)), B.f((34.0, -314.0))]
    ctx.new_path(); smooth_path(ctx, sp, closed=True, tension=0.3)
    ctx.set_source_rgb(*_col((0.12, 0.10, 0.12), sh)); ctx.fill()
    ctx.restore()


# ----------------------------------------------------------------------------- jockey
def _draw_jockey(ctx, P, NG, J, phase, t, ink, lw, rimc, rs, rd, sh, gait):
    B = P["B"]
    silk = _col(J.get("silk", (0.9, 0.9, 0.9)), sh)
    acc = _col(J.get("accent", (0.9, 0.1, 0.2)), sh)
    capc = _col(J.get("cap", acc), sh)
    crouch = clamp(J.get("crouch", 1.0))
    push = clamp(J.get("push", 0.0))
    breech = _col((0.95, 0.95, 0.97), sh)
    boot = _col((0.08, 0.07, 0.09), sh)
    skin = _col(PAL["skin"], sh)
    hair = _col(J.get("hair", (0.14, 0.10, 0.08)), sh)

    ph = TAU * phase if gait != "stand" else 0.0
    bob = math.sin(ph - 0.8)
    # damped rider anchor: follows withers but with reduced pitch/vert motion
    sad = B.f(B_SADDLE)
    rest = (B_SADDLE[0], B_SADDLE[1])
    anchor = (lerp(rest[0], sad[0], 0.6), lerp(rest[1], sad[1], 0.45))
    foot = B.f((24.0 - 6 * (1 - crouch), lerp(-222.0, -262.0, crouch)))
    hip = _add(anchor, (lerp(-6, -34, crouch) + push * 6 * math.sin(ph), lerp(-30, -46, crouch) + 3 * bob * crouch))
    ta = R(lerp(55, 7, crouch) + push * 5 * math.sin(ph + 0.5))
    sho = _add(hip, (96 * math.cos(ta), -96 * math.sin(ta)))
    head = _add(sho, (lerp(12, 28, crouch), lerp(-40, -22, crouch)))
    # hands on neck
    crest = NG["crest"]
    hand_base = _add(_lerp2(crest[0], crest[1], 0.6), (6, 24))
    hp = push * 20 * math.sin(ph + 1.2)
    nv = _norm(_sub(crest[2], crest[0]))
    hand = _add(hand_base, _mul(nv, hp))
    if crouch < 0.5:
        hand = _lerp2(_add(hand_base, (-40, 10)), hand, crouch * 2)
    knee, foot2 = _ik2(hip, foot, 80, 82, -1)
    elbow, hand2 = _ik2(sho, hand, 56, 54, 1)
    far_sho = _add(sho, (-6, -4))
    far_elbow, far_hand = _ik2(far_sho, _add(hand, (8, -6)), 56, 54, 1)

    # reins from hands to bit
    hf = NG["hf"]
    bit = hf((104, 32))
    ctx.new_path(); ctx.move_to(*hand2)
    ctx.curve_to(*_lerp2(hand2, bit, 0.4), *_add(_lerp2(hand2, bit, 0.7), (0, 6)), *bit)
    ctx.set_source_rgb(*_col((0.25, 0.10, 0.08), sh)); ctx.set_line_width(2.5); ctx.stroke()
    # bridle on head
    _bridle(ctx, hf, ink, lw, sh)

    def limb(pts, widths, col, outline=True, alpha=1.0):
        fr, bk = _limb_outline(pts, [(w, w) for w in widths])
        ctx.new_path(); smooth_path(ctx, fr + bk[::-1], closed=True, tension=0.5)
        path = ctx.copy_path()
        _set(ctx, col, alpha); ctx.fill()
        _band(ctx, path, 4, -9, (0.72, 0.66, 0.82), 1.0, cairo.OPERATOR_MULTIPLY)
        if rs > 0:
            _band(ctx, path, -rd[0] * 3.5, -rd[1] * 3.5, rimc, 0.75 * rs)
        if outline:
            ctx.new_path(); ctx.append_path(path)
            ctx.set_source_rgb(*ink); ctx.set_line_width(lw * 0.8); ctx.stroke()
        return path

    # far arm
    limb([far_sho, far_elbow, far_hand], [9, 8, 6], tuple(c * 0.7 for c in silk))
    # torso (silk)
    back_mid = _add(_lerp2(hip, sho, 0.5), _mul(_perp(_norm(_sub(sho, hip))), -22))
    chest_mid = _add(_lerp2(hip, sho, 0.55), _mul(_perp(_norm(_sub(sho, hip))), 14))
    tv = _norm(_sub(sho, hip)); tn = _perp(tv)
    torso = [_add(hip, _mul(tn, -18)), back_mid, _add(sho, _mul(tn, -16)), _add(sho, _mul(tv, 14)),
             _add(sho, _mul(tn, 14)), chest_mid, _add(hip, _mul(tn, 16)), _add(hip, _mul(tv, -14))]
    ctx.new_path(); smooth_path(ctx, torso, closed=True, tension=0.55)
    tpath = ctx.copy_path()
    _set(ctx, silk); ctx.fill()
    # sash (diagonal)
    ctx.save(); ctx.new_path(); ctx.append_path(tpath); ctx.clip()
    s0 = _add(sho, _mul(tn, -18)); s1 = _add(_lerp2(hip, sho, 0.15), _mul(tn, 20))
    sd = _norm(_sub(s1, s0)); sn = _perp(sd)
    ctx.new_path()
    for p in (_add(s0, _mul(sn, -9)), _add(s0, _mul(sn, 9)), _add(s1, _mul(sn, 9)), _add(s1, _mul(sn, -9))):
        ctx.line_to(*p)
    ctx.close_path(); _set(ctx, acc); ctx.fill()
    ctx.restore()
    _band(ctx, tpath, 5, -14, (0.72, 0.66, 0.84), 1.0, cairo.OPERATOR_MULTIPLY)
    if rs > 0:
        _band(ctx, tpath, -rd[0] * 4.5, -rd[1] * 4.5, rimc, 0.85 * rs)
    ctx.new_path(); ctx.append_path(tpath); ctx.set_source_rgb(*ink); ctx.set_line_width(lw * 0.85); ctx.stroke()
    # thigh (breeches) + shin (boot)
    limb([_add(hip, _mul(tn, 4)), _lerp2(hip, knee, 0.5), knee], [17, 14, 11], breech)
    bt = limb([knee, _lerp2(knee, foot2, 0.5), foot2], [11, 9, 7.5], boot)
    # boot cuff
    cuff = _lerp2(knee, foot2, 0.22)
    cv = _perp(_norm(_sub(foot2, knee)))
    ctx.new_path(); ctx.move_to(*_add(cuff, _mul(cv, 11))); ctx.line_to(*_add(cuff, _mul(cv, -11)))
    ctx.set_source_rgb(*_col((0.72, 0.48, 0.28), sh)); ctx.set_line_width(5); ctx.stroke()
    # foot + stirrup
    fdir = _norm(_sub(foot2, knee))
    toe = _add(foot2, (16, 2))
    ctx.new_path(); smooth_path(ctx, [_add(foot2, (-8, -6)), _add(toe, (2, -4)), _add(toe, (2, 4)), _add(foot2, (-8, 6))], closed=True)
    _set(ctx, boot); ctx.fill()
    st_top = B.f((20.0, -318.0))
    ctx.new_path(); ctx.move_to(*st_top); ctx.line_to(*_add(foot2, (2, 4)))
    ctx.set_source_rgb(*_col((0.18, 0.14, 0.12), sh)); ctx.set_line_width(2.5); ctx.stroke()
    ctx.new_path(); ctx.arc(*_add(foot2, (4, 8)), 6, 0, TAU)
    ctx.set_source_rgb(*_col((0.78, 0.80, 0.85), sh)); ctx.set_line_width(2.2); ctx.stroke()

    # ponytail
    if J.get("ponytail", False):
        hb = _add(head, (-18, 6))
        pts = [hb]
        a = R(172)
        cur = hb
        for i in range(5):
            f = (i + 1) / 5
            aa = a + R(10) * f + (fbm1(t * 3.2 - f * 1.5, 71) - 0.5) * R(40) * f + R(8) * math.sin(ph - f * 2)
            cur = _add(cur, _mul(_dir(aa), 13))
            pts.append(cur)
        up, dn = [], []
        wd = [5, 7, 7, 6, 4, 0.5]
        for i, p in enumerate(pts):
            d = _norm(_sub(pts[min(i + 1, 5)], pts[max(i - 1, 0)])); n = _perp(d)
            up.append(_sub(p, _mul(n, wd[i]))); dn.append(_add(p, _mul(n, wd[i])))
        ctx.new_path(); smooth_path(ctx, up + dn[::-1], closed=True)
        _set(ctx, hair); ctx.fill_preserve(); ctx.set_source_rgb(*ink); ctx.set_line_width(lw * 0.6); ctx.stroke()
    # head: face + helmet + goggles
    _jockey_head(ctx, head, crouch, capc, J.get("cap_star", False), skin, ink, lw, rimc, rs, rd, sh, J.get("face"))
    # near arm (sleeve with accent stripes)
    ap = limb([sho, elbow, hand2], [11, 9.5, 7], silk)
    ctx.save(); ctx.new_path(); ctx.append_path(ap); ctx.clip()
    for f in (0.32, 0.72):
        c = _lerp2(sho, elbow, f) if f < 0.5 else _lerp2(elbow, hand2, f - 0.35)
        d = _norm(_sub(elbow, sho)) if f < 0.5 else _norm(_sub(hand2, elbow))
        n = _perp(d)
        ctx.new_path(); ctx.move_to(*_add(c, _mul(n, 14))); ctx.line_to(*_add(c, _mul(n, -14)))
        _set(ctx, acc); ctx.set_line_width(6); ctx.stroke()
    ctx.restore()
    ctx.new_path(); ctx.append_path(ap); ctx.set_source_rgb(*ink); ctx.set_line_width(lw * 0.8); ctx.stroke()
    # glove
    ctx.new_path(); ctx.arc(*hand2, 7.5, 0, TAU)
    _set(ctx, _col((0.95, 0.95, 0.95), sh)); ctx.fill_preserve(); ctx.set_source_rgb(*ink); ctx.set_line_width(lw * 0.7); ctx.stroke()
    if J.get("whip"):
        wa = R(-120 + 25 * math.sin(ph))
        ctx.new_path(); ctx.move_to(*hand2); ctx.line_to(*_add(hand2, _mul(_dir(wa), 70)))
        ctx.set_source_rgb(*ink); ctx.set_line_width(3); ctx.stroke()


def _jockey_head(ctx, c, crouch, capc, star, skin, ink, lw, rimc, rs, rd, sh, face):
    ctx.save(); ctx.translate(*c)
    # face/jaw below helmet
    ctx.new_path(); smooth_path(ctx, [(-14, 0), (2, -4), (17, 2), (20, 10), (16, 17), (6, 19), (-6, 14)], closed=True)
    _set(ctx, skin); ctx.fill_preserve(); ctx.set_source_rgb(*ink); ctx.set_line_width(lw * 0.7); ctx.stroke()
    # mouth
    ctx.new_path()
    if face == "shout":
        ctx.arc(13, 13, 3.2, 0, TAU); ctx.set_source_rgb(0.35, 0.08, 0.1); ctx.fill()
    else:
        ctx.move_to(10, 14); ctx.line_to(16, 13); ctx.set_source_rgb(*ink); ctx.set_line_width(1.4); ctx.stroke()
    # helmet dome
    ctx.new_path(); smooth_path(ctx, [(-22, 4), (-24, -12), (-12, -26), (6, -28), (20, -18), (24, -6), (22, 0)], closed=True)
    hp = ctx.copy_path()
    _set(ctx, capc); ctx.fill()
    if star:
        ctx.save(); ctx.translate(-2, -14); ctx.new_path()
        for k in range(10):
            r = 8.5 if k % 2 == 0 else 3.6
            a = -math.pi / 2 + k * math.pi / 5
            ctx.line_to(r * math.cos(a), r * math.sin(a))
        ctx.close_path(); ctx.set_source_rgb(*_col((0.98, 0.98, 1.0), sh)); ctx.fill()
        ctx.restore()
    _band(ctx, hp, 3, -7, (0.72, 0.64, 0.80), 1.0, cairo.OPERATOR_MULTIPLY)
    if rs > 0:
        _band(ctx, hp, -rd[0] * 3, -rd[1] * 3, rimc, 0.9 * rs)
    ctx.new_path(); ctx.append_path(hp); ctx.set_source_rgb(*ink); ctx.set_line_width(lw * 0.8); ctx.stroke()
    # peak
    ctx.new_path(); smooth_path(ctx, [(18, -6), (32, -3), (30, 0), (18, 0)], closed=True)
    _set(ctx, capc); ctx.fill_preserve(); ctx.set_source_rgb(*ink); ctx.set_line_width(lw * 0.7); ctx.stroke()
    # goggles
    ctx.new_path(); ctx.move_to(-22, 0); ctx.line_to(8, 1)
    ctx.set_source_rgb(0.1, 0.1, 0.12); ctx.set_line_width(4); ctx.stroke()
    ctx.new_path(); smooth_path(ctx, [(7, -3), (19, -3), (22, 3), (18, 7), (8, 6)], closed=True)
    ctx.set_source_rgb(0.12, 0.18, 0.28); ctx.fill_preserve(); ctx.set_source_rgb(*ink); ctx.set_line_width(lw * 0.7); ctx.stroke()
    ctx.new_path(); ctx.move_to(11, -1); ctx.line_to(16, -1)
    ctx.set_source_rgba(0.8, 0.95, 1.0, 0.9); ctx.set_line_width(2); ctx.stroke()
    ctx.restore()


def _bridle(ctx, hf, ink, lw, sh):
    col = _col((0.20, 0.10, 0.08), sh)
    ctx.set_source_rgb(*col); ctx.set_line_width(3.2)
    # cheekpiece: from behind ears down to bit
    ctx.new_path(); smooth_path(ctx, [hf((6, -6)), hf((12, 12)), hf((60, 26)), hf((104, 32))]); ctx.stroke()
    # noseband
    ctx.new_path(); smooth_path(ctx, [hf((84, -3)), hf((86, 18)), hf((88, 40))]); ctx.stroke()
    # browband
    ctx.new_path(); ctx.move_to(*hf((10, -9))); ctx.line_to(*hf((22, -7))); ctx.stroke()
    # throatlatch
    ctx.new_path(); smooth_path(ctx, [hf((10, 8)), hf((0, 28)), hf((-6, 36))]); ctx.stroke()
    # bit ring
    ctx.new_path(); ctx.arc(*hf((104, 32)), 4.5, 0, TAU)
    ctx.set_source_rgb(*_col((0.85, 0.86, 0.9), sh)); ctx.set_line_width(2.0); ctx.stroke()


# ----------------------------------------------------------------------------- head close-up
def draw_horse_head(ctx, x, y, scale, *, facing=-1, coat=PAL["harukaze"], mane=PAL["harukaze_mane"], blaze=True,
                    blink=0.0, ear=0.0, nostril=0.0, look=(0.0, 0.0), mouth=0.0, t=0.0, light=(1.0, 0.78, 0.45),
                    rim_strength=0.8, bridle=True, nuzzle=0.0, line_width=3.0, shade=0.0):
    _draw_head_closeup(ctx, x, y, scale, facing=facing, coat=coat, mane=mane, blaze=blaze, blink=blink, ear=ear,
                       nostril=nostril, look=look, mouth=mouth, t=t, light=light, rim_strength=rim_strength,
                       bridle=bridle, nuzzle=nuzzle, lw=line_width, shade=shade)


# head frame profile (poll origin, +x toward muzzle, +y toward jaw), head length ~300
HC_FRONT = [(-4, -14), (30, -24), (80, -25), (140, -20), (200, -11), (246, -1), (276, 14), (293, 34), (299, 58),
            (293, 78), (276, 86)]
HC_JAW = [(268, 97), (252, 106), (226, 104), (190, 104), (150, 114), (112, 138), (74, 156), (38, 150), (14, 128),
          (2, 100), (-6, 76)]
HC_BACK = [(-30, 60), (-34, 10)]      # hidden inside the neck


def _draw_head_closeup(ctx, x, y, scale, *, facing=-1, coat, mane, blaze, blink, ear, nostril, look, mouth, t,
                       light, rim_strength, bridle, nuzzle, lw, shade):
    sh = clamp(shade)
    base = _col(coat, sh)
    mane_c = _col(mane, sh)
    ink = _col(INK, sh * 0.5)
    white = _col((0.98, 0.96, 0.93), sh)
    rimc = mix_color(light, (1, 1, 1), 0.25)
    rs = rim_strength * (1 - sh * 0.8)
    mulc = (0.70, 0.56, 0.66)            # warm-violet multiply shadow
    breath = math.sin(t * TAU / 3.6)

    ctx.save()
    ctx.translate(x, y)
    ctx.scale(scale * (1 if facing >= 0 else -1), scale)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND); ctx.set_line_cap(cairo.LINE_CAP_ROUND)

    nz = clamp(nuzzle)
    sway = (fbm1(t * 0.35, 81) - 0.5) * 2
    poll = (40 + 30 * nz + 4 * sway, -468 + 40 * nz + 2 * breath)
    ha = R(56 + 16 * nz + 2 * sway)
    hf = _head_frame(poll, ha, 1.18)
    # neck
    nb_back, nb_front = (-200.0, 8.0), (118.0, 8.0)
    nb_back, nb_front = (-185.0, 8.0), (100.0, 8.0)
    crest = [hf((-8, -16)), (poll[0] - 70, poll[1] + 30), (poll[0] - 150, poll[1] + 130), (-182, -170), nb_back]
    throat = [hf((12, 112)), (-12 + 10 * nz, -262 + 20 * nz), (34, -120), nb_front]
    neck_pts = [nb_back] + crest[::-1][1:] + [hf((40, -10)), hf((0, 60))] + throat + [(nb_front[0], 60), (nb_back[0], 60)]
    ctx.new_path(); smooth_path(ctx, crest[::-1] + [hf((60, 40)), hf((10, 118))] + throat[1:] + [(118, 60), (-200, 60)],
                                closed=True, tension=0.5)
    neck_path = ctx.copy_path()
    grad = cairo.LinearGradient(0, -640, 0, 0)
    grad.add_color_stop_rgb(0, *mix_color(base, (1, 0.9, 0.75), 0.10))
    grad.add_color_stop_rgb(0.55, *base)
    grad.add_color_stop_rgb(1, *mix_color(base, (0.25, 0.1, 0.12), 0.35))

    # far ear (behind)
    ea = R(-18 * ear)
    def ear_pts(b0, b1, L, lean, far):
        tip = (b0[0] - L * math.sin(R(lean) + ea) * 0.6 - 10, b0[1] - L * math.cos(R(lean) + ea))
        m0 = _add(_lerp2(b0, tip, 0.5), (14, 0)); m1 = _add(_lerp2(b1, tip, 0.5), (-12, 4))
        return [b0, m0, tip, m1, b1], tip
    far_ear, _ = ear_pts((34, -26), (14, -18), 92, 8 + 6 * math.sin(t * 0.7), True)
    ctx.new_path(); smooth_path(ctx, [hf(p) for p in far_ear], closed=True, tension=0.45)
    _set(ctx, tuple(c * 0.72 for c in base)); ctx.fill_preserve()
    ctx.set_source_rgb(*ink); ctx.set_line_width(lw); ctx.stroke()

    # neck fill + shading
    ctx.new_path(); ctx.append_path(neck_path); ctx.set_source(grad); ctx.fill()
    _band(ctx, neck_path, 30, -40, mulc, 1.0, cairo.OPERATOR_MULTIPLY)
    # jowl cast shadow on the neck
    ctx.save(); ctx.new_path(); ctx.append_path(neck_path); ctx.clip()
    ctx.new_path(); smooth_path(ctx, [hf(p) for p in [(170, 130), (110, 168), (60, 190), (10, 170), (-30, 120), (-40, 60), (60, 60)]], closed=True)
    ctx.set_operator(cairo.OPERATOR_MULTIPLY); _set(ctx, mulc); ctx.fill()
    ctx.restore()
    if rs > 0:
        _band(ctx, neck_path, 6, 7, rimc, 0.85 * rs)
    ctx.new_path(); smooth_path(ctx, crest[::-1], tension=0.5)
    ctx.set_source_rgb(*ink); ctx.set_line_width(lw); ctx.stroke()
    ctx.new_path(); smooth_path(ctx, throat, tension=0.5); ctx.stroke()
    # neck muscle line
    ctx.set_source_rgba(ink[0], ink[1], ink[2], 0.45); ctx.set_line_width(lw * 0.6)
    ctx.new_path(); smooth_path(ctx, [(poll[0] - 90, poll[1] + 120), (-70, -250), (-40, -60)]); ctx.stroke()

    # head
    head_pts = [hf(p) for p in HC_FRONT + HC_JAW + HC_BACK]
    ctx.new_path(); smooth_path(ctx, head_pts, closed=True, tension=0.5)
    head_path = ctx.copy_path()
    ctx.set_source(grad); ctx.fill()
    ctx.save(); ctx.new_path(); ctx.append_path(head_path); ctx.clip()
    # front plane (3/4 cue): slightly lighter band along the face front
    fp = [hf(p) for p in [(20, -26), (140, -22), (246, -3), (282, 22), (262, 30), (200, 14), (120, 8), (40, 6)]]
    ctx.new_path(); smooth_path(ctx, fp, closed=True); _set(ctx, mix_color(base, (1, 0.92, 0.8), 0.12)); ctx.fill()
    if blaze:
        bl = [(34, -30), (90, -32), (160, -26), (230, -12), (272, 6), (300, 30), (304, 62), (296, 84),
              (282, 80), (284, 52), (262, 26), (212, 12), (150, 6), (104, 2), (72, -4), (46, -6)]
        ctx.new_path(); smooth_path(ctx, [hf(p) for p in bl], closed=True, tension=0.5)
        _set(ctx, white); ctx.fill()
    # soft muzzle (pink-grey skin)
    mz = [(250, 20), (282, 12), (310, 50), (300, 100), (256, 110), (236, 80), (240, 40)]
    ctx.new_path(); smooth_path(ctx, [hf(p) for p in mz], closed=True)
    g = cairo.RadialGradient(*hf((282, 58)), 5, *hf((276, 60)), 52)
    mzc = _col((0.96, 0.76, 0.68), sh)
    g.add_color_stop_rgba(0, *mzc, 0.95); g.add_color_stop_rgba(0.7, *mzc, 0.75); g.add_color_stop_rgba(1, *mzc, 0.0)
    ctx.set_source(g); ctx.fill()
    ctx.restore()
    # head cel shadow + extra shadows
    _band(ctx, head_path, 22, -34, mulc, 1.0, cairo.OPERATOR_MULTIPLY)
    ctx.save(); ctx.new_path(); ctx.append_path(head_path); ctx.clip()
    ctx.set_operator(cairo.OPERATOR_MULTIPLY); _set(ctx, (0.84, 0.74, 0.80))
    # eye socket / below-eye hollow
    ctx.new_path(); smooth_path(ctx, [hf(p) for p in [(46, 30), (80, 46), (120, 44), (150, 30), (120, 58), (76, 64)]], closed=True); ctx.fill()
    ctx.restore()
    # warm lamp glow on forehead
    gx, gy = hf((110, -10))
    ctx.save(); ctx.new_path(); ctx.append_path(head_path); ctx.clip()
    gg = cairo.RadialGradient(gx, gy, 0, gx, gy, 170)
    gg.add_color_stop_rgba(0, *light, 0.22 * (1 - sh)); gg.add_color_stop_rgba(1, *light, 0)
    ctx.set_source(gg); ctx.paint()
    ctx.restore()
    if rs > 0:
        _band(ctx, head_path, 5, 8, rimc, 0.9 * rs)
    # head contour (not the hidden back edge)
    ctx.new_path(); smooth_path(ctx, [hf(p) for p in HC_FRONT + HC_JAW], tension=0.5)
    ctx.set_source_rgb(*ink); ctx.set_line_width(lw * 1.1); ctx.stroke()

    # cheek (masseter) line, chin line, lines on muzzle
    ctx.set_source_rgba(ink[0], ink[1], ink[2], 0.55); ctx.set_line_width(lw * 0.6)
    ctx.new_path(); smooth_path(ctx, [hf((170, 70)), hf((140, 96)), hf((96, 118)), hf((50, 116)), hf((26, 92))]); ctx.stroke()
    ctx.new_path(); smooth_path(ctx, [hf((230, 90)), hf((250, 96)), hf((262, 94))]); ctx.stroke()
    # nostril
    fl = clamp(nostril)
    ns = [(262, 30 - 3 * fl), (280, 28 - 4 * fl), (290, 40), (286, 54 + 4 * fl), (276, 50), (274, 40)]
    ctx.new_path(); smooth_path(ctx, [hf(p) for p in ns], closed=True, tension=0.5)
    ctx.set_source_rgb(*mix_color(ink, (0.4, 0.2, 0.2), 0.3)); ctx.fill()
    ctx.new_path(); smooth_path(ctx, [hf((256, 26 - 4 * fl)), hf((270, 18 - 5 * fl)), hf((290, 26))])
    ctx.set_source_rgb(*ink); ctx.set_line_width(lw * 0.7); ctx.stroke()
    # mouth / lips
    m = clamp(mouth)
    ctx.new_path(); smooth_path(ctx, [hf((296, 76)), hf((284, 82 + 4 * m)), hf((262, 84 + 5 * m)), hf((246, 80))])
    ctx.set_source_rgb(*ink); ctx.set_line_width(lw * 0.8); ctx.stroke()
    if m > 0.05:
        ctx.new_path(); smooth_path(ctx, [hf((288, 80)), hf((276, 84 + 12 * m)), hf((258, 88 + 10 * m)), hf((262, 84))], closed=True)
        ctx.set_source_rgb(*_col((0.45, 0.22, 0.24), sh)); ctx.fill()
    # whisker dots
    ctx.set_source_rgba(ink[0], ink[1], ink[2], 0.5)
    for p in ((270, 66), (262, 72), (278, 70), (254, 62)):
        ctx.new_path(); ctx.arc(*hf(p), 1.6, 0, TAU); ctx.fill()

    # eye
    _closeup_eye(ctx, hf, ha, blink, look, ink, lw, sh, light)

    # halter
    if bridle:
        _halter(ctx, hf, ink, lw, sh)

    # near ear
    near_ear, tip = ear_pts((2, -16), (-26, -4), 100, -4 + 5 * math.sin(t * 0.9 + 1), False)
    ctx.new_path(); smooth_path(ctx, [hf(p) for p in near_ear], closed=True, tension=0.45)
    ep = ctx.copy_path()
    ctx.set_source(grad); ctx.fill()
    inner = [_lerp2(near_ear[0], near_ear[4], 0.25), _lerp2(near_ear[1], near_ear[3], 0.35), _add(near_ear[2], (4, 16)),
             _lerp2(near_ear[1], near_ear[3], 0.8), _lerp2(near_ear[0], near_ear[4], 0.8)]
    ctx.new_path(); smooth_path(ctx, [hf(p) for p in inner], closed=True, tension=0.45)
    ctx.set_source_rgba(*_col((0.35, 0.16, 0.14), sh), 0.75); ctx.fill()
    ctx.new_path(); smooth_path(ctx, [hf(_add(p, (0, 6))) for p in inner[1:4]]); ctx.set_source_rgba(*mane_c, 0.7); ctx.set_line_width(lw * 0.8); ctx.stroke()
    if rs > 0:
        _band(ctx, ep, 4, 6, rimc, 0.8 * rs)
    ctx.new_path(); ctx.append_path(ep); ctx.set_source_rgb(*ink); ctx.set_line_width(lw); ctx.stroke()

    # mane on neck (near side, draped) + forelock
    _closeup_mane(ctx, crest, hf, t, mane_c, ink, lw, rimc, rs, sh)
    ctx.restore()


def _closeup_eye(ctx, hf, ha, blink, look, ink, lw, sh, light):
    c = hf((88, 16))
    ctx.save(); ctx.translate(*c); ctx.rotate(ha - R(62))
    b = clamp(blink)
    w, hgt = 33.0, 24.0
    # socket shadow
    ctx.new_path(); ctx.save(); ctx.scale(1.0, 0.72); ctx.arc(0, 0, w + 9, 0, TAU); ctx.restore()
    ctx.set_operator(cairo.OPERATOR_MULTIPLY); ctx.set_source_rgba(0.80, 0.66, 0.72, 1.0); ctx.fill()
    ctx.set_operator(cairo.OPERATOR_OVER)
    top = -hgt * (1 - b) + hgt * 0.35 * b
    # eye white/iris region
    def eye_shape():
        ctx.new_path(); ctx.move_to(-w, 2)
        ctx.curve_to(-w * 0.55, top * 1.05, w * 0.45, top * 1.1, w, -2 + 2 * b)
        ctx.curve_to(w * 0.5, hgt * 0.7, -w * 0.5, hgt * 0.75, -w, 2)
        ctx.close_path()
    if b < 0.95:
        eye_shape(); ctx.save(); ctx.clip()
        ctx.set_source_rgb(0.20, 0.10, 0.08); ctx.paint()
        lx, ly = look[0] * 7, look[1] * 4
        ir = cairo.RadialGradient(lx - 3, ly - 4, 1, lx, ly, 19)
        ir.add_color_stop_rgb(0, 0.42, 0.24, 0.14); ir.add_color_stop_rgb(0.6, 0.22, 0.11, 0.07); ir.add_color_stop_rgb(1, 0.08, 0.04, 0.04)
        ctx.new_path(); ctx.arc(lx, ly, 19, 0, TAU); ctx.set_source(ir); ctx.fill()
        ctx.new_path(); ctx.save(); ctx.translate(lx, ly + 1); ctx.scale(1.0, 0.45); ctx.arc(0, 0, 10, 0, TAU); ctx.restore()
        ctx.set_source_rgb(0.03, 0.02, 0.03); ctx.fill()
        # reflected lamp: warm lower glow
        ctx.new_path(); ctx.save(); ctx.translate(lx + 4, ly + 10); ctx.scale(1.6, 0.6); ctx.arc(0, 0, 8, 0, TAU); ctx.restore()
        ctx.set_source_rgba(*light, 0.45); ctx.fill()
        # catchlights
        ctx.new_path(); ctx.save(); ctx.translate(lx - 8, ly - 7); ctx.rotate(-0.4); ctx.scale(1.3, 1.0); ctx.arc(0, 0, 5.5, 0, TAU); ctx.restore()
        ctx.set_source_rgba(1, 1, 1, 0.97); ctx.fill()
        ctx.new_path(); ctx.arc(lx + 8, ly + 4, 2.4, 0, TAU); ctx.set_source_rgba(1, 1, 1, 0.8); ctx.fill()
        # upper lid shadow on eyeball
        ctx.new_path(); ctx.move_to(-w, 2); ctx.curve_to(-w * 0.55, top * 1.05, w * 0.45, top * 1.1, w, -2)
        ctx.line_to(w, top + 8); ctx.curve_to(w * 0.4, top + 9, -w * 0.5, top + 9, -w, 8); ctx.close_path()
        ctx.set_source_rgba(0, 0, 0, 0.35); ctx.fill()
        ctx.restore()
    # upper lid line (thick) + lashes
    ctx.new_path(); ctx.move_to(-w - 3, 3)
    ctx.curve_to(-w * 0.55, top * 1.05 - 1, w * 0.45, top * 1.1 - 1, w + 2, -2 + 2 * b)
    ctx.set_source_rgb(*ink); ctx.set_line_width(lw * 1.5); ctx.stroke()
    ctx.set_line_width(lw * 0.8)
    for k, f in enumerate((0.2, 0.42, 0.62, 0.8)):
        # point on upper lid
        px = lerp(-w, w, f); py = top * 1.05 * (1 - (2 * f - 1) ** 2) * 0.95 + lerp(2, -2, f)
        dx, dy = (-6 - 5 * f, -8 + 12 * b) if b < 0.5 else (-6 - 4 * f, 8)
        ctx.new_path(); ctx.move_to(px, py); ctx.curve_to(px - 2, py + dy * 0.6, px + dx * 0.6, py + dy, px + dx, py + dy)
        ctx.stroke()
    # lower lid (thin) when open
    if b < 0.9:
        ctx.new_path(); ctx.move_to(-w * 0.8, 6); ctx.curve_to(-w * 0.4, hgt * 0.75, w * 0.4, hgt * 0.7, w * 0.8, 3)
        ctx.set_source_rgba(ink[0], ink[1], ink[2], 0.6); ctx.set_line_width(lw * 0.6); ctx.stroke()
    # lid crease / brow
    ctx.new_path(); ctx.move_to(-w * 0.8, top - 8); ctx.curve_to(-w * 0.3, top - 16, w * 0.4, top - 16, w * 0.9, top - 6)
    ctx.set_source_rgba(ink[0], ink[1], ink[2], 0.5); ctx.set_line_width(lw * 0.6); ctx.stroke()
    ctx.restore()


def _halter(ctx, hf, ink, lw, sh):
    lc = _col((0.46, 0.15, 0.10), sh); hc = _col((0.70, 0.32, 0.22), sh)
    ring = _col((0.95, 0.78, 0.40), sh)
    def strap(pts, w=15):
        ctx.new_path(); smooth_path(ctx, [hf(p) for p in pts])
        ctx.set_source_rgb(*ink); ctx.set_line_width(w + lw * 1.4); ctx.stroke()
        ctx.new_path(); smooth_path(ctx, [hf(p) for p in pts])
        ctx.set_source_rgb(*lc); ctx.set_line_width(w); ctx.stroke()
        ctx.new_path(); smooth_path(ctx, [hf((p[0] - 3, p[1] - 3)) for p in pts])
        ctx.set_source_rgba(*hc, 0.8); ctx.set_line_width(w * 0.25); ctx.stroke()
    strap([(206, -14), (210, 40), (214, 104)])                       # noseband
    strap([(208, 60), (160, 50), (100, 60), (40, 64), (4, 40), (-2, 14)])   # cheek strap to crown
    strap([(20, 74), (4, 104), (-8, 124)], 12)                       # throatlatch
    for p in ((208, 58), (212, 106)):
        ctx.new_path(); ctx.arc(*hf(p), 9, 0, TAU)
        ctx.set_source_rgb(*ink); ctx.set_line_width(7.5); ctx.stroke_preserve()
        ctx.set_source_rgb(*ring); ctx.set_line_width(4.5); ctx.stroke()


def _closeup_mane(ctx, crest, hf, t, c, ink, lw, rimc, rs, sh):
    # draped locks along crest (poll -> withers), hanging down/back onto the near side of the neck
    pts = crest  # poll..base
    segl = [_len(_sub(pts[i + 1], pts[i])) for i in range(len(pts) - 1)]
    tot = sum(segl)
    def at(f):
        d = f * tot
        for i, l in enumerate(segl):
            if d <= l or i == len(segl) - 1:
                return _lerp2(pts[i], pts[i + 1], min(1.0, d / l)), _norm(_sub(pts[i + 1], pts[i]))
            d -= l
    n = 7
    for i in range(n - 1, -1, -1):
        f0 = 0.06 + i / n * 0.88; f1 = 0.06 + (i + 1.25) / n * 0.88
        p0, tg0 = at(f0); p1, tg1 = at(min(f1, 0.99))
        sway = (fbm1(t * 0.9 + i * 0.5, 91) - 0.5) * 2
        L = 120 + 34 * math.sin(i * 1.9) + 26 * (i % 2)
        mid = _lerp2(p0, p1, 0.5)
        tg = _norm(_add(tg0, tg1))
        inward = (tg[1], -tg[0]) if False else (-tg[1], tg[0])
        # choose the perpendicular that points into the neck (toward +x in local space)
        if inward[0] < 0:
            inward = (-inward[0], -inward[1])
        dn = _norm(_add(_mul(inward, 1.0), _mul(tg, 0.55 + 0.15 * sway)))
        tip = _add(mid, _mul(dn, L))
        out0 = _sub(p0, _mul(inward, 12)); out1 = _sub(p1, _mul(inward, 12))
        bend = _perp(dn)
        bamt = 16 * (1 if i % 2 else -0.6) + 8 * sway
        def cv(a, f, extra):
            q = _lerp2(a, tip, f)
            return _add(q, _mul(bend, bamt * math.sin(math.pi * f) + extra))
        poly = [out0, cv(out0, 0.35, -6), cv(out0, 0.72, -3), tip, cv(out1, 0.7, 4), cv(out1, 0.33, 6), out1]
        ctx.new_path(); smooth_path(ctx, poly, closed=True, tension=0.45)
        path = ctx.copy_path()
        _set(ctx, mix_color(c, (0.8, 0.5, 0.3), 0.08 * (i % 2))); ctx.fill()
        _band(ctx, path, 8, -14, (0.80, 0.68, 0.74), 1.0, cairo.OPERATOR_MULTIPLY)
        if rs > 0:
            _band(ctx, path, 5, 6, rimc, 0.7 * rs)
        ctx.new_path(); ctx.append_path(path); ctx.set_source_rgb(*ink); ctx.set_line_width(lw * 0.85); ctx.stroke()
        ctx.new_path(); ctx.move_to(*_lerp2(mid, tip, 0.2)); ctx.line_to(*_lerp2(mid, tip, 0.75))
        ctx.set_source_rgba(ink[0], ink[1], ink[2], 0.4); ctx.set_line_width(lw * 0.5); ctx.stroke()
    # forelock: falls over the forehead
    sway = (fbm1(t * 0.8, 95) - 0.5) * 2
    fl = [(-14, -20), (20, -34), (50, -32), (76 + 5 * sway, -18), (88 + 7 * sway, -4), (66, -10), (52, -8), (40, -4), (22, -10)]
    ctx.new_path(); smooth_path(ctx, [hf(p) for p in fl], closed=True, tension=0.45)
    path = ctx.copy_path()
    _set(ctx, c); ctx.fill()
    _band(ctx, path, 6, -10, (0.80, 0.68, 0.74), 1.0, cairo.OPERATOR_MULTIPLY)
    if rs > 0:
        _band(ctx, path, 4, 6, rimc, 0.7 * rs)
    ctx.new_path(); ctx.append_path(path); ctx.set_source_rgb(*ink); ctx.set_line_width(lw * 0.85); ctx.stroke()


# ----------------------------------------------------------------------------- self test
def _contact_sheet(path):
    import time
    from lib.common import vgradient, text
    Wd, Hd = 3200, 3560
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, Wd, Hd)
    ctx = cairo.Context(surf)
    vgradient(ctx, 0, 0, Wd, Hd, [(0, PAL["night_top"]), (0.5, PAL["night_mid"]), (1, PAL["night_low"])])
    hero = dict(HERO_JOCKEY, push=0.8)
    sc = 0.78
    cw, ch = 800, 380

    def ground(cx, cy):
        ctx.set_source_rgba(*PAL["track_dirt"], 0.85); ctx.rectangle(cx - 390, cy, 780, 18); ctx.fill()

    def label(s_, x_, y_):
        text(ctx, s_, x_, y_, 24, align="left", color=(0.8, 0.9, 1.0))

    timings = []
    # rows 0-2: 12 gallop phases, hero + jockey
    for i in range(12):
        cx = 400 + (i % 4) * cw; cy = 40 + 330 + (i // 4) * ch
        ground(cx, cy)
        t0 = time.perf_counter()
        draw_horse(ctx, cx, cy, sc, i / 12.0, jockey=hero, t=i / 12 / GALLOP_HZ, number=14, motion_blur=0.0)
        timings.append(time.perf_counter() - t0)
        label("gallop %.3f" % (i / 12), cx - 385, cy - 300)
    # row 3: rivals (with motion blur on two)
    y3 = 40 + 330 + 3 * ch
    for i in range(4):
        cx = 400 + i * cw
        ground(cx, y3)
        cp = COAT_PRESET_LIST[i]
        draw_horse(ctx, cx, y3, sc, (0.15 + i * 0.23) % 1, coat=cp["coat"], mane=cp["mane"], blaze=(i == 3),
                   socks=((True, False, False, False) if i == 1 else (False,) * 4), jockey=dict(JOCKEY_PRESETS[i], push=0.6),
                   t=i * 0.3, number=[3, 7, 1, 11][i], motion_blur=0.6 if i % 2 else 0.0)
        label("rival %d%s" % (i, "  motion_blur=.6" if i % 2 else ""), cx - 385, y3 - 300)
    y4 = y3 + ch
    for i in range(4):
        cx = 400 + i * cw
        ground(cx, y4)
        j = 4 + i
        if j < len(JOCKEY_PRESETS):
            cp = COAT_PRESET_LIST[(i + 4) % len(COAT_PRESET_LIST)]
            draw_horse(ctx, cx, y4, sc, (0.4 + i * 0.3) % 1, coat=cp["coat"], mane=cp["mane"], blaze=False,
                       jockey=dict(JOCKEY_PRESETS[j], push=0.6), t=i * 0.3, number=[5, 9, 2, 12][i],
                       shade=[0.0, 0.3, 0.6, 0.0][i], lean=[0, 0, 0, 0.6][i])
            label("rival %d  shade=%.1f%s" % (j, [0.0, 0.3, 0.6, 0.0][i], "  lean=.6" if i == 3 else ""), cx - 385, y4 - 300)
    # row 5: burst sequence
    y5 = y4 + ch
    for i, bp in enumerate((0.0, 0.12, 0.3, 0.6)):
        cx = 400 + i * cw
        ground(cx, y5)
        draw_horse(ctx, cx, y5, sc, bp, gait="burst", jockey=hero, t=bp, number=14)
        label("burst %.2f" % bp, cx - 385, y5 - 300)
    # row 6: stand (warm) + canter
    y6 = y5 + ch
    for i in range(2):
        cx = 400 + i * cw
        ground(cx, y6)
        draw_horse(ctx, cx, y6, sc, i * 0.4, gait="stand", t=i * 2.0, rim=PAL["lamp_warm"],
                   jockey=(dict(HERO_JOCKEY, crouch=0.2) if i else None))
        label("stand" + (" + jockey crouch=.2" if i else ""), cx - 385, y6 - 300)
    for i in range(2):
        cx = 400 + (2 + i) * cw
        ground(cx, y6)
        draw_horse(ctx, cx, y6, sc, 0.2 + i * 0.4, gait="canter", stride=0.8, jockey=dict(HERO_JOCKEY, crouch=0.6),
                   t=i, number=14)
        label("canter %.1f" % (0.2 + i * 0.4), cx - 385, y6 - 300)
    # row 7: head close-ups
    y7 = Hd - 20
    ctx.save(); ctx.rectangle(0, y6 + 40, Wd, Hd - y6 - 40)
    ctx.set_source_rgb(0.12, 0.07, 0.05); ctx.fill(); ctx.restore()
    heads = [dict(), dict(blink=0.55, ear=1.0, nostril=0.8, look=(0.8, 0.2)), dict(blink=1.0, nuzzle=1.0, ear=-0.6),
             dict(facing=1, mouth=0.6, nostril=1.0, ear=1.0)]
    ht = []
    for i, k in enumerate(heads):
        cx = 440 + i * cw
        t0 = time.perf_counter()
        draw_horse_head(ctx, cx, y7, 0.85, t=i * 1.3, **k)
        ht.append(time.perf_counter() - t0)
        label("head " + ", ".join("%s=%s" % kv for kv in k.items()), cx - 400, y6 + 80)
    surf.write_to_png(path)
    print("draw_horse(jockey) avg %.1f ms  max %.1f ms | head avg %.1f ms" %
          (1000 * sum(timings) / len(timings), 1000 * max(timings), 1000 * sum(ht) / len(ht)))


if __name__ == "__main__":
    out = "/tmp/claude-0/-home-user-keiba/d53da140-107f-55e4-b8c0-8a92c9796981/scratchpad/horse_sheet.png"
    _contact_sheet(out)
    print(out)
