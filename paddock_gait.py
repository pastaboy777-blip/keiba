#!/usr/bin/env python3
"""
paddock_gait.py — パドック動画（ローカル or 動画URL）から馬の歩様指標を算出

DeepLabCut SuperAnimal-Quadruped（ゼロショット）で骨格推定し、
ストライド頻度・リズム安定性・ストライド長・頭の上下動・トップライン安定性を
体長正規化して算出、CSVに保存する。

使い方:
    # ローカル動画
    python paddock_gait.py path/to/clip.mp4
    # 動画URL（YouTube等、yt-dlp対応サイト）を渡すと自動ダウンロードして解析
    python paddock_gait.py "https://..." --start 00:12 --end 00:20
    # 区間指定はローカル動画にも使える（真横区間だけ切り出して解析）
    python paddock_gait.py clip.mp4 --start 00:03 --end 00:11
    python paddock_gait.py --selftest   # 依存なしで解析ロジックのみ検証

注意: SuperAnimalモデルは研究用途（非商用）ライセンス。内部検討に留め、
      有料コンテンツへの組み込みは規約を確認のこと。
      URLからのダウンロードは各サイトの利用規約・著作権を確認のこと。
"""
import argparse, glob, os, shutil, subprocess, sys, tempfile
import numpy as np
import pandas as pd
from scipy.signal import find_peaks

PCUTOFF = 0.6  # この信頼度未満はNaN→補間


# ---------------- 入力取得（URL or ローカル、任意で区間切り出し） ----------------
def is_url(s):
    return s.startswith("http://") or s.startswith("https://")


def fetch_video(source, start=None, end=None, workdir="."):
    """URLならDL、ローカルならそのまま。start/end指定時は該当区間だけにする。"""
    if is_url(source):
        if shutil.which("yt-dlp") is None:
            raise RuntimeError("yt-dlp が必要です:  pip install yt-dlp")
        out_tmpl = os.path.join(workdir, "paddock_dl.%(ext)s")
        cmd = ["yt-dlp", "-f", "mp4/bestvideo+bestaudio/best",
               "--merge-output-format", "mp4", "-o", out_tmpl]
        if start and end:
            cmd += ["--download-sections", f"*{start}-{end}", "--force-keyframes-at-cuts"]
        cmd += [source]
        print(f"[0/3] 動画をダウンロード中: {source}")
        subprocess.run(cmd, check=True)
        cands = sorted(glob.glob(os.path.join(workdir, "paddock_dl.*")))
        if not cands:
            raise FileNotFoundError("ダウンロードした動画が見つかりません")
        return cands[0]

    # ローカルファイル
    if not os.path.exists(source):
        raise FileNotFoundError(source)
    if start and end:
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("区間切り出しには ffmpeg が必要です")
        trimmed = os.path.splitext(source)[0] + "_trim.mp4"
        print(f"[0/3] 区間を切り出し中: {start} - {end}")
        subprocess.run(["ffmpeg", "-y", "-ss", start, "-to", end, "-i", source,
                        trimmed], check=True)
        return trimmed
    return source


# ---------------- 推論 ----------------
def downsample_fps(video_path, target_fps):
    """target_fps に間引いた動画を作って返す（高速化）。ffmpeg 必須。"""
    if shutil.which("ffmpeg") is None:
        print("警告: ffmpeg が無いため fps 間引きをスキップ")
        return video_path
    out = os.path.splitext(video_path)[0] + f"_fps{int(target_fps)}.mp4"
    subprocess.run(["ffmpeg", "-y", "-i", video_path, "-r", str(target_fps),
                    "-an", out], check=True)
    return out


