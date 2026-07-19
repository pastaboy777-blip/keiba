#!/usr/bin/env python3
"""
paddock_segment.py — パドック連続映像を「馬番テロップOCR」で馬ごとに自動分割

地方競馬(NAR)のパドック中継は全頭が1本の映像で流れる。画面下部の
馬番テロップをOCRで読み取り、馬番が変わったタイミングで区間を切り出す。
切り出した各区間に paddock_gait.py を掛ければ、1レース全頭の歩様指標を
自動で取得できる。

使い方:
    # 馬番だけ検出して区間一覧を表示
    python paddock_segment.py race.mp4
    # 各馬のクリップを切り出す
    python paddock_segment.py race.mp4 --cut
    # 切り出し＋各馬の歩様解析まで一気に
    python paddock_segment.py race.mp4 --cut --gait --fast --fps 12
    # テロップ位置が違う競馬場向けに馬番ボックス座標を指定
    python paddock_segment.py race.mp4 --roi 258,806,120,70
    python paddock_segment.py --selftest

注意: 馬番ボックスの座標(--roi)は競馬場・配信レイアウトごとに調整が必要。
      既定値は高知けいばナイター配信(1920x1140)向け。
"""
import argparse, json, os, subprocess, sys


# 高知けいば配信(1920x1140)の馬番テロップ既定座標 (x, y, w, h)
DEFAULT_ROI = (258, 806, 120, 70)


def read_umaban(roi_bgr):
    """馬番ボックス画像から数字をOCR。読めなければ None。
    中抜き(アウトライン)フォントに対応するため穴埋め処理を行う。"""
    import cv2, numpy as np, pytesseract
    g = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    _, th = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    inv = cv2.bitwise_not(th)
    inv = cv2.morphologyEx(inv, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    ff = inv.copy()
    h, w = inv.shape
    mask = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(ff, mask, (0, 0), 255)
    filled = inv | cv2.bitwise_not(ff)          # 数字を白塗り(黒地)
    out = cv2.bitwise_not(filled)               # 黒数字・白地(tesseract向き)
    out = cv2.copyMakeBorder(out, 25, 25, 25, 25, cv2.BORDER_CONSTANT, value=255)
    for psm in (10, 8, 7, 13):
        t = pytesseract.image_to_string(
            out, config=f"--psm {psm} -c tessedit_char_whitelist=0123456789").strip()
        if t.isdigit() and 1 <= int(t) <= 18:
            return int(t)
    return None


def scan_umaban(video, roi, sample_fps):
    """動画をsample_fps間隔でOCRし、[(t_sec, umaban or None), ...] を返す。"""
    import cv2
    x, y, w, h = roi
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, int(round(fps / sample_fps)))
    samples = []
    fno = 0
    while True:
        cap.set(cv2.CAP_PROP_POS_FRAMES, fno)
        ok, fr = cap.read()
        if not ok:
            break
        roi_bgr = fr[y:y + h, x:x + w]
        num = read_umaban(roi_bgr) if roi_bgr.size else None
        samples.append((fno / fps, num))
        fno += step
        if total and fno >= total:
            break
    cap.release()
    return samples, fps


def smooth(samples, win=2):
    """欠測/誤読を近傍多数決で補間したラベル列を返す。"""
    labels = [n for _, n in samples]
    out = []
    for i in range(len(labels)):
        lo, hi = max(0, i - win), min(len(labels), i + win + 1)
        votes = {}
        for n in labels[lo:hi]:
            if n is not None:
                votes[n] = votes.get(n, 0) + 1
        out.append(max(votes, key=votes.get) if votes else None)
    return out


