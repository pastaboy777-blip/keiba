# -*- coding: utf-8 -*-
"""馬の調子をどう測るのが正しいかを、候補を並べて競わせる。

  python3 scripts/ana/ooi_form_compare.py

測りたいのは「能力」でも「脚質」でもなく、その馬自身の普段からのズレ。
候補を5つ用意して、同じ土俵で2つの試験にかける。

  試験1 もちこし … 前走の値が次走にどれだけ残るか（相関）
      残らない＝その場かぎりのブレ。残りすぎ＝能力や脚質を測っている
  試験2 当たるか … 直近の向きで4つに割り、人気薄の3着内率と回収率

候補
  A 粘り（鞍の中央ぐらべ）  −（上がりの鞍内差 − 自前半の鞍内差）
  B レース上がりぐらべ      レース上がり3F − 馬の上がり3F
  C レースの減速ぐらべ      レースの落ち込み − 馬の落ち込み（1Fあたり）
  D 走破の二元残差          走破 −（馬の普段）−（鞍の水準）
  E 上がりの二元残差        上がり −（馬の普段）−（鞍の上がり水準）
"""
import json, re, statistics as st
from collections import defaultdict

SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')


def sec(t):
    m = re.match(r'^(?:(\d+):)?(\d+)\.(\d)$', t.strip()) if t else None
    return None if not m else (int(m.group(1) or 0)) * 60 + int(m.group(2)) \
        + int(m.group(3)) / 10


def cor(a, b):
    ma, mb = st.mean(a), st.mean(b)
    n = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    d = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** .5
    return n / d if d else 0


LAP = {}
for l in open(f'{SP}/corners_2026.jsonl', encoding='utf-8'):
    v = json.loads(l)
    if v.get('lap') and len(v['lap']) >= 4:
        LAP[v['rid']] = v['lap']
DIV = json.load(open(f'{SP}/div_year.json', encoding='utf-8'))
R2 = []
for l in open(f'{SP}/ooi_2026_runs.jsonl', encoding='utf-8'):
    r = json.loads(l)
    if r.get('dist') and r.get('e'):
        R2.append(r)
R2.sort(key=lambda r: (r.get('ymd') or '', r['rid']))

KEYS = 'ABCDE'
HIST = defaultdict(lambda: defaultdict(list))   # 馬 -> 指標 -> 値の列
OWN = defaultdict(list)                         # 馬 -> 走破の鞍内差（普段の水準用）
OWNA = defaultdict(list)                        # 馬 -> 上がりの鞍内差
ROWS = []

for r in R2:
    d = r['dist']
    lap = LAP.get(r['rid'])
    hs = []
    for e in r['e']:
        t, a = sec(e.get('tm')), sec(e.get('ag') or '')
        if t and a and t > a:
            hs.append((e, t - a, a, t))
    if len(hs) < 7:
        continue
    mh = st.median([x[1] for x in hs])
    ma = st.median([x[2] for x in hs])
    mt = st.median([x[3] for x in hs])
    nf = d / 200 - 3                      # 前半のハロン数
    if lap:
        rA3 = sum(lap[-3:])               # レース上がり3F
        rF = sum(lap[:len(lap) - 3])      # レース前半
        rDec = rA3 / 3 - rF / nf          # レースの落ち込み（1Fあたり）
    fuku = dict((DIV.get(r['ymd'], {}).get(str(int(r['rid'][-2:])), {})
                 ).get('複勝', []))
    for e, h, a, t in hs:
        if not e.get('f', '').isdigit():
            continue
        pop = e.get('pop', '')
        # ── 予測に使うのは、この走りより前の値だけ ──
        rec = {}
        for k in KEYS:
            v = HIST[e['nm']][k][-5:]
            if len(v) == 5:
                rec[k] = st.mean(v[3:]) - st.mean(v[:3])
        if len(rec) == len(KEYS):
            ROWS.append(dict(hit=int(e['f']) <= 3,
                             fuku=fuku.get(str(int(e['u'])), 0),
                             pop=int(pop) if pop.isdigit() else None, **rec))
    # ── この走りを履歴に積む ──
    for e, h, a, t in hs:
        nm = e['nm']
        dh, da, dt = h - mh, a - ma, t - mt
        own = st.mean(OWN[nm][-5:]) if len(OWN[nm]) >= 3 else None
        owna = st.mean(OWNA[nm][-5:]) if len(OWNA[nm]) >= 3 else None
        val = {'A': -(da - dh)}
        if lap:
            val['B'] = rA3 - a
            val['C'] = rDec - (a / 3 - h / nf)
        val['D'] = -(dt - own) if own is not None else None
        val['E'] = -(da - owna) if owna is not None else None
        for k in KEYS:
            if val.get(k) is not None:
                HIST[nm][k].append(val[k])
        OWN[nm].append(dt)
        OWNA[nm].append(da)

P = [x for x in ROWS if x['pop'] and x['pop'] >= 6]
print(f'5つとも値がそろう {len(ROWS)}頭 / 人気薄 {len(P)}頭')
base = 100 * sum(x['hit'] for x in P) / len(P)
broi = sum(x['fuku'] for x in P) / len(P)
print(f'人気薄ぜんぶ  3着内 {base:.1f}%  回収 {broi:.0f}%\n')

NAME = {'A': 'A 粘り（鞍の中央ぐらべ）', 'B': 'B レース上がりぐらべ',
        'C': 'C レースの減速ぐらべ', 'D': 'D 走破の二元残差',
        'E': 'E 上がりの二元残差'}

# ── 試験1 もちこし ───────────────────────────────────
print('■ 試験1 もちこし（前の走りの値が、次の走りにどれだけ残るか）')
for k in KEYS:
    a, b = [], []
    for nm, h in HIST.items():
        v = h[k]
        for i in range(len(v) - 1):
            a.append(v[i])
            b.append(v[i + 1])
    if len(a) > 200:
        print(f'  {NAME[k]:<26} {cor(a, b):+.2f}   （{len(a)}組）')

# ── 試験2 当たるか ───────────────────────────────────
print('\n■ 試験2 直近の向きで4つに割る（人気薄）')
print(f"{'':<26}{'上向き 1/4':>18}{'下向き 1/4':>18}{'ひらき':>10}")
for k in KEYS:
    q = sorted(x[k] for x in P)
    lo, hi = q[len(q) // 4], q[3 * len(q) // 4]
    up = [x for x in P if x[k] >= hi]
    dn = [x for x in P if x[k] <= lo]
    pu = 100 * sum(x['hit'] for x in up) / len(up)
    pd = 100 * sum(x['hit'] for x in dn) / len(dn)
    ru = sum(x['fuku'] for x in up) / len(up)
    rd = sum(x['fuku'] for x in dn) / len(dn)
    print(f'  {NAME[k]:<24}{pu:6.1f}% 回収{ru:4.0f}%{pd:9.1f}% 回収{rd:4.0f}%'
          f'{pu-pd:+9.1f}pt')

# ── 指標どうしの相関（同じものを測っていないか）─────────────
import itertools
print('\n■ 指標どうしの相関（人気薄）')
for k1, k2 in itertools.combinations(KEYS, 2):
    print(f'  {k1} と {k2}  '
          f'{cor([x[k1] for x in P], [x[k2] for x in P]):+.2f}')
