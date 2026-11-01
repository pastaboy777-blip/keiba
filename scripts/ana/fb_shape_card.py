# -*- coding: utf-8 -*-
"""展開上の立ち位置を出馬表に当てる。

  python3 scripts/ana/fb_shape_card.py <card.json> <YYYYMMDD>

各馬のふだんの4角位置（近5走の中央値）を並べ、自分より前に行く馬が
何頭いるかを数える。すべて前日に分かる。

  前に1頭      船橋19.3%（層11.4%）大井14.9%（層9.1%）川崎16.1%
  前に0頭      最先頭。3着内は良くないが1着率は高い（2.5% 対 1.6%）
  前に3頭以上   9.9%で層を下回る
浦和では効かない。
"""
import json, statistics as st, sys
from collections import defaultdict

CARD, YMD = sys.argv[1], sys.argv[2]
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R = [r for r in R if r['ymd'] < YMD]
R.sort(key=lambda r: (r['ymd'], r['rid']))
HIST = defaultdict(list)
for r in R:
    c4 = r.get('c4') or []
    if not c4:
        continue
    pos = {u: (i + 1) / len(c4) for i, u in enumerate(c4)}
    for e in r['e']:
        if int(e['u']) in pos:
            HIST[e['nm']].append((r['ymd'], pos[int(e['u'])]))

C = json.load(open(CARD, encoding='utf-8'))
print(f'■ {YMD} 船橋　展開上の立ち位置')
print('  ふだんの位置＝近5走の4角位置（頭数で割った割合）の中央値。'
      '小さいほど前')
print('  ◎前に1頭（船橋19.3%・層11.4%）　△最先頭（3着内は落ちるが1着率は高い）')
print('  ×前に3頭以上（9.9%）\n')
best = []
for k in sorted((x for x in C if str(x).isdigit()), key=int):
    r = C[k]
    cur = {}
    for e in r['e']:
        v = [p for y, p in HIST.get(e['nm'], []) if y < YMD][-5:]
        if len(v) >= 3:
            cur[e['nm']] = (st.median(v), len(v))
    if len(cur) < 6:
        print(f'  ── {k}R {r["dist"]}m　近3走そろう馬が少ない（{len(cur)}頭）\n')
        continue
    rows = []
    for e in r['e']:
        if e['nm'] not in cur:
            continue
        me, nr = cur[e['nm']]
        ahead = sum(1 for v, _ in cur.values() if v < me)
        rows.append((e, me, ahead, nr))
    rows.sort(key=lambda x: x[1])
    print(f'  ── {k}R {r["dist"]}m {r["n"]}頭　'
          f'ふだんの位置が分かる {len(cur)}頭 ──')
    for e, me, ahead, nr in rows:
        mk = ('△' if ahead == 0 else '◎' if ahead == 1 else
              '　' if ahead == 2 else '×')
        print(f'     {mk}{e["u"]:>2} {e["nm"]:<16}ふだん {me:.2f}'
              f'（{nr}走）　前に{ahead}頭')
        if ahead == 1:
            best.append((int(k), e['u'], e['nm'], me, r['dist']))
    miss = [e['nm'] for e in r['e'] if e['nm'] not in cur]
    if miss:
        print(f'       位置が分からない：{"、".join(miss)}')
    print()
print(f'● 前に1頭（2番手で運べる形）　{len(best)}頭')
for x in best:
    print(f'  {x[0]:>2}R {x[4]}m  {x[1]:>2}番 {x[2]:<16}ふだん {x[3]:.2f}')