def run_inference(video_path, video_adapt=True, model_name="hrnet_w32",
                  detector_name="fasterrcnn_resnet50_fpn_v2", scales=None):
    import deeplabcut, time
    scale_list = scales if scales is not None else range(200, 600, 50)
    print(f"[1/3] 骨格推定を実行: {video_path} "
          f"(pose={model_name}, detector={detector_name})")
    t0 = time.time()
    deeplabcut.video_inference_superanimal(
        [video_path],
        "superanimal_quadruped",
        model_name=model_name,
        detector_name=detector_name,
        video_adapt=video_adapt,
        scale_list=scale_list,
    )
    print(f"    推論所要時間: {time.time() - t0:.1f}s")
    stem = os.path.splitext(os.path.basename(video_path))[0]
    d = os.path.dirname(video_path) or "."
    cands = sorted(glob.glob(os.path.join(d, f"{stem}*superanimal_quadruped*.h5")))
    if not cands:
        cands = sorted(glob.glob("*superanimal_quadruped*.h5"))
    if not cands:
        raise FileNotFoundError("推論結果の.h5が見つかりません")
    return cands[-1]


def get_fps(video_path, default=30.0):
    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or default
        cap.release()
        return float(fps)
    except Exception:
        return default


# ---------------- 解析 ----------------
def pick_best_individual(df):
    """DLC 3.0のマルチ個体出力から、最も高信頼で検出された個体を1頭選ぶ。
    未検出個体は likelihood=-1 のプレースホルダなので除外される。"""
    lik = df.xs("likelihood", axis=1, level="coords")  # (scorer, individuals) or (individuals)
    lik = lik.where(lik >= 0)  # -1 プレースホルダを無視
    score = lik.mean().groupby(level="individuals").mean()
    return score.idxmax()


