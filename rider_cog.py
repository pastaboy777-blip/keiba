#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""騎手の重心 ＆ 人馬合成重心（モデル推定）  rider_cog.py

人体ポーズ（COCO-17）のキーポイントから、de Leva(1996) の体節質量比を使って
騎手（人）の全身重心を質量加重平均で推定する。さらに馬の重心（biomech.cog 等）と
体重比で合成し、人馬合成重心・人の重心のずれ（前後, 胴長比%）を出す。

【重要・モデル推定である旨の明記】
  ここで出す「人の重心」「人馬合成重心」は、2D単眼ポーズ＋人体標準モデル
  （de Leva 1996 の体節質量比・体節重心位置）からの“推定”であって、実測ではない。
  個人差（体格・馬具・鞍上姿勢）は反映しない相対的な目安。biomech.py の負荷推定と同様、
  モデル仮定に基づく参考値として扱うこと。

【de Leva(1996) 出典】
  de Leva P. (1996) "Adjustments to Zatsiorsky-Seluyanov's segment inertia
  parameters." Journal of Biomechanics 29(9): 1223-1230.
  体節質量比（全体質量に対する%, 男性値 Table 4）:
     頭部   6.94 / 体幹 43.46 / 上腕 2.71 / 前腕 1.62 / 手 0.61 /
     大腿 14.16 / 下腿 4.33 / 足 1.37
  本モジュールは課題仕様に合わせて以下に束ねる（片側ぶんの値）:
     頭部頸部 6.94% / 体幹 43.46% / 上腕 2.71% /
     前腕+手 2.23%(=1.62+0.61) / 大腿 14.16% / 下腿+足 5.70%(=4.33+1.37)
     → 頭+体幹+2×(上腕+前腕手+大腿+下腿足) = 100.0%
  体節重心位置（近位端からの比, 男性値 近似）:
     上腕 0.577 / 前腕 0.457 / 大腿 0.410 / 下腿 0.446（de Leva）
  ※「前腕+手」「下腿+足」は de Leva では別体節なので、合成体節の重心比
     （0.68 / 0.58）は遠位側に寄せた近似。頭部頸部は 0.50 近似、体幹は 0.44 近似。

使い方:
  import rider_cog as rc
  rc.rider_cog(kps)                         # kps: COCO-17 [(x,y,conf),...] か {name:(x,y)}
  rc.combined_cog(horse_cog, rider_cog)     # 人馬合成重心
  rc.cog_offset_pct(horse_cog, rider_cog, body_len_px, forward_sign=+1)
  python3 rider_cog.py --selftest
