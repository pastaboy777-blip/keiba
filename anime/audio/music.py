"""Score for 「最後の一完歩」 -> build/audio/music.wav (48 kHz stereo, exactly 60.0 s).

Composed in code, rendered with tinysoundfont + MuseScore_General.sf2 (MIT), mixed in numpy
(per-stem gain automation, filters, synthetic-IR convolution hall, glitch stutter, hard cut).

Tempo map (beat-exact against timeline.BEATS):
  A  s01  0.30-6.00   8 beats  84.21 BPM  (AI arp, B minor)
  B  s02  6.00-15.00 12 beats  80.00 BPM  (piano motif, D major)
  C  s03 15.00-18.50  free drone -> reverse swell into the gate clang (18.50 = hit)
  D  s04 18.50-29.60 26 beats 140.54 BPM  (2/4 hit bar + 6 bars 4/4, B minor gallop build)
  E  s04 29.60-33.00  8 beats 141.18 BPM  ("今だ!" = downbeat, full drive, G -> A)
  F  s05 33.00-40.20 17 beats 141.67 BPM  (4+4+4+5, motif triumphant in D; 40.20 = downbeat)
  G  s05 40.20-45.00 12 beats 150.00 BPM  (key change to E, accel; 41.40 = beat 4 -> glitch)
  H  s06 45.00-47.40  near-silence (hard cut at 45.00, faint harmonic)
  I  s06/7 47.40-57.40 12 beats 72.00 BPM (win-call tutti, then piano motif; 57.40 = downbeat)
  J  57.40-60.00 final E(add9) chord, faded to digital zero at 60.00
"""
import os
import sys
import time
import multiprocessing as mp

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dsp  # noqa: E402
from dsp import SR, N  # noqa: E402
from timeline import BEATS  # noqa: E402

SF2 = os.path.join(dsp.ROOT, "models", "MuseScore_General.sf2")
SF2_URL = "https://huggingface.co/datasets/mileslilly/soundfonts/resolve/main/MuseScore_General.sf2"
TAIL = 6 * SR  # render tail beyond 60 s so releases/reverb are natural before the fade

# ----------------------------------------------------------------------------------------------
# music theory helpers
_NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def n(name):
    """'F#4' -> MIDI key (C4 = 60)."""
    if isinstance(name, int):
        return name
    p = _NOTE[name[0]]
    i = 1
    while i < len(name) and name[i] in "#b":
        p += 1 if name[i] == "#" else -1
        i += 1
    return p + 12 * (int(name[i:]) + 1)


def keys(spec):
    if isinstance(spec, (list, tuple)):
        return [n(s) for s in spec]
    if isinstance(spec, str) and " " in spec:
        return [n(s) for s in spec.split()]
    return [n(spec)]


class Sec:
    def __init__(self, t0, t1, beats):
        self.t0, self.t1, self.beats = t0, t1, beats
        self.spb = (t1 - t0) / beats
        self.bpm = 60.0 / self.spb

    def t(self, b):
        return self.t0 + b * self.spb

    def d(self, b):
        return b * self.spb


SEC = {
    "A": Sec(0.3, 6.0, 8),
    "B": Sec(6.0, 15.0, 12),
    "C": Sec(15.0, 18.5, 4),
    "D": Sec(BEATS["gate_clang"], BEATS["fourth_corner_go"], 26),
    "E": Sec(BEATS["fourth_corner_go"], BEATS["straight_start"], 8),
    "F": Sec(BEATS["straight_start"], BEATS["neck_and_neck"], 17),
    "G": Sec(BEATS["neck_and_neck"], BEATS["finish_line"], 12),
    "I": Sec(BEATS["win_call"], BEATS["title_card"], 12),
}


class Track:
    def __init__(self, name, prog, bank=0, drums=False, pan=0.0, gain=0.0, rev=0.25, width=1.0,
                 lp=None, hp=None, delay=None, pre=0.0):
        self.name, self.prog, self.bank, self.drums = name, prog, bank, drums
        self.pre = pre  # attack compensation: notes start this much early so the sample's attack lands on time
        self.pan, self.gain, self.rev, self.width = pan, gain, rev, width
        self.lp, self.hp, self.delay = lp, hp, delay
        self.notes = []  # (t, dur, key, vel)
        self.auto = []   # (t, dB) gain automation

    def add(self, t, dur, k, vel):
        self.notes.append((float(t), float(max(dur, 0.02)), int(k), int(np.clip(vel, 1, 127))))


