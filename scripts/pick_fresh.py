# -*- coding: utf-8 -*-
"""繰り返しを続けてきた馬が、今日それを崩すかどうかで絞る。

  python3 scripts/pick_fresh.py rinsen.json 2026-10-14
"""
import json, datetime
import sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
TODAY=datetime.date.fromisoformat(sys.argv[2])
def run(rs):
    """近走の先頭から数えた、同じ騎手／同じ距離の連続数"""
    jk=0
    for x in rs:
        if x['jk']==rs[0]['jk']: jk+=1
        else: break
    dd=0
    for x in rs:
        if x['dist']==rs[0]['dist']: dd+=1
        else: break
    return jk,dd
rows=[]
for Rs in sorted(d,key=int):
    v=d[Rs]
    for r in v['rows']:
        rs=r['runs']
        if len(rs)<3: continue
        jk,dd=run(rs)
        chg_j = rs[0]['jk']!=r['jk']
        chg_d = rs[0]['dist']!=v['dist']
        gap=(TODAY-datetime.date.fromisoformat(rs[0]['date'])).days
        away=sum(1 for x in rs[:3] if x['place']!='川崎')
        rep=max(jk,dd)
        if rep>=3 and (chg_j or chg_d):
            rows.append((int(Rs),r['u'],r['nm'],r['jk'],v['dist'],jk,dd,chg_j,chg_d,gap,away,rs))
print('■ %s ── 繰り返してきたものが今日崩れる馬' % TODAY)
print('   同じ騎手か同じ距離を3走以上続けてきて、今日そこが替わる')
print()
print('   %2s %3s %-16s %-6s %-5s %-14s %4s %s'%('R','馬番','馬','今日の騎手','今日','崩れるもの','間隔','近5走'))
for R,u,nm,jk,dist,cj,cd,chg_j,chg_d,gap,away,rs in sorted(rows,key=lambda z:(-max(z[5],z[6]),z[0],z[1])):
    what=[]
    if chg_j and cj>=3: what.append('同騎手%d走→替'%cj)
    elif chg_j: what.append('騎手替')
    if chg_d and cd>=3: what.append('同距離%d走→替'%cd)
    elif chg_d: what.append('距離替')
    print('   %2dR %3d %-16s %-6s %4dm %-14s %3d日 %s'
          %(R,u,nm[:16],jk[:6],dist,'・'.join(what),gap,
            ' '.join('%s%d/%s'%(x['place'][:2],x['dist'],x['jk'][:3]) for x in rs[:4])))
print()
print('   ── そのうち直近3走に他場を挟んでいる馬（使って動いている）')
for R,u,nm,jk,dist,cj,cd,chg_j,chg_d,gap,away,rs in sorted(rows,key=lambda z:(z[0],z[1])):
    if away>=1 and gap<=40:
        print('   %2dR %3d %-16s 間隔%3d日 他場%d走'%(R,u,nm[:16],gap,away))
