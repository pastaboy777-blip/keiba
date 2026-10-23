# -*- coding: utf-8 -*-
"""祖先グラフから、クロス（インブリード）と配合の形を出す。

  python3 scripts/ana/ped_calc.py <馬名 or ID> [--depth 12] [--min 2]
  python3 scripts/ana/ped_calc.py <馬A> --cmp <馬B> [--depth 8]

「Nearctic 3×4」のような表記は、父側の世代・母側の世代を並べたもの。
世代は自身を0代として、父＝1代、父父＝2代。
ped_graph.py で先にグラフを伸ばしておく（届いていない世代は数えられない）。
"""
import json, os, sys, collections
sys.path.insert(0, os.path.dirname(__file__))
import nkped

ARG = sys.argv[1:]


def opt(k, d=None):
    return ARG[ARG.index(k) + 1] if k in ARG else d


SP = '/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/scratchpad'
CACHE = opt('--cache', SP + '/anc.jsonl')
DEPTH = int(opt('--depth', 12))
MINN = int(opt('--min', 2))
CMP = opt('--cmp')
TARGET = ARG[0]

G, EXP = {}, set()
for l in open(CACHE, encoding='utf-8'):
    try:
        x = json.loads(l)
    except Exception:
        continue
    if x.get('t') == 'exp':
        EXP.add(x['id'])
    else:
        c = G.get(x['id'])
        G[x['id']] = dict(nm=x['nm'], s=x.get('s') or (c or {}).get('s'),
                          d=x.get('d') or (c or {}).get('d'))

NM2ID = {}
for i, v in G.items():
    NM2ID.setdefault(v['nm'], i)


def resolve(t):
    if len(t) == 10 and (t.isdigit() or t in G):
        return t
    if t in NM2ID:
        return NM2ID[t]
    i, _ = nkped.search_id(t)
    return i


def paths(hid, depth):
    """祖先ID -> [(世代, 父母どちら側か), ...]"""
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


def fmt(ps):
    s = sorted(g for g, sd in ps if sd == '父')
    d = sorted(g for g, sd in ps if sd == '母')
    if s and d:
        return '・'.join(map(str, s)) + '×' + '・'.join(map(str, d))
    one = s or d
    return '・'.join(map(str, one)) + f'（{"父" if s else "母"}側のみ）'


def wsum(ps, side=None):
    return sum(0.5 ** g for g, sd in ps if side is None or sd == side)


# ── 2頭の血統の近さ（≒ の目安） ─────────────────────────────
if CMP:
    a, b = resolve(TARGET), resolve(CMP)
    pa, _ = paths(a, DEPTH)
    pb, _ = paths(b, DEPTH)
    sa = {i: wsum(v) for i, v in pa.items()}
    sb = {i: wsum(v) for i, v in pb.items()}
    com = sum(min(sa[i], sb[i]) for i in sa if i in sb)
    tot = (sum(sa.values()) + sum(sb.values())) / 2
    print(f'{G.get(a,{}).get("nm",a)} と {G.get(b,{}).get("nm",b)}  {DEPTH}代まで')
    print(f'共有の重み {com:.2f} / 平均 {tot:.2f} = 近さ {com/tot*100:.1f}%')
    sh = sorted(((min(sa[i], sb[i]), i) for i in sa if i in sb), reverse=True)[:20]
    for w, i in sh:
        print(f'  {w:.3f}  {G[i]["nm"]}   {fmt(pa[i])} / {fmt(pb[i])}')
    sys.exit()

hid = resolve(TARGET)
if not hid:
    sys.exit('馬が見つからない')

# ── その血がどの経路で入っているかを名前で出す ───────────────
ROUTE = opt('--route')
if ROUTE:
    tgt = [i for i, v in G.items() if v['nm'] == ROUTE]
    if not tgt:
        sys.exit(f'{ROUTE} がグラフにない')
    tgt = set(tgt)
    found = []

    def rec(i, g, chain):
        if not i or g > DEPTH:
            return
        n = G.get(i)
        nm = (n or {}).get('nm', i)
        if i in tgt and g:
            found.append((g, chain))
            return
        if not n:
            return
        rec(n['s'], g + 1, chain + [(G.get(n['s'], {}).get('nm', '?'), '父')])
        rec(n['d'], g + 1, chain + [(G.get(n['d'], {}).get('nm', '?'), '母')])
    rec(hid, 0, [])
    found.sort()
    print(f'# {G.get(hid,{}).get("nm", TARGET)} → {ROUTE} の経路（{DEPTH}代以内・{len(found)}本）\n')
    for g, ch in found:
        side = ch[0][1] if ch else '?'
        print(f'  {g}代（{side}側）  ' + ' → '.join(nm for nm, _ in ch))
    sys.exit()
