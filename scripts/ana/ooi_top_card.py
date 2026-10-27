# -*- coding: utf-8 -*-
"""自信のある数頭を1枚にする。

  python3 scripts/ana/ooi_top_card.py <top.json> <日付> <out.html>

点のつけ方は今年の大井の実測から。鞍内1位 55.7%、自前半も3位以内で
61.8%、2位との差が0.5秒以上なら 72.9%。コーナーは「下げる馬を外す」
ために使う（3→4角がマイナスの馬は全馬で −6.8pt）。
"""
import html, json, sys

TOP, DAY, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
T = json.load(open(TOP, encoding='utf-8'))

WHY = {
 'ブルーキャット': ('今日いちばん堅い',
   '<b>鞍内1位・自前半1位</b>で、2位との差 <b>+0.40</b> はこの日の最大。'
   '14頭立てでそれをやっている。普段4角<b>2.0番手</b>で位置も取れる。'
   '見込み1位×自前半3位以内は今年 <b>61.8%</b>・勝ち29.0%'),
 'ワールドフォンテン': ('材料がいちばん厚い',
   '<b>鞍内1位・自前半2位・上がり2位</b>。<b>13走ぶんの実測</b>があり、'
   'この6頭で材料が最も厚い。普段4角4.0番手で位置も取れる。457kgの小型寄り'),
 'ナムラソラン': ('14頭立てで両方1位',
   '<b>鞍内1位、上がりも14頭中1位</b>。この日で両方1位はここだけ。'
   '2位との差+0.30。443kgで普段4角6.0番手。配当が付くなら狙い目'),
 'ココミサイル': ('脚はあるが位置がない',
   '<b>鞍内1位・上がり1位・壁まで+0.60</b>。'
   'ただし<span class=w>普段4角8.0番手</span>で後ろ。'
   '人気薄では8番手以降が 7.5%（−1.7pt）。そこは割り引く'),
 'トンスケ': ('7頭立ての小頭数',
   '<b>鞍内1位・自前半2位</b>、2位との差+0.30。7頭立てで紛れが少ない。'
   '<span class=w>同距離帯の実測が0走</span>で上がり順位は出せない'),
 'リコーヒューズ': ('大型で位置も取れる',
   '<b>鞍内1位・自前半3位</b>、2位との差+0.20。499kgで普段4角4.0番手。'
   '<span class=w>同距離帯0走</span>で上がりは測れない'),
}
# 張る厚さ（馬名で決める）。表はレース番号順に出す。
WEIGHT = {'ブルーキャット': ('厚', '#d95926'), 'ワールドフォンテン': ('厚', '#d95926'),
          'ナムラソラン': ('中', '#3987e5'), 'ココミサイル': ('薄', '#8e8a84'),
          'トンスケ': ('薄', '#8e8a84'), 'リコーヒューズ': ('薄', '#8e8a84')}
T.sort(key=lambda z: z['R'])

rows = []
for i, p in enumerate(T):
    mk, c = WEIGHT.get(p['nm'], ('', '#8e8a84'))
    head, why = WHY.get(p['nm'], ('', ''))
    ar = f"{p['ark']}/{p['nar']}" if p.get('ark') else '－'
    lead = f"{p['lead']:+.2f}" if p.get('lead') is not None else '－'
    g = f"{p['gain']:+.1f}" if p.get('gain') is not None else '－'
    pos = f"{p['pos']:.1f}" if p.get('pos') is not None else '－'
    rows.append(
      f'<tr style="--c:{c}"><td class=no>{mk}</td>'
      f'<td class=r>{p["R"]}R<br><span class=dm>{p["dist"]}m {p["n"]}頭</span></td>'
      f'<td class=u>{p["uu"]}</td>'
      f'<td class=nm>{html.escape(p["nm"])}<span class=si>{html.escape(p["sire"])}</span>'
      f'<span class=hd>{head}</span></td>'
      f'<td class=big>{lead}</td>'
      f'<td class=rk><b>{p["rk"]}</b>/{p["nr"]}</td>'
      f'<td class=rk><b>{p["hrk"]}</b>/{p["nr"]}</td>'
      f'<td class=rk>{ar}</td>'
      f'<td class=rk>{pos}<span class=un>番手</span><br><span class=un>{g}</span></td>'
      f'<td class=sm>{p["wt"] or "－"}<span class=un>kg</span><br>'
      f'<span class=un>{p["nrun"]}走</span></td>'
      f'<td class=pp>{p["pp"]:g}<span class=un>人</span></td>'
      f'<td class=why>{why}</td></tr>')

