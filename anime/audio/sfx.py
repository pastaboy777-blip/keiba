"""Sound design for 「最後の一完歩」 -> build/audio/sfx.wav (48 kHz stereo, 60.0 s).

Pure numpy/scipy synthesis (filtered noise, modal metal, FM, granular crowd), no samples.
Hoofbeats are locked to the music's beat grid (music.SEC) so the gallop and score breathe together:
the tracked horse (ハルカゼ) lands its first footfall of every stride exactly on a music beat.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dsp  # noqa: E402
from dsp import SR, N, place, db, curve  # noqa: E402
from timeline import BEATS  # noqa: E402
from music import SEC  # noqa: E402

RNG = np.random.default_rng(2024)


def env_exp(n, tau, attack=0.002):
    t = np.arange(n) / SR
    e = np.exp(-t / tau)
    a = int(attack * SR)
    if a > 0:
        e[:a] *= np.linspace(0, 1, a)
    return e


def noise(n, ch=1):
    x = RNG.standard_normal((n, ch) if ch > 1 else n)
    return x


def smooth_noise(n, rate_hz, ch=1):
    """Slow random control signal (0..1-ish) with ~rate_hz bandwidth."""
    k = int(n * rate_hz / SR) + 4
    pts = RNG.standard_normal((k, ch)) if ch > 1 else RNG.standard_normal(k)
    xs = np.linspace(0, n, k)
    if ch > 1:
        return np.stack([np.interp(np.arange(n), xs, pts[:, c]) for c in range(ch)], axis=1)
    return np.interp(np.arange(n), xs, pts)


def sine(f, n, phase=0.0):
    """f may be scalar or array (Hz per sample)."""
    if np.isscalar(f):
        return np.sin(2 * np.pi * f * np.arange(n) / SR + phase)
    return np.sin(2 * np.pi * np.cumsum(f) / SR + phase)


# ------------------------------------------------------------------------------------ s01 HUD
def hud_layer(buf):
    t0 = BEATS["hud_boot"]
    # power-on: rising chirp + sub thump + bright confirmation dyad
    n = int(0.45 * SR)
    f = np.geomspace(180, 2400, n)
    x = sine(f, n) * env_exp(n, 0.2, 0.01) * np.linspace(1, 0.3, n)
    place(buf, dsp.pan_mono(x * 0.18, 0), t0 - 0.05)
    n = int(0.5 * SR)
    th = sine(np.geomspace(110, 40, n), n) * env_exp(n, 0.12)
    place(buf, dsp.pan_mono(th * 0.35, 0), t0)
    for fr, dt in ((1760, 0.42), (2637, 0.5)):
        n = int(0.35 * SR)
        x = (sine(fr, n) + 0.3 * sine(fr * 2.01, n)) * env_exp(n, 0.09)
        place(buf, dsp.pan_mono(x * 0.07, 0.1), t0 + dt)
    # data chirps: scattered short FM blips, denser early, sparse under the AI line
    tt = t0 + 0.7
    while tt < 5.8:
        n = int(RNG.uniform(0.015, 0.05) * SR)
        fc = RNG.choice([1200, 1600, 2000, 2400, 3200, 4000]) * RNG.uniform(0.98, 1.02)
        mod = sine(fc * RNG.choice([0.5, 1.5, 2.0]), n) * RNG.uniform(0, 3)
        x = np.sin(2 * np.pi * fc * np.arange(n) / SR + mod) * env_exp(n, n / SR / 3, 0.001)
        g = 0.035 if 1.2 < tt < 5.6 else 0.06
        place(buf, dsp.pan_mono(x * g, RNG.uniform(-0.8, 0.8)), tt)
        tt += RNG.choice([0.06, 0.09, 0.12, 0.25, 0.4]) if tt < 1.2 else RNG.choice([0.12, 0.3, 0.5, 0.7])
    # scanning sweep as the view locks onto 大井 (~4.4 s)
    n = int(0.9 * SR)
    f = 900 + 500 * np.sin(np.linspace(0, 3 * np.pi, n))
    x = sine(f, n) * np.hanning(n) * 0.02
    place(buf, dsp.pan_mono(x, 0), 4.3)
    # lock-on double beep at 5.2
    for dt in (0, 0.11):
        n = int(0.07 * SR)
        place(buf, dsp.pan_mono(sine(2960, n) * env_exp(n, 0.03) * 0.05, 0), 5.2 + dt)


def city_layer(buf):
    """Night Tokyo: distant low hum + traffic swells (s01), fading into the stable."""
    n = N
    x = dsp.lp(noise(n, 2), 350, 2) * 0.5
    x += dsp.bp(noise(n, 2), 500, 2000, 2) * 0.03 * (0.5 + 0.5 * smooth_noise(n, 0.4, 2))
    g = curve([(0, -60), (0.3, -60), (1.0, -30), (5.6, -30), (6.6, -70), (60, -70)], n, "db")
    buf += x * g[:, None]


# ------------------------------------------------------------------------------------ s02 stable
def crickets(n, count=5, dist_lp=6000):
    out = np.zeros((n, 2))
    for c in range(count):
        fc = RNG.uniform(3900, 5200)
        period = RNG.uniform(0.45, 0.9)
        pulses = RNG.integers(2, 5)
        pan = RNG.uniform(-0.9, 0.9)
        g = RNG.uniform(0.3, 1.0)
        pl = int(0.018 * SR)
        pulse = sine(fc, pl) * np.hanning(pl)
        tt = RNG.uniform(0, period)
        while tt < n / SR - 0.2:
            for p in range(pulses):
                place(out, dsp.pan_mono(pulse * g, pan), tt + p * 0.028)
            tt += period * RNG.uniform(0.92, 1.08)
    return dsp.lp(out, dist_lp, 2)


def snort(dur=0.75):
    """Horse snort: forceful nasal exhale with nostril flutter."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = noise(n)
    body = dsp.bp(x, 180, 1400, 2) + 0.5 * dsp.peak_eq(dsp.bp(x, 600, 3500, 2), 900, 6, 2)
    flutter = 0.55 + 0.45 * np.sin(2 * np.pi * (32 - 8 * t / dur) * t) ** 2
    e = np.minimum(1, t / 0.03) * np.exp(-t / 0.22)
    y = body * flutter * e
    # low "chest" component
    y += 0.4 * dsp.lp(noise(n), 250, 2) * e
    return y / (np.max(np.abs(y)) + 1e-9)


