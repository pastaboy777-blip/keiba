"""Voice generation for 「最後の一完歩」.

Engine: Style-Bert-VITS2 (pip `style-bert-vits2` 2.5.0, CPU torch) — JP-Extra models.
Models (downloaded from huggingface.co into anime/models/, gitignored):
  BERT : ku-nlp/deberta-v2-large-japanese-char-wwm           -> models/bert/deberta-v2-large-japanese-char-wwm
  MIZUKI (美月, 19F) : litagin/sbv2_koharune_ami  (小春音アミ; styles ノーマル / ささやきB / るんるん)
  GEN (源さん, 65M)  : litagin/style_bert_vits2_jvnv  jvnv-M1-jp (lowest male), pitch-scaled down (~-2 st)
  ANN (実況, M)      : litagin/style_bert_vits2_jvnv  jvnv-M2-jp (brighter male; Surprise/Happy/Angry styles)
  AI  (KEIBA-AI, F)  : litagin/style_bert_vits2_jvnv  jvnv-F2-jp (adult female), flat intonation + robotic FX
QC   : openai/whisper-small (models/asr/whisper-small) transcribes every candidate; the candidate whose
       kana reading best matches the script (lowest CER) wins.  Several seeds per line are tried.

Setup (once):
  python3 -m venv --system-site-packages anime/models/venv
  anime/models/venv/bin/pip install torch style-bert-vits2 huggingface_hub librosa
  anime/models/venv/bin/pip uninstall -y pyopenjtalk-dict   # use system pyopenjtalk-plus (numpy-2 ABI)
  (models: see download() below; run with --download)
Run:
  anime/models/venv/bin/python anime/audio/voice_gen.py [--lines L01,L10] [--seeds 4] [--download]
Outputs: anime/build/voice/Lxx.wav (48 kHz mono PCM16, ~-1 dBFS peak) + manifest.json
"""
import os, sys, json, argparse, glob, re
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from timeline import LINES  # noqa: E402

MODELS = os.path.join(ROOT, "models")
OUT = os.path.join(ROOT, "build", "voice")
SR = 48000
BERT = os.path.join(MODELS, "bert", "deberta-v2-large-japanese-char-wwm")
ASR = os.path.join(MODELS, "asr", "whisper-small")

VOICES = {
    "MIZUKI": "sbv2/koharune/koharune-ami",
    "GEN": "sbv2/jvnv/jvnv-M1-jp",
    "ANN": "sbv2/jvnv/jvnv-M2-jp",
    "AI": "sbv2/jvnv/jvnv-F2-jp",
}

