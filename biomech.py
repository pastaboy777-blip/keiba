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


# ───────── 体フレーム・蹄の軌跡（手順3: 胴の長さを物差しに） ─────────
def body_frame(fr):
    """重心原点・体長1の座標系 (c, f前方unit, u背側unit, L)。無ければNone。"""
    c = cog(fr)
    n, t = _get(fr, "neck_base"), _get(fr, "tail_base")
    if not (c and n and t):
        return None
    fx, fy = n[0] - t[0], n[1] - t[1]            # 前方(尾→首)
    L = math.hypot(fx, fy) or 1.0
    f = (fx / L, fy / L)
    u = (-f[1], f[0])                            # 垂直
    b = _get(fr, "belly_bottom")
    if b and ((b[0] - c[0]) * u[0] + (b[1] - c[1]) * u[1]) > 0:
        u = (-u[0], -u[1])                       # uを背側(腹と反対)に向ける
    return c, f, u, L


def to_body(p, bf):
    c, f, u, L = bf
    dx, dy = p[0] - c[0], p[1] - c[1]
    return ((dx * f[0] + dy * f[1]) / L, (dx * u[0] + dy * u[1]) / L)  # (前方, 背側)


def hoof_track(frames, bp):
    out = []
    for fr in frames:
        p, bf = _get(fr, bp), body_frame(fr)
        if p and bf:
            out.append(to_body(p, bf))
    return out


def _first_track(frames, bps):
    for bp in bps:
        t = hoof_track(frames, bp)
        if len(t) >= 4:
            return t
    return []


def trajectory_width(frames, bp_pair):
    """蹄の通り道（円弧モデル）の前後幅＝「一歩の大きさ」。体長比で返す
    （参考: 前肢1.19・後肢1.32）。併せて横÷縦の平たさも返す。"""
    t = _first_track(frames, bp_pair)
    if len(t) < 4:
        return None
    w = max(p[0] for p in t) - min(p[0] for p in t)   # 前後幅（体長比）
    h = max(p[1] for p in t) - min(p[1] for p in t)   # 上下幅（体長比）
    return {"幅_体長比": round(w, 2), "横÷縦": round(w / h, 2) if h > 1e-6 else None}


def swing_amplitude(frames, side_pair=("front_left", "front_right")):
    """前肢の振り幅: 脚ベクトル(thai→paw)の鉛直からの前後角。前へ/後ろへ/振り幅(deg)。"""
    angs = []
    for fr in frames:
        bf = body_frame(fr)
        thai = paw = None
        for s in side_pair:
            thai = thai or _get(fr, f"{s}_thai")
            paw = paw or _get(fr, f"{s}_paw")
        if bf and thai and paw:
            c, f, u, L = bf
            vx, vy = paw[0] - thai[0], paw[1] - thai[1]
            fwd = vx * f[0] + vy * f[1]
            down = -(vx * u[0] + vy * u[1])             # 脚は下へ垂れる=正
            angs.append(math.degrees(math.atan2(fwd, down)))  # 0=真下 +前 -後
    if len(angs) < 4:
        return None
    return {"前へ": round(max(angs)), "後ろへ": round(-min(angs)),
            "振り幅": round(max(angs) - min(angs))}


def dig_in_degree(frames, bp_pair):
    """かき込み度 0〜1。着地(最下点)が前方最大reachよりどれだけ後ろか。
    1=蹄を後ろへ引きながら着く(かき込み型)、0=前で突く(ステップ型)。"""
    t = _first_track(frames, bp_pair)
    if len(t) < 6:
        return None
    contact = min(t, key=lambda p: p[1])           # 最も背側マイナス=最下(接地)
    fwd = [p[0] for p in t]
    rng = max(fwd) - min(fwd)
    if rng < 1e-6:
        return None
    return round(max(0.0, min(1.0, (max(fwd) - contact[0]) / rng)), 2)


