# -*- coding: utf-8 -*-
"""キーレースとバウンス ── 日本の地方ではまず使われない2つを測る。

  python3 scripts/ana/nankan_keyrace.py [場名...]

キーレース（米国の古典手法）
  「その馬がどのレースから出てきたか」を、同じレースを走った他馬の
  その後の成績で測る。同走馬が次々に走るレースは中身が濃かった
  ということで、そこの着外馬も買える、という考え方。
  ここでは前走の同走馬のうち、次走で3着内に入った割合を使う。
  前走より後に走った馬だけを数えるので、先の情報は使っていない。

バウンス（反動）
  前走で自己ベースを大きく更新した馬は、次走で凡走しやすい。
  ここでは走破時計の鞍内偏差を、その馬の普段とくらべて測る。
"""
import json, re, statistics as st, sys
from collections import defaultdict

BA = sys.argv[1:] or ['大井', '船橋', '川崎', '浦和']
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
DIVF = {'船橋': 'div_funabashi.json', '大井': 'div_year.json'}


def sec(t):
    m = re.match(r'^(?:(\d+):)?(\d+)\.(\d)$', t.strip()) if t else None
    return None if not m else (int(m.group(1) or 0)) * 60 + int(m.group(2)) \
        + int(m.group(3)) / 10


R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R.sort(key=lambda r: (r['ymd'], r['rid']))

# ── 1周目：馬ごとに「いつ・どの鞍を走り・結果はどうだったか」を並べる ──
RUN = defaultdict(list)          # 馬 -> [(ymd, rid, 3着内か, 走破の鞍内差)]
for r in R:
    ts = [sec(e.get('tm')) for e in r['e']]
    ts = [t for t in ts if t]
    mt = st.median(ts) if len(ts) >= 5 else None
    for e in r['e']:
        if not e.get('f', '').isdigit():
            continue
        t = sec(e.get('tm'))
        RUN[e['nm']].append((r['ymd'], r['rid'], int(e['f']) <= 3,
                             (t - mt) if (t and mt) else None))

# ── 2周目：各走りについて、前走のキーレース度とバウンスを出す ──
ROWS = []
for r in R:
    if r['ba'] not in BA:
        continue
    DIV = {}
    for e in r['e']:
        if not e.get('f', '').isdigit():
            continue
        nm = e['nm']
        v = RUN[nm]
        i = next((i for i, x in enumerate(v) if x[1] == r['rid']), None)
        if i is None or i == 0:
            continue
        pymd, prid, _, pdev = v[i - 1]
        # 前走の同走馬が、そのあと3着内に入ったか
        prev = next((x for x in R if x['rid'] == prid), None)
        if not prev:
            continue
        nxt = tot = 0
        for o in prev['e']:
            if o['nm'] == nm:
                continue
            w = RUN[o['nm']]
            j = next((j for j, x in enumerate(w) if x[1] == prid), None)
            if j is None or j + 1 >= len(w):
                continue
            if w[j + 1][0] >= r['ymd']:      # この馬の今走より後の走りは使わない
                continue
            tot += 1
            nxt += w[j + 1][2]
        # バウンス：前走の出来が、その馬の普段からどれだけ良かったか
        past = [x[3] for x in v[max(0, i - 6):i - 1] if x[3] is not None]
        bounce = (st.mean(past) - pdev) if (len(past) >= 3 and pdev is not None) \
            else None
        pop = e.get('pop', '')
        ROWS.append(dict(ba=r['ba'], ymd=r['ymd'], R=r['R'],
                         hit=int(e['f']) <= 3,
                         pop=int(pop) if pop.isdigit() else None,
                         key=(nxt / tot) if tot >= 5 else None, ktot=tot,
                         bounce=bounce))

for ba in BA:
    P = [x for x in ROWS if x['ba'] == ba and x['pop'] and x['pop'] >= 6]
    if len(P) < 400:
        print(f'■ {ba}  材料不足（{len(P)}頭）\n')
        continue
    base = 100 * sum(x['hit'] for x in P) / len(P)
    print(f'■ {ba}　人気薄 {len(P)}頭　3着内 {base:.1f}%')

    def show(lab, f, mn=80):
        v = [x for x in P if f(x)]
        if len(v) < mn:
            print(f'    {lab:<26} 材料不足({len(v)})')
            return
        i = sum(x['hit'] for x in v)
        print(f'    {lab:<26} {100*i/len(v):5.1f}%  ({i}/{len(v)})'
              f' {100*i/len(v)-base:+5.1f}pt')

    print('  〈キーレース〉前走の同走馬が、次走で3着内に入った割合')
    for lab, lo, hi in (('1割未満', 0, .10), ('1〜2割', .10, .20),
                        ('2〜3割', .20, .30), ('3割以上', .30, 1.01)):
        show(lab, lambda x, a=lo, b=hi: x['key'] is not None and a <= x['key'] < b)
    print('  〈バウンス〉前走が普段よりどれだけ良かったか（＋ほど前走が良い）')
    q = sorted(x['bounce'] for x in P if x['bounce'] is not None)
    if len(q) > 300:
        a, b = q[len(q) // 4], q[3 * len(q) // 4]
        show('前走が特に良かった1/4', lambda x: x['bounce'] is not None and x['bounce'] >= b)
        show('まん中', lambda x: x['bounce'] is not None and a < x['bounce'] < b)
        show('前走が特に悪かった1/4', lambda x: x['bounce'] is not None and x['bounce'] <= a)
    print()