# Per-line direction. `say` overrides the reading text (reading only; meaning unchanged).
# length: SBV2 length scale (auto-shrunk to fit `max`). pitch/inton: SBV2 pitch_scale / intonation_scale.
# assist: emotional BERT "assist text" to colour delivery. fx: post-processing chain name.
DIRECTION = {
    "L01": dict(style="Neutral", w=1.0, sdp=0.0, noise=0.4, noise_w=0.6, length=0.95, inton=0.65,
                say="第十一レース。十四番、ハルカゼ。勝率、れいてんはちパーセント。推奨は、見送りです。", gap=0.07,
                fx="ai"),
    "L02": dict(style="Neutral", w=1.0, sdp=0.3, length=1.0, pitch=0.89, inton=0.95,
                assist="まあ、そう言うなって。こいつはな、根性だけは誰にも負けねえんだ。", aw=0.5, fx="gen"),
    "L03": dict(style="ノーマル", w=1.0, sdp=0.4, length=1.05, inton=1.05,
                assist="大丈夫だよ。ずっとそばにいるから、安心してね。", aw=0.5, fx="mizuki"),
    "L04": dict(style="Surprise", w=2.0, sdp=0.3, length=0.85, pitch=1.06, inton=1.25,
                assist="さあ始まった!いよいよだ!", aw=0.4, fx="ann"),
    "L05": dict(style="Surprise", w=2.0, sdp=0.3, length=0.85, pitch=1.04, inton=1.2,
                say="ハルカゼは、さいこうほう!ここからどうか!",
                assist="さあどうなる!まだわからないぞ!", aw=0.4, fx="ann"),
    "L06": dict(style="ささやきB（有声）", w=1.3, sdp=0.4, length=1.05,
                assist="しずかに、まだ我慢して、ひそひそ", aw=0.4, fx="whisper"),
    "L07": dict(style="ノーマル", w=1.0, sdp=0.5, length=0.9, pitch=1.07, inton=1.35,
                assist="いけっ!全力で!今しかない!", aw=0.6, fx="shout"),
    "L08": dict(style="Surprise", w=2.5, sdp=0.4, length=0.92, pitch=1.08, inton=1.3,
                say="直線コース!おおそとから、ハルカゼ!ハルカゼが来た!",
                assist="すごいぞ!来た来た来た!信じられない!", aw=0.5, fx="ann"),
    "L09": dict(style="Surprise", w=3.0, sdp=0.4, length=0.82, pitch=1.12, inton=1.35,
                assist="すごい!信じられない!とんでもないことになった!", aw=0.5, fx="ann"),
    "L10": dict(style="Neutral", w=1.0, sdp=0.0, noise=0.4, noise_w=0.6, length=0.9, inton=0.6,
                say="計算、不能。", fx="ai_glitch"),
    "L11": dict(style="Surprise", w=3.5, sdp=0.5, length=0.9, pitch=1.18, inton=1.45,
                say="ハルカゼ!差し切ったぁ!",
                assist="やったぁ!すごい!信じられない!奇跡だ!", aw=0.6, fx="ann_scream"),
    "L12": dict(style="Sad", w=1.2, sdp=0.1, noise=0.5, length=1.05, inton=0.8,
                fx="ai_soft"),
    "L13": dict(style="るんるん", w=1.0, sdp=0.4, length=1.0, inton=1.1,
                assist="ふふっ、ほらね、言ったとおりでしょ。うれしいな。", aw=0.5, fx="mizuki"),
}


# ----------------------------------------------------------------------------- download
def download():
    from huggingface_hub import snapshot_download
    snapshot_download("litagin/style_bert_vits2_jvnv", local_dir=os.path.join(MODELS, "sbv2/jvnv"),
                      allow_patterns=["jvnv-*-jp/*"])
    snapshot_download("litagin/sbv2_koharune_ami", local_dir=os.path.join(MODELS, "sbv2/koharune"))
    snapshot_download("ku-nlp/deberta-v2-large-japanese-char-wwm", local_dir=BERT,
                      ignore_patterns=["pytorch_model.bin"])
    snapshot_download("openai/whisper-small", local_dir=ASR,
                      allow_patterns=["*.json", "*.txt", "model.safetensors"])


# ----------------------------------------------------------------------------- DSP helpers
from scipy import signal  # noqa: E402


def resample(x, sr_in, sr_out):
    if sr_in == sr_out:
        return x
    from math import gcd
    g = gcd(sr_in, sr_out)
    return signal.resample_poly(x, sr_out // g, sr_in // g).astype(np.float32)


def trim(x, sr=SR, thresh_db=-42, pad=0.03):
    hop = int(sr * 0.005)
    n = len(x) // hop
    e = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, 1) + 1e-12)
    db = 20 * np.log10(e / (e.max() + 1e-9))
    idx = np.where(db > thresh_db)[0]
    if len(idx) == 0:
        return x
    a = max(0, idx[0] * hop - int(pad * sr))
    b = min(len(x), (idx[-1] + 1) * hop + int(pad * sr))
    y = x[a:b].copy()
    f = int(0.008 * sr)
    y[:f] *= np.linspace(0, 1, f)
    y[-f:] *= np.linspace(1, 0, f)
    return y


