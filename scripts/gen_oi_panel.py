# -*- coding: utf-8 -*-
"""大井の1レースを拡大したラップ画像。使い方: gen_oi.py <json> <日付表記> <R> <読み文> <out>"""
import json, sys
SCR='/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/scratchpad/'
src, label, RNO, read, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5]
D = {d['rno']: d for d in json.load(open(SCR+src))}
d = D[RNO]
# 大井：内回り1周1400m・直線286m ／ 外回り1周1600m・直線386m
# 内回り(286m)を使うのは1600m。1200m・1400m・1800m・2000mは外回り(386m)
COURSE = {1000:("外",386), 1200:("外",386), 1400:("外",386), 1600:("内",286),
          1650:("外",386), 1800:("外",386), 2000:("外",386), 2400:("外",386)}
SEG = {
 1000:["スタート(向正面)","3コーナー","3C〜4C","4C〜直線","直線386m"],
 1200:["スタート(2C出口)","向正面","向正面〜3C","3C〜4C","4C〜直線","直線386m"],
 1400:["スタート(2コーナー)","2C〜向正面","向正面","向正面〜3C","3C〜4C","4C〜直線","直線386m"],
 1600:["スタート(直線)","1コーナー","1C〜2C","2C〜向正面","向正面〜3C","3コーナー","3C〜4C","直線286m"],
 1800:["スタート(直線)","ゴール前〜1C","1コーナー","1C〜2C","2C〜向正面","向正面","向正面〜3C","3C〜4C","直線386m"],
 1650:["スタート(ゴール直前)","ゴール前〜1C","1コーナー","1C〜2C","2C〜向正面","向正面","向正面〜3C","3C〜4C","直線386m"],
 2400:["スタート(3コーナー)","3C〜4C","4C〜直線","直線・ゴール前","ゴール前〜1C","1C〜2C","2C〜向正面","向正面","向正面〜3C","3C〜4C","4C〜直線","直線386m"],
 2000:["スタート(4C出口)","直線・ゴール前","ゴール前〜1C","1コーナー","1C〜2C","2C〜向正面","向正面","向正面〜3C","3C〜4C","直線386m"],
}
def col(s):
    if s.startswith("直線"): return "#e9f5ec"
    if "3C" in s or "4C" in s or "3コーナー" in s or "4コーナー" in s: return "#fcebf0"
    if "向正面" in s: return "#e6f4fb"
    return "#fdf5e0"
laps, dist = d['laps'], d['dist']
v = laps[:]; n = len(v)
segs = SEG.get(dist, ["区間%d"%(i+1) for i in range(n)])
if len(segs) != n: segs = ["区間%d"%(i+1) for i in range(n)]
mawari, chokusen = COURSE.get(dist, ("", 0))
bands = [col(s) for s in segs]
first = dist - 200*(n-1) if dist % 200 else 200
marks = [first + 200*i for i in range(n)]

# 半端ハロン(50m等)はスケールを壊すのでグラフからは外し、表にだけ残す
skip = 1 if dist % 200 else 0
cv, cmarks, cbands = v[skip:], marks[skip:], bands[skip:]
cn = len(cv)
def chart(w=1320, h=520):
    L,R,T,B = 74,20,26,58
    pw,ph = w-L-R, h-T-B
    lo,hi = min(cv)-.40, max(cv)+.40
    X = lambda i: L+pw*(i+.5)/cn
    Y = lambda t: T+ph*(t-lo)/(hi-lo)
    o=[f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}">']
    for i,b in enumerate(cbands):
        o.append(f'<rect x="{L+pw*i/cn:.1f}" y="{T}" width="{pw/cn:.1f}" height="{ph}" fill="{b}"/>')
    for k in range(5):
        t=lo+(hi-lo)*k/4; y=Y(t)
        o.append(f'<line x1="{L}" y1="{y:.1f}" x2="{w-R}" y2="{y:.1f}" stroke="#e2e9f0"/>')
        o.append(f'<text x="{L-10}" y="{y+7:.1f}" text-anchor="end" font-size="19" fill="#8a99a8">{t:.1f}</text>')
    o.append(f'<polyline points="{" ".join(f"{X(i):.1f},{Y(t):.1f}" for i,t in enumerate(cv))}" '
             f'fill="none" stroke="#e6a020" stroke-width="6" stroke-linejoin="round"/>')
    for i,t in enumerate(cv):
        big = t == min(cv)
        o.append(f'<circle cx="{X(i):.1f}" cy="{Y(t):.1f}" r="{13 if big else 9}" fill="{"#c92a2a" if big else "#e6a020"}"/>')
        o.append(f'<text x="{X(i):.1f}" y="{Y(t)-24:.1f}" text-anchor="middle" font-size="{27 if big else 21}" '
                 f'font-weight="900" fill="{"#c92a2a" if big else "#8a6a20"}">{t}</text>')
        o.append(f'<text x="{X(i):.1f}" y="{T+ph+28}" text-anchor="middle" font-size="19" fill="#6b7c8c">{cmarks[i]}m</text>')
    o.append(f'<text x="{L}" y="{h-8}" font-size="17" fill="#8a99a8">通過距離　／　縦軸は上が速い</text>')
    o.append('</svg>')
    return "".join(o)

