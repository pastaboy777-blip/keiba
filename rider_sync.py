#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""馬のバネ × 騎手のアクション 相関解析（モデル推定）  rider_sync.py

馬の「バネ」（背・重心の鉛直オシレーション＝上下動）と、騎手の「乗り方」
（重心の振れ＝アクション：鉛直の浮き沈み・前後の推進動作）を数値化し、
ユーザー仮説『馬のバネが大きいほど騎手のアクションが大きい』を測れる形にする。

  frames入力（各フレーム {bodypart:(x,y)} のリスト）で動く pandas/cv2 非依存のコア。
  馬は biomech.body_frame / cog / body_len を、騎手は rider_cog.rider_cog を流用する。
  騎手ポーズは COCO-17（rider_cog準拠）。

─────────────────────────────────────────────────────────────────────────
【重要・設計上の注意（仮説検証の本質）】
  同一ペア（1頭＋その騎手）の内部では、馬のバネと騎手の動きが連動するのは
  “自明”である。騎手は馬に乗っており、馬が跳ねれば騎手も（吸収しきれない分だけ）
  動く。つまり1ペア内の相関は仮説の検証にならない。

  ユーザー仮説『馬のバネが大きいほど騎手のアクションが大きい』の本来の検証は、
  “馬をまたいだ” 比較── すなわち【バネの大きい馬ほど、その上の騎手のアクション
  （特に前後の推進動作 A_drive）が大きいか】という、複数ペア間の
  A_horse ↔ A_drive の相関である。これには実データの複数ペアが要る。
  本モジュールの correlate_pairs はそのための器であり、3ペア未満では
  「判定不可(サンプル不足)」を返す。

【すべて推定・計測の限界】
  ・馬の重心・騎手の重心はいずれも 2D単眼ポーズ＋標準モデルからの“推定”であり
    実測ではない（biomech.cog / rider_cog の明記を参照）。
  ・「バネ」「アクション」は重心・背の画面上オシレーション振幅から求める相対指標。
    カメラのパン/ズーム・奥行き・個体差・鞍やスターティング姿勢は補正していない。
  ・鉛直＝画像y（重力方向の近似）、前後＝進行方向成分。線形トレンド（並進ドリフト）は
    除去するが、周期以外の揺れは残りうる。参考値として相対比較に用いること。

【一次証言（設計根拠）── 横山武史『with 佑』】
  現役トップ騎手の証言から「測るべき量」を定めた：
   ・膝を支点に脚をばねのように使い、馬の反発（バネ）を受けて体を“ぶらす”（＝アクション）。
   ・体が大きくダイナミックに走る馬（＝バネ大）ほど、大きなぶらしを使える。
   ・完歩の小さいピッチ走法（高頻度）の馬は足をぶらせない。ぶらそうとした時には
     馬の完歩が既に次の一歩へ移っており、人の動きが“位相遅れ”してしまう。
  ⇒ 使えるアクションの大きさは【馬のバネ A_horse】×【馬のピッチ＝完歩頻度 stride_freq】に
     拘束され、鍵は騎手の鉛直オシレーションが馬のストライドと“同位相”で乗れているか。
     本モジュールは stride_freq（完歩頻度Hz）と phase_sync（同期度＝相互相関ピーク値／
     位相遅れ）でこれを数値化する。高同期＝デムーロ的「連動した大アクション」、
     位相遅れ大＝ピッチ馬で“ぶらせない”状態。

【『逆回転』の実測化 ── 下肢ループ循環方向の反転】
  武史証言「右回りの洗濯機を左回りに」「人間の動き自体が逆回転」の核心は、
  騎手の下肢（膝→足首）や重心が矢状面（前後x×上下y）で描く“閉じたループ”の
  循環方向（時計回り/反時計回り）が、乗り方で反転することにある。
   ・鐙（あぶみ）支点のアメリカン型 と 膝支点のヨーロピアン型 でループの回り方が逆。
  これを leg_loop_sense / cog_loop_sense が、1完歩ぶんの軌跡の【符号付き面積】
  （shoelace）として実測化する。符号の基準は本ファイル内コメントで明示。
  ※符号付き面積は“向き”の相対指標であって、絶対的な良否（優劣）ではない。
    型推定ラベル（ヨーロピアン寄り/アメリカン寄り/中間）は暫定閾値による目安。
─────────────────────────────────────────────────────────────────────────

使い方:
  import rider_sync as rs
  rs.horse_bounce(horse_frames)                         # 馬の鉛直バネ（体長比）
  rs.rider_motion(rider_frames, forward_sign=-1, norm_px=L)  # 騎手の振幅
  rs.stride_freq(horse_frames, fps)                     # 馬の完歩頻度(Hz)
  rs.phase_sync(horse_vert_series, rider_vert_series, fps)   # 同期度・位相遅れ
  rs.pair_metrics(horse_frames, rider_frames, forward_sign, fps)  # 1ペアまとめ
  rs.correlate_pairs([pm1, pm2, pm3, ...])              # 複数ペアの相関（仮説検証）
  python3 rider_sync.py --selftest
