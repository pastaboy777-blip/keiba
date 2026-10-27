# -*- coding: utf-8 -*-
"""馬のリストを、今年の大井の実測で並べて1枚にする。

  python3 scripts/ana/ooi_list_card.py <list.json> <日付> <out.html>

同距離帯の上がり・そのばらつき・実測の走数・馬体重・普段の4角位置・
3→4角を並べる。印はつけない。
"""
import html, json, sys

LIST, DAY, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
P = json.load(open(LIST, encoding='utf-8'))

WHY = {
 'グレートロッタリー':
   '1600mを4走して上がり 40.4・41.3・40.6・40.9。<b>0.9秒の幅に収まり、'
   'ばらつき0.34はこの11頭で最小</b>。<b>440kg</b>',
 'ムーンシェイド':
   '450kgで<b>普段4角1番手</b>。この11頭で唯一はっきり前に行ける。'
   '人気薄で4角3番手以内は <b>11.6%</b>（+2.4pt）。1600m→1200mの短縮。'
   '前走は1600mを1番人気3着',
 'アップタウンガール':
   '<b>上がり39.9はこの11頭で最速</b>。'
   '普段4角3.0番手から<b>3→4角も+0.5</b>と押し上げる。<b>455kg</b>',
 'カルサパラストリス':
   '<b>1600mを5走、ばらつき0.52</b>で材料がいちばん厚い。上がり40.1は11頭で2番目に速い。'
   '<b>445kg</b>',
 'ヤッティライネン':
   '<b>443kgで10走ぶんの実測</b>。1200mでは上がり 38.0・38.5・38.7・39.2・39.4 を使えている。'
   '普段4角8番手から<b>3→4角+1.0</b>と押し上げる',
 'ユイノサンバンカン':
   '<b>1600mを5走</b>、上がり40.6でばらつき0.92。<b>462kg</b>で普段4角7番手',
 'クリムゾンバースト':
   '前走1600mで上がり<b>40.4</b>。466kgで普段4角6番手。1600m→1200mの短縮',
 'ウィルアトレ':
   '465kgで普段4角7番手。前走は1800mを6番人気<b>4着</b>。1800m→1400mの短縮',
 'イノセントワールド':
   '<b>452kgで普段4角4番手</b>。前走は1600m稍重を4番人気<b>3着</b>。1600m→1400mの短縮',
 'ディアローラ': '大井は初出走',
 'サラン': '大井は初出走',
}

# 長い馬名は意味の切れ目で2行にする（数字は前半の文字数）
BREAK = {'イノセントワールド': 5, 'ユイノサンバンカン': 3, 'クリムゾンバースト': 5,
         'グレートロッタリー': 4, 'アップタウンガール': 6, 'カルサパラストリス': 3,
         'ヤッティライネン': 4, 'ムーンシェイド': 3, 'ディアローラ': 0,
         'ウィルアトレ': 0, 'サラン': 0}


def wrap(nm):
    k = BREAK.get(nm, 5 if len(nm) >= 9 else 0)
    if not k:
        return html.escape(nm)
    return html.escape(nm[:k]) + '<br>' + html.escape(nm[k:])


NR = len({p['R'] for p in P})

rows = []
for p in P:
    why = WHY.get(p['nm'], '')
    thin = p['nsd'] < 2
    ag = (f"{p['ag']:.1f}" if p['ag'] is not None
          else ('<span class=w>他距離</span>' if p['ag_other'] else '－'))
    sd = f"{p['sd']:.2f}" if p['sd'] is not None else '－'
    pos = f"{p['pos']:.1f}" if p['pos'] is not None else '－'
    g = f"{p['gain']:+.1f}" if p['gain'] is not None else '－'
    rows.append(
      f'<tr><td class=r>{p["R"]}R<br><span class=dm>{p["dist"]}m {p["n"]}頭</span></td>'
      f'<td class=u>{p["u"]}</td>'
      f'<td class=nm>{wrap(p["nm"])}<span class=si>{html.escape(p["sire"])}</span></td>'
      f'<td class="ag{" dim" if thin else ""}">{ag}<br><span class=un>SD {sd}</span></td>'
      f'<td class=sm>{p["nsd"]}<span class=un>走</span><br>'
      f'<span class=un>全{p["nrun"]}走</span></td>'
      f'<td class=wtc>{p["wt"] or "－"}<span class=un>kg</span></td>'
      f'<td class=poc>{pos}<span class=un>番手</span><br>'
      f'<span class="gn{" up" if (p["gain"] or 0) > 0 else ""}">{g}</span></td>'
      f'<td class=why>{why}</td></tr>')

