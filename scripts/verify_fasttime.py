# -*- coding: utf-8 -*-
"""「その日の時計上位」が本当に効くか、手元の全日でまとめて数える。

  python3 scripts/verify_fasttime.py

notes/live/*/ に dayrank.txt と results.json が両方ある日を全部使う。
生の3着内率は人気でほとんど説明がつくので、人気別3着内率からの上振れで見る。
"""
import json, os, re, glob
HEAD=re.compile(r'^■ (\d+)R (\S+) ── (\d+)頭')
ROW=re.compile(r'^\s*(\d+) (.+?)\s+(\d\d/\d\d) (\S+) ([良稍重不]) ／ (\S+?)\s*\(負荷([\d.]+)\) ／ '
               r'([追流])組 (\d+)/(\d+)\s+／ その日 (\d+)/(\d+)\s+／ 同脚色 (\d+)/(\d+)\s+／ (\d+)本')
rows=[]
for d in sorted(glob.glob('/home/user/keiba/notes/live/*/')):
    dr, rs = d+'dayrank.txt', d+'results.json'
    if not (os.path.exists(dr) and os.path.exists(rs)): continue
    day=os.path.basename(d.rstrip('/'))
    CH={}; R=None
    for ln in open(dr,encoding='utf-8'):
        s=ln.rstrip('\n')
        if re.match(r'^■ \d{8} ',s.strip()): continue
        h=HEAD.match(s.strip())
        if h: R=int(h.group(1)); continue
        m=ROW.match(s)
        if m and R: CH[(R,int(m.group(1)))]=(int(m.group(11)),int(m.group(12)))
    res=json.load(open(rs,encoding='utf-8'))
    for Rs,r in res.items():
        for e in r['e']:
            f=str(e.get('f',''))
            if not f.isdigit(): continue
            c=CH.get((int(Rs),e['u']))
            if not c: continue
            rows.append(dict(day=day,R=int(Rs),u=e['u'],nm=e['nm'],fin=int(f),
                pop=int(e['pop']) if str(e.get('pop','')).isdigit() else None,
                c4=e.get('c4'),dp=c[0],dn=c[1]))
BASE={}
for p in range(1,20):
    g=[x for x in rows if x['pop']==p]
    if g: BASE[p]=100.0*sum(1 for x in g if x['fin']<=3)/len(g)
def ud(g,lab,w=22):
    n=len(g)
    if not n: print('   %-*s   0頭'%(w,lab)); return
    t=sum(1 for x in g if x['fin']<=3); w1=sum(1 for x in g if x['fin']==1)
    act=100.0*t/n
    hv=[x for x in g if x['pop'] in BASE]
    exp=sum(BASE[x['pop']] for x in hv)/len(hv) if hv else 0
    print('   %-*s %4d頭 3着内%3d (%5.1f%%) 1着%2d 期待%5.1f%% 上振れ%+5.1fpt'
          %(w,lab,n,t,act,w1,exp,act-exp))
ok=[x for x in rows if x['dn']>=20]
print('■ 調教の順位が取れた %d頭（母数20本以上 %d頭）／ %d日'
      %(len(rows),len(ok),len({x['day'] for x in rows})))
print('\n■ その日の全体での時計順位')
for lo,hi,lab in ((1,1,'その日1位'),(2,3,'2〜3位'),(4,5,'4〜5位'),(6,10,'6〜10位')):
    ud([x for x in ok if lo<=x['dp']<=hi],lab)
print('   ──')
ud([x for x in ok if x['dp']<=3],'3位以内')
ud([x for x in ok if x['dp']<=5],'5位以内')
ud([x for x in ok if x['dp']<=10],'10位以内')
ud([x for x in ok if x['dp']>10],'11位以下')
print('\n■ 人気薄（7番人気以下）だけ')
a=[x for x in ok if x['pop'] and x['pop']>=7]
for lo,hi,lab in ((1,3,'3位以内'),(4,10,'4〜10位'),(11,999,'11位以下')):
    ud([x for x in a if lo<=x['dp']<=hi],lab)
print('\n■ 日ごと（3位以内）')
for day in sorted({x['day'] for x in ok}):
    g=[x for x in ok if x['day']==day and x['dp']<=3]
    if g:
        t=sum(1 for x in g if x['fin']<=3)
        print('   %s  %2d頭 3着内%d (%3.0f%%)  1着%d'%(day[5:],len(g),t,100.0*t/len(g),
              sum(1 for x in g if x['fin']==1)))
print('\n■ 3位以内の馬をぜんぶ')
for x in sorted([y for y in ok if y['dp']<=3],key=lambda z:(z['day'],z['R'])):
    print('   %s %2dR %2d番 %-14s その日%d/%-3d %3s人気 → %2d着'
          %(x['day'][5:],x['R'],x['u'],x['nm'][:14],x['dp'],x['dn'],x['pop'],x['fin']))
