"""Shared DSP helpers for the music / sfx / mix scripts (numpy + scipy only)."""
import os
import sys

import numpy as np
from scipy import signal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import AUDIO_SR as SR, DURATION, BUILD  # noqa: E402

N = int(round(DURATION * SR))
AUDIO_OUT = os.path.join(BUILD, "audio")


def silence(n=N, ch=2):
    return np.zeros((n, ch), dtype=np.float64)


def db(x):
    return 10.0 ** (x / 20.0)


def to_db(x):
    return 20.0 * np.log10(np.maximum(np.abs(x), 1e-12))


def tsec(n=N):
    return np.arange(n) / SR


def curve(points, n=N, kind="lin"):
    """Piecewise automation curve. points = [(t_sec, value), ...]. kind 'db' -> values in dB, returned linear."""
    pts = sorted(points)
    ts = np.array([p[0] for p in pts]) * SR
    vs = np.array([p[1] for p in pts], dtype=np.float64)
    y = np.interp(np.arange(n), ts, vs)
    return db(y) if kind == "db" else y


def pan_gains(p):
    """Equal-power pan, p in [-1, 1]."""
    a = (np.clip(p, -1, 1) + 1) * np.pi / 4
    return np.cos(a), np.sin(a)


def pan_mono(x, p):
    gl, gr = pan_gains(p)
    return np.stack([x * gl, x * gr], axis=1)


def stereo_balance(x, p, width=1.0):
    """Apply balance + width to a stereo buffer."""
    m = (x[:, 0] + x[:, 1]) * 0.5
    s = (x[:, 0] - x[:, 1]) * 0.5 * width
    l, r = m + s, m - s
    gl, gr = pan_gains(p)
    return np.stack([l * gl * 1.4142, r * gr * 1.4142], axis=1)


def sos(kind, f, order=2, fs=SR):
    return signal.butter(order, f, btype=kind, fs=fs, output="sos")


def filt(x, kind, f, order=2):
    return signal.sosfilt(sos(kind, f, order), x, axis=0)


def lp(x, f, order=2):
    return filt(x, "lowpass", f, order)


def hp(x, f, order=2):
    return filt(x, "highpass", f, order)


def bp(x, lo, hi, order=2):
    return filt(x, "bandpass", [lo, hi], order)


def peak_eq(x, f0, gain_db, q=1.0):
    """RBJ peaking EQ."""
    A = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * f0 / SR
    al = np.sin(w0) / (2 * q)
    b = np.array([1 + al * A, -2 * np.cos(w0), 1 - al * A])
    a = np.array([1 + al / A, -2 * np.cos(w0), 1 - al / A])
    return signal.lfilter(b / a[0], a / a[0], x, axis=0)


def shelf(x, f0, gain_db, high=True):
    A = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * f0 / SR
    al = np.sin(w0) / 2 * np.sqrt(2)
    c = np.cos(w0)
    if high:
        b = [A * ((A + 1) + (A - 1) * c + 2 * np.sqrt(A) * al), -2 * A * ((A - 1) + (A + 1) * c),
             A * ((A + 1) + (A - 1) * c - 2 * np.sqrt(A) * al)]
        a = [(A + 1) - (A - 1) * c + 2 * np.sqrt(A) * al, 2 * ((A - 1) - (A + 1) * c),
             (A + 1) - (A - 1) * c - 2 * np.sqrt(A) * al]
    else:
        b = [A * ((A + 1) - (A - 1) * c + 2 * np.sqrt(A) * al), 2 * A * ((A - 1) - (A + 1) * c),
             A * ((A + 1) - (A - 1) * c - 2 * np.sqrt(A) * al)]
        a = [(A + 1) + (A - 1) * c + 2 * np.sqrt(A) * al, -2 * ((A - 1) + (A + 1) * c),
             (A + 1) + (A - 1) * c - 2 * np.sqrt(A) * al]
    b, a = np.array(b), np.array(a)
    return signal.lfilter(b / a[0], a / a[0], x, axis=0)


