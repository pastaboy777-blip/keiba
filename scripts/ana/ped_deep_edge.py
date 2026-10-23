# -*- coding: utf-8 -*-
"""10代まで遡った血統だけで、その開催の結果を測る。

  python3 scripts/ana/ped_deep_edge.py --track 大井 --days 2026-10-04,... [--pop 7]

位置・ラップ・調教は一切使わない。血統の構造だけで見る。

出すもの
  - 母父・母母父・母母母父 別の上振れ
  - 5代以内のクロスの有無／濃さ（近交係数）別
  - ハイインロー（Hyperion×Son-in-Law）・ナスキロ（Nasrullah×Princequillo）の濃さ別
  - サンデーサイレンスのクロス
  - 父系・母系それぞれの大系統

上振れ = 実測の3着内率 − 人気から見た期待値。
"""
import json, glob, os, sys, collections
sys.path.insert(0, os.path.dirname(__file__))

ARG = sys.argv[1:]


def opt(k, d=None):
    return ARG[ARG.index(k) + 1] if k in ARG else d


SP = '/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/scratchpad'
CACHE = opt('--cache', SP + '/anc.jsonl')
IDS = opt('--ids', SP + '/ids_nk.jsonl')
TRACK = opt('--track', '大井')
DAYS = (opt('--days') or '').split(',') if opt('--days') else None
DEPTH = int(opt('--depth', 10))
POP = int(opt('--pop', 7))
MINN = int(opt('--min', 8))
BA = {'18': '浦和', '19': '船橋', '20': '大井', '21': '川崎'}

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
ID = {}
for l in open(IDS, encoding='utf-8'):
    try:
        x = json.loads(l)
        ID[x['nm']] = x['id']
    except Exception:
        pass

runs = []
for p in sorted(glob.glob('notes/live/*/results.json')):
    d = p.split('/')[2]
    if len(d) != 10 or (DAYS and d not in DAYS):
        continue
    for Rs, r in json.load(open(p, encoding='utf-8')).items():
        if BA.get(str(r.get('rid', ''))[8:10]) != TRACK:
            continue
        for e in r['e']:
            if not str(e.get('f', '')).isdigit():
                continue
            runs.append(dict(d=d, R=int(Rs), dist=r['dist'], nm=e['nm'],
                             f=int(e['f']), pop=int(e['pop'])))


def paths(hid):
    out = collections.defaultdict(list)

    def rec(i, g, side):
        if not i or g > DEPTH:
            return
        if g:
            out[i].append((g, side))
        n = G.get(i)
        if not n:
            return
        rec(n['s'], g + 1, side or '父')
        rec(n['d'], g + 1, side or '母')
    rec(hid, 0, '')
    return out


def line(hid, path):
    cur = hid
    for ch in path:
        n = G.get(cur)
        if not n or not cur:
            return None
        cur = n['s'] if ch == '父' else n['d']
    return G.get(cur, {}).get('nm') if cur else None


def w(ps, side=None):
    return sum(0.5 ** g for g, sd in ps if side is None or sd == side)


KEY = ['Hyperion', 'Son-in-Law', 'Nasrullah', 'Princequillo', 'Northern Dancer',
       'Mr. Prospector', 'Native Dancer', 'Storm Cat', 'サンデーサイレンス',
       'Halo', 'Hail to Reason', 'Bold Ruler', 'ノーザンテースト', 'Danzig']

