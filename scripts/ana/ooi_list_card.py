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
 'タイセイディエティ':
   '1200mを5走して上がり <b>38.4・39.3・39.5・39.0・38.3</b>。'
   '<b>中央39.0・ばらつき0.48</b>で、この9頭でいちばん速い。'
   '前走は1600mで、<b>1200mに戻る</b>。450kg',
 'ムービングアップ':
   '前走10/07の1200mで<b>上がり37.3</b>。6Rの出走馬でいちばん速い数字。'
   '1600mでは 3人2着・2人2着・2人3着と好走している。'
   '<b>3→4角+1.0</b>と押し上げる。479kg',
 'フタバサクセス':
   '1600mで上がり 40.0・39.6、<b>ばらつき0.20はこの9頭で最小</b>。'
   '前走1800mでは<b>上がり38.4で4着</b>。<b>3→4角+0.5</b>と押し上げる。449kg',
 'ノンフィクション':
   '1600mを4走して上がり <b>40.9・40.2・39.3・39.6</b>。'
   '9/02の1800mでは<b>38.4</b>を使えている。普段4角7.5番手。471kg',
 'ワールドフォンテン':
   '1600mを5走して <b>39.7・39.2・40.2・39.8・40.0</b>。'
   '<b>ばらつき0.34</b>で、直近3走が <b>1着・1着・4着</b>。'
   '普段4角4番手で位置も取れる。462kg',
 'マウリノ':
   '1600mで上がり 40.2・39.6。<b>普段4角2番手</b>でこの9頭でいちばん前。'
   '前走は1600mを4番人気<b>3着</b>（上がり39.6）。473kg',
 'エスプリワールド':
   '前走10/07の1400mで<b>上がり38.2</b>（8番人気4着）。'
   '良馬場の1400mでは <b>39.4・38.2</b> を使えている。'
   '普段4角5番手で位置も取れる。462kg',
 'モンサンヴデット':
   '1200mを5走して上がり <b>39.7・38.8・38.3・39.5・40.6</b>。'
   '6/09の1200mで<b>38.3を使って3着</b>、9/17も<b>39.5で2着</b>。'
   '普段4角8番手。465kg',
 'アクアジェット':
   '1600mを5走。<b>良馬場では 39.7・39.8・40.1</b>と安定している。'
   '普段4角7番手。464kg',
}

# 長い馬名は意味の切れ目で2行にする（数字は前半の文字数、0は折り返さない）
BREAK = {
    'イノセントワールド': 5, 'ユイノサンバンカン': 3, 'クリムゾンバースト': 5,
    'グレートロッタリー': 4, 'アップタウンガール': 6, 'カルサパラストリス': 3,
    'ヤッティライネン': 4, 'ムーンシェイド': 3, 'タイセイディエティ': 4,
    'ワールドフォンテン': 4, 'エスプリワールド': 4, 'モンサンヴデット': 4,
    'ディアローラ': 0, 'ウィルアトレ': 0, 'サラン': 0, 'クライスラー': 0,
    'フタバサクセス': 0, 'アクアジェット': 0, 'ヒンナ': 0,
    'ムービングアップ': 4, 'ノンフィクション': 4, 'マウリノ': 0,
}


def wrap(nm):
    k = BREAK.get(nm, 5 if len(nm) >= 9 else 0)
    if not k:
        return html.escape(nm)
    return html.escape(nm[:k]) + '<br>' + html.escape(nm[k:])


RS = sorted({p['R'] for p in P})
NR = len(RS)
OK2 = [p for p in P if p['nsd'] >= 2]
N2 = len(OK2)
LIST2 = '・'.join(f"{p['R']}R{chr(0x2460 + p['u'] - 1) if p['u'] <= 20 else p['u']}"
                 f"（{p['nsd']}走）" for p in OK2)
# レースごとの色（検証ずみの5色から順に）
PAL = ['#d95926', '#3987e5', '#199e70', '#c98500', '#d55181']
RCOL = {r: PAL[i % len(PAL)] for i, r in enumerate(RS)}

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
      f'<tr style="--rc:{RCOL[p["R"]]}"><td class=r>{p["R"]}<span class=rr>R</span>'
      f'<br><span class=dm>{p["dist"]}m</span></td>'
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

.r{{width:126px;color:var(--rc);font-weight:800;font-size:44px;line-height:1.05;
 border-left:6px solid var(--rc);padding-left:18px;font-variant-numeric:tabular-nums}}
.rr{{font-size:26px;color:var(--rc);opacity:.6;margin-left:3px}}
.dm{{display:inline-block;margin-top:9px;font-size:17px;color:#8e8a84;font-weight:600}}
.u{{width:76px;font-weight:800;font-size:44px;color:#e8e6e3;line-height:1.05;
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
  <div class=v>{N2}<small>/{len(P)}頭</small></div>
  <div class=n>{LIST2}</div></div>
</div>
<table><thead><tr><th>R</th><th>番</th><th>馬名 / 父</th>
<th>同距離の上がり</th><th>実測</th><th>馬体重</th><th>普段4角／3→4角</th>
<th>材料</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<footer>
ばらつきがいちばん小さいのは <b>7R①（0.20）</b>、次が <b>7R⑥（0.34）</b>と <b>6R①（0.48）</b>。
上がりがいちばん速いのは <b>6R①の39.0</b>。<br>
前に行けるのは <b>7R⑨（普段4角2番手）</b>と <b>7R⑥（4番手）</b>。
押し上げがあるのは <b>6R⑬（+1.0）</b>と <b>7R①（+0.5）</b>。<br>
7R⑥は<b>1600mを5走して直近3走が1着・1着・4着</b>、この9頭で実測がいちばん厚い。<br>8R⑩は前走1400mで<b>上がり38.2</b>、良馬場に限れば 39.4・38.2。9R⑩は1200mで<b>38.3で3着・39.5で2着</b>の実績。<br>
馬場は良で置いた。発走30分前にオッズで印を打ち直す。
</footer></body></html>'''
open(OUT, 'w', encoding='utf-8').write(HTML)
print('書き出し', OUT)
