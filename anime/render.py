"""Frame renderer for 「最後の一完歩」.

Usage:
  python render.py --frames 30,150,400        # PNG stills -> build/frames/
  python render.py --times 7.5,12.0           # stills at global seconds
  python render.py --sheet s04 --n 12         # contact sheet of a shot -> build/sheet_s04.png
  python render.py --clip s04                 # quick mp4 of one shot (no audio, 12 fps preview with --preview)
  python render.py --full [--jobs 4]          # full film video -> build/video.mp4
Scene modules: scenes/<mod>.py must define  draw(ctx, t, dur, gt)
  t = seconds since shot start, dur = shot length, gt = global time.
  Must paint the whole 1920x1080 frame. May be called with t slightly outside [0,dur] (transitions).
  Optional module attr POST = dict(bloom=0.0..1.0, grain=0..1, vignette=0..1, aberration=px)
"""
import os, sys, json, math, argparse, importlib, subprocess
import numpy as np
import cairo
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import W, H, FPS, DURATION, BUILD, FONT_SANS, FONT_SANS_M
from timeline import SHOTS, TRANSITIONS, LINES, SPEAKERS, shot_at
from lib.common import text, clamp

_mods = {}
def get_mod(name):
    if name not in _mods:
        _mods[name] = importlib.import_module("scenes." + name)
    return _mods[name]

DEFAULT_POST = dict(bloom=0.35, grain=0.35, vignette=0.45, aberration=0.0)

def _voice_durations():
    p = os.path.join(BUILD, "voice", "manifest.json")
    if os.path.exists(p):
        try:
            return {k: v["duration"] for k, v in json.load(open(p)).items()}
        except Exception:
            pass
    return {}
VOICE_DUR = _voice_durations()

def draw_shot(mod_name, t, dur, gt):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(s)
    ctx.set_source_rgb(0, 0, 0); ctx.paint()
    mod = get_mod(mod_name)
    try:
        mod.draw(ctx, t, dur, gt)
    except Exception as e:  # keep rendering; show error on frame
        import traceback; traceback.print_exc()
        ctx.identity_matrix(); ctx.set_source_rgb(0.3, 0, 0); ctx.paint()
        text(ctx, f"{mod_name}: {e}"[:90], W / 2, H / 2, 36)
    s.flush()
    a = np.ndarray((H, W, 4), np.uint8, s.get_data()).copy()
    rgb = a[:, :, [2, 1, 0]].astype(np.float32) / 255.0
    return rgb, getattr(mod, "POST", {})

# ---------- post FX ----------
_yy, _xx = np.mgrid[0:H, 0:W].astype(np.float32)
_rr = np.sqrt(((_xx - W / 2) / (W / 2)) ** 2 + ((_yy - H / 2) / (H / 2)) ** 2)
VIGNETTE = np.clip(1.0 - 0.55 * np.clip(_rr - 0.35, 0, None) ** 1.6, 0, 1)[..., None]
del _yy, _xx

