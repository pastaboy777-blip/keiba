# -*- coding: utf-8 -*-
"""大井1200m 2レース比較パネル（7/21 9R vs 8/12 8R）"""
SEG = ["スタート(2C出口)","向正面","向正面〜3C","3C〜4C","4C〜直線","直線386m"]
MARKS = [200,400,600,800,1000,1200]
def col(s):
    if s.startswith("直線"): return "#e9f5ec"
    if "3C" in s or "4C" in s: return "#fcebf0"
    if "向正面" in s: return "#e6f4fb"
    return "#fdf5e0"
BANDS=[col(s) for s in SEG]

def chart(v, hi_idx, hi_color, w=1320, h=380):
    L,R,T,B = 74,20,26,52
    pw,ph = w-L-R, h-T-B
    lo,hiv = min(v)-.40, max(v)+.40
    n=len(v)
    X = lambda i: L+pw*(i+.5)/n
    Y = lambda t: T+ph*(t-lo)/(hiv-lo)
    o=[f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}">']
    for i,b in enumerate(BANDS):
        o.append(f'<rect x="{L+pw*i/n:.1f}" y="{T}" width="{pw/n:.1f}" height="{ph}" fill="{b}"/>')
    for k in range(5):
        t=lo+(hiv-lo)*k/4; y=Y(t)
        o.append(f'<line x1="{L}" y1="{y:.1f}" x2="{w-R}" y2="{y:.1f}" stroke="#e2e9f0"/>')
        o.append(f'<text x="{L-10}" y="{y+6:.1f}" text-anchor="end" font-size="17" fill="#8a99a8">{t:.1f}</text>')
    o.append(f'<polyline points="{" ".join(f"{X(i):.1f},{Y(t):.1f}" for i,t in enumerate(v))}" '
             f'fill="none" stroke="#e6a020" stroke-width="6" stroke-linejoin="round"/>')
    for i,t in enumerate(v):
        big = (i==hi_idx)
        o.append(f'<circle cx="{X(i):.1f}" cy="{Y(t):.1f}" r="{14 if big else 9}" fill="{hi_color if big else "#e6a020"}"/>')
        o.append(f'<text x="{X(i):.1f}" y="{Y(t)-24:.1f}" text-anchor="middle" font-size="{29 if big else 20}" '
                 f'font-weight="900" fill="{hi_color if big else "#8a6a20"}">{t}</text>')
        o.append(f'<text x="{X(i):.1f}" y="{T+ph+26}" text-anchor="middle" font-size="17" fill="#6b7c8c">{MARKS[i]}m</text>')
    o.append('</svg>')
    return "".join(o)

def block(rno, head, laps, hi_idx, hi_color, tops, note, ncolor):
    heads="".join(f'<th>{m}m</th>' for m in MARKS)
    vals ="".join(f'<td>{t}</td>' for t in laps)
    tags ="".join(f'<td class="sg" style="background:{BANDS[i]}">{SEG[i]}</td>' for i in range(6))
    tp="".join(f'<div class="tp"><span class="f">{a}</span><span class="hn">{b}</span>'
               f'<span class="pp">{c}</span><span class="cn">{d}</span><span class="ag">{e}</span></div>'
               for a,b,c,d,e in tops)
    return f'''<div class="box">
    <div class="bh" style="background:{ncolor}"><b>{rno}</b><span>{head}</span></div>
    <table><tr>{heads}</tr><tr>{vals}</tr><tr>{tags}</tr></table>
    {chart(laps, hi_idx, hi_color)}
    <div class="tops">{tp}</div>
    <div class="read" style="border-color:{ncolor}">{note}</div>
  </div>'''

A = block("7/21 9R",
  "大井1200m・良・12頭　勝ち時計 1:12.8",
  [12.4,11.5,11.8,12.5,11.9,12.7], 4, "#1f8a4c",
  [("1着","⑫ゴルトフェニックス","2番人気","4角2番手","上がり37.0"),
   ("2着","⑥ジーティーゴッド","1番人気","4角4番手","上がり37.0"),
   ("3着","⑤ラインガーラ","5番人気","4角3番手","上がり37.5")],
  "4角〜直線の1本を<b>11.9で締め直した</b>。ここで緩まないと前は止まらない。"
  "ラスト1Fは12.7で、決着は<b>4角2番手・4番手・3番手</b>。人気も2・1・5番人気で収まった。",
  "#1f8a4c")

