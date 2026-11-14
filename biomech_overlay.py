#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""バイオメカ解析オーバーレイ（手順4の見た目）  biomech_overlay.py

biomech.py の計測を、1フレームの馬の上に重ねて描く。参考画面の中心ビジュアル:
  ・骨格線（負荷1〜5で色分け: 青→赤）
  ・関節角度ラベル（頸・肩・腕節・膝・飛節）
  ・馬の重心（黄）＋重心を通る鉛直線
  ・走法クロック（12浮き/3推進/6回転/9制動＋現在位置の赤◆）
  ・円弧モデル（重心を原点にした蹄の通り道）インセット
  ・力の向き矢印・負荷の凡例・まとめ

実写では image_b64（真横フレーム）に重ねる。無ければ暗背景に骨格だけ描く。
SVGを書き出し、chromiumでPNG化できる（--png）。

使い方:
  python3 biomech_overlay.py --selftest          # 合成データで描画→HTML/PNG
  # 実パイプラインでは biomech.frames_from_h5 → render() に frames と image を渡す
"""
import math

HEAT = ["#2f6fe0", "#17a2b8", "#38b000", "#f59f00", "#e03131"]  # 負荷1→5

# 描く骨格線（利用可能なキーポイントのみ）
EDGES_SPINE = [("neck_base", "back_base"), ("back_base", "back_middle"),
               ("back_middle", "back_end"), ("back_end", "tail_base"),
               ("neck_base", "nose")]
# 肢: (親, 子, 負荷セグメント名)
EDGES_LEG = {
    "front_left": [("front_left_thai", "front_left_knee", "腕節・前腕"),
                   ("front_left_knee", "front_left_paw", "球節・繋")],
    "back_left": [("back_left_thai", "back_left_knee", "腕節・前腕"),
                  ("back_left_knee", "back_left_paw", "球節・繋")],
}
# 角度を出す関節: 表示名 → 中心キーポイント
ANGLE_AT = {"頸": "neck_base", "腕節": "front_left_knee", "飛節": "back_left_knee"}


def _heat(load):
    return HEAT[max(1, min(5, int(round(load or 1)))) - 1]


def render(frames, idx, analysis, image_b64=None, W=1000, H=620):
    import biomech
    fr = frames[idx]

    def P(bp):
        return fr.get(bp)
    s = [f'<svg viewBox="0 0 {W} {H}" width="100%" font-family="sans-serif">']
    if image_b64:
        s.append(f'<image href="data:image/webp;base64,{image_b64}" x="0" y="0" '
                 f'width="{W}" height="{H}" preserveAspectRatio="xMidYMid slice"/>')
        s.append(f'<rect width="{W}" height="{H}" fill="#000" opacity="0.18"/>')
    else:
        s.append(f'<rect width="{W}" height="{H}" fill="#0d0d0c"/>')

    load = analysis.get("load_est") or {}
    # 背骨（白太）
    for a, b in EDGES_SPINE:
        pa, pb = P(a), P(b)
        if pa and pb:
            s.append(f'<line x1="{pa[0]:.0f}" y1="{pa[1]:.0f}" x2="{pb[0]:.0f}" '
                     f'y2="{pb[1]:.0f}" stroke="#eee" stroke-width="3" opacity="0.8"/>')
    # 肢（負荷色）
    for leg, edges in EDGES_LEG.items():
        for a, b, seg in edges:
            pa, pb = P(a), P(b)
            if pa and pb:
                col = _heat(load.get(seg, load.get("球節・繋", 3)))
                s.append(f'<line x1="{pa[0]:.0f}" y1="{pa[1]:.0f}" x2="{pb[0]:.0f}" '
                         f'y2="{pb[1]:.0f}" stroke="{col}" stroke-width="7" '
                         f'stroke-linecap="round"/>')
    # 関節点＋角度ラベル
    ang = analysis.get("angles", {})
    for name, bp in ANGLE_AT.items():
        p = P(bp)
        if p and name in ang:
            s.append(f'<circle cx="{p[0]:.0f}" cy="{p[1]:.0f}" r="5" fill="#fff"/>')
            s.append(f'<rect x="{p[0]+8:.0f}" y="{p[1]-20:.0f}" width="78" height="20" '
                     f'rx="3" fill="#000b"/>'
                     f'<text x="{p[0]+12:.0f}" y="{p[1]-5:.0f}" font-size="13" '
                     f'fill="#ffd43b">{name} {ang[name]:.0f}°</text>')
    # 重心＋鉛直線
    c = biomech.cog(fr)
    if c:
        s.append(f'<line x1="{c[0]:.0f}" y1="20" x2="{c[0]:.0f}" y2="{H-120}" '
                 f'stroke="#ffd43b" stroke-width="1.5" stroke-dasharray="6 5" opacity="0.7"/>')
        s.append(f'<circle cx="{c[0]:.0f}" cy="{c[1]:.0f}" r="9" fill="#ffd43b" '
                 f'stroke="#000" stroke-width="2"/>')
        s.append(f'<text x="{c[0]+12:.0f}" y="{c[1]+4:.0f}" font-size="12" fill="#ffd43b">馬の重心</text>')
        # 力の向き矢印（走法傾向で前/後ろ）
        tend = analysis.get("走法傾向", "")
        dirx = -60 if "推進" in tend else 60 if "制動" in tend else 0
        if dirx:
            s.append(f'<line x1="{c[0]:.0f}" y1="{c[1]:.0f}" x2="{c[0]+dirx:.0f}" '
                     f'y2="{c[1]-40:.0f}" stroke="#fff" stroke-width="4"/>')
            lab = "推進(前)" if dirx < 0 else "制動(後ろ)"
            s.append(f'<text x="{c[0]+dirx-20:.0f}" y="{c[1]-46:.0f}" font-size="12" '
                     f'fill="#fff">力の向き {lab}</text>')

    # 走法クロック（右上）
    _clock_inset(s, analysis, W - 150, 90, 66)
    # 円弧モデル（左下）
    _arc_inset(s, frames, 150, H - 90, 120)
    # 負荷凡例＋まとめ（下帯）
    _legend(s, analysis, W, H)
    s.append("</svg>")
    return "".join(s)


def _clock_inset(s, analysis, cx, cy, r):
    s.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#000a" stroke="#555" stroke-width="1.5"/>')
    for hour, lab in ((12, "浮"), (3, "推"), (6, "回"), (9, "制")):
        a = math.radians((hour % 12) * 30 - 90)
        x, y = cx + (r - 12) * math.cos(a), cy + (r - 12) * math.sin(a)
        s.append(f'<text x="{x:.0f}" y="{y+4:.0f}" text-anchor="middle" font-size="11" '
                 f'fill="#aaa">{lab}</text>')
    h = analysis.get("走法位置_時")
    if h is not None:
        a = math.radians((h % 12) * 30 - 90)
        x, y = cx + (r - 28) * math.cos(a), cy + (r - 28) * math.sin(a)
        s.append(f'<path d="M{x:.0f},{y-7:.0f} L{x+7:.0f},{y:.0f} L{x:.0f},{y+7:.0f} '
                 f'L{x-7:.0f},{y:.0f} Z" fill="#e03131"/>')
        s.append(f'<text x="{cx}" y="{cy+r+16:.0f}" text-anchor="middle" font-size="12" '
                 f'fill="#fff">走法 {h}時 {analysis.get("走法傾向","")}</text>')


def _arc_inset(s, frames, cx, cy, size):
    import biomech
    s.append(f'<rect x="{cx-size:.0f}" y="{cy-size*0.6:.0f}" width="{size*2}" '
             f'height="{size*1.2:.0f}" rx="6" fill="#000a" stroke="#555"/>')
    s.append(f'<text x="{cx-size+6:.0f}" y="{cy-size*0.6+14:.0f}" font-size="10" '
             f'fill="#bbb">円弧モデル（重心が原点）</text>')
    for bps, col in ((("front_left_paw",), "#ffd43b"), (("back_left_paw",), "#4dabf7")):
        t = biomech.hoof_track(frames, bps[0])
        if len(t) < 3:
            continue
        pts = []
        for fwd, up in t:
            # 体長比→インセット座標（前方=右, 背側上=上）
            px = cx + fwd * size * 0.9
            py = cy - up * size * 0.9
            pts.append(f"{px:.0f},{py:.0f}")
        s.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{col}" '
                 f'stroke-width="2" opacity="0.9"/>')
    s.append(f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="3" fill="#fff"/>')


def _legend(s, analysis, W, H):
    y = H - 44
    s.append(f'<rect x="0" y="{y-6}" width="{W}" height="50" fill="#000c"/>')
    for i, c in enumerate(HEAT):
        s.append(f'<rect x="{14+i*26}" y="{y}" width="22" height="12" fill="{c}"/>')
        s.append(f'<text x="{20+i*26}" y="{y+22:.0f}" font-size="9" fill="#ccc">{i+1}</text>')
    s.append(f'<text x="14" y="{y-10:.0f}" font-size="10" fill="#aaa">負荷(推定1→5)</text>')
    # まとめ
    sw = analysis.get("振り幅_前肢") or {}
    tf = (analysis.get("軌跡幅_前肢") or {}).get("幅_体長比")
    parts = []
    if sw:
        parts.append(f"前肢振り{sw.get('振り幅')}°")
    if analysis.get("かき込み度") is not None:
        parts.append(f"かき込み{analysis['かき込み度']}")
    if tf is not None:
        parts.append(f"軌跡幅{tf}")
    if analysis.get("リズム重なり") is not None:
        parts.append(f"リズム{analysis['リズム重なり']}")
    s.append(f'<text x="170" y="{y+8:.0f}" font-size="12" fill="#fff">'
             f'まとめ: {" / ".join(parts)}</text>')
    s.append(f'<text x="170" y="{y+24:.0f}" font-size="9.5" fill="#999">'
             f'※重心・力・負荷はモデル推定（実測ではない）</text>')


def to_png(svg_or_html_path, png_path, W=1000, H=620):
    import glob, os, subprocess
    ch = (glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome") or [None])[0]
    if not ch:
        return None
    subprocess.run([ch, "--headless", "--no-sandbox", "--disable-gpu",
                    "--hide-scrollbars", "--force-device-scale-factor=2",
                    f"--window-size={W},{H}", f"--screenshot={png_path}",
                    f"file://{svg_or_html_path}"], capture_output=True)
    return png_path if os.path.exists(png_path) else None


def selftest():
    import biomech, tempfile, os
    frames = biomech._synthetic(dig_delta=2.2)
    analysis = biomech.analyze(frames, fps=120)
    svg = render(frames, len(frames) // 2, analysis, W=1000, H=620)
    assert svg.startswith("<svg") and "走法" in svg and "馬の重心" in svg
    assert "円弧モデル" in svg and "負荷(推定" in svg
    d = tempfile.mkdtemp()
    html = os.path.join(d, "ov.html")
    open(html, "w", encoding="utf-8").write(
        f'<!doctype html><meta charset="utf-8"><body style="margin:0">{svg}</body>')
    print(f"HTML: {html}")
    print("SELFTEST PASSED（オーバーレイSVG生成: 骨格・角度・重心・走法クロック・"
          "円弧モデル・負荷凡例・まとめを含む）")
    return html


def main():
    import argparse
    ap = argparse.ArgumentParser(description="バイオメカ解析オーバーレイ")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--png", help="PNG出力先")
    a = ap.parse_args()
    if a.selftest:
        html = selftest()
        if a.png:
            print("PNG:", to_png(html, a.png))
        return
    ap.error("--selftest を使うか、パイプラインから render() を呼んでください")


if __name__ == "__main__":
    main()
