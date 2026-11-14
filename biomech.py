#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全身バイオメカ解析エンジン（馬・MVP）  biomech.py

骨格キーポイント（DeepLabCut SuperAnimal-Quadruped → paddock_gait.extract_target_horse）
から、下記を算出する。pandas/cv2非依存のコア（frames = 各フレーム {bodypart:(x,y)} のリスト）。

【実測（＝キーポイントから計算。確実）】
  ・関節角度: 頸・肩まわり・腕節(前膝)・膝(後)・飛節
  ・馬の重心（第12〜13肋骨相当。既存cog_pointと同式）
  ・走法クロック位置: 蹄が重心を原点にどの時計位置か
       12時=浮き / 3時=推進 / 6時=接地・回転 / 9時=制動
  ・歩幅/体長比・毎秒◯完歩（回転数）・後肢踏み込み位置（体長比）・接地/空中%（暫定）

【推定（＝実測ではない。モデル仮定）】
  ・各部の負荷(1〜5)・力の向き … 2D単眼からは真の力は測れないためモデル推定。
    参考動画も「負荷メーター（モデル推定・実測ではない）」。同方式の相対ヒート。

使い方:
  import biomech; m = biomech.analyze(frames, fps=120)   # framesは単一トラック
  biomech.analyze_h5("race_uma05....h5", fps=120)         # h5から直接
  python3 biomech.py --selftest
