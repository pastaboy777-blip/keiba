# -*- coding: utf-8 -*-
"""穴狙いの1枚カードをつくる。

  python3 scripts/ana/ooi_ana_card.py <pick.json> <out.html>

載せるのは買う側だけ。見送る馬は「見送る理由」の欄に短く置く。
数字はすべて今年の大井の実測から（当日6番人気以下 × 見込み3位以内 533頭）。
"""
import html, json, sys

PICK, OUT = sys.argv[1], sys.argv[2]
P = json.load(open(PICK, encoding='utf-8'))

WHY = {
 'ノーブルミューズ': '前走1200mを<b>37.2＋39.8</b>で6番人気5着。同距離の据え置きで条件は'
                 '何も変わらない。<b>壁まで0.80秒</b>の余裕があり、しかも'
                 '<b>自前半が鞍内1位</b>。この2つが揃う形は今年 <b>32.6%</b>',
 'グレートロッタリー': '前走1600mで9番人気9着。<b>65.0＋40.9</b>を同じ1600mの水準に'
                  '置き直すと壁まで0.30秒。自前半は鞍内2位で位置も取れる',
 'ムーンショア': '前走1400mを<b>52.4＋39.9</b>で8番人気8着。壁まで0.30秒。'
             '自前半は4頭中3位で、位置の裏づけはやや薄い',
}
CUT = [
 ('1R②ムサシウォリアー', '余裕+0.30はあるが、<b>自前半が4頭中4位</b>。前に行けない'),
 ('1R⑨アヤサンミニサンタ', '壁と同値。余裕がない'),
 ('2R②モーモールーツ', '壁と同値、自前半3頭中3位'),
 ('4R⑪ガリマド', '壁と同値。直近<b>11番人気</b>で、この層は今年 <b>9.4%</b>'),
 ('6R②ドレヴィーナス', '同じく直近11番人気。自前半も14頭中6位'),
 ('8R⑪ピルゴスアイトス', '壁と同値、<b>自前半が8頭中8位</b>'),
]
BUY = ['ノーブルミューズ', 'グレートロッタリー', 'ムーンショア']
MK = {'ノーブルミューズ': ('◎', '#d95926'), 'グレートロッタリー': ('○', '#3987e5'),
      'ムーンショア': ('△', '#c98500')}

rows = []
for nm in BUY:
    p = next(x for x in P if x['nm'] == nm)
    mk, c = MK[nm]
    ds = (f"{p['pd']}<span class=ar>→</span>{p['dist']}" if p['pd'] != p['dist']
          else f"{p['dist']}m<br><span class=dm>据え置き</span>")
    rows.append(
      f'<tr style="--c:{c}"><td class=mk>{mk}</td><td class=r>{p["R"]}R</td>'
      f'<td class=u>{p["uu"]}</td><td class=nm>{html.escape(nm)}</td>'
      f'<td class=d>{ds}</td>'
      f'<td class=big>{p["slack"]:+.2f}<span class=un>秒</span></td>'
      f'<td class=rk><b>{p["hrk"]}</b>/{p["nh"]}</td>'
      f'<td class=pp>{p["pp"]}</td>'
      f'<td class=why>{WHY[nm]}</td></tr>')