def rustle(n, density=160):
    """Straw rustle: dense tiny crackles, band-limited."""
    out = np.zeros(n)
    k = int(density * n / SR)
    idx = RNG.integers(0, n - 200, k)
    for i in idx:
        L = RNG.integers(20, 160)
        out[i:i + L] += RNG.standard_normal(L) * np.exp(-np.arange(L) / (L / 4)) * RNG.uniform(0.2, 1)
    out = dsp.bp(out, 1200, 9000, 2)
    return out / (np.max(np.abs(out)) + 1e-9)


def hoof_on_wood():
    n = int(0.25 * SR)
    t = np.arange(n) / SR
    x = sine(np.geomspace(140, 70, n), n) * np.exp(-t / 0.05) + 0.4 * dsp.bp(noise(n), 300, 2500) * np.exp(-t / 0.02)
    return x / np.max(np.abs(x))


def stable_layer(buf):
    a, b = 5.6, 15.3
    n = int((b - a) * SR)
    amb = dsp.lp(noise(n, 2), 220, 2) * 0.07  # room tone
    amb += crickets(n, 6) * 0.05
    e = curve([(0, 0), (0.9, 1), (b - a - 0.9, 1), (b - a, 0)], n)
    place(buf, amb * e[:, None], a)
    # straw rustles (feet shifting)
    for t0, dur, g, pan in ((7.3, 0.9, 0.05, 0.3), (10.2, 0.6, 0.035, -0.2), (12.4, 0.7, 0.04, 0.35),
                            (13.9, 0.8, 0.05, 0.25)):
        m = int(dur * SR)
        r = rustle(m) * np.hanning(m)
        place(buf, dsp.pan_mono(r * g, pan), t0)
    # hoof shift on wooden floor
    for t0, g in ((8.3, 0.09), (8.62, 0.07), (12.5, 0.06)):
        place(buf, dsp.pan_mono(dsp.lp(hoof_on_wood(), 2500) * g, 0.25), t0)
    # snort at 13.5 (+ soft preceding breath)
    s = snort()
    place(buf, dsp.pan_mono(s * 0.30, 0.2), 13.5)
    m = int(0.5 * SR)
    br = dsp.bp(noise(m), 200, 1200) * np.hanning(m) * 0.04
    place(buf, dsp.pan_mono(br, 0.2), 12.85)
    # wooden creak (door / beam)
    m = int(0.6 * SR)
    f0 = 180 + 40 * np.sin(np.linspace(0, 5, m))
    cr = dsp.bp(np.sign(sine(f0, m)) * (0.5 + 0.5 * smooth_noise(m, 30)), 300, 3000) * np.hanning(m) * 0.012
    place(buf, dsp.pan_mono(cr, -0.5), 9.6)


