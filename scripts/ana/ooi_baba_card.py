# -*- coding: utf-8 -*-
"""その日の馬場感を1枚にする。

  python3 scripts/ana/ooi_baba_card.py <out.html>

数字は scripts/ana/ooi_baba_day.py と同じ材料（今年の大井 70日・706鞍）。
「残り」は、メンバーの過去から推したレベルを引いたあとの3着時計の差。
クラスを抜いてあるので、その日その場の速さに近い。
"""
import sys

OUT = sys.argv[1]

# 鞍ごとの残り（＋は見当より遅い）
PER = [(4, 1200, +0.64), (5, 1600, +1.07), (6, 1200, +0.87), (7, 1600, +0.55),
       (8, 1400, +0.49), (9, 1200, +1.19), (10, 1400, +0.38), (11, 1600, -0.23),
       (12, 2400, -0.13)]
# 距離×馬場ごとの3着時計の中央値（今年の大井）
COND = [('1200m', [('良', 74.8, 175), ('稍重', 74.9, 58), ('重', 74.4, 21),
                   ('不良', 75.2, 77)]),
        ('1400m', [('良', 89.0, 106), ('稍重', 88.3, 39), ('重', 88.9, 15),
                   ('不良', 89.5, 53)]),
        ('1600m', [('良', 104.0, 130), ('稍重', 104.3, 41), ('重', 104.2, 18),
                   ('不良', 104.2, 64)])]
# 4角の位置
POS = [('1〜3番手', 57.6, 19, 33, 54.9, '#d95926'),
       ('4〜6番手', 21.2, 7, 33, 28.7, '#c98500'),
       ('7番手以降', 11.3, 7, 62, 8.6, '#3987e5')]
# 直近の日
DAYS = [('10/26', '不良', +0.69), ('10/27', '不良', +0.09), ('10/28', '重', +0.55)]
# 朝の3鞍をどれだけ足すか
W = [(0.0, 0.26), (0.2, 0.19), (0.3, 0.17), (0.5, 0.17), (0.8, 0.28), (1.0, 0.40)]

LO, HI = -0.4, 1.3                      # 残りの棒の目盛り
ZERO = 100 * (0 - LO) / (HI - LO)


def rbar(v):
    c = '#d95926' if v > 0 else '#3987e5'
    if v >= 0:
        left, w = ZERO, 100 * v / (HI - LO)
    else:
        left, w = ZERO - 100 * (-v) / (HI - LO), 100 * (-v) / (HI - LO)
    return (f'<div class=bw><div class=zl style="left:{ZERO:.1f}%"></div>'
            f'<div class=bar style="left:{left:.1f}%;width:{w:.1f}%;'
            f'background:{c}"></div></div>')


prow = ''.join(
    f'<tr><td class=rr style="color:{"#d95926" if v>0 else "#3987e5"}">{R}'
    f'<span class=un2>R</span></td>'
    f'<td class=dd>{d}m</td><td class=bc>{rbar(v)}</td>'
    f'<td class=vv style="color:{"#d95926" if v>0 else "#3987e5"}">{v:+.2f}'
    f'<span class=un2>秒</span></td></tr>' for R, d, v in PER)

crow = ''
for dist, cs in COND:
    best = min(c[1] for c in cs)
    cells = ''.join(
        f'<td class="cv{" bst" if t==best else ""}">{t:.1f}'
        f'<span class=un>{n}鞍</span></td>' for b, t, n in cs)
    crow += f'<tr><td class=cd>{dist}</td>{cells}</tr>'

orow = ''.join(
    f'<tr><td class=pl style="border-left:5px solid {c}">{n}</td>'
    f'<td class=pv style="color:{c}">{v:.1f}<span class=pc>%</span>'
    f'<span class=un>{i}/{t}</span></td>'
    f'<td class=pa>{y:.1f}<span class=pc>%</span></td>'
    f'<td class=pd>{v-y:+.1f}<span class=pc>pt</span></td></tr>'
    for n, v, i, t, y, c in POS)

drow = ''.join(
    f'<tr><td class=dl>{d}</td><td class=db>{b}</td>'
    f'<td class=bc>{rbar(v)}</td>'
    f'<td class=vv style="color:{"#d95926" if v>0 else "#3987e5"}">{v:+.2f}'
    f'<span class=un2>秒</span></td></tr>' for d, b, v in DAYS)

wmin = min(x[1] for x in W)
wrow = ''.join(
    f'<td class="wv{" bst" if e==wmin else ""}">'
    f'<div class=wk>{"足さない" if w == 0 else f"{w:g}倍"}</div>'
    f'<div class=we>{e:.2f}<span class=un2>秒</span></div></td>' for w, e in W)

