#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YouTube→パドック全自動解析  youtube_paddock.py

YouTube等のURLを渡すだけで、
  ① 区間ダウンロード(yt-dlp)
  ② 全頭に自動分割(馬番OCR)
  ③ 各馬の歩様を数値化＋骨格確認動画
  ④ 気配スコアで横並び比較
  ⑤ 腹圧(体幹エンゲージ)スコア
  ⑥ パドックアイ風ダッシュボード(全頭1画面HTML)
まで一気に通す“ワンコマンド”ラッパー。

※ネットワーク制限のあるクラウド環境ではYouTubeへ接続できないことがある
  （データセンターIPがボット判定される/プロキシが遮断する）。その場合は
  自宅PCやColabなど家庭回線で実行すること。本スクリプトは既存の
  paddock_gait.fetch_video / run_paddock.py / core_engagement.py /
  paddock_dashboard.py を順に呼ぶだけなので、環境が通ればそのまま動く。

使い方:
  python youtube_paddock.py "https://youtu.be/XXXX" --start 1:08 --end 1:18
  python youtube_paddock.py "https://youtu.be/XXXX" --start 0:10 --end 0:40 \
         --fast --fps 12 --roi 258,806,120,70 --title 高知11R
  python youtube_paddock.py local.mp4            # ローカル動画でもOK(URLでなくても可)
  python youtube_paddock.py --selftest           # 手順の結線のみ検証(DL/推論なし)