# ------------------------------------------------------------------------------------ heartbeat / gate
def heartbeat(g=1.0):
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    lub = sine(np.geomspace(75, 38, n), n) * np.exp(-t / 0.07) * np.minimum(1, t / 0.006)
    dub = np.zeros(n)
    d0 = int(0.19 * SR)
    m = n - d0
    tm = np.arange(m) / SR
    dub[d0:] = sine(np.geomspace(90, 45, m), m) * np.exp(-tm / 0.05) * np.minimum(1, tm / 0.005) * 0.7
    x = lub + dub
    x += 0.15 * dsp.lp(noise(n), 200) * (np.exp(-t / 0.03))
    return dsp.lp(x, 180, 2) * g


def gate_clang():
    """Starting gate: many spring-loaded steel doors slamming open (modal metal) + latch clack."""
    n = int(2.5 * SR)
    t = np.arange(n) / SR
    out = np.zeros((n, 2))
    modes = [(163, 1.2), (412, 0.9), (721, 0.8), (1187, 0.7), (1633, 0.5), (2219, 0.45), (2987, 0.35),
             (3702, 0.3), (4810, 0.2), (6180, 0.12)]
    for door in range(14):
        dt = abs(RNG.normal(0, 0.006)) if door else 0.0
        pan = -0.9 + 1.8 * door / 13
        sig = np.zeros(n)
        detune = RNG.uniform(0.94, 1.06)
        for f, tau in modes:
            sig += np.sin(2 * np.pi * f * detune * t + RNG.uniform(0, 6.28)) * np.exp(-t / (tau * 0.55)) * \
                   RNG.uniform(0.4, 1) / (1 + f / 1500)
        sig += dsp.hp(noise(n), 1500) * np.exp(-t / 0.012) * 1.5  # impact
        place(out, dsp.pan_mono(sig * 0.12, pan), dt)
    # low body thump of the whole structure
    body = sine(np.geomspace(90, 45, n), n) * np.exp(-t / 0.15)
    out += dsp.pan_mono(body * 0.6, 0)
    # bells: the start bell ringing (electric bell ~ 1.1 kHz rattle) in the background
    rb = int(1.4 * SR)
    bell = sine(1080, rb) * (0.5 + 0.5 * np.sign(sine(22, rb))) * np.exp(-np.arange(rb) / SR / 0.8)
    place(out, dsp.pan_mono(dsp.bp(bell, 800, 4000) * 0.03, 0.4), 0.02)
    return out


# ------------------------------------------------------------------------------------ gallop
def beat_grid():
    bts = []
    for k in "DEFG":
        s = SEC[k]
        bts += [s.t(b) for b in range(s.beats)]
    return np.array(bts + [SEC["G"].t1])


def hoof_hit(bright=1.0, distance=0.0):
    n = int(0.18 * SR)
    t = np.arange(n) / SR
    f0 = RNG.uniform(70, 110)
    thud = sine(np.geomspace(f0 * 1.8, f0, n), n) * np.exp(-t / 0.028)
    dirt = dsp.lp(noise(n), 1800) * np.exp(-t / 0.02) * 0.7
    clods = dsp.hp(noise(n), 2500) * np.exp(-t / 0.05) * 0.18 * bright
    x = thud + dirt + clods
    x *= np.minimum(1, t / 0.0015)
    if distance > 0:
        x = dsp.lp(x, 2500 / (1 + 3 * distance), 2)
    return x / (np.max(np.abs(x)) + 1e-9)


