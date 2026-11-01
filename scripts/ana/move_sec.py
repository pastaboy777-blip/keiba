# -*- coding: utf-8 -*-
"""コーナーでの動きを、順位ではなく「何秒ぶん詰めたか」で測る。

  python3 scripts/ana/move_sec.py <corners_margin.jsonl> [場名...]

これまで「動き」は順位の上下でしか測れなかった。
  4角で3つ上げた … でもそれが 0.2秒ぶんなのか 1.5秒ぶんなのかは分からない
通過順位の記号に着差が入っていたので、秒で出せるようになった。

  各馬の「先頭から何馬身うしろか」を記号から読む
  × 1馬身 0.21秒 → 先頭から何秒うしろか
  この差を2つのコーナーで引けば、詰めた秒数になる

秒で見ると順位では見えないものが出る。
  馬群が詰まれば、順位を上げなくても距離を詰めている
  馬群がばらければ、順位は変わらないのに離されている

順位と秒、どちらが着順に効くかを並べて比べる。

場によって使えるかどうかが違う。4角の文字列に着差（括弧＝横並び）が
どれだけ書かれているかを数えると
  大井  1鞍あたり1.8個  32%の馬が括弧に入る
  川崎  1.4個  29%
  浦和  0.9個  18%
  船橋  0個    0%     ← 199鞍すべてゼロ
船橋は着順表そのものに着差が書かれていないので、この測り方は使えない。
生ページでも確認した。
  大井 ４角  13,6,(1,9),4,11,5,7,3,2,10,(8,12)
  船橋 ４角  11,9,7,6,12,2,1,3,5,4,8,10
船橋は順位での動き（fb_all.py）を使う。そちらは4場のなかで船橋が
いちばん強く出ている。

分かったこと（大井の人気薄3,081頭）
  秒は順位に勝たない。順位+1以上 13.6%・回収93% に対して
  秒の上位1/4は 10.2%・回収61%。極端に詰めた馬は、もともと
  離れていた馬だから。
  効くのは「順位が同じ馬のなかを秒で割る」ところだけ。
    順位±0 ぜんぶ            10.5%・回収67%
    └ 秒では詰めていた(881頭) 12.6%・回収83%
    └ 秒では離された(366頭)    5.5%・回収30%
"""
import json, re, statistics as st, sys
from collections import defaultdict

SRC = sys.argv[1]
BA = sys.argv[2:] or ['船橋', '大井']
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
DIVF = {'船橋': 'div_funabashi.json', '大井': 'div_year.json'}
GAP = {',': 0.7, '-': 1.5, '=': 3.0}
SEC = 0.21


def parse_corner(s):
    if not s:
        return None
    out, lead = [], 0.0
    for t in re.findall(r'\((?:\d+,?)+\)|\d+|[,=\-]', s):
        if t in GAP:
            lead += GAP[t]
        elif t.startswith('('):
            for u in re.findall(r'\d+', t):
                out.append((int(u), lead))
        else:
            out.append((int(t), lead))
    return out or None


CM = {}
for l in open(SRC, encoding='utf-8'):
    v = json.loads(l)
    CM[v['rid']] = v
R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R.sort(key=lambda r: (r['ymd'], r['rid']))

ROWS = []
for r in R:
    if r['ba'] not in BA:
        continue
    v = CM.get(r['rid'])
    if not v:
        continue
    cs = {}
    for key, lab in (('c1s', 1), ('c2s', 2), ('c3s', 3), ('c4s', 4)):
        p = parse_corner(v.get(key))
        if p:
            cs[lab] = dict(p)
    if 4 not in cs:
        continue
    first = min(k for k in cs)
    if first == 4:
        continue
    b4, bf = cs[4], cs[first]
    b3 = cs.get(3)
    # 順位（これまでの測り方）
    o4 = {u: i + 1 for i, u in
          enumerate(sorted(b4, key=lambda u: (b4[u], u)))}
    of = {u: i + 1 for i, u in
          enumerate(sorted(bf, key=lambda u: (bf[u], u)))}
    o3 = ({u: i + 1 for i, u in enumerate(sorted(b3, key=lambda u: (b3[u], u)))}
          if b3 else None)
    N = len([x for x in r['e'] if x.get('f', '').isdigit()])
    for e in r['e']:
        if not e.get('f', '').isdigit():
            continue
        u = int(e['u'])
        if u not in b4 or u not in bf:
            continue
        pop = e.get('pop', '')
        ROWS.append(dict(
            ba=r['ba'], ymd=r['ymd'], R=r['R'], u=e['u'], nm=e['nm'],
            hit=int(e['f']) <= 3, win=int(e['f']) == 1,
            pop=int(pop) if pop.isdigit() else None,
            # 秒での動き（＋が詰めた）
            gain=(bf[u] - b4[u]) * SEC,
            gain34=((b3[u] - b4[u]) * SEC) if (b3 and u in b3) else None,
            back4=b4[u] * SEC,          # 600m地点で先頭から何秒うしろか
            # 順位での動き（これまでの測り方）
            mv=of[u] - o4[u],
            mv34=(o3[u] - o4[u]) if (o3 and u in o3) else None,
            n4=len(b4), first=first))