class Score:
    def __init__(self, seed=7):
        self.tr = {}
        self.rng = np.random.default_rng(seed)

    def track(self, name, *a, **kw):
        self.tr[name] = Track(name, *a, **kw)
        return self.tr[name]

    def note(self, name, sec, beat, dur, pitches, vel, legato=0.98, jit=0.006, vj=6, abs_t=False):
        tr = self.tr[name]
        t = beat if abs_t else sec.t(beat)
        d = dur if abs_t else sec.d(dur)
        for k in keys(pitches):
            dt = self.rng.uniform(-jit, jit) if jit else 0.0
            dv = int(self.rng.integers(-vj, vj + 1)) if vj else 0
            tr.add(max(0.0, t + dt), d * legato, k, vel + dv)

    def seq(self, name, sec, beat, items, vel, shift=0, legato=0.97, accent=None):
        """items: [(pitch or None(rest), dur_beats), ...]"""
        b = beat
        for i, (p, d) in enumerate(items):
            if p is not None:
                v = vel(i) if callable(vel) else vel
                for k in keys(p):
                    self.note(name, sec, b, d, [k + shift], v, legato=legato)
            b += d
        return b

    def roll(self, name, sec, b0, b1, pitch, v0, v1, rate=8, jit=0.0):
        """Repeated-note roll (rate notes per beat), velocity ramp."""
        cnt = int(round((b1 - b0) * rate))
        for i in range(cnt):
            b = b0 + i / rate
            v = v0 + (v1 - v0) * i / max(1, cnt - 1)
            self.note(name, sec, b, 1.5 / rate, pitch, v, jit=jit, vj=4)


# ----------------------------------------------------------------------------------------------
# the motif (written in D major, beats). Introduced softly on piano in s02, triumphant in s05,
# (transposed to E) broad at the win call and gentle in the epilogue.
M1 = [("A4", 1), ("D5", .5), ("E5", .5), ("F#5", 2)]            # "rising stride"
M2 = [("E5", 1), ("D5", .5), ("B4", .5), ("A4", 2)]              # answer
M3 = [("G4", 1), ("B4", .5), ("D5", .5), ("G5", 1.5), ("F#5", .5)]  # reach


def tr_items(items, semis):
    return [(None if p is None else n(p) + semis, d) for p, d in items]


