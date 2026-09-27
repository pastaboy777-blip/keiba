"""Lip-sync from generated voice files.

mouth(spk, gt) -> 0..1 mouth openness for speaker spk ("MIZUKI","GEN","ANN","AI") at global time gt.
talking(spk, gt) -> True while that speaker has a line in progress.
Works before voices exist (falls back to a synthetic flap during each line's slot).
"""
import os, json, math
import numpy as np
from config import BUILD
from timeline import LINES

_ENV = None  # id -> (start, env array @100Hz)
RATE = 100

def _load():
    global _ENV
    if _ENV is not None:
        return _ENV
    _ENV = {}
    man = os.path.join(BUILD, "voice", "manifest.json")
    M = json.load(open(man)) if os.path.exists(man) else {}
    for L in LINES:
        info = M.get(L["id"])
        env = None
        if info:
            try:
                import soundfile as sf
                x, sr = sf.read(os.path.join(BUILD, "voice", info["file"]), dtype="float32")
            except Exception:
                from scipy.io import wavfile
                sr, x = wavfile.read(os.path.join(BUILD, "voice", info["file"]))
                x = x.astype(np.float32) / (32768.0 if x.dtype == np.int16 else 1.0)
            if x.ndim > 1: x = x.mean(1)
            hop = sr // RATE
            n = len(x) // hop
            rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-9)
            ref = np.percentile(rms, 95) + 1e-6
            e = np.clip((rms / ref - 0.08) / 0.8, 0, 1)
            # smooth a bit (attack fast, release slower)
            out = np.zeros_like(e); v = 0
            for i, s in enumerate(e):
                v = s if s > v else v * 0.72 + s * 0.28
                out[i] = v
            env = out
            start = info.get("start", L["start"])
        else:
            dur = L["max"] * 0.9
            ts = np.arange(int(dur * RATE)) / RATE
            env = (0.5 + 0.5 * np.sin(ts * 2 * math.pi * 5.5)) * (0.6 + 0.4 * np.sin(ts * 7.3))
            env = np.clip(env, 0, 1)
            start = L["start"]
        _ENV[L["id"]] = (L["spk"], start, env)
    return _ENV

def mouth(spk, gt):
    for lid, (s, start, env) in _load().items():
        if s != spk: continue
        i = int((gt - start) * RATE)
        if 0 <= i < len(env):
            return float(env[i])
    return 0.0

def talking(spk, gt):
    for lid, (s, start, env) in _load().items():
        if s == spk and start <= gt < start + len(env) / RATE:
            return True
    return False
