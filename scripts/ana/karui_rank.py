# -*- coding: utf-8 -*-
import re
from collections import defaultdict
exec(open('karui.py').read().split('DAYS=')[0])
def payout(fp):
    t=open(fp,encoding='utf-8',errors='replace').read()
    y=re.sub(r'<[^>]+>','|',t); y=re.sub(r'[ 　]+',' ',y); y=re.sub(r'\|{3,}','||',y)
    j=y.find('■|払戻金'); tail=re.sub(r'\s+',' ',y[j:j+1500])
    m=re.search(r'三連単\| \|[\d\- ]+\| \|([\d,]+) 円',tail)
    return int(m.group(1).replace(',','')) if m else None
DAYS=[('7/27','rp727_%02d.html'),('7/28','rp728_%02d.html'),('7/29','rp729_%02d.html')]
print("── レース内の『軽さ順位』別 3着内率 ──")
print(f"  {'日':<6}{'最軽量':>16}{'2番目に軽い':>16}{'軽い方の半分':>16}{'重い方の半分':>16}")
tot=defaultdict(lambda:[0,0])
for tag,pat in DAYS:
    g=defaultdict(lambda:[0,0])
    for RR in range(1,13):
        o,d=res(pat%RR)
        ws=sorted([(v['w'],ub) for ub,v in o.items() if v['w']])
        n=len(ws)
        if n<6: continue
        for i,(w,ub) in enumerate(ws):
            hit=o[ub]['ch']<=3
            k=("①最軽量" if i==0 else "②2番目" if i==1 else ("③軽い半分" if i< n/2 else "④重い半分"))
            g[k][0]+=1; g[k][1]+=hit; tot[k][0]+=1; tot[k][1]+=hit
    N=sum(x[0] for x in g.values()); H=sum(x[1] for x in g.values()); b=H/N
    row=[]
    for k in ["①最軽量","②2番目","③軽い半分","④重い半分"]:
        n2,h2=g[k]
        row.append(f"{h2}/{n2}={h2/n2*100:.0f}%({h2/n2/b:.2f})" if n2 else "—")
    print(f"  {tag:<6}"+"".join(f"{x:>16}" for x in row))
N=sum(x[0] for x in tot.values()); H=sum(x[1] for x in tot.values()); b=H/N
print(f"  {'3日計':<6}"+"".join(f"{tot[k][1]}/{tot[k][0]}={tot[k][1]/tot[k][0]*100:.0f}%({tot[k][1]/tot[k][0]/b:.2f})".rjust(16) for k in ["①最軽量","②2番目","③軽い半分","④重い半分"]))

print("\n── 7/29：最軽量or2番目の馬が3着内に来たレースと配当 ──")
for RR in range(1,13):
    o,d=res('rp729_%02d.html'%RR); p=payout('rp729_%02d.html'%RR)
    ws=sorted([(v['w'],ub) for ub,v in o.items() if v['w']])
    rank={ub:i+1 for i,(w,ub) in enumerate(ws)}
    hits=[(o[ub]['ch'],ub,w,rank[ub],o[ub]['nin']) for w,ub in ws if rank[ub]<=2 and o[ub]['ch']<=3]
    if hits:
        s=" / ".join(f"{ch}着 {ub}番 {w}kg(軽さ{r}位) {nk}人気" for ch,ub,w,r,nk in sorted(hits))
        print(f"  {RR:>2}R ダ{d:>4}m 三連単{p:>8,}円  {s}")
