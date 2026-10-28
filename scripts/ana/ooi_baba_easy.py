# -*- coding: utf-8 -*-
"""きのうの馬場を、はじめて競馬を見る人向けに1枚にする。

  python3 scripts/ana/ooi_baba_easy.py <out.html>

数字は scripts/ana/ooi_baba_day.py と同じ。専門語は使わず、
「どうやって測ったか」を3段階の図で見せる。
"""
import sys

OUT = sys.argv[1]

# きのうの鞍ごとの、予想とのズレ（＋はおそい）
PER = [(4, +0.64), (5, +1.07), (6, +0.87), (7, +0.55), (8, +0.49),
       (9, +1.19), (10, +0.38), (11, -0.23), (12, -0.13)]
LO, HI = -0.4, 1.3
ZERO = 100 * (0 - LO) / (HI - LO)


def rbar(v, h=26):
    c = '#d95926' if v > 0 else '#3987e5'
    left = ZERO if v >= 0 else ZERO - 100 * (-v) / (HI - LO)
    w = 100 * abs(v) / (HI - LO)
    return (f'<div class=bw style="height:{h}px">'
            f'<div class=zl style="left:{ZERO:.1f}%"></div>'
            f'<div class=bar style="left:{left:.1f}%;width:{w:.1f}%;'
            f'background:{c};height:{h}px"></div></div>')


prow = ''.join(
    f'<tr><td class=rn>{R}<span class=rs>R</span></td>'
    f'<td class=bc>{rbar(v)}</td>'
    f'<td class=pv style="color:{"#d95926" if v>0 else "#3987e5"}">'
    f'{"おそい" if v>0 else "はやい"} {abs(v):.2f}<span class=un>秒</span></td></tr>'
    for R, v in PER)