def segment(samples, labels, min_seg, merge_gap):
    """同一馬番の連続区間を[(umaban, start, end)]にまとめる。"""
    segs = []
    cur, start = None, None
    for (t, _), lab in zip(samples, labels):
        if lab != cur:
            if cur is not None and start is not None:
                segs.append([cur, start, t])
            cur, start = lab, t
    if cur is not None and start is not None:
        segs.append([cur, start, samples[-1][0]])
    segs = [s for s in segs if s[0] is not None]
    # 同一馬番で近接する区間を結合（一時的な誤読で割れた場合の対策）
    merged = []
    for s in segs:
        if merged and merged[-1][0] == s[0] and s[1] - merged[-1][2] <= merge_gap:
            merged[-1][2] = s[2]
        else:
            merged.append(s)
    return [s for s in merged if s[2] - s[1] >= min_seg]


def fmt(t):
    return f"{int(t // 60):02d}:{t % 60:05.2f}"


def process(video, roi, sample_fps, min_seg, merge_gap, cut, gait, gait_args):
    print(f"[1/2] 馬番テロップをOCR中 (roi={roi}, sample={sample_fps}fps)…")
    samples, fps = scan_umaban(video, roi, sample_fps)
    labels = smooth(samples)
    segs = segment(samples, labels, min_seg, merge_gap)
    print(f"[2/2] {len(segs)} 区間を検出:")
    stem = os.path.splitext(video)[0]
    result = []
    for i, (uma, st, en) in enumerate(segs, 1):
        print(f"  #{uma:>2}  {fmt(st)} - {fmt(en)}  ({en - st:4.1f}s)")
        rec = {"umaban": uma, "start": round(st, 2), "end": round(en, 2),
               "dur": round(en - st, 2)}
        if cut:
            clip = f"{stem}_uma{uma:02d}.mp4"
            subprocess.run(["ffmpeg", "-y", "-ss", f"{st:.2f}", "-to", f"{en:.2f}",
                            "-i", video, "-an", clip],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            rec["clip"] = clip
            if gait:
                cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "paddock_gait.py"), clip, "--no-adapt"] + gait_args
                print(f"      → 歩様解析: {' '.join(cmd[-3:])}")
                subprocess.run(cmd, check=False)
                csv = os.path.splitext(clip)[0] + "_gait_metrics.csv"
                rec["gait_csv"] = csv if os.path.exists(csv) else None
        result.append(rec)
    out_json = f"{stem}_segments.json"
    with open(out_json, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n区間情報を保存: {out_json}")
    return result


def selftest():
    samples = [(i * 0.5, n) for i, n in enumerate(
        [None, 3, 3, 3, None, 3, 3, 7, 7, 7, 7, None, 7, 12, 12, 12, 12])]
    labels = smooth(samples)
    segs = segment(samples, labels, min_seg=1.0, merge_gap=1.0)
    got = [s[0] for s in segs]
    print("segments:", [(u, round(a, 1), round(b, 1)) for u, a, b in segs])
    assert got == [3, 7, 12], got
    print("SELFTEST PASSED (3頭 [3,7,12] を正しく分割)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?", help="パドック連続映像のパス")
    ap.add_argument("--roi", help="馬番ボックス座標 x,y,w,h（既定:高知配信）")
    ap.add_argument("--sample-fps", type=float, default=3.0, help="OCRサンプリング間隔(fps)")
    ap.add_argument("--min-seg", type=float, default=2.0, help="この秒数未満の区間は無視")
    ap.add_argument("--merge-gap", type=float, default=1.5, help="同一馬番の近接区間を結合する猶予(秒)")
    ap.add_argument("--cut", action="store_true", help="各馬のクリップを切り出す")
    ap.add_argument("--gait", action="store_true", help="各クリップに paddock_gait.py を実行")
    ap.add_argument("--selftest", action="store_true", help="分割ロジックのみ検証")
    args, gait_args = ap.parse_known_args()

    if args.selftest:
        selftest(); return
    if not args.video:
        ap.error("パドック映像のパスを指定してください（または --selftest）")

    roi = tuple(int(v) for v in args.roi.split(",")) if args.roi else DEFAULT_ROI
    if len(roi) != 4:
        ap.error("--roi は x,y,w,h の4値で指定してください")
    process(args.video, roi, args.sample_fps, args.min_seg, args.merge_gap,
            args.cut, args.gait, gait_args)


if __name__ == "__main__":
    main()
