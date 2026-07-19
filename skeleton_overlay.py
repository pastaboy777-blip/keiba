#!/usr/bin/env python3
"""
skeleton_overlay.py — 推論結果(h5)から「関節点＋骨格線」を動画に描画

DeepLabCut既定の出力は点主体なので、Tom Wilson系のウォーキング動画のように
点を線で結んだ骨格オーバーレイを描く。馬の動き（歩様)を目視検証しやすくする。

使い方:
    python skeleton_overlay.py clip.mp4                 # 同名h5を自動検出
    python skeleton_overlay.py clip.mp4 --h5 result.h5 --out skel.mp4
    python skeleton_overlay.py --selftest

出力はH.264(どこでも再生可)。信頼度 pcutoff 未満の点/線は描かない。
"""
import argparse, glob, os, subprocess, sys

PCUTOFF = 0.6

# 背骨(トップライン): き甲→背中→尾の付け根。歩様評価で最重要のため専用に強調描画する。
# ※ tail_end(尾の先)は垂れ下がるので含めない。neck_end(首)も背骨ではないので除く。
SPINE = ["neck_base", "back_base", "back_middle", "back_end", "tail_base"]

# SuperAnimal-Quadruped(39点)に対する馬の骨格線定義
SKELETON = [
    # 顔
    ("nose", "upper_jaw"), ("nose", "lower_jaw"),
    ("upper_jaw", "mouth_end_right"), ("upper_jaw", "mouth_end_left"),
    ("nose", "right_eye"), ("nose", "left_eye"),
    ("right_eye", "right_earbase"), ("left_eye", "left_earbase"),
    ("right_earbase", "right_earend"), ("left_earbase", "left_earend"),
    ("lower_jaw", "throat_base"),
    # 首→背骨→尾
    ("throat_base", "throat_end"),
    ("right_earbase", "neck_end"), ("left_earbase", "neck_end"),
    ("neck_end", "neck_base"), ("neck_base", "back_base"),
    ("back_base", "back_middle"), ("back_middle", "back_end"),
    ("back_end", "tail_base"), ("tail_base", "tail_end"),
    # 前肢(左右)
    ("neck_base", "front_left_thai"), ("neck_base", "front_right_thai"),
    ("body_middle_left", "front_left_thai"), ("body_middle_right", "front_right_thai"),
    ("front_left_thai", "front_left_knee"), ("front_left_knee", "front_left_paw"),
    ("front_right_thai", "front_right_knee"), ("front_right_knee", "front_right_paw"),
    # 後肢(左右)
    ("back_end", "back_left_thai"), ("back_end", "back_right_thai"),
    ("tail_base", "back_left_thai"), ("tail_base", "back_right_thai"),
    ("back_left_thai", "back_left_knee"), ("back_left_knee", "back_left_paw"),
    ("back_right_thai", "back_right_knee"), ("back_right_knee", "back_right_paw"),
    # 胴(腹)
    ("neck_base", "body_middle_left"), ("neck_base", "body_middle_right"),
    ("body_middle_left", "belly_bottom"), ("body_middle_right", "belly_bottom"),
    ("belly_bottom", "back_middle"), ("belly_bottom", "back_end"),
]


def cog_point(getp):
    """馬の重心(第12〜13肋骨=肘の後ろ)を推定して座標を返す。
    き甲(neck_base)から尾根(tail_base)へ約1/3後ろ、トップラインから腹(belly_bottom)へ
    約55%下、を重心とみなす。必要点が無ければ None。"""
    nb, tb, bb = getp("neck_base"), getp("tail_base"), getp("belly_bottom")
    if not (nb and tb):
        return None
    f = 0.33                                   # き甲から後方へ1/3(第12〜13肋骨あたり)
    cx = nb[0] + f * (tb[0] - nb[0])
    ty = nb[1] + f * (tb[1] - nb[1])           # その位置のトップラインの高さ
    if bb:
        by = bb[1]
    else:                                      # 腹が未検出なら体長の1/3下を腹とみなす
        L = ((tb[0] - nb[0]) ** 2 + (tb[1] - nb[1]) ** 2) ** 0.5
        by = ty + 0.33 * L
    cy = ty + 0.55 * (by - ty)                 # トップラインから腹へ55%下
    return (int(cx), int(cy))


def _prep_df(df):
    """マルチ個体h5から『目的馬』を単一トラックとして抽出し (bodyparts, coords) にする。
    paddock_gait.extract_target_horse と同じロジックで、毎フレーム最大・手前・連続する
    馬を選び、別馬への乗り移りフレームを除外する。"""
    import paddock_gait
    return paddock_gait.extract_target_horse(df)


