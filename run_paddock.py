#!/usr/bin/env python3
"""
run_paddock.py — パドック動画1本から「全頭の気配ランキング＋骨格動画」を一発生成

内部で4ツールを順に呼ぶ:
  1. paddock_segment.py … 馬番テロップOCRで全頭に自動分割＋各馬クリップ切り出し
  2. paddock_gait.py    … 各馬の歩様を数値化(目的馬ロック付き)
  3. skeleton_overlay.py… 各馬の骨格線＋背骨＋重心を描いた確認動画
  4. paddock_compare.py … 全頭を気配スコアで横並び比較(HTML)

使い方:
    python run_paddock.py race.mp4
    python run_paddock.py race.mp4 --fast --fps 12 --outdir race12R
    python run_paddock.py race.mp4 --roi 258,806,120,70   # 競馬場ごとのテロップ位置
    python run_paddock.py race.mp4 --no-skeleton           # 骨格動画をスキップして高速化

出力(--outdir 既定は <動画名>_paddock/):
    <馬番>のクリップ / *_gait_metrics.csv / *_skeleton.mp4 / kehai.html(気配ランキング)
"""
import argparse, glob, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def sh(cmd):
    print("  $", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, check=False).returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", help="パドック連続映像(全頭が写った1本)")
    ap.add_argument("--roi", help="馬番ボックス座標 x,y,w,h(競馬場ごと)")
    ap.add_argument("--sample-fps", type=float, default=3.0, help="馬番OCRのサンプリング")
    ap.add_argument("--fast", action="store_true", help="軽量モデルで高速化(精度は少し落ちる)")
    ap.add_argument("--fps", type=float, help="推論前にこのfpsへ間引き(例12)")
    ap.add_argument("--no-skeleton", action="store_true", help="骨格確認動画をスキップ")
    ap.add_argument("--outdir", help="出力先(既定: <動画名>_paddock)")
    args = ap.parse_args()

    if not os.path.exists(args.video):
        ap.error(f"動画が見つかりません: {args.video}")
    outdir = args.outdir or (os.path.splitext(os.path.basename(args.video))[0] + "_paddock")
    os.makedirs(outdir, exist_ok=True)
    work = os.path.join(outdir, "race.mp4")
    shutil.copy(args.video, work)
    print(f"■ 出力先: {outdir}\n")

    # 1) 全頭に自動分割＋クリップ切り出し
    print("■ [1/4] 馬番OCRで全頭に自動分割")
    seg = [PY, os.path.join(HERE, "paddock_segment.py"), work, "--cut",
           "--sample-fps", str(args.sample_fps)]
    if args.roi:
        seg += ["--roi", args.roi]
    sh(seg)
    clips = sorted(glob.glob(os.path.join(outdir, "race_uma*.mp4")))
    if not clips:
        print("！馬番を検出できませんでした。--roi でテロップ位置を調整してください。")
        return
    print(f"  → {len(clips)}頭のクリップを検出\n")

    gait_opts = ["--no-adapt"] + (["--fast"] if args.fast else []) + \
                (["--fps", str(args.fps)] if args.fps else [])

    # 2)+3) 各馬: 歩様数値化 → 骨格確認動画
    for i, clip in enumerate(clips, 1):
        name = os.path.basename(clip)
        print(f"■ [2/4] 歩様解析 ({i}/{len(clips)}): {name}")
        sh([PY, os.path.join(HERE, "paddock_gait.py"), clip] + gait_opts)
        if not args.no_skeleton:
            print(f"■ [3/4] 骨格動画 ({i}/{len(clips)}): {name}")
            sh([PY, os.path.join(HERE, "skeleton_overlay.py"), clip])
        print()

    # 4) 全頭 気配ランキング
    print("■ [4/4] 気配スコアで全頭比較")
    html = os.path.join(outdir, "kehai.html")
    sh([PY, os.path.join(HERE, "paddock_compare.py"),
        os.path.join(outdir, "*_gait_metrics.csv"), "--html", html])

    print("\n==============================")
    print(f"完了！ 出力先: {outdir}")
    print(f"  ・気配ランキング: {html}")
    print(f"  ・各馬の骨格動画: {outdir}/*_skeleton.mp4")
    print(f"  ・各馬の歩様CSV : {outdir}/*_gait_metrics.csv")
    print("==============================")


if __name__ == "__main__":
    main()
