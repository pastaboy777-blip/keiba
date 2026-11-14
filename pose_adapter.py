#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ViTPose+（AP-10K・馬17点）→ biomech キーポイント名 への変換  pose_adapter.py

参考資料は ViTPose+（AP-10K 17点）で姿勢推定している。biomech.py は
DeepLabCut系の名前（neck_base, back_base, front_left_thai …）で書かれているので、
両者を橋渡しするマッピング層。中間の背点(back_base/back_middle)や腹点(belly_bottom)は
17点に無いので、首〜尾と四肢から幾何的に合成する。

AP-10K 17点の標準並び（index: 名前）:
  0 左目 1 右目 2 鼻 3 首 4 尾根 5 左肩 6 左肘 7 左前蹄
  8 右肩 9 右肘 10 右前蹄 11 左股 12 左膝 13 左後蹄 14 右股 15 右膝 16 右後蹄

使い方:
  frame = ap10k_to_biomech(kps)      # kps: [(x,y,conf), ...] len17
  frames = [ap10k_to_biomech(k) for k in per_frame_kps]
  res = biomech.analyze(frames, fps=...)
"""
AP10K = ["left_eye", "right_eye", "nose", "neck", "root_of_tail",
         "left_shoulder", "left_elbow", "left_front_paw",
         "right_shoulder", "right_elbow", "right_front_paw",
         "left_hip", "left_knee", "left_back_paw",
         "right_hip", "right_knee", "right_back_paw"]
IDX = {n: i for i, n in enumerate(AP10K)}

# AP-10K名 → biomech名（直接対応ぶん）
DIRECT = {
    "nose": "nose", "neck": "neck_base", "root_of_tail": "tail_base",
    "left_shoulder": "front_left_thai", "left_elbow": "front_left_knee",
    "left_front_paw": "front_left_paw",
    "right_shoulder": "front_right_thai", "right_elbow": "front_right_knee",
    "right_front_paw": "front_right_paw",
    "left_hip": "back_left_thai", "left_knee": "back_left_knee",
    "left_back_paw": "back_left_paw",
    "right_hip": "back_right_thai", "right_knee": "back_right_knee",
    "right_back_paw": "back_right_paw",
}


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def ap10k_to_biomech(kps, pcutoff=0.3):
    """kps: 長さ17の [(x,y,conf), ...]（または [(x,y), ...]）。
    戻り: biomechが使う {name:(x,y)} のフレーム辞書。信頼度不足は除外。"""
    def g(name):
        i = IDX[name]
        if i >= len(kps):
            return None
        p = kps[i]
        if len(p) >= 3 and p[2] < pcutoff:
            return None
        x, y = p[0], p[1]
        if x != x or y != y:
            return None
        return (float(x), float(y))

    fr = {}
    for apn, bmn in DIRECT.items():
        p = g(apn)
        if p:
            fr[bmn] = p

    neck, tail = fr.get("neck_base"), fr.get("tail_base")
    if neck and tail:
        # 背線上の中間点を合成（17点に無い）
        fr.setdefault("back_base", _lerp(neck, tail, 0.15))
        fr["back_middle"] = _lerp(neck, tail, 0.5)
        fr.setdefault("back_end", _lerp(neck, tail, 0.85))
        # 腹点 belly_bottom: 背線中点から、蹄側(腹方向)へ体長の約28%下ろす
        hooves = [fr[k] for k in ("front_left_paw", "front_right_paw",
                                  "back_left_paw", "back_right_paw") if k in fr]
        bm = fr["back_middle"]
        if hooves:
            mh = (sum(h[0] for h in hooves) / len(hooves),
                  sum(h[1] for h in hooves) / len(hooves))
            L = ((tail[0] - neck[0]) ** 2 + (tail[1] - neck[1]) ** 2) ** 0.5 or 1.0
            vx, vy = mh[0] - bm[0], mh[1] - bm[1]
            vlen = (vx * vx + vy * vy) ** 0.5 or 1.0
            fr["belly_bottom"] = (bm[0] + 0.28 * L * vx / vlen,
                                  bm[1] + 0.28 * L * vy / vlen)
    return fr


def selftest():
    import math
    import biomech
    # 合成の17点フレーム列（左向き・頭=左、前肢が振動）を作って変換→解析
    frames = []
    for i in range(30):
        p = 2 * math.pi * i / 12
        x0 = 600 - i * 2
        reach = 60 * math.cos(p)
        lift = 70 * (0.5 - 0.5 * math.cos(p - 2.2))
        kps = [None] * 17
        def put(n, xy): kps[IDX[n]] = (xy[0], xy[1], 0.9)
        put("nose", (x0 - 205, 205)); put("neck", (x0 - 130, 200))
        put("root_of_tail", (x0 + 130, 205))
        put("left_shoulder", (x0 - 70, 235)); put("left_elbow", (x0 - 80, 300))
        put("left_front_paw", (x0 - 70 - reach, 360 - lift))
        put("right_shoulder", (x0 - 66, 238)); put("right_elbow", (x0 - 76, 302))
        put("right_front_paw", (x0 - 66 - reach, 362 - lift))
        put("left_hip", (x0 + 70, 235)); put("left_knee", (x0 + 80, 300))
        put("left_back_paw", (x0 + 70 - 55 * math.cos(p + math.pi), 360))
        put("right_hip", (x0 + 66, 238)); put("right_knee", (x0 + 76, 302))
        put("right_back_paw", (x0 + 66 - 55 * math.cos(p + math.pi), 362))
        frames.append(ap10k_to_biomech(kps))
    # 合成した背点・腹点が入っているか
    f0 = frames[0]
    for need in ("neck_base", "tail_base", "back_base", "back_middle",
                 "back_end", "belly_bottom", "front_left_thai", "back_left_knee"):
        assert need in f0, f"変換で {need} が欠落"
    # biomechが解析でき、主要メトリクスが出る
    res = biomech.analyze(frames, fps=120)
    assert res["ok"], "変換フレームをbiomechが解析できない"
    assert res["angles"] and res.get("走法位置_時") is not None
    assert res["かき込み度"] is not None and res["振り幅_前肢"]
    print("変換例:", {k: (round(v[0]), round(v[1])) for k, v in list(f0.items())[:5]})
    print("解析OK: 走法", res["走法位置_時"], "時 / かき込み", res["かき込み度"],
          "/ 前肢振り幅", res["振り幅_前肢"]["振り幅"], "°")
    print("SELFTEST PASSED（AP-10K 17点→biomech名の変換、背点/腹点の合成、"
          "biomech解析まで通る）")


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        selftest()
    else:
        print("使い方: python3 pose_adapter.py --selftest")