rows = []
for x in runs:
    hid = ID.get(x['nm'])
    if not hid or hid not in G:
        continue
    P = paths(hid)
    byn = collections.defaultdict(list)
    for i, ps in P.items():
        byn[G[i]['nm']] += ps
    F = 0.0
    for i, ps in P.items():
        for g1, s1 in ps:
            for g2, s2 in ps:
                if s1 == '父' and s2 == '母':
                    F += 0.5 ** (g1 + g2 - 1)
    ws = {i: w(v, '父') for i, v in P.items()}
    wd = {i: w(v, '母') for i, v in P.items()}
    tot = (sum(ws.values()) + sum(wd.values())) / 2
    com = sum(min(ws[i], wd[i]) for i in ws if wd.get(i)) / tot * 100 if tot else 0
    cross5 = {G[i]['nm']: v for i, v in P.items()
              if len(v) >= 2 and min(g for g, _ in v) <= 5}
    hyin = min(w(byn.get('Hyperion', [])), w(byn.get('Son-in-Law', [])))
    nasu = min(w(byn.get('Nasrullah', [])), w(byn.get('Princequillo', [])))
    ss = byn.get('サンデーサイレンス', [])
    rows.append(dict(x, id=hid, F=F * 100, com=com,
                     bms=line(hid, '母父'), bmms=line(hid, '母母父'),
                     bmmms=line(hid, '母母母父'), sire=line(hid, '父'),
                     ss_n=len(ss), ss_cross=len({sd for _, sd in ss}) == 2 and len(ss) >= 2,
                     ss_min=(min(g for g, _ in ss) if ss else None),
                     hyin=hyin * 1000, nasu=nasu * 1000,
                     cross5=len(cross5), cross5_names=sorted(cross5),
                     **{('n_' + k): len(byn.get(k, [])) for k in KEY},
                     **{('m_' + k): (min(g for g, _ in byn[k]) if byn.get(k) else 99) for k in KEY}))

print(f'# {TRACK} {len(runs)}走 / 血統が{DEPTH}代まで取れた {len(rows)}走\n')
if not rows:
    sys.exit('まだ血統が足りない')

exp = collections.defaultdict(lambda: [0, 0])
for x in rows:
    exp[x['pop']][0] += 1
    exp[x['pop']][1] += x['f'] <= 3
EXP = {p: v[1] / v[0] for p, v in exp.items()}


def ed(g):
    if not g:
        return None
    h = sum(1 for x in g if x['f'] <= 3)
    e = sum(EXP.get(x['pop'], 0) for x in g)
    return dict(n=len(g), h=h, r=h / len(g) * 100, edge=(h - e) / len(g) * 100)


def table(label, keyf, src=None, minn=None):
    src = src if src is not None else rows
    minn = minn or MINN
    g = collections.defaultdict(list)
    for x in src:
        k = keyf(x)
        if k is not None:
            g[k].append(x)
    out = [(k, ed(v)) for k, v in g.items() if len(v) >= minn]
    if not out:
        return
    out.sort(key=lambda z: -z[1]['edge'])
    print(f'\n### {label}（{minn}頭以上）')
    print('| | 頭数 | 3着内 | 複勝率 | 上振れ |')
    print('|---|---|---|---|---|')
    for k, s in out:
        print(f"| {k} | {s['n']} | {s['h']} | {s['r']:.0f}% | {s['edge']:+.1f}pt |")


def qbuck(name, f, nq=4, src=None):
    src = src if src is not None else rows
    v = sorted(f(x) for x in src)
    if not v:
        return
    cut = [v[int(len(v) * (i + 1) / nq) - 1] for i in range(nq)]

    def kf(x):
        y = f(x)
        for i, c in enumerate(cut):
            if y <= c:
                return f'{name} {i+1}/{nq}（〜{c:.2f}）'
        return f'{name} {nq}/{nq}'
    table(name, kf, src)


ana = [x for x in rows if x['pop'] >= POP]
print(f'人気薄（{POP}番人気以下） {len(ana)}走\n')

for src, tag in ((rows, '全体'), (ana, f'{POP}番人気以下')):
    print(f'\n## {tag}')
    table(f'母父［{tag}］', lambda x: x['bms'], src)
    table(f'母母父［{tag}］', lambda x: x['bmms'], src)
    table(f'母母母父［{tag}］', lambda x: x['bmmms'], src)
    qbuck(f'近交係数F［{tag}］', lambda x: x['F'], 4, src)
    qbuck(f'父母の血の共有［{tag}］', lambda x: x['com'], 4, src)
    qbuck(f'ハイインロー濃度［{tag}］', lambda x: x['hyin'], 4, src)
    qbuck(f'ナスキロ濃度［{tag}］', lambda x: x['nasu'], 4, src)
    table(f'5代以内のクロスの本数［{tag}］', lambda x: f"{x['cross5']}種", src)
    table(f'サンデーのクロス［{tag}］',
          lambda x: ('あり' if x['ss_cross'] else ('片側のみ' if x['ss_n'] else 'なし')), src)
    table(f'サンデーの最も浅い世代［{tag}］',
          lambda x: (f"{x['ss_min']}代" if x['ss_min'] else 'なし'), src)