def squeeze_pauses(x, max_gap=0.25, sr=SR, thresh_db=-38):
    """Shorten internal silences longer than max_gap (keeps speech rate natural while fitting slots)."""
    hop = int(sr * 0.005)
    n = len(x) // hop
    e = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, 1) + 1e-12)
    sil = 20 * np.log10(e / (e.max() + 1e-9)) < thresh_db
    keep = int(max_gap * sr / hop)
    out, i, f = [], 0, int(0.006 * sr)
    last = 0
    while i < n:
        if sil[i]:
            j = i
            while j < n and sil[j]:
                j += 1
            if j - i > keep and i > 0 and j < n:
                a = i * hop + (keep // 2) * hop
                b = j * hop - (keep - keep // 2) * hop
                seg = x[last:a].copy()
                seg[-f:] *= np.linspace(1, 0, f)
                out.append(seg)
                last = b
                x = x.copy(); x[b:b + f] *= np.linspace(0, 1, f)
            i = j
        else:
            i += 1
    out.append(x[last:])
    return np.concatenate(out).astype(np.float32)


def biquad(kind, f0, q=0.707, gain_db=0.0, sr=SR):
    A = 10 ** (gain_db / 40)
    w = 2 * np.pi * f0 / sr
    al = np.sin(w) / (2 * q)
    c = np.cos(w)
    if kind == "hp":
        b = [(1 + c) / 2, -(1 + c), (1 + c) / 2]; a = [1 + al, -2 * c, 1 - al]
    elif kind == "lp":
        b = [(1 - c) / 2, 1 - c, (1 - c) / 2]; a = [1 + al, -2 * c, 1 - al]
    elif kind == "peak":
        b = [1 + al * A, -2 * c, 1 - al * A]; a = [1 + al / A, -2 * c, 1 - al / A]
    elif kind == "lowshelf":
        sa = 2 * np.sqrt(A) * al
        b = [A * ((A + 1) - (A - 1) * c + sa), 2 * A * ((A - 1) - (A + 1) * c), A * ((A + 1) - (A - 1) * c - sa)]
        a = [(A + 1) + (A - 1) * c + sa, -2 * ((A - 1) + (A + 1) * c), (A + 1) + (A - 1) * c - sa]
    elif kind == "highshelf":
        sa = 2 * np.sqrt(A) * al
        b = [A * ((A + 1) + (A - 1) * c + sa), -2 * A * ((A - 1) + (A + 1) * c), A * ((A + 1) + (A - 1) * c - sa)]
        a = [(A + 1) - (A - 1) * c + sa, 2 * ((A - 1) - (A + 1) * c), (A + 1) - (A - 1) * c - sa]
    b = np.array(b) / a[0]; a = np.array(a) / a[0]
    return b, a


def eq(x, *specs):
    for s in specs:
        b, a = biquad(*s)
        x = signal.lfilter(b, a, x)
    return x.astype(np.float32)


def compress(x, thresh_db=-18, ratio=4.0, attack=0.003, release=0.08, makeup=True, sr=SR):
    ax = np.abs(x)
    # envelope follower (vectorised-ish via lfilter on two passes)
    a_att = np.exp(-1 / (attack * sr)); a_rel = np.exp(-1 / (release * sr))
    env = np.zeros_like(ax); v = 0.0
    for i, s in enumerate(ax):
        v = a_att * v + (1 - a_att) * s if s > v else a_rel * v + (1 - a_rel) * s
        env[i] = v
    edb = 20 * np.log10(env + 1e-9)
    over = np.maximum(0, edb - thresh_db)
    gdb = -over * (1 - 1 / ratio)
    y = x * 10 ** (gdb / 20)
    return y.astype(np.float32)


def normalize(x, peak_db=-1.0):
    p = np.max(np.abs(x)) + 1e-9
    return (x * (10 ** (peak_db / 20) / p)).astype(np.float32)


def comb(x, delay_ms, fb, mix, sr=SR):
    d = int(sr * delay_ms / 1000)
    b = np.zeros(d + 1); b[0] = 1
    a = np.zeros(d + 1); a[0] = 1; a[d] = -fb
    y = signal.lfilter(b, a, x) * (1 - fb)
    return ((1 - mix) * x + mix * y).astype(np.float32)


def chorus(x, sr=SR, voices=((11, 0.9, 0.22), (17, 0.6, 0.18)), depth_ms=1.6):
    n = np.arange(len(x))
    y = x.copy()
    for base, rate, g in voices:
        dl = (base + depth_ms * np.sin(2 * np.pi * rate * n / sr)) * sr / 1000
        idx = n - dl
        y += g * np.interp(idx, n, x, left=0, right=0)
    return y.astype(np.float32)


def ringmod(x, fc, mix, sr=SR):
    t = np.arange(len(x)) / sr
    return (x * (1 - mix) + x * np.sin(2 * np.pi * fc * t) * mix).astype(np.float32)


def bitcrush(x, bits=6, hold=3):
    q = 2 ** (bits - 1)
    y = np.round(x * q) / q
    y = np.repeat(y[::hold], hold)[: len(x)]
    return y.astype(np.float32)


def robot(x, strength=1.0):
    x = eq(x, ("hp", 180, 0.7), ("peak", 2600, 1.2, 3.0 * strength), ("highshelf", 7000, 0.7, -3))
    x = comb(x, 3.1, 0.55, 0.28 * strength)     # metallic resonance
    x = ringmod(x, 55, 0.10 * strength)         # subtle hum ring-mod
    x = chorus(x)                                # doubled synthetic sheen
    return x


def glitch(x, sr=SR, max_len=None, rng=None):
    """Stutter repeats + bitcrushed bursts + dropouts. Keeps words intelligible."""
    rng = rng or np.random.default_rng(7)
    hop = int(0.005 * sr)
    n = len(x) // hop
    e = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, 1))
    on = e > e.max() * 0.12
    # word onsets = rising edges after >=40ms of silence
    onsets, sil = [], 99
    for i, v in enumerate(on):
        if v and sil >= 8:
            onsets.append(i * hop)
        sil = 0 if v else sil + 1
    if not onsets:
        onsets = [0]
    segs, pos = [], 0
    for k, o in enumerate(onsets[:1]):
        segs.append(x[pos:o])
        chunk = x[o:o + int(0.075 * sr)].copy()
        f = int(0.004 * sr)
        chunk[-f:] *= np.linspace(1, 0, f)
        reps = 2 if k == 0 else 1
        for r in range(reps):
            c = bitcrush(chunk, bits=5 + r, hold=4) if r == 0 else chunk
            segs.append(c * (0.85 - 0.1 * r))
            segs.append(np.zeros(int(0.018 * sr), np.float32))
        pos = o
    segs.append(x[pos:])
    y = np.concatenate(segs).astype(np.float32)
    # bitcrushed burst on the tail of word 1 + a short pitch-jump chunk
    L = len(y)
    a = int(L * 0.30); b = a + int(0.07 * sr)
    y[a:b] = bitcrush(y[a:b], bits=5, hold=4)
    a2 = int(L * 0.50); seg = y[a2:a2 + int(0.05 * sr)]
    if len(seg) > 10:
        up = signal.resample(seg, int(len(seg) / 1.35))
        y[a2:a2 + len(seg)] = np.pad(up, (0, len(seg) - len(up)))
    # a couple of 12ms dropouts
    for frac in (0.42, 0.62):
        d = int(L * frac)
        y[d:d + int(0.012 * sr)] *= 0.05
    if max_len and len(y) > max_len:
        y = y[:max_len]
        f = int(0.01 * sr); y[-f:] *= np.linspace(1, 0, f)
    return y