print(f'材料 {len(ROWS)}頭　（{"・".join(BA)}）\n')

D = {}
for ba, fn in DIVF.items():
    try:
        D[ba] = json.load(open(f'{SP}/{fn}', encoding='utf-8'))
    except Exception:
        pass
for x in ROWS:
    fk = dict((D.get(x['ba'], {}).get(x['ymd'], {})
               .get(str(x['R']), {})).get('複勝', []))
    x['fuku'] = fk.get(str(int(x['u'])), 0)
    x['has'] = bool(fk)

print('■ 順位で上げた馬のなかで、秒ではどうだったか')
print('   （順位は同じでも、詰めた秒数はばらける）')
for lo, hi, lab in ((1, 1, '順位+1'), (2, 3, '順位+2〜3'), (4, 99, '順位+4以上')):
    v = [x for x in ROWS if lo <= x['mv'] <= hi]
    if len(v) < 100:
        continue
    g = sorted(x['gain'] for x in v)
    print(f'  {lab:<10} {len(v):>6}頭　詰めた秒 中央 {st.median(g):+.2f}　'
          f'下1/4 {g[len(g)//4]:+.2f}　上1/4 {g[3*len(g)//4]:+.2f}')
v = [x for x in ROWS if x['mv'] == 0]
g = sorted(x['gain'] for x in v)
print(f'  {"順位±0":<10} {len(v):>6}頭　詰めた秒 中央 {st.median(g):+.2f}　'
      f'下1/4 {g[len(g)//4]:+.2f}　上1/4 {g[3*len(g)//4]:+.2f}')
print('  → 順位±0でも、詰めた馬と離された馬が混ざっている\n')

for ba in BA:
    P = [x for x in ROWS if x['ba'] == ba and x['pop'] and x['pop'] >= 6]
    if len(P) < 300:
        print(f'■ {ba}　材料不足（{len(P)}頭）\n')
        continue
    base = 100 * sum(x['hit'] for x in P) / len(P)
    dd = [x for x in P if x['has']]
    broi = sum(x['fuku'] for x in dd) / len(dd) if dd else 0
    print(f'■ {ba}　人気薄 {len(P)}頭　3着内 {base:.1f}%　複勝の回収 {broi:.0f}%')

    def show(lab, f, mn=120):
        v = [x for x in P if f(x)]
        if len(v) < mn:
            print(f'    {lab:<24} 材料不足({len(v)})')
            return
        i = sum(x['hit'] for x in v)
        d = [x for x in v if x['has']]
        roi = f'  回収 {sum(x["fuku"] for x in d)/len(d):5.0f}%' if d else ''
        print(f'    {lab:<24} {100*i/len(v):5.1f}%{roi}  ({i}/{len(v)})'
              f' {100*i/len(v)-base:+5.1f}pt')

    print('  〈これまで〉順位での動き')
    show('順位を下げた(-1以下)', lambda x: x['mv'] <= -1)
    show('順位±0', lambda x: x['mv'] == 0)
    show('順位を上げた(+1以上)', lambda x: x['mv'] >= 1)
    print('  〈今回〉秒での動き　＋が先頭に詰めた')
    q = sorted(x['gain'] for x in P)
    cut = [q[int(len(q)*i/4)] for i in (1, 2, 3)]
    show(f'詰めた 上位1/4 ({cut[2]:+.2f}秒以上)', lambda x: x['gain'] >= cut[2])
    show('2/4', lambda x: cut[1] <= x['gain'] < cut[2])
    show('3/4', lambda x: cut[0] <= x['gain'] < cut[1])
    show(f'下位1/4 ({cut[0]:+.2f}秒未満)', lambda x: x['gain'] < cut[0])
    print('  〈組み合わせ〉順位±0のなかを秒で割る')
    z = [x for x in P if x['mv'] == 0]
    if len(z) >= 240:
        zq = sorted(x['gain'] for x in z)
        zc = zq[len(zq)//2]
        show('順位±0 で秒は詰めた', lambda x: x['mv'] == 0 and x['gain'] >= zc)
        show('順位±0 で秒は離された', lambda x: x['mv'] == 0 and x['gain'] < zc)
    print()
json.dump([{k: v for k, v in x.items() if k != 'has'} for x in ROWS],
          open(f'{SP}/move_sec.json', 'w', encoding='utf-8'),
          ensure_ascii=False)
