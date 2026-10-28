# -*- coding: utf-8 -*-
"""「粘り」の推移を1頭ずつの小さなグラフにする。

  python3 scripts/ana/ooi_nebari_card.py <nebari.json> <out.html>

縦じくは全パネル共通。0＝その鞍の中央で、上にあるほど後半で落ちていない。
"""
import html, json, sys

SRC, OUT = sys.argv[1], sys.argv[2]
Z = json.load(open(SRC, encoding='utf-8'))
UP, DOWN = Z[:12], Z[-6:]
C_UP, C_DN = '#d95926', '#3987e5'

# 縦じくは全パネル共通（ここを変えると比べられなくなる）
LO, HI = -5.5, 5.5
W, HT = 268, 132
PL, PR, PT, PB = 10, 12, 12, 10
IW, IH = W - PL - PR, HT - PT - PB


def panel(z, c):
    ser = z['ser']
    xs = [PL + IW * i / 4 for i in range(5)]
    ys = [PT + IH * (HI - v) / (HI - LO) for v in ser]
    zero = PT + IH * HI / (HI - LO)
    pts = ' '.join(f'{x:.1f},{y:.1f}' for x, y in zip(xs, ys))
    dots = ''.join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{5 if i < 4 else 6.5}" '
        f'fill="{c}" stroke="#0a0a0a" stroke-width="2"/>'
        for i, (x, y) in enumerate(zip(xs, ys)))
    last = ser[-1]
    lx = xs[-1]
    # 枠からはみ出さないよう上下に収める
    ly = min(max(ys[-1] + (-12 if last >= 0 else 20), PT + 14), HT - 6)
    r = z['runs'][-1]
    sub = (f"{r['d'][4:6]}/{r['d'][6:]} {r['R']}R {r['dist']}m "
           f"{r['f'] or '－'}着 {r['pop'] or '－'}人気")
    return (
      f'<div class=pn>'
      f'<div class=hd><span class=nm>{html.escape(z["nm"])}</span>'
      f'<span class=tv style="color:{c}">{z["trend"]:+.2f}</span></div>'
      f'<svg viewBox="0 0 {W} {HT}" width="{W}" height="{HT}">'
      f'<line x1="{PL}" y1="{zero:.1f}" x2="{W-PR}" y2="{zero:.1f}" '
      f'stroke="#2e2e2a" stroke-width="1"/>'
      f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="2" '
      f'stroke-linejoin="round" stroke-linecap="round"/>{dots}'
      f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="end" fill="#e8e6e3" '
      f'font-size="15" font-weight="700">{last:+.1f}</text>'
      f'</svg><div class=sb>{sub}</div></div>')


ups = ''.join(panel(z, C_UP) for z in UP)
dns = ''.join(panel(z, C_DN) for z in DOWN)

