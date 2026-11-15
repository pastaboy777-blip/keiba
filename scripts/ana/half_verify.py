# -*- coding: utf-8 -*-
import re,glob,statistics as st
from collections import Counter,defaultdict
def load(fp):
    t=open(fp,encoding='utf-8',errors='replace').read()
    y=re.sub(r'<[^>]+>','|',t); y=re.sub(r'[ 　]+',' ',y); y=re.sub(r'\|{3,}','||',y)
    i=y.find('着順'); j=y.find('■|払戻金')
    if i<0 or j<=i: return None
    seg=re.sub(r'\s+',' ',y[i:j])
    hits=[(m.start(),int(m.group(1)),int(m.group(3))) for m in re.finditer(r'\|(\d{1,2})\| \|(\d{1,2})\| \|(\d{1,2})\| \|',seg)]
    if not hits: return None
    o=[(ch,ub) for _,ch,ub in hits]
    fy=re.sub(r'\s+',' ',y); tail=re.sub(r'\s+',' ',y[j:j+1500])
    c4=re.search(r'４角\| \|([^|]+)\|',fy)
    san=re.search(r'三連単\| \|[\d\- ]+\| \|([\d,]+) 円',tail)
    return o,(c4.group(1).strip() if c4 else ''),(int(san.group(1).replace(',','')) if san else None)
def cls(c4):
    out,rank={},0
    for tok in re.findall(r'\([^)]*\)|\d+',c4):
        if tok.startswith('('):
            for k,u in enumerate(int(v) for v in re.findall(r'\d+',tok)):
                rank+=1; out[u]=('先頭' if rank==1 else ('ラチ沿い追走' if k==0 else '外を回す'),rank)
        else:
            rank+=1; out[int(tok)]=('先頭' if rank==1 else '単独',rank)
    return out
files=[(f,int(f.split('_')[1][:2])) for f in sorted(glob.glob('prev/*.html'))] + \
      [(f,int(f.split('_')[1][:2])) for f in sorted(glob.glob('rp727_*.html'))] + \
      [(f,int(f.split('_')[1][:2])) for f in sorted(glob.glob('rp728_*.html'))]
G=defaultdict(lambda:[Counter(),Counter(),Counter()]); SAN=defaultdict(list); NR=Counter()
for fp,RR in files:
    d=load(fp)
    if not d: continue
    o,c4,san=d; r=cls(c4)
    h='前半(1-6R)' if RR<=6 else '後半(7-12R)'
    NR[h]+=1
    if san: SAN[h].append(san)
    for ch,ub in o:
        k=r.get(ub,('?',0))[0]
        G[h][0][k]+=1
        if ch<=3: G[h][1][k]+=1
        if ch==1: G[h][2][k]+=1
print("■ 川崎 84R（7/6-7/10 + 7/27 + 7/28）前後半の比較")
for h in ['前半(1-6R)','後半(7-12R)']:
    tot,hit,win=G[h]; N=sum(tot.values()); base=sum(hit.values())/N
    print(f"\n【{h}】{NR[h]}R / {N}頭 / 全体3着内率{base*100:.1f}%")
    print(f"  {'区分':<14}{'頭数':>5}{'1着':>5}{'3着内':>6}{'率':>8}{'倍率':>7}")
    for k in ['先頭','ラチ沿い追走','外を回す','単独']:
        if not tot[k]: continue
        p=hit[k]/tot[k]
        print(f"  {k:<14}{tot[k]:>5}{win[k]:>5}{hit[k]:>6}{p*100:>7.1f}%{p/base:>7.2f}")
    s=SAN[h]
    print(f"  三連単 中央{st.median(s):,.0f}円 / 1万超 {sum(1 for x in s if x>=10000)}/{len(s)} ({sum(1 for x in s if x>=10000)/len(s)*100:.0f}%) / 10万超 {sum(1 for x in s if x>=100000)}")
# 日ごとに前後半の「先頭倍率」を出して再現性を見る
print("\n■ 日ごとの再現性（先頭の倍率）")
byday=defaultdict(lambda:defaultdict(lambda:[Counter(),Counter()]))
for fp,RR in files:
    d=load(fp)
    if not d: continue
    o,c4,_=d; r=cls(c4)
    day=re.search(r'(prev/(\d{8})|rp72(\d)_)',fp)
    key=fp.split('/')[-1].replace('prev/','')[:8] if 'prev/' in fp else ('2026-07-'+fp.split('_')[0][-2:])
    h='前半' if RR<=6 else '後半'
    for ch,ub in o:
        k=r.get(ub,('?',0))[0]
        byday[key][h][0][k]+=1
        if ch<=3: byday[key][h][1][k]+=1
print(f"  {'日':<12}{'前半 先頭倍率':>14}{'後半 先頭倍率':>14}{'前半 外倍率':>13}{'後半 外倍率':>13}")
for day in sorted(byday):
    row=[day]
    for k in ['先頭','外を回す']:
        for h in ['前半','後半']:
            tot,hit=byday[day][h]
            N=sum(tot.values()); b=sum(hit.values())/N if N else 0
            row.append(f"{(hit[k]/tot[k]/b):.2f}" if tot[k] and b else "—")
    print(f"  {row[0]:<12}{row[1]:>14}{row[2]:>14}{row[3]:>13}{row[4]:>13}")
