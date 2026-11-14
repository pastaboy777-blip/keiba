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
import statistics as st

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


# ══════════════════════════════════════════════════════════════════
# 採点表ビュー（参考スライド手順6-1）
#   各項目を競走成績への重要順に並べ、1〜5点（3＝標準）で採点する。
#   ・同じ速さで比べる馬が3頭未満の項目は採点せず「判定しない(灰)」。
#   ・res から値が取れない項目も「判定しない」。
#   ・緑＝良い／灰＝標準・判定しない／赤＝課題。
#   ・採点できた項目だけで平均点を出す（判定しない項目は除く）。
# ══════════════════════════════════════════════════════════════════
SC_GREEN = "#2f9e44"   # 良い
SC_GRAY = "#adb5bd"    # 標準・判定しない
SC_RED = "#e03131"     # 課題

MIN_PRIORS = 3         # これ未満の比較頭数なら「判定しない」


def _swing_mean(r):
    """腰（後肢）と前肢の振り幅の平均（°）。"""
    vs = [(r.get("振り幅_後肢") or {}).get("振り幅"),
          (r.get("振り幅_前肢") or {}).get("振り幅")]
    vs = [x for x in vs if x is not None]
    return round(st.mean(vs)) if vs else None


def _rom_mean(r):
    """飛節・腕節の動く幅の平均（°）。"""
    rom = r.get("関節ROM") or {}
    vs = [rom.get("飛節"), rom.get("腕節")]
    vs = [x for x in vs if x is not None]
    return round(st.mean(vs), 1) if vs else None


def _load_peak(r):
    """負荷の配分の代表＝最も高い部位の負荷（1〜5・モデル推定）。小さいほど良い。"""
    le = r.get("load_est") or {}
    return max(le.values()) if le else None


# 行定義: (番号ラベル, 単位, higher_better＝値が大きいほど良い, est＝モデル推定, getter)
#   並び順＝競走成績への重要順（スライド手順6-1）。
SCORE_ROWS = [
    ("歩幅", "倍", True, False,
     lambda r: (r.get("stride") or {}).get("歩幅_体長比")),
    ("リズムの安定", "", True, False,
     lambda r: r.get("リズム重なり")),
    ("毎秒の完歩数", "回", True, False,
     lambda r: (r.get("stride") or {}).get("完歩_毎秒")),
    ("軌跡の大きさ（幅）", "", True, False,
     lambda r: (r.get("軌跡幅_前肢") or {}).get("幅_体長比")),
    ("腰・前肢の振り幅", "°", True, False, _swing_mean),
    ("騎乗バランス（人の重心）", "%", True, False,
     lambda r: r.get("人重心ずれ")),            # phase2（人体ポーズ）→ None＝判定しない
    ("後肢の踏み込み", "", True, False,
     lambda r: r.get("踏み込み_臀端0肩端1")),
    ("飛節・腕節の動く幅", "°", True, False, _rom_mean),
    ("前肢のブレーキの少なさ（かき込み）", "", True, False,
     lambda r: r.get("かき込み度")),            # 1=後ろへ引いて着く＝ブレーキ少
    ("負荷の配分", "", False, True, _load_peak),  # 小さいほど良い・モデル推定
]


def _score(v, priors, higher_better):
    """1〜5点（3＝標準）。比較分布 priors が3頭未満 or 値なし→None（判定しない）。"""
    vals = [p for p in (priors or []) if p is not None]
    if v is None or len(vals) < MIN_PRIORS:
        return None
    mean = st.mean(vals)
    sd = st.pstdev(vals)
    if sd < 1e-9:
        return 3
    z = (v - mean) / sd
    if not higher_better:
        z = -z
    if z >= 1.0:
        return 5
    if z >= 0.33:
        return 4
    if z > -0.33:
        return 3
    if z > -1.0:
        return 2
    return 1


def _score_color(score):
    if score is None or score == 3:
        return SC_GRAY
    return SC_GREEN if score >= 4 else SC_RED


def _score_word(score):
    if score is None:
        return "判定しない"
    return {5: "とても良い", 4: "良い", 3: "標準", 2: "やや課題", 1: "課題"}[score]


def _score_bar_svg(score):
    """1〜5点の5マスバー。得点まで色で塗る。判定しない＝灰の帯。"""
    W, H = 180, 24
    cells, gap = 5, 5
    cw = (W - gap * (cells - 1)) / cells
    col = _score_color(score)
    out = [f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           f'font-family="sans-serif">']
    if score is None:
        out.append(f'<rect x="0" y="3" width="{W}" height="18" rx="4" '
                   f'fill="#f1f3f5" stroke="#dee2e6"/>')
        out.append(f'<text x="{W/2:.0f}" y="16" text-anchor="middle" '
                   f'font-size="11" fill="{SC_GRAY}">判定しない</text>')
    else:
        for i in range(cells):
            x = i * (cw + gap)
            fill = col if (i + 1) <= score else "#e9ecef"
            out.append(f'<rect x="{x:.1f}" y="3" width="{cw:.1f}" height="18" '
                       f'rx="4" fill="{fill}"/>')
    out.append("</svg>")
    return "".join(out)