def pitch_shift_formant(x, semis, sr=SR):
    """pyworld based pitch shift keeping formants (optional)."""
    import pyworld as pw
    xd = x.astype(np.float64)
    f0, t = pw.harvest(xd, sr, f0_floor=60, f0_ceil=800, frame_period=5)
    sp = pw.cheaptrick(xd, f0, t, sr); ap = pw.d4c(xd, f0, t, sr)
    return pw.synthesize(f0 * 2 ** (semis / 12), sp, ap, sr, 5).astype(np.float32)


def apply_fx(name, x, max_len):
    if name == "mizuki":
        x = eq(x, ("hp", 90, 0.7), ("peak", 3500, 1.0, 1.5), ("highshelf", 9000, 0.7, 1.0))
        x = compress(x, -20, 2.5)
    elif name == "whisper":
        x = eq(x, ("hp", 120, 0.7), ("peak", 4500, 1.0, 2.0))
        x = compress(x, -24, 3.0)
    elif name == "shout":
        x = eq(x, ("hp", 110, 0.7), ("peak", 2800, 1.0, 3.0))
        x = compress(x, -22, 5.0, 0.002, 0.06)
        x = np.tanh(normalize(x, 0) * 1.4) / np.tanh(1.4)
    elif name == "gen":
        x = eq(x, ("hp", 60, 0.7), ("lowshelf", 220, 0.7, 2.5), ("peak", 1800, 1.0, 1.0), ("highshelf", 8000, 0.7, -2.5))
        x = compress(x, -20, 3.0)
    elif name in ("ann", "ann_scream"):
        drive = 1.8 if name == "ann" else 2.6
        x = eq(x, ("hp", 130, 0.7), ("peak", 2500, 0.9, 4.0), ("peak", 250, 1.0, -2.0), ("lp", 9500, 0.7))
        x = compress(x, -26, 8.0, 0.001, 0.05)
        x = np.tanh(normalize(x, 0) * drive) / np.tanh(drive)
        # stadium PA slap
        d = int(0.085 * SR)
        x = x + 0.12 * np.pad(x, (d, 0))[: len(x)]
    elif name == "ai":
        x = robot(x, 1.0)
    elif name == "ai_soft":
        x = robot(x, 0.7)
    elif name == "ai_glitch":
        x = glitch(x, max_len=max_len)
        x = robot(x, 1.2)
        x = ringmod(x, 90, 0.12)
    return normalize(trim(x.astype(np.float32), thresh_db=-45, pad=0.03), -1.0)


