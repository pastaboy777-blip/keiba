# -*- coding: utf-8 -*-
"""貼ってもらった馬のリストを、選んだ条件の実測だけで並べる。

  python3 scripts/ana/ooi_list_card.py <list.json> <日付> <out.html>

並べるのは 同じ距離帯の上がり／そのばらつき／その距離の走数／馬体重と
鞍の中央との差／父／普段の4角位置／3角→4角。印はつけない。
"""
import html, json, sys

LIST, DAY, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
P = json.load(open(LIST, encoding='utf-8'))

# 推す理由／推せない理由。数字から読めることだけ書く
WHY = {
 'グレートロッタリー':
   ('推す', '#d95926',
    '1600mを4走して上がり 40.4・41.3・40.6・40.9。<b>0.9秒の幅に収まっていて'
    'ばらつき0.34はこの11頭で最小</b>。440kgは鞍の中央より39kg軽い。'
    '貼ってもらった条件のうち<b>体重と上がりの安定が両方そろう唯一の馬</b>。'
    'ただし普段4角11番手で、前に行く形ではない'),
 'カルサパラストリス':
   ('推す', '#d95926',
    '<b>1600mを5走、ばらつき0.52</b>で材料がいちばん厚い。上がり40.1は11頭で2番目に速く、'
    '445kgで鞍の中央より36kg軽い。普段4角6番手・3→4角±0で位置は中団のまま。'
    '条件に合うが<b>前に出る動きはない</b>'),
 'ムーンシェイド':
   ('位置だけ', '#3987e5',
    '450kgで<b>普段4角1番手</b>。この11頭で唯一、はっきり前に行ける。'
    '1600m→1200mの短縮。ただし<b>大井は1走だけ</b>で、その1走も1600m。'
    '1200mの上がりもばらつきも出せない'),
 'アップタウンガール':
   ('振れる', '#c98500',
    '上がり39.9は11頭で最速、普段4角3番手で3→4角も+0.5と動く。'
    'ただし<b>1600mは2走だけでばらつき1.35</b>。'
    '11頭でいちばん振れる数字で、40秒を切ったのは1本だけ'),
 'ユイノサンバンカン':
   ('合わない', '#8e8a84',
    '1600mを5走、上がり40.6・ばらつき0.92。462kgは鞍の中央より19kg軽いだけで'
    '<b>小型とは言いにくい</b>。上がりも11頭で遅い側'),
 'ヤッティライネン':
   ('距離が違う', '#8e8a84',
    '443kgの小型で10走ぶんの実測があるが、<b>上がり38.0〜39.9はすべて1200mのもの</b>。'
    '1600mは未経験で、この条件では測れない'),
 'クリムゾンバースト':
   ('測れない', '#8e8a84', '大井は1走だけ（1600mで上がり40.4）。1200mは未経験'),
 'ウィルアトレ': ('測れない', '#8e8a84', '大井は1走だけ。1400mは未経験'),
 'イノセントワールド':
   ('測れない', '#8e8a84', '大井は1走だけ。452kgで普段4角4番手だが、1400mの実測はゼロ'),
 'ディアローラ': ('測れない', '#8e8a84', '大井の実測がゼロ'),
 'サラン': ('測れない', '#8e8a84', '大井の実測がゼロ'),
}

rows = []
for p in P:
    tag, c, why = WHY.get(p['nm'], ('', '#8e8a84', ''))
    thin = p['nsd'] < 2
    ag = f"{p['ag']:.1f}" if p['ag'] is not None else '－'
    sd = f"{p['sd']:.2f}" if p['sd'] is not None else '－'
    pos = f"{p['pos']:.0f}" if p['pos'] is not None else '－'
    g = f"{p['gain']:+.1f}" if p['gain'] is not None else '－'
    dw = f"{p['dw']:+d}" if p['dw'] is not None else ''
    rows.append(
      f'<tr style="--c:{c}"><td class=r>{p["R"]}R<br><span class=dm>{p["dist"]}m</span></td>'
      f'<td class=u>{p["u"]}</td>'
      f'<td class=nm>{html.escape(p["nm"])}'
      f'<span class=si>{html.escape(p["sire"])}</span></td>'
      f'<td class="ag{" dim" if thin else ""}">{ag}</td>'
      f'<td class=sd>{sd}</td>'
      f'<td class="rn{" dim" if thin else ""}">{p["nsd"]}<span class=un>走</span></td>'
      f'<td class=wt>{p["wt"] or "－"}<span class=un>kg</span>'
      f'<span class=dwv>{dw}</span></td>'
      f'<td class=po>{pos}<span class=un>番手</span></td>'
      f'<td class=gn>{g}</td>'
      f'<td class=tg>{tag}</td><td class=why>{why}</td></tr>')

