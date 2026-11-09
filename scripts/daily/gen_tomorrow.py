import sys,os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','ana'))
import json, monogatari as M, myindex as MI, daikei as D, pedigree_line as P, tenkai_ooi as T
PRE='2026111003'; MMDD='0723'; BEF=(2026,7,23)
DIST={1:1600,2:1200,3:1200,4:1600,5:1200,6:1600,7:1400,8:1200,9:1400,10:2400,11:1200,12:1650}
def role(avg1):
    if avg1<=1.8:return '逃げ'
    if avg1<=3.0:return '先行'
    if avg1<=5.0:return '好位'
    if avg1<=8.0:return '差し'
    return '追込'
out={}
for rr in range(1,13):
    rid=f'{PRE}{rr:02d}{MMDD}'; dist=DIST[rr]
    d=M.race_danwa(rid); ped=P.sires(rid)
    sc=[]
    for cd,info in d.items():
        ub=info.get('umaban')
        if ub is None: continue
        pi=MI.horse_index(cd,dist,before=BEF)
        v=pi['best5'] if pi['best5'] is not None else -999
        k=T.kyakushitsu(cd); rl=role(k['avg1']) if k else '?'
        s=ped.get(cd,{}).get('sire'); pw=D.power(s,ped.get(cd,{}).get('gsire'))
        sc.append({'v':v,'ub':ub,'nm':info['name'],'b2':pi['best2'],'b10':pi['best10'],'mk':pi['makuri'],'role':rl,'pw':pw})
    sc.sort(key=lambda x:x['v'],reverse=True)
    diff=(sc[0]['v']-sc[1]['v']) if len(sc)>1 else 0
    out[rr]={'dist':dist,'n':len(sc),'diff':diff,'top':sc[:5]}
json.dump(out,open('tomorrow_full.json','w'),ensure_ascii=False)
print('DONE',{rr:(out[rr]['top'][0]['ub'],out[rr]['top'][0]['nm'],out[rr]['diff']) for rr in out})
