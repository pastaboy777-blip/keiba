# -*- coding: utf-8 -*-
"""貼ってもらった馬のリストを、今年の大井の実測で当てて1枚にする。

  python3 scripts/ana/ooi_list_card.py <list.json> <日付> <out.html>

同距離帯の上がり・そのばらつき・実測の走数・馬体重・普段の4角位置・
3→4角・置き直した時計の鞍内順位と壁までの余裕を並べる。印はつけない。
"""
import html, json, sys

LIST, DAY, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
P = json.load(open(LIST, encoding='utf-8'))

WHY = {
 'グレートロッタリー':
   '1600mを4走して上がり 40.4・41.3・40.6・40.9。<b>0.9秒の幅に収まり、'
   'ばらつき0.34はこの11頭で最小</b>。<b>440kg</b>。'
   '壁まで<b>+0.30</b>で、今年 28.4% の条件に入る',
 'ムーンシェイド':
   '450kgで<b>普段4角1番手</b>。この11頭で唯一はっきり前に行ける。'
   '人気薄で4角3番手以内は <b>11.6%</b>（+2.4pt）。1600m→1200mの短縮。'
   '前走は1600mを1番人気3着',
 'アップタウンガール':
   '<b>上がり39.9はこの11頭で最速</b>。鞍内2位で壁まで<b>+0.30</b>、'
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

rows = []
for p in P:
    why = WHY.get(p['nm'], '')
    thin = p['nsd'] < 2
    ag = (f"{p['ag']:.1f}" if p['ag'] is not None
          else ('<span class=w>他距離</span>' if p['ag_other'] else '－'))
    sd = f"{p['sd']:.2f}" if p['sd'] is not None else '－'
    ark = f"{p['ark']}/{p['nar']}" if p.get('ark') else '－'
    rk = f"{p['rk']}/{p['nr']}" if p.get('rk') else '－'
    hrk = f"{p['hrk']}/{p['nr']}" if p.get('hrk') else '－'
    sl = f"{p['slack']:+.2f}" if p['slack'] is not None else '－'
    pos = f"{p['pos']:.1f}" if p['pos'] is not None else '－'
    g = f"{p['gain']:+.1f}" if p['gain'] is not None else '－'
    rows.append(
      f'<tr><td class=r>{p["R"]}R<br><span class=dm>{p["dist"]}m {p["n"]}頭</span></td>'
      f'<td class=u>{p["u"]}</td>'
      f'<td class=nm>{html.escape(p["nm"])}<span class=si>{html.escape(p["sire"])}</span></td>'
      f'<td class="sm{" dim" if thin else ""}">{ag}<br><span class=un>SD {sd}</span></td>'
      f'<td class=sm>{p["nsd"]}<span class=un>走</span><br>'
      f'<span class=un>全{p["nrun"]}走</span></td>'
      f'<td class=sm>{p["wt"] or "－"}<span class=un>kg</span></td>'
      f'<td class=sm>{pos}<span class=un>番手</span><br><span class=un>{g}</span></td>'
      f'<td class=big>{sl}</td>'
      f'<td class=rk>{rk}</td><td class=rk>{hrk}</td><td class=rk>{ark}</td>'
      f'<td class=why>{why}</td></tr>')

HTML = f'''<!doctype html><html lang=ja><head><meta charset=utf-8>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0a0a0a;color:#e8e6e3;font-family:"Hiragino Sans","Noto Sans JP",system-ui,sans-serif;
 padding:46px 54px 38px;width:2090px;-webkit-font-smoothing:antialiased}}
h1{{font-size:39px;font-weight:800}} h1 .ac{{color:#d95926}}
.tag{{display:inline-block;background:#d95926;color:#fff;font-size:15px;font-weight:700;
 padding:4px 12px;border-radius:5px;margin-left:14px;vertical-align:7px}}
.lead{{margin-top:17px;font-size:19px;line-height:1.85;color:#cfccc8;max-width:1880px}}
.lead b{{color:#fff}} .lead .hl{{color:#ff8a5c;font-weight:700}}
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
.r{{width:100px;color:#cfccc8;font-weight:700;font-size:17px;
 border-left:4px solid #3a3a36;padding-left:16px}}
.dm{{font-size:12px;color:#8e8a84;font-weight:500}}
.u{{width:48px;font-weight:800;font-size:24px;color:#e8e6e3}}
.nm{{width:352px;font-weight:800;font-size:32px;line-height:1.2;
 letter-spacing:.01em;white-space:nowrap}}
.si{{display:block;font-size:13px;font-weight:500;color:#8e8a84;margin-top:7px}}
.sm{{width:88px;color:#cfccc8;font-variant-numeric:tabular-nums;line-height:1.55;
 font-size:19px;font-weight:700;white-space:nowrap}}
.sm .un{{font-weight:500}}
.dim{{color:#5e5a54}}
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
<h1>{DAY} 大井 ── <span class=ac>上がり40の小型馬リストを当てた</span>
<span class=tag>今年の大井 927鞍で検証ずみ</span></h1>
<p class=lead>
貼ってもらった11頭を、今年の大井の実測で当てた。見るのは
<b>同じ距離帯の上がりとそのばらつき</b>、<b>馬体重</b>、<b>普段の4角位置</b>、
置き直した時計の<b>鞍内順位</b>と<b>壁までの余裕</b>。
<span class=hl>その距離の実測が2走以上あるのは4頭。</span>残りは走数が少ないので、上がりは参考に。
</p>
<div class=tiles>
 <div class=tile><div class=k>人気薄 × 鞍内3位以内</div><div class=v>20.3<small>%</small></div>
  <div class=n>人気薄ぜんぶは 9.3%</div></div>
 <div class=tile><div class=k>↑ かつ 壁まで0.3秒以上の余裕</div>
  <div class=v style="color:#d95926">28.4<small>%</small></div>
  <div class=n>壁とほぼ同値だと 18.7%</div></div>
 <div class=tile><div class=k>人気薄 × 普段4角3番手以内</div>
  <div class=v style="color:#3987e5">11.6<small>%</small></div>
  <div class=n>8番手以降は <b>7.5%</b>（−1.7pt）</div></div>
 <div class=tile><div class=k>3→4角で順位を上げる馬</div>
  <div class=v style="color:#c98500">30.2<small>%</small></div>
  <div class=n>+0.5〜1.0の押し上げで <b>+7.3pt</b></div></div>
</div>
<table><thead><tr><th>R</th><th>番</th><th>馬名 / 父</th>
<th>同距離の上がり</th><th>実測</th><th>馬体重</th><th>普段4角／3→4角</th>
<th>壁まで</th><th>鞍内</th><th>自前半</th><th>上がり順</th><th>材料</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<footer>
その距離の実測が2走以上あるのは <b>3R②（4走）・5R⑩（2走）・5R⑫（5走）・5R⑭（5走）</b>。
ばらつきがいちばん小さいのは 3R②の <b>0.34</b>、次が 5R⑫の 0.52。
上がりがいちばん速いのは 5R⑩の <b>39.9</b>。<br>
前に行けるのは <b>4R⑦（普段4角1番手）</b>と <b>5R⑩（3番手）</b>。押し上げがあるのは
<b>5R①（+1.0）</b>と <b>5R⑩（+0.5）</b>。<br>
今年の大井で測った水準 … 人気薄×鞍内3位以内 20.3%（人気薄ぜんぶ 9.3%）、
壁まで0.3秒以上の余裕があると 28.4%。普段4角3番手以内 11.6%。
3→4角で+0.5〜1.0の押し上げがあると 30.2%。<br>
馬場は良で置いた。発走30分前にオッズで印を打ち直す。
</footer></body></html>'''
open(OUT, 'w', encoding='utf-8').write(HTML)
print('書き出し', OUT)
