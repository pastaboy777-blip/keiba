import sys,os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','ana'))
import json,html
allr=json.load(open('allres_0722.json'))
def buck(ub,n):
    rel=(ub-1)/(n-1) if n>1 else .5
    return '内' if rel<0.34 else '中' if rel<0.67 else '外'
BC={'内':'#eaf3fb','中':'#eafaf0','外':'#fdecea'}
BT={'内':'#2f6fb0','中':'#2e9c5a','外':'#c0392b'}
arare={3,6,10,11}  # 指数①位圏外で1着
rows=''
for rr in range(1,13):
    dist,n,top=allr[str(rr)]
    cells=''
    for rank,ub,nm in top:
        b=buck(ub,n)
        cells+=f"<td style='background:{BC[b]}'><span class='rk'>{rank}着</span> <b>{ub}</b> {html.escape(nm[:7])} <span class='wk' style='color:{BT[b]}'>{b}</span></td>"
    ar='<span class="ar">荒れ</span>' if rr in arare else ''
    rows+=f"<tr><td class='rc'>{rr}R<small>{dist}m {n}頭</small></td>{cells}<td class='arc'>{ar}</td></tr>"
page=f"""<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif;background:#f3ede2;width:1360px;padding:0}}
.hd{{background:#1a1a1a;color:#fff;padding:20px 28px}}.hd h1{{font-size:30px;font-weight:900}}.hd .dt{{color:#bbb;font-size:15px;font-weight:700;margin-left:12px}}
table{{border-collapse:collapse;width:100%}}
th{{background:#1f2d4a;color:#fff;font-size:14px;font-weight:800;padding:9px;text-align:left}}
td{{border-bottom:1px solid #e2d9c8;padding:8px 10px;font-size:14.5px}}
.rc{{font-size:18px;font-weight:900;width:92px}}.rc small{{display:block;font-size:10.5px;color:#8a7256;font-weight:700}}
.rk{{font-size:11px;color:#8a7256;font-weight:800}}td b{{color:#c0392b}}
.wk{{font-size:11px;font-weight:800;float:right}}
.arc{{width:60px;text-align:center}}.ar{{background:#c0392b;color:#fff;font-size:12px;font-weight:900;padding:2px 8px;border-radius:6px}}
.cards{{display:flex;gap:14px;padding:16px 28px}}
.cd{{flex:1;background:#fff;border-radius:12px;padding:14px 18px;box-shadow:0 2px 8px rgba(120,80,30,.1);border-top:5px solid #c0392b}}
.cd h2{{font-size:15px;font-weight:900;color:#c0392b;margin-bottom:7px}}
.cd p{{font-size:13.5px;color:#33291c;line-height:1.6}}.cd b{{color:#1f7a3d}}.cd .x{{color:#c0392b}}
.foot{{padding:6px 28px 18px;font-size:12.5px;color:#6b5a44;line-height:1.6}}
</style>
<div class="hd"><h1>大井 全12R 結果まとめ<span class="dt">2026-07-22（水）</span></h1></div>
<table><tr><th>R</th><th>1着</th><th>2着</th><th>3着</th><th></th></tr>{rows}</table>
<div class="cards">
  <div class="cd"><h2>📊 指数（Engine B）成績</h2><p>①位が<b>1着 4/12（33%）</b>／<b>3着内 8/12（67%）</b>。<br>複勝軸は強力だが<span class="x">勝ち切りはブレる</span>。<br><span class="x">荒れ4R＝3・6・10・11R</span>は指数圏外が1着。</p></div>
  <div class="cd" style="border-top-color:#2e9c5a"><h2>🟩 枠バイアス（重要）</h2><p>1〜3着36頭：<b>内15・中14</b>・<span class="x">外7（19%）</span>。<br><b>外枠が明確に不利</b>、内〜中が有利。<br>後半は中枠席巻＝<b>12Rは1-2-3着すべて中枠</b>。</p></div>
  <div class="cd" style="border-top-color:#2f6fb0"><h2>🧬 馬場・血統／予想</h2><p>血統は<b>パワー系優勢</b>だが6R後方勝ち・7Rスピード残りで極端でない。<br>我々の予想：<b>8R◎的中・9R◎的中(単)</b>、6R⑧・7R④は穴的中。<br>反省＝<span class="x">「消」の断定と単騎逃げ軽視</span>。</p></div>
</div>
<div class="foot">■ セル背景：内枠=青／中枠=緑／外枠=赤　■ 荒れ＝指数①位が3着圏外で決着したレース　■ 最適解＝<b>指数（軸）×血統・展開（TARGET流）×枠（外消し・内中）</b></div>"""
open('summary_0722.html','w').write(page);print('ok')