B = block("8/12 8R",
  "大井1200m・不良・13頭　勝ち時計 1:14.3",
  [12.5,11.2,11.7,12.6,12.5,13.8], 4, "#c92a2a",
  [("1着","⑫ドピエッタ","12番人気","4角10番手","上がり37.6"),
   ("2着","③サフィールシェール","7番人気","4角1番手","上がり39.0"),
   ("3着","⑥スマイルケイ","10番人気","4角5番手","上がり38.8")],
  "前半3Fは35.4で<b>7/21とほぼ同じ</b>。違うのは4角〜直線で<b>12.5まで緩んだ</b>こと。"
  "そこから立て直せずラスト1Fは<b>13.8</b>まで落ち、<b>4角10番手の12番人気が突き抜けた</b>。単勝17,570円。",
  "#c92a2a")

ROWS = [
 ("7/22", 7,"良",13,35.1,12.4,13.6,"2・8・3",True),
 ("7/22", 2,"良",16,35.2,12.6,13.6,"2・8・1",True),
 ("7/20", 2,"稍",15,35.3,12.9,14.0,"5・9・10",True),
 ("8/12", 8,"不",13,35.4,12.5,13.8,"10・1・5",True),
 ("7/23", 2,"良",16,35.5,12.5,13.6,"2・3・4",False),
 ("7/23", 5,"良",16,35.6,12.6,12.8,"6・5・8",True),
 ("8/12", 5,"不",16,36.6,12.6,13.2,"3・6・9",True),
 ("7/20", 6,"良",12,37.0,12.7,13.5,"3・7・8",True),
]

trs="".join(
 f'<tr class="{"hi" if h else ""}"><td>{d}</td><td>{r}R</td><td>{b}</td><td>{n}</td>'
 f'<td>{f3}</td><td class="key">{l2}</td><td>{l1}</td><td class="l">{p}</td>'
 f'<td class="{"y" if h else "n"}">{"後方が混ざった" if h else "前で決着"}</td></tr>'
 for d,r,b,n,f3,l2,l1,p,h in ROWS)

