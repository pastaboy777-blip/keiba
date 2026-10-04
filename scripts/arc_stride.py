#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""凱旋門賞 2025/2026 ── 完歩・ピッチ・接地時間で読む。

同じ53完歩で速度が違うのはなぜか、を数字で詰めるための道具。
  速度 = ストライド長 × ピッチ
完歩数が同じならストライド長は同じなので、差は全部ピッチから来る。
"""
from __future__ import annotations
import json, statistics

SRC = "/home/user/keiba/data/temae/arc_sectionals.json"
D = json.load(open(SRC, encoding="utf-8"))
SEG = 200.0          # 1区間の距離
STR_LAST400 = 53     # ファンクの目視


def g(year, name):
    for h in D[year]["horses"]:
        if h["name"] == name:
            return h
    return None


def line(s=""):
    print(s)


daryz = {y: g(y, "DARYZ") for y in ("2025", "2026")}

line("■ ダリズ ── ラスト400mを完歩で割る")
line("   完歩数は2年とも53（目視）。つまりストライド長は同じ。")
line()
line("   %-6s %-9s %-9s %-10s %-11s %-11s %s"
     % ("年", "400→200", "200→ARR", "ラスト400", "ストライド", "ピッチ", "1完歩の時間"))
rows = {}
for y, h in daryz.items():
    t5, t6 = h["T5"], h["T6"]
    last400 = t5 + t6
    sl = 400.0 / STR_LAST400
    pitch = STR_LAST400 / last400
    sdur = last400 / STR_LAST400
    rows[y] = dict(t5=t5, t6=t6, last400=last400, sl=sl, pitch=pitch, sdur=sdur,
                   last600=h["T4"] + t5 + t6, vmax=h["vmax"])
    line("   %-6s %-9.2f %-9.2f %-10.2f %-11.3f %-11.4f %.4f秒"
         % (y, t5, t6, last400, sl, pitch, sdur))

a, b = rows["2025"], rows["2026"]
line()
line("   ラスト400mの差       %+.2f秒  (%.2f → %.2f)" % (b["last400"] - a["last400"], a["last400"], b["last400"]))
line("   ストライド長の差     %+.3f m   ← 完歩数が同じなのでゼロ" % (b["sl"] - a["sl"]))
line("   ピッチの差           %+.4f 完歩/秒 (%+.1f%%)"
     % (b["pitch"] - a["pitch"], 100 * (b["pitch"] / a["pitch"] - 1)))
line("   1完歩の時間の差      %+.1f ミリ秒  ← 速度差の正体はこれが全部"
     % (1000 * (b["sdur"] - a["sdur"])))

line()
line("■ 同じ馬の中での疲労（400→200m と 200→ARR の1完歩あたり）")
line("   1区間200m ÷ ストライド %.3fm = %.1f完歩ぶん" % (a["sl"], SEG / a["sl"]))
line()
nseg = SEG / (400.0 / STR_LAST400)
for y in ("2025", "2026"):
    r = rows[y]
    d5, d6 = r["t5"] / nseg, r["t6"] / nseg
    line("   %s  400→200 %.4f秒/完歩 → 200→ARR %.4f秒/完歩  落ち %+.1f ミリ秒"
         % (y, d5, d6, 1000 * (d6 - d5)))

line()
line("■ ものさしを揃える（すべて1完歩あたりのミリ秒）")
# 2016良 2:23.6 と 2012重 2:37.6（netkeiba）。2400mを同じストライドで割る。
sl = 400.0 / STR_LAST400
for lab, sec_ in (("2016 良 2:23.6（Found）", 143.6), ("2012 重 2:37.6（ソレミア）", 157.6)):
    line("   %-26s 1完歩 %.4f秒" % (lab, sl / (2400.0 / sec_)))
d_going = sl / (2400.0 / 157.6) - sl / (2400.0 / 143.6)
line("   → 良と重の差                %+.1f ミリ秒" % (1000 * d_going))
line("   → ダリズ 2025→2026 の差     %+.1f ミリ秒" % (1000 * (b["sdur"] - a["sdur"])))
line("   → ダリズ 2026 の終い200mの落ち %+.1f ミリ秒"
     % (1000 * (b["t6"] / nseg - b["t5"] / nseg)))

line()
line("■ 両年に走った馬 ── 最高速度（km/h）")
line("   %-16s %-8s %-8s %s" % ("馬", "2025", "2026", "差"))
both = []
for nm in ("DARYZ", "MINNIE HAUK", "KALPANA", "ARROW EAGLE"):
    x, y2 = g("2025", nm), g("2026", nm)
    if x and y2:
        both.append(y2["vmax"] - x["vmax"])
        line("   %-16s %-8.2f %-8.2f %+.2f" % (nm, x["vmax"], y2["vmax"], y2["vmax"] - x["vmax"]))
line("   %-16s %-8s %-8s %+.2f" % ("平均", "", "", statistics.mean(both)))

line()
line("■ 出走馬全体の最高速度（km/h）")
for y in ("2025", "2026"):
    v = D[y]["vmax_field"]
    line("   %s  %d頭  最低 %.2f  中央 %.2f  最高 %.2f"
         % (y, len(v), min(v), statistics.median(v), max(v)))
v25, v26 = D["2025"]["vmax_field"], D["2026"]["vmax_field"]
line("   2026の最低 %.2f  vs  2025の最高 %.2f  → 分布の重なり %s"
     % (min(v26), max(v25), "ほぼ無し" if min(v26) >= max(v25) - 0.5 else "あり"))
line("   中央値の差 %+.2f km/h" % (statistics.median(v26) - statistics.median(v25)))

line()
line("■ 両年に走った馬 ── ラスト600m（秒）")
line("   %-16s %-8s %-8s %s" % ("馬", "2025", "2026", "差"))
for nm in ("DARYZ", "MINNIE HAUK", "KALPANA", "ARROW EAGLE"):
    x, y2 = g("2025", nm), g("2026", nm)
    if not (x and y2):
        continue
    l25 = x.get("last600_sheet")
    l26 = (y2.get("T4") or 0) + y2["T5"] + y2["T6"]
    if l25 and y2.get("T4"):
        line("   %-16s %-8.2f %-8.2f %+.2f" % (nm, l25, l26, l26 - l25))

line()
line("■ レースの形（ダリズ）")
for y in ("2025", "2026"):
    h = daryz[y]
    tot = sum(h[k] for k in ("T1", "T2", "T3", "T4", "T5", "T6"))
    line("   %s  前1400m %.2f ／ 以降1000m %.2f ／ 合計 %.2f（公式 %s）"
         % (y, h["T1"], tot - h["T1"], tot, h["official"]))
line("   → 前半は %+.2f秒、後半1000mは %+.2f秒"
     % (daryz["2026"]["T1"] - daryz["2025"]["T1"],
        (sum(daryz["2026"][k] for k in ("T2", "T3", "T4", "T5", "T6")))
        - (sum(daryz["2025"][k] for k in ("T2", "T3", "T4", "T5", "T6")))))

line()
line("■ 手前の替え（目視・未検証）")
t = D["temae_observed"]
line("   2025 ダリズ %d完歩で %d回 → %.1f完歩に1回"
     % (t["2025"]["strides_last400"], t["2025"]["changes"],
        t["2025"]["strides_last400"] / max(t["2025"]["changes"], 1)))
line("   2026 ダリズ %d完歩で %d回 → %.1f完歩に1回"
     % (t["2026"]["strides_last400"], t["2026"]["changes"],
        t["2026"]["strides_last400"] / max(t["2026"]["changes"], 1)))