HTML = f'''<!doctype html><html lang=ja><head><meta charset=utf-8>
<title>粘りの推移</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0a0a0a;color:#e8e6e3;font-family:"Hiragino Sans","Noto Sans JP",system-ui,sans-serif;
 padding:48px 54px 40px;width:1300px;-webkit-font-smoothing:antialiased}}
h1{{font-size:40px;font-weight:800;line-height:1.3}} h1 .ac{{color:#d95926}}
.tag{{display:inline-block;background:#d95926;color:#fff;font-size:14px;font-weight:700;
 padding:4px 11px;border-radius:5px;margin-left:14px;vertical-align:8px}}
.lead{{margin-top:16px;font-size:17px;line-height:1.85;color:#cfccc8;max-width:1180px}}
.lead b{{color:#fff}} .lead .hl{{color:#ff8a5c;font-weight:700}}
.tiles{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:24px 0 6px}}
.tile{{background:#141412;border:1px solid #262622;border-radius:10px;padding:16px 18px}}
.tile .k{{font-size:12px;color:#8e8a84}}
.tile .v{{font-size:33px;font-weight:800;margin-top:5px;line-height:1}}
.tile .v small{{font-size:16px;color:#8e8a84;margin-left:4px}}
.tile .n{{font-size:12px;color:#8e8a84;margin-top:7px;line-height:1.55}}
.key{{display:flex;gap:26px;align-items:center;margin-top:26px;font-size:15px;
 color:#8e8a84}}
.key i{{display:inline-block;width:26px;height:3px;border-radius:2px;margin-right:9px;
 vertical-align:4px}}
h2{{font-size:26px;font-weight:800;margin:34px 0 4px}}
h2 small{{font-size:15px;font-weight:500;color:#8e8a84;margin-left:14px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-top:14px}}
.pn{{background:#121210;border:1px solid #1f1f1c;border-radius:11px;padding:13px 10px 11px}}
.hd{{display:flex;justify-content:space-between;align-items:baseline;
 padding:0 6px 2px}}
.nm{{font-size:19px;font-weight:800;letter-spacing:.01em}}
.tv{{font-size:19px;font-weight:800;font-variant-numeric:tabular-nums}}
.sb{{padding:4px 6px 0;font-size:12px;color:#8e8a84;font-variant-numeric:tabular-nums}}
.ax{{margin-top:10px;font-size:13px;color:#8e8a84;line-height:1.7}}
.ax b{{color:#cfccc8}}
footer{{margin-top:34px;padding-top:22px;border-top:1px solid #262622;
 font-size:15px;line-height:1.9;color:#a5a19b}}
footer b{{color:#fff}} footer .hl{{color:#ff8a5c;font-weight:700}}
</style></head><body>
<h1>後半の<span class=ac>粘り</span>の推移　<span style="font-size:24px;color:#8e8a84">今開催の大井に出た250頭から</span>
<span class=tag>今年の大井 2,449頭で検証</span></h1>
<p class=lead>
1走ぶんの<b>粘り</b>を、<b>その鞍の中央を0</b>にして出した。
上にあるほど、同じレースの馬より後半で落ちていない。
中央を引いてあるので、その日のペースもクラスも抜けている。
左から右へ古い走りから新しい走りへ。<b>縦じくは全パネル共通</b>。<br>
<span class=hl>生の落ち込み（時計から出すだけ）では効かなかった</span>。
その鞍のペースでほとんど決まってしまうため。中央を引いて初めて向きが出る。
</p>
<div class=tiles>
 <div class=tile><div class=k>上向きの上位1/4</div>
  <div class=v style="color:#d95926">10.4<small>%</small></div>
  <div class=n>複勝の回収 70%（614頭）</div></div>
 <div class=tile><div class=k>人気薄ぜんぶ</div>
  <div class=v>9.2<small>%</small></div>
  <div class=n>複勝の回収 63%（2,449頭）</div></div>
 <div class=tile><div class=k>下向きの下位1/4</div>
  <div class=v style="color:#3987e5">7.4<small>%</small></div>
  <div class=n>複勝の回収 <b>51%</b>（612頭）</div></div>
 <div class=tile><div class=k>もともと落ちる側 × 向き</div>
  <div class=v style="color:#c98500">9.9<small>%</small></div>
  <div class=n>同じ層の下向きは 6.3%。<b>ここが一番ひらく</b></div></div>
</div>
<div class=key>
 <span><i style="background:{C_UP}"></i>上向き（直近2走が、その前3走より粘っている）</span>
 <span><i style="background:{C_DN}"></i>下向き</span>
 <span>横の細い線 ＝ その鞍の中央（0）</span>
</div>

<h2>上向き 12頭<small>向きの大きい順。右端の数字がいちばん新しい走り</small></h2>
<div class=grid>{ups}</div>

<h2>下向き 6頭<small>この側のほうが、数字としてははっきりしている</small></h2>
<div class=grid>{dns}</div>

<footer>
<b>買うより、外すのに効く。</b>上向きの上位1/4は人気薄の平均9.2%に対して10.4%で、
+1.2ptしかない。いっぽう下向きの下位1/4は <b>7.4%・回収51%</b> まで落ちる。
<span class=hl>上がってきた馬を買う材料ではなく、下がってきた馬を外す材料</span>として使うほうが素直。<br>
<b>効き目が出るのは「もともと落ちる馬」。</b>直近2走の粘りが下半分だった馬のなかでは、
上向き 9.9%・回収79% に対し 下向き 6.3%・回収50%。もともと粘る馬はどちらでも変わらない。<br>
5走そろう馬だけが対象。今開催423頭のうち250頭。
</footer></body></html>'''
open(OUT, 'w', encoding='utf-8').write(HTML)
print('書き出し', OUT)
