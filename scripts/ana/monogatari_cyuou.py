"""中央(JRA)版 近3走『物語』エンジン。
談話源: /cyuou/danwa/0/{rid} (全馬・地方と同形式)。
過去走: /db/uma/{umacd}/kanzen の /cyuou/seiseki/ id を新しい順に。
A型4パターンは地方版 monogatari の grammar_score をそのまま利用。
"""
import subprocess,re,os,sys
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import monogatari as M   # grammar_score/verdict/RANK を再利用
ARC=os.path.join(os.path.dirname(os.path.abspath(__file__)),"cyarc");os.makedirs(ARC,exist_ok=True)
BASE="https://p.keibabook.co.jp"

def _get(url,out):
    if not os.path.exists(out) or os.path.getsize(out)<800:
        subprocess.run(["curl","-s","-L","-K",os.path.join(os.path.dirname(__file__),"kb.conf"),url,"-o",out],check=False)
    return out

def _clean(body):
    t=re.sub(r'<[^>]+>',' ',body);t=re.sub(r'\s+',' ',t).strip()
    t=re.sub(r'\s+\d+\s+\d+\s*$','',t)          # 末尾「着 人気」
    # 【師名】の後 or ――の後 が本文
    mm=re.search(r'】\s*(.+)$',t) or re.search(r'[―—－]{2,}\s*(.+)$',t)
    cm=mm.group(1).strip() if mm else ''
    cm=re.sub(r'\s*\d+(\s+\d+)?\s*$','',cm).strip()
    return cm

def race_danwa(rid):
    f=_get(f"{BASE}/cyuou/danwa/0/{rid}",os.path.join(ARC,f"dw_{rid}.html"))
    h=open(f,encoding='utf-8',errors='replace').read()
    out={}
    for m in re.finditer(r'umacd="(\d+)"(.*?)(?=umacd="|</table>|\Z)',h,re.S):
        cd,body=m.group(1),m.group(2)
        t=re.sub(r'<[^>]+>',' ',body);t=re.sub(r'\s+',' ',t).strip()
        um=re.search(r'umaban">\s*(\d+)',h[max(0,m.start()-260):m.start()])
        nm=re.search(r'([゠-ヿ一-龯ー]{2,})\s+[牡牝セせ騸]',t)
        mk=re.search(r'([◎○▲△☆注消Ｘ×])',t)
        out[cd]={"umaban":int(um.group(1)) if um else None,
                 "name":nm.group(1) if nm else None,
                 "mark":mk.group(1) if mk else "","comment":_clean(body)}
    return out

def horse_recent_rids(umacd,exclude=None,n=2):
    f=_get(f"{BASE}/db/uma/{umacd}/kanzen",os.path.join(ARC,f"uma_{umacd}.html"))
    h=open(f,encoding='utf-8',errors='replace').read()
    ids=set(re.findall(r'/cyuou/seiseki/(\d{12})',h))
    if exclude: ids.discard(exclude)
    # ID文字列の降順=新しい順(年→開催回の順で単調増加)
    return sorted(ids,reverse=True)[:n]

def horse_comment(rid,umacd):
    return race_danwa(rid).get(umacd)

def build(rid):
    today=race_danwa(rid)
    rows=[]
    for cd,info in today.items():
        marks=[info["mark"]];comments=[info["comment"]];arc=[("今走",info["mark"],info["comment"])]
        for prid in horse_recent_rids(cd,exclude=rid,n=2):
            pc=horse_comment(prid,cd)
            if pc: marks.append(pc["mark"]);comments.append(pc["comment"]);arc.append((prid,pc["mark"],pc["comment"]))
            else: arc.append((prid,"","(なし)"))
        sc,tags=M.grammar_score(marks,comments)
        rows.append({"umaban":info["umaban"],"name":info["name"],"umacd":cd,"score":sc,"tags":tags,"arc":arc})
    rows.sort(key=lambda r:(r["umaban"] or 99))
    return rows

if __name__=="__main__":
    rid=sys.argv[1]
    for r in sorted(build(rid),key=lambda x:-x["score"]):
        v=M.verdict(r["score"],r["tags"])
        if v=="-": continue
        print(f"\n{r['umaban']} {r['name']} {v} [{'/'.join(r['tags'])}]")
        for lab,mk,cm in r["arc"]:
            print(f"   {lab[:8]} {mk or '-'} 「{cm[:60]}」")
