# -*- coding: utf-8 -*-
"""今開催の浦和を血統だけでまとめる。次開催にそのまま持ち込む用。

  python3 scripts/ana/urawa_ped_meet.py <ped.jsonl> [日付 日付 ...]

人気別の3着内率は年間ぶんの血統データ（4,588頭）から作り、
今開催の実測との差を pt で出す。母数の小さい開催単体の率を
そのまま見ないための枠組み。
"""
import json, glob, sys, collections

PED = sys.argv[1]
DAYS = sys.argv[2:] or ['2026-10-19', '2026-10-20', '2026-10-21', '2026-10-22', '2026-10-23']
BA = {'18': '浦和', '19': '船橋', '20': '大井', '21': '川崎'}

ped = {}
for l in open(PED, encoding='utf-8'):
    x = json.loads(l)
    ped[x['nm']] = x


def load(days=None):
    out = []
    for p in sorted(glob.glob('notes/live/*/results.json')):
        d = p.split('/')[2]
        if len(d) != 10 or (days and d not in days):
            continue
        for Rs, r in json.load(open(p, encoding='utf-8')).items():
            if BA.get(str(r.get('rid', ''))[8:10]) != '浦和':
                continue
            for e in r['e']:
                if not str(e.get('f', '')).isdigit():
                    continue
                pp = ped.get(e['nm'])
                if not pp:
                    continue
                out.append(dict(d=d, R=int(Rs), dist=r['dist'], cls=r.get('cls', ''),
                                nm=e['nm'], f=int(e['f']), pop=int(e['pop']),
                                c4=e.get('c4'), age=e.get('age'), sx=e.get('sx'),
                                sire=pp['sire'], bms=pp['bms'], dam=pp['dam']))
    return out


# 期待値（人気別3着内率）は年間ぶんの南関全体から
base = collections.defaultdict(lambda: [0, 0])
for x in load(None):
    base[x['pop']][0] += 1
    base[x['pop']][1] += x['f'] <= 3
EXP = {p: v[1] / v[0] for p, v in base.items() if v[0]}

rows = load(DAYS)


def ed(g):
    """頭数・勝・3着内・複勝率・期待・上振れpt"""
    n = len(g)
    if not n:
        return None
    w = sum(1 for x in g if x['f'] == 1)
    h = sum(1 for x in g if x['f'] <= 3)
    e = sum(EXP.get(x['pop'], 0) for x in g)
    return dict(n=n, w=w, h=h, r=h / n * 100, e=e / n * 100, edge=(h - e) / n * 100)


def table(key, label, minn=6, sub=None):
    g = collections.defaultdict(list)
    for x in rows:
        if sub and not sub(x):
            continue
        g[x[key]].append(x)
    out = [(k, ed(v)) for k, v in g.items() if len(v) >= minn]
    out.sort(key=lambda z: -z[1]['edge'])
    print(f'\n### {label}（{minn}頭以上）')
    print('| 血統 | 出走 | 勝 | 3着内 | 複勝率 | 期待 | 上振れ |')
    print('|---|---|---|---|---|---|---|')
    for k, s in out:
        print(f"| {k} | {s['n']} | {s['w']} | {s['h']} | {s['r']:.0f}% | {s['e']:.0f}% | {s['edge']:+.1f}pt |")
    return out


print(f'# 浦和 今開催（{DAYS[0]}〜{DAYS[-1]}）── 血統だけのまとめ')
print(f'\n対象 {len(rows)}頭 / 血統の取れなかった馬は除外。')
print('上振れ = 実測の3着内率 − 人気から見た期待値（期待は南関4,588頭ぶんの人気別3着内率）。')

table('sire', '父別', 6)
table('bms', '母父別', 6)
print('\n#### 短距離（ダ800・1400）')
table('bms', '母父別・短距離', 6, sub=lambda x: x['dist'] <= 1400)
print('\n#### 1500m以上')
table('bms', '母父別・1500m以上', 5, sub=lambda x: x['dist'] >= 1500)

print('\n### 人気薄（7番人気以下）で3着内に来た馬の血統')
print('| 日 | R | 人気 | 着 | 馬名 | 父 | 母父 |')
print('|---|---|---|---|---|---|---|')
ana = [x for x in rows if x['pop'] >= 7 and x['f'] <= 3]
for x in sorted(ana, key=lambda z: (z['d'], z['R'])):
    print(f"| {x['d'][5:]} | {x['R']} | {x['pop']}人 | {x['f']} | {x['nm']} | {x['sire']} | {x['bms']} |")
print(f'\n該当 {len(ana)}頭。')
cs = collections.Counter(x['sire'] for x in ana)
cb = collections.Counter(x['bms'] for x in ana)
print('\n穴馬の父：' + ('／'.join(f'{k}{v}' for k, v in cs.most_common() if v >= 2) or 'ダブりなし'))
print('穴馬の母父：' + ('／'.join(f'{k}{v}' for k, v in cb.most_common() if v >= 2) or 'ダブりなし'))

# ── 次開催への持ち込み：浦和の持っている全日で裏を取る ──────────────
allr = [x for x in load(None)]
mine = {(x['d'], x['R'], x['nm']) for x in rows}
other = [x for x in allr if (x['d'], x['R'], x['nm']) not in mine]
odays = sorted({x['d'] for x in other})


def grp(src, key, sub=None):
    g = collections.defaultdict(list)
    for x in src:
        if sub and not sub(x):
            continue
        g[x[key]].append(x)
    return g


def carry(key, label, sub, minn_meet, minn_prev):
    gm, go = grp(rows, key, sub), grp(other, key, sub)
    out = []
    for k, v in gm.items():
        if len(v) < minn_meet or len(go.get(k, [])) < minn_prev:
            continue
        a, b = ed(v), ed(go[k])
        if a['edge'] * b['edge'] > 0:          # 今開催と過去で向きが揃うもの
            out.append((k, a, b))
    out.sort(key=lambda z: -(z[1]['edge'] + z[2]['edge']))
    print(f'\n### {label}')
    print('| 血統 | 今開催 | 過去{}日 | 判定 |'.format(len(odays)))
    print('|---|---|---|---|')
    for k, a, b in out:
        v = '買える' if a['edge'] > 0 else '消せる'
        print(f"| {k} | {a['h']}/{a['n']} {a['edge']:+.0f}pt | {b['h']}/{b['n']} {b['edge']:+.0f}pt | {v} |")
    return out


print('\n\n## 次開催への持ち込み')
print(f'\n今開催 {len(rows)}頭と、浦和の過去 {len(odays)}日 {len(other)}頭で向きが揃ったものだけ。')
print('片方だけで出た数字は開催一度の偏りとして落とす。')
carry('bms', '母父（全距離）', None, 6, 15)
carry('bms', '母父・ダ800/1400', lambda x: x['dist'] <= 1400, 6, 12)
carry('bms', '母父・1500m以上', lambda x: x['dist'] >= 1500, 5, 8)
carry('sire', '父（全距離）', None, 6, 12)
