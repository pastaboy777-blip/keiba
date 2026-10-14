
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
    meta[r]=dict(start=v[0]['start'],dist=v[0]['dist'],n=v[0]['n'],
                 live=live,dead=[x for x in v if flags(x)])
BIG=[1,2,6,7,9,11]
ANA=[(5,8),(6,9),(6,12),(8,12),(12,12)]
MK=['&#9678;','&#9675;','&#9650;','&#9651;','&middot;']

def card(r):
    m=meta[r]; L=m['live']; cls='big' if r in BIG else 'sml'
    h='<div class="rc '+cls+'">'
    h+='<div class="rh"><span class="rn">'+str(r)+'R</span><span class="rd">'+str(m['dist'])+'m</span>'
    h+='<span class="rt">'+m['start']+'</span>'
    h+='<span class="rz">'+(('<b>勝負</b>　' if cls=='big' else '')+str(len(L))+'/'+str(m['n'])+'頭 残')+'</span></div>'
    for i,z in enumerate(L[:5]):
        cl='p1' if i==0 else ('p2' if i<=2 else 'p3')
        h+='<div class="hr '+cl+'"><span class="mk">'+MK[i]+'</span><span class="ub">'+str(z['ub'])+'</span>'
        h+='<span class="nm">'+H.escape(z['name'])+'</span><span class="jk">'+H.escape((z['jk'] or '')[:5])+'</span>'
        h+='<span class="sc">'+('%+d'%score(z))+'</span></div>'
        if i<=1:
            h+='<div class="wy">'+(' &middot; '.join(why(z)) or '&mdash;')+'</div>'
    if len(L)<5:
        h+='<div class="few">残り'+str(len(L))+'頭。これで全部です</div>'
    h+='</div>'
    return h

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Hiragino Kaku Gothic ProN","Noto Sans JP","IPAPGothic",sans-serif;
 background:#0c0c0e;color:#f2efe9;width:1260px;padding:40px 42px 30px;
 background-image:repeating-linear-gradient(100deg,rgba(255,255,255,.022) 0 3px,transparent 3px 9px)}
