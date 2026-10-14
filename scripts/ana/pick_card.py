
import json, html as H
J=json.load(open('/tmp/claude-0/pick15.json'))
def flags(z):
    ng=[]
    if z['pn'] and z['pn']<=10: ng.append('1')
    if z['gap'] and z['gap']>=75: ng.append('2')
    if z['lg'] is not None and z['lg']>=0.20: ng.append('3')
    return ng
def score(z):
    s=0
    if z['pchaku'] and 2<=z['pchaku']<=6: s+=2
    if z['edge'] is not None and 0.5<=z['edge']<1.5: s+=2
    if z['prel'] is not None and z['prel']<0.30: s+=2
    elif z['prel'] is not None and z['prel']>=0.65: s-=2
    if z['fc'] is not None and z['fc']<=-0.5: s+=1
    if z['inn']>=3: s+=1
    if z['edge'] is not None and z['edge']>=1.5: s-=1
    if z['pchaku'] and z['pchaku']==1: s-=1
    if z['pchaku'] and z['pchaku']>=7: s-=1
    return s
def why(z):
    w=[]
    if z['pchaku'] and 2<=z['pchaku']<=6: w.append('前走'+str(z['pchaku'])+'着')
    if z['edge'] is not None and 0.5<=z['edge']<1.5: w.append('脚を残す')
    if z['prel'] is not None and z['prel']<0.30: w.append('いつも前')
    if z['fc'] is not None and z['fc']<=-0.5: w.append('4角で上げる')
    if z['inn']>=3: w.append('ラチ沿い')
    return w
R={}
for z in J: R.setdefault(z['R'],[]).append(z)
meta={}
for r,v in R.items():
    live=[x for x in v if not flags(x)]
    live.sort(key=lambda t:-score(t))
    meta[r]=dict(start=v[0]['start'],dist=v[0]['dist'],n=v[0]['n'],cond=v[0]['cond'],
                 live=live,dead=[x for x in v if flags(x)])
BIG=[7,6,1,9,11,2]
REST=[12,5,4,8,3,10]
ndead=sum(len(meta[r]['dead']) for r in meta)
ntot=len(J)

def card(r,cls):
    m=meta[r]; L=m['live']
    h='<div class="rc '+cls+'">'
    h+='<div class="rh"><span class="rn">'+str(r)+'R</span><span class="rd">'+str(m['dist'])+'m</span>'
    h+='<span class="rt">'+m['start']+'</span>'
    h+='<span class="rz">'+(('<b>勝負</b>　' if cls=='big' else '')+str(len(L))+'/'+str(m['n'])+'頭 残')+'</span></div>'
    for i,z in enumerate(L[:3]):
        s=score(z)
        mk='&#9678;' if i==0 else ('&#9675;' if i==1 else '&#9651;')
        cl='p1' if i==0 else 'p2'
        h+='<div class="hr '+cl+'"><span class="mk">'+mk+'</span><span class="ub">'+str(z['ub'])+'</span>'
        h+='<span class="nm">'+H.escape(z['name'])+'</span><span class="jk">'+H.escape((z['jk'] or '')[:5])+'</span>'
        h+='<span class="sc">'+('%+d'%s)+'</span></div>'
        if i==0:
            h+='<div class="wy">'+' &middot; '.join(why(z))+'</div>'
    h+='</div>'
    return h

allcards=''.join(card(r,('big' if r in BIG else 'sml')) for r in sorted(meta))

ANA=sorted([(6,12),(6,9),(12,12),(8,12),(5,8)])
ana=''
for r,ub in ANA:
    z=[x for x in meta[r]['live'] if x['ub']==ub][0]
    ana+='<tr><td class="ar">'+str(r)+'R</td><td class="au">'+str(ub)+'</td>'
    ana+='<td class="an">'+H.escape(z['name'])+'</td>'
    ana+='<td class="aj">'+H.escape((z['jk'] or '')[:5])+'</td>'
    ana+='<td class="aw">'+' &middot; '.join(why(z))+'</td></tr>'

dead3=[]
for r in sorted(meta):
    for z in meta[r]['dead']:
        if '3' in flags(z): dead3.append(str(r)+'R'+str(z['ub'])+' '+z['name'])
d3='　'.join(dead3)

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Hiragino Kaku Gothic ProN","Noto Sans JP","IPAPGothic",sans-serif;
 background:#0c0c0e;color:#f2efe9;width:1260px;padding:40px 42px 30px;
 background-image:repeating-linear-gradient(100deg,rgba(255,255,255,.022) 0 3px,transparent 3px 9px)}