P, reach = paths(hid, DEPTH)
full = [2 ** g for g in range(DEPTH + 1)]
print(f'# {G.get(hid,{}).get("nm", TARGET)}  ({hid})')
print('\n## グラフの届き方（世代ごとの延べ本数 / 満数）')
print('  ' + '  '.join(f'{g}代 {reach[g]}/{full[g]}' for g in range(1, DEPTH + 1)))

print(f'\n## クロス（{DEPTH}代以内・{MINN}本以上）')
rows = []
for i, ps in P.items():
    if len(ps) < MINN:
        continue
    rows.append((min(g for g, _ in ps), -len(ps), i, ps))
rows.sort()
for mn, nneg, i, ps in rows:
    both = len({sd for _, sd in ps}) == 2
    print(f'  {G[i]["nm"]:<26} {fmt(ps):<22} {len(ps)}本' + ('  ◎父母にまたがる' if both else ''))

# 近交係数（父側×母側の経路の組み合わせ、祖先自身の内部インブリードは無視）
Fc = 0.0
for i, ps in P.items():
    for g1, s1 in ps:
        for g2, s2 in ps:
            if s1 == '父' and s2 == '母':
                Fc += 0.5 ** (g1 + g2 - 1)
print(f'\n近交係数 F ≒ {Fc*100:.2f}%（{DEPTH}代まで・届いている範囲で）')

# 父母相似配合の目安
ws = {i: wsum(v, '父') for i, v in P.items()}
wd = {i: wsum(v, '母') for i, v in P.items()}
com = sum(min(ws[i], wd[i]) for i in ws if wd.get(i))
tot = (sum(ws.values()) + sum(wd.values())) / 2
print(f'父側と母側の共有（父母相似配合の目安） {com/tot*100:.1f}%')

LINES = {
    'Hyperion': 'ハイペリオン',
    'Son-in-Law': 'サンインロー',
    'Nasrullah': 'ナスルーラ',
    'Royal Charger': 'ロイヤルチャージャー',
    'Northern Dancer': 'ノーザンダンサー',
    'Mr. Prospector': 'ミスタープロスペクター',
    'Native Dancer': 'ネイティヴダンサー',
    'Polynesian': 'ポリネシアン',
    'Princequillo': 'プリンスキロ',
    'Nearctic': 'ニアークティック',
    'Mahmoud': 'マームード',
    'Victoria Park': 'ヴィクトリアパーク',
    'La Troienne': 'ラトロワエンヌ',
    'Teddy': 'テディ',
    'Blandford': 'ブランドフォード',
    'Sir Gallahad': 'サーギャラハッド',
    'Turn-to': 'ターントゥ',
    'Sadler\'s Wells': 'サドラーズウェルズ',
    'Halo': 'ヘイロー',
    'サンデーサイレンス': 'サンデーサイレンス',
    'ノーザンテースト': 'ノーザンテースト',
}
print('\n## 血脈ごとの本数（浅い順）')
for en, ja in LINES.items():
    hits = [(i, ps) for i, ps in P.items() if G[i]['nm'] == en]
    if not hits:
        continue
    i, ps = hits[0]
    print(f'  {ja:<14}（{en}） {len(ps)}本  最も浅い {min(g for g,_ in ps)}代  {fmt(ps)}')
hy = [ps for i, ps in P.items() if G[i]['nm'] == 'Hyperion']
sl = [ps for i, ps in P.items() if G[i]['nm'] == 'Son-in-Law']
if hy and sl:
    print(f'\nハイインロー（Hyperion×Son-in-Law）… Hyperion {len(hy[0])}本 / '
          f'Son-in-Law {len(sl[0])}本、浅い側は {min(min(g for g,_ in hy[0]), min(g for g,_ in sl[0]))}代')
