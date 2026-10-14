# -*- coding: utf-8 -*-
"""出馬表から、各馬の近5走の騎手と距離を取る（臨戦過程を見るため）。

  python3 scripts/fetch_rinsen.py 20261014 21 6 out.json
                                  日付 場コード 開始R 出力
"""
import json, re, sys, time, datetime
sys.path.insert(0,'/home/user/keiba/src')
from nankeiba.scraping.client import PoliteClient
c=PoliteClient(use_cache=True)
YMD, PLACE = sys.argv[1], sys.argv[2]
R0 = int(sys.argv[3]) if len(sys.argv) > 3 else 1
OUT = sys.argv[4] if len(sys.argv) > 4 else 'rinsen.json'
TODAY = datetime.date(int(YMD[:4]), int(YMD[4:6]), int(YMD[6:]))
def get(u,n=4):
    for i in range(n):
        try: return c.get(u)
        except Exception: time.sleep(2*(i+1))
    return None
def flat(t):
    t=re.sub(r'<[^>]+>','|',t); t=re.sub(r'\|+','|',t); t=re.sub(r'[ \t]+',' ',t)
    t=re.sub(r'\|\s*','|',t); return re.sub(r'\s*\|','|',t)
ENT=re.compile(r'\|([牡牝セ])(\d)\|[^|]*\|([\d.]+)\|\|([^|]+?)\|\|（([^）]*)）')
RUN=re.compile(r'\|([^|\s]+) (\d\d)\.(\d\d)\.(\d\d)\|.*?(\d{3,4})(?:右|左|直)(ダ|芝)\n?(\d+)人\|([^\n|]+)\n([\d.]+)\|',re.S)
idx=get('https://keiba.rakuten.co.jp/race_card/list/RACEID/%s%s00000000'%(YMD,PLACE))
rids=sorted({x for x in re.findall(r'RACEID/(%s%s\d{8})'%(YMD,PLACE),idx) if not x.endswith('00000000')})
p5=json.load(open('/home/user/keiba/notes/live/%s-%s-%s/past5.json'%(YMD[:4],YMD[4:6],YMD[6:]),encoding='utf-8'))
out={}
for rid in rids:
    R=int(rid[-2:])
    if R < R0: continue
    t=flat(get('https://keiba.rakuten.co.jp/race_card/list/RACEID/%s'%rid))
    dm=re.search(r'ダ([\d,]+)m',t); dist=int(dm.group(1).replace(',','')) if dm else 0
    ms=list(ENT.finditer(t))
    names=[e['nm'] for e in p5[str(R)]['e']]
    us=[e['u'] for e in p5[str(R)]['e']]
    rows=[]
    for i,m in enumerate(ms):
        seg=t[m.end(): ms[i+1].start() if i+1<len(ms) else len(t)]
        runs=[]
        for g in RUN.finditer(seg):
            pl,yy,mm,dd,rd,sf,pop,jk,kin=g.groups()
            try: dt=datetime.date(2000+int(yy),int(mm),int(dd))
            except Exception: continue
            runs.append(dict(place=pl.replace('Ｊ',''),date=dt,dist=int(rd),surf=sf,
                             pop=int(pop),jk=jk.strip().lstrip('★☆◇▲△')))
            if len(runs)>=5: break
        rows.append(dict(jk=m.group(4).strip().lstrip('★☆◇▲△'),kin=float(m.group(3)),runs=runs))
    if len(rows)!=len(names):
        print('%2dR 件数が合わない %d vs %d'%(R,len(rows),len(names)))
    for u,nm,r in zip(us,names,rows):
        r['u']=u; r['nm']=nm
    out[R]=dict(dist=dist,rows=rows)
json.dump({str(k):{'dist':v['dist'],'rows':[{**r,'runs':[{**x,'date':x['date'].isoformat()} for x in r['runs']]} for r in v['rows']]} for k,v in out.items()},
          open(OUT,'w'),ensure_ascii=False)
print('■ 10/14 川崎 6R以降 ── 臨戦過程')
for R in sorted(out):
    v=out[R]
    print('\n■ %dR ダ%d'%(R,v['dist']))
    for r in v['rows']:
        rs=r['runs']
        if not rs:
            print('   %2d %-16s %-6s  近走なし'%(r['u'],r['nm'][:16],r['jk'][:6])); continue
        last=rs[0]
        gap=(TODAY-last['date']).days
        same=0
        for x in rs:
            if x['jk']==r['jk'] and x['dist']==v['dist']: same+=1
            else: break
        samejk=sum(1 for x in rs if x['jk']==r['jk'])
        samed=sum(1 for x in rs if x['dist']==v['dist'])
        tag=[]
        if rs[0]['jk']!=r['jk']: tag.append('騎手替')
        if rs[0]['dist']!=v['dist']: tag.append('距離替')
        if rs[0]['place']!='川崎': tag.append('他場から')
        print('   %2d %-16s %-6s 間隔%3d日 連続同騎手同距離%d 近5走で同騎手%d 同距離%d  %s | %s'
              %(r['u'],r['nm'][:16],r['jk'][:6],gap,same,samejk,samed,'・'.join(tag) or '─',
                ' '.join('%s%d/%s%s'%(x['place'][:2],x['dist'],x['jk'][:3],'' if x['surf']=='ダ' else '芝') for x in rs)))

print('\n' + '='*78)
print('■ フレッシュな臨戦過程（同じ騎手で同じ距離を続けていない馬）')
print('   %2s %3s %-16s %-6s %4s %-18s %s'%('R','馬番','馬','騎手','間隔','変化','近5走'))
for R in sorted(out):
    v=out[R]
    for r in v['rows']:
        rs=r['runs']
        if not rs: continue
        gap=(TODAY-rs[0]['date']).days
        same=0
        for x in rs:
            if x['jk']==r['jk'] and x['dist']==v['dist']: same+=1
            else: break
        tag=[]
        if rs[0]['jk']!=r['jk']: tag.append('騎手替')
        if rs[0]['dist']!=v['dist']: tag.append('距離替')
        if rs[0]['place']!='川崎': tag.append('他場')
        if same==0 and ('騎手替' in tag or '距離替' in tag):
            print('   %2dR %3d %-16s %-6s %3d日 %-18s %s'
                  %(R,r['u'],r['nm'][:16],r['jk'][:6],gap,'・'.join(tag),
                    ' '.join('%s%d/%s'%(x['place'][:2],x['dist'],x['jk'][:3]) for x in rs[:3])))

print('\n■ 逆に、同じ騎手で同じ距離を続けている馬（3走以上）')
for R in sorted(out):
    v=out[R]
    for r in v['rows']:
        rs=r['runs']
        if not rs: continue
        same=0
        for x in rs:
            if x['jk']==r['jk'] and x['dist']==v['dist']: same+=1
            else: break
        if same>=3:
            gap=(TODAY-rs[0]['date']).days
            print('   %2dR %3d %-16s %-6s 同騎手同距離 %d走連続  間隔%3d日'
                  %(R,r['u'],r['nm'][:16],r['jk'][:6],same,gap))
