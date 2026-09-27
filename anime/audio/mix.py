"""Final mix -> build/audio/final.wav (48 kHz stereo, 60.0 s).

  music.wav + sfx.wav + voices from build/voice/manifest.json
  - voices centred; AI slightly wide (Haas) + plate; announcer through a PA chain with stadium slapback;
    characters with a light room.
  - music & sfx side-chain ducked under dialogue (up to -8 dB).
  - loudness normalised to -16 LUFS, look-ahead limiter to -1 dBTP.

Usage:  python audio/mix.py [--placeholder] [--png]
  --placeholder  fill lines missing from build/voice/ with build/audio/tmp_voice/ (testing only)
"""
import json
import os
import sys

import numpy as np
from scipy import ndimage, signal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dsp  # noqa: E402
from dsp import SR, N, db  # noqa: E402
from timeline import BEATS, LINES  # noqa: E402

VOICE_DIR = os.path.join(dsp.BUILD, "voice")
TMP_VOICE_DIR = os.path.join(dsp.AUDIO_OUT, "tmp_voice")
TARGET_LUFS = -16.0
CEIL_DBTP = -1.0
DUCK_DB = 8.0

# bus levels (dB) before loudness normalisation
MUSIC_DB = -1.5
SFX_DB = -1.0
# shouted lines that land on big musical hits duck the bed less, so the hit still lands
DUCK_OVERRIDE = {"L07": 4.0, "L09": 6.0, "L10": 10.0, "L11": 5.0}
# "fader rides" on the beds: the score's quiet scenes are written soft, lift them against the dialogue
MUSIC_RIDE = [(0, 7), (14.6, 7), (15.4, 3), (18.3, 3), (18.5, 0), (50.0, 0), (51.0, 6), (60, 6)]
SFX_RIDE = [(0, 3), (15.0, 3), (18.3, 2), (18.5, 0), (60, 0)]
VOICE_LINE_LUFS = {"AI": -17.0, "GEN": -16.5, "MIZUKI": -16.5, "ANN": -15.5}


def load_manifest(path_dir):
    p = os.path.join(path_dir, "manifest.json")
    if not os.path.exists(p):
        return {}
    with open(p) as f:
        man = json.load(f)
    return {k: dict(v, _dir=path_dir) for k, v in man.items()}


def line_loudness(x):
    import pyloudnorm as pyln
    m = pyln.Meter(SR, block_size=0.2)
    try:
        v = m.integrated_loudness(x)
    except Exception:
        v = -70.0
    return v if np.isfinite(v) else -70.0


# -------------------------------------------------------------------- speaker chains (mono in -> stereo out)
IR_ROOM = dsp.make_ir(t60=0.45, predelay=0.006, damp_hz=5000, seed=21, width=0.8)
IR_PLATE = dsp.make_ir(t60=1.3, predelay=0.012, damp_hz=8000, seed=33, width=1.2)
IR_STADIUM = dsp.make_ir(t60=2.8, predelay=0.04, damp_hz=3500, hp_hz=200, seed=45, width=1.3)


def delay(x, sec):
    d = int(sec * SR)
    return np.concatenate([np.zeros(d), x])[: len(x)]


def chain_room(x, send=0.12):
    x = dsp.hp(x, 90)
    x = dsp.peak_eq(x, 3000, 1.5, 1.0)
    dry = np.stack([x, x], axis=1)
    return dry + dsp.convolve(x * send, IR_ROOM)


def chain_ai(x):
    x = dsp.hp(x, 160)
    x = dsp.peak_eq(x, 2800, 2.5, 1.2)
    x = dsp.shelf(x, 7000, 2.0, high=True)
    # slight width: Haas-delayed band-limited copies either side (mono-compatible, centre stays)
    side = dsp.bp(x, 600, 7000)
    l = x + 0.22 * delay(side, 0.009)
    r = x + 0.22 * delay(side, 0.014)
    dry = np.stack([l, r], axis=1)
    return dry + dsp.convolve(x * 0.22, IR_PLATE)


