# -*- coding: utf-8 -*-
"""貼ってもらった馬のリストを、上がりと馬体重だけで並べる。

  python3 scripts/ana/ooi_list_card.py <list.json> <日付> <out.html>
"""
import html, json, sys

LIST, DAY, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
P = json.load(open(LIST, encoding='utf-8'))

rows = []
for p in P:
    ag = f"{p['ag']:.1f}" if p['ag'] is not None else '－'
    rows.append(
      f'<tr><td class=r>{p["R"]}R<br><span class=dm>{p["dist"]}m</span></td>'
      f'<td class=u>{p["u"]}</td>'
      f'<td class=nm>{html.escape(p["nm"])}</td>'
      f'<td class=ag>{ag}</td>'
      f'<td class=wt>{p["wt"] or "－"}<span class=un>kg</span></td></tr>')

HTML = f'''<!doctype html><html lang=ja><head><meta charset=utf-8>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0a0a0a;color:#e8e6e3;font-family:"Hiragino Sans","Noto Sans JP",system-ui,sans-serif;
 padding:54px 64px 46px;width:1020px;-webkit-font-smoothing:antialiased}}
h1{{font-size:38px;font-weight:800}} h1 .ac{{color:#d95926}}
table{{width:100%;border-collapse:collapse;margin-top:30px}}
th{{font-size:14px;color:#8e8a84;font-weight:500;text-align:left;padding:0 14px 11px;
 border-bottom:1px solid #262622}}
td{{padding:20px 14px;border-bottom:1px solid #1d1d1a;vertical-align:middle}}
.r{{width:92px;color:#8e8a84;font-weight:700;font-size:18px;line-height:1.4}}
.dm{{font-size:14px;font-weight:500}}
.u{{width:58px;font-weight:800;font-size:28px}}
.nm{{font-weight:800;font-size:31px;letter-spacing:.01em}}
.ag{{width:116px;font-size:29px;font-weight:800;font-variant-numeric:tabular-nums}}
.wt{{width:124px;font-size:23px;font-weight:700;font-variant-numeric:tabular-nums}}
.un{{font-size:14px;color:#8e8a84;margin-left:3px;font-weight:500}}
footer{{margin-top:32px;padding-top:22px;border-top:1px solid #262622;
 font-size:16px;line-height:1.9;color:#a5a19b}}
footer b{{color:#fff}}
</style></head><body>
<h1>{DAY} 大井 ── <span class=ac>11頭</span></h1>
<table><thead><tr><th>R</th><th>番</th><th>馬名</th><th>上がり</th><th>馬体重</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<footer>上がりは同じ距離帯の直近5走の中央値。<b>－ はその距離の実測が足りない馬</b>（11頭中7頭）。
馬体重は直近3走の中央値。</footer></body></html>'''
open(OUT, 'w', encoding='utf-8').write(HTML)
print('書き出し', OUT)
