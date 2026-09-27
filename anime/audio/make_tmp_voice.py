"""Placeholder voices (pyopenjtalk) for testing the mix before the real build/voice/ exists.
Writes build/audio/tmp_voice/{Lxx.wav, manifest.json} in the same format as build/voice/manifest.json."""
import json
import os
import sys

import numpy as np
from scipy import signal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dsp  # noqa: E402
from timeline import LINES  # noqa: E402

OUT = os.path.join(dsp.AUDIO_OUT, "tmp_voice")
TONE = {"AI": 0.0, "GEN": -4.0, "MIZUKI": 5.0, "ANN": 1.0}


def main():
    import pyopenjtalk
    os.makedirs(OUT, exist_ok=True)
    man = {}
    for ln in LINES:
        speed = 1.0
        for _ in range(6):
            x, sr = pyopenjtalk.tts(ln["text"], speed=speed, half_tone=TONE[ln["spk"]])
            if len(x) / sr <= ln["max"]:
                break
            speed *= len(x) / sr / ln["max"] * 1.02
        x = (x / 32768.0).astype(np.float64)
        x = signal.resample_poly(x, dsp.SR, sr) if sr != dsp.SR else x
        dsp.write_wav(os.path.join(OUT, ln["id"] + ".wav"), x[:, None])
        man[ln["id"]] = dict(file=ln["id"] + ".wav", duration=round(len(x) / dsp.SR, 3), start=ln["start"],
                             spk=ln["spk"])
    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(man, f, indent=1, ensure_ascii=False)
    print("wrote", len(man), "placeholder lines to", OUT)


if __name__ == "__main__":
    main()
