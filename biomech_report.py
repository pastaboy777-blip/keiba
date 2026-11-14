#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""バイオメカ報告「この馬の位置」比較チャート  biomech_report.py

biomech.analyze() の結果から、参考スライド『この馬の位置を図で示す』と同じ
横軸ドットプロットのレポートHTMLを生成する。
  ・赤いひし形＝この馬の値
  ・灰色の点＝これまでに解析した馬の分布（0頭なら位置づけは未確定）
  ・各行に根拠 A/B/C（A=成績と直接比べた研究, B=間接, C=成績との研究なし）
  ・並び順＝競走成績への重要順（上ほど根拠が強い）
  ・「良い/悪い」の判定ではなく“位置”を見る図。区切り(軸範囲)は暫定。

出典: 体節質量比 Buchner 1997 / de Leva 1996、歩幅・回転と成績 Morrice-West 2021 /
      Barrey 2001 / Schrurs 2022、円弧モデル・かき込み型 小林寛道（東大名誉教授）。

使い方:
  python3 biomech_report.py --h5 race_uma05...h5 --fps 120 --name メイショウアキカゼ -o report.html
  python3 biomech_report.py --selftest
"""
import argparse
import html

# 行定義: (ラベル, 根拠, 軸lo, 軸hi, 単位, res→値 の取り出し)
#   並び順＝競走成績への重要順。軸範囲は暫定。
ROWS = [
    ("歩幅（胴の長さ比）", "A", 3.69, 4.29, "倍",
     lambda r: (r.get("stride") or {}).get("歩幅_体長比")),
    ("リズムの重なり", "A", 0.93, 1.05, "",
     lambda r: r.get("リズム重なり")),
    ("軌跡の幅（胴の長さ比）", "B", 1.16, 1.34, "",
     lambda r: (r.get("軌跡幅_前肢") or {}).get("幅_体長比")),
    ("腰の振り幅", "B", 65, 79, "°",
     lambda r: (r.get("振り幅_後肢") or {}).get("振り幅")),
    ("前肢の振り幅", "B", 69, 83, "°",
     lambda r: (r.get("振り幅_前肢") or {}).get("振り幅")),
    ("人の重心のずれ（前が＋）", "B", 3, 15, "%",
     lambda r: r.get("人重心ずれ")),            # phase2（人体ポーズ）→ None
    ("飛節の動く幅", "C", 57, 71, "°",
     lambda r: (r.get("関節ROM") or {}).get("飛節")),
    ("腕節の動く幅", "C", 82, 96, "°",
     lambda r: (r.get("関節ROM") or {}).get("腕節")),
]

GRADE_COLOR = {"A": "#2f9e44", "B": "#e8842a", "C": "#868e96"}


def _fmt(v, unit):
    if v is None:
        return "—"
    s = f"{v:+.0f}" if unit == "%" else (f"{v:.2f}" if abs(v) < 10 else f"{v:.0f}")
    return s + unit


def _axis_svg(v, lo, hi, priors):
    """1行ぶんの横軸SVG。赤ひし形＝この馬、灰点＝これまでの馬。"""
    W, H = 460, 44
    x0, x1, y = 70, W - 70, 22
    out = [f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           f'font-family="sans-serif">']
    out.append(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="#ced4da" stroke-width="2"/>')
    out.append(f'<text x="{x0-6}" y="{y+4}" text-anchor="end" font-size="10" fill="#868e96">{lo:g}</text>')
    out.append(f'<text x="{x1+6}" y="{y+4}" font-size="10" fill="#868e96">{hi:g}</text>')

    def X(val):
        t = 0.0 if hi == lo else (val - lo) / (hi - lo)
        return x0 + max(0.0, min(1.0, t)) * (x1 - x0)
    for p in (priors or []):
        out.append(f'<circle cx="{X(p):.1f}" cy="{y}" r="4" fill="#adb5bd" opacity="0.7"/>')
    if v is not None:
        cx = X(v)
        out.append(f'<path d="M{cx:.1f},{y-8} L{cx+8:.1f},{y} L{cx:.1f},{y+8} '
                   f'L{cx-8:.1f},{y} Z" fill="#e03131" stroke="#fff" stroke-width="1.5"/>')
    else:
        out.append(f'<text x="{(x0+x1)/2:.0f}" y="{y+4}" text-anchor="middle" '
                   f'font-size="10" fill="#adb5bd">測定なし</text>')
    out.append("</svg>")
    return "".join(out)


def render(res, name="この馬", date="", gait="駈歩・襲歩", priors=None):
    priors = priors or {}
    n_prior = max((len(v) for v in priors.values()), default=0)
    rows_html = []
    for label, grade, lo, hi, unit, getter in ROWS:
        v = getter(res) if res else None
        gc = GRADE_COLOR[grade]
        rows_html.append(
            '<div class="row">'
            f'<div class="lab"><div class="nm">{html.escape(label)}</div>'
            f'<div class="gr" style="color:{gc}">根拠{grade}'
            f'{"：成績と直接比べた研究あり" if grade=="A" else "：間接の研究" if grade=="B" else "：成績との研究なし"}</div></div>'
            f'<div class="ax">{_axis_svg(v, lo, hi, priors.get(label))}</div>'
            f'<div class="val" style="color:{"#e03131" if v is not None else "#adb5bd"}">{_fmt(v, unit)}</div>'
            '</div>')
    undet = ("<b>比べた馬はまだ0頭です。</b>位置の良し悪しはまだ言えません。"
             if n_prior < 3 else f"比べた馬 {n_prior}頭。")
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(name)} この馬の位置</title><style>
 body{{margin:0;background:#f4f5f7;color:#1b2733;font-family:system-ui,
   -apple-system,"Hiragino Kaku Gothic ProN",sans-serif}}
 .wrap{{max-width:980px;margin:0 auto;background:#fff}}
 .hd{{background:#17345c;color:#fff;padding:14px 20px;display:flex;
   justify-content:space-between;align-items:baseline}}
 .hd .t{{font-size:17px;font-weight:700}} .hd .m{{font-size:12px;opacity:.85}}
 .leg{{display:flex;gap:16px;padding:8px 20px;font-size:11px;color:#495057;
   border-bottom:1px solid #e9ecef;flex-wrap:wrap}}
 .leg b{{color:#e03131}}
 .row{{display:grid;grid-template-columns:230px 460px 1fr;align-items:center;
   padding:4px 20px;border-bottom:1px solid #f1f3f5}}
 .row:nth-child(even){{background:#fafbfc}}
 .lab .nm{{font-size:14px;font-weight:600}} .lab .gr{{font-size:10.5px}}
 .val{{font-size:17px;font-weight:700;text-align:right}}
 .note{{padding:12px 20px;font-size:11.5px;color:#495057;line-height:1.7}}
 .note .warn{{color:#e03131;font-weight:600}}
 .src{{padding:4px 20px 18px;font-size:10.5px;color:#868e96;line-height:1.7}}
</style></head><body><div class="wrap">
<div class="hd"><div class="t">{html.escape(name)}　比較：この馬の位置（同じ歩法の馬と、研究の値）</div>
<div class="m">{html.escape(date)}　{html.escape(gait)}</div></div>
<div class="leg"><span>◆ <b>この馬</b></span>
<span>● これまでに解析した馬（{n_prior}頭）</span>
<span>並び順＝競走成績への重要順（上ほど根拠が強い）</span></div>
{"".join(rows_html)}
<div class="note"><span class="warn">{undet}</span>
　同じ条件の馬が増えるほど、灰色の点で分布が出て位置づけが確かになります。
これは“位置”を見る図で、良い・悪いの判定ではありません。関節角度は測り方が研究と
違うため、研究の値は重ねていません。区切り（軸範囲）は暫定です。</div>
<div class="src">根拠 A＝成績と直接比べた研究あり／B＝間接の研究／C＝成績との研究なし。
研究の値（毎秒の完歩数）：レース2.36±0.12回（日本921頭・Takahashi 2025）、
秒速9.5〜12.5mで2.01〜2.16回（Parsons 2008・Ferrari 2009）。
出典：体節質量比 Buchner 1997／de Leva 1996、歩幅・回転と成績 Morrice-West 2021／
Barrey 2001／Schrurs 2022、円弧モデル・かき込み型 小林寛道（東京大学名誉教授）。
重心・力・負荷はモデル推定で実測ではありません。</div>
</div></body></html>"""