def gallop_layer(buf):
    beats = beat_grid()
    t_start = BEATS["gate_clang"] + 0.12
    t_end = BEATS["finish_line"]
    phases = np.array([0.0, 0.13, 0.32, 0.44])      # four-beat gallop: HL HR FL FR + suspension
    accents = np.array([0.8, 0.7, 0.9, 1.0])
    bank = [hoof_hit(1.0, 0) for _ in range(12)]
    bank_far = [hoof_hit(0.5, 0.7) for _ in range(12)]
    # tracked horse ハルカゼ: stride = one music beat
    hk = np.zeros((N, 2))
    for i in range(len(beats) - 1):
        b0, b1 = beats[i], beats[i + 1]
        if b0 < t_start - 0.01 or b0 >= t_end:
            continue
        P = b1 - b0
        for ph, ac in zip(phases, accents):
            tt = b0 + ph * P
            if tt >= t_end:
                break
            h = bank[RNG.integers(len(bank))]
            place(hk, dsp.pan_mono(h * ac * RNG.uniform(0.85, 1.0), RNG.uniform(-0.1, 0.1)), tt)
    # her hooves come forward when she kicks at 29.6 and dominate the straight
    g = curve([(0, -40), (18.5, -40), (18.6, -6), (29.5, -5), (29.6, -1), (33.0, 0), (44.95, 1), (45.0, -80),
               (60, -80)], N, "db")
    buf += hk * g[:, None] * 0.5
    # the pack: 13 other horses with their own stride rates / phases, spread across stereo
    pack = np.zeros((N, 2))
    for h in range(13):
        rate = RNG.uniform(2.3, 2.5)
        tt = t_start + RNG.uniform(0, 0.4)
        pan = RNG.uniform(-0.85, 0.85)
        gain = RNG.uniform(0.35, 0.8)
        while tt < t_end:
            P = 1.0 / (rate * RNG.uniform(0.985, 1.015))
            for ph, ac in zip(phases, accents):
                u = tt + ph * P + RNG.normal(0, 0.004)
                if u < t_end:
                    hh = bank_far[RNG.integers(len(bank_far))]
                    place(pack, dsp.pan_mono(hh * ac * gain, pan), u)
            tt += P
    # continuous ground rumble under the pack
    rum = dsp.lp(noise(N, 2), 110, 3) * 1.6
    pack += rum * curve([(0, 0), (18.5, 0), (19.0, 1), (44.9, 1), (45.0, 0), (60, 0)], N)[:, None]
    gp = curve([(0, -80), (18.5, -80), (18.6, -13), (24, -15), (29.6, -15), (33.0, -18), (40.2, -17), (44.95, -15),
                (45.0, -80), (60, -80)], N, "db")
    buf += pack * gp[:, None] * 0.5
    # horses thunder past after the line (47.4 -> decelerating, muffled by the crowd)
    tail = np.zeros((N, 2))
    tt = 47.45
    P = 0.42
    while tt < 51.0:
        for ph, ac in zip(phases, accents):
            place(tail, dsp.pan_mono(bank_far[RNG.integers(12)] * ac, RNG.uniform(-0.6, 0.6)), tt + ph * P)
        tt += P * RNG.uniform(0.45, 0.55)   # overlapping pack
        P *= 1.01
    buf += tail * curve([(0, -80), (47.4, -18), (49.0, -24), (51, -60), (60, -80)], N, "db")[:, None] * 0.5


# ------------------------------------------------------------------------------------ crowd
def babble(n, bands=((250, 500), (450, 900), (800, 1500), (1300, 2400), (2200, 3800)), mod_rate=6.0):
    out = np.zeros((n, 2))
    for lo, hi in bands:
        x = dsp.bp(noise(n, 2), lo, hi, 2)
        m = np.abs(smooth_noise(n, mod_rate, 2)) ** 1.5 + 0.35
        out += x * m * (1000 / (lo + 500))
    return out


def applause(n, rate=900):
    out = np.zeros(n + 400)
    k = int(rate * n / SR)
    idx = RNG.integers(0, n, k)
    L = 240
    clap = (dsp.bp(noise(L), 900, 6000) * np.exp(-np.arange(L) / 30))
    amps = RNG.uniform(0.2, 1.0, k)
    for i, a in zip(idx, amps):
        out[i:i + L] += clap * a
    return out[:n]