# ----------------------------------------------------------------------------- QC (ASR)
HOMOGRAPHS = {"春風": "はるかぜ", "ハル風": "はるかぜ", "最高法": "さいこうほう", "最後方": "さいこうほう",
              "大外": "おおそと", "十四": "じゅうよん", "14": "じゅうよん", "11": "じゅういち", "0.8": "れいてんはち"}


def to_kana(s):
    import pyopenjtalk
    for k, v in HOMOGRAPHS.items():
        s = s.replace(k, v)
    s = re.sub(r"[、。!！?？…,.\s・「」『』ー〜~-]", "", s)
    k = pyopenjtalk.g2p(s, kana=True) if s else ""
    return re.sub(r"[、。！？ー]", "", k)


def cer(ref, hyp):
    r, h = to_kana(ref), to_kana(hyp)
    d = np.arange(len(h) + 1)
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)] / max(1, len(r))


class ASRCheck:
    def __init__(self):
        self.ok = os.path.exists(os.path.join(ASR, "model.safetensors"))
        if self.ok:
            import torch
            from transformers import WhisperForConditionalGeneration, WhisperProcessor
            self.torch = torch
            self.proc = WhisperProcessor.from_pretrained(ASR)
            self.model = WhisperForConditionalGeneration.from_pretrained(ASR, dtype=torch.float32).eval()

    def __call__(self, x):
        if not self.ok:
            return ""
        x16 = resample(x, SR, 16000)
        f = self.proc(x16, sampling_rate=16000, return_tensors="pt").input_features
        with self.torch.no_grad():
            ids = self.model.generate(f, language="ja", task="transcribe", max_new_tokens=60)
        return self.proc.batch_decode(ids, skip_special_tokens=True)[0].strip()


