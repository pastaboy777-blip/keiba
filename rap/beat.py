#!/usr/bin/env python3
"""チル/リラックス系 lo-fi ヒップホップ・ビート生成スクリプト。

外部ライブラリ不要(標準ライブラリのみ)。実行すると WAV ファイルを書き出す。

    python3 rap/beat.py                 # 既定設定で chill_beat.wav を生成
    python3 rap/beat.py --bpm 82 --bars 16 --out my_beat.wav

構成:
    - ドラム    : キック / スネア(リムショット寄り) / ハイハット
    - コード    : Rhodes 風のジャジーな 7th コード(I-vi-ii-V ループ)
    - ベース    : 各コードのルート音
    - lo-fi 加工: ソフトクリップ + ビニールノイズ + わずかな揺らぎ
"""

from __future__ import annotations

import argparse
import math
import random
import struct
import wave
from array import array

SAMPLE_RATE = 44100


# --------------------------------------------------------------------------
# 音名 → 周波数
# --------------------------------------------------------------------------
_NOTE_BASE = {
    "C": -9, "C#": -8, "Db": -8, "D": -7, "D#": -6, "Eb": -6,
    "E": -5, "F": -4, "F#": -3, "Gb": -3, "G": -2, "G#": -1, "Ab": -1,
    "A": 0, "A#": 1, "Bb": 1, "B": 2,
}


def note_to_freq(note: str) -> float:
    """'A4' や 'C#3' のような音名を周波数(Hz)に変換する。A4 = 440Hz。"""
    i = 1
    while i < len(note) and (note[i].isdigit() is False):
        i += 1
    name, octave = note[:i], int(note[i:])
    semis = _NOTE_BASE[name] + (octave - 4) * 12
    return 440.0 * (2.0 ** (semis / 12.0))


# --------------------------------------------------------------------------
# エンベロープ付きシンセ音源(各パートを float リストで返す)
# --------------------------------------------------------------------------
def _adsr(n: int, a: float, d: float, s: float, r: float) -> list[float]:
    """サンプル数 n のエンベロープ。a/d/r は秒、s はサステインレベル(0..1)。"""
    env = [0.0] * n
    at = int(a * SAMPLE_RATE)
    dt = int(d * SAMPLE_RATE)
    rt = int(r * SAMPLE_RATE)
    st = max(0, n - at - dt - rt)
    idx = 0
    for k in range(at):
        env[idx] = k / max(1, at); idx += 1
    for k in range(dt):
        if idx >= n: break
        env[idx] = 1.0 - (1.0 - s) * (k / max(1, dt)); idx += 1
    for _ in range(st):
        if idx >= n: break
        env[idx] = s; idx += 1
    for k in range(rt):
        if idx >= n: break
        env[idx] = s * (1.0 - k / max(1, rt)); idx += 1
    return env


def kick(dur: float = 0.34) -> list[float]:
    """ピッチが下がるサイン + わずかなクリックのキック。"""
    n = int(dur * SAMPLE_RATE)
    out = [0.0] * n
    for i in range(n):
        t = i / SAMPLE_RATE
        # 120Hz -> 45Hz にスイープ
        f = 45 + 75 * math.exp(-t * 28)
        env = math.exp(-t * 6.5)
        out[i] = math.sin(2 * math.pi * f * t) * env
    return out


def snare(dur: float = 0.22) -> list[float]:
    """ノイズ + 胴鳴りのスネア(lo-fi なので少し softly)。"""
    n = int(dur * SAMPLE_RATE)
    out = [0.0] * n
    for i in range(n):
        t = i / SAMPLE_RATE
        noise = random.uniform(-1, 1)
        body = math.sin(2 * math.pi * 190 * t)
        env = math.exp(-t * 22)
        out[i] = (0.65 * noise + 0.35 * body) * env
    return out


def hihat(dur: float = 0.06, level: float = 1.0) -> list[float]:
    """短いフィルタ付きノイズのハイハット。"""
    n = int(dur * SAMPLE_RATE)
    out = [0.0] * n
    prev = 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        white = random.uniform(-1, 1)
        # ハイパス(1次差分)で明るく
        hp = white - prev
        prev = white
        env = math.exp(-t * 90)
        out[i] = hp * env * level
    return out


def rhodes_chord(freqs: list[float], dur: float, detune: float = 0.004) -> list[float]:
    """複数音を重ねた Rhodes 風のやわらかいコード音。"""
    n = int(dur * SAMPLE_RATE)
    out = [0.0] * n
    env = _adsr(n, a=0.01, d=0.25, s=0.55, r=0.35)
    for f in freqs:
        for det in (1.0 - detune, 1.0 + detune):
            ff = f * det
            w = 2 * math.pi * ff
            for i in range(n):
                t = i / SAMPLE_RATE
                # 基音 + 弱い2倍音で電子ピアノ感
                s = math.sin(w * t) + 0.18 * math.sin(2 * w * t)
                out[i] += s * env[i]
    scale = 0.5 / max(1, len(freqs))
    for i in range(n):
        out[i] *= scale
    return out


