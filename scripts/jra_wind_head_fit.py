"""直線の向かい風(models/course_straight.json に投影)でペース3区分が当たりやすくなるか。前半で係数、後半で検証 → models/wind_head.json"""
import json,sys
sys.path.insert(0,'scripts'); sys.path.insert(0,'src')
from jra_wind_choku import head_cross
from jra_pace_model import PaceModel
from nankeiba.scraping.db_race import pace_of
raw=[json.loads(l) for l in open('data/jra/races.jsonl')]
raw=[d for d in raw if d.get('surface') in ('芝','ダ') and pace_of(d.get('lap') or [],d['distance']) and d['result'][0].get('time')]
raw.sort(key=lambda d:(d['date'],d['race_id']))
cut=raw[len(raw)//2]['date']
tr=[d for d in raw if d['date']<cut]; te=[d for d in raw if d['date']>=cut]
pm=PaceModel().fit(tr)
v=sorted(pace_of(d['lap'],d['distance'])['diff'] for d in tr); q=(v[len(v)//3],v[2*len(v)//3])
cl=lambda x:'H' if x<q[0] else ('S' if x>q[1] else 'M')
def rows(ds):
    o=[]
    for d in ds:
        hc=head_cross(d['place'],d['date'],int(d['race_id'][-2:]))
        o.append((d, hc[0] if hc else 0.0, pace_of(d['lap'],d['distance'])['diff'], pm.predict(d)))
    return o
R=rows(tr); T=rows(te)
coef={}
for sf in ('芝','ダ'):
    xs=[(h,a-p) for d,h,a,p in R if d['surface']==sf]
    sxx=sum(h*h for h,_ in xs); sxy=sum(h*r for h,r in xs); coef[sf]=sxy/sxx
print('係数(前後差/向かい1m)',coef)
for lab,f in (('風なし',lambda d,h:0),('風あり',lambda d,h:coef[d['surface']]*max(-6,min(6,h)))):
    ok=sum(cl(p+f(d,h))==cl(a) for d,h,a,p in T); 
    big=[(d,h,a,p) for d,h,a,p in T if abs(h)>=3]
    okb=sum(cl(p+f(d,h))==cl(a) for d,h,a,p in big)
    print(lab, f'全体 {ok/len(T):.3f} (n={len(T)})  風3m+の鞍 {okb/len(big):.3f} (n={len(big)})')
json.dump({'coef_diff_per_head':coef,'cut':cut},open('models/wind_head.json','w'),ensure_ascii=False)