"""
import argparse
import glob
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def sh(cmd, check=False):
    print("  $ " + " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, check=check).returncode


def download_section(source, start, end, workdir):
    """URLなら区間DL、ローカルなら(必要なら)区間切り出し。パスを返す。
    paddock_gait.fetch_video をそのまま再利用する。"""
    sys.path.insert(0, HERE)
    import paddock_gait
    return paddock_gait.fetch_video(source, start=start, end=end, workdir=workdir)


def run_core_engagement(outdir):
    """outdir内の各馬h5に腹圧スコアを付け、サイドカーtxt＋一覧を書く。"""
    try:
        sys.path.insert(0, HERE)
        import core_engagement as ce
    except Exception as e:
        print(f"  腹圧スコアをスキップ(core_engagement読込失敗): {e}")
        return []
    rows = []
    h5s = sorted(glob.glob(os.path.join(outdir, "*uma*superanimal_quadruped*.h5"))) \
        or sorted(glob.glob(os.path.join(outdir, "*superanimal_quadruped*.h5")))
    for h5 in h5s:
        m = re.search(r"uma(\d+)", os.path.basename(h5))
        uma = int(m.group(1)) if m else 0
        try:
            res = ce.analyze_h5(h5)
        except Exception as e:
            print(f"  腹圧スコア失敗 {os.path.basename(h5)}: {e}")
            continue
        if not res.get("ok"):
            continue
        rows.append((uma, res))
        # サイドカー(ダッシュボードが拾えるよう uma番号付きで保存)
        side = os.path.join(outdir, f"race_uma{uma:02d}_fukuatsu.txt")
        with open(side, "w", encoding="utf-8") as f:
            f.write(f"fukuatsu_score={res['score']}\n")
            f.write(f"verdict={res['verdict']}\n")
            for k, v in res["norm"].items():
                f.write(f"{k}={v}\n")
    if rows:
        rows.sort(key=lambda r: r[1]["score"], reverse=True)
        print("\n―― 腹圧ランキング ――")
        for rank, (uma, res) in enumerate(rows, 1):
            print(f"  {rank}. {uma:>2}番  {res['score']:5.1f}  {res['verdict']}")
    return rows


def main():
    ap = argparse.ArgumentParser(description="YouTube→パドック全自動解析")
    ap.add_argument("source", nargs="?", help="動画URL(YouTube等)またはローカル動画パス")
    ap.add_argument("--start", help="開始位置 例 1:08")
    ap.add_argument("--end", help="終了位置 例 1:18")
    ap.add_argument("--roi", help="馬番ボックス x,y,w,h(競馬場ごと)")
    ap.add_argument("--fast", action="store_true", help="軽量モデルで高速化")
    ap.add_argument("--fps", type=float, help="推論前にこのfpsへ間引き(例12)")
    ap.add_argument("--no-skeleton", action="store_true", help="骨格動画をスキップ")
    ap.add_argument("--no-dashboard", action="store_true", help="ダッシュボードHTMLをスキップ")
    ap.add_argument("--outdir", help="出力先(既定: <動画名>_paddock)")
    ap.add_argument("--title", default="レース", help="ダッシュボードのタイトル")
    ap.add_argument("--selftest", action="store_true", help="結線のみ検証")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return

    if not args.source:
        ap.error("source(URLまたは動画パス)が必要です。--selftest で結線確認のみ可。")

    workdir = args.outdir or "."
    os.makedirs(workdir, exist_ok=True)

    # ① ダウンロード / 区間切り出し
    print("=" * 56)
    print("① 動画を取得")
    try:
        video = download_section(args.source, args.start, args.end, workdir)
    except Exception as e:
        print(f"\n✗ 取得に失敗しました: {e}\n")
        if args.source and args.source.startswith("http"):
            print("  YouTube等はクラウド環境だとボット判定/遮断で落とせないことがあります。")
            print("  → 自宅PCやColabなど家庭回線で実行してください。")
        sys.exit(1)
    print(f"  取得: {video}")

    # ②③④ run_paddock（分割→歩様→骨格→気配比較）
    print("=" * 56)
    print("②③④ 全頭分割→歩様→骨格→気配比較 (run_paddock)")
    cmd = [PY, os.path.join(HERE, "run_paddock.py"), video]
    if args.roi:
        cmd += ["--roi", args.roi]
    if args.fast:
        cmd += ["--fast"]
    if args.fps:
        cmd += ["--fps", str(args.fps)]
    if args.no_skeleton:
        cmd += ["--no-skeleton"]
    if args.outdir:
        cmd += ["--outdir", args.outdir]
    rc = sh(cmd)
    if rc != 0:
        print("  run_paddock が異常終了しました。ログを確認してください。")

    # 出力フォルダを特定
    outdir = args.outdir or (os.path.splitext(os.path.basename(video))[0] + "_paddock")
    if not os.path.isdir(outdir):
        cand = sorted(glob.glob("*_paddock"), key=os.path.getmtime)
        outdir = cand[-1] if cand else outdir

    # ⑤ 腹圧スコア
    print("=" * 56)
    print("⑤ 腹圧(体幹エンゲージ)スコア")
    run_core_engagement(outdir)

    # ⑥ ダッシュボード
    if not args.no_dashboard:
        print("=" * 56)
        print("⑥ パドックアイ風ダッシュボード")
        dash = os.path.join(outdir, "dashboard.html")
        sh([PY, os.path.join(HERE, "paddock_dashboard.py"),
            "--dir", outdir, "--out", dash, "--title", args.title])

    print("=" * 56)
    print("完了。出力:")
    print(f"  ・各馬クリップ/骨格動画/歩様CSV : {outdir}/")
    print(f"  ・気配ランキング               : {outdir}/kehai.html")
    print(f"  ・腹圧スコア(サイドカー)        : {outdir}/*_fukuatsu.txt")
    if not args.no_dashboard:
        print(f"  ・全頭ダッシュボード           : {outdir}/dashboard.html")


def selftest():
    """DL/推論を伴わず、依存スクリプトと結線が揃っているかだけ検証。
    numpy等の重依存を読み込まないよう paddock_gait はソース走査で確認する。"""
    need = ("run_paddock.py", "paddock_dashboard.py", "core_engagement.py",
            "paddock_segment.py", "paddock_gait.py", "skeleton_overlay.py")
    for f in need:
        assert os.path.exists(os.path.join(HERE, f)), f"依存スクリプトが無い: {f}"
    # paddock_gait が fetch_video / is_url を定義しているか(importせずテキストで)
    with open(os.path.join(HERE, "paddock_gait.py"), encoding="utf-8") as fh:
        src = fh.read()
    assert "def fetch_video(" in src, "paddock_gait.fetch_video が無い"
    assert "def is_url(" in src, "paddock_gait.is_url が無い"
    assert "--download-sections" in src, "区間DL(yt-dlp)の実装が無い"
    # core_engagement は stdlib のみなので実際に読み込んで確認
    import core_engagement as ce
    assert hasattr(ce, "analyze_h5"), "core_engagement.analyze_h5 が無い"
    g = ce.core_metrics_from_frames(ce._synthetic(engaged=True))
    assert g.get("ok"), "core_engagement が動作しない"
    print("SELFTEST PASSED (①DL→②③④run_paddock→⑤腹圧→⑥ダッシュボードの結線OK)")


if __name__ == "__main__":
    main()