"""
import math

PCUTOFF = 0.3

# COCO-17 標準並び（index: 名前）。dict入力時のキー名もこれに準拠。
COCO = ["nose", "left_eye", "right_eye", "left_ear", "right_ear",
        "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
        "left_wrist", "right_wrist", "left_hip", "right_hip",
        "left_knee", "right_knee", "left_ankle", "right_ankle"]
IDX = {n: i for i, n in enumerate(COCO)}

# ───────── 体節定義（de Leva 1996） ─────────
# (体節名, 近位端spec, 遠位端spec, 質量比(全体=1.0), 近位端からの重心比)
#   specは COCO名 か 合成点トークン（_point参照）。
#   質量比は de Leva(1996) Table4 男性値（下記docstring参照）。
SEGMENTS = [
    ("頭部頸部",  "head",          "shoulder_mid", 0.0694, 0.50),   # 頭6.94%
    ("体幹",      "shoulder_mid",  "hip_mid",      0.4346, 0.44),   # 体幹43.46%
    ("上腕_左",   "left_shoulder", "left_elbow",   0.0271, 0.577),  # 上腕2.71%
    ("上腕_右",   "right_shoulder","right_elbow",  0.0271, 0.577),
    ("前腕手_左", "left_elbow",    "left_wrist",   0.0223, 0.68),   # 前腕1.62+手0.61
    ("前腕手_右", "right_elbow",   "right_wrist",  0.0223, 0.68),
    ("大腿_左",   "left_hip",      "left_knee",    0.1416, 0.41),   # 大腿14.16%
    ("大腿_右",   "right_hip",     "right_knee",   0.1416, 0.41),
    ("下腿足_左", "left_knee",     "left_ankle",   0.0570, 0.58),   # 下腿4.33+足1.37
    ("下腿足_右", "right_knee",    "right_ankle",  0.0570, 0.58),
]


# ───────── キーポイント取得 ─────────
def _kp(kps, name, pcutoff):
    """COCO-17 の1点を (x,y) で返す。信頼度不足・欠損・NaNはNone。
    kps は [(x,y,conf),...] / [(x,y),...] / {name:(x,y[,conf])} のいずれでも可。"""
    if isinstance(kps, dict):
        p = kps.get(name)
    else:
        i = IDX.get(name)
        if i is None or i >= len(kps):
            return None
        p = kps[i]
    if not p:
        return None
    if len(p) >= 3 and p[2] is not None and p[2] < pcutoff:
        return None
    x, y = p[0], p[1]
    if x != x or y != y:          # NaN除外
        return None
    return (float(x), float(y))


def _mid(a, b):
    if not (a and b):
        return None
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def _point(kps, spec, pcutoff):
    """体節端点のspecを実座標へ解決。合成点（左右中点・頭）も扱う。"""
    if spec == "shoulder_mid":
        return _mid(_kp(kps, "left_shoulder", pcutoff),
                    _kp(kps, "right_shoulder", pcutoff))
    if spec == "hip_mid":
        return _mid(_kp(kps, "left_hip", pcutoff),
                    _kp(kps, "right_hip", pcutoff))
    if spec == "head":
        # 耳の中点を優先、無ければ鼻
        m = _mid(_kp(kps, "left_ear", pcutoff), _kp(kps, "right_ear", pcutoff))
        return m or _kp(kps, "nose", pcutoff)
    return _kp(kps, spec, pcutoff)


# ───────── 騎手（人）の重心 ─────────
def rider_cog(kps, pcutoff=PCUTOFF):
    """de Leva(1996) の体節質量比で人の全身重心(x,y)を質量加重平均で推定。
    各体節の重心 = 近位端 + 比×(遠位端−近位端)。端点が欠けた体節は除外し、
    残った体節の質量で再正規化する。有効体節が無ければ None。
    ※実測ではなくモデル推定（ファイル冒頭参照）。"""
    sx = sy = m_sum = 0.0
    for _name, prox, dist, mass, ratio in SEGMENTS:
        a = _point(kps, prox, pcutoff)
        b = _point(kps, dist, pcutoff)
        if not (a and b):
            continue                      # 端点欠け体節は除外
        cx = a[0] + ratio * (b[0] - a[0])
        cy = a[1] + ratio * (b[1] - a[1])
        sx += mass * cx
        sy += mass * cy
        m_sum += mass
    if m_sum <= 0:
        return None
    return (sx / m_sum, sy / m_sum)       # 残体節の質量で再正規化


# ───────── 人馬合成重心 ─────────
def combined_cog(horse_cog, rider_cog, horse_kg=500, rider_kg=55):
    """馬重心と人重心を体重比で加重した人馬合成重心(x,y)。
    馬が圧倒的に重いので合成重心は馬重心寄りに来る。どちらか欠ければ他方を返す。"""
    if not horse_cog:
        return rider_cog
    if not rider_cog:
        return horse_cog
    tot = horse_kg + rider_kg
    if tot <= 0:
        return None
    return ((horse_cog[0] * horse_kg + rider_cog[0] * rider_kg) / tot,
            (horse_cog[1] * horse_kg + rider_cog[1] * rider_kg) / tot)


# ───────── 進行方向（馬キーポイントから） ─────────
def forward_sign_from_horse(fr):
    """馬フレーム {name:(x,y)} から進行方向の水平符号(+1/-1)を推定。
    頭が前。biomech.travel_dir と同趣旨（nose/neck_base→tail_base のx符号）。"""
    n = fr.get("neck_base")
    nose = fr.get("nose") or fr.get("neck_end")
    t = fr.get("tail_base")
    if n and nose:
        dx = nose[0] - n[0]
    elif n and t:
        dx = n[0] - t[0]
    else:
        return 1.0
    return 1.0 if dx >= 0 else -1.0


def cog_offset_pct(horse_cog, rider_cog, body_len_px,
                   forward_sign=1.0, horse_frame=None):
    """人の重心が馬の重心より前(＋)か後ろ(−)かを、胴長比(%)で返す。
    （参考画面「人の重心のずれ 前へ9%」に相当＝＋9.0）
    進行方向は forward_sign（進行方向が画面+xなら+1, -xなら-1）で与えるか、
    horse_frame（馬の{name:(x,y)}）を渡せば自動推定する。
    body_len_px は馬の胴長(px)。算出不能なら None。"""
    if not (horse_cog and rider_cog) or not body_len_px:
        return None
    if horse_frame is not None:
        forward_sign = forward_sign_from_horse(horse_frame)
    fwd = (rider_cog[0] - horse_cog[0]) * forward_sign   # 進行方向成分
    return round(100.0 * fwd / body_len_px, 1)


# ───────── selftest ─────────
def _synthetic_rider(lean=0.0, hx=300.0, as_dict=False):
    """合成の人体17点（側面・頭=左右中央, 前=+x）。
    lean: 上半身（頭・肩・肘・手首）を前方(+x)へずらす量px。0=直立, 大=前傾騎乗。
    画像座標（yは下向き＝下ほど大）。"""
    pts = {
        "nose":           (hx + lean, 90),
        "left_eye":       (hx + lean - 3, 88),  "right_eye": (hx + lean + 3, 88),
        "left_ear":       (hx + lean - 5, 95),  "right_ear": (hx + lean + 5, 95),
        "left_shoulder":  (hx + lean - 8, 130), "right_shoulder": (hx + lean + 8, 130),
        "left_elbow":     (hx + lean + 7, 160), "right_elbow": (hx + lean + 23, 160),
        "left_wrist":     (hx + lean + 22, 180),"right_wrist": (hx + lean + 38, 180),
        "left_hip":       (hx - 8, 200),        "right_hip": (hx + 8, 200),
        "left_knee":      (hx + 22, 230),       "right_knee": (hx + 38, 230),
        "left_ankle":     (hx + 2, 270),        "right_ankle": (hx + 18, 270),
    }
    if as_dict:
        return pts
    kps = [None] * 17
    for n, xy in pts.items():
        kps[IDX[n]] = (xy[0], xy[1], 0.9)
    return kps


def selftest():
    # 1) 直立姿勢: rider_cog が体幹寄り（肩〜股の縦範囲内）に出る
    up = _synthetic_rider(lean=0.0)
    rc_up = rider_cog(up)
    assert rc_up is not None, "rider_cog が算出できない"
    sh_y = (up[IDX["left_shoulder"]][1] + up[IDX["right_shoulder"]][1]) / 2  # 130
    hip_y = (up[IDX["left_hip"]][1] + up[IDX["right_hip"]][1]) / 2           # 200
    print("直立   人重心:", (round(rc_up[0], 1), round(rc_up[1], 1)),
          f"（肩y={sh_y:.0f}, 股y={hip_y:.0f}）")
    assert sh_y < rc_up[1] < hip_y, \
        f"人重心が体幹範囲外: y={rc_up[1]:.1f}（肩{sh_y}〜股{hip_y}の間に無い）"

    # dict入力でも同じ結果になる（入力形の両対応チェック）
    rc_up_d = rider_cog(_synthetic_rider(lean=0.0, as_dict=True))
    assert abs(rc_up_d[0] - rc_up[0]) < 1e-6 and abs(rc_up_d[1] - rc_up[1]) < 1e-6, \
        "dict入力とlist入力で結果が食い違う"

    # 欠損体節の除外・再正規化が落ちない（両腕を欠落させても算出できる）
    broken = list(up)
    for n in ("left_elbow", "right_elbow", "left_wrist", "right_wrist"):
        broken[IDX[n]] = (0.0, 0.0, 0.0)   # conf=0 → 除外
    assert rider_cog(broken) is not None, "体節欠損時に重心が出ない"

    # 2) 前傾させると cog_offset_pct が前(＋)へ動く
    lean = _synthetic_rider(lean=40.0)
    rc_lean = rider_cog(lean)
    horse_cog = (rc_up[0], 350.0)          # 直立人重心の真下あたりに馬重心
    body_len = 300.0                       # 馬胴長px
    off_up = cog_offset_pct(horse_cog, rc_up, body_len, forward_sign=+1)
    off_lean = cog_offset_pct(horse_cog, rc_lean, body_len, forward_sign=+1)
    print(f"直立   ずれ: {off_up:+.1f}%   前傾 ずれ: {off_lean:+.1f}%（＋=前へ）")
    assert off_lean > off_up, f"前傾でずれが前に動かない: {off_up}→{off_lean}"
    assert off_lean > 0, f"前傾なのに前(＋)にならない: {off_lean}"

    # 進行方向を逆(-x)にすると符号が反転する
    off_lean_rev = cog_offset_pct(horse_cog, rc_lean, body_len, forward_sign=-1)
    assert off_lean_rev < 0 and abs(off_lean_rev) == abs(off_lean), \
        "進行方向を逆にしても符号が反転しない"

    # 馬キーポイントから進行方向を渡す形（頭=左→前は-x）も動く
    horse_fr = {"neck_base": (200, 300), "nose": (120, 305), "tail_base": (330, 305)}
    assert forward_sign_from_horse(horse_fr) == -1.0
    off_fr = cog_offset_pct(horse_cog, rc_lean, body_len, horse_frame=horse_fr)
    assert off_fr < 0, "馬フレーム経由の進行方向推定が効いていない"

    # 3) combined_cog は体重比で馬重心寄りに来る
    cc = combined_cog(horse_cog, rc_up, horse_kg=500, rider_kg=55)
    print("人馬合成重心:", (round(cc[0], 1), round(cc[1], 1)),
          f"（馬y={horse_cog[1]:.0f}, 人y={rc_up[1]:.1f}）")
    d_horse = abs(cc[1] - horse_cog[1])
    d_rider = abs(cc[1] - rc_up[1])
    assert d_horse < d_rider, "合成重心が馬重心寄りに来ていない"
    # 体重比どおりか（人側に rider_kg/総重量 だけ寄る）
    expect_y = (horse_cog[1] * 500 + rc_up[1] * 55) / 555.0
    assert abs(cc[1] - expect_y) < 1e-6, "合成重心が体重比の加重平均と一致しない"

    print("SELFTEST PASSED（de Leva体節質量比で人重心が体幹寄りに出る／前傾で"
          "重心ずれが前(＋)へ動く／合成重心が体重比で馬重心寄りに来る）")


def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="騎手重心＆人馬合成重心（de Leva 1996・モデル推定）")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    else:
        ap.error("--selftest を指定（または import して各関数を使用）")


if __name__ == "__main__":
    main()