HTML = f'''<!doctype html><html lang=ja><head><meta charset=utf-8>
<title>今日の馬場</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0a0a0a;color:#e8e6e3;font-family:"Hiragino Sans","Noto Sans JP",system-ui,sans-serif;
 padding:46px 54px 38px;width:1800px;-webkit-font-smoothing:antialiased}}
h1{{font-size:44px;font-weight:800;letter-spacing:.01em}}
h1 .ac{{color:#d95926}}
.tag{{display:inline-block;background:#d95926;color:#fff;font-size:15px;font-weight:700;
 padding:4px 12px;border-radius:5px;margin-left:16px;vertical-align:9px}}
.lead{{margin-top:16px;font-size:18px;line-height:1.8;color:#cfccc8;max-width:1620px}}
.lead b{{color:#fff}} .lead .hl{{color:#ff8a5c;font-weight:700}}
.tiles{{display:grid;grid-template-columns:repeat(4,1fr);gap:15px;margin:28px 0 10px}}
.tile{{background:#141412;border:1px solid #262622;border-radius:10px;padding:18px 20px}}
.tile .k{{font-size:13px;color:#8e8a84}}
.tile .v{{font-size:40px;font-weight:800;margin-top:6px;line-height:1}}
.tile .v small{{font-size:19px;color:#8e8a84;margin-left:5px}}
.tile .n{{font-size:13px;color:#8e8a84;margin-top:9px;line-height:1.55}}
section{{margin-top:34px}}
h2{{font-size:25px;font-weight:800;margin-bottom:4px}}
h2 .s{{font-size:14px;font-weight:500;color:#8e8a84;margin-left:14px}}
table{{width:100%;border-collapse:collapse;margin-top:12px}}
td{{padding:13px 10px;border-bottom:1px solid #1d1d1a;vertical-align:middle}}
.rr{{width:110px;font-size:34px;font-weight:800;font-variant-numeric:tabular-nums;
 padding-left:16px}}
.un2{{font-size:.48em;color:#8e8a84;margin-left:3px;font-weight:600}}
.dd{{width:130px;font-size:19px;font-weight:700;color:#8e8a84}}
.bc{{padding-right:26px}}
.bw{{position:relative;height:30px;background:#141412;border-radius:4px}}
.zl{{position:absolute;top:-4px;height:38px;width:2px;background:#3a3a35}}
.bar{{position:absolute;top:0;height:30px;border-radius:3px;opacity:.92}}
.vv{{width:160px;font-size:30px;font-weight:800;font-variant-numeric:tabular-nums;
 text-align:right;padding-right:16px}}
.cd{{width:150px;font-size:23px;font-weight:800;color:#e8e6e3}}
.cv{{font-size:30px;font-weight:700;color:#b5b1ab;font-variant-numeric:tabular-nums}}
.cv.bst{{color:#199e70;font-weight:800}}
.cv .un{{display:block;font-size:13px;color:#8e8a84;font-weight:500;margin-top:4px}}
.ch{{font-size:14px;color:#8e8a84;font-weight:600;padding-bottom:6px;
 border-bottom:1px solid #262622}}
.pl{{width:300px;font-size:23px;font-weight:700;color:#cfccc8;padding-left:20px}}
.pv{{width:300px;font-size:36px;font-weight:800;font-variant-numeric:tabular-nums}}
.pc{{font-size:.5em;margin-left:2px}}
.un{{font-size:14px;color:#8e8a84;font-weight:500;margin-left:10px}}
.pa{{width:260px;font-size:27px;font-weight:700;color:#8e8a84;
 font-variant-numeric:tabular-nums}}
.pd{{font-size:26px;font-weight:800;color:#b5b1ab;font-variant-numeric:tabular-nums}}
.dl{{width:140px;font-size:28px;font-weight:800;color:#e8e6e3;padding-left:16px}}
.db{{width:110px;font-size:19px;font-weight:700;color:#8e8a84}}
.wv{{text-align:center;background:#121210;border:1px solid #1f1f1c;border-radius:9px;
 padding:16px 10px}}
.wv.bst{{background:#16211c;border-color:#199e70}}
.wk{{font-size:15px;color:#8e8a84;font-weight:600}}
.we{{font-size:32px;font-weight:800;margin-top:7px;font-variant-numeric:tabular-nums;
 color:#b5b1ab}}
.wv.bst .we{{color:#199e70}}
.wt{{width:100%;border-collapse:separate;border-spacing:11px 0;margin-top:12px}}
.wt td{{border:0}}
.note{{margin-top:12px;font-size:15px;color:#8e8a84;line-height:1.75}}
.note b{{color:#cfccc8}}
footer{{margin-top:34px;padding-top:22px;border-top:1px solid #262622;
 font-size:16px;line-height:1.9;color:#a5a19b}}
footer b{{color:#fff}} footer .hl{{color:#ff8a5c;font-weight:700}}
</style></head><body>
<h1>10/28（水）大井の<span class=ac>馬場</span>
<span class=tag>今年の大井 70日・706鞍で検証</span></h1>
<p class=lead>
表示は<b>重・晴</b>。ただし時計は見当より <b>0.55秒おそい</b>。
ここでいう「残り」は、<b>出走メンバーの過去から推したレベルを引いたあと</b>の3着時計の差。
クラスのぶんを抜いてあるので、残るのはその日その場の速さ。
706鞍で測ると残りの中央値は <b>−0.00秒</b> で、モデルにかたよりはない。
</p>
<div class=tiles>
 <div class=tile><div class=k>3着時計の残り</div>
  <div class=v style="color:#d95926">+0.55<small>秒</small></div>
  <div class=n>70日のうち<b>おそいほうから8番目</b>（上位11%）</div></div>
 <div class=tile><div class=k>4角 1〜3番手の3着内</div>
  <div class=v style="color:#199e70">57.6<small>%</small></div>
  <div class=n>今年の大井は 54.9%。<b>いつも通り</b></div></div>
 <div class=tile><div class=k>439kg以下</div>
  <div class=v style="color:#c98500">0<small>/15頭</small></div>
  <div class=n>今年の重・不良は 16.3%（455頭）</div></div>
 <div class=tile><div class=k>上がり最速だった馬</div>
  <div class=v style="color:#3987e5">8<small>/14頭</small></div>
  <div class=n>今年は 71.6%。<b>いつもより届いていない</b></div></div>
</div>

<section><h2>鞍ごとの残り<span class=s>オレンジが見当よりおそい、青がはやい</span></h2>
<table>{prow}</table>
<p class=note><b>前半（4〜6R）が +0.87、後半（7〜12R）が +0.44。</b>
日が進んで時計が出るようになった。ただし 10/26 は逆に後半のほうがおそく、
10/27 は前半がはやかった。<b>向きは日によって変わる。</b></p>
</section>

<section><h2>大井では「重」は時計をほとんど動かさない<span class=s>今年の3着時計の中央値（秒）</span></h2>
<table><tr><td class=ch></td><td class=ch>良</td><td class=ch>稍重</td>
<td class=ch>重</td><td class=ch>不良</td></tr>{crow}</table>
<p class=note>いちばんはやい欄を緑にした。<b>1200mだけ重が0.4秒はやく、1600mは4つとも横一線。</b>
表示が重に変わったから時計が出る、という読みは大井では成り立たない。
今日の +0.55秒は<b>「重のわりにおそい」ではなく、そのままおそい</b>。</p>
</section>

<section><h2>位置の効き方はいつも通り<span class=s>左が10/28、右が今年の大井ぜんぶ</span></h2>
<table>{orow}</table>
<p class=note>前が止まらない日に見えるが、<b>年間の54.9%に対して +2.7pt</b>。
後ろからの馬もむしろ年間より届いている（11.3% ／ 年間8.6%）。
<b>今日かぎりの前残りではない。</b></p>
</section>

<section><h2>この3日の並び<span class=s>表示と、実際の速さは別</span></h2>
<table>{drow}</table>
<p class=note>10/26 と 10/27 はどちらも<b>不良</b>の表示だったが、実際は 0.6秒ちがう。
<b>表示ではなく残りで見る。</b></p>
</section>

<section><h2>朝の3鞍はどこまで使えるか<span class=s>最初の3鞍の残りを何倍して以降に足すか／以降の日の外れ</span></h2>
<table class=wt><tr>{wrow}</tr></table>
<p class=note><b>0.3倍がいちばん当たる。</b>何も足さないと 0.26秒、そのまま足すと 0.40秒で
かえって悪くなる。最初の3鞍と以降の相関は <b>+0.46</b>。
朝の時計は効くが、<b>見えたぶんの3割だけ</b>動かす。</p>
</section>

<footer>
<b>今日は「時計の出ない日」だった。</b>残り +0.55秒は70日で8番目。
番組は重の表示だったが、大井では重でも時計は動かない。<br>
<b>位置も体重も、今日かぎりの特別な偏りではない。</b>439kg以下の0/15は目を引くが15頭。
年間でも439kg以下は16.3%で、もともと一段落ちる層。<br>
<b>朝の3鞍は0.3倍だけ足す。</b>ただしこれで当たるのは「その日ぜんたいがどちら寄りか」まで。
1鞍ごとの3着時計の外れは <span class=hl>0.57秒 → 0.55秒</span> とほとんど変わらない。
</footer></body></html>'''
open(OUT, 'w', encoding='utf-8').write(HTML)
print('書き出し', OUT)
