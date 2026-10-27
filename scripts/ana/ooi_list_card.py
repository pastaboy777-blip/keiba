# -*- coding: utf-8 -*-
"""貼ってもらった馬のリストを、今年の大井の実測で当てて1枚にする。

  python3 scripts/ana/ooi_list_card.py <list.json> <日付> <out.html>

同距離帯の上がり・そのばらつき・馬体重・普段の4角位置・3→4角・
置き直した時計の鞍内順位を並べ、材料の足りない馬はそう書く。
"""
import html, json, sys

LIST, DAY, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
P = json.load(open(LIST, encoding='utf-8'))

NOTE = {
 'グレートロッタリー': ('', '#3a3a36',
   '<b>上がり40.8・SD0.34</b>で4走とも40.4〜41.3の0.9秒幅。440kgで鞍の中央より'
   '<b>−39kg</b>。壁まで<b>+0.30</b>で条件（28.4%）を満たす。'
   '<span class=w>ただし普段4角11番手</span>で位置がない'),
 'ムーンシェイド': ('', '#3a3a36',
   '450kgで<b>普段4角1番手</b>。人気薄で4角3番手以内は 11.6%（+2.4pt）。'
   '1600m→1200mの短縮。<span class=w>父ビッグアーサーは今年の人気薄で 0/27</span>。'
   '前走1人気3着で人気も被る'),
 'アップタウンガール': ('', '#3a3a36',
   '<b>鞍内2位・壁まで+0.30</b>、普段4角3.0番手で3→4角も+0.5。'
   '<span class=w>ただし1600mは2走だけでSD1.35</span>と振れる。直近2.5番人気で妙味は薄い'),
 'カルサパラストリス': ('', '#3a3a36',
   '<b>1600mを5走してSD0.52</b>、上がり40.1は安定している。445kgで−36kg。'
   '<span class=w>自前半12/13</span>で前に行けず、壁まで−0.10'),
 'ヤッティライネン': ('', '#3a3a36',
   '直近5走の上がり38.0〜39.9は<span class=w>すべて1200m</span>で、1600mは未経験。'
   '鞍内6/13・自前半7/13・壁まで−0.30。443kgの小型だが時計が足りない'),
 'ユイノサンバンカン': ('', '#3a3a36',
   '上がり40.6・SD0.92。<b>鞍内7/13・自前半9/13・壁まで−0.50</b>。'
   '直近12番人気で、この層は今年 9.4%'),
 'クリムゾンバースト': ('', '#3a3a36',
   '大井は1走だけ（1600mで上がり40.4）。1200mは未経験で、SDも出せない。'
   '体重466kg・普段4角6番手はどちらも中位'),
 'ウィルアトレ': ('', '#3a3a36', '大井1走のみ。1400mは未経験で上がりが測れない'),
 'イノセントワールド': ('', '#3a3a36',
   '大井1走のみ。452kgで普段4角4番手だが、1400mの実測はゼロ'),
 'ディアローラ': ('', '#3a3a36', '<b>大井の実測がゼロ</b>。何も測れない'),
 'サラン': ('', '#3a3a36', '<b>大井の実測がゼロ</b>。何も測れない'),
}

rows = []
for p in P:
    mk, c, why = NOTE.get(p['nm'], ('', '#3a3a36', ''))
    ag = (f"{p['ag']:.1f}" if p['ag'] is not None
          else ('<span class=w>他距離</span>' if p['ag_other'] else '－'))
    sd = f"{p['sd']:.2f}" if p['sd'] is not None else '－'
    ark = f"{p['ark']}/{p['nar']}" if p.get('ark') else '－'
    rk = f"{p['rk']}/{p['nr']}" if p.get('rk') else '－'
    hrk = f"{p['hrk']}/{p['nr']}" if p.get('hrk') else '－'
    sl = f"{p['slack']:+.2f}" if p['slack'] is not None else '－'
    pos = f"{p['pos']:.1f}" if p['pos'] is not None else '－'
    g = f"{p['gain']:+.1f}" if p['gain'] is not None else '－'
    dw = (f"<span class=un>{p['dw']:+d}</span>" if p['dw'] is not None else '')
    rows.append(
      f'<tr style="--c:{c}">'
      f'<td class=r2>{p["R"]}R<br><span class=dm>{p["dist"]}m {p["n"]}頭</span></td>'
      f'<td class=u>{p["u"]}</td>'
      f'<td class=nm>{html.escape(p["nm"])}<span class=si>{html.escape(p["sire"])}</span></td>'
      f'<td class=sm>{ag}<br><span class=un>SD {sd}</span></td>'
      f'<td class=sm>{p["nsd"]}<span class=un>走</span><br>'
      f'<span class=un>全{p["nrun"]}走</span></td>'
      f'<td class=sm>{p["wt"] or "－"}<span class=un>kg</span><br>{dw}</td>'
      f'<td class=sm>{pos}<span class=un>番手</span><br><span class=un>{g}</span></td>'
      f'<td class=big>{sl}</td>'
      f'<td class=rk>{rk}</td><td class=rk>{hrk}</td><td class=rk>{ark}</td>'
      f'<td class=why>{why}</td></tr>')

