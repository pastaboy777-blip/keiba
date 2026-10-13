# -*- coding: utf-8 -*-
"""荒れた鞍と、そうでない鞍を、発走前に分かるもので比べる。"""
import glob, json, os, re, statistics, collections
DAYS=sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob('/home/user/keiba/notes/live/*/past5.json')
            if os.path.exists(os.path.join(os.path.dirname(p),'results.json')))
R=[]
for d in DAYS:
    p5=json.load(open('/home/user/keiba/notes/live/%s/past5.json'%d,encoding='utf-8'))
    res=json.load(open('/home/user/keiba/notes/live/%s/results.json'%d,encoding='utf-8'))
    for Rs,r in res.items():
        es=[e for e in r['e'] if str(e.get('f','')).isdigit()]
        ent=(p5.get(Rs,{}).get('e') or [])
        if not es or not ent: continue
        esc=n3=0; pos=[]
        senmap={}
        for e in ent:
            fc=[int(x['cor'].split('-')[0]) for x in (e.get('runs') or []) if x.get('cor')]
            rel=[int(x['cor'].split('-')[0])/float(x['fs']) for x in (e.get('runs') or []) if x.get('cor') and x.get('fs')]
            if rel: senmap[e['u']]=statistics.median(rel)
            if not fc: continue
            m=statistics.median(fc); pos.append(m)
            if m<=3.5: n3+=1
            if sum(1 for x in fc if x==1)>=2: esc+=1
        if len(senmap)<4: continue
        srt=sorted(senmap.items(),key=lambda z:z[1])
        rank={u:i/float(len(srt)) for i,(u,_) in enumerate(srt)}
        ana_sen=sum(1 for e in es if e.get('pop') and int(e['pop'])>=7 and rank.get(e['u'],1)<0.25)
        lap=[float(x) for x in r['lap'].split('-') if x] if r.get('lap') else []
        body=lap[1:] if lap and lap[0]<10 else lap
        h=len(body)//2
        shape=(sum(body[h:])/(len(body)-h)-sum(body[:h])/h) if h else None
        hits=[e for e in es if e.get('pop') and int(e['pop'])>=7 and int(e['f'])<=3]
        ags=sorted(e['ag'] for e in es if e.get('ag'))
        R.append(dict(day=d,R=int(Rs),dist=r['dist'],n=r['n'],place=d,
            esc=esc,n3=n3,r3=n3/float(len(pos)) if pos else 0,anasen=ana_sen,
            shape=shape,are=1 if hits else 0,
            hits=[(e['nm'],int(e['pop']),e.get('c4'),ags.index(e['ag'])+1 if e.get('ag') in ags else None) for e in hits]))
print('■ %d鞍（%d日）／ 荒れた鞍（7番人気以下が3着内）%d鞍 (%.1f%%)'
      %(len(R),len(DAYS),sum(x['are'] for x in R),100.0*sum(x['are'] for x in R)/len(R)))
def rt(g,lab,w=26):
    n=len(g)
    if not n: print('   %-*s   0鞍'%(w,lab)); return
    a=sum(x['are'] for x in g)
    print('   %-*s %3d鞍  荒れ %2d (%5.1f%%)'%(w,lab,n,a,100.0*a/n))
print('\n■ 本物の逃げ馬の数（近5走で1角先頭が2回以上）')
for lo,hi,lab in ((0,0,'0頭'),(1,1,'1頭'),(2,2,'2頭'),(3,99,'3頭以上')):
    rt([x for x in R if lo<=x['esc']<=hi],lab)
print('\n■ 前に行きたい馬の割合（近5走の1角が3番手以内）')
rs=sorted(R,key=lambda z:z['r3']); k=len(rs)//3
rt(rs[:k],'少ない %.2f〜%.2f'%(rs[0]['r3'],rs[k-1]['r3']))
rt(rs[k:2*k],'中')
rt(rs[2*k:],'多い %.2f〜%.2f'%(rs[2*k]['r3'],rs[-1]['r3']))
print('\n■ 人気薄で先行力が鞍内上位25%の頭数')
for lo,hi,lab in ((0,0,'0頭'),(1,1,'1頭'),(2,99,'2頭以上')):
    rt([x for x in R if lo<=x['anasen']<=hi],lab)
print('\n■ 頭数')
for lo,hi,lab in ((0,9,'9頭以下'),(10,12,'10〜12頭'),(13,99,'13頭以上')):
    rt([x for x in R if lo<=x['n']<=hi],lab)
print('\n■ 距離')
for lo,hi,lab in ((0,1000,'〜1000m'),(1100,1300,'1100〜1300m'),(1400,1500,'1400〜1500m'),(1600,9999,'1600m以上')):
    rt([x for x in R if lo<=x['dist']<=hi],lab)
print('\n■ 結果側：ラップの形（1Fあたり後半−前半。大きいほど前傾）')
g=[x for x in R if x['shape'] is not None]
gs=sorted(g,key=lambda z:z['shape']); k=len(gs)//3
rt(gs[:k],'後傾寄り %+.2f〜%+.2f'%(gs[0]['shape'],gs[k-1]['shape']))
rt(gs[k:2*k],'中')
rt(gs[2*k:],'前傾寄り %+.2f〜%+.2f'%(gs[2*k]['shape'],gs[-1]['shape']))
print('\n■ 荒れた鞍で来た人気薄の形')
hs=[h for x in R for h in x['hits']]
c4=[h[2] for h in hs if h[2]]; ag=[h[3] for h in hs if h[3]]
print('   %d頭  4角の中央値 %.0f番手  上り順位の中央値 %.0f位'%(len(hs),statistics.median(c4),statistics.median(ag)))
for lo,hi,lab in ((1,2,'4角1〜2番手'),(3,4,'3〜4番手'),(5,8,'5〜8番手'),(9,99,'9番手〜')):
    print('     %-12s %2d頭 (%.0f%%)'%(lab,sum(1 for x in c4 if lo<=x<=hi),100.0*sum(1 for x in c4 if lo<=x<=hi)/len(c4)))
for lo,hi,lab in ((1,1,'上り1位'),(2,3,'2〜3位'),(4,5,'4〜5位'),(6,99,'6位以下')):
    print('     %-12s %2d頭 (%.0f%%)'%(lab,sum(1 for x in ag if lo<=x<=hi),100.0*sum(1 for x in ag if lo<=x<=hi)/len(ag)))
import sys
OUT = sys.argv[1] if len(sys.argv) > 1 else 'are_races.json'
json.dump(R,open(OUT,'w'),ensure_ascii=False)
print('\n→ %s %d鞍' % (OUT, len(R)))