HTML = f'''<!doctype html><html lang=ja><head><meta charset=utf-8>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0a0a0a;color:#e8e6e3;font-family:"Hiragino Sans","Noto Sans JP",system-ui,sans-serif;
 padding:52px 62px 44px;width:2060px;-webkit-font-smoothing:antialiased}}
h1{{font-size:38px;font-weight:800}} h1 .ac{{color:#d95926}}
.lead{{margin-top:13px;font-size:17px;line-height:1.75;color:#8e8a84}}
table{{width:100%;border-collapse:collapse;margin-top:26px}}
th{{font-size:13px;color:#8e8a84;font-weight:500;text-align:left;padding:0 13px 10px;
 border-bottom:1px solid #262622}}
td{{padding:19px 13px;border-bottom:1px solid #1d1d1a;vertical-align:middle}}
.r{{width:94px;color:#8e8a84;font-weight:700;font-size:17px;line-height:1.4;
 border-left:4px solid var(--c);padding-left:14px}}
.dm{{font-size:13px;font-weight:500}}
.u{{width:52px;font-weight:800;font-size:27px}}
.nm{{width:304px;font-weight:800;font-size:29px;letter-spacing:.01em;line-height:1.2}}
.si{{display:block;font-size:13px;font-weight:500;color:#8e8a84;margin-top:6px}}
.ag{{width:104px;font-size:28px;font-weight:800;font-variant-numeric:tabular-nums}}
.sd{{width:92px;font-size:20px;color:#b5b1ab;font-variant-numeric:tabular-nums}}
.rn{{width:78px;font-size:19px;color:#b5b1ab;font-variant-numeric:tabular-nums}}
.dim{{color:#4e4a45}}
.wt{{width:118px;font-size:22px;font-weight:700;font-variant-numeric:tabular-nums}}
.dwv{{display:block;font-size:14px;color:#8e8a84;font-weight:500;margin-top:4px}}
.po{{width:96px;font-size:21px;font-weight:700;font-variant-numeric:tabular-nums;color:#cfccc8}}
.gn{{width:80px;font-size:19px;color:#b5b1ab;font-variant-numeric:tabular-nums}}
.un{{font-size:13px;color:#8e8a84;margin-left:3px;font-weight:500}}
.tg{{width:86px;font-size:15px;font-weight:800;color:var(--c);white-space:nowrap}}
.why{{color:#cfccc8;font-size:15px;line-height:1.72}}
.why b{{color:#fff}}
footer{{margin-top:30px;padding-top:21px;border-top:1px solid #262622;
 font-size:16px;line-height:1.9;color:#a5a19b}}
footer b{{color:#fff}}
</style></head><body>
<h1>{DAY} 大井 ── <span class=ac>11頭の実測</span></h1>
<p class=lead>上がりは同じ距離帯の直近5走の中央値、ばらつきはその標準偏差。走数はその距離の実測。
馬体重は直近3走の中央値で、下はその鞍の中央との差。3→4角はプラスが押し上げ。</p>
<table><thead><tr><th>R</th><th>番</th><th>馬名 / 父</th>
<th>上がり</th><th>ばらつき</th><th>走数</th><th>馬体重</th><th>普段4角</th><th>3→4角</th><th></th><th>理由</th>
</tr></thead><tbody>{''.join(rows)}</tbody></table>
<footer>
<b>11頭のうち7頭は、その距離の実測が0〜1走</b>で上がりもばらつきも出せない。
<b>5R①ヤッティライネンの上がりは全部1200mのもの</b>で、今回の1600mは未経験。<br>
2走以上あるのは 3R②（4走）・5R⑩（2走）・5R⑫（5走）・5R⑭（5走）。
ばらつきがいちばん小さいのは 3R② の <b>0.34</b>、次が 5R⑫ の 0.52。
</footer></body></html>'''
open(OUT, 'w', encoding='utf-8').write(HTML)
print('書き出し', OUT)
