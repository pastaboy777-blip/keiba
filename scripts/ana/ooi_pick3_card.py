# -*- coding: utf-8 -*-
"""3条件に合った馬を1枚にする。

  python3 scripts/ana/ooi_pick3_card.py <pick3b.json> <日付> <out.html>

載せるのは買う側だけ。印はつけない。
"""
import html, json, sys

SRC, DAY, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
P = json.load(open(SRC, encoding='utf-8'))

# 直近3走の人気が6番人気以下なら、検証した層に入る
ANA = [x for x in P if x['pop3'] and x['pop3'] >= 6 and (x['trend'] or 0) > -0.5]
NIN = [x for x in P if not (x['pop3'] and x['pop3'] >= 6)
       and (x['trend'] or 0) > -0.5]

WHY = {
 'サブノリョウマ':
   '同じ1200mで上がり <b>37.7・38.9・37.5・38.0・37.5</b>。'
   '<b>10/9の37.5</b>はこの距離で最速の部類。粘りの向きが <b>+1.30</b> で'
   'この9頭の最大。馬体重も <b>461→466→464→470→472kg</b> と増え続けている',
 'リケアミネオラ':
   '1600mで <b>5着・5着・3着・5着・5着</b>。掲示板を外していない。'
   '上がりは 38.9・40.6・39.5・39.1・39.7 で、ふだん4角6番手から'
   '<b>下げずに運べる</b>。426kgの小型',
 'ミユンガー':
   '同じ1200mで <b>38.6・39.5・39.3・39.1・38.8</b>、'
   '<b>ばらつき0.33</b>はこの9頭で最小。ふだん4角4番手で'
   '位置を取りにいける。479kgで体重も動かない',
 'リバイブメイラード':
   'ふだん4角5番手から <b>3→4角で1つ押し上げる</b>。'
   '直近5走が 1着・3着・6着・4着・3着。452kg',
 'ジーティーマジカル':
   '上がり <b>38.8・39.0・38.1・39.1・39.7</b>。'
   'ふだん4角4番手で下げない。510kgの大型',
 'ペルセイズ':
   '上がり <b>38.7・38.8・38.9・37.9・38.0</b> と、'
   '直近2走でひと声速くなっている。ふだん4角<b>2.0番手</b>。513kg',
 'メイショウアキカゼ':
   '上がり <b>37.8・38.4・37.4・37.6・37.3</b>。'
   '<b>5走のうち4走が37秒台</b>でそろう。ふだん4角4番手。前走1着。486kg',
}
BREAK = {'サブノリョウマ': 4, 'リケアミネオラ': 4, 'ミユンガー': 0,
         'リバイブメイラード': 5, 'ジーティーマジカル': 5,
         'ペルセイズ': 0, 'メイショウアキカゼ': 5}
PAL = ['#d95926', '#3987e5', '#199e70', '#c98500', '#d55181']
RS = sorted({x['R'] for x in P})
RCOL = {r: PAL[i % len(PAL)] for i, r in enumerate(RS)}


def wrap(nm):
    k = BREAK.get(nm, 5 if len(nm) >= 9 else 0)
    return (html.escape(nm) if not k
            else html.escape(nm[:k]) + '<br>' + html.escape(nm[k:]))


def rows(v):
    out = ''
    for x in v:
        c = RCOL[x['R']]
        tr = f"{x['trend']:+.2f}" if x['trend'] is not None else '－'
        up = ' up' if (x['trend'] or 0) > 0 else ''
        out += (
          f'<tr style="--rc:{c}"><td class=r>{x["R"]}<span class=rr>R</span>'
          f'<br><span class=dm>{x["dist"]}m {x["n"]}頭</span></td>'
          f'<td class=u>{x["u"]}</td>'
          f'<td class=nm>{wrap(x["nm"])}'
          f'<span class=si>{html.escape(x["sire"])}</span></td>'
          f'<td class=sd>{x["sd"]:.2f}<br><span class=un>{x["nag"]}走</span></td>'
          f'<td class=po>{x["pos"]:.1f}<span class=un>番手</span><br>'
          f'<span class=un>3→4角 {x["gain"]:+.1f}</span></td>'
          f'<td class="tr{up}">{tr}</td>'
          f'<td class=wt>{x["wt"]}<span class=un>kg</span></td>'
          f'<td class=why>{WHY.get(x["nm"], "")}</td></tr>')
    return out