"""
import math
import statistics as st

PCUTOFF = 0.6

# 角度を測る関節定義（左サイド優先・無ければ右）  name: (A, 中心, C)
JOINTS = {
    "頸":   ("back_base",       "neck_base",       "nose"),
    "肩":   ("back_base",       "{F}_thai",        "{F}_knee"),
    "腕節": ("{F}_thai",        "{F}_knee",        "{F}_paw"),
    "膝":   ("back_end",        "{B}_thai",        "{B}_knee"),
    "飛節": ("{B}_thai",        "{B}_knee",        "{B}_paw"),
}


# ───────── 幾何 ─────────
def _ang(a, b, c):
    """点Bでの ∠ABC（0〜180度）。"""
    bax, bay = a[0] - b[0], a[1] - b[1]
    bcx, bcy = c[0] - b[0], c[1] - b[1]
    na = math.hypot(bax, bay) or 1e-9
    nc = math.hypot(bcx, bcy) or 1e-9
    cos = max(-1.0, min(1.0, (bax * bcx + bay * bcy) / (na * nc)))
    return math.degrees(math.acos(cos))


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _get(fr, name):
    return fr.get(name)


def _side_points(fr, tmpl, side_f, side_b):
    """テンプレ {F}/{B} を左右に差し替えて3点を取得。"""
    out = []
    for p in tmpl:
        p = p.replace("{F}", side_f).replace("{B}", side_b)
        out.append(_get(fr, p))
    return out


# ───────── 重心 ─────────
def cog(fr):
    front = _get(fr, "back_base") or _get(fr, "neck_base")
    rear = _get(fr, "tail_base") or _get(fr, "back_end") or _get(fr, "back_middle")
    if not (front and rear):
        return None
    vx, vy = rear[0] - front[0], rear[1] - front[1]
    L = math.hypot(vx, vy) or 1.0
    fx, fy = front[0] + 0.52 * vx, front[1] + 0.52 * vy
    px, py = -vy, vx
    if py < 0:
        px, py = vy, -vx
    depth = 0.22 * L
    return (fx + depth * px / L, fy + depth * py / L)


def body_len(fr):
    n, t = _get(fr, "neck_base"), _get(fr, "tail_base")
    return _dist(n, t) if (n and t) else None


def travel_dir(fr):
    """進行方向の水平単位（頭が前）。neck_base→noseのx符号。"""
    n, nose = _get(fr, "neck_base"), _get(fr, "nose") or _get(fr, "neck_end")
    t = _get(fr, "tail_base")
    if n and nose:
        dx = nose[0] - n[0]
    elif n and t:
        dx = n[0] - t[0]
    else:
        dx = 1.0
    return 1.0 if dx >= 0 else -1.0


# ───────── 関節角度 ─────────
def joint_angles(fr):
    out = {}
    for name, tmpl in JOINTS.items():
        got = None
        for sf, sb in (("front_left", "back_left"), ("front_right", "back_right")):
            pts = _side_points(fr, tmpl, sf, sb)
            if all(pts):
                got = _ang(*pts)
                break
        if got is not None:
            out[name] = round(got, 1)
    return out


# ───────── 走法クロック ─────────
def clock_of(hoof, c, tdir):
    """蹄vが重心cを原点に、どの時計位置か。
    12時=真上(浮き) 3時=進行方向(推進) 6時=真下(接地) 9時=後方(制動)。
    戻り: (hour[0-12), ラベル)。"""
    vx, vy = (hoof[0] - c[0]) * tdir, hoof[1] - c[1]   # x: 前方+になるよう進行方向を掛ける
    up = -vy            # 画面上方向が+
    fwd = vx            # 前方が+
    # 12時(上)から時計回りに測る角度
    phi = math.degrees(math.atan2(fwd, up)) % 360.0
    hour = (phi / 30.0) % 12.0
    if up >= abs(fwd):
        lab = "浮き(12時)"
    elif fwd >= abs(up) and fwd > 0:
        lab = "推進(3時)"
    elif -vy <= -abs(fwd):
        lab = "接地・回転(6時)"
    else:
        lab = "制動(9時)"
    return hour, lab


def gait_clock(fr):
    """接地側の蹄（最下）で走法位置を代表。前後それぞれも返す。"""
    c = cog(fr)
    if not c:
        return None
    tdir = travel_dir(fr)
    res = {}
    hooves = {}
    for key, bps in (("前", ("front_left_paw", "front_right_paw")),
                     ("後", ("back_left_paw", "back_right_paw"))):
        p = _get(fr, bps[0]) or _get(fr, bps[1])
        if p:
            hooves[key] = p
            res[key] = clock_of(p, c, tdir)
    if not hooves:
        return None
    # 代表＝最も下にある蹄（接地に近い）
    low = max(hooves.items(), key=lambda kv: kv[1][1])
    res["代表"] = clock_of(low[1], c, tdir)
    return res


# ───────── 歩幅・回転・接地 ─────────
def stride_metrics(frames, fps):
    paws, bodylens, lows = [], [], []
    for fr in frames:
        p = _get(fr, "back_left_paw") or _get(fr, "back_right_paw") \
            or _get(fr, "front_left_paw") or _get(fr, "front_right_paw")
        if p:
            paws.append(p[0])
            lows.append(p[1])
        bl = body_len(fr)
        if bl:
            bodylens.append(bl)
    out = {}
    if len(bodylens) >= 1:
        out["体長px"] = round(st.median(bodylens), 1)
    # 完歩/秒: 蹄x座標のゼロ交差(前後往復)の頻度
    if len(paws) > 4 and fps:
        m = st.mean(paws)
        sign = [1 if x >= m else -1 for x in paws]
        crossings = sum(1 for i in range(1, len(sign)) if sign[i] != sign[i - 1])
        strides = crossings / 2.0
        secs = len(paws) / fps
        if secs > 0:
            out["完歩_毎秒"] = round(strides / secs, 2)
    # 歩幅/体長比: 蹄xの可動幅 / 体長
    if len(paws) > 2 and bodylens:
        amp = max(paws) - min(paws)
        out["歩幅_体長比"] = round(amp / st.median(bodylens), 2)
    # 接地%/空中%(暫定): 最下蹄yの上側ばらつきで近似
    if len(lows) > 4:
        g = max(lows)                       # 最も低い=地面に近い
        contact = sum(1 for y in lows if y >= g - 0.03 * (st.median(bodylens) if bodylens else 100))
        out["接地率_暫定"] = round(100 * contact / len(lows), 0)
    return out


# ───────── 負荷推定（モデル・実測ではない） ─────────
LOAD_SEGMENTS = ["肩・胸", "肘・上腕", "腕節・前腕", "屈腱・繋靭帯", "球節・繋", "蹄"]


def load_estimate(fr):
    """各部の相対負荷(1〜5)の“推定”。接地・体重を受ける側ほど、遠位ほど高い。
    ※2D単眼からの力は測れない。角度と接地状況からのヒューリスティック。"""
    c = cog(fr)
    if not c:
        return {}
    tdir = travel_dir(fr)
    # 接地前肢（最下の前蹄）を支持肢とみなす
    cand = [p for p in (_get(fr, "front_left_paw"), _get(fr, "front_right_paw")) if p]
    if not cand:
        return {}
    paw = max(cand, key=lambda p: p[1])
    hour, lab = clock_of(paw, c, tdir)
    # 支持性: 蹄が重心の真下〜後方(6〜9時)にあるほど体重を受ける＝高負荷
    weightbearing = 1.0 if paw[1] > c[1] else 0.4      # 蹄が重心より下
    brake = 1.0 if (paw[0] - c[0]) * tdir < 0 else 0.7  # 重心より後方=制動寄り
    base = 5.0 * weightbearing * brake
    # 遠位(蹄・球節)を重く、近位(肩)を軽めに配分
    weights = [0.55, 0.6, 0.7, 0.9, 1.0, 0.95]
    out = {}
    for seg, w in zip(LOAD_SEGMENTS, weights):
        out[seg] = max(1, min(5, round(base * w)))
    return out


# ───────── まとめ ─────────
def analyze(frames, fps=None):
    frames = [f for f in frames if f]
    if not frames:
        return {"ok": False, "reason": "有効フレーム無し"}
    mid = frames[len(frames) // 2]
    res = {
        "ok": True, "n_frames": len(frames),
        "angles": joint_angles(mid),
        "clock": gait_clock(mid),
        "load_est": load_estimate(mid),
        "stride": stride_metrics(frames, fps) if fps else {},
    }
    c = cog(mid)
    res["cog"] = (round(c[0], 1), round(c[1], 1)) if c else None
    # 走法の総合位置(代表)を全フレーム平均で安定化
    hours = []
    for fr in frames:
        gc = gait_clock(fr)
        if gc and "代表" in gc:
            hours.append(gc["代表"][0])
    if hours:
        # 円周平均
        s = sum(math.sin(math.radians(h * 30)) for h in hours)
        co = sum(math.cos(math.radians(h * 30)) for h in hours)
        mh = (math.degrees(math.atan2(s, co)) / 30.0) % 12.0
        res["走法位置_時"] = round(mh, 1)
        res["走法傾向"] = ("推進寄り" if 1.5 <= mh < 4.5 else
                           "接地・回転" if 4.5 <= mh < 7.5 else
                           "制動寄り" if 7.5 <= mh < 10.5 else "浮き寄り")
    return res


def frames_from_h5(h5_path, pcutoff=PCUTOFF):
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
                if x == x and y == y:
                    fr[bp] = (float(x), float(y))
        frames.append(fr)
    return frames


def analyze_h5(h5_path, fps=None, pcutoff=PCUTOFF):
    return analyze(frames_from_h5(h5_path, pcutoff), fps=fps)


def print_report(res):
    if not res.get("ok"):
        print("解析不可:", res.get("reason")); return
    print(f"■ バイオメカ解析（{res['n_frames']}フレーム）")
    print("  関節角度:", "  ".join(f"{k}{v}°" for k, v in res["angles"].items()))
    if res.get("走法位置_時") is not None:
        print(f"  走法クロック: {res['走法位置_時']}時 → {res['走法傾向']}"
              "（12浮き/3推進/6回転/9制動）")
    if res.get("stride"):
        print("  歩様:", "  ".join(f"{k}={v}" for k, v in res["stride"].items()))
    if res.get("load_est"):
        print("  負荷(推定1-5):", " ".join(f"{k}:{v}" for k, v in res["load_est"].items()))


# ───────── selftest ─────────
def _synthetic(phase="drive", n=24):
    """合成フレーム。phase='drive'(後肢が重心後方で蹴る=制動/回転寄り) or
       'float'(浮き)。左向き(頭=左, x小)で前進。"""
    frames = []
    for i in range(n):
        x0 = 500 - i * 3
        neck = (x0 - 130, 200); tail = (x0 + 130, 205); nose = (x0 - 200, 210)
        back_base = (x0 - 90, 198); back_end = (x0 + 95, 205)
        fr = {"neck_base": neck, "tail_base": tail, "nose": nose,
              "back_base": back_base, "back_end": back_end,
              "back_middle": (x0, 196)}
        fr["front_left_thai"] = (x0 - 70, 235)
        fr["front_left_knee"] = (x0 - 80, 300)
        if phase == "drive":
            # 前肢は浮き気味(接地はしていない)、後肢が重心後方・下で接地=制動/回転寄り
            fr["front_left_paw"] = (x0 - 100, 310)
            fr["back_left_thai"] = (x0 + 70, 235)
            fr["back_left_knee"] = (x0 + 95, 310)
            fr["back_left_paw"]  = (x0 + 120, 385)   # 最下=接地, 重心より後方
        else:
            # float: 全蹄が重心付近に畳まれ高い位置=浮き(12時)
            fr["front_left_paw"] = (x0 + 20, 205)
            fr["back_left_thai"] = (x0 + 60, 235)
            fr["back_left_knee"] = (x0 + 45, 280)
            fr["back_left_paw"]  = (x0 + 30, 200)
        frames.append(fr)
    return frames


def selftest():
    drive = analyze(_synthetic("drive"), fps=120)
    float_ = analyze(_synthetic("float"), fps=120)
    print_report(drive); print()
    print_report(float_); print()
    assert drive["ok"] and float_["ok"]
    assert drive["angles"], "関節角度が出ていない"
    for need in ("頸", "腕節", "飛節"):
        assert need in drive["angles"], f"{need}角度が無い"
    # driveは後蹄が重心後方・下→制動/回転寄り(6〜9時)、floatは浮き寄り(12時付近)
    assert drive.get("走法位置_時") is not None
    hd = drive["走法位置_時"]; hf = float_["走法位置_時"]
    assert 4.5 <= hd <= 10.5, f"drive走法位置が想定外: {hd}時"
    assert (hf <= 2.0 or hf >= 10.0), f"float走法位置が想定外: {hf}時"
    # 負荷推定が1-5で出る
    le = drive["load_est"]
    assert le and all(1 <= v <= 5 for v in le.values())
    assert le["球節・繋"] >= le["肩・胸"], "遠位ほど高負荷のモデルが崩れている"
    print("SELFTEST PASSED（関節角度・走法クロック・負荷推定・歩様が算出でき、"
          "drive(制動寄り)とfloat(浮き)を判別）")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="全身バイオメカ解析（馬MVP）")
    ap.add_argument("--h5", help="DeepLabCut h5")
    ap.add_argument("--fps", type=float)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest(); return
    if not a.h5:
        ap.error("--h5 か --selftest を指定")
    print_report(analyze_h5(a.h5, fps=a.fps))


if __name__ == "__main__":
    main()