def rhythm_overlap(frames):
    """リズムの重なり 0〜1。蹄の前後位置信号を1完歩ずらした自己相関のピーク。
    1=完全に周期的(安定)。"""
    sig = []
    for fr in frames:
        bf = body_frame(fr)
        p = _get(fr, "back_left_paw") or _get(fr, "back_right_paw") \
            or _get(fr, "front_left_paw") or _get(fr, "front_right_paw")
        if bf and p:
            sig.append(to_body(p, bf)[0])
    if len(sig) < 8:
        return None
    m = sum(sig) / len(sig)
    s = [x - m for x in sig]
    den = sum(x * x for x in s) or 1e-9
    best = 0.0
    for lag in range(2, len(s) // 2):
        v = sum(s[i] * s[i - lag] for i in range(lag, len(s))) / den
        best = max(best, v)
    return round(best, 2)


def hind_reach(frames):
    """後肢の踏み込み: 後蹄がいちばん前へ出た位置を 臀端0〜肩端1 で返す
    （参考: 0.66）。"""
    vals = []
    for fr in frames:
        rear = _get(fr, "back_end") or _get(fr, "tail_base")       # 臀端
        front = (_get(fr, "front_left_thai") or _get(fr, "front_right_thai")
                 or _get(fr, "neck_base"))                         # 肩端
        paw = _get(fr, "back_left_paw") or _get(fr, "back_right_paw")
        if rear and front and paw:
            ax = (front[0] - rear[0], front[1] - rear[1])
            L2 = ax[0] ** 2 + ax[1] ** 2 or 1e-9
            t = ((paw[0] - rear[0]) * ax[0] + (paw[1] - rear[1]) * ax[1]) / L2
            vals.append(t)
    return round(max(vals), 2) if vals else None


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
    # 追加メトリクス（複数フレーム）
    res["かき込み度"] = dig_in_degree(frames, ("front_left_paw", "front_right_paw"))
    res["振り幅_前肢"] = swing_amplitude(frames, ("front_left", "front_right"))
    res["振り幅_後肢"] = swing_amplitude(frames, ("back_left", "back_right"))
    res["リズム重なり"] = rhythm_overlap(frames)
    res["軌跡幅_前肢"] = trajectory_width(frames, ("front_left_paw", "front_right_paw"))
    res["軌跡幅_後肢"] = trajectory_width(frames, ("back_left_paw", "back_right_paw"))
    res["踏み込み_臀端0肩端1"] = hind_reach(frames)
    res["関節ROM"] = joint_rom(frames)
    return res


def joint_rom(frames):
    """各関節が1完歩で動く幅（最大角−最小角, deg）。飛節・腕節の可動幅など。"""
    series = {}
    for fr in frames:
        for k, v in joint_angles(fr).items():
            series.setdefault(k, []).append(v)
    return {k: round(max(v) - min(v), 1) for k, v in series.items() if len(v) >= 2}


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
    sw = res.get("振り幅_前肢")
    if sw:
        print(f"  前肢の振り幅: {sw['振り幅']}°（前へ{sw['前へ']}°/後ろへ{sw['後ろへ']}°）")
    if res.get("かき込み度") is not None:
        print(f"  かき込み度: {res['かき込み度']}（1=後ろへ引いて着く/0=前で突く）")
    tf = res.get("軌跡幅_前肢"); tb = res.get("軌跡幅_後肢")
    if tf and tb:
        print(f"  蹄の通り道の幅(体長比): 前肢{tf['幅_体長比']}・後肢{tb['幅_体長比']}")
    if res.get("リズム重なり") is not None:
        print(f"  リズムの重なり: {res['リズム重なり']}（1=周期が安定）")
    if res.get("踏み込み_臀端0肩端1") is not None:
        print(f"  後肢の踏み込み: {res['踏み込み_臀端0肩端1']}（臀端0〜肩端1）")
    if res.get("stride"):
        print("  歩様:", "  ".join(f"{k}={v}" for k, v in res["stride"].items()))
    if res.get("load_est"):
        print("  負荷(推定1-5):", " ".join(f"{k}:{v}" for k, v in res["load_est"].items()))


# ───────── selftest ─────────
def _synthetic(dig_delta=2.2, n=36, period=12):
    """脚が振動する合成フレーム。左向き(頭=左)前進。
    dig_delta: 前肢の接地位相。大→後ろへ引いて着く(かき込み型), 小→前で突く。"""
    frames = []
    Ar, Lf = 60.0, 70.0      # 前肢 前後reach / 持ち上げ
    Ab, Lb = 55.0, 64.0      # 後肢
    for i in range(n):
        p = 2 * math.pi * i / period
        x0 = 600 - i * 2
        neck = (x0 - 130, 200); tail = (x0 + 130, 205); nose = (x0 - 205, 205)
        fr = {"neck_base": neck, "tail_base": tail, "nose": nose,
              "back_base": (x0 - 90, 198), "back_end": (x0 + 95, 205),
              "back_middle": (x0, 196), "belly_bottom": (x0, 272)}
        # 前肢(左): reach=前後, lift=接地(dig_delta)で0
        reach = Ar * math.cos(p)
        lift = Lf * (0.5 - 0.5 * math.cos(p - dig_delta))
        ft = (x0 - 70, 235)
        fp = (ft[0] - reach, 360 - lift)
        fr["front_left_thai"] = ft
        fr["front_left_paw"] = fp
        fr["front_left_knee"] = ((ft[0] + fp[0]) / 2 - 12, (ft[1] + fp[1]) / 2)
        # 後肢(左): 逆位相
        reachb = Ab * math.cos(p + math.pi)
        liftb = Lb * (0.5 - 0.5 * math.cos(p + math.pi - 0.6))
        bt = (x0 + 70, 235)
        bp_ = (bt[0] - reachb, 360 - liftb)
        fr["back_left_thai"] = bt
        fr["back_left_paw"] = bp_
        fr["back_left_knee"] = ((bt[0] + bp_[0]) / 2 + 12, (bt[1] + bp_[1]) / 2)
        frames.append(fr)
    return frames


def selftest():
    rake = analyze(_synthetic(dig_delta=2.2), fps=120)   # 後ろへ引いて着く
    stab = analyze(_synthetic(dig_delta=0.6), fps=120)   # 前で突く
    print_report(rake); print()
    assert rake["ok"] and stab["ok"]
    for need in ("頸", "腕節", "飛節", "膝"):
        assert need in rake["angles"], f"{need}角度が無い"
    assert rake.get("走法位置_時") is not None, "走法クロックが出ない"
    # かき込み度: rake(後ろ引き) > stab(前突き)
    assert rake["かき込み度"] is not None and stab["かき込み度"] is not None
    assert rake["かき込み度"] > stab["かき込み度"], \
        f"かき込み度の向きが逆: rake{rake['かき込み度']} vs stab{stab['かき込み度']}"
    assert rake["かき込み度"] >= 0.5 and stab["かき込み度"] <= 0.4, "かき込み度の域が不適切"
    # 振り幅・軌跡幅・リズム・踏み込みが算出される
    assert rake["振り幅_前肢"] and rake["振り幅_前肢"]["振り幅"] > 0
    assert rake["軌跡幅_前肢"]["幅_体長比"] > 0
    assert rake["リズム重なり"] is not None
    assert rake["踏み込み_臀端0肩端1"] is not None
    # 負荷推定 1-5・遠位>=近位
    le = rake["load_est"]
    assert le and all(1 <= v <= 5 for v in le.values())
    assert le["球節・繋"] >= le["肩・胸"], "遠位ほど高負荷のモデルが崩れている"
    print("SELFTEST PASSED（角度・走法クロック・かき込み度・振り幅・軌跡幅・"
          "リズム・踏み込み・負荷推定が算出でき、かき込み型と突き型を判別）")


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
