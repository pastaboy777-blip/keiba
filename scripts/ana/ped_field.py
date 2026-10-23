# -*- coding: utf-8 -*-
"""出走メンバーぶんの血統を、同じ深さで並べる。

  python3 scripts/ana/ped_field.py <field.json> [--depth 12] [--lines Hyperion,Son-in-Law]

field.json は [{nm, id, u}, ...]。ped_graph.py でグラフを伸ばしてから使う。
世代が届いていない馬は「届き方」の欄に出るので、数字を比べる前に確認する。
"""
import json, os, sys, collections
sys.path.insert(0, os.path.dirname(__file__))

ARG = sys.argv[1:]


def opt(k, d=None):
    return ARG[ARG.index(k) + 1] if k in ARG else d


SP = '/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/scratchpad'
CACHE = opt('--cache', SP + '/anc.jsonl')
DEPTH = int(opt('--depth', 12))
LINES = (opt('--lines') or 'Hyperion,Son-in-Law,Northern Dancer,Mr. Prospector,'
         'Nasrullah,Princequillo,La Troienne,Mahmoud').split(',')
FIELD = json.load(open(ARG[0], encoding='utf-8'))

G = {}
for l in open(CACHE, encoding='utf-8'):
    try:
        x = json.loads(l)
    except Exception:
        continue
    if x.get('t') == 'exp':
        continue
    c = G.get(x['id'])
    G[x['id']] = dict(nm=x['nm'], s=x.get('s') or (c or {}).get('s'),
                      d=x.get('d') or (c or {}).get('d'))


def paths(hid, depth):
    out = collections.defaultdict(list)
    reach = [0] * (depth + 2)

    def rec(i, g, side):
        if not i or g > depth:
            return
        if g:
            out[i].append((g, side))
            reach[g] += 1
        n = G.get(i)
        if not n:
            return
        rec(n['s'], g + 1, side or '父')
        rec(n['d'], g + 1, side or '母')
    rec(hid, 0, '')
    return out, reach


def line(hid, path):
    cur = hid
    for ch in path:
        n = G.get(cur)
        if not n:
            return '?'
        cur = n['s'] if ch == '父' else n['d']
        if not cur:
            return '?'
    return G.get(cur, {}).get('nm', '?')


def byname(P, nm):
    return [ps for i, ps in P.items() if G.get(i, {}).get('nm') == nm]


rows = []
for h in FIELD:
    hid = h['id']
    if hid not in G:
        rows.append((h, None, None, None))
        continue
    P, reach = paths(hid, DEPTH)
    full = all(reach[g] == 2 ** g for g in range(1, DEPTH + 1))
    st = {}
    for ln in LINES:
        hit = byname(P, ln)
        if hit:
            ps = hit[0]
            st[ln] = dict(n=len(ps), mn=min(g for g, _ in ps),
                          s=sum(1 for _, sd in ps if sd == '父'),
                          d=sum(1 for _, sd in ps if sd == '母'))
    F = 0.0
    for i, ps in P.items():
        for g1, s1 in ps:
            for g2, s2 in ps:
                if s1 == '父' and s2 == '母':
                    F += 0.5 ** (g1 + g2 - 1)
    ws = {i: sum(0.5 ** g for g, sd in v if sd == '父') for i, v in P.items()}
    wd = {i: sum(0.5 ** g for g, sd in v if sd == '母') for i, v in P.items()}
    com = sum(min(ws[i], wd[i]) for i in ws if wd.get(i))
    tot = (sum(ws.values()) + sum(wd.values())) / 2
    cross5 = [(G[i]['nm'], v) for i, v in P.items()
              if len(v) >= 2 and min(g for g, _ in v) <= 5]
    cross5.sort(key=lambda z: min(g for g, _ in z[1]))
    rows.append((h, st, dict(F=F * 100, com=com / tot * 100, full=full,
                             reach=reach, cross5=cross5), P))

print(f'# {DEPTH}代までの血統（{len(FIELD)}頭）\n')
print('| 馬番 | 馬名 | 父 | 母父 | 母母父 | 近交F | 父母共有 | 12代 |')
print('|---|---|---|---|---|---|---|---|')
for h, st, s, P in rows:
    if not s:
        print(f"| {h.get('u','')} | {h['nm']} | （血統未取得） | | | | | |")
        continue
    print(f"| {h.get('u','')} | {h['nm']} | {line(h['id'],'父')} | {line(h['id'],'母父')} "
          f"| {line(h['id'],'母母父')} | {s['F']:.2f}% | {s['com']:.1f}% "
          f"| {'完' if s['full'] else '欠'} |")

print('\n## 血脈の本数（父側/母側・最も浅い世代）\n')
hdr = '| 馬番 | 馬名 | ' + ' | '.join(LINES) + ' |'
print(hdr)
print('|' + '---|' * (len(LINES) + 2))
for h, st, s, P in rows:
    if not s:
        continue
    cs = []
    for ln in LINES:
        v = st.get(ln)
        cs.append(f"{v['n']}本({v['s']}/{v['d']}) {v['mn']}代" if v else '—')
    print(f"| {h.get('u','')} | {h['nm']} | " + ' | '.join(cs) + ' |')

print('\n## 5代以内のクロス\n')
for h, st, s, P in rows:
    if not s:
        continue
    cx = s['cross5']
    if not cx:
        print(f"- **{h['nm']}** … 5代以内のクロスなし（アウトブリード）")
        continue
    t = []
    for nm, v in cx:
        sg = sorted(g for g, sd in v if sd == '父')
        dg = sorted(g for g, sd in v if sd == '母')
        t.append(nm + ' ' + ('・'.join(map(str, sg)) + '×' + '・'.join(map(str, dg))
                             if sg and dg else
                             '・'.join(map(str, sg or dg)) + ('（父側）' if sg else '（母側）')))
    print(f"- **{h['nm']}** … " + '／'.join(t))