def post(rgb, P, frame_idx):
    bloom = P.get("bloom", DEFAULT_POST["bloom"])
    if bloom > 0:
        small = rgb[::4, ::4]
        bright = np.clip((small - 0.62) / 0.38, 0, 1) * small
        im = Image.fromarray((np.clip(bright, 0, 1) * 255).astype(np.uint8))
        b1 = np.asarray(im.filter(ImageFilter.GaussianBlur(6)), np.float32) / 255
        b2 = np.asarray(im.resize((im.width // 4, im.height // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(6))
                        .resize(im.size, Image.BILINEAR), np.float32) / 255
        b = (b1 * 0.6 + b2 * 0.8)
        b = np.asarray(Image.fromarray((np.clip(b, 0, 1) * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR), np.float32) / 255
        rgb = 1 - (1 - rgb) * (1 - np.clip(b * bloom * 1.6, 0, 1))   # screen blend
    ab = P.get("aberration", DEFAULT_POST["aberration"])
    if ab and ab > 0.5:
        k = int(round(ab))
        rgb = rgb.copy()
        rgb[:, k:, 0] = rgb[:, :-k, 0]
        rgb[:, :-k, 2] = rgb[:, k:, 2]
    vig = P.get("vignette", DEFAULT_POST["vignette"])
    if vig > 0:
        rgb = rgb * (1 - vig + vig * VIGNETTE)
    grain = P.get("grain", DEFAULT_POST["grain"])
    if grain > 0:
        r = np.random.default_rng(frame_idx)
        n = r.standard_normal((H // 2, W // 2), dtype=np.float32)
        n = np.repeat(np.repeat(n, 2, 0), 2, 1)[..., None]
        rgb = rgb + n * 0.018 * grain
    return np.clip(rgb, 0, 1)

# ---------- subtitles ----------
def draw_subtitles(ctx, gt):
    for L in LINES:
        d = VOICE_DUR.get(L["id"], L["max"])
        a, b = L["start"] - 0.05, L["start"] + d + 0.45
        if a <= gt < b:
            alpha = clamp((gt - a) / 0.12) * clamp((b - gt) / 0.2)
            spk = SPEAKERS[L["spk"]]
            y = H - 92
            size = 50
            text(ctx, L["sub"], W / 2, y, size, font=FONT_SANS, color=(1, 1, 1), alpha=alpha,
                 outline=9, outline_color=(0.02, 0.02, 0.06), outline_alpha=0.85)
            text(ctx, spk["name"], W / 2, y - 62, 28, font=FONT_SANS_M, color=spk["color"], alpha=alpha * 0.95,
                 outline=6, outline_color=(0.02, 0.02, 0.06), outline_alpha=0.8)

def overlay_subs(rgb, gt):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(s)
    draw_subtitles(ctx, gt)
    s.flush()
    a = np.ndarray((H, W, 4), np.uint8, s.get_data()).astype(np.float32) / 255
    if a[..., 3].max() == 0:
        return rgb
    premul = a[:, :, [2, 1, 0]]; al = a[:, :, 3:4]
    return premul + rgb * (1 - al)

# ---------- frame ----------
def render_frame(fi, subs=True):
    gt = fi / FPS
    sid, a, b, mod = shot_at(gt)
    t = gt - a
    rgb, P = draw_shot(mod, t, b - a, gt)
    tr = TRANSITIONS.get(sid)
    if tr and tr[1] > 0 and t < tr[1]:
        kind, td = tr; k = t / td
        idx = [s[0] for s in SHOTS].index(sid)
        if kind == "cross" and idx > 0:
            psid, pa, pb, pmod = SHOTS[idx - 1]
            prev, _ = draw_shot(pmod, gt - pa, pb - pa, gt)
            k = k * k * (3 - 2 * k)
            rgb = prev * (1 - k) + rgb * k
        elif kind == "fade_black":
            rgb = rgb * k
        elif kind == "flash_white":
            w = (1 - k) ** 1.5
            rgb = rgb * (1 - w) + w
    rgb = post(rgb, P, fi)
    if subs:
        rgb = overlay_subs(rgb, gt)
    return (np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8)

def ffmpeg_exe():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()

def encode(frames_iter, out, fps=FPS, crf=18):
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for fr in frames_iter:
        p.stdin.write(fr.tobytes())
    p.stdin.close(); p.wait()

def _render_segment(args):
    f0, f1, out = args
    encode((render_frame(i) for i in range(f0, f1)), out)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames"); ap.add_argument("--times"); ap.add_argument("--sheet"); ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--clip"); ap.add_argument("--full", action="store_true"); ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--nosubs", action="store_true")
    A = ap.parse_args()
    os.makedirs(os.path.join(BUILD, "frames"), exist_ok=True)
    subs = not A.nosubs
    idxs = []
    if A.frames: idxs += [int(x) for x in A.frames.split(",")]
    if A.times: idxs += [int(round(float(x) * FPS)) for x in A.times.split(",")]
    for i in idxs:
        p = os.path.join(BUILD, "frames", f"f{i:05d}.png")
        Image.fromarray(render_frame(i, subs)).save(p); print(p)
    if A.sheet:
        sh = [s for s in SHOTS if s[0] == A.sheet][0]
        n = A.n; cols = 4; rows = math.ceil(n / cols); tw, th = W // 4, H // 4
        sheet = Image.new("RGB", (tw * cols, th * rows))
        for k in range(n):
            gt = sh[1] + (sh[2] - sh[1]) * (k + 0.5) / n
            im = Image.fromarray(render_frame(int(gt * FPS), subs)).resize((tw, th), Image.BILINEAR)
            sheet.paste(im, ((k % cols) * tw, (k // cols) * th))
        p = os.path.join(BUILD, f"sheet_{A.sheet}.png"); sheet.save(p); print(p)
    if A.clip:
        sh = [s for s in SHOTS if s[0] == A.clip][0]
        out = os.path.join(BUILD, f"clip_{A.clip}.mp4")
        _render_parallel(int(sh[1] * FPS), int(round(sh[2] * FPS)), out, A.jobs); print(out)
    if A.full:
        out = os.path.join(BUILD, "video.mp4")
        _render_parallel(0, int(round(DURATION * FPS)), out, A.jobs); print(out)

def _render_parallel(f0, f1, out, jobs):
    from multiprocessing import Pool
    n = f1 - f0; step = math.ceil(n / (jobs * 3))
    segs = [(a, min(a + step, f1), os.path.join(BUILD, f"seg_{a:05d}.mp4")) for a in range(f0, f1, step)]
    with Pool(jobs) as pool:
        parts = pool.map(_render_segment, segs)
    lst = os.path.join(BUILD, "segs.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out], check=True)
    for p in parts: os.remove(p)

if __name__ == "__main__":
    main()