html = f'''<!doctype html><html><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; font-family:'WenQuanYi Zen Hei',sans-serif; }}
  body {{ background:#eef2f6; }}
  .card {{ width:1400px; background:#eef2f6; padding:26px 30px 22px; }}
  .hd {{ background:linear-gradient(135deg,#2f6fb0 0%,#1d5490 100%); border-radius:16px;
        padding:22px 32px 20px; color:#fff; margin-bottom:18px; }}
  .hd .k {{ color:#ffd83b; font-size:18px; font-weight:900; }}
  .hd h1 {{ font-size:42px; font-weight:900; margin-top:4px; letter-spacing:1px; }}
  .hd .s {{ font-size:20px; font-weight:800; color:#cfe6fa; margin-top:7px; }}
  .box {{ background:#fff; border-radius:16px; overflow:hidden; box-shadow:0 5px 16px rgba(0,0,0,.09); margin-bottom:18px; }}
  .bh {{ color:#fff; padding:14px 24px; display:flex; align-items:baseline; gap:16px; }}
  .bh b {{ font-size:34px; font-weight:900; }}
  .bh span {{ font-size:21px; font-weight:800; }}
  table {{ width:100%; border-collapse:collapse; table-layout:fixed; }}
  th {{ background:#f2f5f8; color:#41566b; font-size:17px; font-weight:800; padding:8px 2px; border:1px solid #e2e8ee; }}
  td {{ text-align:center; font-size:28px; font-weight:900; color:#1d3a5c; padding:10px 2px; border:1px solid #e2e8ee; }}
  td.sg {{ font-size:14px; font-weight:800; color:#5d7186; padding:6px 2px; }}
  .tops {{ padding:10px 26px 2px; }}
  .tp {{ display:flex; align-items:baseline; gap:14px; padding:5px 0; }}
  .tp .f {{ color:#c92a2a; font-size:22px; font-weight:900; flex:0 0 56px; }}
  .tp .hn {{ color:#1d3a5c; font-size:25px; font-weight:900; flex:0 0 340px; }}
  .tp .pp {{ color:#a8420a; font-size:20px; font-weight:900; flex:0 0 110px; }}
  .tp .cn {{ color:#0a58a6; font-size:22px; font-weight:900; flex:0 0 160px; }}
  .tp .ag {{ color:#5d7186; font-size:19px; font-weight:800; }}
  .read {{ margin:8px 26px 20px; background:#f6f9fc; border-left:7px solid #2f6fb0; border-radius:10px;
          padding:14px 20px; color:#33465a; font-size:21px; font-weight:700; line-height:1.7; }}
  .read b {{ color:#c92a2a; }}

  .verdict {{ background:#0e3b66; border-radius:16px; padding:20px 28px; color:#fff;
              font-size:24px; font-weight:900; line-height:1.65; margin-bottom:18px; }}
  .verdict .y {{ color:#ffd83b; }} .verdict .c {{ color:#8fe3ff; }}
  .verdict .sub {{ font-size:19px; font-weight:800; color:#cfe6fa; margin-top:9px; line-height:1.6; }}

  .tbl {{ background:#fff; border-radius:16px; padding:20px 26px 22px; box-shadow:0 5px 16px rgba(0,0,0,.09); }}
  .tbl h2 {{ font-size:23px; font-weight:900; color:#1d3a5c; margin-bottom:12px;
             padding-left:12px; border-left:7px solid #2f6fb0; }}
  .tbl h2 small {{ font-size:16px; color:#6b7f93; font-weight:800; margin-left:10px; }}
  .tbl table {{ table-layout:auto; }}
  .tbl th {{ font-size:16px; }}
  .tbl td {{ font-size:20px; padding:8px 6px; }}
  .tbl td.l {{ text-align:center; color:#0a58a6; }}
  .tbl td.key {{ color:#c92a2a; font-size:24px; }}
  .tbl td.y {{ color:#c92a2a; font-size:17px; }}
  .tbl td.n {{ color:#8a99a8; font-size:17px; }}
  .tbl tr.hi td {{ background:#fffaf0; }}
  .sig {{ text-align:right; color:#8a99a8; font-size:16px; font-weight:800; margin-top:14px; }}
</style></head><body>
<div class="card">
  <div class="hd">
    <div class="k">変態か、変態以外か。 ── AI分析</div>
    <h1>大井1200m　穴が開く条件</h1>
    <div class="s">7/21 9R（前で決着）と 8/12 8R（12番人気が突き抜け）を並べる</div>
  </div>

  {A}
  {B}

  <div class="verdict">🔑 分かれ目は<span class="y">ラスト1F</span>ではなく、<span class="y">その1本前 ── 4コーナー〜直線の区間</span>。
    <div class="sub">前半3Fは35.7 と 35.4 でほぼ同じ。<span class="c">4C〜直線を11.9で締め直せた7/21は前が止まらず、12.5まで緩んだ8/12は4角10番手が届いた。</span>
    ここが緩むと、前は直線でもう一度加速できずにラスト1Fが13.8まで落ちる。</div>
  </div>

  <div class="tbl">
    <h2>4C〜直線が12.4以上に緩んだ8鞍<small>大井1200m・10頭以上・7月開催＋8/12＝20鞍で検証</small></h2>
    <table>
      <tr><th>日付</th><th>R</th><th>馬場</th><th>頭数</th><th>前3F</th><th>4C〜直線</th><th>ラスト1F</th><th>3着内の4角</th><th></th></tr>
      {trs}
    </table>
    <div class="read" style="margin:14px 0 0">この帯に入った<b>8鞍のうち7鞍</b>で、4角8番手以降が3着内に来た。
    12.4より速く通過した12鞍では<b>3鞍だけ</b>。<b>88% 対 25%</b>。<br>
    以前使っていた「ラスト1F 13.5」の線は 75%対33% で、<b>4C〜直線のほうが素直に効く</b>。</div>
  </div>

  <div class="sig">By Claude AI</div>
</div>
</body></html>'''
import sys
open(sys.argv[1],'w',encoding='utf-8').write(html)
print('ok', sys.argv[1])
