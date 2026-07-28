# -*- coding: utf-8 -*-
"""人気パースを修正して★条件を再フィット。
バグ：行内の最後の1-2桁を人気としていたが、人気が「-」の競走では馬番を拾っていた。
修正：着順・枠・馬番の3トークンを除いた残りの最後の1-2桁。無ければ人気不明として除外。"""
import re,glob
from collections import Counter
exec(open('zenso.py').read().split('rows=[]')[0])
def res(fp):
    t=open(fp,encoding='utf-8',errors='replace').read()
    y=re.sub(r'<[^>]+>','|',t); y=re.sub(r'[ 　]+',' ',y); y=re.sub(r'\|{3,}','||',y)
    i=y.find('着順'); j=y.find('■|払戻金')
    if i<0 or j<=i: return {}
    seg=re.sub(r'\s+',' ',y[i:j])
    hits=[(m.start(),int(m.group(1)),int(m.group(3))) for m in re.finditer(r'\|(\d{1,2})\| \|(\d{1,2})\| \|(\d{1,2})\| \|',seg)]
    o={}
    for k,(pos,ch,ub) in enumerate(hits):
        b=seg[pos:(hits[k+1][0] if k+1<len(hits) else len(seg))]
        n=re.findall(r'\|(\d{1,2})\|',b)
        o[ub]=(ch, int(n[3]) if len(n)>3 else None)   # 0=着順 1=枠 2=馬番 3=人気
    return o
rows=[];noninki=0
files=[(f,'prev/'+f.split('/')[1]) for f in sorted(glob.glob('pcard/*.html'))] + \
      [(f'anat/k728_{r}.html',f'rp728_{r}.html') for r in ['01','02','03','04','05','07','08','09','10','11']]
for cf,rf in files:
    try: c=card(cf); r=res(rf)
    except: continue
    for ub,v in c.items():
        if ub not in r: continue
        ch,nin=r[ub]
        if nin is None: noninki+=1; continue
        rows.append(dict(chaku=ch,ninki=nin,hit=ch<=3,runs=v['runs']))
print(f"有効 {len(rows)}頭（人気非掲載で除外 {noninki}頭）")
ana=[x for x in rows if x['ninki']>=6]
print(f"今回6番人気以下 {len(ana)}頭／3着内 {sum(1 for x in ana if x['hit'])} = {sum(1 for x in ana if x['hit'])/len(ana)*100:.1f}%")
def tab(t,f,order=None):
    tot,hit=Counter(),Counter()
    for x in ana:
        k=f(x)
        if k is None: continue
        tot[k]+=1
        if x['hit']: hit[k]+=1
    N=sum(tot.values()); b=sum(hit.values())/N
    print(f"\n── {t} ── 母数{N}／基準{b*100:.1f}%")
    for k in (order or sorted(tot,key=lambda z:-hit[z]/max(tot[z],1))):
        p=hit[k]/tot[k]
        print(f"  {str(k):<28}{tot[k]:>4}頭 {hit[k]:>3}本 {p*100:>5.1f}%  倍率{p/b:.2f}")
tab("前走着順",lambda x:(None if x['runs'][0]['chaku'] is None else
    ("①前走1-3着" if x['runs'][0]['chaku']<=3 else ("②前走4-5着" if x['runs'][0]['chaku']<=5 else "③前走6着以下"))),
    ["①前走1-3着","②前走4-5着","③前走6着以下"])
def cmb(x):
    c,f=x['runs'][0]['chaku'],x['runs'][0]['front']
    if c is None or f is None: return None
    return f"{'前走1-3着' if c<=3 else ('前走4-5着' if c<=5 else '前走6着以下')} × {'前' if f<=3 else '後'}"
tab("前走着順 × 前走の位置",cmb)
def cmb2(x):
    c,d=x['runs'][0]['chaku'],x['runs'][1]['chaku']
    if c is None or d is None: return None
    return f"前走{'好' if c<=3 else ('中' if c<=5 else '凡')} × 前々走{'好' if d<=3 else ('中' if d<=5 else '凡')}"
tab("前走 × 前々走",cmb2)