def render(video, h5, out, pcutoff=PCUTOFF):
    import cv2, numpy as np, pandas as pd
    df = _prep_df(pd.read_hdf(h5))
    bps = list(df.columns.get_level_values(0).unique())
    # 各bodypartに固定色(虹)を割当
    cmap = {}
    for i, bp in enumerate(bps):
        hue = int(179 * i / max(1, len(bps) - 1))
        c = cv2.cvtColor(np.uint8([[[hue, 220, 255]]]), cv2.COLOR_HSV2BGR)[0, 0]
        cmap[bp] = (int(c[0]), int(c[1]), int(c[2]))

    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    tmp = os.path.splitext(out)[0] + "_tmp.mp4"
    vw = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))

    def pt(row, bp):
        if (bp, "likelihood") not in df.columns:
            return None
        if row[(bp, "likelihood")] < pcutoff:
            return None
        x, y = row[(bp, "x")], row[(bp, "y")]
        if x != x or y != y:
            return None
        return (int(x), int(y))

    n = min(len(df), int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or len(df)))
    for i in range(n):
        ok, fr = cap.read()
        if not ok:
            break
        row = df.iloc[i]
        # 骨格線(黒・やや細)
        for a, b in SKELETON:
            pa, pb = pt(row, a), pt(row, b)
            if pa and pb:
                cv2.line(fr, pa, pb, (20, 20, 20), 2, cv2.LINE_AA)
        # ★背骨(トップライン): 最重要。太い緑線で強調描画。
        # 背骨はほぼ直線なので、首の根本(neck_base)と尾(tail_base)を直線1本で結ぶ。
        # 途中の背中の点はサドル/腹に落ちやすく線を凹ませるため使わない。
        avail = [p for p in (pt(row, bp) for bp in SPINE) if p]
        if len(avail) >= 2:
            a, b = avail[0], avail[-1]      # 端＝首の根本 と 尾の付け根
            cv2.line(fr, a, b, (255, 255, 255), 8, cv2.LINE_AA)   # 白フチ
            cv2.line(fr, a, b, (60, 220, 30), 4, cv2.LINE_AA)     # 緑本体
        # 関節点(色付き)。背骨の関節は大きめに
        for bp in bps:
            p = pt(row, bp)
            if p:
                r = 9 if bp in SPINE else 6
                cv2.circle(fr, p, r, cmap[bp], -1, cv2.LINE_AA)
        # ●馬の重心(第12〜13肋骨・肘の後ろ)を赤い点で表示
        cog = cog_point(lambda bp: pt(row, bp))
        if cog:
            cv2.circle(fr, cog, 13, (255, 255, 255), -1, cv2.LINE_AA)  # 白フチ
            cv2.circle(fr, cog, 10, (0, 0, 255), -1, cv2.LINE_AA)      # 赤(重心)
        vw.write(fr)
    cap.release(); vw.release()

    # H.264へ変換(どこでも再生可)
    subprocess.run(["ffmpeg", "-y", "-i", tmp, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "23", "-preset", "veryfast", "-movflags", "+faststart", out],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.remove(tmp)
    print(f"骨格線オーバーレイ動画を保存: {out}")
    return out


def find_h5(video):
    stem = os.path.splitext(os.path.basename(video))[0]
    d = os.path.dirname(video) or "."
    c = sorted(glob.glob(os.path.join(d, f"{stem}*superanimal_quadruped*.h5")))
    return c[-1] if c else None


def selftest():
    # 骨格定義が既知bodypartのみを参照しているか検証
    known = {
        "nose","upper_jaw","lower_jaw","mouth_end_right","mouth_end_left","right_eye",
        "right_earbase","right_earend","left_eye","left_earbase","left_earend","neck_base",
        "neck_end","throat_base","throat_end","back_base","back_end","back_middle",
        "tail_base","tail_end","front_left_thai","front_left_knee","front_left_paw",
        "front_right_thai","front_right_knee","front_right_paw","back_left_paw",
        "back_left_thai","back_right_thai","back_left_knee","back_right_knee",
        "back_right_paw","belly_bottom","body_middle_right","body_middle_left",
    }
    bad = {p for e in SKELETON for p in e if p not in known}
    assert not bad, f"未知のbodypart: {bad}"
    print(f"SELFTEST PASSED (骨格線 {len(SKELETON)}本, 全て既知の関節を参照)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--h5", help="推論結果h5(省略時は自動検出)")
    ap.add_argument("--out", help="出力mp4(省略時は <video>_skeleton.mp4)")
    ap.add_argument("--pcutoff", type=float, default=PCUTOFF)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest(); return
    if not args.video:
        ap.error("動画パスを指定してください（または --selftest）")
    h5 = args.h5 or find_h5(args.video)
    if not h5 or not os.path.exists(h5):
        ap.error("推論結果h5が見つかりません。--h5 で指定してください")
    out = args.out or (os.path.splitext(args.video)[0] + "_skeleton.mp4")
    render(args.video, h5, out, args.pcutoff)


if __name__ == "__main__":
    main()
