"""ラップ分析の可視化(標準ライブラリのみ)。

- render_text:  ターミナル向けの表+サマリ
- render_html:  画像と同等の見た目(緑ヘッダ + 200m列 + コーナー区間色分け +
                200m換算の折れ線グラフ)を inline SVG で描画。外部依存なし。
"""

from __future__ import annotations

from .lap import RaceLap, LapAnalysis


# コーナー区間ラベル → 背景色(画像の配色に合わせた淡色)
_SEG_COLORS = {
    "スタート〜1C": "#fdf3da",
    "1C〜2C": "#fdf3da",
    "2C〜向正面": "#e8f3fb",
    "向正面": "#e8f3fb",
    "向正面〜3C": "#e8f3fb",
    "3C〜4C": "#fce8ee",
    "4C〜直線": "#fce8ee",
    "直線": "#e7f4e8",
}
_DEFAULT_SEG_COLOR = "#f2f2f2"


def _seg_color(label: str) -> str:
    return _SEG_COLORS.get(label, _DEFAULT_SEG_COLOR)


# ---------------------------------------------------------------------------
# テキスト出力
# ---------------------------------------------------------------------------

def render_text(race: RaceLap) -> str:
    a = race.analysis
    lines: list[str] = []
    head = f"{race.date} {race.place}{race.race_no}R  {race.surface}{race.distance}m  馬場:{race.going}"
    lines.append(head)
    if race.race_name:
        lines.append(f"  {race.race_name}")
    lines.append("=" * max(len(head), 40))

    # 表(距離 / ラップ / 区間)
    cols = [f"{m}m" for m in a.marks]
    laps = [f"{x:.1f}" for x in a.furlongs]
    w = max(7, max(len(c) for c in cols))
    lines.append("距離 | " + " ".join(c.rjust(w) for c in cols))
    lines.append("ﾗｯﾌﾟ | " + " ".join(l.rjust(w) for l in laps))
    lines.append("区間 | " + " ".join((race.analysis.labels[i] if i < len(a.labels) else "").rjust(w) for i in range(len(a.marks))))

    # 最速・最遅マーク
    mark = ["  "] * len(a.furlongs)
    mark[a.fastest_idx] = "▲速"
    mark[a.slowest_idx] = "▽遅"
    lines.append("     | " + " ".join(m.rjust(w) for m in mark))

    lines.append("-" * 40)
    lines.append(f"走破:{a.race_time:.1f}  平均ハロン:{a.avg_furlong:.2f}")
    if a.ten_3f is not None and a.last_3f is not None:
        lines.append(f"テン3F:{a.ten_3f:.1f}  上がり3F:{a.last_3f:.1f}  差:{a.ten_3f - a.last_3f:+.1f}")
    if a.first_half is not None and a.second_half is not None:
        lines.append(f"前半{a.first_half_n}F:{a.first_half:.1f}  後半{a.second_half_n}F:{a.second_half:.1f}")
    lines.append(f"ペース:{a.pace} / {a.balance}")
    if a.note:
        lines.append(f"※ {a.note}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML 出力(画像相当)
# ---------------------------------------------------------------------------

def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _svg_chart(a: LapAnalysis, *, width: int = 1180, height: int = 560) -> str:
    """200m換算の折れ線グラフを inline SVG で描く。

    y軸はラップ秒で、速い(小さい)ほど上=画像と同じ向き(上が速い)。
    背景はコーナー区間色で塗り分ける。
    """
    n = len(a.furlongs)
    if n == 0:
        return ""
    pad_l, pad_r, pad_t, pad_b = 64, 24, 24, 56
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    lo = min(a.furlongs)
    hi = max(a.furlongs)
    # 0.5秒の余白を上下に。レンジが狭すぎる場合の保険。
    y_min = round(lo - 0.5, 1)
    y_max = round(hi + 0.5, 1)
    if y_max - y_min < 1.0:
        y_min, y_max = lo - 0.5, hi + 0.5

    def x_at(i: int) -> float:
        if n == 1:
            return pad_l + plot_w / 2
        return pad_l + plot_w * i / (n - 1)

    def y_at(v: float) -> float:
        # 上が速い(小さい値) → 上端が y_min ではなく…画像は上が速い(11.0)下が遅い(14.0)
        frac = (v - y_min) / (y_max - y_min)
        return pad_t + plot_h * frac

    parts: list[str] = []
    parts.append(f'<svg viewBox="0 0 {width} {height}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="sans-serif">')
    parts.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>')

    # 区間背景(各点を中心に左右半区間ずつ塗る)
    for i in range(n):
        label = a.labels[i] if i < len(a.labels) else ""
        color = _seg_color(label)
        left = x_at(i) - (plot_w / (n - 1) / 2 if n > 1 else plot_w / 2)
        right = x_at(i) + (plot_w / (n - 1) / 2 if n > 1 else plot_w / 2)
        left = max(left, pad_l)
        right = min(right, pad_l + plot_w)
        parts.append(f'<rect x="{left:.1f}" y="{pad_t}" width="{right-left:.1f}" height="{plot_h}" fill="{color}"/>')

    # y軸グリッド+目盛(0.5刻み)
    t = y_min
    while t <= y_max + 1e-6:
        yy = y_at(t)
        parts.append(f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{pad_l+plot_w}" y2="{yy:.1f}" stroke="#e6e6e6" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l-10}" y="{yy+4:.1f}" font-size="13" fill="#888" text-anchor="end">{t:.1f}</text>')
        t = round(t + 0.5, 1)

    # x軸ラベル(距離)
    for i in range(n):
        parts.append(f'<text x="{x_at(i):.1f}" y="{pad_t+plot_h+24}" font-size="13" fill="#666" text-anchor="middle">{a.marks[i]}</text>')

    # 折れ線
    pts = " ".join(f"{x_at(i):.1f},{y_at(a.furlongs[i]):.1f}" for i in range(n))
    parts.append(f'<polyline points="{pts}" fill="none" stroke="#e6a23c" stroke-width="3"/>')
    for i in range(n):
        parts.append(f'<circle cx="{x_at(i):.1f}" cy="{y_at(a.furlongs[i]):.1f}" r="5" fill="#e6a23c"/>')

    # 凡例
    parts.append(f'<line x1="{pad_l}" y1="{height-14}" x2="{pad_l+30}" y2="{height-14}" stroke="#e6a23c" stroke-width="3"/>')
    parts.append(f'<text x="{pad_l+38}" y="{height-10}" font-size="13" fill="#555">ラップタイム(200m換算)</text>')
    parts.append('</svg>')
    return "".join(parts)


def render_race_html_fragment(race: RaceLap) -> str:
    a = race.analysis
    n = len(a.furlongs)

    # ヘッダ見出し
    title = f"{race.place}{race.race_no}R ラップタイム"
    sub = f"{race.date}　{race.surface}{race.distance}m　馬場:{race.going}　{_esc(race.race_name)}"

    # 表(距離 / ラップ / 区間)
    th_cells = "".join(f'<th>{m}m</th>' for m in a.marks)
    lap_cells = "".join(f'<td class="lap">{x:.1f}</td>' for x in a.furlongs)
    seg_cells = ""
    for i in range(n):
        label = a.labels[i] if i < len(a.labels) else ""
        seg_cells += f'<td class="seg" style="background:{_seg_color(label)}">{_esc(label)}</td>'

    # サマリ
    summ = []
    summ.append(f"走破 <b>{a.race_time:.1f}</b>")
    summ.append(f"平均ハロン <b>{a.avg_furlong:.2f}</b>")
    if a.ten_3f is not None:
        summ.append(f"テン3F <b>{a.ten_3f:.1f}</b>")
    if a.last_3f is not None:
        summ.append(f"上がり3F <b>{a.last_3f:.1f}</b>")
    if a.first_half is not None and a.second_half is not None:
        summ.append(f"前半{a.first_half_n}F <b>{a.first_half:.1f}</b> / 後半{a.second_half_n}F <b>{a.second_half:.1f}</b>")
    summ.append(f'ペース <b class="pace">{a.pace}</b>（{a.balance}）')

    chart = _svg_chart(a)
    corners = ""
    if race.corners:
        corners = '<div class="corners">コーナー通過順位：' + " / ".join(_esc(c) for c in race.corners) + "</div>"

    return f'''<section class="race">
  <div class="hd">{_esc(title)}</div>
  <div class="sub">{sub}</div>
  <table class="lap">
    <tr class="head">{th_cells}</tr>
    <tr class="laprow">{lap_cells}</tr>
    <tr class="segrow">{seg_cells}</tr>
  </table>
  <div class="summary">{" ｜ ".join(summ)}</div>
  {corners}
  <div class="chart">{chart}</div>
</section>'''


_CSS = """
body{font-family:'Hiragino Sans','Noto Sans JP',sans-serif;background:#f6f7f9;margin:0;padding:24px;color:#333}
h1{font-size:20px;margin:0 0 16px}
.race{background:#fff;border-radius:10px;box-shadow:0 1px 4px rgba(0,0,0,.08);padding:0 0 16px;margin:0 0 28px;overflow:hidden}
.hd{background:#5cb377;color:#fff;font-size:20px;font-weight:bold;text-align:center;padding:14px}
.sub{font-size:13px;color:#666;text-align:center;padding:10px 8px 6px}
table.lap{border-collapse:collapse;width:calc(100% - 24px);margin:8px 12px}
table.lap td,table.lap th{border:1px solid #e3e3e3;text-align:center;padding:8px 4px;font-size:14px}
table.lap tr.head th{background:#efefef;color:#555;font-weight:600}
table.lap td.lap{font-size:17px}
table.lap td.seg{font-size:11px;color:#555}
.summary{margin:10px 14px;font-size:14px;color:#444}
.summary .pace{color:#c0552b}
.corners{margin:4px 14px 0;font-size:12px;color:#777}
.chart{margin:8px 12px 0}
"""


def render_html(races: list[RaceLap], *, title: str = "ラップ分析") -> str:
    body = "\n".join(render_race_html_fragment(r) for r in races)
    return f'''<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>{_CSS}</style></head>
<body>
<h1>{_esc(title)}</h1>
{body}
</body></html>'''