.bt{font-size:11.5px;letter-spacing:.18em;color:#9a9288;font-weight:800;margin-bottom:9px}
h1{font-size:66px;font-weight:900;color:#e8362f;line-height:1.02;letter-spacing:-.02em}
h1 small{display:block;font-size:30px;color:#6b645b;margin-bottom:5px}
.sub{font-size:19px;font-weight:800;margin-top:13px}
.sub span{color:#a39b90;font-size:15px;font-weight:700;margin-left:10px}
.lead{font-size:14.5px;color:#cdc6bc;line-height:1.75;margin:15px 0 0;border-left:5px solid #f5d020;padding-left:14px}
.lead b{color:#fff}
.sh{font-size:20px;font-weight:900;margin:34px 0 14px;padding-left:13px;border-left:7px solid #e8362f}
.sh span{font-size:13px;color:#8d867c;font-weight:700;margin-left:11px}
.grid{display:flex;flex-wrap:wrap;gap:13px}
.rc{background:#17161a;border:1px solid #39353d;border-radius:11px;padding:14px 16px 13px}
.rc.big{width:calc(33.333% - 9px);border-color:#8a2b26;box-shadow:inset 0 0 0 1px #5d201c}
.rc.sml{width:calc(33.333% - 9px);background:#131216;border-color:#2b2930}
.rh{display:flex;align-items:baseline;gap:9px;border-bottom:1px solid #2b2930;padding-bottom:8px;margin-bottom:9px}
.rn{font-size:24px;font-weight:900;color:#f5d020}
.rd{font-size:14px;font-weight:800}
.rt{font-size:11.5px;color:#7e776e;font-weight:700}
.rz{margin-left:auto;font-size:11.5px;color:#8d867c;font-weight:800}
.rz b{color:#e8362f;font-size:11.5px}
.hr{display:flex;align-items:center;gap:8px;padding:4px 0}
.mk{flex:none;width:17px;font-size:14px;color:#e8362f;font-weight:900}
.hr.p2 .mk{color:#6b645b}
.ub{flex:none;width:21px;height:21px;line-height:21px;text-align:center;border-radius:4px;
 background:#2b2930;font-size:12px;font-weight:900}
.hr.p1 .ub{background:#e8362f;color:#fff}
.nm{flex:1;font-size:15px;font-weight:900;letter-spacing:-.01em}
.hr.p2 .nm{font-size:13.5px;font-weight:800;color:#b5ada2}
.jk{flex:none;font-size:11px;color:#7e776e;font-weight:700}
.sc{flex:none;width:26px;text-align:right;font-size:14px;font-weight:900;color:#f5d020}
.hr.p2 .sc{color:#6b645b;font-size:12.5px}
.wy{font-size:11.5px;color:#ff8a52;font-weight:700;margin:3px 0 7px 25px;line-height:1.5}
.sml .rn{font-size:20px;color:#8d867c}
.sml .wy{color:#8d867c}
.sml .sc{color:#8d867c}
.sml .hr.p1 .ub{background:#4a4752}
table{width:100%;border-collapse:collapse;margin-top:4px}
td{padding:8px 6px;font-size:14px;border-bottom:1px solid #222026}
.ar{width:46px;color:#f5d020;font-weight:900;font-size:15px}
.au{width:28px;text-align:center;background:#2b2930;border-radius:4px;font-weight:900;font-size:12.5px}
.an{font-weight:900;font-size:15.5px;padding-left:12px}
.aj{width:72px;color:#7e776e;font-weight:700;font-size:12px}
.aw{color:#ff8a52;font-weight:700;font-size:12.5px;text-align:right}
.note{font-size:12.5px;color:#8d867c;line-height:1.85;margin-top:12px}
.note b{color:#ff6b63}
.kill{background:#1b1512;border:1px solid #3a2a22;border-radius:11px;padding:16px 18px;margin-top:14px}
.kill .kt{font-size:15px;font-weight:900;color:#ff6b63;margin-bottom:8px}
.kill .kl{font-size:12.5px;color:#a39b90;font-weight:700;line-height:1.95}
.use{background:#f5d020;color:#141216;border-radius:12px;padding:21px 25px;margin-top:30px}
.use .t{font-size:19px;font-weight:900;margin-bottom:11px}
.use ol{margin-left:21px}
.use li{font-size:15px;font-weight:900;line-height:2.0}
.use li span{font-weight:700;color:#4a4335;font-size:13px}

.tiles{display:flex;gap:13px}
.tl{flex:1;background:#17161a;border:1px solid #39353d;border-radius:11px;padding:17px 19px 15px}
.tn{font-size:40px;font-weight:900;color:#f5d020;line-height:1}
.tn small{font-size:17px;color:#a39b90}
.tc{font-size:15px;font-weight:900;color:#ff6b63;margin-top:5px}
.tc b{font-size:20px}
.tt{font-size:16px;font-weight:900;margin-top:10px}
.ts{font-size:12px;color:#8d867c;font-weight:700;line-height:1.65;margin-top:5px}
.sum{display:flex;align-items:center;gap:16px;background:#e8362f;color:#fff;border-radius:11px;
 padding:14px 20px;margin-top:13px}
.sl{font-size:17px;font-weight:900}
.sl b{font-size:21px}
.sr{margin-left:auto;font-size:12.5px;font-weight:800;color:#ffd9d7}
.row{display:flex;align-items:center;gap:15px;padding:6px 0}
.row .lb{flex:none;width:132px;text-align:right;font-size:15px;font-weight:900}
.row .lb i{display:block;font-size:11px;color:#7e776e;font-weight:700;font-style:normal;margin-top:2px}
.row .tr{flex:1;background:#1c1a20;border-radius:5px;height:27px}
.row .fl{height:100%;border-radius:5px}
.row .vv{flex:none;width:168px;font-size:17px;font-weight:900}
.row .vv i{font-style:normal;font-size:12px;color:#7e776e;font-weight:700;margin-left:8px}
.hot{background:linear-gradient(90deg,#ff8a52,#e8362f)}
.cold{background:linear-gradient(90deg,#4a4752,#343139)}
.bb{margin-top:22px;display:flex;justify-content:space-between;font-size:10.5px;
 letter-spacing:.16em;color:#5d574f;font-weight:800;border-top:1px solid #222026;padding-top:11px}
"""

HTML=('<!doctype html><html lang="ja"><head><meta charset="utf-8"><style>'+CSS+'</style></head><body>'
 '<div class="bt">変態か、変態以外か。</div>'
 '<h1><small>141頭から、</small>41頭を消した。</h1>'
 '<div class="sub">10/15（木）川崎 全12鞍<span>残った100頭を、点数順に並べています</span></div>'
 '<div class="lead">消す基準は3つ。<b>前走が10頭以下／出走間隔75日以上／外を回ると崩れる馬。</b><br>'
 '点数は <b>前走2〜6着・脚を残している・いつも前にいる・最終コーナーで上げる・ラチ沿いを通す</b> の積み上げです。</div>'
 '<div class="sh">1R〜12R<span>赤枠の6鞍が勝負どころ。3Rと10Rは根拠が立ちません</span></div>'
 '<div class="grid">'+allcards+'</div>'
 '<div class="sh">穴で狙うなら<span>前走の着順は悪いが、最終コーナーで押し上げていた馬</span></div>'
 '<table>'+ana+'</table>'
 '<div class="note">明日の穴は<b>「前走の着順が悪くて、でも最終コーナーで押し上げていた馬」</b>に集まります。</div>'
 '<div class="kill"><div class="kt">&#10006;「外を回ると崩れる」で消えた18頭 &mdash; 人気でも切る</div>'
 '<div class="kl">'+H.escape(d3)+'</div></div>'
 '<div class="sh">なぜこの3つで消すのか<span>前日10/14 川崎 全12鞍136頭の実測</span></div>'
 '<div class="tiles">'
 '<div class="tl"><div class="tn">14<small>頭</small></div><div class="tc">1着 <b>0</b></div>'
 '<div class="tt">前走が10頭以下</div><div class="ts">相手が薄い鞍を勝ち上がってきた馬。3着内も1頭だけ</div></div>'
 '<div class="tl"><div class="tn">17<small>頭</small></div><div class="tc">1着 <b>0</b></div>'
 '<div class="tt">出走間隔75日以上</div><div class="ts">1ヶ月あけは標準。2ヶ月半を超えると走れていない</div></div>'
 '<div class="tl"><div class="tn">12<small>頭</small></div><div class="tc">1着 <b>0</b></div>'
 '<div class="tt">外を回ると崩れる</div><div class="ts">同じ馬の内と外を比べた差。1番人気2頭・2番人気2頭が全員6着以下</div></div>'
 '</div>'
 '<div class="sum"><span class="sl">3つで <b>31頭</b> 消して、<b>勝ち馬はゼロ</b></span>'
 '<span class="sr">残った105頭に12勝すべて　／　そこから前走2〜6着に絞ると 40頭で7勝・3着内48%</span></div>'
 '<div class="sh">前日の川崎は、上がりで決まった<span>位置ではありません</span></div>'
 '<div class="row"><div class="lb">上がり上位25%<i>25頭</i></div><div class="tr"><div class="fl hot" style="width:88%"></div></div><div class="vv">3着内 88%<i>11勝</i></div></div>'
 '<div class="row"><div class="lb">25〜50%<i>33頭</i></div><div class="tr"><div class="fl hot" style="width:36%"></div></div><div class="vv">36%<i>1勝</i></div></div>'
 '<div class="row"><div class="lb">50〜75%<i>35頭</i></div><div class="tr"><div class="fl cold" style="width:6%"></div></div><div class="vv" style="color:#8d867c">6%<i>0勝</i></div></div>'
 '<div class="row"><div class="lb">下位25%<i>43頭</i></div><div class="tr"></div><div class="vv" style="color:#8d867c">0%<i>3着内ゼロ</i></div></div>'
 '<div class="note">そしてその上がりの正体は<b>最終コーナーの出口</b>でした。3角→4角で2つ以上押し上げた19頭が3着内53%、'
 '2つ以上下げた12頭は<b>3着内ゼロ</b>。1角→2角と向正面の動きは無関係で、<b>向正面で押し上げた馬はむしろ悪い</b>（12頭で8%）。</div>'

 '<div class="bb"><span>2026/10/15 川崎 &mdash; 買う馬リスト</span><span>変態か、変態以外か。</span></div>'
 '</body></html>')
open('/tmp/claude-0/pick15.html','w',encoding='utf-8').write(HTML)
print('書きました', len(HTML))