HTML = f'''<!doctype html><html lang=ja><head><meta charset=utf-8>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0a0a0a;color:#e8e6e3;font-family:"Hiragino Sans","Noto Sans JP",system-ui,sans-serif;
 padding:46px 54px 38px;width:2010px;-webkit-font-smoothing:antialiased}}
h1{{font-size:42px;font-weight:800;letter-spacing:.01em}}
h1 .ac{{color:#d95926;margin-left:18px}}
.cnt{{display:inline-block;background:#1d1d1a;border:1px solid #2e2e2a;color:#cfccc8;
 font-size:17px;font-weight:700;padding:5px 14px;border-radius:5px;margin-left:16px;
 vertical-align:7px}}
.tag{{display:inline-block;background:#d95926;color:#fff;font-size:15px;font-weight:700;
 padding:4px 12px;border-radius:5px;margin-left:14px;vertical-align:7px}}
.lead{{margin-top:14px;font-size:17px;line-height:1.75;color:#8e8a84}}
.lead b{{color:#cfccc8}}
.tiles{{display:grid;grid-template-columns:repeat(4,1fr);gap:15px;margin:26px 0 8px}}
.tile{{background:#141412;border:1px solid #262622;border-radius:10px;padding:17px 19px}}
.tile .k{{font-size:13px;color:#8e8a84}}
.tile .v{{font-size:37px;font-weight:800;margin-top:5px;line-height:1}}
.tile .v small{{font-size:18px;color:#8e8a84;margin-left:5px}}
.tile .n{{font-size:13px;color:#8e8a84;margin-top:8px;line-height:1.55}}
table{{width:100%;border-collapse:collapse;margin-top:18px}}
th{{font-size:12px;color:#8e8a84;font-weight:500;text-align:left;padding:0 10px 8px;
 border-bottom:1px solid #262622}}
td{{padding:15px 10px;border-bottom:1px solid #1d1d1a;font-size:16px;vertical-align:top}}
tr:nth-child(odd) td{{background:#0e0e0d}}

.r{{width:100px;color:#8e8a84;font-weight:700;font-size:17px;
 border-left:4px solid #3a3a36;padding-left:16px}}
.dm{{font-size:12px;color:#8e8a84;font-weight:500}}
.u{{width:62px;font-weight:800;font-size:34px;color:#d95926;line-height:1;
 font-variant-numeric:tabular-nums}}
.nm{{width:270px;font-weight:800;font-size:32px;line-height:1.24;
 letter-spacing:.01em}}
.si{{display:block;font-size:13px;font-weight:500;color:#8e8a84;margin-top:7px}}

.sm{{width:88px;color:#cfccc8;font-variant-numeric:tabular-nums;line-height:1.55;
 font-size:19px;font-weight:700;white-space:nowrap}}
.sm .un{{font-weight:500}}
.dim{{color:#5e5a54}}
.ag{{width:92px;color:#d95926;font-variant-numeric:tabular-nums;line-height:1.55;
 font-size:21px;font-weight:800;white-space:nowrap}}
.ag .un{{color:#8e8a84;font-weight:500}}
.ag.dim{{color:#6e6a64}}
.wtc{{width:92px;color:#199e70;font-variant-numeric:tabular-nums;font-size:21px;
 font-weight:800;white-space:nowrap}}
.wtc .un{{color:#8e8a84;font-weight:500}}
.poc{{width:96px;color:#3987e5;font-variant-numeric:tabular-nums;font-size:21px;
 font-weight:800;line-height:1.55;white-space:nowrap}}
.poc .un{{color:#8e8a84;font-weight:500}}
.gn{{font-size:14px;color:#8e8a84;font-weight:600}}
.gn.up{{color:#c98500}}
.un{{font-size:12px;color:#8e8a84}}
.big{{width:88px;font-size:21px;font-weight:800;font-variant-numeric:tabular-nums;color:#cfccc8}}
.rk{{width:64px;color:#b5b1ab;font-variant-numeric:tabular-nums;font-size:16px}}
.why{{color:#cfccc8;font-size:15px;line-height:1.72}}
.why b{{color:#fff}} .why .w{{color:#cfccc8;font-weight:700}}
.sm .w{{color:#8e8a84;font-weight:500;font-size:14px}}
footer{{margin-top:30px;padding-top:20px;border-top:1px solid #262622;
 font-size:15px;line-height:1.85;color:#a5a19b}}
footer b{{color:#fff}} footer .hl{{color:#ff8a5c;font-weight:700}}
</style></head><body>
<h1>{DAY} 大井　<span class=ac>{NR}鞍 {len(P)}頭</span></h1>
<p class=lead>上がりは<b>同じ距離帯の直近5走の中央値</b>、ばらつきはその標準偏差。
走数はその距離の実測。馬体重は直近3走の中央値。3→4角はプラスが押し上げ。</p>
<div class=tiles>
 <div class=tile><div class=k>人気薄 × 普段4角3番手以内</div>
  <div class=v style="color:#3987e5">11.6<small>%</small></div>
  <div class=n>人気薄ぜんぶは 9.3%（+2.4pt）</div></div>
 <div class=tile><div class=k>3→4角で+0.5〜1.0の押し上げ</div>
  <div class=v style="color:#c98500">30.2<small>%</small></div>
  <div class=n>全馬で <b>+7.3pt</b></div></div>
 <div class=tile><div class=k>同じ距離帯の上がりが最速</div>
  <div class=v style="color:#d95926">38.9<small>%</small></div>
  <div class=n>全体は 18.4%。人気薄なら 17.0%</div></div>
 <div class=tile><div class=k>その距離の実測が2走以上</div>
  <div class=v>4<small>/11頭</small></div>
  <div class=n>3R②（4走）・5R⑩（2走）・5R⑫（5走）・5R⑭（5走）</div></div>
</div>
<table><thead><tr><th>R</th><th>番</th><th>馬名 / 父</th>
<th>同距離の上がり</th><th>実測</th><th>馬体重</th><th>普段4角／3→4角</th>
<th>材料</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<footer>
その距離の実測が2走以上あるのは <b>3R②（4走）・5R⑩（2走）・5R⑫（5走）・5R⑭（5走）</b>。
ばらつきがいちばん小さいのは 3R②の <b>0.34</b>、次が 5R⑫の 0.52。
上がりがいちばん速いのは 5R⑩の <b>39.9</b>。<br>
前に行けるのは <b>4R⑦（普段4角1番手）</b>と <b>5R⑩（3番手）</b>。
押し上げがあるのは <b>5R①（+1.0）</b>と <b>5R⑩（+0.5）</b>。<br>
馬場は良で置いた。発走30分前にオッズで印を打ち直す。
</footer></body></html>'''
open(OUT, 'w', encoding='utf-8').write(HTML)
print('書き出し', OUT)