def crowd_layer(buf):
    b = BEATS
    # roar: babble + broadband shout layer; excitement raises the formant brightness
    roar = babble(N) * 0.6
    shout = dsp.bp(noise(N, 2), 500, 3500, 2) * (0.5 + 0.5 * np.abs(smooth_noise(N, 2.0, 2)))
    body = dsp.bp(noise(N, 2), 120, 600, 2) * 0.8
    g_roar = curve([(0, -80), (15.0, -80), (15.3, -34), (18.4, -32), (18.8, -24), (22, -21), (27, -19), (29.6, -16),
                    (33.0, -13), (38, -11), (40.2, -9), (44.95, -7), (45.0, -80), (47.38, -80), (47.4, -2),
                    (49.5, -4), (51.0, -12), (54, -18), (57, -24), (59.5, -45), (60, -80)], N, "db")
    g_shout = curve([(0, -80), (18.5, -80), (22, -34), (29.6, -24), (33, -20), (40.2, -15), (44.95, -12), (45.0, -80),
                     (47.38, -80), (47.4, -6), (49.5, -9), (51, -22), (55, -34), (60, -80)], N, "db")
    buf += roar * g_roar[:, None] + shout * g_shout[:, None] * 0.6 + body * g_roar[:, None] * 0.5
    # muffled crowd "underwater" during the photo-finish freeze 45.0 - 47.4
    muff = dsp.lp(babble(N), 300, 3) * 2.0
    buf += muff * curve([(0, -80), (45.0, -80), (45.15, -30), (47.2, -26), (47.4, -80), (60, -80)], N, "db")[:, None]
    # explosion at 47.4: fast swell + applause + whistles
    a0 = b["win_call"]
    ln = int((60 - a0) * SR)
    ap = np.stack([applause(ln, 1100), applause(ln, 1100)], axis=1)
    ga = curve([(0, -3), (2.5, -4), (4.0, -10), (7, -18), (10.0, -30), (12.6, -80)], ln, "db")
    place(buf, ap * ga[:, None] * 0.35, a0 + 0.08)
    for w in range(5):
        tw = a0 + RNG.uniform(0.3, 3.5)
        m = int(RNG.uniform(0.5, 1.1) * SR)
        f = np.linspace(RNG.uniform(1800, 2400), RNG.uniform(2600, 3400), m) * (1 + 0.01 * np.sin(np.arange(m) / 300))
        x = sine(f, m) * np.hanning(m) * 0.03
        place(buf, dsp.pan_mono(x, RNG.uniform(-0.8, 0.8)), tw)
    # impact "whump" of the eruption
    m = int(1.2 * SR)
    th = dsp.lp(noise(m), 200) * env_exp(m, 0.3, 0.02) * 0.6
    place(buf, dsp.pan_mono(th, 0), a0)


# ------------------------------------------------------------------------------------ wind / whoosh
def whoosh(dur, f_lo=300, f_hi=3000, peak=0.6):
    """Noise whoosh: band centre sweeps up to f_hi at the peak and back (blend of fixed bands, click-free)."""
    n = int(dur * SR)
    x = noise(n, 2)
    t = np.linspace(0, 1, n)
    env = np.exp(-((t - peak) ** 2) / 0.04)
    centres = np.geomspace(f_lo, f_hi, 6)
    pos = np.exp(-((t - peak) ** 2) / 0.05) * (len(centres) - 1)   # 0..5 index into centres
    out = np.zeros_like(x)
    for i, fc in enumerate(centres):
        w = np.maximum(0, 1 - np.abs(pos - i))
        out += dsp.bp(x, fc / 1.6, min(fc * 1.6, 20000), 2) * w[:, None]
    return out * env[:, None]


def wind_layer(buf):
    w = dsp.bp(noise(N, 2), 200, 2400, 2)
    gust = 0.6 + 0.4 * np.abs(smooth_noise(N, 0.8, 2))
    g = curve([(0, -80), (19.8, -80), (20.2, -26), (29.5, -26), (29.6, -20), (33, -18), (44.95, -15), (45.0, -80),
               (60, -80)], N, "db")
    buf += w * gust * g[:, None]
    # whooshes: flash into s04, the kick at 29.6, the cut at 33.0, the finish at 45.0
    for tc, dur, gg in ((20.0, 0.8, 0.25), (29.6, 0.9, 0.35), (33.0, 0.7, 0.25), (40.2, 0.6, 0.2)):
        place(buf, whoosh(dur) * gg, tc - dur * 0.6)
    place(buf, whoosh(1.1, 400, 6000, 0.82) * 0.45, BEATS["finish_line"] - 1.1 * 0.82)


def ring_layer(buf):
    """45.0 bright ring (tinnitus-like shimmer) + heartbeat in the freeze."""
    t0 = BEATS["finish_line"]
    n = int(2.6 * SR)
    t = np.arange(n) / SR
    r = np.zeros(n)
    for f, a in ((3520, 1.0), (4186, 0.6), (5274, 0.4), (7040, 0.25), (2637, 0.5)):
        r += a * sine(f * (1 + 0.002 * np.sin(2 * np.pi * 5 * t)), n)
    r *= np.exp(-t / 0.9) * np.minimum(1, t / 0.004)
    stereo = np.stack([r, np.roll(r, 37)], axis=1) * 0.035
    place(buf, stereo, t0)
    # flash impact: bright noise burst
    m = int(0.35 * SR)
    fl = dsp.hp(noise(m, 2), 3000) * env_exp(m, 0.06)[:, None] * 0.12
    place(buf, fl, t0)
    for tb, g in ((45.55, 0.55), (46.45, 0.6)):
        place(buf, dsp.pan_mono(heartbeat(g), 0), tb)


