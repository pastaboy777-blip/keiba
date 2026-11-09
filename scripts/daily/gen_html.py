import sys,os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','ana'))
import json,html
o=json.load(open('tomorrow_full.json'))
CIRC='①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯'
def circ(u): return CIRC[u-1] if 1<=u<=16 else str(u)
MK=['◎','○','▲','△','△']
def kata(diff):
    if diff>=15: return ('断トツ','#1f7a3d','#e7f6ec')
    if diff>=8:  return ('堅い','#2e9c5a','#eafaf0')
    if diff>=4:  return ('やや堅','#8a7256','#f6f0e4')
    return ('混戦','#c0392b','#fdecea')
PW={'パ':'🟢パ','ス':'🔵ス','軽':'🔴軽','中':'・'}
rows=''
for rr in range(1,13):
    r=o[str(rr)]; cells=''
    for i in range(5):
        if i<len(r['top']):
            h=r['top'][i]; mk=MK[i]
            val=f"{h['v']:+d}" if h['v']>-900 else '—'
            makuri='<span style=\"color:#c0392b;font-weight:800\"> 巻</span>' if h['mk'] else ''
            cells+=f"<td class='c{ 'a' if i==0 else 'b' if i==1 else 'n'}'><div class='mk'>{mk}</div><div class='nm'><b>{circ(h['ub'])}</b>{html.escape(h['nm'][:8])}</div><div class='sub'><span class='v'>{val}</span> <span class='rl'>{h['role']}</span> {PW.get(h['pw'],'')}{makuri}</div></td>"
        else: cells+="<td class='cn'></td>"
    kt,kc,kb=kata(r['diff'])
    rows+=f"<tr><td class='rc'>{rr}R<small>{r['dist']}m {r['n']}頭</small></td>{cells}<td class='kata' style='color:{kc};background:{kb}'>{kt}<small>①②差+{r['diff']}</small></td></tr>"
htmlpage=f"""<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif;background:#f3ede2;width:1720px;padding:0}}
.hd{{background:#1a1a1a;color:#fff;padding:22px 30px;display:flex;align-items:center;justify-content:space-between}}
.hd h1{{font-size:34px;font-weight:900}}.hd .dt{{color:#bbb;font-size:16px;font-weight:700;margin-left:14px}}
.hd .bd{{background:#c0392b;color:#fff;font-size:16px;font-weight:900;padding:7px 16px;border-radius:8px}}
.note{{background:#c0392b;color:#fff;font-weight:800;font-size:15px;padding:8px 30px}}
table{{border-collapse:collapse;width:100%}}
th{{background:#1f2d4a;color:#fff;font-size:15px;font-weight:800;padding:11px 8px;text-align:left}}
td{{border-bottom:1px solid #e2d9c8;padding:9px 10px;vertical-align:middle}}
.rc{{font-size:20px;font-weight:900;color:#1a1a1a;width:96px}}.rc small{{display:block;font-size:11px;color:#8a7256;font-weight:700}}
.ca{{background:#fdf6e3}}.cb{{background:#eef3fb}}
.mk{{font-size:13px;font-weight:900;color:#c0392b;float:left;margin-right:5px}}
.nm{{font-size:15.5px;font-weight:800;color:#1a1a1a}}.nm b{{color:#c0392b;margin-right:3px}}
.sub{{font-size:12px;color:#6b5a44;margin-top:2px;clear:both}}.sub .v{{font-weight:900;color:#1f7a3d}}.sub .rl{{color:#2f6fb0;font-weight:700}}
.kata{{font-size:16px;font-weight:900;width:120px;text-align:center;border-radius:8px}}.kata small{{display:block;font-size:11px;font-weight:700;opacity:.8}}
.foot{{padding:16px 30px;font-size:14px;color:#4a3d2c;line-height:1.7}}.foot b{{color:#c0392b}}
</style>
<div class="hd"><div><span style="font-size:34px;font-weight:900">大井 全12R 指数予想（トップ5）</span><span class="dt">2026-07-23（木）・明日開催</span></div><div class="bd">Engine B（自前計算＝優先）</div></div>
<div class="note">◆ 各レース 指数上位5頭・脚質・血統パワー軸・軸の堅さ（①②指数差）　🟢パ=パワー/🔵ス=スピード/🔴軽=切れ　巻=巻き返し妙味</div>
<table><tr><th>R</th><th>◎ 指数1位</th><th>○ 2位</th><th>▲ 3位</th><th>△ 4位</th><th>△ 5位</th><th>軸の堅さ</th></tr>{rows}</table>
<div class="foot">📝 <b>自前エンジン（Engine B）の値を優先</b>。核＝マキシマム逆算(k=10/par二次式/観測B)、大井過去走ベース。<br>
狙い：<b>12R ⑨スリーレジェンド+67（①②差+14＝準断トツ・地力最上位）</b>／11R ⑥ディキシーガンナー+53（①②差+9・やや堅）／10R ⑬ピースフィールド+60（2400m長距離）。<br>
<b>混戦（赤）は指数だけで頭固定しない</b>→展開・血統(TARGET流)・枠（外消し/内中）で補強。当日は馬場状態と枠傾向で最終補正。</div>"""
open('r_tomorrow.html','w').write(htmlpage); print('html ok',len(htmlpage))
