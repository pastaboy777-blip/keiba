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
─────────────────────────────────────────────────────────────────────────

使い方:
  import rider_sync as rs
  rs.horse_bounce(horse_frames)                         # 馬の鉛直バネ（体長比）
  rs.rider_motion(rider_frames, forward_sign=-1, norm_px=L)  # 騎手の振幅
  rs.pair_metrics(horse_frames, rider_frames, forward_sign)  # 1ペアまとめ
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
def horse_bounce(horse_frames):
    """馬の鉛直バネ（1完歩あたりの上下動の振幅, 体長比）。

    back_middle（無ければ biomech.cog）の軌跡を、biomech.body_frame の前方unit
    （体軸：尾→首）に沿う並進＝進行成分を除いた“鉛直（体軸に直交）”方向へ射影し、
    その線形トレンドを除いたオシレーション振幅を体長で正規化して返す。

    戻り: {"振幅_体長比": p-p, "振幅2sd_体長比": 2×SD, "n": 点数, "体長px": 物差し}
          有効点<4 や体長不明なら None。
    ※実測ではなくモデル推定（ファイル冒頭参照）。"""
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
        return None
    # 平均前方unit → それに直交する軸＝鉛直（進行成分を除く）
    fx = sum(f[0] for f in fwds) / len(fwds)
    fy = sum(f[1] for f in fwds) / len(fwds)
    nf = math.hypot(fx, fy) or 1e-9
    fwd = (fx / nf, fy / nf)
    perp = (-fwd[1], fwd[0])            # 体軸に直交（≒鉛直）
    sig = _detrend([p[0] * perp[0] + p[1] * perp[1] for p in pts])
    L = st.median(lens) or 1.0
    pp, sd2 = _amp(sig)
    return {"振幅_体長比": round(pp / L, 4),
            "振幅2sd_体長比": round(sd2 / L, 4),
            "n": len(pts), "体長px": round(L, 1)}


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
def pair_metrics(horse_frames, rider_frames, forward_sign=None):
    """1ペア（1頭＋その騎手）の指標をまとめて返す。
      forward_sign=None なら馬フレームから自動推定。
      騎手振幅の正規化は馬の体長px（decoupling を成立させるため）。

    戻り: {"A_horse", "A_rider_vert", "A_drive", "decouple",
           "forward_sign", "体長px", "馬", "騎手"}"""
    hb = horse_bounce(horse_frames)
    if forward_sign is None:
        forward_sign = _auto_forward(horse_frames)
    L = hb["体長px"] if hb else None
    rm = rider_motion(rider_frames, forward_sign=forward_sign, norm_px=L)
    A_horse = hb["振幅_体長比"] if hb else None
    A_rv = rm["A_rider_vert"] if rm else None
    A_dr = rm["A_drive"] if rm else None
    return {"A_horse": A_horse, "A_rider_vert": A_rv, "A_drive": A_dr,
            "decouple": decoupling(A_rv, A_horse),
            "forward_sign": forward_sign, "体長px": L, "馬": hb, "騎手": rm}


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
    if corr is None and len(pairs) >= 1:
        corr = correlate_pairs(pairs)
    if corr is not None:
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


def _synth_rider(vert=15.0, drive=20.0, n=48, period=12, x0=300, step=3):
    """合成の騎手フレーム（COCO-17 dict）。左へ前進（進行方向=-x, forward_sign=-1）。
    vert: 重心の鉛直片振幅px, drive: 前後（推進）片振幅px。rider_cogは線形なので
    全点を (dx,dy) 平行移動すれば重心も同じだけ動く。"""
    base = rc._synthetic_rider(lean=0.0, as_dict=True)
    frames = []
    for i in range(n):
        p = 2 * math.pi * i / period
        drift = -i * step                      # 馬とともに前進（-x）
        dx = drift + drive * math.cos(p)       # 前後の推進動作＋並進
        dy = -vert * math.sin(p)               # 鉛直の浮き沈み
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

    print("SELFTEST PASSED（馬のバネ A_horse と騎手アクション A_drive/A_rider_vert を"
          "体長比で算出し、大バネ＋大アクションと平坦＋静かを判別／decoupleを両者で算出／"
          "馬をまたいだ複数ペアで正の相関を検出／3ペア未満は判定不可）")


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
