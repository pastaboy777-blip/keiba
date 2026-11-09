# -*- coding: utf-8 -*-
"""ボス理論が特定種牡馬の産駒に効くかを2つの角度で測る。
 ①再戦一致率：一度負けた相手に、次も負けるか（序列が固定されるか）
 ②Elo残差：Eloが期待する勝率と実際の勝率の差（＋なら格上げ相手に食い込む＝序列を壊す側）
"""
import json,re
from collections import defaultdict
IDX=json.load(open('/home/user/keiba/scripts/ana/h2h_index.json'))
ELO=json.load(open('/home/user/keiba/scripts/ana/h2h_elo.json'))
SIRE=json.load(open('siremap.json'))

def rematch_stats(pred):
    """pred(name)->bool を満たす馬が絡むペアで、初戦の結果が再戦で繰り返された率"""
    same=tot=0
    for key,v in IDX.items():
        a,b=key.split('\t')
        if not (pred(a) or pred(b)): continue
        m=v['m']
        if len(m)<2: continue
        first=m[0][-1]
        for later in m[1:]:
            tot+=1
            if later[-1]==first: same+=1
    return same,tot

def elo_residual(pred):
    """産駒側から見た 実際の勝率 − Elo期待勝率"""
    exp=act=n=0.0
    for key,v in IDX.items():
        a,b=key.split('\t')
        # 産駒がどちら側か
        for me,opp,w,l in ((a,b,v['a'],v['b']),(b,a,v['b'],v['a'])):
            if not pred(me): continue
            if me not in ELO or opp not in ELO: continue
            g=w+l
            if not g: continue
            e=1.0/(1.0+10**((ELO[opp]-ELO[me])/400.0))
            exp+=e*g; act+=w; n+=g
    return (act/n if n else None),(exp/n if n else None),int(n)

def report(label,pred):
    s,t=rematch_stats(pred)
    a,e,n=elo_residual(pred)
    print(f"{label:<26} 再戦一致 {s}/{t}={s/t*100:>5.1f}%" if t else f"{label:<26} 再戦データなし", end="")
    if n: print(f"  ｜ Elo期待{e*100:>5.1f}% 実際{a*100:>5.1f}% 残差{(a-e)*100:+5.1f}pt (n={n})")
    else: print()

ALL=lambda x: True
report("【全馬・基準】",ALL)
NK=set(n for n,s in SIRE.items() if 'ニシケンモノノフ' in s)
report("ニシケンモノノフ産駒",lambda x: x in NK)
print()
from collections import Counter
c=Counter(SIRE.values())
for sire,cnt in c.most_common(12):
    if cnt<12: continue
    S=set(n for n,s in SIRE.items() if s==sire)
    report(f"{sire}({cnt}頭)",lambda x,S=S: x in S)
print("\n── ニシケンモノノフ産駒 個別 ──")
for h in sorted(NK,key=lambda z:-ELO.get(z,0)):
    if h not in ELO: continue
    s,t=rematch_stats(lambda x,h=h: x==h); a,e,n=elo_residual(lambda x,h=h: x==h)
    rm=f"{s}/{t}={s/t*100:.0f}%" if t else "再戦なし"
    print(f"  {h:<16} Elo{ELO[h]:>7.1f}  再戦一致 {rm:<12} 残差{((a-e)*100 if n else 0):+5.1f}pt (n={n})")
