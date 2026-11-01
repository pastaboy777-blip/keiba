# -*- coding: utf-8 -*-
"""「タケゾウ型」を測る ── 終いは鞍内1位だが前半が下位の馬。

  python3 scripts/ana/takezo.py [場名...]

ユーザーの板にある見立て：
  終い速度が鞍内1位でも、前半速度が下位なら群に入れず買えない。

1走ごとに鞍の中で2つの順位をつける。
  前半速度 ＝（距離−600）÷（走破時計 − 自身の上り3F）
  終い速度 ＝ 600 ÷ 自身の上り3F
各馬の近5走で、その順位の中央値を取る。
  タケゾウ型 ＝ 終いが上位1/3 かつ 前半が下位1/3
すべて前日に分かる。同点は乱数で崩す（CLAUDE.md の作法）。
"""
import json, random, re, statistics as st, sys
from collections import defaultdict

BA = sys.argv[1:] or ['船橋', '大井']
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
DIVF = {'船橋': 'div_funabashi.json', '大井': 'div_year.json'}


def sec(t):
    m = re.match(r'^(?:(\d+):)?(\d+)\.(\d)$', t.strip()) if t else None
    return None if not m else int(m.group(1) or 0) * 60 + int(m.group(2)) \
        + int(m.group(3)) / 10


R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R.sort(key=lambda r: (r['ymd'], r['rid']))
D = {}
for ba, fn in DIVF.items():
    try:
        D[ba] = json.load(open(f'{SP}/{fn}', encoding='utf-8'))
    except Exception:
        pass

rnd = random.Random(11)
HIST = defaultdict(list)
ROWS = []
for r in R:
    v = []
    for e in r['e']:
        t, a = sec(e.get('tm')), sec(e.get('ag') or '')
        if t is None or a is None or a <= 0 or not r.get('dist'):
            continue
        if t <= a:
            continue
        v.append((e['nm'], (r['dist'] - 600) / (t - a), 600 / a))
    # 今日の分析（前日に使えるのは過去走の順位なので、まず判定）
    if r['ba'] in BA and len(v) >= 6:
        fk = dict((D.get(r['ba'], {}).get(r['ymd'], {})
                   .get(str(r['R']), {})).get('複勝', []))
        for e in r['e']:
            nm = e['nm']
            if not e.get('f', '').isdigit():
                continue
            p = [x for x in HIST.get(nm, []) if x[0] < r['ymd']][-5:]
            if len(p) < 3:
                continue
            ef = st.median(x[1] for x in p)      # 前半の順位（0が最前）
            el = st.median(x[2] for x in p)      # 終いの順位
            pop = e.get('pop', '')
            ROWS.append(dict(ba=r['ba'], hit=int(e['f']) <= 3,
                             pop=int(pop) if pop.isdigit() else None,
                             ef=ef, el=el, n=len(p),
                             fuku=fk.get(str(int(e['u'])), 0), has=bool(fk)))
    # 履歴を更新（鞍内の順位。同点は乱数で崩す）
    if len(v) >= 4:
        for k, idx in ((1, 1), (2, 2)):
            pass
        for key in (1, 2):
            w = v[:]
            rnd.shuffle(w)
            w.sort(key=lambda x: -x[key])
            for i, x in enumerate(w):
                HIST[x[0]].append((r['ymd'], 0, 0)) if False else None
        # 2つの順位をまとめて入れる
        a1 = sorted(rnd.sample(v, len(v)), key=lambda x: -x[1])
        a2 = sorted(rnd.sample(v, len(v)), key=lambda x: -x[2])
        r1 = {x[0]: i / max(1, len(v) - 1) for i, x in enumerate(a1)}
        r2 = {x[0]: i / max(1, len(v) - 1) for i, x in enumerate(a2)}
        for nm, _, _ in v:
            HIST[nm].append((r['ymd'], r1[nm], r2[nm]))

P = [x for x in ROWS if x['pop'] and x['pop'] >= 6]
base = 100 * sum(x['hit'] for x in P) / len(P)
d = [x for x in P if x['has']]
print(f'■ 人気薄 {len(P)}頭　3着内 {base:.1f}%　'
      f'複勝の回収 {sum(x["fuku"] for x in d)/len(d):.0f}%\n')


def sh(lab, f, mn=100):
    v = [x for x in P if f(x)]
    if len(v) < mn:
        print(f'    {lab:<30} 材料不足({len(v)})')
        return
    i = sum(x['hit'] for x in v)
    dd = [x for x in v if x['has']]
    print(f'    {lab:<30}{len(v):>5}頭 {100*i/len(v):5.1f}%'
          f'  回収{sum(x["fuku"] for x in dd)/len(dd) if dd else 0:5.0f}%'
          f' {100*i/len(v)-base:+5.1f}pt')


print('  〈終いの速さだけで見る〉')
sh('終いが上位1/3', lambda x: x['el'] <= 1/3)
sh('終いが下位1/3', lambda x: x['el'] > 2/3)
print('  〈前半の速さだけで見る〉')
sh('前半が上位1/3', lambda x: x['ef'] <= 1/3)
sh('前半が下位1/3', lambda x: x['ef'] > 2/3)
print('  〈組み合わせ ── ここがユーザーの見立て〉')
sh('終い上位1/3 × 前半上位1/3', lambda x: x['el'] <= 1/3 and x['ef'] <= 1/3)
sh('終い上位1/3 × 前半中1/3',
   lambda x: x['el'] <= 1/3 and 1/3 < x['ef'] <= 2/3)
sh('終い上位1/3 × 前半下位1/3（タケゾウ型）',
   lambda x: x['el'] <= 1/3 and x['ef'] > 2/3, mn=50)
sh('終い下位1/3 × 前半上位1/3', lambda x: x['el'] > 2/3 and x['ef'] <= 1/3)