HTML = f'''<!doctype html><html lang=ja><head><meta charset=utf-8>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0a0a0a;color:#e8e6e3;font-family:"Hiragino Sans","Noto Sans JP",system-ui,sans-serif;
 padding:46px 54px 38px;width:2000px;-webkit-font-smoothing:antialiased}}
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
.mk{{width:44px;font-size:21px;font-weight:800;color:var(--c);
 border-left:4px solid var(--c);padding-left:14px}}
.r2{{width:94px;color:#cfccc8;font-weight:700;font-size:17px;
 border-left:4px solid var(--c);padding-left:14px}}
.dm{{font-size:12px;color:#8e8a84;font-weight:500}}
.u{{width:44px;font-weight:800;font-size:22px;color:#e8e6e3}}
.nm{{font-weight:700;font-size:18px;width:198px}}
.si{{display:block;font-size:12px;font-weight:500;color:#8e8a84;margin-top:4px}}
.sm{{width:84px;color:#cfccc8;font-variant-numeric:tabular-nums;line-height:1.55}}
.un{{font-size:12px;color:#8e8a84}}
.big{{width:86px;font-size:21px;font-weight:800;font-variant-numeric:tabular-nums;color:#cfccc8}}
.rk{{width:62px;color:#b5b1ab;font-variant-numeric:tabular-nums;font-size:15px}}
.why{{color:#cfccc8;font-size:15px;line-height:1.72}}
.why b{{color:#fff}} .why .w{{color:#c98500;font-weight:700}}
.sm .w{{color:#c98500;font-weight:700;font-size:13px}}
footer{{margin-top:30px;padding-top:20px;border-top:1px solid #262622;
 font-size:15px;line-height:1.85;color:#a5a19b}}
footer b{{color:#fff}} footer .hl{{color:#ff8a5c;font-weight:700}}
</style></head><body>
<h1>{DAY} 大井 ── <span class=ac>貼ってもらった11頭の実測</span>
<span class=tag>今年の大井 927鞍で検証ずみ</span></h1>
<p class=lead>
貼ってもらった11頭を、今年の大井の実測で当てた。見るのは
<b>同じ距離帯の上がりとそのばらつき</b>、<b>馬体重</b>、<b>普段の4角位置</b>、
置き直した時計の<b>鞍内順位</b>と<b>壁までの余裕</b>。
<span class=hl>11頭のうち7頭は、その距離の実測が足りず上がりが測れない。</span>
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
 <div class=tile><div class=k>3→4角で順位を下げる馬</div>
  <div class=v style="color:#6e6a64">16.1<small>%</small></div>
  <div class=n>全馬で −6.8pt。<b>下げる馬は外す</b></div></div>
</div>
<table><thead><tr><th>R</th><th>番</th><th>馬名 / 父</th>
<th>同距離の上がり</th><th>実測</th><th>馬体重</th><th>普段4角／3→4角</th>
<th>壁まで</th><th>鞍内</th><th>自前半</th><th>上がり順</th><th>材料</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<footer>
<b>11頭のうち7頭は、その距離の実測が0〜1走。</b>1R④⑤⑦・3R⑩・4R⑨は上がりもばらつきも出せない。
<b>5R①ヤッティライネンの上がり38.0〜39.9は全部1200mのもので、今回の1600mは未経験。</b><br>
その距離の実測が2走以上あるのは <b>3R②（4走）・5R⑩（2走）・5R⑫（5走）・5R⑭（5走）</b> の4頭。
ばらつきがいちばん小さいのは 3R②の <b>SD 0.34</b>、次が 5R⑫の 0.52。<br>
今年の大井で測った水準 … 人気薄×鞍内3位以内 20.3%（人気薄ぜんぶ 9.3%）、
壁まで0.3秒以上の余裕があると 28.4%、壁と同値だと 18.7%。
普段4角3番手以内 11.6%／8番手以降 7.5%。3→4角で下げる馬は全馬で −6.8pt。<br>
馬場は良で置いた。発走30分前にオッズで印を打ち直す。
</footer></body></html>'''
open(OUT, 'w', encoding='utf-8').write(HTML)
print('書き出し', OUT)
