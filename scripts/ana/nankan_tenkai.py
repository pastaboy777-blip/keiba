# -*- coding: utf-8 -*-
"""南関の隊列を、過去走だけで自前で組む。

  python3 scripts/ana/nankan_tenkai.py <nankan_raw.jsonl> <card.json> [--from-r 1] [--to-r 12]

11/9の川崎で、当日の見解の「先頭候補」を信じて12頭拾ったら、
実際に4角で上位1/3にいたのは3頭だけだった（中央値0.55）。
一方、過去走から出した「ふだんの4角位置」のほうは、
ふだん前の22頭のうち55%が当日も上位1/3に入り、3着内36%だった。
データが47%しか埋まっていない状態でそれなので、自前で組み直す。

出すもの（どれも過去走の中央値。鞍の中で相対化する）
  位置   最終コーナーの正規化順位         0が先頭・1.00が最後方
  ぶれ   その標準偏差                   小さいほど毎回同じ位置
  終い   自身の上り3F − レースの後半3F   マイナスほど速い
  本数   材料にした走りの数（3走未満は判定しない）

11/9の川崎で好走した人気薄7頭は、4角で前(0.00〜0.27)が4頭、
後ろ(0.73〜1.00)が3頭。中1/3の27頭は全滅だった。
だから「前か後ろかに振り切れているか」を見る。
"""
import json
import re
import statistics as st
import sys
from collections import defaultdict

SRC, CARD = sys.argv[1], sys.argv[2]
FR = int(sys.argv[sys.argv.index('--from-r') + 1]) if '--from-r' in sys.argv else 1
TO = int(sys.argv[sys.argv.index('--to-r') + 1]) if '--to-r' in sys.argv else 12
BA = sys.argv[sys.argv.index('--ba') + 1] if '--ba' in sys.argv else None
YMD = sys.argv[sys.argv.index('--before') + 1] if '--before' in sys.argv else '99999999'


def groups(s):
    """括弧の中は同じ順位。並びは内→外（実データで確かめた）"""
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == '(':
            j = s.find(')', i)
            g = [int(x) for x in re.findall(r'\d+', s[i:j + 1])]
            if g:
                out.append(g)
            i = j + 1
        elif c.isdigit():
            j = i
            while j < len(s) and s[j].isdigit():
                j += 1
            out.append([int(s[i:j])])
            i = j
        else:
            i += 1
    return out


H = defaultdict(list)
for l in open(SRC, encoding='utf-8'):
    r = json.loads(l)
    if r['ymd'] >= YMD:
        continue
    ent = [e for e in r['e'] if str(e.get('f', '')).isdigit()]
    n = len(ent)
    if n < 6:
        continue
    pos, out, rank = {}, {}, 1
    for g in groups(r.get('c4') or ''):
        for i, u in enumerate(g):
            pos[u] = (rank - 1) / (n - 1)
            out[u] = (i / (len(g) - 1)) if len(g) > 1 else None
        rank += len(g)
    lap = r.get('lap') or []
    l3 = sum(lap[-3:]) if len(lap) >= 3 else None
    for e in ent:
        u = int(e['u'])
        if u not in pos:
            continue
        ag = float(e['ag']) if re.match(r'^[\d.]+$', e.get('ag') or '') else None
        H[e['nm']].append(dict(ymd=r['ymd'], ba=r['ba'], dist=r.get('dist'),
                               baba=r.get('baba'), n=n, f=int(e['f']),
                               pop=e.get('pop'), c4=pos[u], soto=out[u],
                               gap=(ag - l3) if (ag is not None and l3) else None))

C = json.load(open(CARD, encoding='utf-8'))


def waku(u, n):
    base, rem = divmod(n, 8)
    cnt = [base + (1 if (8 - i) < rem else 0) for i in range(1, 9)]
    s = 0
    for i, c in enumerate(cnt, 1):
        s += c
        if u <= s:
            return i
    return 8


for R in range(FR, TO + 1):
    r = C.get(str(R))
    if not r:
        continue
    V = []
    for e in r['e']:
        v = H.get(e['nm'], [])[:8]
        if len(v) < 3:
            V.append(dict(e=e, pos=None, n=len(v)))
            continue
        g = [x['gap'] for x in v if x['gap'] is not None]
        so = [x['soto'] for x in v if x['soto'] is not None]
        V.append(dict(e=e, n=len(v), use=v,
                      pos=st.median(x['c4'] for x in v),
                      sd=st.pstdev([x['c4'] for x in v]),
                      gap=(st.median(g) if g else None),
                      soto=(st.median(so) if so else None)))
    ok = [x for x in V if x['pos'] is not None]
    print(f"\n═══ {R}R {r.get('surf','ダ')}{r['dist']}m {r['n']}頭 "
          f"── 過去走がわかる {len(ok)}/{len(r['e'])}頭 " + '═' * 16)
    if not ok:
        continue
    mp = st.median(x['pos'] for x in ok)
    gs = [x['gap'] for x in ok if x['gap'] is not None]
    mg = st.median(gs) if gs else None
    print(f"  この鞍の物差し：位置の中央値 {mp:.2f}"
          + (f"　終いの中央値 {mg:+.2f}秒" if mg is not None else ''))
    print(f"  {'番':>3} {'馬名':<14}{'枠':>3}{'位置':>7}{'ぶれ':>6}{'終い':>7}{'走':>4}  判定")
    for x in sorted(V, key=lambda y: (y['pos'] is None, y['pos'] or 0)):
        e = x['e']
        w = e.get('waku') if isinstance(e.get('waku'), int) else waku(e['u'], r['n'])
        if x['pos'] is None:
            print(f"  {e['u']:>3} {e['nm']:<14}{w:>3}{'―':>7}{'―':>6}{'―':>7}{x['n']:>4}  材料不足")
            continue
        tag = []
        if x['pos'] <= 1 / 3:
            tag.append('ふだん前')
        elif x['pos'] > 2 / 3:
            tag.append('ふだん後ろ')
        else:
            tag.append('中団')
        if mg is not None and x['gap'] is not None and x['gap'] < mg:
            tag.append('終い上位')
        if x['sd'] <= .18:
            tag.append('位置が動かない')
        gg = f"{x['gap']:+.2f}" if x['gap'] is not None else '  ―  '
        print(f"  {e['u']:>3} {e['nm']:<14}{w:>3}{x['pos']:>7.2f}{x['sd']:>6.2f}"
              f"{gg:>7}{x['n']:>4}  {'／'.join(tag)}")
