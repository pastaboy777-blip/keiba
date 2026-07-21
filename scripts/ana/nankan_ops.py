"""南関版・直線OPS(逆算)：逃げ(4角先頭)の複勝率を 場×距離 別に実測＝コース別"逃げ有利度"。
キャッシュ済み地方seiseki全部(大井10/川崎11/船橋12/浦和13)。最終直線が短い場ほど逃げ有利のはず。
"""
import re, os, glob
from collections import defaultdict
import monogatari as M
import corner as C
JYO={"10":"大井","11":"川崎","12":"船橋","13":"浦和"}
STR={"大井":"内286/外386","川崎":"約300","船橋":"約308","浦和":"約220(短)"}  # 最終直線(m)参考
def parse(rid):
    h=open(os.path.join(M.ARC,f"sei_{rid}.html"),encoding="utf-8",errors="replace").read()
    tt=re.sub(r"<[^>]+>"," ",h)
    md=re.search(r"(\d{3,4})m",tt); dist=int(md.group(1)) if md else None
    rows=[]
    for m in re.finditer(r"<tr[^>]*>(.*?)</tr>",h,re.S):
        row=m.group(1)
        if 'class="umaban"' not in row: continue
        tds=[re.sub(r"<[^>]+>"," ",x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>",row,re.S)]
        if len(tds)<14 or not re.match(r"^\d+$",tds[0]): continue
        ub=int(re.search(r'class="umaban">(\d+)',row).group(1))
        rows.append({"ub":ub,"chaku":int(tds[0])})
    try: lead=set(ub for gr,ln,ub in C.parse_line(C.corners(rid).get(4,"")) if gr==1)
    except Exception: lead=set()
    return dist,rows,lead
agg=defaultdict(lambda:[0,0])   # (場,距離)->[逃げ数, 逃げ複勝]
base=defaultdict(lambda:[0,0])  # (場,距離)->[全頭, 全複勝]
for f in glob.glob(os.path.join(M.ARC,"sei_*.html")):
    rid=os.path.basename(f)[4:-5]
    if len(rid)!=16 or rid[6:8] not in JYO: continue
    try: dist,rows,lead=parse(rid)
    except Exception: continue
    if not dist or not rows: continue
    k=(JYO[rid[6:8]],dist)
    for r in rows:
        base[k][0]+=1; base[k][1]+= 1 if r["chaku"]<=3 else 0
        if r["ub"] in lead:
            agg[k][0]+=1; agg[k][1]+= 1 if r["chaku"]<=3 else 0
print("=== 南関版 直線OPS：場×距離別『逃げ(4角先頭)複勝率』＝逃げ有利度 ===")
print(f"{'場':<4}{'距離':>6}{'最終直線':>12}{'逃げ複勝':>12}{'全体複勝(参考)':>14}")
for k in sorted(agg, key=lambda x:(x[0],x[1])):
    n,f=agg[k]; bn,bf=base[k]
    if n>=5:
        print(f"{k[0]:<4}{k[1]:>5}m{STR.get(k[0],'?'):>12}  {f}/{n}={f/n*100:>4.0f}%   {bf}/{bn}={bf/bn*100:>3.0f}%")