HTML = f'''<!doctype html><html lang=ja><head><meta charset=utf-8>
<title>3条件に合った馬</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0a0a0a;color:#e8e6e3;font-family:"Hiragino Sans","Noto Sans JP",system-ui,sans-serif;
 padding:46px 54px 38px;width:1960px;-webkit-font-smoothing:antialiased}}
h1{{font-size:44px;font-weight:800}} h1 .ac{{color:#d95926}}
.tag{{display:inline-block;background:#d95926;color:#fff;font-size:15px;font-weight:700;
 padding:4px 12px;border-radius:5px;margin-left:16px;vertical-align:9px}}
.lead{{margin-top:16px;font-size:18px;line-height:1.85;color:#cfccc8;max-width:1760px}}
.lead b{{color:#fff}} .lead .hl{{color:#ff8a5c;font-weight:700}}
.tiles{{display:grid;grid-template-columns:repeat(4,1fr);gap:15px;margin:26px 0 8px}}
.tile{{background:#141412;border:1px solid #262622;border-radius:10px;padding:17px 19px}}
.tile .k{{font-size:13px;color:#8e8a84}}
.tile .v{{font-size:38px;font-weight:800;margin-top:5px;line-height:1}}
.tile .v small{{font-size:18px;color:#8e8a84;margin-left:5px}}
.tile .n{{font-size:13px;color:#8e8a84;margin-top:8px;line-height:1.55}}
h2{{font-size:27px;font-weight:800;margin:36px 0 2px}}
h2 small{{font-size:15px;font-weight:500;color:#8e8a84;margin-left:14px}}
table{{width:100%;border-collapse:collapse;margin-top:12px}}
th{{font-size:12px;color:#8e8a84;font-weight:500;text-align:left;padding:0 10px 8px;
 border-bottom:1px solid #262622}}
td{{padding:17px 10px;border-bottom:1px solid #1d1d1a;font-size:16px;vertical-align:top}}
tr:nth-child(odd) td{{background:#0e0e0d}}
.r{{width:132px;color:#fff;font-weight:800;font-size:46px;line-height:1.05;
 border-left:6px solid var(--rc);padding-left:18px;font-variant-numeric:tabular-nums}}
.rr{{font-size:26px;opacity:.6;margin-left:3px}}
.dm{{display:inline-block;margin-top:9px;font-size:16px;color:#8e8a84;
 font-weight:600;white-space:nowrap}}
.u{{width:80px;font-weight:800;font-size:46px;line-height:1.05;
 font-variant-numeric:tabular-nums}}
.nm{{width:272px;font-weight:800;font-size:33px;line-height:1.24}}
.si{{display:block;font-size:13px;font-weight:500;color:#8e8a84;margin-top:8px}}
.sd{{width:104px;color:#d95926;font-size:26px;font-weight:800;line-height:1.5;
 font-variant-numeric:tabular-nums}}
.po{{width:124px;color:#3987e5;font-size:24px;font-weight:800;line-height:1.5;
 font-variant-numeric:tabular-nums;white-space:nowrap}}
.tr{{width:104px;color:#8e8a84;font-size:24px;font-weight:800;
 font-variant-numeric:tabular-nums}}
.tr.up{{color:#199e70}}
.wt{{width:112px;color:#c98500;font-size:24px;font-weight:800;
 font-variant-numeric:tabular-nums;white-space:nowrap}}
.un{{font-size:12.5px;color:#8e8a84;font-weight:500;margin-left:3px}}
.why{{color:#cfccc8;font-size:15.5px;line-height:1.75}}
.why b{{color:#fff}}
footer{{margin-top:34px;padding-top:22px;border-top:1px solid #262622;
 font-size:16px;line-height:1.9;color:#a5a19b}}
footer b{{color:#fff}} footer .hl{{color:#ff8a5c;font-weight:700}}
</style></head><body>
<h1>{DAY} 大井　<span class=ac>3条件に合った馬</span>
<span class=tag>今年の大井 人気薄6,394頭で検証</span></h1>
<p class=lead>
① 同じ距離帯の直近5走で<b>上がりのばらつきが0.6未満</b>
② <b>ふだんの4角が7番手以内</b>
③ <b>3角→4角で下げない</b>。<br>
この3つがそろうと、人気薄の3着内が <b>9.0% → 16.1%</b>、複勝の回収が
<b>61% → 87%</b>。<span class=hl>渋った日ならさらに +5.3pt</span>。
粘りの向きは直近2走と、その前3走の差。
</p>
<div class=tiles>
 <div class=tile><div class=k>3条件がそろう</div>
  <div class=v style="color:#d95926">16.1<small>%</small></div>
  <div class=n>複勝の回収 87%（267頭）</div></div>
 <div class=tile><div class=k>人気薄ぜんぶ</div>
  <div class=v>9.0<small>%</small></div>
  <div class=n>複勝の回収 61%（6,394頭）</div></div>
 <div class=tile><div class=k>ばらつき0.6未満 × 渋った日</div>
  <div class=v style="color:#c98500">15.2<small>%</small></div>
  <div class=n>この開催は4日のうち3日が<b>時計の出ない側</b></div></div>
 <div class=tile><div class=k>明日の該当</div>
  <div class=v style="color:#199e70">{len(P)}<small>/128頭</small></div>
  <div class=n>粘りが上を向いている <b>{len(ANA)+len(NIN)}頭</b>を載せた。
   うち直近6番人気以下が <b>{len(ANA)}頭</b></div></div>
</div>

<h2>直近6番人気以下<small>検証した層。ここがいちばん効く</small></h2>
<table><thead><tr><th>R</th><th>番</th><th>馬名 / 父</th><th>ばらつき</th>
<th>ふだん4角</th><th>粘りの向き</th><th>馬体重</th><th>材料</th></tr></thead>
<tbody>{rows(ANA)}</tbody></table>

<h2>直近5番人気以内<small>同じ3条件に合うが、この層では検証していない</small></h2>
<table><thead><tr><th>R</th><th>番</th><th>馬名 / 父</th><th>ばらつき</th>
<th>ふだん4角</th><th>粘りの向き</th><th>馬体重</th><th>材料</th></tr></thead>
<tbody>{rows(NIN)}</tbody></table>

<footer>
<b>人気は直近3走のもの。</b>明日のオッズで変わるので、発走前に見直す。<br>
<b>128頭のうち59頭は、大井での走りが足りず判定できない。</b>他場やJRAから来た馬と、
キャリアの浅い馬。南関4場のデータが入ったので、次の開催からここは埋まる。<br>
この開催の馬場は 10/26 +0.71／10/27 +0.09／10/28 +0.55／10/29 +0.51 で、
<b>4日のうち3日が時計の出ない側</b>。同じなら、ばらつきの小さい馬に追い風。
</footer></body></html>'''
open(OUT, 'w', encoding='utf-8').write(HTML)
print('書き出し', OUT, f'／ 人気薄{len(ANA)}頭・人気側{len(NIN)}頭')
