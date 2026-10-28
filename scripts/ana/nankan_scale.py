# -*- coding: utf-8 -*-
"""南関4場の「ものさし」がそろうかを確かめる。

  python3 scripts/ana/nankan_scale.py [out.json]

各場で「その場の距離×馬場の中央からのズレ」を出すと、場の速さは消える。
けれど残るものがある ── その場に集まる馬の格。浦和の中央は大井の中央より
弱いので、同じ馬でも浦和では良く見える。

そこで両方を走った馬をつかまえて、ズレの差の中央値を取る。
ただし「一本の数字」にはならなかった。3つの検算で分かったこと：

  行きと帰り   そろう（ひらき 0.00〜0.30秒）。移籍の向きによる偏りではない
  道の検算     大井→浦和は 直接+0.80／船橋ごし+0.50／川崎ごし+0.15 と
               0.65秒ちらばる。つまり足し算でつながらない
  馬の格       浦和→船橋は 強い馬で-0.70、弱い馬で-0.40。格で0.3秒動く

結論：大井・船橋・川崎はほぼ同じものさし（差0.2秒以内）。浦和だけ
0.5〜0.8秒ぶん良く見える。ただし精度は ±0.3秒 までで、それ以上は
詰められない。
"""
import json, re, statistics as st, sys
from collections import defaultdict

SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
OUT = sys.argv[1] if len(sys.argv) > 1 else f'{SP}/nankan_scale.json'
BA = ('大井', '浦和', '船橋', '川崎')
WET = ('重', '不良')


def sec(t):
    m = re.match(r'^(?:(\d+):)?(\d+)\.(\d)$', t.strip()) if t else None
    return None if not m else (int(m.group(1) or 0)) * 60 + int(m.group(2)) \
        + int(m.group(3)) / 10


R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
cell = defaultdict(list)
for r in R:
    if not r.get('dist'):
        continue
    k = (r['ba'], r['dist'], 'wet' if r.get('baba') in WET else 'dry')
    for e in r['e']:
        t = sec(e.get('tm'))
        if t:
            cell[k].append(t)
M = {k: st.median(v) for k, v in cell.items() if len(v) >= 40}

H = defaultdict(lambda: defaultdict(list))
for r in R:
    k = (r['ba'], r.get('dist'), 'wet' if r.get('baba') in WET else 'dry')
    m = M.get(k)
    if not m:
        continue
    for e in r['e']:
        t = sec(e.get('tm'))
        if t:
            H[e['nm']][r['ba']].append(t - m)

PAIR = {}
print('■ 両方を走った馬でくらべる（2走以上ある馬だけ）')
print(f"{'':>14}" + ''.join(f'{b:>16}' for b in BA))
for a in BA:
    row = ''
    for b in BA:
        if a == b:
            row += f'{"－":>16}'
            continue
        d = [st.median(H[nm][a]) - st.median(H[nm][b]) for nm in H
             if len(H[nm][a]) >= 2 and len(H[nm][b]) >= 2]
        if len(d) >= 30:
            PAIR[(a, b)] = (st.median(d), len(d))
            row += f'{st.median(d):+9.2f}秒({len(d):>3})'
        else:
            row += f'{"材料不足":>14}'
    print(f'  {a:>10}{row}')

# ── 大井を0に置いて、場ごとの一本の数字にする ──────────────
# 直接くらべられない組み合わせは、間に場をはさんだ道でも出せるので、
# すべての道の中央値をとる。
base = {'大井': 0.0}
for b in BA[1:]:
    paths = []
    if ('大井', b) in PAIR:
        paths.append(PAIR[('大井', b)][0])
    for mid in BA[1:]:
        if mid == b:
            continue
        if ('大井', mid) in PAIR and (mid, b) in PAIR:
            paths.append(PAIR[('大井', mid)][0] + PAIR[(mid, b)][0])
    if paths:
        base[b] = round(st.median(paths), 2)

print('\n■ 大井を0に置いたときの、場ごとのものさし')
for b in BA:
    v = base.get(b)
    if v is None:
        print(f'  {b}  －')
        continue
    say = ('基準' if b == '大井' else
           f'この場のズレに {v:+.2f} 足すと大井のズレになる')
    print(f'  {b}  {v:+.2f}秒   {say}')

print('\n■ 道が合っているかの検算（ちがう道で同じ答えになるか）')
for b in BA[1:]:
    paths = []
    if ('大井', b) in PAIR:
        paths.append(('直接', PAIR[('大井', b)][0]))
    for mid in BA[1:]:
        if mid != b and ('大井', mid) in PAIR and (mid, b) in PAIR:
            paths.append((f'{mid}ごし', PAIR[('大井', mid)][0] + PAIR[(mid, b)][0]))
    s = ' / '.join(f'{nm} {v:+.2f}' for nm, v in paths)
    w = max(v for _, v in paths) - min(v for _, v in paths) if len(paths) > 1 else 0
    print(f'  大井→{b}　{s}　　ちらばり {w:.2f}秒')

json.dump({'base': base,
           'pair': {f'{a}-{b}': v for (a, b), v in PAIR.items()}},
          open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f'\n書き出し {OUT}')
