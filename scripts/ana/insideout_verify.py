"""インサイドアウト検証：前走4角で"外"を回した馬は次走で巻き返すか（大井）。
キャッシュ済み大井seiseki(回10=6/29-7/3, 7/20, 7/21)で同一馬の連続出走ペアを作り、
前走4角レーン(内=最内/内寄り, 外=外寄り)で今走の複勝率を比較する。
"""
import re, os, glob
from collections import defaultdict
import monogatari as M
import corner as C

def parse(rid):
    f=os.path.join(M.ARC,f"sei_{rid}.html")
    if not os.path.exists(f): return None
    h=open(f,encoding="utf-8",errors="replace").read()
    rows={}
    for m in re.finditer(r"<tr[^>]*>(.*?)</tr>",h,re.S):
        row=m.group(1)
        if 'class="umaban"' not in row: continue
        tds=[re.sub(r"<[^>]+>"," ",x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>",row,re.S)]
        if len(tds)<14 or not re.match(r"^\d+$",tds[0]): continue
        ub=int(re.search(r'class="umaban">(\d+)',row).group(1))
        cd=re.search(r"/db/uma/(\d+)",row)
        ni=None
        for i in range(13,len(tds)-1):
            if re.match(r"^\d{1,2}$",tds[i]) and re.match(r"^\d{2}\.\d$",tds[i-1]) and re.match(r"^\d{1,3}\.\d$",tds[i+1]): ni=i;break
        rows[ub]={"chaku":int(tds[0]),"cd":cd.group(1) if cd else None,"nk":int(tds[ni]) if ni else None}
    # 4角レーン
    try:
        cs=C.corners(rid); c4={ub:(gr,ln,fieldn) for (gr,ln,ub),fieldn in zip(C.parse_line(cs.get(4,"")),[0]*99)}
        lanes={ub:ln for gr,ln,ub in C.parse_line(cs.get(4,""))}
        maxln=max(lanes.values()) if lanes else 0
    except Exception:
        lanes={}; maxln=0
    for ub in rows:
        ln=lanes.get(ub)
        rows[ub]["lane4"]=ln
        rows[ub]["outer"]=(ln is not None and maxln>=2 and ln>=2)  # 外寄り(内から3頭目以降)
        rows[ub]["inner"]=(ln is not None and ln<=1)               # 最内〜内2
    return rows

# 対象rid（大井キャッシュ）
rids=[]
for f in glob.glob(os.path.join(M.ARC,"sei_*.html")):
    rid=os.path.basename(f)[4:-5]
    if len(rid)==16 and rid[6:8]=="10" and rid[:4]=="2026" and (rid[:10] in
       ("2026101001","2026101002","2026101003","2026101004","2026101005","2026111001","2026111002")):
        rids.append(rid)
# cd -> [(date, rid, ub, chaku, nk, lane4, outer, inner)]
hist=defaultdict(list)
for rid in rids:
    r=parse(rid)
    if not r: continue
    date=(int(rid[:4]),int(rid[-4:-2]),int(rid[-2:]))
    for ub,v in r.items():
        if v["cd"]: hist[v["cd"]].append((date,rid,ub,v["chaku"],v["nk"],v["lane4"],v["outer"],v["inner"]))
# 連続ペア（前走→今走）
res={"外":[0,0],"内":[0,0]}   # [n, 複勝(3着内)]
pairs=0
for cd,lst in hist.items():
    lst.sort()
    for a,b in zip(lst,lst[1:]):
        # a=前走, b=今走
        if a[5] is None: continue      # 前走4角レーン不明
        cur_fuku=1 if b[3]<=3 else 0
        pairs+=1
        if a[6]: res["外"][0]+=1; res["外"][1]+=cur_fuku
        elif a[7]: res["内"][0]+=1; res["内"][1]+=cur_fuku
print(f"=== インサイドアウト検証（大井 回10+7/20+7/21, 連続出走ペア{pairs}件）===")
for k in ("外","内"):
    n,f=res[k]
    print(f"  前走4角『{k}』通し → 今走複勝率: {f}/{n} = {f/n*100:.1f}%" if n else f"  {k}: データ無")
if res["外"][0] and res["内"][0]:
    lift=(res["外"][1]/res["外"][0])/(res["内"][1]/res["内"][0])
    print(f"\n  ▶ 外/内 リフト = {lift:.2f}倍  → {'外通しに次走妙味アリ(方向一致)' if lift>1.05 else '有意差なし' if lift>0.95 else '逆(内有利)'}")