def heartbeat_layer(buf):
    t = 15.25
    iv = 0.92
    k = 0
    while t < 18.15:
        place(buf, dsp.pan_mono(heartbeat(0.45 + 0.08 * k), 0), t)
        t += iv
        iv *= 0.9
        k += 1


def glitch_layer(buf):
    """AI glitch at 41.4: bit-crushed stutters, square blips, pitch-jumping data burst."""
    t0 = BEATS["ai_glitch"]
    n = int(0.9 * SR)
    out = np.zeros((n, 2))
    pos = 0
    while pos < n - 200:
        L = int(RNG.choice([0.012, 0.02, 0.035, 0.06]) * SR)
        kind = RNG.integers(0, 4)
        tt = np.arange(L) / SR
        if kind == 0:
            x = np.sign(np.sin(2 * np.pi * RNG.choice([220, 440, 880, 1760, 3520]) * tt))
        elif kind == 1:
            x = noise(L)
            x = np.repeat(x[::RNG.integers(4, 24)], 24)[:L]
        elif kind == 2:
            x = np.sin(2 * np.pi * np.geomspace(RNG.uniform(3000, 8000), 200, L) * tt)
        else:
            x = np.zeros(L)
        x = np.round(x * 6) / 6
        pan = RNG.choice([-0.8, 0, 0.8])
        seg = dsp.pan_mono(x * RNG.uniform(0.3, 1.0), pan)
        out[pos:pos + L] += seg[: n - pos]
        pos += L
    e = curve([(0, 1), (0.5, 0.8), (0.9, 0)], n)
    place(buf, out * e[:, None] * 0.12, t0)
    # low digital "drop" thump
    m = int(0.3 * SR)
    place(buf, dsp.pan_mono(sine(np.geomspace(200, 30, m), m) * env_exp(m, 0.08) * 0.3, 0), t0)


def epilogue_layer(buf):
    # night ambience returns: distant crickets + soft wind, and an AI "update" data trickle under L12
    a = 50.0
    n = int((60 - a) * SR)
    amb = crickets(n, 5, 4500) * 0.04 + dsp.lp(noise(n, 2), 400) * 0.12
    e = curve([(0, 0), (1.5, 1), (8.0, 1), (9.8, 0.1), (10, 0)], n)
    place(buf, amb * e[:, None], a)
    tt = 51.1
    while tt < 54.4:
        m = int(0.03 * SR)
        fc = RNG.choice([2000, 2400, 3000])
        place(buf, dsp.pan_mono(sine(fc, m) * env_exp(m, 0.01) * 0.018, RNG.uniform(-0.5, 0.5)), tt)
        tt += RNG.choice([0.21, 0.42, 0.63])


def main():
    buf = dsp.silence()
    city_layer(buf)
    hud_layer(buf)
    stable_layer(buf)
    heartbeat_layer(buf)
    place(buf, gate_clang() * 0.9, BEATS["gate_clang"])
    gallop_layer(buf)
    crowd_layer(buf)
    wind_layer(buf)
    glitch_layer(buf)
    ring_layer(buf)
    epilogue_layer(buf)
    buf[-int(0.02 * SR):] *= np.linspace(1, 0, int(0.02 * SR))[:, None]
    # fixed calibration (not loudness-normalised, so mix balance stays stable), safety soft-clip
    buf *= 0.9
    pk = np.max(np.abs(buf))
    if pk > 0.95:
        buf = np.tanh(buf / 0.95) * 0.95
    out = os.path.join(dsp.AUDIO_OUT, "sfx.wav")
    dsp.write_wav(out, buf)
    print("wrote", out, "peak %.2f dBFS" % dsp.to_db(np.max(np.abs(buf))), "LUFS %.1f" % dsp.lufs(buf))
    if "--png" in sys.argv:
        dsp.spectrogram_png(buf, os.path.join(dsp.AUDIO_OUT, "sfx.png"), "sfx.wav", BEATS)


if __name__ == "__main__":
    main()