heads = "".join(f'<th>{marks[i]}m</th>' for i in range(n))
vals  = "".join(f'<td>{t}</td>' for t in v)
tags  = "".join(f'<td class="sg" style="background:{bands[i]}">{segs[i]}</td>' for i in range(n))
tops = "".join(f'<div class="tp"><span class="f">{t[0]}着</span><span class="hn">{t[1]}{t[2]}</span>'
               f'<span class="pp">{t[3]}人気</span><span class="tm">{t[4]}</span>'
               f'<span class="cn">4角{t[6]}番手</span><span class="ag">上がり{t[5]}</span></div>' for t in d['top'])

html = f'''<!doctype html><html><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; font-family:'WenQuanYi Zen Hei',sans-serif; }}
  body {{ background:#eef2f6; }}
  .card {{ width:1400px; background:#eef2f6; padding:28px 30px 24px; }}
  .box {{ background:#fff; border-radius:16px; overflow:hidden; box-shadow:0 5px 16px rgba(0,0,0,.09); }}
  .bh {{ background:#2f6fb0; color:#fff; padding:16px 24px; display:flex; align-items:baseline; gap:16px; }}
  .bh b {{ font-size:40px; font-weight:900; }}
  .bh span {{ font-size:22px; font-weight:800; }}
  table {{ width:100%; border-collapse:collapse; table-layout:fixed; }}
  th {{ background:#f2f5f8; color:#41566b; font-size:18px; font-weight:800; padding:9px 2px; border:1px solid #e2e8ee; }}
  td {{ text-align:center; font-size:30px; font-weight:900; color:#1d3a5c; padding:11px 2px; border:1px solid #e2e8ee; }}
  td.sg {{ font-size:15px; font-weight:800; color:#5d7186; padding:7px 2px; }}
  .tops {{ padding:12px 26px 4px; }}
  .tp {{ display:flex; align-items:baseline; gap:14px; padding:6px 0; }}
  .tp .f {{ color:#c92a2a; font-size:24px; font-weight:900; flex:0 0 60px; }}
  .tp .hn {{ color:#1d3a5c; font-size:26px; font-weight:900; flex:0 0 330px; }}
  .tp .pp {{ color:#5d7186; font-size:20px; font-weight:800; flex:0 0 90px; }}
  .tp .tm {{ color:#5d7186; font-size:20px; font-weight:800; flex:0 0 110px; }}
  .tp .cn {{ color:#0a58a6; font-size:22px; font-weight:900; flex:0 0 150px; }}
  .tp .ag {{ color:#5d7186; font-size:20px; font-weight:800; }}
  .read {{ margin:10px 26px 22px; background:#f6f9fc; border-left:7px solid #2f6fb0; border-radius:10px;
          padding:15px 20px; color:#33465a; font-size:22px; font-weight:700; line-height:1.7; }}
  .read b {{ color:#c92a2a; }}
  .sig {{ text-align:right; color:#8a99a8; font-size:16px; font-weight:800; margin-top:14px; }}
</style></head><body>
<div class="card">
  <div class="box">
    <div class="bh"><b>{RNO}R</b><span>{label} 大井{dist}m・{d['baba']}・{d['n']}頭　勝ち時計 {d['top'][0][4]}　（{mawari}回り・直線{chokusen}m）</span></div>
    <table><tr>{heads}</tr><tr>{vals}</tr><tr>{tags}</tr></table>
    {chart()}
    <div class="tops">{tops}</div>
    <div class="read">{read}</div>
  </div>
  <div class="sig">By Claude AI</div>
</div>
</body></html>'''
open(out,'w',encoding='utf-8').write(html)
print('ok', out)
