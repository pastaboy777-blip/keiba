# -*- coding: utf-8 -*-
"""日ごとに「砂の軽さ」と「大型馬/最軽量馬の成績」が連動するかを見る。
砂の軽さの代理指標＝ダ1400mの勝ち上がり3F中央値（速いほど軽い＝乾いている想定）"""
import re,glob,statistics as st
from collections import defaultdict
def res(fp):
    t=open(fp,encoding='utf-8',errors='replace').read()
    y=re.sub(r'<[^>]+>','|',t); y=re.sub(r'[ 　]+',' ',y); y=re.sub(r'\|{3,}','||',y)
    i=y.find('着順'); j=y.find('■|払戻金')
    if i<0 or j<=i: return {},'?',None,'?'
    seg=re.sub(r'\s+',' ',y[i:j])
    h=[(m.start(),int(m.group(1)),int(m.group(3))) for m in re.finditer(r'\|(\d{1,2})\| \|(\d{1,2})\| \|(\d{1,2})\| \|',seg)]
    o={}
    for k,(pos,ch,ub) in enumerate(h):
        b=seg[pos:(h[k+1][0] if k+1<len(h) else len(seg))]
        w=re.search(r'\| (\d{3})\|(±0|[+\-]\d+)',b)
        o[ub]=dict(ch=ch,w=(int(w.group(1)) if w else None))
    fy=re.sub(r'\s+',' ',y)
    ra=re.search(r'上がり\| \|4F [0-9.]+ - 3F ([0-9.]+)',fy)
    flat=re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',t))
    d=re.search(r'ダ\s*([\d,]+)m',flat); ba=re.search(r'ダ\s*[\d,]+m.{0,40}?(良|稍重|重|不良)',flat)
    return o,(d.group(1).replace(',','') if d else '?'),(float(ra.group(1)) if ra else None),(ba.group(1) if ba else '?')
DAYS=[]
for f in sorted(glob.glob('prev/*.html')):
    DAYS.append((f.split('/')[1][:8],f))
byday=defaultdict(list)
for tag,f in DAYS: byday[tag].append(f)
for tag,pat in (('20260727','rp727_%02d.html'),('20260728','rp728_%02d.html'),('20260729','rp729_%02d.html')):
    byday[tag]=[pat%r for r in range(1,13)]
print(f"{'日':<10}{'馬場':>5}{'ダ1400上3F':>11}{'510kg+':>16}{'最軽量':>16}{'〜449kg':>16}")
rows=[]
for tag in sorted(byday):
    ag14=[]; big=[0,0]; lite=[0,0]; small=[0,0]; tot=[0,0]; baba=[]
    for f in sorted(byday[tag]):
        o,d,ra,ba=res(f)
        if not o: continue
        baba.append(ba)
        if d=='1400' and ra: ag14.append(ra)
        ws=sorted([(v['w'],ub) for ub,v in o.items() if v['w']])
        for i,(w,ub) in enumerate(ws):
            hit=o[ub]['ch']<=3
            tot[0]+=1; tot[1]+=hit
            if w>=510: big[0]+=1; big[1]+=hit
            if w<450: small[0]+=1; small[1]+=hit
            if i==0 and len(ws)>=6: lite[0]+=1; lite[1]+=hit
    if not tot[0]: continue
    b=tot[1]/tot[0]
    def f2(x): return f"{x[1]}/{x[0]}={x[1]/x[0]*100:.0f}%({x[1]/x[0]/b:.2f})" if x[0] else "—"
    from collections import Counter
    bb=Counter(baba).most_common(1)[0][0]
    a=st.median(ag14) if ag14 else None
    print(f"{tag:<10}{bb:>5}{(f'{a:.1f}' if a else '—'):>11}{f2(big):>16}{f2(lite):>16}{f2(small):>16}")
    if a and big[0]>=4: rows.append((tag,a,big[1]/big[0]/b,lite[1]/lite[0]/b if lite[0] else None))
print("\n── ダ1400の上がりが速い日ほど大型馬(510kg+)が沈むか ──")
rows.sort(key=lambda z:z[1])
print(f"  {'日':<10}{'ダ1400上3F':>11}{'510kg+倍率':>12}{'最軽量倍率':>12}")
for tag,a,bb,ll in rows:
    print(f"  {tag:<10}{a:>11.1f}{bb:>12.2f}{(f'{ll:.2f}' if ll else '—'):>12}")
if len(rows)>=4:
    xs=[r[1] for r in rows]; ys=[r[2] for r in rows]
    mx=st.mean(xs); my=st.mean(ys)
    cov=sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    den=(sum((x-mx)**2 for x in xs)*sum((y-my)**2 for y in ys))**0.5
    print(f"\n  相関係数（上がりの速さ × 大型馬倍率）= {cov/den:+.2f}  n={len(rows)}日")
    print("  ＋なら『上がりが遅い日ほど大型馬が走る／速い日ほど沈む』")