# ----------------------------------------------------------------------------- main
def _patch_openjtalk():
    """pyopenjtalk-plus returns pron '！' for '!', which SBV2 2.5 (built for pyopenjtalk-dict) rejects.
    Map it back to '、' so SBV2 treats it as punctuation."""
    import pyopenjtalk
    if getattr(pyopenjtalk, "_sbv2_patched", False):
        return
    orig = pyopenjtalk.run_frontend

    def run_frontend(text, *a, **k):
        out = orig(text, *a, **k)
        for n in out:
            if n.get("pron") in ("！", "!", "…", "―"):
                n["pron"] = "、"
        return out
    pyopenjtalk.run_frontend = run_frontend
    pyopenjtalk._sbv2_patched = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", default="")
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--download", action="store_true")
    args = ap.parse_args()
    if args.download:
        download()
    import torch
    _patch_openjtalk()
    from style_bert_vits2.nlp import bert_models
    from style_bert_vits2.constants import Languages
    from style_bert_vits2.tts_model import TTSModel
    torch.set_num_threads(os.cpu_count() or 4)
    bert_models.load_model(Languages.JP, BERT).float()  # transformers>=5 loads fp16 weights as half
    bert_models.load_tokenizer(Languages.JP, BERT)
    asr = ASRCheck()
    os.makedirs(OUT, exist_ok=True)
    want = set(args.lines.split(",")) if args.lines else None
    man_p = os.path.join(OUT, "manifest.json")
    manifest = json.load(open(man_p)) if os.path.exists(man_p) else {}
    tts = {}
    report = []
    for L in LINES:
        lid = L["id"]
        if want and lid not in want:
            continue
        D = DIRECTION[lid]
        spk = L["spk"]
        if spk not in tts:
            d = os.path.join(MODELS, VOICES[spk]) + "/"
            tts[spk] = TTSModel(glob.glob(d + "*.safetensors")[0], d + "config.json", d + "style_vectors.npy", device="cpu")
        m = tts[spk]
        text = D.get("say", L["text"])
        max_len = int(L["max"] * SR)
        target = L["max"] * (0.96 if D["fx"] != "ai_glitch" else 0.72)  # glitch adds ~0.25s
        best = None
        for seed in range(args.seeds):
            length = D.get("length", 1.0)
            for attempt in range(4):
                torch.manual_seed(1000 + seed)
                kw = dict(style=D["style"], style_weight=D.get("w", 1.0), sdp_ratio=D.get("sdp", 0.2),
                          noise=D.get("noise", 0.6), noise_w=D.get("noise_w", 0.8), length=length,
                          pitch_scale=D.get("pitch", 1.0), intonation_scale=D.get("inton", 1.0))
                if D.get("assist"):
                    kw.update(assist_text=D["assist"], assist_text_weight=D.get("aw", 0.5), use_assist_text=True)
                sr, a = m.infer(text, **kw)
                x = resample(a.astype(np.float32) / 32768.0, sr, SR)
                x = squeeze_pauses(trim(x), D.get("gap", 0.22))
                dur = len(x) / SR
                if dur <= target or attempt == 3:
                    break
                length *= (target / dur) * 0.99
            y = apply_fx(D["fx"], x, max_len)
            hyp = asr(y)
            c = cer(L["text"], hyp) if asr.ok else 0.0
            clip = float(np.mean(np.abs(a.astype(np.float32)) > 32000))
            score = c + (0.5 if len(y) > max_len else 0) + clip * 10
            print(f"{lid} seed{seed} len={length:.2f} dur={len(y)/SR:.2f}/{L['max']} cer={c:.2f} asr='{hyp}'", flush=True)
            if best is None or score < best[0]:
                best = (score, y, hyp, c, length, seed)
        score, y, hyp, c, length, seed = best
        if len(y) > max_len:  # last resort: time-compress (should not happen)
            import librosa
            y = librosa.effects.time_stretch(y, rate=len(y) / (max_len - int(0.02 * SR)))
            y = normalize(y, -1.0)
        import soundfile as sf
        sf.write(os.path.join(OUT, f"{lid}.wav"), y, SR, subtype="PCM_16")
        manifest[lid] = {"file": f"{lid}.wav", "duration": round(len(y) / SR, 3), "start": L["start"], "spk": spk}
        report.append((lid, spk, len(y) / SR, L["max"], c, hyp, seed, length))
        json.dump(dict(sorted(manifest.items())), open(man_p, "w"), ensure_ascii=False, indent=1)
    print("\n=== chosen ===")
    for r in report:
        print(f"{r[0]} {r[1]:6s} {r[2]:.2f}s / max {r[3]}  cer={r[4]:.2f} seed={r[6]} length={r[7]:.2f}  asr='{r[5]}'")


if __name__ == "__main__":
    main()