def make_ir(t60=2.2, length=None, predelay=0.02, damp_hz=6000.0, hp_hz=120.0, seed=1,
            early=True, width=1.0):
    """Synthetic stereo reverb impulse response: decorrelated noise with frequency-dependent decay
    (high band decays faster) + sparse early reflections."""
    rng = np.random.default_rng(seed)
    length = length or t60 * 1.2
    n = int(length * SR)
    t = np.arange(n) / SR
    ir = np.zeros((n, 2))
    for ch in range(2):
        noise = rng.standard_normal(n)
        lo = lp(noise, damp_hz * 0.25, 2)
        mid = bp(noise, damp_hz * 0.25, damp_hz, 2)
        hi = hp(noise, damp_hz, 2)
        k = 6.91 / t60
        e = lo * np.exp(-k * 0.85 * t) + mid * np.exp(-k * t) + hi * np.exp(-k * 2.2 * t) * 0.5
        # soft onset (diffusion build-up)
        e *= 1 - np.exp(-t / 0.012)
        ir[:, ch] = e
    if width != 1.0:
        m = ir.mean(axis=1, keepdims=True)
        ir = m + (ir - m) * width
    if early:
        for i in range(10):
            d = predelay + rng.uniform(0.003, 0.06)
            g = 0.6 * rng.uniform(0.3, 1.0) * np.exp(-d * 20)
            idx = int(d * SR)
            if idx < n:
                ir[idx, i % 2] += g * 3
    pd = int(predelay * SR)
    ir = np.concatenate([np.zeros((pd, 2)), ir])[:n]
    ir = hp(ir, hp_hz, 2)
    ir /= np.sqrt(np.sum(ir ** 2) / 2)
    return ir


def convolve(x, ir):
    """Stereo (or mono->stereo) convolution, output same length as x."""
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    out = np.zeros_like(x)
    for ch in range(2):
        out[:, ch] = signal.fftconvolve(x[:, ch], ir[:, ch])[: len(x)]
    return out


def place(buf, sig, t, gain=1.0):
    """Add sig (mono or stereo) into buf at time t (sec). Clips at buffer edges."""
    i = int(round(t * SR))
    if sig.ndim == 1:
        sig = np.stack([sig, sig], axis=1)
    j0 = max(0, i)
    s0 = j0 - i
    j1 = min(len(buf), i + len(sig))
    if j1 > j0:
        buf[j0:j1] += sig[s0:s0 + (j1 - j0)] * gain
    return buf


def rms_curve(x, win=0.1):
    if x.ndim == 2:
        x = x.mean(axis=1)
    h = int(win * SR)
    k = len(x) // h
    return np.sqrt(np.mean(x[: k * h].reshape(k, h) ** 2, axis=1) + 1e-20)


def true_peak(x):
    """Approximate true peak via 4x oversampling."""
    up = signal.resample_poly(x, 4, 1, axis=0)
    return np.max(np.abs(up))


def lufs(x):
    import pyloudnorm as pyln
    return pyln.Meter(SR).integrated_loudness(x)


def write_wav(path, x):
    import soundfile as sf
    os.makedirs(os.path.dirname(path), exist_ok=True)
    x = np.asarray(x, dtype=np.float32)
    sf.write(path, x, SR, subtype="PCM_24")


def read_wav(path, sr_target=SR):
    import soundfile as sf
    x, sr = sf.read(path, dtype="float64", always_2d=True)
    if sr != sr_target:
        from math import gcd
        g = gcd(sr, sr_target)
        x = signal.resample_poly(x, sr_target // g, sr // g, axis=0)
    return x


def fit_length(x, n=N):
    if len(x) >= n:
        return x[:n]
    return np.concatenate([x, np.zeros((n - len(x),) + x.shape[1:])])


def spectrogram_png(x, path, title="", marks=None, fmax=12000):
    """Save a spectrogram + RMS curve PNG with vertical beat markers."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    mono = x.mean(axis=1) if x.ndim == 2 else x
    f, t, S = signal.spectrogram(mono, SR, nperseg=2048, noverlap=1536)
    fig, ax = plt.subplots(2, 1, figsize=(18, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    ax[0].pcolormesh(t, f, 10 * np.log10(S + 1e-14), shading="auto", vmin=-130, vmax=-30, cmap="magma")
    ax[0].set_ylim(20, fmax)
    ax[0].set_yscale("symlog", linthresh=500)
    ax[0].set_title(title)
    r = rms_curve(x, 0.05)
    ax[1].plot(np.arange(len(r)) * 0.05, to_db(r), lw=0.8)
    ax[1].set_ylim(-70, 0)
    ax[1].set_ylabel("RMS dBFS")
    ax[1].set_xlim(0, len(mono) / SR)
    ax[1].set_xticks(np.arange(0, len(mono) / SR + 0.1, 2))
    for name, tm in (marks or {}).items():
        for a in ax:
            a.axvline(tm, color="cyan", lw=0.7, alpha=0.8)
        ax[1].text(tm, -8, name, rotation=90, fontsize=7, color="teal", va="top")
    ax[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=80)
    plt.close(fig)
