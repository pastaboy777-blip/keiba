"""上がり指数の土台を検証：大井で①上がり最速(1位)馬 ②逃げ(4角先頭)馬 の複勝率。
キャッシュ済み大井seiseki全部（回10+7/20+7/21）。上がり3F=人気の直前(\d\d.\d)、4角先頭=corner grank==1。
"""
import re, os, glob
import monogatari as M
import corner as C
def parse(rid):
    f=os.path.join(M.ARC,f"sei_{rid}.html")
    h=open(f,encoding="utf-8",errors="replace").read()
    rows=[]
    for m in re.finditer(r"<tr[^>]*>(.*?)</tr>",h,re.S):
        row=m.group(1)
        if 'class="umaban"' not in row: continue
        tds=[re.sub(r"<[^>]+>"," ",x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>",row,re.S)]
        if len(tds)<14 or not re.match(r"^\d+$",tds[0]): continue
        ub=int(re.search(r'class="umaban">(\d+)',row).group(1))
        ni=None
        for i in range(13,len(tds)-1):
            if re.match(r"^\d{1,2}$",tds[i]) and re.match(r"^\d{2}\.\d$",tds[i-1]) and re.match(r"^\d{1,3}\.\d$",tds[i+1]): ni=i;break
        agari=float(tds[ni-1]) if ni else None
        rows.append({"ub":ub,"chaku":int(tds[0]),"agari":agari})
    try:
        cs=C.corners(rid); lead=[ub for gr,ln,ub in C.parse_line(cs.get(4,"")) if gr==1]
    except Exception: lead=[]
    return rows,set(lead)
rids=[os.path.basename(f)[4:-5] for f in glob.glob(os.path.join(M.ARC,"sei_*.html"))]
rids=[r for r in rids if len(r)==16 and r[6:8]=="10" and r[:10] in
      ("2026101001","2026101002","2026101003","2026101004","2026101005","2026111001","2026111002")]
ag=[0,0]; ni=[0,0]; allf=[0,0]; nr=0
for rid in rids:
    try: rows,lead=parse(rid)
    except Exception: continue
    if not rows: continue
    nr+=1
    valid=[r for r in rows if r["agari"]]
    if valid:
        best=min(r["agari"] for r in valid)
        for r in valid:
            if abs(r["agari"]-best)<1e-9:
                ag[0]+=1; ag[1]+= 1 if r["chaku"]<=3 else 0
    for r in rows:
        allf[0]+=1; allf[1]+= 1 if r["chaku"]<=3 else 0
        if r["ub"] in lead:
            ni[0]+=1; ni[1]+= 1 if r["chaku"]<=3 else 0
def pc(v): return f"{v[1]}/{v[0]}={v[1]/v[0]*100:.1f}%" if v[0] else "-"
print(f"=== 大井 上がり指数の土台検証（{nr}R）===")
print(f"  ①上がり最速(1位)馬 → 複勝率 {pc(ag)}   （新聞主張:60〜67%）")
print(f"  ②逃げ(4角先頭)馬   → 複勝率 {pc(ni)}   （新聞主張:40%前後）")
print(f"  （参考）全出走馬ベース複勝率 {pc(allf)}")