def chain_pa(x):
    """Stadium PA: horn-speaker band-limit, mild drive, slapback echoes from the stands + big space."""
    x = dsp.bp(x, 230, 5500, 2)
    x = dsp.peak_eq(x, 1800, 4.0, 1.0)
    x = np.tanh(x * 2.0) / 2.0 * 1.3
    dry = np.stack([x, x], axis=1)
    slap = np.stack([0.30 * delay(x, 0.095) + 0.16 * delay(x, 0.23),
                     0.26 * delay(x, 0.12) + 0.14 * delay(x, 0.265)], axis=1)
    slap = dsp.lp(slap, 3500)
    return dry + slap + dsp.convolve(x * 0.28, IR_STADIUM)


def voice_bus(man):
    bus = np.zeros((N, 2))
    key = np.zeros(N)         # dry mono voice for side-chain detection
    depth = np.zeros(N)       # per-sample duck depth (dB) of the line speaking there
    for lid in sorted(man):
        info = man[lid]
        spk = info.get("spk", "GEN")
        x = dsp.read_wav(os.path.join(info["_dir"], info["file"])).mean(axis=1)
        L = line_loudness(x)
        g = db(VOICE_LINE_LUFS.get(spk, -16.5) - L) if L > -60 else 1.0
        x = x * g
        # fade edges to avoid clicks
        f = min(len(x) // 4, int(0.005 * SR))
        if f > 0:
            x[:f] *= np.linspace(0, 1, f)
            x[-f:] *= np.linspace(1, 0, f)
        if spk == "AI":
            y = chain_ai(x)
        elif spk == "ANN":
            y = chain_pa(x)
        elif lid in ("L06", "L07"):
            y = chain_room(x, 0.05)   # on horseback: dry, open air
        else:
            y = chain_room(x, 0.12)
        # keep reverb tails (up to 1.5 s)
        tail = int(1.5 * SR)
        xx = np.concatenate([x, np.zeros(tail)])
        yy = np.concatenate([y, np.zeros((tail, 2))])
        if spk == "AI":
            yy[len(x):] = dsp.convolve(xx * 0.22, IR_PLATE)[len(x):]
        elif spk == "ANN":
            yy[len(x):] = (np.stack([0.30 * delay(dsp.bp(xx, 230, 5500), 0.095)] * 2, axis=1) * 0.5 +
                           dsp.convolve(dsp.bp(xx, 230, 5500) * 0.28, IR_STADIUM))[len(x):]
        else:
            yy[len(x):] = dsp.convolve(xx * 0.1, IR_ROOM)[len(x):]
        start = float(info.get("start", next((ln["start"] for ln in LINES if ln["id"] == lid), 0.0)))
        dsp.place(bus, yy, start)
        i0 = int(round(start * SR))
        i1 = min(N, i0 + len(x))
        key[i0:i1] += x[: i1 - i0]
        d0, d1 = max(0, i0 - int(0.1 * SR)), min(N, i1 + int(0.4 * SR))
        depth[d0:d1] = np.maximum(depth[d0:d1], DUCK_OVERRIDE.get(lid, DUCK_DB))
        print("  %s %-6s start %6.2f dur %5.2f  (%.1f LUFS -> %.1f)" % (lid, spk, start, len(x) / SR, L,
                                                                       VOICE_LINE_LUFS.get(spk, -16.5)))
    return bus, key, depth


def duck_gain(key, depth_db, attack=0.04, release=0.35, lookahead=0.05):
    """Side-chain ducking curve from the dry voice key (linear gain per sample)."""
    h = int(0.01 * SR)
    k = len(key) // h
    r = np.sqrt(np.mean(key[: k * h].reshape(k, h) ** 2, axis=1) + 1e-12)
    lvl = dsp.to_db(r)
    amt = np.clip((lvl + 50) / 14, 0, 1)                 # -50 dBFS .. -36 dBFS -> 0..1
    amt = ndimage.maximum_filter1d(amt, int(0.12 / 0.01))  # bridge short gaps between syllables
    la = int(lookahead / 0.01)
    amt = np.concatenate([amt[la:], np.zeros(la)])       # open before the voice starts
    out = np.zeros_like(amt)
    a = np.exp(-0.01 / attack)
    rl = np.exp(-0.01 / release)
    s = 0.0
    for i, v in enumerate(amt):
        c = a if v > s else rl
        s = c * s + (1 - c) * v
        out[i] = s
    amt_s = np.interp(np.arange(len(key)), np.arange(k) * h + h / 2, out)
    return db(-depth_db * amt_s)


def limiter(x, ceil_db=CEIL_DBTP, lookahead=0.005, release=0.12):
    ceil = db(ceil_db)
    # 4x oversampled peak envelope
    up = signal.resample_poly(x, 4, 1, axis=0)
    pk = np.max(np.abs(up), axis=1).reshape(-1, 4).max(axis=1)[: len(x)]
    need = np.minimum(1.0, ceil / np.maximum(pk, 1e-9))
    la = int(lookahead * SR)
    need = ndimage.minimum_filter1d(need, 2 * la + 1)
    # block-wise release smoothing (instant attack thanks to look-ahead min filter)
    blk = 48
    nb = int(np.ceil(len(need) / blk))
    nbk = np.pad(need, (0, nb * blk - len(need)), constant_values=1).reshape(nb, blk).min(axis=1)
    rl = np.exp(-blk / SR / release)
    g = np.empty(nb)
    s = 1.0
    for i, v in enumerate(nbk):
        s = v if v < s else rl * s + (1 - rl) * v
        g[i] = s
    gs = np.interp(np.arange(len(x)), np.arange(nb) * blk + blk / 2, g)
    gs = np.minimum(gs, need)
    # smooth the gain slightly without losing the peaks (min-filter then short average)
    gs = ndimage.uniform_filter1d(ndimage.minimum_filter1d(gs, la), la)
    gs = np.minimum(gs, need)
    return x * gs[:, None]


def main():
    man = load_manifest(VOICE_DIR)
    if "--placeholder" in sys.argv:
        tmp = load_manifest(TMP_VOICE_DIR)
        for k, v in tmp.items():
            man.setdefault(k, v)
    missing = [ln["id"] for ln in LINES if ln["id"] not in man]
    print("voices: %d lines from %s%s" % (len(man), VOICE_DIR, " (+placeholders)" if "--placeholder" in sys.argv
                                            else ""))
    if missing:
        print("  WARNING: missing lines:", " ".join(missing))

    music = dsp.fit_length(dsp.read_wav(os.path.join(dsp.AUDIO_OUT, "music.wav")))
    sfx = dsp.fit_length(dsp.read_wav(os.path.join(dsp.AUDIO_OUT, "sfx.wav")))
    vbus, key, depth = voice_bus(man)

    duck = duck_gain(key, depth)
    bed = music * (db(MUSIC_DB) * dsp.curve(MUSIC_RIDE, N, "db"))[:, None] + \
        sfx * (db(SFX_DB) * dsp.curve(SFX_RIDE, N, "db"))[:, None]
    mix = bed * duck[:, None] + vbus

    # loudness normalise -> limit, iterate to land on target
    gain = 0.0
    for it in range(4):
        y = limiter(mix * db(gain))
        L = dsp.lufs(y)
        if abs(L - TARGET_LUFS) < 0.2:
            break
        gain += TARGET_LUFS - L
    y[-1] = 0
    y = dsp.fit_length(y)
    tp = dsp.to_db(dsp.true_peak(y))
    if tp > CEIL_DBTP:
        y *= db(CEIL_DBTP - tp - 0.05)
        tp = dsp.to_db(dsp.true_peak(y))
    out = os.path.join(dsp.AUDIO_OUT, "final.wav")
    dsp.write_wav(out, y)
    print("wrote %s  %.3fs  %.1f LUFS  true-peak %.2f dBTP  (min duck gain %.1f dB)" % (
        out, len(y) / SR, dsp.lufs(y), tp, dsp.to_db(duck.min())))
    if "--png" in sys.argv:
        marks = dict(BEATS)
        for ln in LINES:
            marks[ln["id"]] = ln["start"]
        dsp.spectrogram_png(y, os.path.join(dsp.AUDIO_OUT, "final.png"), "final.wav", marks)


if __name__ == "__main__":
    main()