HTML = f'''<!doctype html><html lang=ja><head><meta charset=utf-8>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0a0a0a;color:#e8e6e3;font-family:"Hiragino Sans","Noto Sans JP",system-ui,sans-serif;
 padding:48px 56px 40px;width:1800px;-webkit-font-smoothing:antialiased}}
h1{{font-size:40px;font-weight:800}}
h1 .ac{{color:#d95926}}
.tag{{display:inline-block;background:#d95926;color:#fff;font-size:15px;font-weight:700;
 padding:4px 12px;border-radius:5px;margin-left:14px;vertical-align:7px}}
.lead{{margin-top:18px;font-size:19px;line-height:1.85;color:#cfccc8;max-width:1680px}}
.lead b{{color:#fff}} .lead .hl{{color:#ff8a5c;font-weight:700}}
.tiles{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:28px 0 6px}}
.tile{{background:#141412;border:1px solid #262622;border-radius:10px;padding:18px 20px}}
.tile .k{{font-size:13px;color:#8e8a84}}
.tile .v{{font-size:38px;font-weight:800;margin-top:6px;line-height:1}}
.tile .v small{{font-size:19px;color:#8e8a84;margin-left:6px}}
.tile .n{{font-size:13px;color:#8e8a84;margin-top:9px;line-height:1.55}}
section{{margin-top:36px}}
.sh{{display:flex;align-items:center;gap:13px;margin-bottom:14px}}
h2{{font-size:25px;font-weight:800}} .sub{{font-size:14px;color:#8e8a84}}
table{{width:100%;border-collapse:collapse}}
th{{font-size:13px;color:#8e8a84;font-weight:500;text-align:left;padding:0 12px 9px;
 border-bottom:1px solid #262622}}
td{{padding:17px 12px;border-bottom:1px solid #1d1d1a;font-size:16px;vertical-align:top}}
.mk{{width:40px;font-size:22px;font-weight:800;color:var(--c);
 border-left:4px solid var(--c);padding-left:14px}}
.r{{color:#8e8a84;width:54px}} .u{{font-weight:800;font-size:21px;color:var(--c);width:44px}}
.nm{{font-weight:700;font-size:19px;width:200px}}
.d{{width:128px;font-weight:700;white-space:nowrap}}
.ar{{color:#6e6a64;margin:0 5px;font-weight:400}} .dm{{font-size:12px;color:#8e8a84;font-weight:500}}
.big{{width:150px;font-size:26px;font-weight:800;font-variant-numeric:tabular-nums;
 color:var(--c);white-space:nowrap}}
.un{{font-size:14px;font-weight:600;margin-left:3px;color:#8e8a84}}
.rk{{width:90px;color:#8e8a84;font-variant-numeric:tabular-nums}}
.rk b{{font-size:21px;color:#e8e6e3}}
.pp{{width:80px;font-weight:700;color:#b5b1ab}}
.why{{color:#cfccc8;font-size:15px;line-height:1.72}} .why b{{color:#fff}}
.cut{{display:grid;grid-template-columns:1fr 1fr;gap:12px 20px;margin-top:4px}}
.cut div{{background:#121210;border:1px solid #1f1f1c;border-radius:8px;padding:13px 16px;
 font-size:15px;color:#a5a19b;line-height:1.65}}
.cut b{{color:#e8e6e3}} .cut .h{{color:#fff;font-weight:700;margin-right:8px}}
footer{{margin-top:34px;padding-top:22px;border-top:1px solid #262622;
 font-size:15px;line-height:1.85;color:#a5a19b}}
footer b{{color:#fff}} footer .hl{{color:#ff8a5c;font-weight:700}}
</style></head><body>
<h1>10/28（水）大井 ── <span class=ac>穴狙い</span><span class=tag>今年の大井 927鞍で検証ずみ</span></h1>
<p class=lead>
馬の脚は変わらないものとして置き、条件（距離×馬場）の水準だけを動かす。置き直した時計が
<b>その鞍の3番手に届くか</b>を見る。<br>
昨日の実戦で分かったのは、<span class=hl>壁ちょうどの馬は走らない</span>ということ。
人気薄で効くのは<b>壁までの余裕</b>と<b>前に行けるか</b>の2つだけで、
実測の厚み・鞍のレベル・前走着順はどれも効かなかった。
</p>
<div class=tiles>
 <div class=tile><div class=k>当日6番人気以下 × 見込み3位以内</div><div class=v>20.3<small>%</small></div>
  <div class=n>人気薄ぜんぶは 9.3%。533頭で測った</div></div>
 <div class=tile><div class=k>↑ かつ 壁まで0.3秒以上の余裕</div>
  <div class=v style="color:#d95926">28.4<small>%</small></div>
  <div class=n>壁とほぼ同値だと 18.7% に落ちる</div></div>
 <div class=tile><div class=k>↑ かつ 自前半も鞍内3位以内</div>
  <div class=v style="color:#d95926">32.6<small>%</small></div>
  <div class=n>人気薄ぜんぶの <b>3.5倍</b>（43頭）</div></div>
 <div class=tile><div class=k>当日 8〜10番人気の層</div>
  <div class=v style="color:#6e6a64">9.4<small>%</small></div>
  <div class=n>6〜7番人気は 26.7%。<b>沈みすぎた馬は見送る</b></div></div>
</div>
<section><div class=sh><h2>買う3頭</h2>
<span class=sub>見込み3位以内 × 直近3走の人気が6番人気以下</span></div>
<table><thead><tr><th></th><th>R</th><th>番</th><th>馬名</th><th>距離</th>
<th>壁までの余裕</th><th>自前半順位</th><th>直近人気</th><th>買える理由</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></section>
<footer>
候補は9頭いたが、<b>6頭は壁と同値か自前半が鞍内下位</b>で外した（4R⑪ガリマド・6R②ドレヴィーナスは直近11番人気で、この層は今年 <b>9.4%</b>）。<br><b>いちばん強い形に該当馬がいない。</b>「壁まで0.3秒以上 × 距離が動く」は今年 <b>28.4%</b> だが、
明日の候補9頭は全員が同距離か、余裕ゼロ。<span class=hl>穴の材料そのものが薄い日</span>なので広げない。<br>
番組は今日より一段速い（11Rのレベル −3.79 は今年の上位2%）。12鞍のうち
<b>1200mが4鞍・1600mが4鞍</b>で、この2距離は時計の見当が 0.43〜0.63秒 で当たる。<br>
<b>12R（2400m）は手を出さない。</b>年53鞍しかなく、同じ薄さの1800mで昨日 2.8秒 外している。<br>
馬場は乾く見込み。朝に馬場状態を取り直し、<b>1〜3鞍走ってから</b>以降の3着ラインを直す。
</footer></body></html>'''
open(OUT, 'w', encoding='utf-8').write(HTML)
print('書き出し', OUT)