def extract_target_horse(df, conf=0.35, min_kpts=6, jump_frac=0.6):
    """マルチ個体h5から『本命馬』を単一トラックとして抽出し (bodyparts, coords) を返す。

    各フレームで「高信頼キーポイントが多く・体が大きく(=手前)・前フレームに連続する」
    個体を選ぶ。さらに体中心が大きく飛ぶフレーム(別馬への乗り移り)はNaNで除外する。
    複数馬・引き馬・写り込みのある地方競馬パドックで、目的馬をロックするための処理。
    """
    import numpy as np, pandas as pd
    names = list(df.columns.names or [])
    if "individuals" not in names:
        # 単一個体: scorerを落として (bodyparts, coords) に
        while df.columns.nlevels > 2:
            df = df.droplevel(0, axis=1)
        return df
    while df.columns.nlevels > 3:      # scorerを除去 → (individuals, bodyparts, coords)
        df = df.droplevel(0, axis=1)

    inds = list(df.columns.get_level_values("individuals").unique())
    bps = list(df.columns.get_level_values("bodyparts").unique())
    n = len(df)
    cols = pd.MultiIndex.from_product([bps, ["x", "y", "likelihood"]],
                                      names=["bodyparts", "coords"])
    colidx = {c: j for j, c in enumerate(cols)}
    out = np.full((n, len(cols)), np.nan)
    cens = np.full((n, 2), np.nan)
    spans = np.full(n, np.nan)
    prev = None
    for i in range(n):
        row = df.iloc[i]
        best = None  # (score, pts, cen, span)
        for a in inds:
            xs, ys, pts = [], [], {}
            for bp in bps:
                lk = row.get((a, bp, "likelihood"))
                if lk is not None and lk == lk and lk >= conf:
                    x = row.get((a, bp, "x")); y = row.get((a, bp, "y"))
                    if x == x and y == y:
                        pts[bp] = (x, y, lk); xs.append(x); ys.append(y)
            if len(pts) < min_kpts:
                continue
            span = ((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2) ** 0.5
            cen = (sum(xs) / len(xs), sum(ys) / len(ys))
            score = span  # 大きい(手前)ほど本命
            if prev is not None:  # 前フレームに近いほど加点(連続性)
                score -= 0.7 * ((cen[0] - prev[0]) ** 2 + (cen[1] - prev[1]) ** 2) ** 0.5
            if best is None or score > best[0]:
                best = (score, pts, cen, span)
        if best is not None:
            _, pts, cen, span = best
            for bp, (x, y, lk) in pts.items():
                out[i, colidx[(bp, "x")]] = x
                out[i, colidx[(bp, "y")]] = y
                out[i, colidx[(bp, "likelihood")]] = lk
            cens[i] = cen; spans[i] = span; prev = cen
    # 体中心が中央値から大きく外れるフレーム=別馬への乗り移りとみなし除外
    valid = ~np.isnan(cens[:, 0])
    if valid.sum() >= 5:
        med = np.nanmedian(cens[valid], axis=0)
        thr = max(np.nanmedian(spans[valid]) * jump_frac, 40.0)
        for i in range(n):
            if valid[i] and ((cens[i, 0] - med[0]) ** 2 + (cens[i, 1] - med[1]) ** 2) ** 0.5 > thr:
                out[i, :] = np.nan
    return pd.DataFrame(out, columns=cols)


def analyze_h5(df, fps):
    # 目的馬ロック: 毎フレーム最大・手前・連続する馬を選び、乗り移りフレームを除外
    df = extract_target_horse(df)

    def lik_mean(bp):
        return df[(bp, "likelihood")].mean()

    def coord(bp, c):
        s = df[(bp, c)].copy()
        s[df[(bp, "likelihood")] < PCUTOFF] = np.nan
        return s.interpolate(limit_direction="both")

    front = "front_right_paw" if lik_mean("front_right_paw") >= lik_mean("front_left_paw") else "front_left_paw"
    back = "back_right_paw" if lik_mean("back_right_paw") >= lik_mean("back_left_paw") else "back_left_paw"

    body_len = np.nanmedian(np.hypot(coord("neck_base", "x") - coord("tail_base", "x"),
                                     coord("neck_base", "y") - coord("tail_base", "y")))

    rel_x = coord(front, "x") - coord("back_base", "x")
    rel_x = (rel_x - rel_x.mean()).rolling(max(1, int(fps * 0.1)), center=True, min_periods=1).mean()
    amp = rel_x.std()
    peaks, _ = find_peaks(rel_x.values, distance=max(1, int(fps * 0.35)), prominence=amp * 0.5)
    intervals = np.diff(peaks) / fps
    stride_freq = float(1 / np.mean(intervals)) if len(intervals) else float("nan")
    regularity = float(np.std(intervals)) if len(intervals) else float("nan")

    paw_exc = coord(front, "x") - coord("back_base", "x")
    stride_len_norm = float((np.nanpercentile(paw_exc, 95) - np.nanpercentile(paw_exc, 5)) / body_len)
    nose_y = coord("nose", "y")
    head_bob = float((np.nanpercentile(nose_y, 95) - np.nanpercentile(nose_y, 5)) / body_len)
    topline = float(np.mean([coord(b, "y").std() / body_len for b in ["back_base", "back_middle", "tail_base"]]))

    return {
        "n_strides": int(len(peaks)),
        "stride_freq_hz": round(stride_freq, 3),
        "stride_regularity_s": round(regularity, 4),
        "stride_len_norm": round(stride_len_norm, 3),
        "head_bob_norm": round(head_bob, 4),
        "topline_stability": round(topline, 4),
        "near_front": front,
        "near_back": back,
        "body_len_px": round(float(body_len), 1),
    }


def selftest():
    np.random.seed(0)
    fps, n = 60, 300
    t = np.arange(n) / fps
    scorer = "DLC_superanimal_quadruped_hrnetw32"
    bps = ["nose", "neck_base", "back_base", "back_middle", "tail_base",
           "front_left_paw", "front_right_paw", "back_left_paw", "back_right_paw"]
    cols = pd.MultiIndex.from_product([[scorer], bps, ["x", "y", "likelihood"]],
                                     names=["scorer", "bodyparts", "coords"])
    df = pd.DataFrame(np.zeros((n, len(cols))), columns=cols)
    base_x = {"nose": 500, "neck_base": 420, "back_base": 300, "back_middle": 260, "tail_base": 180,
              "front_left_paw": 410, "front_right_paw": 415, "back_left_paw": 210, "back_right_paw": 215}
    base_y = {"nose": 180, "neck_base": 150, "back_base": 140, "back_middle": 142, "tail_base": 150,
              "front_left_paw": 330, "front_right_paw": 330, "back_left_paw": 330, "back_right_paw": 330}
    hz = 1.2
    for bp in bps:
        x = base_x[bp] + 40 * t
        y = np.full(n, base_y[bp], float)
        phase = 0 if "right" in bp else np.pi
        if "paw" in bp:
            x = x + 25 * np.sin(2 * np.pi * hz * t + phase)
            y = y - 20 * np.clip(np.sin(2 * np.pi * hz * t + phase), 0, None)
        if bp == "nose":
            y = y + 8 * np.sin(2 * np.pi * hz * t)
        df[(scorer, bp, "x")] = x + np.random.normal(0, 1, n)
        df[(scorer, bp, "y")] = y + np.random.normal(0, 1, n)
        df[(scorer, bp, "likelihood")] = 0.4 if "left" in bp else 0.95
    m = analyze_h5(df, fps)
    print("selftest metrics:", m)
    assert m["near_front"] == "front_right_paw"
    assert abs(m["stride_freq_hz"] - hz) < 0.2, m["stride_freq_hz"]
    print("SELFTEST PASSED (stride_freq %.3f ≈ %.1f)" % (m["stride_freq_hz"], hz))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?", help="パドック動画のパス、または動画URL")
    ap.add_argument("--start", help="切り出し開始 (例 00:12) URL/ローカル両対応")
    ap.add_argument("--end", help="切り出し終了 (例 00:20)")
    ap.add_argument("--no-adapt", action="store_true", help="video_adaptを切って高速化")
    ap.add_argument("--fps", type=float, help="この fps に間引いて高速化 (例 12)。歩様は約1Hzなので10〜15で十分")
    ap.add_argument("--fast", action="store_true",
                    help="軽量モデル(mobilenet検出器+rtmpose_s, 単一スケール)で高速化。精度は少し落ちる")
    ap.add_argument("--model", help="ポーズモデル上書き (hrnet_w32/resnet_50/rtmpose_s)")
    ap.add_argument("--detector", help="検出器上書き (fasterrcnn_resnet50_fpn_v2/fasterrcnn_mobilenet_v3_large_fpn/ssdlite)")
    ap.add_argument("--selftest", action="store_true", help="解析ロジックのみ検証")
    args = ap.parse_args()

    if args.selftest:
        selftest(); return
    if not args.video:
        ap.error("動画パスまたはURLを指定してください（または --selftest）")

    video = fetch_video(args.video, args.start, args.end, workdir=".")
    if args.fps:
        src_fps = get_fps(video)
        if args.fps < src_fps:
            print(f"[0/3] fpsを{src_fps:.0f}→{args.fps:g}に間引き（高速化）")
            video = downsample_fps(video, args.fps)
    fps = get_fps(video)
    print(f"FPS: {fps}")
    model_name = args.model or ("rtmpose_s" if args.fast else "hrnet_w32")
    detector_name = args.detector or (
        "fasterrcnn_mobilenet_v3_large_fpn" if args.fast else "fasterrcnn_resnet50_fpn_v2")
    scales = [400] if args.fast else None
    h5_path = run_inference(video, video_adapt=not args.no_adapt,
                            model_name=model_name, detector_name=detector_name, scales=scales)
    print(f"[2/3] 結果読み込み: {h5_path}")
    df = pd.read_hdf(h5_path)
    print(f"[3/3] 歩様指標を算出")
    m = analyze_h5(df, fps)
    m["source"] = args.video
    m["fps"] = fps

    for k in ["n_strides", "stride_freq_hz", "stride_regularity_s",
              "stride_len_norm", "head_bob_norm", "topline_stability",
              "near_front", "near_back", "body_len_px"]:
        print(f"  {k:22s}: {m[k]}")

    out_csv = os.path.splitext(video)[0] + "_gait_metrics.csv"
    pd.DataFrame([m]).to_csv(out_csv, index=False)
    print(f"\n保存しました: {out_csv}")
    labeled = sorted(glob.glob(os.path.splitext(os.path.basename(video))[0] + "*superanimal_quadruped*.mp4"))
    if labeled:
        print(f"骨格付き動画（要目視確認）: {labeled[-1]}")


if __name__ == "__main__":
    main()
