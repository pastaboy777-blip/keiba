#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""腹圧（体幹エンゲージメント）スコア  core_engagement.py

「その馬が腹圧を使えているか」をパドック映像の骨格から定量化する。

― 何を測っているか ―
腹腔内圧（IAP）や腹筋のEMGは外から直接は測れない。だが腹圧を使って体幹を
固め、背中を吊り上げている馬は、横から見て必ず次の“見える結果”を伴う
（青木修『走りと重心』の背線理論 / 馬場馬術のエンゲージメント＝ハミ受け・
半減却で背を丸めトモを踏み込む、と同じ指標）：

  1. 背線のリフト (topline_camber)  … 背中中央(back_middle)が首〜尾を結ぶ
     弦に対しどれだけ背側へ持ち上がっているか。腹圧が抜けると鞍部が落ちる(凹背)。
  2. 腹の引き上げ (belly_tuck)      … 腹の底(belly_bottom)が体軸にどれだけ
     近いか（＝腹が吊り上がっているか）。緩むと腹線が垂れ下がる。
  3. 後肢の踏み込み (hind_engagement)… 後肢の蹄(back_paw)が股関節(back_thai)
     より前＝重心の下へどれだけ入るか。体幹が効くと深く踏み込める。
  4. 背の安定 (topline_stability)   … 背線の上下動の小ささ。吊れていれば揺れない。
  5. 骨盤の入り (pelvic_tuck)       … 尻(back_end→tail_base)が体軸に対し
     巻き込まれているか（腰椎屈曲）。

これらを0〜100に正規化し、重み付き合成した **腹圧スコア** を返す。
※あくまで“幾何学的な代理指標”。直接の筋活動ではなく、人の目が見ている
  外形的な結果を数値化したもの。閾値（アンカー）は暫定で、実データで要較正。

使い方:
  python3 core_engagement.py --h5 out/uma06.h5            # 1頭を解析
  python3 core_engagement.py --h5 a.h5 b.h5 --names 6番 7番  # 複数頭を比較
  python3 core_engagement.py --selftest                   # 合成データで検証