HTML = f'''<!doctype html><html lang=ja><head><meta charset=utf-8>
<title>きのうの馬場</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0a0a0a;color:#e8e6e3;font-family:"Hiragino Sans","Noto Sans JP",system-ui,sans-serif;
 padding:54px 60px 44px;width:1680px;-webkit-font-smoothing:antialiased;line-height:1.6}}
h1{{font-size:52px;font-weight:800;letter-spacing:.01em;line-height:1.25}}
h1 .ac{{color:#d95926}}
.sub{{margin-top:14px;font-size:22px;color:#8e8a84;font-weight:600}}
.ans{{margin-top:30px;background:#171512;border:2px solid #d95926;border-radius:14px;
 padding:28px 32px}}
.ans .lb{{font-size:17px;color:#d95926;font-weight:800;letter-spacing:.06em}}
.ans .tx{{margin-top:12px;font-size:34px;font-weight:800;line-height:1.5}}
.ans .tx b{{color:#ff8a5c}}
.ans .nt{{margin-top:12px;font-size:19px;color:#a5a19b;line-height:1.7}}
section{{margin-top:52px}}
h2{{font-size:34px;font-weight:800;line-height:1.4;margin-bottom:8px}}
h2 .q{{color:#3987e5;margin-right:12px}}
.p{{font-size:21px;line-height:1.95;color:#cfccc8;max-width:1500px;margin-top:14px}}
.p b{{color:#fff}} .p .hl{{color:#ff8a5c;font-weight:700}}
.ex{{margin-top:22px;background:#121210;border-left:6px solid #3987e5;border-radius:0 12px 12px 0;
 padding:24px 30px}}
.ex .h{{font-size:20px;font-weight:800;color:#3987e5}}
.ex .b{{margin-top:10px;font-size:20px;line-height:1.9;color:#cfccc8}}
.ex .b b{{color:#fff}}
.steps{{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-top:26px}}
.st{{background:#141412;border:1px solid #262622;border-radius:14px;padding:26px 26px 28px}}
.st .n{{width:46px;height:46px;border-radius:50%;background:#d95926;color:#fff;
 font-size:25px;font-weight:800;display:flex;align-items:center;justify-content:center}}
.st .t{{margin-top:16px;font-size:23px;font-weight:800;line-height:1.45}}
.st .d{{margin-top:11px;font-size:17px;color:#8e8a84;line-height:1.75}}
.big{{display:flex;align-items:baseline;gap:18px;margin-top:26px}}
.big .v{{font-size:92px;font-weight:800;color:#d95926;line-height:1;
 font-variant-numeric:tabular-nums}}
.big .u{{font-size:30px;font-weight:700;color:#8e8a84}}
.big .s{{font-size:21px;color:#cfccc8;line-height:1.7}}
.big .s b{{color:#fff}}
.horse{{margin-top:24px;background:#121210;border:1px solid #1f1f1c;border-radius:12px;
 padding:22px 28px;font-size:21px;color:#cfccc8;line-height:1.8}}
.horse b{{color:#ff8a5c;font-weight:800;font-size:25px}}
table{{width:100%;border-collapse:collapse;margin-top:18px}}
td{{padding:16px 10px;border-bottom:1px solid #1d1d1a;vertical-align:middle}}
.rn{{width:110px;font-size:32px;font-weight:800;color:#b5b1ab;
 font-variant-numeric:tabular-nums;padding-left:12px}}
.rs{{font-size:17px;color:#8e8a84;margin-left:3px}}
.bc{{padding-right:24px}}
.bw{{position:relative;background:#141412;border-radius:4px}}
.zl{{position:absolute;top:-5px;bottom:-5px;width:2px;background:#3a3a35}}
.bar{{position:absolute;top:0;border-radius:3px;opacity:.92}}
.pv{{width:260px;font-size:24px;font-weight:800;font-variant-numeric:tabular-nums;
 text-align:right;padding-right:14px}}
.un{{font-size:16px;color:#8e8a84;margin-left:3px;font-weight:600}}
.cd{{width:190px;font-size:26px;font-weight:800;color:#e8e6e3}}
.cv{{font-size:36px;font-weight:700;color:#b5b1ab;font-variant-numeric:tabular-nums;
 text-align:center}}
.cv .k{{display:block;font-size:17px;color:#8e8a84;font-weight:600;margin-bottom:7px}}
.three{{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-top:24px}}
.tc{{background:#141412;border:1px solid #262622;border-radius:14px;padding:26px}}
.tc .q{{font-size:20px;color:#8e8a84;font-weight:700;line-height:1.5}}
.tc .a{{margin-top:14px;font-size:40px;font-weight:800;line-height:1.15}}
.tc .d{{margin-top:13px;font-size:17px;color:#a5a19b;line-height:1.8}}
.tc .d b{{color:#e8e6e3}}
.last{{margin-top:54px;background:#171512;border:2px solid #d95926;border-radius:14px;
 padding:34px 38px}}
.last .lb{{font-size:17px;color:#d95926;font-weight:800;letter-spacing:.06em}}
.last ul{{margin-top:18px;list-style:none}}
.last li{{font-size:28px;font-weight:800;line-height:1.75;padding-left:40px;
 position:relative}}
.last li:before{{content:"";position:absolute;left:8px;top:18px;width:14px;height:14px;
 border-radius:50%;background:#d95926}}
.last li b{{color:#ff8a5c}}
footer{{margin-top:40px;padding-top:24px;border-top:1px solid #262622;
 font-size:17px;line-height:1.9;color:#8e8a84}}
footer b{{color:#cfccc8}}
</style></head><body>

<h1>きのうの大井は、<br>どんな<span class=ac>馬場</span>だった？</h1>
<p class=sub>10月28日（水）／ はじめて競馬を見る人へ</p>

<div class=ans>
 <div class=lb>こたえ</div>
 <div class=tx>発表は「重」。でも実際は<b>タイムが出にくい日</b>でした。<br>
  ふだんより、だいたい<b>馬3頭ぶん</b>おそい。</div>
 <div class=nt>「馬場」は走る地面の状態のこと。乾いているか濡れているかで、タイムが変わります。
  競馬場は毎日それを「良・稍重・重・不良」の4段階で発表しています。</div>
</div>

<section>
<h2><span class=q>?</span>タイムを見れば、馬場がわかるのでは</h2>
<p class=p>
それがうまくいきません。<b>速いタイムが出た理由が、2つあるから</b>です。
地面が速かったのか、速い馬が集まっていたのか。結果を見ただけでは区別がつきません。
</p>
<div class=ex>
 <div class=h>テストの平均点と同じです</div>
 <div class=b>平均点が低かったからといって、問題が難しかったとは限りません。
  <b>受けた人が違えば、点も変わります。</b></div>
</div>
<p class=p>
競馬では、この「受けた人の差」がとても大きい。きのうの大井の同じ1600mでも、
出ていた馬の力の差だけで <b>3.5秒</b> ひらきがありました。
いっぽう地面のちがいは、どんなに濡れても <b>0.3秒ぐらい</b>。
</p>
<p class=p>
つまり <span class=hl>タイムの中身は、ほとんどが「誰と走ったか」</span>。
地面の情報は、そのうちのほんの少ししか入っていません。
</p>
</section>

<section>
<h2>だから、こうやって測ります</h2>
<div class=steps>
 <div class=st><div class=n>1</div>
  <div class=t>出る馬ぜんぶの、これまでの走りを集める</div>
  <div class=d>1頭ずつ、過去に何秒で走ってきたかを見ます</div></div>
 <div class=st><div class=n>2</div>
  <div class=t>「このメンバーなら、ふつうこれくらい」を先に出す</div>
  <div class=d>レースが始まる前に、予想のタイムを決めておきます</div></div>
 <div class=st><div class=n>3</div>
  <div class=t>実際のタイムと、くらべる</div>
  <div class=d>その差が、その日の地面のぶん。これなら「誰と走ったか」は消えます</div></div>
</div>
<p class=p>
今年の大井 <b>706レース</b>でためすと、この予想のズレは平均でほぼゼロでした。
やり方そのものが、どちらかに片寄ってはいません。
</p>
</section>

<section>
<h2>きのうは、予想より 0.55秒 おそかった</h2>
<div class=big>
 <div class=v>+0.55</div><div class=u>秒</div>
 <div class=s>今年の<b>70日のうち、おそいほうから8番目</b>。<br>
  上から1割に入る「タイムの出ない日」でした。</div>
</div>
<div class=horse>0.55秒 というのは、ゴール前で <b>だいたい馬3頭ぶん</b>の差です。
 見ていて「あっ、差された」と思うくらいの長さ。</div>
<table>{prow}</table>
<p class=p>9レース中<b>7レースで、予想より遅く</b>決着しました。
きのうは全体として、そういう地面だったということです。</p>
<p class=p style="font-size:18px;color:#8e8a84">
1R〜3Rがないのは、デビューしたばかりの2歳馬のレースで、
<b style="color:#cfccc8">過去の走りがまだ少なく、予想のタイムを作れなかった</b>からです。</p>
</section>

<section>
<h2><span class=q>?</span>「重」と発表されたら、タイムは速くなるのでは</h2>
<p class=p>よく言われますが、<b>大井では、ほとんど変わりません。</b>
今年1年ぶんの1600mの3着のタイムを、発表ごとに並べるとこうなります。</p>
<table>
 <tr><td class=cd>1600m</td>
  <td class=cv><span class=k>良（かわいた）</span>104.0</td>
  <td class=cv><span class=k>稍重（ややおもい）</span>104.3</td>
  <td class=cv><span class=k>重（おもい）</span>104.2</td>
  <td class=cv><span class=k>不良（いちばん濡れた）</span>104.2</td></tr>
</table>
<p class=p>
4つとも、ほぼ同じです。<span class=hl>発表を見ても、その日が速いか遅いかは分かりません。</span>
だからきのうの「0.55秒おそい」は、「重のわりにおそい」ではなく、<b>そのままおそい</b>。
</p>
</section>

<section>
<h2>ほかに、きのう起きたこと</h2>
<div class=three>
 <div class=tc><div class=q>前のほうを走っていた馬が、<br>強かった？</div>
  <div class=a style="color:#199e70">ふつうでした</div>
  <div class=d>3着以内に入ったのは <b>57.6%</b>。
   ふだんの大井も <b>54.9%</b> なので、きのうだけ特別だったわけではありません。</div></div>
 <div class=tc><div class=q>小さい馬は<br>どうだった？</div>
  <div class=a style="color:#c98500">15頭走って 0頭</div>
  <div class=d>439kg以下の馬は、<b>1頭も3着以内に入れませんでした</b>。
   ただし15頭だけなので、たまたまの可能性も残ります。</div></div>
 <div class=tc><div class=q>人気どおりに<br>決まった？</div>
  <div class=a style="color:#3987e5">はい、かなり</div>
  <div class=d>1〜3番人気の馬が <b>63.9%</b> で3着以内。
   いっぽう8番人気以下は56頭いて<b>1頭だけ</b>。荒れない日でした。</div></div>
</div>
</section>

<div class=last>
 <div class=lb>はじめての人が、ひとつだけ覚えるなら</div>
 <ul>
  <li>発表された馬場（良・稍重・重・不良）は、<br>大井では<b>タイムをほとんど変えません</b>。</li>
  <li>タイムを見るときは、<b>「誰と走ったか」</b>を先に考える。</li>
 </ul>
</div>

<footer>
今年の大井 70日・706レースで検証。「予想のタイム」は、出走する馬それぞれの過去の走りから
先に計算したもの。<b>実際のタイムとの差だけを馬場として見ています。</b><br>
馬3頭ぶん＝0.55秒 は、1頭ぶんを約0.2秒として置いた目安です。
</footer>
</body></html>'''
open(OUT, 'w', encoding='utf-8').write(HTML)
print('書き出し', OUT)