"""
import math
import statistics as st

import biomech
import rider_cog as rc


# ───────── 信号処理ヘルパ（stdlib） ─────────
def _detrend(ys):
    """線形トレンド（並進ドリフト・カメラパン）を最小二乗で除去。
    残差＝オシレーション成分。"""
    n = len(ys)
    if n < 2:
        return list(ys)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs) or 1e-9
    sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    b = sxy / sxx
    a = my - b * mx
    return [ys[i] - (a + b * xs[i]) for i in range(n)]


def _amp(sig):
    """オシレーション振幅: (p-p＝最大-最小, 2×標準偏差)。"""
    if len(sig) < 2:
        return 0.0, 0.0
    pp = max(sig) - min(sig)
    sd2 = 2.0 * st.pstdev(sig)
    return pp, sd2


def _autocorr_norm(sig):
    """項数(n-lag)で正規化した自己相関 r[lag]（r[0]=1）。lag=0..n//2。"""
    n = len(sig)
    m = sum(sig) / n
    s = [x - m for x in sig]
    var = (sum(x * x for x in s) / n) or 1e-9
    r = [0.0] * (n // 2 + 1)
    for lag in range(0, n // 2 + 1):
        cnt = n - lag
        r[lag] = (sum(s[i] * s[i - lag] for i in range(lag, n)) / cnt) / var
    return r


def _dominant_period(sig, min_lag=2):
    """主要周期（フレーム数）＝正規化自己相関の“最初のピーク”のラグ。
    周期性が無ければ None。項数で正規化するので短ラグへの偏りが無い。"""
    n = len(sig)
    if n < 2 * min_lag + 1:
        return None
    r = _autocorr_norm(sig)
    half = n // 2
    for lag in range(min_lag, half):
        if r[lag] > 0.3 and r[lag] >= r[lag - 1] and r[lag] >= r[lag + 1]:
            return lag
    # ピークが明確でなければ正規化自己相関の最大ラグで代用
    cand = range(min_lag, half + 1)
    best = max(cand, key=lambda L: r[L])
    return best if r[best] > 0.1 else None


def _pearson(xs, ys):
    """ピアソン相関係数（stdlib）。分散0・サンプル不足はNone。"""
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sx = sum((x - mx) ** 2 for x in xs)
    sy = sum((y - my) ** 2 for y in ys)
    if sx <= 0 or sy <= 0:
        return None
    sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    return sxy / math.sqrt(sx * sy)


# ───────── 1. 馬の鉛直バネ ─────────
def horse_vertical_series(horse_frames):
    """馬の鉛直（体軸に直交＝進行成分を除いた）オシレーション系列と体長中央値。

    back_middle（無ければ biomech.cog）を、biomech.body_frame の前方unit
    （体軸：尾→首）に直交する軸へ射影し、線形トレンド（並進ドリフト）を除いた系列。
    phase_sync / stride_freq の入力に使う。
    戻り: (sig:list, L:float) / (None, None)。"""
    pts, fwds, lens = [], [], []
    for fr in horse_frames:
        if not fr:
            continue
        p = fr.get("back_middle") or biomech.cog(fr)
        bf = biomech.body_frame(fr)
        if p and bf:
            pts.append(p)
            fwds.append(bf[1])          # 前方unit f（尾→首）
        bl = biomech.body_len(fr)
        if bl:
            lens.append(bl)
    if len(pts) < 4 or not lens:
        return None, None
    # 平均前方unit → それに直交する軸＝鉛直（進行成分を除く）
    fx = sum(f[0] for f in fwds) / len(fwds)
    fy = sum(f[1] for f in fwds) / len(fwds)
    nf = math.hypot(fx, fy) or 1e-9
    perp = (-fy / nf, fx / nf)          # 体軸に直交（≒鉛直）
    if perp[1] > 0:                     # 画像は下向きが+。perpを“上向き+”に揃える
        perp = (-perp[0], -perp[1])
    sig = _detrend([p[0] * perp[0] + p[1] * perp[1] for p in pts])
    return sig, (st.median(lens) or 1.0)


def horse_bounce(horse_frames):
    """馬の鉛直バネ（1完歩あたりの上下動の振幅, 体長比）。

    horse_vertical_series の振幅を体長で正規化して返す。
    戻り: {"振幅_体長比": p-p, "振幅2sd_体長比": 2×SD, "n": 点数, "体長px": 物差し}
          有効点<4 や体長不明なら None。
    ※実測ではなくモデル推定（ファイル冒頭参照）。"""
    sig, L = horse_vertical_series(horse_frames)
    if sig is None:
        return None
    pp, sd2 = _amp(sig)
    return {"振幅_体長比": round(pp / L, 4),
            "振幅2sd_体長比": round(sd2 / L, 4),
            "n": len(sig), "体長px": round(L, 1)}


# ───────── 1b. 馬の完歩頻度（ピッチ） ─────────
def stride_freq(horse_frames, fps):
    """馬の完歩頻度(Hz)。蹄の前後位置（体フレーム, biomech.hoof_track）の周期を
    自己相関で推定。蹄が無ければ背の鉛直バネ系列の周期で代用。fps必須。
    算出不能なら None。完歩頻度が高い＝ピッチ走法（足をぶらせない）。"""
    if not fps:
        return None
    track = biomech._first_track(
        horse_frames,
        ("back_left_paw", "back_right_paw", "front_left_paw", "front_right_paw"))
    if len(track) >= 8:
        sig = _detrend([p[0] for p in track])      # 蹄の前後オシレーション
    else:
        sig, _ = horse_vertical_series(horse_frames)   # 代用：背の上下動
    if not sig or len(sig) < 6:
        return None
    lag = _dominant_period(sig)
    if not lag:
        return None
    return round(fps / lag, 3)


# ───────── 2. 騎手のアクション ─────────
def _torso_len(rider_frames):
    """騎手の胴長（肩中点→股中点）の中央値。正規化px未指定時の人スケール代替。"""
    ds = []
    for fr in rider_frames:
        sm = rc._point(fr, "shoulder_mid", rc.PCUTOFF)
        hm = rc._point(fr, "hip_mid", rc.PCUTOFF)
        if sm and hm:
            ds.append(math.hypot(sm[0] - hm[0], sm[1] - hm[1]))
    return st.median(ds) if ds else None


def rider_motion(rider_frames, forward_sign=1.0, norm_px=None):
    """騎手の動き（乗り方＝重心の振れ）を振幅で返す。

    各フレームに rider_cog.rider_cog を適用して人の重心列を得て、
      A_rider_vert … 鉛直（画像y）オシレーション振幅
      A_drive       … 前後（進行方向）オシレーション振幅＝推進・押しの動き
    を算出。いずれも線形トレンド（馬とともに前進する並進ドリフト）を除いた振幅。
    進行方向は forward_sign（進行方向が画面+xなら+1, -xなら-1）。

    正規化 norm_px は馬の体長px推奨（decoupling を馬のバネと比較可能にするため）。
    未指定なら騎手胴長（肩幅相当の人スケール）で代替し、さらに無ければ素のpxを返す。

    戻り: {"A_rider_vert", "A_drive", "A_rider_vert_2sd", "A_drive_2sd",
           "n", "正規化px"}  有効重心<4 なら None。
    ※実測ではなくモデル推定（ファイル冒頭参照）。"""
    cogs = []
    for fr in rider_frames:
        c = rc.rider_cog(fr)
        if c:
            cogs.append(c)
    if len(cogs) < 4:
        return None
    xs = [c[0] for c in cogs]
    ys = [c[1] for c in cogs]
    drive_sig = _detrend([x * forward_sign for x in xs])   # 前後（進行方向）
    vert_sig = _detrend(ys)                                # 鉛直（画像y）
    L = norm_px or _torso_len(rider_frames) or 1.0
    v_pp, v_sd2 = _amp(vert_sig)
    d_pp, d_sd2 = _amp(drive_sig)
    return {"A_rider_vert": round(v_pp / L, 4), "A_drive": round(d_pp / L, 4),
            "A_rider_vert_2sd": round(v_sd2 / L, 4), "A_drive_2sd": round(d_sd2 / L, 4),
            "n": len(cogs), "正規化px": round(L, 1)}


def rider_vertical_series(rider_frames):
    """騎手重心の鉛直(画像y)オシレーション系列（線形トレンド除去済み）。
    phase_sync の入力。有効重心<4 なら None。"""
    ys = []
    for fr in rider_frames:
        c = rc.rider_cog(fr)
        if c:
            ys.append(-c[1])          # 画像は下向きが+なので反転＝“上向き+”（馬側と統一）
    if len(ys) < 4:
        return None
    return _detrend(ys)


# ───────── 2b. 位相同期（馬のバネ vs 騎手の上下動） ─────────
def phase_sync(horse_vertical_series, rider_vertical_series, fps=None):
    """馬の鉛直オシレーションと騎手の鉛直オシレーションの位相同期。

    正規化相互相関（NCC）を全ラグで計算し、
      sync          … ピーク値（0〜1。同期度。負相関は0＝非同期扱い）
      phase_lag_*   … ピークを与えるラグ＝騎手の位相遅れ（＋＝騎手が馬に遅れる）
    を返す。同位相で高振幅に乗れていれば sync 高（連動した大アクション＝デムーロ的）。
    位相遅れが大きく波形も崩れる（ピッチ馬で“ぶらせない”）と sync 低。

    戻り: {"sync", "phase_lag_frames", "phase_lag_deg", "phase_lag_sec",
           "period_frames"}  入力不足なら None。"""
    hs, rs = horse_vertical_series, rider_vertical_series
    if not hs or not rs:
        return None
    n = min(len(hs), len(rs))
    if n < 6:
        return None
    hm = sum(hs[:n]) / n
    rm = sum(rs[:n]) / n
    h = [hs[i] - hm for i in range(n)]
    r = [rs[i] - rm for i in range(n)]
    # 位相は1完歩以内で評価（周期の整数倍ずれの多義性を避ける）。
    period = _dominant_period(h) or _dominant_period(r)
    maxlag = max(2, int(round((period or n // 2) / 2.0)))
    maxlag = min(maxlag, n // 2)
    best, best_lag = -2.0, 0
    for lag in range(-maxlag, maxlag + 1):
        num = dh = dr = 0.0
        for i in range(n):
            j = i + lag
            if 0 <= j < n:
                num += h[i] * r[j]
                dh += h[i] * h[i]
                dr += r[j] * r[j]
        if dh > 1e-12 and dr > 1e-12:
            cc = num / math.sqrt(dh * dr)
            if cc > best:
                best, best_lag = cc, lag
    return {
        "sync": round(max(0.0, best), 3),
        "phase_lag_frames": best_lag,
        "phase_lag_deg": round(360.0 * best_lag / period, 1) if period else None,
        "phase_lag_sec": round(best_lag / fps, 4) if fps else None,
        "period_frames": period,
    }


# ───────── 2c. 下肢ループの回転の向き（『逆回転』の実測化） ─────────
#
# 座標系と符号の基準（重要・明示）:
#   各点を「体フレーム」= 進行方向を +x（前方）、画面上方向を +y（上）に取り直す。
#     fwd = (rider_cog_x 等) に forward_sign を掛けて前方を +x に統一。
#     up  = -画像y（画像は下向きが+なので符号反転）で上を +y に。
#   この右手系（x右・y上）で shoelace の符号付き面積 A を計算すると、
#     A > 0 … 反時計回り（CCW）
#     A < 0 … 時計回り（CW）
#   基準の対応づけ（暫定・コメントで固定）:
#     +（反時計回り/CCW） → 膝支点ヨーロピアン寄り
#     −（時計回り/CW）   → 鐙支点アメリカン寄り
#   ※この＋/−の割り当ては相対的な“向き”の規約であり、良否ではない（冒頭参照）。
#     実データで型が既知のサンプルを得たら符号対応を校正する前提の暫定値。

# 型推定の暫定しきい値（|符号付き面積|＝体長比。これ未満は向きが不定＝中間/ミックス）
LOOP_SENSE_DEADBAND = 0.002


def _loop_signed_area(frames, point_fn, forward_sign, norm_px):
    """point_fn(fr)->(x,y)（画像座標）の軌跡を体フレーム(前方+x, 上+y)へ直し、
    shoelace で1完歩ぶんの符号付き面積を計算。norm_px(体長/胴長)の2乗で正規化。
    戻り: (signed_area_正規化, n) / (None, 0)。
    注: 1完歩ぶん＝点列が一巡するループ（多周回でも面積は相殺されず平均的に符号を保つ）。"""
    pts = []
    for fr in frames:
        p = point_fn(fr)
        if p and p[0] == p[0] and p[1] == p[1]:
            pts.append((p[0] * forward_sign, -p[1]))   # 前方+x, 上+y
    if len(pts) < 6 or not norm_px:
        return None, 0
    # 前後・上下とも線形トレンド（前進ドリフト・オフセット）を除去＝閉ループ化
    xs = _detrend([p[0] for p in pts])
    ys = _detrend([p[1] for p in pts])
    area2 = 0.0
    m = len(xs)
    for i in range(m):
        x1, y1 = xs[i], ys[i]
        x2, y2 = xs[(i + 1) % m], ys[(i + 1) % m]
        area2 += x1 * y2 - x2 * y1
    area = 0.5 * area2
    # 多周回ぶん重なるので完歩数で割り、“1完歩あたり”の符号付き面積に正規化
    per = _dominant_period(ys) or _dominant_period(xs)
    cycles = max(1, round(m / per)) if per else 1
    return area / cycles / (norm_px * norm_px), m


def _sense_label(signed_area):
    """符号付き面積(体長比)から 向き と 型推定ラベルを返す。"""
    if signed_area is None:
        return None, None
    if signed_area > LOOP_SENSE_DEADBAND:
        return "反時計", "膝支点ヨーロピアン寄り"
    if signed_area < -LOOP_SENSE_DEADBAND:
        return "時計", "鐙支点アメリカン寄り"
    return "ほぼ不定", "中間/ミックス"


def _ankle_point(fr):
    """騎手の下肢先端＝足首（COCO 15/16）。無ければ膝（13/14）で代替。左右の中点。"""
    la = rc._kp(fr, "left_ankle", rc.PCUTOFF)
    ra = rc._kp(fr, "right_ankle", rc.PCUTOFF)
    m = rc._mid(la, ra) or la or ra
    if m:
        return m
    lk = rc._kp(fr, "left_knee", rc.PCUTOFF)
    rk = rc._kp(fr, "right_knee", rc.PCUTOFF)
    return rc._mid(lk, rk) or lk or rk


def leg_loop_sense(rider_frames, forward_sign=1.0, norm_px=None):
    """騎手の下肢先端（足首, 無ければ膝で代替）が矢状面に描くループの回転の向き。

    1完歩ぶんの軌跡の符号付き面積（shoelace）を体長/胴長で正規化して返す。
    符号規約: +=反時計(CCW)=膝支点ヨーロピアン寄り / −=時計(CW)=鐙支点アメリカン寄り
             （上のコメント参照。向きの相対指標であり良否ではない）。
    norm_px 未指定時は騎手胴長で正規化。
    戻り: {"signed_area", "向き", "型推定", "n"} / None。"""
    L = norm_px or _torso_len(rider_frames)
    area, n = _loop_signed_area(rider_frames, _ankle_point, forward_sign, L)
    if area is None:
        return None
    sense, kind = _sense_label(area)
    return {"signed_area": round(area, 5), "向き": sense, "型推定": kind, "n": n}


def cog_loop_sense(rider_frames, forward_sign=1.0, norm_px=None):
    """（補助）騎手“重心”の矢状面ループの回転の向き。規約は leg_loop_sense と同じ。
    戻り: {"signed_area", "向き", "型推定", "n"} / None。"""
    L = norm_px or _torso_len(rider_frames)
    area, n = _loop_signed_area(rider_frames,
                                lambda fr: rc.rider_cog(fr), forward_sign, L)
    if area is None:
        return None
    sense, kind = _sense_label(area)
    return {"signed_area": round(area, 5), "向き": sense, "型推定": kind, "n": n}


# ───────── 3. デカップリング（切り離し度） ─────────
def decoupling(A_rider_vert, A_horse):
    """A_rider_vert / A_horse。馬の鉛直バネに対し騎手がどれだけ一緒に跳ねるか。
      小（<1）＝よく浮いて切り離せている（衝撃を吸収）
      ≒1      ＝馬と一体に上下（吸収していない）
      大（>1）＝騎手が自ら余計に上下（暴れ）
    どちらか欠損、または馬が平坦でバネ≒0（定義不能）なら None。"""
    if A_rider_vert is None or A_horse is None:
        return None
    if A_horse <= 1e-9:
        return None
    return round(A_rider_vert / A_horse, 3)


# ───────── 進行方向の自動推定 ─────────
def _auto_forward(horse_frames):
    """馬フレーム列から進行方向符号(+1/-1)を推定（rider_cog.forward_sign_from_horse）。"""
    for fr in horse_frames:
        if fr and fr.get("neck_base") and (
                fr.get("nose") or fr.get("neck_end") or fr.get("tail_base")):
            return rc.forward_sign_from_horse(fr)
    return 1.0


# ───────── 4. 1ペアまとめ ─────────
def pair_metrics(horse_frames, rider_frames, forward_sign=None, fps=None):
    """1ペア（1頭＋その騎手）の指標をまとめて返す。
      forward_sign=None なら馬フレームから自動推定。
      騎手振幅の正規化は馬の体長px（decoupling を成立させるため）。
      fps を渡すと完歩頻度 freq_Hz と位相同期 sync/phase_lag も算出する。

    戻り: {"A_horse", "A_rider_vert", "A_drive", "decouple",
           "freq_Hz", "sync", "phase_lag_deg", "loop_sense",
           "forward_sign", "体長px", "馬", "騎手", "位相", "回転"}"""
    hb = horse_bounce(horse_frames)
    if forward_sign is None:
        forward_sign = _auto_forward(horse_frames)
    L = hb["体長px"] if hb else None
    rm = rider_motion(rider_frames, forward_sign=forward_sign, norm_px=L)
    A_horse = hb["振幅_体長比"] if hb else None
    A_rv = rm["A_rider_vert"] if rm else None
    A_dr = rm["A_drive"] if rm else None
    # 完歩頻度（ピッチ）と位相同期
    freq = stride_freq(horse_frames, fps) if fps else None
    hv, _ = horse_vertical_series(horse_frames)
    rv = rider_vertical_series(rider_frames)
    ps = phase_sync(hv, rv, fps) if (hv and rv) else None
    # 下肢ループの回転の向き（『逆回転』）
    ls = leg_loop_sense(rider_frames, forward_sign=forward_sign, norm_px=L)
    return {"A_horse": A_horse, "A_rider_vert": A_rv, "A_drive": A_dr,
            "decouple": decoupling(A_rv, A_horse),
            "freq_Hz": freq,
            "sync": ps["sync"] if ps else None,
            "phase_lag_deg": ps["phase_lag_deg"] if ps else None,
            "loop_sense": ls["signed_area"] if ls else None,
            "forward_sign": forward_sign, "体長px": L,
            "馬": hb, "騎手": rm, "位相": ps, "回転": ls}


# ───────── 5. 複数ペアの相関（仮説検証） ─────────
def correlate_pairs(list_of_pair_metrics):
    """複数ペアの (A_horse, A_drive) のピアソン相関係数と、A_horse昇順の一覧を返す。
    これが“馬をまたいだ”仮説検証（冒頭の設計注意を参照）。
    3ペア未満は {"判定":"判定不可(サンプル不足)", ...} を返す。

    戻り: {"判定", "n", "pearson_r", "一覧"(A_horse昇順 [(A_horse,A_drive),...]),
           "注記"?}"""
    rows = [(m.get("A_horse"), m.get("A_drive")) for m in list_of_pair_metrics
            if m.get("A_horse") is not None and m.get("A_drive") is not None]
    ordered = sorted(rows, key=lambda r: r[0])
    if len(rows) < 3:
        return {"判定": "判定不可(サンプル不足)", "n": len(rows), "pearson_r": None,
                "一覧": ordered,
                "注記": "仮説検証には“馬をまたいだ”3ペア以上が必要（1ペア内の連動は自明）"}
    r = _pearson([a for a, _ in rows], [d for _, d in rows])
    if r is None:
        judge = "判定不可(分散なし)"
    elif r >= 0.5:
        judge = "正の相関（仮説を支持：バネが大きい馬ほど騎手のアクション大）"
    elif r > 0.1:
        judge = "弱い正の相関（仮説の方向だが決め手に欠ける）"
    elif r <= -0.5:
        judge = "負の相関（仮説に反する）"
    elif r < -0.1:
        judge = "弱い負の相関（仮説に反する方向）"
    else:
        judge = "相関ほぼ無し（仮説を支持しない）"
    return {"判定": judge, "n": len(rows),
            "pearson_r": round(r, 3) if r is not None else None,
            "一覧": ordered}


# ───────── 6. レポート（テキスト／HTML） ─────────
def print_report(pairs, corr=None):
    """ペア一覧と相関のテキスト出力。"""
    print("■ 馬のバネ × 騎手のアクション")
    print("  （A_*はいずれも馬体長比のモデル推定・実測ではない）")
    for i, m in enumerate(pairs, 1):
        ah = m.get("A_horse"); av = m.get("A_rider_vert")
        ad = m.get("A_drive"); dc = m.get("decouple")
        print(f"  ペア{i}: 馬バネ A_horse={ah}  "
              f"騎手鉛直 A_rider_vert={av}  前後 A_drive={ad}  "
              f"切離し decouple={dc}")
        extra = []
        if m.get("freq_Hz") is not None:
            extra.append(f"完歩頻度={m['freq_Hz']}Hz")
        if m.get("sync") is not None:
            extra.append(f"同期={m['sync']}")
        if m.get("phase_lag_deg") is not None:
            extra.append(f"位相遅れ={m['phase_lag_deg']}°")
        rot = m.get("回転")
        if rot:
            extra.append(f"下肢ループ={m['loop_sense']}({rot['向き']}→{rot['型推定']})")
        if extra:
            print("         " + "  ".join(extra))
    if corr is None and len(pairs) >= 1:
        corr = correlate_pairs(pairs)
    if corr:
        print(f"  ── 仮説検証（馬をまたいだ A_horse↔A_drive）: {corr['判定']}"
              f"  r={corr['pearson_r']}  n={corr['n']}")
        if corr.get("注記"):
            print(f"     注記: {corr['注記']}")
        if corr.get("一覧"):
            seq = "  ".join(f"({a},{d})" for a, d in corr["一覧"])
            print(f"     A_horse昇順 (A_horse,A_drive): {seq}")


def render(pairs, corr=None):
    """簡易HTMLレポートを文字列で返す（任意）。"""
    if corr is None:
        corr = correlate_pairs(pairs)
    rows = []
    for i, m in enumerate(pairs, 1):
        rows.append(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                i, m.get("A_horse"), m.get("A_rider_vert"),
                m.get("A_drive"), m.get("decouple")))
    judge = corr.get("判定", "")
    r = corr.get("pearson_r")
    note = corr.get("注記", "")
    return (
        "<!doctype html><html lang='ja'><head><meta charset='utf-8'>"
        "<title>馬のバネ×騎手のアクション</title>"
        "<style>body{font-family:sans-serif;margin:1.5em;}"
        "table{border-collapse:collapse}td,th{border:1px solid #999;padding:4px 8px}"
        ".note{color:#666;font-size:.9em}</style></head><body>"
        "<h1>馬のバネ × 騎手のアクション</h1>"
        "<p class='note'>A_* はいずれも馬体長比のモデル推定（2D単眼ポーズ＋標準モデル）"
        "であり実測ではない。</p>"
        "<table><tr><th>ペア</th><th>A_horse<br>(馬バネ)</th>"
        "<th>A_rider_vert<br>(騎手鉛直)</th><th>A_drive<br>(前後=推進)</th>"
        "<th>decouple<br>(切離し)</th></tr>" + "".join(rows) + "</table>"
        "<h2>仮説検証（馬をまたいだ A_horse↔A_drive）</h2>"
        "<p><b>{}</b>　ピアソン r = {}　n = {}</p>".format(judge, r, corr.get("n")) +
        ("<p class='note'>{}</p>".format(note) if note else "") +
        "<p class='note'>1ペア内の連動は自明。本来の仮説検証は複数の実ペアによる"
        "馬間比較を要する。</p>"
        "</body></html>")


# ───────── selftest ─────────
def _synth_horse(bounce=40.0, n=48, period=12, x0=600, step=3):
    """合成の馬フレーム（頭=左・左へ前進）。bounce: 背の鉛直上下動の片振幅px。
    全身を同じだけ上下させ、back_middle にバネを与える。"""
    frames = []
    for i in range(n):
        p = 2 * math.pi * i / period
        x = x0 - i * step
        bob = -bounce * math.sin(p)          # 上=y小 なので符号-
        fr = {
            "neck_base": (x - 130, 200 + bob), "tail_base": (x + 130, 205 + bob),
            "nose": (x - 205, 205 + bob), "back_base": (x - 90, 198 + bob),
            "back_end": (x + 95, 205 + bob), "back_middle": (x, 196 + bob),
            "belly_bottom": (x, 272 + bob),
        }
        frames.append(fr)
    return frames


def _synth_rider(vert=15.0, drive=20.0, n=48, period=12, x0=300, step=3,
                 phase=0.0, decoh=0.0, decoh_period=5.0, loop_dir=1):
    """合成の騎手フレーム（COCO-17 dict）。左へ前進（進行方向=-x, forward_sign=-1）。
    vert: 重心の鉛直片振幅px, drive: 前後（推進）片振幅px。rider_cogは線形なので
    全点を (dx,dy) 平行移動すれば重心も同じだけ動く。
    phase: 鉛直・前後を馬に対し遅らせる位相(rad)。decoh: 別周波数の鉛直ノイズ比
           （ピッチ馬で“ぶらせない”＝波形が崩れ同期が落ちる状況を合成）。
    loop_dir: 下肢ループ循環方向(+1/-1)。鉛直の位相を反転し、矢状面ループの
              回り（符号付き面積の符号）を逆にする＝『逆回転』の合成。"""
    base = rc._synthetic_rider(lean=0.0, as_dict=True)
    frames = []
    for i in range(n):
        p = 2 * math.pi * i / period
        th = p - phase
        drift = -i * step                      # 馬とともに前進（-x）
        dx = drift + drive * math.cos(th)      # 前後の推進動作＋並進
        dy = (-vert * math.sin(loop_dir * th)  # 鉛直の浮き沈み（loop_dirで回転反転）
              + decoh * vert * math.sin(2 * math.pi * i / decoh_period + 0.7))
        frames.append({name: (xy[0] + dx, xy[1] + dy) for name, xy in base.items()})
    return frames


def selftest():
    # (a) 大バネ馬＋大アクション騎手 / (b) ほぼ平坦馬＋静かな騎手
    big = pair_metrics(_synth_horse(bounce=40.0),
                       _synth_rider(vert=15.0, drive=20.0))
    flat = pair_metrics(_synth_horse(bounce=4.0),
                        _synth_rider(vert=3.0, drive=5.0))
    print_report([big, flat])
    print()

    # 進行方向が自動で -1（頭=左）に推定される
    assert big["forward_sign"] == -1.0, f"進行方向推定が誤り: {big['forward_sign']}"

    # 馬のバネ: 大 > 平坦
    assert big["A_horse"] is not None and flat["A_horse"] is not None
    assert big["A_horse"] > flat["A_horse"], \
        f"A_horse の大小が逆: big{big['A_horse']} vs flat{flat['A_horse']}"

    # 騎手の前後アクション: 大 > 静か
    assert big["A_drive"] is not None and flat["A_drive"] is not None
    assert big["A_drive"] > flat["A_drive"], \
        f"A_drive の大小が逆: big{big['A_drive']} vs flat{flat['A_drive']}"

    # 騎手の鉛直アクションも 大 > 静か（参考）
    assert big["A_rider_vert"] > flat["A_rider_vert"]

    # decouple が両方で算出される（平坦馬も微バネありなので定義可能）
    assert big["decouple"] is not None and flat["decouple"] is not None, \
        f"decouple未算出: big{big['decouple']} flat{flat['decouple']}"
    # 真に平坦（バネ0）なら decoupling は定義不能(None)
    assert decoupling(0.1, 0.0) is None

    # ── 複数ペア（馬をまたいだ）仮説検証: バネに比例してアクションを大きく ──
    pairs = []
    for b, dr, vt in [(8, 4, 3), (20, 10, 7), (35, 18, 12), (50, 25, 16)]:
        pairs.append(pair_metrics(_synth_horse(bounce=b),
                                  _synth_rider(vert=vt, drive=dr)))
    corr = correlate_pairs(pairs)
    print(f"4ペア相関: {corr['判定']}  r={corr['pearson_r']}  n={corr['n']}")
    print(f"  A_horse昇順(A_horse,A_drive): {corr['一覧']}")
    assert corr["pearson_r"] is not None and corr["pearson_r"] > 0, \
        f"正の相関にならない: r={corr['pearson_r']}"
    assert "正の相関" in corr["判定"], f"判定文が不適切: {corr['判定']}"
    # 一覧は A_horse 昇順
    hs = [a for a, _ in corr["一覧"]]
    assert hs == sorted(hs), "一覧が A_horse 昇順でない"

    # 3ペア未満は判定不可
    few = correlate_pairs(pairs[:2])
    assert few["判定"] == "判定不可(サンプル不足)" and few["pearson_r"] is None, \
        f"サンプル不足判定が出ない: {few}"
    print(f"2ペア: {few['判定']}（n={few['n']}）")

    # render がHTMLを返す（任意機能）
    html = render(pairs, corr)
    assert html.startswith("<!doctype html>") and "A_horse" in html

    # ── 完歩頻度（ピッチ）と位相同期 ──────────────────────────────
    # 大バネ・中ピッチ馬: 騎手が同位相で乗れている→同期高・位相遅れ小
    # 高ピッチ馬: 馬の完歩が先へ進み“ぶらせない”→位相遅れ大・同期低（波形も崩れる）
    fps = 60
    mid = pair_metrics(_synth_horse(bounce=40.0, period=16),
                       _synth_rider(vert=16.0, drive=20.0, period=16, phase=0.2),
                       forward_sign=-1, fps=fps)
    pit = pair_metrics(_synth_horse(bounce=18.0, period=6),
                       _synth_rider(vert=10.0, drive=8.0, period=6, phase=2.4,
                                    decoh=0.9, decoh_period=4.3),
                       forward_sign=-1, fps=fps)
    print_report([mid, pit], corr={})
    print(f"中ピッチ大バネ: freq={mid['freq_Hz']}Hz sync={mid['sync']} "
          f"位相遅れ={mid['phase_lag_deg']}°")
    print(f"高ピッチ:       freq={pit['freq_Hz']}Hz sync={pit['sync']} "
          f"位相遅れ={pit['phase_lag_deg']}°")
    assert mid["freq_Hz"] and pit["freq_Hz"] and pit["freq_Hz"] > mid["freq_Hz"], \
        f"ピッチ馬の完歩頻度が高くない: mid{mid['freq_Hz']} pit{pit['freq_Hz']}"
    assert mid["sync"] is not None and pit["sync"] is not None, "sync未算出"
    assert mid["sync"] > pit["sync"], \
        f"高ピッチで同期が落ちていない: mid{mid['sync']} pit{pit['sync']}"
    assert abs(pit["phase_lag_deg"]) > abs(mid["phase_lag_deg"]), \
        f"高ピッチで位相遅れが大きくない: mid{mid['phase_lag_deg']} pit{pit['phase_lag_deg']}"

    # ── 『逆回転』＝下肢ループ循環方向の反転 ──────────────────────
    # loop_dir を反転した合成騎手2体で、符号付き面積の符号が逆・型推定ラベルが分かれる
    euro_fr = _synth_rider(vert=14.0, drive=18.0, loop_dir=-1)   # 反時計→ヨーロピアン
    amer_fr = _synth_rider(vert=14.0, drive=18.0, loop_dir=+1)   # 時計→アメリカン
    euro = leg_loop_sense(euro_fr, forward_sign=-1)
    amer = leg_loop_sense(amer_fr, forward_sign=-1)
    print(f"下肢ループ ヨーロ型: signed_area={euro['signed_area']} "
          f"向き={euro['向き']} → {euro['型推定']}")
    print(f"下肢ループ アメリ型: signed_area={amer['signed_area']} "
          f"向き={amer['向き']} → {amer['型推定']}")
    assert euro["signed_area"] * amer["signed_area"] < 0, \
        "下肢ループの符号が逆向きにならない"
    assert euro["型推定"] == "膝支点ヨーロピアン寄り", f"型推定が不適切: {euro['型推定']}"
    assert amer["型推定"] == "鐙支点アメリカン寄り", f"型推定が不適切: {amer['型推定']}"
    # 重心版も符号付き面積が算出される（補助）
    cg = cog_loop_sense(euro_fr, forward_sign=-1)
    assert cg is not None and cg["signed_area"] is not None, "cog_loop_sense未算出"

    print("SELFTEST PASSED（馬のバネ A_horse と騎手アクション A_drive/A_rider_vert を"
          "体長比で算出し、大バネ＋大アクションと平坦＋静かを判別／decoupleを両者で算出／"
          "馬をまたいだ複数ペアで正の相関を検出／3ペア未満は判定不可／"
          "完歩頻度stride_freqと位相同期phase_syncで高ピッチ馬の位相遅れ大・同期低を検出／"
          "leg_loop_senseで下肢ループの『逆回転』=符号反転とヨーロ/アメリカ型判定）")


def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="馬のバネ×騎手のアクション 相関解析（モデル推定）")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    else:
        ap.error("--selftest を指定（または import して各関数を使用）")


if __name__ == "__main__":
    main()