def bass(freq: float, dur: float) -> list[float]:
    """サイン主体のまるいベース。"""
    n = int(dur * SAMPLE_RATE)
    out = [0.0] * n
    env = _adsr(n, a=0.008, d=0.1, s=0.8, r=0.12)
    w = 2 * math.pi * freq
    for i in range(n):
        t = i / SAMPLE_RATE
        s = math.sin(w * t) + 0.12 * math.sin(2 * w * t)
        out[i] = s * env[i] * 0.9
    return out


# --------------------------------------------------------------------------
# ミックス補助
# --------------------------------------------------------------------------
def mix_into(buf: list[float], src: list[float], start: int, gain: float = 1.0) -> None:
    end = min(len(buf), start + len(src))
    j = 0
    for i in range(start, end):
        buf[i] += src[j] * gain
        j += 1


def soft_clip(x: float) -> float:
    """tanh 風のソフトクリップで温かみを出す。"""
    return math.tanh(x)


# --------------------------------------------------------------------------
# ビート本体
# --------------------------------------------------------------------------
# I - vi - ii - V (キー C)。lo-fi の定番進行。
PROGRESSION = [
    ("Cmaj7", ["C3", "E3", "G3", "B3"], "C2"),
    ("Am7",   ["A2", "C3", "E3", "G3"], "A1"),
    ("Dm7",   ["D3", "F3", "A3", "C4"], "D2"),
    ("G7",    ["G2", "B2", "D3", "F3"], "G1"),
]


def build_beat(bpm: int, bars: int, seed: int = 7) -> list[float]:
    random.seed(seed)
    spb = 60.0 / bpm                      # 1拍の秒数
    bar_sec = spb * 4                     # 4/4
    total_sec = bar_sec * bars
    n_total = int(total_sec * SAMPLE_RATE) + SAMPLE_RATE
    buf = [0.0] * n_total

    # ワンショットを一度だけ生成して使い回す
    k = kick()
    s = snare()
    hh = hihat(level=0.5)
    hh_open = hihat(dur=0.12, level=0.42)

    def at(beat_pos: float) -> int:
        return int(beat_pos * spb * SAMPLE_RATE)

    for bar in range(bars):
        chord_name, chord_notes, bass_note = PROGRESSION[bar % len(PROGRESSION)]
        bar_start_beat = bar * 4

        # --- コード(小節頭で1回、やや後ろに揺らぎ) ---
        chord_freqs = [note_to_freq(x) for x in chord_notes]
        chord = rhodes_chord(chord_freqs, dur=bar_sec * 0.98)
        mix_into(buf, chord, at(bar_start_beat) + random.randint(0, 400), gain=0.55)

        # --- ベース(1拍目と3拍目) ---
        bfreq = note_to_freq(bass_note)
        b = bass(bfreq, dur=spb * 1.6)
        mix_into(buf, b, at(bar_start_beat + 0), gain=0.8)
        mix_into(buf, b, at(bar_start_beat + 2), gain=0.7)

        # --- キック(1拍目・3拍目の裏に軽く) ---
        mix_into(buf, k, at(bar_start_beat + 0), gain=1.0)
        mix_into(buf, k, at(bar_start_beat + 2.5), gain=0.7)

        # --- スネア(2拍目・4拍目) ---
        mix_into(buf, s, at(bar_start_beat + 1), gain=0.8)
        mix_into(buf, s, at(bar_start_beat + 3), gain=0.8)

        # --- ハイハット(8分。たまにオープン & スイング) ---
        for eighth in range(8):
            pos = bar_start_beat + eighth * 0.5
            swing = 0.06 if eighth % 2 == 1 else 0.0   # ゆるいスイング
            g = 0.9 if eighth % 2 == 0 else 0.55
            hs = hh_open if (eighth == 7 and bar % 2 == 1) else hh
            mix_into(buf, hs, at(pos + swing), gain=g)

    # --- lo-fi なビニールノイズを薄く敷く ---
    for i in range(n_total):
        if random.random() < 0.0006:              # まばらなプチノイズ
            buf[i] += random.uniform(-0.28, 0.28)
        buf[i] += random.uniform(-0.006, 0.006)   # 常時のヒスノイズ

    return buf


def normalize_and_clip(buf: list[float], target_peak: float = 0.89) -> array:
    peak = max((abs(x) for x in buf), default=1.0) or 1.0
    pre = target_peak / peak
    out = array("h")
    for x in buf:
        y = soft_clip(x * pre * 1.1)
        out.append(int(max(-1.0, min(1.0, y)) * 32767))
    return out


def write_wav(path: str, samples: array) -> None:
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(samples.tobytes())


def main() -> None:
    ap = argparse.ArgumentParser(description="チル lo-fi ビート生成")
    ap.add_argument("--bpm", type=int, default=80, help="テンポ(既定80)")
    ap.add_argument("--bars", type=int, default=16, help="小節数(既定16)")
    ap.add_argument("--seed", type=int, default=7, help="乱数シード")
    ap.add_argument("--out", default="chill_beat.wav", help="出力WAVパス")
    args = ap.parse_args()

    print(f"generating: bpm={args.bpm} bars={args.bars} -> {args.out}")
    buf = build_beat(args.bpm, args.bars, args.seed)
    samples = normalize_and_clip(buf)
    write_wav(args.out, samples)
    dur = len(samples) / SAMPLE_RATE
    print(f"done: {args.out}  ({dur:.1f} sec, {len(samples)} samples)")


if __name__ == "__main__":
    main()
