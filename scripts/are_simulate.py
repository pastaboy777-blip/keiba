# -*- coding: utf-8 -*-
"""荒れ方のシミュレーション。

発走前に分かる2つ（人気薄で先行力が鞍内上位の頭数／頭数）で荒れ率を出し、
12鞍の1日を1万回まわす。荒れた鞍の中身は、実際に来た31頭から引く。
"""
import json, random, statistics, collections
import sys, os
SRC = sys.argv[1] if len(sys.argv) > 1 else 'are_races.json'
R=json.load(open(SRC,encoding='utf-8'))
random.seed(7)

def rate(g):
    return (sum(x['are'] for x in g), len(g))

print('■ 発走前の2つで区切る（81鞍）')
print('   %-34s %s'%('','荒れ率'))
cells={}
for a0,a1,la in ((0,0,'人気薄の先行力上位 0頭'),(1,99,'1頭以上')):
    for n0,n1,ln in ((0,11,'11頭以下'),(12,99,'12頭以上')):
        g=[x for x in R if a0<=x['anasen']<=a1 and n0<=x['n']<=n1]
        a,n=rate(g)
        cells[(a0,n0)]=(a,n)
        print('   %-34s %2d/%2d鞍 %5.1f%%'%('%s × %s'%(la,ln),a,n,100.0*a/n if n else 0))

# 鞍ごとの荒れ率（区切りから）
def p_are(x):
    a0=0 if x['anasen']==0 else 1
    n0=0 if x['n']<=11 else 12
    a,n=cells[(a0,n0)]
    return (a+1.0)/(n+2.0)      # ラプラス補正

print('\n■ 1日12鞍を1万回まわす')
for lab,mk in (('いまの開催とおなじ混ざり方',None),
               ('全鞍が「先行力上位の人気薄あり × 12頭以上」',(1,12)),
               ('全鞍が「先行力上位の人気薄なし × 11頭以下」',(0,0))):
    cnt=collections.Counter()
    for _ in range(10000):
        if mk is None:
            day=random.sample(R,12) if len(R)>=12 else R
            ps=[p_are(x) for x in day]
        else:
            a,n=cells[mk]
            ps=[(a+1.0)/(n+2.0)]*12
        k=sum(1 for p in ps if random.random()<p)
        cnt[k]+=1
    tot=sum(cnt.values())
    mean=sum(k*v for k,v in cnt.items())/tot
    print('   %s'%lab)
    print('     荒れ鞍数の平均 %.1f／12  '%mean + ' '.join('%d鞍:%4.1f%%'%(k,100.0*cnt[k]/tot) for k in range(0,7)))
    p0=100.0*cnt[0]/tot
    print('     1鞍も荒れない日 %.1f%%  ／ 4鞍以上荒れる日 %.1f%%'
          %(p0,100.0*sum(v for k,v in cnt.items() if k>=4)/tot))

print('\n■ 荒れた鞍の中身を、ラップの形で分ける')
hs=[]
for x in R:
    for h in x['hits']:
        hs.append((x,h))
for lo,hi,lab in ((-9,0.3,'後傾〜平坦な鞍'),(0.3,0.9,'やや前傾'),(0.9,9,'前傾がきつい鞍')):
    g=[(x,h) for x,h in hs if x['shape'] is not None and lo<=x['shape']<hi]
    if not g: continue
    c4=[h[2] for x,h in g if h[2]]; ag=[h[3] for x,h in g if h[3]]
    f=sum(1 for v in c4 if v<=2); b=sum(1 for v in c4 if v>=5)
    print('   %-14s %2d頭  4角中央値%2.0f番手 上り中央値%2.0f位  逃げ・番手%2d頭 / 後方%2d頭'
          %(lab,len(g),statistics.median(c4),statistics.median(ag),f,b))

print('\n■ 実際に来た31頭（人気の高い順）')
print('   %-7s %3s %-16s %3s %4s %4s'%('日','R','馬','人気','4角','上り'))
for x,h in sorted(hs,key=lambda z:z[1][1]):
    print('   %-7s %2dR %-16s %3d %4s %3s位'%(x['day'][5:],x['R'],h[0][:16],h[1],h[2],h[3]))
