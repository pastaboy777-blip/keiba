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
 'スマイルケイ':
   '母父<b>クロフネ</b>。1200mを5走して上がり <b>38.3・38.4・38.8・38.4・39.4</b>、'
   '<b>ばらつき0.39</b>でこの5頭で最小。普段4角5番手で前走は<b>4角1番手</b>。486kg',
 'アレスグート':
   '父<b>マインドユアビスケッツ</b>。1600mで上がり <b>38.7・37.6・38.2・39.0</b>、'
   '<b>37.6はこの5頭で最速</b>。普段4角4番手で<b>3→4角も押し上げる走りがある</b>。479kg',
 'アーススピリット':
   '父<b>マインドユアビスケッツ</b>。2400mは初めてだが、直近5走で'
   '<b>4角11→5→6→2→8番手</b>と位置を取りにいっている。543kgの大型',
 'ラストラブラブ':
   '母父<b>クロフネ</b>。直近5走の4角が <b>1・1・2・2・1番手</b>で、'
   'この5頭で<b>いちばん前に行ける</b>。482kgで体重も安定',
 'オーサムデアラー':
   '父<b>マインドユアビスケッツ</b>。普段4角11番手で後ろから。'
   '484kgで体重は安定している',
}

# 長い馬名は意味の切れ目で2行にする（数字は前半の文字数、0は折り返さない）
BREAK = {
    'イノセントワールド': 5, 'ユイノサンバンカン': 3, 'クリムゾンバースト': 5,
    'グレートロッタリー': 4, 'アップタウンガール': 6, 'カルサパラストリス': 3,
    'ヤッティライネン': 4, 'ムーンシェイド': 3, 'タイセイディエティ': 4,
    'ワールドフォンテン': 4, 'エスプリワールド': 4, 'モンサンヴデット': 4,
    'ディアローラ': 0, 'ウィルアトレ': 0, 'サラン': 0, 'クライスラー': 0,
    'フタバサクセス': 0, 'アクアジェット': 0, 'ヒンナ': 0,
    'ムービングアップ': 4, 'スマイルケイ': 0, 'アレスグート': 0,
    'アーススピリット': 4, 'ラストラブラブ': 4, 'オーサムデアラー': 4, 'ノンフィクション': 4, 'マウリノ': 0,
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
<p class=lead>今日の大井（重）で <b>Deputy Minister 系</b>が浮いている。
クロフネ・マインドユアビスケッツ・フレンチデピュティは、すべてこの系統。
上がりは同じ距離帯の直近5走の中央値、ばらつきはその標準偏差。馬体重は直近3走の中央値。</p>
<div class=tiles>
 <div class=tile><div class=k>今日ここまで（4鞍）</div>
  <div class=v style="color:#d95926">3<small>/6頭</small></div>
  <div class=n>出走42頭中6頭しかいないのに、3着内12頭のうち3頭</div></div>
 <div class=tile><div class=k>今年の大井・重／不良</div>
  <div class=v style="color:#d95926">29.5<small>%</small></div>
  <div class=n>ほかの馬は 25.7%（156頭）</div></div>
 <div class=tile><div class=k>↑ かつ 6番人気以下</div>
  <div class=v style="color:#c98500">14.6<small>%</small></div>
  <div class=n>ほかの馬は 10.0%（89頭）</div></div>
 <div class=tile><div class=k>良・稍重だと</div>
  <div class=v style="color:#6e6a64">6.7<small>%</small></div>
  <div class=n>ほかの馬 8.6%。<b>渋った日だけの材料</b></div></div>
</div>
<table><thead><tr><th>R</th><th>番</th><th>馬名 / 父</th>
<th>同距離の上がり</th><th>実測</th><th>馬体重</th><th>普段4角／3→4角</th>
<th>材料</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<footer>
今日ここまでの3着内 … <b>1R③ソーラウィンド（父マインドユアビスケッツ）</b>、
<b>2R②ウズ（母父クロフネ）</b>、<b>4R③ベルベットオニキス（母父クロフネ）</b>。
3R④グレートロッタリー（母父フレンチデピュティ）も4着。<br>
<b>6R〜8Rにはこの系統がいない。</b>9R以降の5頭が残り。<br>
12Rに3頭集まるが、2400mは今年53鞍しかなく時計の裏づけが薄い。
9R⑤と11R⑧はその距離の実測が4〜5走ある。<br>
母数は重・不良の人気薄で89頭・13的中。これ一本ではなく、上がりや位置と重ねて使う。
</footer></body></html>'''
open(OUT, 'w', encoding='utf-8').write(HTML)
print('書き出し', OUT)