def compose():
    S = Score()
    T = S.track
    # --- instruments -----------------------------------------------------------------------
    T("ai_pad", 94, pan=0.0, gain=-12, rev=0.45, width=1.3)
    T("ai_arp", 80, pan=0.0, gain=-9, rev=0.25, lp=3200, delay=(0.2672, 0.35))
    T("ai_sub", 38, gain=-9, rev=0.05, lp=400)
    T("ai_bell", 98, pan=0.15, gain=-15, rev=0.5)
    T("piano", 0, pan=0.05, gain=6, rev=0.32)
    T("harp", 46, pan=-0.35, gain=-3, rev=0.35)
    T("str_pad", 49, pan=0.0, gain=-7, rev=0.4, width=1.2, pre=0.07)
    T("str_trem", 44, pan=0.2, gain=-9, rev=0.35, pre=0.04)
    T("str_lo", 41, pan=0.25, gain=1, rev=0.25)        # violas/celli gallop ostinato (fast-attack viola)
    T("pizz", 45, pan=0.35, gain=-6, rev=0.25)         # pizzicato doubling for bite
    T("str_16", 41, pan=-0.25, gain=0, rev=0.3)        # 16th ostinato
    T("vln", 48, pan=-0.3, gain=3, rev=0.35, pre=0.05)  # violin melody
    T("bass", 43, pan=0.1, gain=-5, rev=0.2, pre=0.02)
    T("horn", 60, pan=0.3, gain=-5, rev=0.4, pre=0.025)
    T("tpt", 56, pan=-0.1, gain=-6, rev=0.35)
    T("brass", 61, pan=0.0, gain=-9, rev=0.35, pre=0.03)
    T("lowbrass", 57, pan=0.15, gain=-8, rev=0.3, pre=0.03)
    T("tuba", 58, pan=0.1, gain=-8, rev=0.25, pre=0.02)
    T("choir", 52, pan=0.0, gain=-5, rev=0.5, width=1.3, pre=0.04)
    T("timp", 47, pan=-0.1, gain=-6, rev=0.3)
    T("taiko", 116, pan=0.0, gain=-2, rev=0.25)
    T("kit", 48, bank=128, drums=True, pan=0.0, gain=-7, rev=0.3)
    T("glock", 9, pan=0.2, gain=-14, rev=0.5)
    T("celesta", 8, pan=-0.2, gain=-10, rev=0.5)
    T("crystal", 98, pan=0.0, gain=-13, rev=0.4, lp=5000, delay=(0.3125, 0.3))

    A, B, C, D, E, F, G, I = (SEC[k] for k in "ABCDEFGI")

    # ======================= s01: AI boot (cold, digital) ==================================
    S.note("ai_bell", A, 0, 3, "B5 F#6", 70)
    S.note("ai_pad", A, 0, 4, "B2 F#3 C#4 D4", 70, jit=0)
    S.note("ai_pad", A, 4, 4.4, "G2 D3 F#3 B3 C#4", 70, jit=0)
    arp1 = ["B4", "F#5", "D5", "C#5"]
    arp2 = ["G4", "D5", "B4", "F#5"]
    for i in range(30):
        b = 0.5 + i * 0.25
        pat = arp1 if b < 4 else arp2
        oct_ = 12 if (i // 8) % 2 == 1 else 0
        S.note("ai_arp", A, b, 0.2, [n(pat[i % 4]) + oct_], 55 + (i % 4 == 0) * 15, jit=0, vj=0)
    for b in range(1, 8):
        S.note("ai_sub", A, b, 0.5, "B1" if b < 4 else "G1", 90, jit=0)

    # ======================= s02: stable (tender, motif on piano) ==========================
    # harp entry on the cross-fade
    for i, p in enumerate(["D3", "A3", "D4", "F#4", "A4", "D5", "F#5"]):
        S.note("harp", B, i * 0.25, 3, p, 60 + i * 3)
    S.note("str_pad", B, 0, 4, "D3 A3 F#4", 48)
    S.note("str_pad", B, 4, 4, "B2 F#3 D4 A4", 46)
    S.note("str_pad", B, 8, 4, "G2 D3 B3 E4", 44)
    S.note("bass", B, 0, 4, "D2", 45)
    S.note("bass", B, 4, 4, "B1", 45)
    S.note("bass", B, 8, 3.5, "G1", 42)
    lh = [["D3", "A3", "F#4", "A3"], ["B2", "F#3", "D4", "F#3"], ["G2", "D3", "B3", "D3"]]
    for bar in range(3):
        for e in range(8):
            if bar == 2 and e >= 6:
                break
            S.note("piano", B, bar * 4 + e * 0.5, 1.2, lh[bar][e % 4], 42 + (e % 4 == 0) * 8, legato=1)
    S.seq("piano", B, 0, M1, 62)
    S.seq("piano", B, 4, M2, 58)
    S.seq("piano", B, 8, [("G4", 1), ("B4", .5), ("D5", .5), ("G5", 1.2)], 55)
    S.note("piano", B, 11.2, 0.8, "F#5", 45)
    S.note("harp", B, 8, 3, "G2 D3", 55)

    # ======================= s03: gate (silence, heartbeat, tension) =======================
    S.note("bass", C, 0.3, 3.2, "B1", 50, jit=0)
    S.note("str_trem", C, 0.3, 3.0, "B2 F#3", 40, jit=0)
    S.note("str_trem", C, 1.0, 2.2, "C5 F#5", 30, jit=0)   # b9 colour, very soft

    # ======================= s04: race build (B minor gallop) ==============================
    # gate CLANG hit at 18.5 (beat 0 of D)
    S.note("lowbrass", D, 0, 1.6, "B1 B2 F#3", 120, jit=0)
    S.note("tuba", D, 0, 1.6, "B0 B1", 118, jit=0)
    S.note("horn", D, 0, 1.6, "B3 D4 F#4", 115, jit=0)
    S.note("timp", D, 0, 1.0, "B1", 127, jit=0)
    S.note("taiko", D, 0, 1.0, "C3", 127, jit=0, vj=0)
    S.note("kit", D, 0, 4, "B1", 120, jit=0)    # key 35 concert BD
    S.note("kit", D, 0, 6, "A3", 115, jit=0)    # key 57 crash
    S.note("str_lo", D, 0, 0.5, "B1 B2 B3", 125, jit=0)
    S.note("str_trem", D, 0.0, 2.0, "B3 F#4 B4 D5", 80, jit=0)

    harm = ["Bm", "Bm", "G", "G", "Em", "F#"]
    root = {"Bm": "B1", "G": "G1", "Em": "E1", "F#": "F#1"}
    low = {"Bm": ["B2", "F#3"], "G": ["G2", "D3"], "Em": ["E2", "B2"], "F#": ["F#2", "C#3"]}
    trem = {"Bm": "D5 F#5 B5", "G": "D5 G5 B5", "Em": "E5 G5 B5", "F#": "C#5 F#5 A#5"}
    hornc = {"Bm": "B3 D4 F#4", "G": "B3 D4 G4", "Em": "B3 E4 G4", "F#": "A#3 C#4 F#4"}
    for bar, h in enumerate(harm):
        b0 = 2 + bar * 4
        hush = bar in (3, 4)  # 「まだ……まだだよ。」 — hold back
        vbase = 72 + bar * 7 - (10 if hush else 0)
        S.note("bass", D, b0, 4, root[h], vbase + 5, legato=1)
        for beat in range(4):
            for off, dd, acc in ((0, 0.45, 12), (0.5, 0.22, 0), (0.75, 0.22, 4)):  # gallop: dum da-da
                S.note("str_lo", D, b0 + beat + off, dd, low[h], vbase + acc, jit=0.003, vj=3)
        # timpani on 1 & 3
        S.note("timp", D, b0, 0.9, root[h].replace("1", "2"), vbase + 10)
        S.note("timp", D, b0 + 2, 0.9, root[h].replace("1", "2"), vbase)
        # taiko pattern DON . . (ka) DON
        S.note("taiko", D, b0, 0.5, "C3", vbase + 20, vj=4)
        S.note("taiko", D, b0 + 1.5, 0.3, "G3", vbase - 5, vj=4)
        S.note("taiko", D, b0 + 2.5, 0.5, "C3", vbase + 10, vj=4)
        if bar >= 2:
            S.note("horn", D, b0, 4, hornc[h], vbase - 5, legato=1)
            S.note("str_trem", D, b0, 4, trem[h], vbase - 10 + (20 if bar == 5 else 0), legato=1)
        if bar >= 1 and not hush:
            S.note("choir", D, b0, 4, "B3 F#4" if h == "Bm" else ("B3 D4" if h == "G" else "A#3 C#4"), 50,
                   legato=1)
    # bar 6 (F#) crescendo: timpani roll, snare roll, rising scale ending on G at 29.6
    S.roll("timp", D, 22, 26, "F#2", 40, 92, rate=8)
    S.roll("kit", D, 23, 26, "D2", 25, 90, rate=8)   # key 38 concert snare
    scale = ["F#3", "G3", "A#3", "B3", "C#4", "D4", "E4", "F#4", "G4", "A#4", "B4", "C#5", "D5", "E5", "F#5",
             "A#5"]
    for i, p in enumerate(scale):
        S.note("str_16", D, 22 + i * 0.25, 0.3, [p, n(p) - 12] if i < 8 else [p], 70 + i * 3, jit=0.002)
    S.note("choir", D, 22, 4, "F#3 A#3 C#4 F#4", 70, legato=1)

    # ======================= 29.6 "今だ!" full drive: G -> A ================================
    for i, (h, rt, chord, arp) in enumerate([
            ("G", "G1", "G3 B3 D4 G4", ["G4", "D5", "B4", "D5"]),
            ("A", "A1", "A3 C#4 E4 A4", ["A4", "E5", "C#5", "E5"])]):
        b0 = i * 4
        S.note("bass", E, b0, 4, rt, 110, legato=1)
        S.note("tuba", E, b0, 1.5, rt, 110)
        S.note("lowbrass", E, b0, 1.5, rt.replace("1", "2") + " " + rt.replace("1", "3"), 112)
        S.note("choir", E, b0, 4, chord, 88, legato=1)
        S.note("horn", E, b0, 2, chord, 110)
        for st in (1.5, 2.5, 3.5):
            S.note("brass", E, b0 + st, 0.35, chord, 100)
        for beat in range(4):
            for off, dd, acc in ((0, 0.45, 12), (0.5, 0.22, 0), (0.75, 0.22, 4)):
                S.note("str_lo", E, b0 + beat + off, dd, [rt.replace("1", "2"), rt.replace("1", "3")], 100 + acc,
                       jit=0.002, vj=3)
            for s16 in range(4):
                if i == 1 and beat == 3:
                    break
                S.note("str_16", E, b0 + beat + s16 * 0.25, 0.22, arp[s16], 92 + (s16 == 0) * 10, jit=0.002)
            S.note("taiko", E, b0 + beat, 0.4, "C3", 118 if beat % 2 == 0 else 100)
            S.note("taiko", E, b0 + beat + 0.5, 0.3, "G3", 85)
            S.note("taiko", E, b0 + beat + 0.75, 0.3, "G3", 75)
        S.note("timp", E, b0, 0.9, rt.replace("1", "2"), 118)
        S.note("timp", E, b0 + 2, 0.9, rt.replace("1", "2"), 100)
        S.note("kit", E, b0, 4, "B1", 118)   # BD
    S.note("kit", E, 0, 5, "A3", 122)        # crash at 29.6
    S.note("kit", E, 4, 4, "C#3", 105)       # crash 2 (key 49)
    # horn call rising: D4 E4 F#4 G4 | A4 -- B4 C#5
    S.seq("horn", E, 2, [("D4", .5), ("E4", .5), ("F#4", .5), ("G4", .5)], 108)
    S.seq("tpt", E, 6, [("A4", .5), ("B4", .5), ("C#5", .5), ("E5", .5)], 100)
    for i, p in enumerate(["A4", "B4", "C#5", "D5", "E5", "F#5", "G5", "A5"]):  # run into 33.0
        S.note("vln", E, 6 + i * 0.25, 0.3, p, 90 + i * 4, jit=0.002)
    S.roll("kit", E, 6, 8, "D2", 60, 118, rate=8)

    # ======================= s05: final straight, motif triumphant in D ====================
    fb = [0, 4, 8, 12]
    fharm = [("D", "D1", "D3 F#3 A3 D4"), ("Bm7", "B0", "B2 F#3 A3 D4"), ("G", "G1", "G2 D3 G3 B3"),
             ("A", "A1", "A2 E3 A3 C#4")]
    mel = [M1, M2, M3, [("E5", 1), ("D5", .5), ("C#5", .5), ("D#5", 1), ("F#5", 1), ("A5", 1)]]
    for bi, (b0, (h, rt, ch), m) in enumerate(zip(fb, fharm, mel)):
        blen = 5 if bi == 3 else 4
        S.seq("vln", F, b0, m, 108, shift=12)
        S.seq("vln", F, b0, m, 100)
        S.seq("horn", F, b0, m, 112)
        if bi >= 2:
            S.seq("tpt", F, b0, m, 104)
        S.note("bass", F, b0, blen, rt, 110, legato=1)
        S.note("bass", F, b0, blen, n(rt) + 12, 100, legato=1)
        S.note("choir", F, b0, blen if bi < 3 else 2, keys(ch)[1:] + [keys(ch)[-1] + 12], 92, legato=1)
        S.note("brass", F, b0, 1.2, ch, 100)
        S.note("lowbrass", F, b0, 1.5, [n(rt) + 12, n(rt) + 24], 108)
        S.note("str_pad", F, b0, blen, ch, 90, legato=1)
        chord_k = keys(ch)
        for beat in range(blen):
            for off, dd, acc in ((0, 0.45, 10), (0.5, 0.22, 0), (0.75, 0.22, 4)):
                S.note("str_lo", F, b0 + beat + off, dd, [n(rt) + 12, n(rt) + 24], 98 + acc, jit=0.002, vj=3)
            for s16 in range(4):
                k = chord_k[[1, 3, 2, 3][s16]] + 12
                S.note("str_16", F, b0 + beat + s16 * 0.25, 0.22, [k], 84 + (s16 == 0) * 10, jit=0.002)
            S.note("taiko", F, b0 + beat, 0.4, "C3", 115 if beat % 2 == 0 else 96)
            S.note("taiko", F, b0 + beat + 0.5, 0.3, "G3", 82)
        S.note("timp", F, b0, 0.9, n(rt) + 12 if n(rt) + 12 >= 40 else n(rt) + 24, 115)
        S.note("timp", F, b0 + 2, 0.9, n(rt) + 12 if n(rt) + 12 >= 40 else n(rt) + 24, 98)
        S.note("kit", F, b0, 4, "B1", 115)
        S.note("kit", F, b0, 3.5, "A3" if bi % 2 == 0 else "C#3", 100 + (bi == 0) * 22)
    # bar 4 second half: B7 (pivot to E) for beats 14-17
    S.note("choir", F, 14, 3, "B3 D#4 F#4 A4", 100, legato=1)
    S.note("brass", F, 14, 3, "B2 D#3 F#3 A3", 108, legato=1)
    S.note("bass", F, 14, 3, "B1", 112, legato=1)
    S.note("lowbrass", F, 14, 3, "B1 B2", 112, legato=1)
    S.roll("timp", F, 14, 17, "B2", 70, 127, rate=8)
    S.roll("kit", F, 14, 17, "D2", 60, 122, rate=8)

    # ======================= 40.2 neck-and-neck: E major, 150 BPM ==========================
    gharm = [("E", "E1", "E3 G#3 B3 E4", 4), ("C#m", "C#1", "C#3 G#3 C#4 E4", 4), ("A", "A0", "A2 E3 A3 C#4", 2),
             ("B", "B0", "B2 F#3 B3 D#4", 2)]
    GM = [[("B4", 1), ("E5", .5), ("F#5", .5), ("G#5", 2)],
          [("F#5", 1), ("E5", .5), ("C#5", .5), ("B4", 2)],
          [("A4", 1), ("C#5", .5), ("E5", .5), ("F#5", 1), ("G#5", .5), ("A#5", .5)]]
    for bi, m in enumerate(GM):
        S.seq("vln", G, bi * 4, m, 115, shift=12)
        S.seq("vln", G, bi * 4, m, 108)
        S.seq("horn", G, bi * 4, m, 120)
        S.seq("tpt", G, bi * 4, m, 112)
    b0 = 0
    for h, rt, ch, blen in gharm:
        S.note("bass", G, b0, blen, rt if n(rt) >= 28 else n(rt) + 12, 118, legato=1)
        S.note("bass", G, b0, blen, n(rt) + 12, 108, legato=1)
        S.note("choir", G, b0, blen, keys(ch)[1:] + [keys(ch)[-1] + 12], 110, legato=1)
        S.note("str_pad", G, b0, blen, ch, 100, legato=1)
        S.note("brass", G, b0, blen, ch, 104, legato=1)
        S.note("lowbrass", G, b0, min(blen, 2), [n(rt) + 12, n(rt) + 24], 116)
        S.note("tuba", G, b0, min(blen, 2), [n(rt) + 12], 112)
        ck = keys(ch)
        for beat in range(blen):
            for off, dd, acc in ((0, 0.45, 10), (0.5, 0.22, 0), (0.75, 0.22, 4)):
                S.note("str_lo", G, b0 + beat + off, dd, [n(rt) + 12, n(rt) + 24], 108 + acc, jit=0.002, vj=3)
            for s16 in range(4):
                S.note("str_16", G, b0 + beat + s16 * 0.25, 0.2, [ck[[1, 3, 2, 3][s16]] + 12], 96 + (s16 == 0) * 10,
                       jit=0.002)
            S.note("taiko", G, b0 + beat, 0.4, "C3", 124 if beat % 2 == 0 else 104)
            S.note("taiko", G, b0 + beat + 0.5, 0.3, "G3", 92)
            S.note("taiko", G, b0 + beat + 0.75, 0.3, "G3", 80)
            S.note("kit", G, b0 + beat, 0.5, "B1", 112 if beat == 0 else 90)
        tk = n(rt) + 12 if n(rt) + 12 >= 40 else n(rt) + 24
        S.note("timp", G, b0, 0.9, tk, 124)
        b0 += blen
    S.note("kit", G, 0, 4, "A3", 127)
    S.note("kit", G, 4, 4, "C#3", 115)
    S.roll("timp", G, 8, 12, "B2", 80, 127, rate=8)
    S.roll("kit", G, 8, 12, "D2", 70, 127, rate=8)
    S.note("kit", G, 8, 4, "B3", 100)   # key 59 ride/suspended wash

    # ======================= s06: 45.0 near-silence, faint harmonic ========================
    S.note("str_pad", None, 45.35, 2.1, "B5 F#6", 38, abs_t=True, jit=0)

    # ======================= 47.4 win call tutti (E) -> epilogue ============================
    S.note("kit", I, 0, 6, "A3", 127, jit=0)
    S.note("kit", I, 0, 4, "B1", 127, jit=0)
    S.note("taiko", I, 0, 1, "C3", 127, jit=0)
    S.note("timp", I, 0, 1, "E2", 127, jit=0)
    S.roll("timp", I, 0.25, 3.0, "E2", 100, 60, rate=6)
    S.seq("tpt", I, 0, [("B4", 1), ("E5", .5), ("F#5", .5), ("G#5", 2)], 118)
    S.seq("horn", I, 0, [("B4", 1), ("E5", .5), ("F#5", .5), ("G#5", 2)], 116)
    S.seq("vln", I, 0, [("B5", 1), ("E6", .5), ("F#6", .5), ("G#6", 2)], 112)
    S.note("horn", I, 0, 4, "E4 G#4", 100, legato=1)
    S.note("brass", I, 0, 4, "E3 B3 E4 G#4", 110, legato=1)
    S.note("lowbrass", I, 0, 4, "E2 B2", 115, legato=1)
    S.note("tuba", I, 0, 4, "E1 E2", 112, legato=1)
    S.note("choir", I, 0, 4, "E4 G#4 B4 E5", 112, legato=1)
    S.note("str_pad", I, 0, 4, "E3 B3 E4 G#4 B4", 110, legato=1)
    S.note("str_trem", I, 0, 4, "G#5 B5 E6", 100, legato=1)
    S.note("bass", I, 0, 4, "E1 E2", 115, legato=1)
    for i, p in enumerate(["E4", "G#4", "B4", "E5", "G#5", "B5", "E6"]):
        S.note("harp", I, 0.1 + i * 0.12, 3, p, 90)
    # epilogue: bar 2 F#m7 -> B, bar 3 A -> B(sus4) -> E at 57.4
    S.note("str_pad", I, 4, 2, "F#3 A3 C#4 E4", 55, legato=1)
    S.note("str_pad", I, 6, 2, "B2 F#3 A3 D#4", 52, legato=1)
    S.note("str_pad", I, 8, 2, "A2 E3 A3 C#4", 55, legato=1)
    S.note("str_pad", I, 10, 1, "B2 F#3 B3 E4", 55, legato=1)
    S.note("str_pad", I, 11, 1, "B2 F#3 A3 D#4", 55, legato=1)
    S.note("bass", I, 4, 2, "F#1", 50, legato=1)
    S.note("bass", I, 6, 2, "B1", 50, legato=1)
    S.note("bass", I, 8, 2, "A1", 50, legato=1)
    S.note("bass", I, 10, 2, "B1", 52, legato=1)
    S.seq("piano", I, 4, [("F#5", 1), ("E5", .5), ("C#5", .5), ("B4", 2)], 60)
    S.seq("piano", I, 8, [("A4", 1), ("C#5", .5), ("E5", .5), ("F#5", 1.5), ("D#5", .5)], 62)
    plh = [(4, ["F#2", "C#3", "A3", "C#4"]), (6, ["B1", "F#2", "D#3", "A3"]), (8, ["A1", "E2", "C#3", "E3"]),
           (10, ["B1", "F#2", "B2", "D#3"])]
    for b0, arp in plh:
        for e in range(4):
            S.note("piano", I, b0 + e * 0.5, 1.0, arp[e], 40 + (e == 0) * 8, legato=1)
    for i, p in enumerate(["F#3", "C#4", "E4", "A4"]):
        S.note("harp", I, 4 + i * 0.25, 2, p, 50)
    for i, p in enumerate(["A3", "E4", "A4", "C#5"]):
        S.note("harp", I, 8 + i * 0.25, 2, p, 50)
    # AI arp (reconciled, in E) under L12
    ai = ["C#5", "F#5", "A5", "E5", "B4", "F#5", "A5", "D#5"]
    for i in range(16):
        S.note("crystal", I, 4 + i * 0.25, 0.2, ai[(i // 4) % 2 * 4 + i % 4], 50, jit=0, vj=0)
    # 57.4 title card: E(add9) resolution, sparkle
    S.note("piano", I, 12, 3.0, "E5", 64)
    S.note("piano", I, 12, 3.0, "E2 B2 E3 G#3 B3 F#4", 50)
    S.note("str_pad", I, 12, 3.2, "E2 B2 G#3 B3 E4 F#4 B4", 62, legato=1)
    S.note("choir", I, 12, 3.2, "G#4 B4 E5", 55, legato=1)
    S.note("bass", I, 12, 3.2, "E1", 55, legato=1)
    for i, p in enumerate(["E6", "G#6", "B6", "E7", "F#7"]):
        S.note("celesta", I, 12 + i * 0.3, 1.5, p, 70 - i * 4)
        S.note("glock", I, 12.15 + i * 0.3, 1.5, p, 55 - i * 3)
    for i, p in enumerate(["E3", "B3", "E4", "G#4", "B4", "E5", "F#5", "G#5", "B5"]):
        S.note("harp", I, 12 + i * 0.09, 3, p, 62)
    return S


# ----------------------------------------------------------------------------------------------
# rendering (one tinysoundfont Synth per worker process)
_SYN = None
_SFID = None


def _init():
    global _SYN, _SFID
    import tinysoundfont
    _SYN = tinysoundfont.Synth(samplerate=SR)
    _SFID = _SYN.sfload(SF2, max_voices=256)


def _render(args):
    name, prog, bank, drums, notes, nsamp = args
    s = _SYN
    s.sounds_off()
    s.generate(4096)
    s.program_select(0, _SFID, bank, prog, is_drums=drums)
    ev = []
    for t, d, k, v in notes:
        ev.append((int(round(t * SR)), 1, k, v))
        ev.append((int(round((t + d) * SR)), 0, k, 0))
    ev.sort(key=lambda e: (e[0], e[1]))
    out = np.zeros((nsamp, 2), dtype=np.float32)
    pos = 0
    for smp, typ, k, v in ev:
        smp = min(smp, nsamp)
        if smp > pos:
            out[pos:smp] = np.frombuffer(s.generate(smp - pos), dtype=np.float32).reshape(-1, 2)
            pos = smp
        if typ == 1:
            s.noteon(0, k, v)
        else:
            s.noteoff(0, k)
    if pos < nsamp:
        out[pos:] = np.frombuffer(s.generate(nsamp - pos), dtype=np.float32).reshape(-1, 2)
    s.notes_off()
    return name, out


def ensure_sf2():
    if os.path.exists(SF2) and os.path.getsize(SF2) > 200_000_000:
        return
    import urllib.request
    os.makedirs(os.path.dirname(SF2), exist_ok=True)
    print("downloading", SF2_URL)
    urllib.request.urlretrieve(SF2_URL, SF2 + ".part")
    os.replace(SF2 + ".part", SF2)


def reverse_swell(stem_crash, end_t, length, NN):
    """Reverse a rendered crash so that its peak lands exactly on end_t."""
    x = stem_crash[: int(length * SR)][::-1]
    out = np.zeros((NN, 2))
    return dsp.place(out, x, end_t - len(x) / SR)


def stutter(x, t0, t1, slice_len=0.05):
    """AI glitch: repeat a short slice with bit-crush between t0 and t1."""
    i0, i1 = int(t0 * SR), int(t1 * SR)
    sl = x[i0:i0 + int(slice_len * SR)].copy()
    rep = np.tile(sl, (int(np.ceil((i1 - i0) / len(sl))), 1))[: i1 - i0]
    step = 6
    rep = np.repeat(rep[::step], step, axis=0)[: i1 - i0]
    rep = np.round(rep * 24) / 24
    fade = np.ones(i1 - i0)
    fade[:96] = np.linspace(0, 1, 96)
    fade[-96:] = np.linspace(1, 0, 96)
    for k in range(0, i1 - i0, len(sl)):
        g = 1.0 if (k // len(sl)) % 2 == 0 else 0.55
        rep[k:k + len(sl)] *= g
    x[i0:i1] = x[i0:i1] * (1 - fade[:, None]) + rep * fade[:, None]
    return x


def main():
    t_start = time.time()
    ensure_sf2()
    S = compose()
    NN = N + TAIL
    for tr in S.tr.values():   # pizzicato doubles the gallop ostinato's accented "dum" (first 16th of each beat)
        if tr.name == "str_lo":
            S.tr["pizz"].notes = [(t, 0.2, k, v) for t, d, k, v in tr.notes if d > 0.15]
    jobs = [(tr.name, tr.prog, tr.bank, tr.drums, [(max(0.0, t - tr.pre), d, k, v) for t, d, k, v in tr.notes], NN)
            for tr in S.tr.values() if tr.notes]
    jobs.append(("_crash", 48, 128, True, [(0.0, 5.0, n("A3"), 120)], 6 * SR))
    jobs.sort(key=lambda j: -len(j[4]))
    with mp.Pool(4, initializer=_init) as pool:
        stems = dict(pool.map(_render, jobs))
    print("rendered %d stems in %.1fs" % (len(stems), time.time() - t_start))

    B = BEATS
    hall = dsp.make_ir(t60=2.4, predelay=0.025, damp_hz=5500, seed=11)
    dry = np.zeros((NN, 2))
    wet_in = np.zeros((NN, 2))
    for name, tr in S.tr.items():
        if name not in stems:
            continue
        x = stems[name].astype(np.float64)
        if tr.hp:
            x = dsp.hp(x, tr.hp)
        if tr.lp:
            x = dsp.lp(x, tr.lp, 2)
        if tr.delay:
            dt, fb = tr.delay
            d = int(dt * SR)
            y = x.copy()
            for rep in range(1, 5):
                g = fb ** rep
                sh = np.zeros_like(x)
                sh[d * rep:] = x[: len(x) - d * rep]
                if rep % 2:
                    sh = sh[:, ::-1]  # ping-pong
                y += sh * g
            x = y
        x = dsp.stereo_balance(x, tr.pan, tr.width) * dsp.db(tr.gain)
        dry += x
        wet_in += x * tr.rev

    # reverse cymbal swells into the big hits
    crash = stems["_crash"].astype(np.float64)
    swells = np.zeros((NN, 2))
    for end_t, ln, g in ((B["gate_clang"], 1.6, 0.55), (B["fourth_corner_go"], 1.3, 0.45),
                         (B["straight_start"], 1.0, 0.35), (B["neck_and_neck"], 1.4, 0.5)):
        swells += reverse_swell(crash, end_t, ln, NN) * g
    swells = dsp.hp(swells, 300)
    swells = swells * dsp.db(-8)
    swells = swells + dsp.convolve(swells * 0.4, hall)

    wet = dsp.convolve(wet_in, hall) * 0.9
    mix = dry + wet

    # ---- section automation on the whole bus ----------------------------------------------
    g = dsp.curve([
        (0.0, -60), (0.3, -60), (0.35, 0), (5.2, 0), (6.0, 2), (6.6, 3),  # s01 -> s02
        (14.3, 3), (15.0, -5), (15.4, -8), (17.2, -4), (18.05, -12), (18.42, -12), (18.47, 0),
        (19.3, -3), (24.4, -3), (27.8, -3), (29.55, -2), (29.6, 0), (32.9, 0), (33.0, 3), (40.1, 3),
        (40.2, 4), (45.0, 4.5), (45.04, -70), (45.3, -70), (45.55, -8), (47.2, -8), (47.38, 0),
        (50.0, -1), (50.73, 0), (57.4, 0), (58.0, -1), (59.2, -18), (59.85, -50), (60.0, -120),
    ], NN, "db")
    mix *= g[:, None]
    mix += swells
    # s01 digital stems only in s01 (+ crossfade): handled by track timing; dampen arp tails into s02
    # glitch at the AI's "計算、不能" (41.4 = beat 4 of the E-major bar)
    mix = stutter(mix, B["ai_glitch"], B["ai_glitch"] + 0.32, 0.055)
    # short gated hall tail at the white flash, then near silence
    i45 = int(B["finish_line"] * SR)
    mix = mix[:N].copy()
    tail = (dry + wet)[i45: i45 + int(0.6 * SR)] * np.exp(-np.arange(int(0.6 * SR)) / (0.12 * SR))[:, None] * 0.35
    mix[i45: i45 + len(tail)] += tail
    mix[-1] = 0.0

    # gentle bus glue: soft-knee peak control + normalise
    pk = np.max(np.abs(mix))
    mix *= 0.85 / pk
    mix = np.tanh(mix * 1.15) / np.tanh(1.15)
    mix *= dsp.db(-1.0) / max(1e-9, dsp.true_peak(mix))
    mix = dsp.fit_length(mix, N)
    out = os.path.join(dsp.AUDIO_OUT, "music.wav")
    dsp.write_wav(out, mix)
    print("wrote", out, "%.2fs" % (len(mix) / SR), "LUFS %.1f" % dsp.lufs(mix), "tp %.2f dBFS" %
          dsp.to_db(dsp.true_peak(mix)), "(%.1fs)" % (time.time() - t_start))
    if "--stems" in sys.argv:
        for k, v in stems.items():
            dsp.write_wav(os.path.join(dsp.AUDIO_OUT, "stems", k + ".wav"), v[:N])
    if "--png" in sys.argv:
        dsp.spectrogram_png(mix, os.path.join(dsp.AUDIO_OUT, "music.png"), "music.wav", BEATS)
    for k, s in SEC.items():
        print("  sec %s %6.2f-%6.2f  %6.2f BPM" % (k, s.t0, s.t1, s.bpm))


if __name__ == "__main__":
    main()