def _score_reason(v, unit, priors, est=False):
    """右側の短い根拠テキスト（res の数値）。"""
    vals = [p for p in (priors or []) if p is not None]
    tail = "（モデル推定・実測でない）" if est else ""
    if v is None:
        return "値が取れません（測定なし）" + tail
    sv = _fmt(v, unit)
    if len(vals) < MIN_PRIORS:
        return f"測定値 {sv}・比較 {len(vals)}頭（3頭未満のため判定しない）" + tail
    return f"測定値 {sv}・比較 {len(vals)}頭（中央 {_fmt(st.median(vals), unit)}）" + tail


def render_scorecard(res, name="この馬", date="", gait="駈歩・襲歩", priors=None):
    """採点表（手順6-1）のHTMLを返す。priors＝比較馬の分布 {ラベル:[値,...]}。"""
    priors = priors or {}
    rows_html, scores, good, bad = [], [], [], []
    for idx, (label, unit, hb, est, getter) in enumerate(SCORE_ROWS, 1):
        v = getter(res) if res else None
        pr = priors.get(label)
        sc = _score(v, pr, hb)
        if sc is not None:
            scores.append(sc)
            if sc >= 4:
                good.append(label)
            elif sc <= 2:
                bad.append(label)
        col = _score_color(sc)
        disp = str(sc) if sc is not None else "—"
        rows_html.append(
            '<div class="row">'
            f'<div class="lab"><span class="no">{idx}</span>'
            f'<span class="nm">{html.escape(label)}</span></div>'
            f'<div class="bar">{_score_bar_svg(sc)}</div>'
            f'<div class="sc" style="color:{col}">{disp}'
            f'<span class="j">{_score_word(sc)}</span></div>'
            f'<div class="rz">{html.escape(_score_reason(v, unit, pr, est))}</div>'
            '</div>')
    m, n = len(scores), len(SCORE_ROWS)
    avg = round(st.mean(scores), 1) if scores else None
    avg_txt = (f"{n}項目中 <b>{m}項目</b>を採点／平均は <b>{avg}</b> 点"
               if m else f"{n}項目中 <b>0項目</b>を採点（採点できる項目がありません）")
    good_txt = "・".join(good) if good else "—"
    bad_txt = "・".join(bad) if bad else "—"
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(name)} 採点表</title><style>
 body{{margin:0;background:#f4f5f7;color:#1b2733;font-family:system-ui,
   -apple-system,"Hiragino Kaku Gothic ProN",sans-serif}}
 .wrap{{max-width:980px;margin:0 auto;background:#fff}}
 .hd{{background:#17345c;color:#fff;padding:14px 20px;display:flex;
   justify-content:space-between;align-items:baseline}}
 .hd .t{{font-size:17px;font-weight:700}} .hd .m{{font-size:12px;opacity:.85}}
 .leg{{display:flex;gap:16px;padding:8px 20px;font-size:11px;color:#495057;
   border-bottom:1px solid #e9ecef;flex-wrap:wrap}}
 .leg .g{{color:{SC_GREEN};font-weight:700}} .leg .y{{color:{SC_GRAY};font-weight:700}}
 .leg .r{{color:{SC_RED};font-weight:700}}
 .row{{display:grid;grid-template-columns:220px 190px 92px 1fr;align-items:center;
   padding:5px 20px;border-bottom:1px solid #f1f3f5}}
 .row:nth-child(even){{background:#fafbfc}}
 .lab .no{{display:inline-block;width:20px;color:#adb5bd;font-size:12px;
   font-weight:700}}
 .lab .nm{{font-size:14px;font-weight:600}}
 .sc{{font-size:20px;font-weight:700}}
 .sc .j{{display:block;font-size:10.5px;font-weight:600;margin-top:-2px}}
 .rz{{font-size:11px;color:#495057;line-height:1.45}}
 .sum{{padding:10px 20px;font-size:12.5px;color:#1b2733;line-height:1.8;
   border-bottom:1px solid #e9ecef}}
 .sum .g{{color:{SC_GREEN};font-weight:700}} .sum .r{{color:{SC_RED};font-weight:700}}
 .note{{padding:12px 20px;font-size:11.5px;color:#495057;line-height:1.7}}
 .note .warn{{color:{SC_RED};font-weight:600}}
 .src{{padding:4px 20px 18px;font-size:10.5px;color:#868e96;line-height:1.7}}
</style></head><body><div class="wrap">
<div class="hd"><div class="t">{html.escape(name)}　採点表（手順6-1：競走成績への重要順に1〜5点）</div>
<div class="m">{html.escape(date)}　{html.escape(gait)}</div></div>
<div class="leg"><span class="g">■ 緑＝良い</span>
<span class="y">■ 灰＝標準・判定しない</span>
<span class="r">■ 赤＝課題</span>
<span>各点は 1〜5点（3＝標準）。並び順＝競走成績への重要順。</span></div>
{"".join(rows_html)}
<div class="sum"><div>平均：{avg_txt}</div>
<div><span class="g">良い点</span>：{html.escape(good_txt)}</div>
<div><span class="r">課題</span>：{html.escape(bad_txt)}</div></div>
<div class="note"><span class="warn">採点できた項目だけで平均を出しています。</span>
判定しない項目（比較する馬が3頭未満／値が取れない）は平均から除くため、
<b>平均は高めに出る可能性</b>があります。同じ速さで比べる馬が3頭以上そろうと、
その項目も採点できるようになります。これは“採点”であって断定ではありません。
関節角度は測り方が研究と違うため、採点は比較馬の分布に対する相対です。</div>
<div class="src">緑＝良い／灰＝標準・判定しない／赤＝課題。負荷の配分は
<b>モデル推定（実測でない）</b>です。区切り（1〜5点の境目）は暫定です。
出典：体長比・歩幅・回転と成績 Morrice-West 2021／Barrey 2001／Schrurs 2022、
円弧モデル・かき込み型 小林寛道（東京大学名誉教授）、体節質量比 Buchner 1997／
de Leva 1996。重心・力・負荷はモデル推定で実測ではありません。</div>
</div></body></html>"""


def build_scorecard(res, out, **kw):
    doc = render_scorecard(res, **kw)
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

    # ── 採点表ビュー（手順6-1）──
    # priors を細工して、緑（歩幅）／赤（後肢の踏み込み）／灰（他）が全部出るようにする
    v_sr = (res.get("stride") or {}).get("歩幅_体長比")
    v_rc = res.get("踏み込み_臀端0肩端1")
    assert v_sr is not None and v_rc is not None, "採点対象の値が取れない"
    priors = {
        # res の歩幅より十分低い分布（ばらつき有り）→ 高評価＝緑
        "歩幅": [v_sr * 0.40, v_sr * 0.48, v_sr * 0.44, v_sr * 0.52, v_sr * 0.46],
        # res の踏み込みより十分高い分布→ 低評価＝赤
        "後肢の踏み込み": [v_rc * 1.5, v_rc * 1.7, v_rc * 1.55, v_rc * 1.65, v_rc * 1.6],
        # 2頭だけ＝3頭未満→判定しない（灰）
        "リズムの安定": [0.9, 0.95],
    }
    out2 = "/tmp/biomech_scorecard_selftest.html"
    build_scorecard(res, out2, name="合成テスト号", date="2026-11-14", priors=priors)
    doc2 = open(out2, encoding="utf-8").read()
    for need in ("採点", "判定しない", "平均", "歩幅", "負荷の配分",
                 SC_GREEN, SC_GRAY, SC_RED):
        assert need in doc2, f"採点表に {need} が無い"
    # 行数 = SCORE_ROWS 数
    assert doc2.count('class="row"') == len(SCORE_ROWS), "採点行数が合わない"
    # 空 priors なら全項目「判定しない」＝採点0項目
    doc3 = render_scorecard(res, name="無比較号")
    assert "0項目</b>を採点" in doc3, "比較0頭で全項目が判定しないになっていない"
    # 細工 priors で緑と赤が両方描画されている（バーの塗り色）
    assert f'fill="{SC_GREEN}"' in doc2, "緑の採点バーが出ていない"
    assert f'fill="{SC_RED}"' in doc2, "赤の採点バーが出ていない"
    print(f"保存: {out2}")
    print("SELFTEST PASSED（この馬の位置レポート8行＋採点表10行を生成。採点は"
          "1〜5点・3頭未満は判定しない・緑/灰/赤・平均と良い点/課題・モデル推定"
          "注記・出典を含む）")


def main():
    ap = argparse.ArgumentParser(description="バイオメカ報告『この馬の位置』")
    ap.add_argument("--h5")
    ap.add_argument("--fps", type=float)
    ap.add_argument("--name", default="この馬")
    ap.add_argument("--date", default="")
    ap.add_argument("--gait", default="駈歩・襲歩")
    ap.add_argument("-o", "--out", default="biomech_report.html")
    ap.add_argument("--scorecard", action="store_true",
                    help="採点表ビュー（手順6-1）を出力する")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest(); return
    if not a.h5:
        ap.error("--h5 か --selftest を指定")
    import biomech
    res = biomech.analyze_h5(a.h5, fps=a.fps)
    builder = build_scorecard if a.scorecard else build
    print("保存:", builder(res, a.out, name=a.name, date=a.date, gait=a.gait))


if __name__ == "__main__":
    main()