def build(res, out, **kw):
    doc = render(res, **kw)
    with open(out, "w", encoding="utf-8") as f:
        f.write(doc)
    return out


def selftest():
    import biomech
    res = biomech.analyze(biomech._synthetic(dig_delta=2.2), fps=120)
    out = "/tmp/biomech_report_selftest.html"
    build(res, out, name="合成テスト号", date="2026-11-14")
    doc = open(out, encoding="utf-8").read()
    for need in ("この馬の位置", "歩幅（胴の長さ比）", "根拠A", "比べた馬はまだ0頭",
                 "e03131", "飛節の動く幅", "小林寛道"):
        assert need in doc, f"レポートに {need} が無い"
    # 行数 = ROWS 数
    assert doc.count('class="row"') == len(ROWS), "行数が合わない"
    print(f"保存: {out}")
    print("SELFTEST PASSED（この馬の位置レポートを生成・8行・赤マーカー・根拠・"
          "0頭注記・出典を含む）")


def main():
    ap = argparse.ArgumentParser(description="バイオメカ報告『この馬の位置』")
    ap.add_argument("--h5")
    ap.add_argument("--fps", type=float)
    ap.add_argument("--name", default="この馬")
    ap.add_argument("--date", default="")
    ap.add_argument("--gait", default="駈歩・襲歩")
    ap.add_argument("-o", "--out", default="biomech_report.html")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest(); return
    if not a.h5:
        ap.error("--h5 か --selftest を指定")
    import biomech
    res = biomech.analyze_h5(a.h5, fps=a.fps)
    print("保存:", build(res, a.out, name=a.name, date=a.date, gait=a.gait))


if __name__ == "__main__":
    main()
