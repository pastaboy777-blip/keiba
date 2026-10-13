# -*- coding: utf-8 -*-
"""内から位置を取れそうな馬を拾う。

  python3 scripts/pick_inside_front.py notes/live/2026-10-14/past5.json

条件
  内枠    馬番を頭数で割った相対位置が 0.40 未満
  先行力  近5走の1角位置を頭数で割った相対の中央値が、鞍の中で上位25%
人気は当日にならないと分からないので、人気になりにくさの目安として
前走の着順と近5走の3着内の数を添える。
"""
import json, statistics
import sys
p5=json.load(open(sys.argv[1],encoding='utf-8'))
out=[]
for Rs in sorted(p5,key=int):
    v=p5[Rs]
    ent=v['e']; n=len(ent)
    sen={}
    for e in ent:
        rel=[int(x['cor'].split('-')[0])/float(x['fs'])
             for x in (e.get('runs') or []) if x.get('cor') and x.get('fs')]
        if rel: sen[e['u']]=statistics.median(rel)
    if len(sen)<4: continue
    srt=sorted(sen.items(),key=lambda z:z[1])
    rank={u:i/float(len(srt)) for i,(u,_) in enumerate(srt)}
    for e in ent:
        u=e['u']; uq=(u-1)/float(n)
        if u not in rank: continue
        if rank[u]>=0.25 or uq>=0.40: continue
        runs=e.get('runs') or []
        last=runs[0] if runs else None
        t3=sum(1 for x in runs if x['fin']<=3)
        esc=sum(1 for x in runs if x.get('cor') and int(x['cor'].split('-')[0])==1)
        out.append(dict(R=int(Rs),dist=v.get('dist'),n=n,u=u,nm=e['nm'],
            sen=sen[u],rk=rank[u],uq=uq,
            last=('%d着/%d頭 %s%d'%(last['fin'],last['fs'],last['place'],last['dist'])) if last else '─',
            lastfin=last['fin'] if last else 99, nrun=len(runs), t3=t3, esc=esc,
            wt=(last or {}).get('wt')))
print('■ 内枠（馬番の相対 0.40未満）× 先行力が鞍内上位25%')
print('   %2s %-4s %3s %-16s %5s %5s %4s %5s %s'
      %('R','距離','馬番','馬','先行力','鞍内','逃げ','近走','前走'))
for x in sorted(out,key=lambda z:(z['R'],z['u'])):
    print('   %2dR ダ%4d %3d %-16s %5.2f %4.0f%% %3d回 %d走%d好 %s'
          %(x['R'],x['dist'] or 0,x['u'],x['nm'][:16],x['sen'],100*x['rk'],
            x['esc'],x['nrun'],x['t3'],x['last']))
print('\n■ そのうち前走で3着内に入っていない馬（人気になりにくい側）')
for x in sorted([y for y in out if y['lastfin']>3],key=lambda z:(z['R'],z['u'])):
    print('   %2dR %2d番 %-16s 先行力%4.0f%%  逃げ%d回  近5走の3着内%d  前走 %s  前走馬体重%s'
          %(x['R'],x['u'],x['nm'][:16],100*x['rk'],x['esc'],x['t3'],x['last'],
            ('%dk'%x['wt']) if x['wt'] else '─'))
