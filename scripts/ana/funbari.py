# -*- coding: utf-8 -*-
"""7/29の砂で「踏ん張れた馬」の条件を洗い出す。
   斤量／間隔（連続使用）／父系／前走で同レンジの上がりを刻んでいたか／位置取り
"""
import re,datetime
from collections import defaultdict
def res(fp):
    t=open(fp,encoding='utf-8',errors='replace').read()
    y=re.sub(r'<[^>]+>','|',t); y=re.sub(r'[ 　]+',' ',y); y=re.sub(r'\|{3,}','||',y)
    i=y.find('着順'); j=y.find('■|払戻金')
    if i<0 or j<=i: return {},'?'
    seg=re.sub(r'\s+',' ',y[i:j])
    h=[(m.start(),int(m.group(1)),int(m.group(3))) for m in re.finditer(r'\|(\d{1,2})\| \|(\d{1,2})\| \|(\d{1,2})\| \|',seg)]
    o={}
    for k,(pos,ch,ub) in enumerate(h):
        b=seg[pos:(h[k+1][0] if k+1<len(h) else len(seg))]
        w=re.search(r'\| (\d{3})\|(±0|[+\-]\d+)',b)
        kg=re.search(r'\|(\d{2}\.\d)\|',b)
        n=re.findall(r'\|(\d{1,2})\|',b)
        o[ub]=dict(ch=ch,w=(int(w.group(1)) if w else None),kg=(float(kg.group(1)) if kg else None),
                   nin=(int(n[3]) if len(n)>3 else None))
    d=re.search(r'ダ\s*([\d,]+)m',re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',t)))
    return o,(d.group(1).replace(',','') if d else '?')
PL=r"(浦和|川崎|大井|船橋|門別|金沢|名古屋|園田|高知|佐賀|水沢|盛岡|笠松)"
def card(fp):
    t=open(fp,encoding='utf-8',errors='replace').read()
    sires={}
    for m in re.finditer(r'class="number">\s*(\d{1,2})\s*<.*?class="name">\s*(.*?)</td>',t,re.S):
        ub=int(m.group(1)); body=re.sub(r'\s+',' ',m.group(2))
        s=re.match(r'\s*([^<]{2,20}?)\s*<br',body); sires[ub]=(s.group(1).strip() if s else '?')
    x=re.sub(r"<script.*?</script>"," ",t,flags=re.S); x=re.sub(r"<[^>]+>","|",x)
    x=re.sub(r"[ 　]+"," ",x); x=re.sub(r"\|{3,}","||",x)
    marks=[a.start() for a in re.finditer(r"\|◎\|",x)]
    o={}
    for k,pos in enumerate(marks):
        pre=x[max(0,pos-90):pos]; nums=re.findall(r"\|\s*(\d+)\s*\|",pre)
        ub=int(nums[-1]) if nums else k+1
        seg=x[pos:(marks[k+1] if k+1<len(marks) else len(x))]
        ag=[float(a) for a in re.findall(r"([\d.]{4}) \d{3}k",seg)]
        runs=re.findall(PL+r" (\d\d)\.(\d\d)\.(\d\d)",seg)
        ds=[]
        for p,y2,m2,d2 in runs:
            try: ds.append(datetime.date(2000+int(y2),int(m2),int(d2)))
            except: pass
        cor=re.findall(r"\|\s*(\d+(?:-\d+){2,3})\s*\|",seg)
        p0=[int(v) for v in cor[0].split("-")] if cor else None
        o[ub]=dict(sire=sires.get(ub,'?'),agari=ag,runs=ds,front=(min(p0[:3]) if p0 else None))
    return o
TODAY=datetime.date(2026,7,29)
G=defaultdict(lambda:defaultdict(lambda:[0,0]))
for RR in range(1,13):
    o,d=res('rp729_%02d.html'%RR); c=card('anat/k729_%02d.html'%RR)
    for ub,v in o.items():
        e=c.get(ub,{})
        hit=v['ch']<=3
        if v['kg']:
            k=("A 〜52.0kg" if v['kg']<=52 else "B 52.1-54.0" if v['kg']<=54 else "C 54.1-55.9" if v['kg']<56 else "D 56.0kg〜")
            G['斤量'][k][0]+=1; G['斤量'][k][1]+=hit
        ds=e.get('runs') or []
        if ds:
            g=(TODAY-ds[0]).days
            k=("A 中2週以内" if g<=17 else "B 中3週(18-27日)" if g<=27 else "C 中4-8週" if g<=59 else "D 休み明け(60日超)")
            G['間隔'][k][0]+=1; G['間隔'][k][1]+=hit
        if len(ds)>=3:
            span=(ds[0]-ds[2]).days
            k=("A 直近3走を60日以内" if span<=60 else "B 3走に61-100日" if span<=100 else "C 間隔が空いている")
            G['使用頻度(直近3走の期間)'][k][0]+=1; G['使用頻度(直近3走の期間)'][k][1]+=hit
        ag=e.get('agari') or []
        if ag and d!='900':
            k=("A 38.9以下のみ" if max(ag[:5])<=38.9 else
               "B 39.0-39.8を持つ" if min(ag[:5])<=39.8 else
               "C 39.9-40.7止まり" if min(ag[:5])<=40.7 else "D 40.8以上")
            G['近走の上がりの持ち駒'][k][0]+=1; G['近走の上がりの持ち駒'][k][1]+=hit
        if e.get('front'):
            k=("A 前走3番手以内" if e['front']<=3 else "B 前走4-6番手" if e['front']<=6 else "C 前走7番手以降")
            G['前走の位置'][k][0]+=1; G['前走の位置'][k][1]+=hit
for title,g in G.items():
    N=sum(x[0] for x in g.values()); H=sum(x[1] for x in g.values()); b=H/N
    print(f"\n── {title} ── 母数{N}／基準{b*100:.1f}%")
    for k in sorted(g):
        n,h=g[k]
        print(f"  {k:<22}{n:>4}頭 {h:>3}本 {h/n*100:>5.1f}%  倍率{h/n/b:.2f}")