"""
import argparse
import math
import statistics as st

PCUTOFF = 0.6

# ―― 合成に使う指標の重み（腹圧への寄与・可視性の信頼度で配分）――
WEIGHTS = {
    "topline_camber":    0.40,   # 最も直接的で見やすい
    "hind_engagement":   0.30,
    "belly_tuck":        0.15,
    "topline_stability": 0.10,
    "pelvic_tuck":       0.05,
}

# ―― 0〜100へ写像するアンカー（暫定・実データで較正する）――
#   (worst_value, best_value)  … worst→0点, best→100点 に線形写像
ANCHORS = {
    # 背側リフト比（弦からの背側オフセット / 体長）。凹背(負)→持ち上げ(正)
    "topline_camber":    (-0.060, 0.020),
    # 後肢の踏み込み比（股より前への最大到達 / 体長）
    "hind_engagement":   (0.00, 0.35),
    # 腹の深さ比（体軸から腹底までの距離 / 体長）。深い(垂れ)→浅い(吊り上げ)
    "belly_tuck":        (0.46, 0.30),   # 値が小さいほど良い＝反転アンカー
    # 背線のブレ（背側オフセット比の標準偏差）。大→小 が良い＝反転アンカー
    "topline_stability": (0.055, 0.010),
    # 骨盤の巻き込み角（体軸と尻線のなす角 deg）。寝すぎ/立ちすぎを中庸で評価
    "pelvic_tuck":       (0.0, 18.0),
}

LABELS = {
    "topline_camber":    "背線のリフト",
    "hind_engagement":   "後肢の踏み込み",
    "belly_tuck":        "腹の引き上げ",
    "topline_stability": "背の安定",
    "pelvic_tuck":       "骨盤の入り",
}


# ───────────────────────── 幾何ヘルパ ─────────────────────────
def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _signed_dist(p, a, b):
    """線 a→b に対する点p の符号付き距離（+は a→b ベクトルの左側）。"""
    vx, vy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(vx, vy) or 1.0
    cross = vx * (p[1] - a[1]) - vy * (p[0] - a[0])
    return cross / L


def _angle_between(v, w):
    """2ベクトルのなす角(deg)。"""
    dot = v[0] * w[0] + v[1] * w[1]
    nv = math.hypot(*v) or 1.0
    nw = math.hypot(*w) or 1.0
    c = max(-1.0, min(1.0, dot / (nv * nw)))
    return math.degrees(math.acos(c))


def _lerp01(x, worst, best):
    """worst→0, best→100 へ線形写像しクリップ。"""
    if best == worst:
        return 0.0
    t = (x - worst) / (best - worst)
    return max(0.0, min(100.0, 100.0 * t))


def _get(frame, name):
    """frame(dict bp->(x,y)) から点を取得。無ければ None。"""
    return frame.get(name)


def _first(frame, names):
    for n in names:
        p = frame.get(n)
        if p:
            return p
    return None


# ───────────────────────── 指標計算 ─────────────────────────
def core_metrics_from_frames(frames, min_frames=6):
    """frames: 各フレームの {bodypart: (x,y)} のリスト（目的馬・単一トラック）。
    戻り値: dict（raw指標・0-100正規化・合成スコア・内訳・判定）。"""
    cambers, depths, pelvics, reaches = [], [], [], []

    for fr in frames:
        N = _get(fr, "neck_base")
        T = _get(fr, "tail_base") or _get(fr, "back_end")
        M = _get(fr, "back_middle")
        B = _get(fr, "belly_bottom")
        if not (N and T):
            continue
        L = _dist(N, T) or 1.0

        # 背側(dorsal)方向の符号を belly_bottom から決める
        if B:
            s_belly = _signed_dist(B, N, T)
            dorsal_sign = -1.0 if s_belly >= 0 else 1.0
        else:
            # 腹点が無ければ画面下(y+)を腹とみなす
            vx, vy = T[0] - N[0], T[1] - N[1]
            dorsal_sign = 1.0 if (-vx) <= 0 else -1.0  # 近似

        # 1. 背線リフト比
        if M:
            cam = dorsal_sign * _signed_dist(M, N, T) / L
            cambers.append(cam)

        # 2. 腹の深さ比（体軸から腹底まで・ventral側の距離）
        if B:
            depths.append(abs(_signed_dist(B, N, T)) / L)

        # 5. 骨盤の巻き込み角（体軸 vs 尻線 back_end→tail_base）
        BE, TB = _get(fr, "back_end"), _get(fr, "tail_base")
        if BE and TB:
            axis = (T[0] - N[0], T[1] - N[1])
            croup = (TB[0] - BE[0], TB[1] - BE[1])
            pelvics.append(_angle_between(axis, croup))

        # 3. 後肢の踏み込み（股より前への到達 / L）。
        #    前方=頭の向き(尾→首のベクトル)。蹄が股より前方へ射影されるほど+。
        fdx, fdy = (N[0] - T[0]), (N[1] - T[1])
        fL = math.hypot(fdx, fdy) or 1.0
        fux, fuy = fdx / fL, fdy / fL          # 前方単位ベクトル
        for paw_bp, hip_bp in (("back_left_paw", "back_left_thai"),
                               ("back_right_paw", "back_right_thai")):
            paw = _get(fr, paw_bp)
            hip = _get(fr, hip_bp) or BE
            if paw and hip:
                # (蹄−股) を前方方向へ射影。+なら蹄が股より前＝踏み込み
                reach = ((paw[0] - hip[0]) * fux + (paw[1] - hip[1]) * fuy) / L
                reaches.append(reach)

    n_ok = len(cambers)
    if n_ok < min_frames:
        return {"ok": False, "reason": f"有効フレーム不足({n_ok}<{min_frames})"}

    raw = {}
    raw["topline_camber"] = st.mean(cambers)
    # 踏み込みは“最も深い一歩”を代表に（上位20%平均）
    if reaches:
        reaches_sorted = sorted(reaches, reverse=True)
        top = reaches_sorted[:max(1, len(reaches_sorted) // 5)]
        raw["hind_engagement"] = st.mean(top)
    else:
        raw["hind_engagement"] = None
    raw["belly_tuck"] = st.mean(depths) if depths else None
    raw["topline_stability"] = st.pstdev(cambers) if len(cambers) > 1 else 0.0
    raw["pelvic_tuck"] = st.mean(pelvics) if pelvics else None

    # 0-100 正規化
    norm = {}
    for k, (worst, best) in ANCHORS.items():
        v = raw.get(k)
        norm[k] = None if v is None else round(_lerp01(v, worst, best), 1)

    # 重み付き合成（欠損指標は重みから除外して再正規化）
    num = den = 0.0
    for k, w in WEIGHTS.items():
        if norm.get(k) is not None:
            num += w * norm[k]
            den += w
    score = round(num / den, 1) if den else 0.0

    verdict = ("◎ 腹圧しっかり" if score >= 70 else
               "○ 使えている"   if score >= 55 else
               "△ やや抜け気味" if score >= 40 else
               "× 腹圧抜け(凹背/踏み込み浅い)")

    # 強み/弱み
    present = {k: v for k, v in norm.items() if v is not None}
    strengths = sorted(present, key=lambda k: present[k], reverse=True)[:2]
    weaks = sorted(present, key=lambda k: present[k])[:2]

    return {
        "ok": True, "n_frames": n_ok, "raw": raw, "norm": norm,
        "score": score, "verdict": verdict,
        "strength": [LABELS[k] for k in strengths],
        "weakness": [LABELS[k] for k in weaks],
    }


# ───────────────────── h5 読み込み（実パイプライン用）─────────────────────
def frames_from_h5(h5_path, pcutoff=PCUTOFF):
    """DeepLabCut h5 から目的馬を抽出し frames(list of dict bp->(x,y)) に変換。"""
    import pandas as pd
    import paddock_gait
    df = paddock_gait.extract_target_horse(pd.read_hdf(h5_path))
    bps = list(df.columns.get_level_values(0).unique())
    frames = []
    for _, row in df.iterrows():
        fr = {}
        for bp in bps:
            if (bp, "likelihood") in df.columns and row[(bp, "likelihood")] >= pcutoff:
                x, y = row[(bp, "x")], row[(bp, "y")]
                if x == x and y == y:  # not NaN
                    fr[bp] = (float(x), float(y))
        frames.append(fr)
    return frames


def analyze_h5(h5_path, pcutoff=PCUTOFF):
    return core_metrics_from_frames(frames_from_h5(h5_path, pcutoff))


# ───────────────────────── 表示 ─────────────────────────
def print_report(res, name=""):
    head = f"【腹圧スコア】{name}".strip()
    if not res.get("ok"):
        print(f"{head}: 解析不可 — {res.get('reason')}")
        return
    print(f"{head}:  {res['score']} / 100   {res['verdict']}  （{res['n_frames']}フレーム）")
    for k in WEIGHTS:
        v = res["norm"].get(k)
        r = res["raw"].get(k)
        bar = "█" * int((v or 0) / 5)
        rtxt = "―" if r is None else f"{r:+.3f}" if abs(r) < 10 else f"{r:.1f}"
        vt = " ―" if v is None else f"{v:5.1f}"
        print(f"   {LABELS[k]:　<7} {vt}  {bar:<20} (raw {rtxt})")
    print(f"   強み: {' / '.join(res['strength'])}   弱み: {' / '.join(res['weakness'])}")


# ───────────────────────── selftest ─────────────────────────
def _synthetic(engaged=True, n=40):
    """合成フレーム生成。engaged=True は腹圧◎(背リフト・腹吊り・深い踏み込み)、
    False は腹圧抜け(凹背・腹垂れ・浅い踏み込み)。左向き(頭が左=x小)で歩く。"""
    frames = []
    for i in range(n):
        ph = 2 * math.pi * i / 8.0           # 歩隔の位相
        x0 = 400 - i * 2                      # 前進（頭が左へ）
        # 体軸（ほぼ水平）: 首根本(左) → 尾(右)
        neck = (x0 - 120, 200)
        tail = (x0 + 120, 200)
        back_end = (x0 + 80, 200)
        # 背中央: engagedは背側(上=y小)へリフト、抜けは鞍部が落ちる(下=y大)
        lift = -10 if engaged else +14
        bounce = (1.0 if engaged else 4.0) * math.sin(ph)   # 抜けは上下動大
        back_mid = (x0, 200 + lift + bounce)
        # 腹底: engagedは吊り上げ(浅い)、抜けは垂れ(深い)
        belly_depth = 70 if engaged else 110
        belly = (x0, 200 + belly_depth)
        # 後肢: engagedは蹄が股より前へ深く踏み込む
        hip = (x0 + 70, 230)
        step = (40 if engaged else 8) * (0.5 + 0.5 * math.sin(ph))
        paw = (hip[0] - step, 330)           # 頭方向(x小)へ step ぶん前進
        frames.append({
            "neck_base": neck, "tail_base": tail, "back_end": back_end,
            "back_middle": back_mid, "belly_bottom": belly,
            "back_left_thai": hip, "back_left_paw": paw,
        })
    return frames


def selftest():
    good = core_metrics_from_frames(_synthetic(engaged=True))
    bad = core_metrics_from_frames(_synthetic(engaged=False))
    assert good["ok"] and bad["ok"], "合成データ解析に失敗"
    print_report(good, "合成・腹圧◎")
    print_report(bad, "合成・腹圧抜け")
    # 腹圧ありの方が高スコア
    assert good["score"] > bad["score"], f"スコア順序が逆: {good['score']} vs {bad['score']}"
    # 個別指標の向きも確認
    assert good["norm"]["topline_camber"] > bad["norm"]["topline_camber"], "背線リフトの向きが逆"
    assert good["norm"]["hind_engagement"] > bad["norm"]["hind_engagement"], "踏み込みの向きが逆"
    assert good["norm"]["topline_stability"] > bad["norm"]["topline_stability"], "背の安定の向きが逆"
    assert good["score"] >= 55, f"腹圧◎が低すぎ: {good['score']}"
    assert bad["score"] <= 45, f"腹圧抜けが高すぎ: {bad['score']}"
    print("\nSELFTEST PASSED (腹圧スコアが『使える馬>抜けた馬』を正しく判別)")


# ───────────────────────── CLI ─────────────────────────
def main():
    ap = argparse.ArgumentParser(description="腹圧（体幹エンゲージメント）スコア")
    ap.add_argument("--h5", nargs="*", default=[], help="DeepLabCut h5（複数可）")
    ap.add_argument("--names", nargs="*", default=[], help="各h5の表示名")
    ap.add_argument("--pcutoff", type=float, default=PCUTOFF)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return

    if not args.h5:
        ap.error("--h5 を指定するか --selftest を使ってください")

    results = []
    for i, h5 in enumerate(args.h5):
        name = args.names[i] if i < len(args.names) else h5
        res = analyze_h5(h5, args.pcutoff)
        results.append((name, res))
        print_report(res, name)
        print()

    # 複数頭なら腹圧スコア順にランキング
    ok = [(n, r) for n, r in results if r.get("ok")]
    if len(ok) > 1:
        ok.sort(key=lambda nr: nr[1]["score"], reverse=True)
        print("―― 腹圧ランキング ――")
        for rank, (n, r) in enumerate(ok, 1):
            print(f"  {rank}. {n:　<10} {r['score']:5.1f}  {r['verdict']}")


if __name__ == "__main__":
    main()