HTML = f'''<!doctype html><html lang=ja><head><meta charset=utf-8>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0a0a0a;color:#e8e6e3;font-family:"Hiragino Sans","Noto Sans JP",system-ui,sans-serif;
 padding:46px 54px 38px;width:1960px;-webkit-font-smoothing:antialiased}}
h1{{font-size:39px;font-weight:800}} h1 .ac{{color:#d95926}}
.tag{{display:inline-block;background:#d95926;color:#fff;font-size:15px;font-weight:700;
 padding:4px 12px;border-radius:5px;margin-left:14px;vertical-align:7px}}
.lead{{margin-top:17px;font-size:19px;line-height:1.85;color:#cfccc8;max-width:1840px}}
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
td{{padding:17px 10px;border-bottom:1px solid #1d1d1a;font-size:16px;vertical-align:top}}
.no{{width:44px;font-size:21px;font-weight:800;color:var(--c);
 border-left:4px solid var(--c);padding-left:14px}}
.r{{width:84px;color:#cfccc8;font-weight:700;font-size:17px}}
.dm{{font-size:12px;color:#8e8a84;font-weight:500}}
.u{{width:46px;font-weight:800;font-size:23px;color:var(--c)}}
.nm{{font-weight:700;font-size:19px;width:218px}}
.si{{display:block;font-size:12px;font-weight:500;color:#8e8a84;margin-top:4px}}
.hd{{display:block;font-size:12px;font-weight:700;color:var(--c);margin-top:6px}}
.big{{width:86px;font-size:22px;font-weight:800;font-variant-numeric:tabular-nums;color:var(--c)}}
.rk{{width:76px;color:#8e8a84;font-variant-numeric:tabular-nums;font-size:13px;line-height:1.5}}
.rk b{{font-size:19px;color:#e8e6e3}}
.sm{{width:78px;color:#b5b1ab;font-variant-numeric:tabular-nums;line-height:1.5}}
.un{{font-size:12px;color:#8e8a84;margin-left:2px}}
.pp{{width:60px;font-weight:700;color:#cfccc8}}
.why{{color:#cfccc8;font-size:15px;line-height:1.72}}
.why b{{color:#fff}} .why .w{{color:#c98500;font-weight:700}}
footer{{margin-top:32px;padding-top:20px;border-top:1px solid #262622;
 font-size:15px;line-height:1.85;color:#a5a19b}}
footer b{{color:#fff}} footer .hl{{color:#ff8a5c;font-weight:700}}
</style></head><body>
<h1>{DAY} 大井 ── <span class=ac>自信のある6頭</span><span class=tag>今年の大井 927鞍で検証ずみ</span></h1>
<p class=lead>
馬の脚は変わらないものとして置き、条件（距離×馬場）の水準だけを動かす。
置き直した時計の<b>鞍内順位</b>、<b>自前半の鞍内順位</b>、<b>同距離帯の過去の上がり</b>、
<b>2位との差</b>の4つで選んだ。コーナーは<span class=hl>「下げる馬を外す」ために使う</span>
──3→4角で順位を落とす馬は全馬で −6.8pt。<b>6頭とも下げない。</b>
</p>
<div class=tiles>
 <div class=tile><div class=k>鞍内1位</div><div class=v>55.7<small>%</small></div>
  <div class=n>全体は 22.9%。勝ちは 24.4%</div></div>
 <div class=tile><div class=k>↑ かつ 自前半も鞍内3位以内</div>
  <div class=v style="color:#d95926">61.8<small>%</small></div>
  <div class=n>勝ちは <b>29.0%</b>（434頭）</div></div>
 <div class=tile><div class=k>↑ かつ 2位との差が0.5秒以上</div>
  <div class=v style="color:#d95926">72.9<small>%</small></div>
  <div class=n>勝ち <b>40.1%</b>。<span class=hl>この日は該当なし</span></div></div>
 <div class=tile><div class=k>同距離帯の過去の上がりが鞍内1位</div>
  <div class=v>38.9<small>%</small></div>
  <div class=n>全体18.4%。走り終えた上がりの71.6%とは別物</div></div>
</div>
<table><thead><tr><th>張る</th><th>R</th><th>番</th><th>馬名 / 父</th>
<th>2位との差</th><th>鞍内</th><th>自前半</th><th>上がり</th><th>普段4角／3→4角</th>
<th>馬体重／実測</th><th>直近</th><th>買える理由</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<footer>
<b>今日は一点に大きく張る日ではない。</b>2位との差が0.5秒以上（3着内 72.9%・勝ち 40.1%）の鞍が
<span class=hl>ひとつもない</span>。最大が 5R⑧ の +0.40 で、ここが上限。<br>
<b>厚く張るのは 5R⑧ と 7R⑥（表の「厚」）。</b>自前半・位置・材料の厚みが全部そろう。
6R⑪は14頭立てで鞍内1位かつ上がり1位、配当が付くならここ（「中」）。<br>
<b>残る3頭（「薄」）は鞍内1位だが欠けがある。</b>3R⑧は普段4角8番手で後ろ、2R⑦と8R⑤は同距離帯の実測が0走で
上がりが測れない。薄く。<br>
馬場は良で置いた。朝に取り直し、<b>1〜3鞍走ってから</b>以降の3着ラインを直す。
発走30分前にオッズで印を打ち直す。
</footer></body></html>'''
open(OUT, 'w', encoding='utf-8').write(HTML)
print('書き出し', OUT)