.bt{font-size:11.5px;letter-spacing:.18em;color:#9a9288;font-weight:800;margin-bottom:9px}
h1{font-size:60px;font-weight:900;color:#e8362f;line-height:1.02;letter-spacing:-.02em}
h1 small{display:block;font-size:27px;color:#6b645b;margin-bottom:5px}
.sub{font-size:19px;font-weight:800;margin-top:12px}
.sub span{color:#a39b90;font-size:15px;font-weight:700;margin-left:10px}
.lead{font-size:14.5px;color:#cdc6bc;line-height:1.75;margin:15px 0 0;border-left:5px solid #f5d020;padding-left:14px}
.lead b{color:#fff}
.sh{font-size:20px;font-weight:900;margin:32px 0 13px;padding-left:13px;border-left:7px solid #e8362f}
.sh span{font-size:13px;color:#8d867c;font-weight:700;margin-left:11px}
.grid{display:flex;flex-wrap:wrap;gap:13px}
.rc{background:#17161a;border:1px solid #39353d;border-radius:11px;padding:14px 16px 12px;width:calc(33.333% - 9px)}
.rc.big{border-color:#8a2b26;box-shadow:inset 0 0 0 1px #5d201c}
.rc.sml{background:#131216;border-color:#2b2930}
.rh{display:flex;align-items:baseline;gap:9px;border-bottom:1px solid #2b2930;padding-bottom:8px;margin-bottom:8px}
.rn{font-size:24px;font-weight:900;color:#f5d020}
.sml .rn{font-size:20px;color:#8d867c}
.rd{font-size:14px;font-weight:800}
.rt{font-size:11.5px;color:#7e776e;font-weight:700}
.rz{margin-left:auto;font-size:11.5px;color:#8d867c;font-weight:800}
.rz b{color:#e8362f}
.hr{display:flex;align-items:center;gap:8px;padding:3.5px 0}
.mk{flex:none;width:17px;font-size:14px;color:#e8362f;font-weight:900}
.hr.p2 .mk{color:#8d867c}.hr.p3 .mk{color:#4a4752}
.ub{flex:none;width:21px;height:21px;line-height:21px;text-align:center;border-radius:4px;
 background:#2b2930;font-size:12px;font-weight:900}
.hr.p1 .ub{background:#e8362f;color:#fff}
.sml .hr.p1 .ub{background:#4a4752}
.nm{flex:1;font-size:15px;font-weight:900;letter-spacing:-.01em}
.hr.p2 .nm{font-size:13.5px;font-weight:800;color:#c4bcb1}
.hr.p3 .nm{font-size:13px;font-weight:700;color:#8d867c}
.jk{flex:none;font-size:11px;color:#7e776e;font-weight:700}
.sc{flex:none;width:26px;text-align:right;font-size:14px;font-weight:900;color:#f5d020}
.hr.p2 .sc{color:#8d867c;font-size:12.5px}.hr.p3 .sc{color:#5d574f;font-size:12px}
.sml .sc{color:#8d867c}
.wy{font-size:11.5px;color:#ff8a52;font-weight:700;margin:2px 0 6px 25px;line-height:1.5}
.hr.p2+.wy{color:#9a9288;font-size:11px}
.sml .wy{color:#8d867c}
.few{font-size:11px;color:#5d574f;font-weight:700;margin:6px 0 0 25px}
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
.tiles{display:flex;gap:13px}
.tl{flex:1;background:#17161a;border:1px solid #39353d;border-radius:11px;padding:19px 21px 17px}
.tn{font-size:46px;font-weight:900;color:#f5d020;line-height:1}
.tn small{font-size:19px;color:#a39b90}
.tc{font-size:16px;font-weight:900;color:#ff6b63;margin-top:6px}
.tc b{font-size:22px}
.tt{font-size:17px;font-weight:900;margin-top:11px}
.ts{font-size:12.5px;color:#8d867c;font-weight:700;line-height:1.7;margin-top:6px}
.sum{display:flex;align-items:center;gap:16px;background:#e8362f;color:#fff;border-radius:11px;
 padding:16px 22px;margin-top:13px}
.sl{font-size:19px;font-weight:900}
.sl b{font-size:24px}
.sr{margin-left:auto;font-size:13px;font-weight:800;color:#ffd9d7}
.row{display:flex;align-items:center;gap:15px;padding:7px 0}
.row .lb{flex:none;width:138px;text-align:right;font-size:16px;font-weight:900}
.row .lb i{display:block;font-size:11.5px;color:#7e776e;font-weight:700;font-style:normal;margin-top:2px}
.row .tr{flex:1;background:#1c1a20;border-radius:5px;height:30px}
.row .fl{height:100%;border-radius:5px}
.row .vv{flex:none;width:178px;font-size:18px;font-weight:900}
.row .vv i{font-style:normal;font-size:12.5px;color:#7e776e;font-weight:700;margin-left:8px}
.hot{background:linear-gradient(90deg,#ff8a52,#e8362f)}
.cold{background:linear-gradient(90deg,#4a4752,#343139)}
.bb{margin-top:22px;display:flex;justify-content:space-between;font-size:10.5px;
 letter-spacing:.16em;color:#5d574f;font-weight:800;border-top:1px solid #222026;padding-top:11px}
"""
HEAD='<!doctype html><html lang="ja"><head><meta charset="utf-8"><style>'+CSS+'</style></head><body>'

def build(rs, title_small, title, badge, path):
    cards=''.join(card(r) for r in rs)
    nlive=sum(len(meta[r]['live']) for r in rs)
    ntot=sum(meta[r]['n'] for r in rs)
    ana=''
    for r,ub in ANA:
        if r not in rs: continue
        z=[x for x in meta[r]['live'] if x['ub']==ub][0]
        ana+='<tr><td class="ar">'+str(r)+'R</td><td class="au">'+str(ub)+'</td>'
        ana+='<td class="an">'+H.escape(z['name'])+'</td>'
        ana+='<td class="aj">'+H.escape((z['jk'] or '')[:5])+'</td>'
        ana+='<td class="aw">'+' &middot; '.join(why(z))+'</td></tr>'
    d3=[]
    for r in rs:
        for z in meta[r]['dead']:
            if '3' in flags(z): d3.append(str(r)+'R'+str(z['ub'])+' '+z['name'])
    anasec=''
    if ana:
        anasec=('<div class="sh">穴で狙うなら<span>前走の着順は悪いが、最終コーナーで押し上げていた馬</span></div>'
                '<table>'+ana+'</table>')
    killsec=''
    if d3:
        killsec=('<div class="kill"><div class="kt">&#10006;「外を回ると崩れる」で消えた'+str(len(d3))+'頭 &mdash; 人気でも切る</div>'
                 '<div class="kl">'+H.escape('　'.join(d3))+'</div></div>')
    HTML=(HEAD+'<div class="bt">変態か、変態以外か。</div>'
     '<h1><small>'+title_small+'</small>'+title+'</h1>'
     '<div class="sub">10/15（木）川崎　'+badge+'<span>'+str(ntot)+'頭から'+str(ntot-nlive)+'頭を消して、各レース上位5頭</span></div>'
     '<div class="lead">消す基準は3つ。<b>前走が10頭以下／出走間隔75日以上／外を回ると崩れる馬。</b><br>'
     '点数は <b>前走2〜6着・脚を残している・いつも前にいる・最終コーナーで上げる・ラチ沿いを通す</b> の積み上げです。</div>'
     '<div class="sh">'+badge+'<span>赤枠が勝負どころ</span></div><div class="grid">'+cards+'</div>'
     +anasec+killsec+
     '<div class="bb"><span>2026/10/15 川崎 '+badge+' &mdash; 買う馬リスト</span><span>変態か、変態以外か。</span></div>'
     '</body></html>')
    open(path,'w',encoding='utf-8').write(HTML)
    print(path, nlive, '/', ntot)

build([1,2,3,4,5,6],'10/15 川崎 前半','1R〜6R','1R〜6R','/tmp/claude-0/p15a.html')
build([7,8,9,10,11,12],'10/15 川崎 後半','7R〜12R','7R〜12R','/tmp/claude-0/p15b.html')

EV=(HEAD+'<div class="bt">変態か、変態以外か。</div>'
 '<h1><small>10/15 川崎の買い方</small>なぜ、そう消すのか。</h1>'
 '<div class="sub">前日 10/14（水）川崎 全12鞍 136頭の実測<span>この日の数字だけで作っています</span></div>'
 '<div class="lead">前日の川崎は<b>上がり勝負の日</b>でした。位置ではありません。<br>'
 'そしてその上がりの正体は<b>最終コーナーの出口</b>です。ラップを残り距離で揃えると、12鞍すべての最も遅いハロンが'
 '<b>残り1000→800m</b>か<b>残り400→200m</b>のどちらかに集まります。</div>'
 '<div class="sh">消す3つ<span>どれも1着ゼロ</span></div>'
 '<div class="tiles">'
 '<div class="tl"><div class="tn">14<small>頭</small></div><div class="tc">1着 <b>0</b></div>'
 '<div class="tt">前走が10頭以下</div><div class="ts">相手が薄い鞍を勝ち上がってきた馬。3着内も1頭だけ</div></div>'
 '<div class="tl"><div class="tn">17<small>頭</small></div><div class="tc">1着 <b>0</b></div>'
 '<div class="tt">出走間隔75日以上</div><div class="ts">1ヶ月あけは標準。2ヶ月半を超えると走れていない</div></div>'
 '<div class="tl"><div class="tn">12<small>頭</small></div><div class="tc">1着 <b>0</b></div>'
 '<div class="tt">外を回ると崩れる</div><div class="ts">同じ馬の内を通った走りと外を回った走りを比べた差。'
 '1番人気2頭・2番人気2頭が入って全員6着以下</div></div>'
 '</div>'
 '<div class="sum"><span class="sl">3つで <b>31頭</b> 消して、<b>勝ち馬はゼロ</b></span>'
 '<span class="sr">残った105頭に12勝すべて　／　そこから前走2〜6着に絞ると 40頭で7勝・3着内48%</span></div>'
 '<div class="sh">前日は、上がりで決まった<span>位置ではありません</span></div>'
 '<div class="row"><div class="lb">上がり上位25%<i>25頭</i></div><div class="tr"><div class="fl hot" style="width:88%"></div></div><div class="vv">3着内 88%<i>11勝</i></div></div>'
 '<div class="row"><div class="lb">25〜50%<i>33頭</i></div><div class="tr"><div class="fl hot" style="width:36%"></div></div><div class="vv">36%<i>1勝</i></div></div>'
 '<div class="row"><div class="lb">50〜75%<i>35頭</i></div><div class="tr"><div class="fl cold" style="width:6%"></div></div><div class="vv" style="color:#8d867c">6%<i>0勝</i></div></div>'
 '<div class="row"><div class="lb">下位25%<i>43頭</i></div><div class="tr"></div><div class="vv" style="color:#8d867c">0%<i>3着内ゼロ</i></div></div>'
 '<div class="sh">決まったのは最終コーナー<span>1角→2角と向正面の動きは無関係でした</span></div>'
 '<div class="row"><div class="lb">2つ以上 上げた<i>19頭</i></div><div class="tr"><div class="fl hot" style="width:53%"></div></div><div class="vv">3着内 53%<i>4勝</i></div></div>'
 '<div class="row"><div class="lb">1つ上げた<i>19頭</i></div><div class="tr"><div class="fl hot" style="width:37%"></div></div><div class="vv">37%<i>1勝</i></div></div>'
 '<div class="row"><div class="lb">動かず<i>27頭</i></div><div class="tr"><div class="fl hot" style="width:30%"></div></div><div class="vv">30%<i>3勝</i></div></div>'
 '<div class="row"><div class="lb">1つ下げた<i>23頭</i></div><div class="tr"><div class="fl cold" style="width:9%"></div></div><div class="vv" style="color:#8d867c">9%<i>1勝</i></div></div>'
 '<div class="row"><div class="lb">2つ以上 下げた<i>12頭</i></div><div class="tr"></div><div class="vv" style="color:#8d867c">0%<i>3着内ゼロ</i></div></div>'
 '<div class="note">向正面（2角→3角）で押し上げた馬は<b>12頭で3着内8%</b>と、むしろ悪い結果でした。'
 '残り800→600mは前日いちばん速い区間（平均12.05秒）で、そこで動かすと最後に残らない形です。</div>'
 '<div class="bb"><span>2026/10/15 川崎 &mdash; 買い方の根拠</span><span>変態か、変態以外か。</span></div>'
 '</body></html>')
open('/tmp/claude-0/p15c.html','w',encoding='utf-8').write(EV)
print('/tmp/claude-0/p15c.html')

