# -*- coding: utf-8 -*-
"""近5走の「動き」を点にして、効くかを過去で確かめてから出馬表に当てる。

  検証   python3 scripts/ana/fb_score.py <corners_margin.jsonl> test [場名]
  出馬表 python3 scripts/ana/fb_score.py <corners_margin.jsonl> card <card.json> <YYYYMMDD> [場名]

1走ごとに、最初に取れたコーナーから4角までで何が起きたかを4つに分ける。
点は船橋の人気薄で測った1走あたりの3着内率そのもの。置いた数字ではない。

  順位を上げた                18.1
  順位は同じだが秒では詰めた   12.0
  順位は同じで秒では離された    3.8
  順位を下げた                 3.3
  着差が書かれていない走       層の9.8（1〜3月の船橋など）

近5走の平均を取る。順位だけで見る版（秒を使わない）も並べて出し、
秒を足した意味があるかどうかを見られるようにする。

【結果：効かなかった。負の記録として残す】
船橋の人気薄1,931頭（層11.3%・回収71%）
  順位だけの点  上位1/5 11.5%・回収69%   下位1/5 7.3%・59%
  秒を足した点  上位1/5 12.2%・回収72%   下位1/5 7.3%・54%
  秒を足した点の上位1割  9.2%・回収56%  ← むしろ沈む
平均にすると「3回上げて2回下げた馬」が真ん中に入って薄まる。
効いた形は平均ではなく回数だった。

そして回数に戻しても、船橋では効かない。
  船橋 上げた3回以上 8.7%／4回以上 8.7%（層11.0%）  ← 逆向き
  大井 上げた4回以上 13.0%（+4.0pt）
  浦和 上げた3回以上 17.1%（+4.6pt）
  川崎 上げた5回   15.2%（+4.4pt）
以前「近5走すべて押し上げ19.8%・回収123%」と出したのは4場を混ぜた
106頭で、中身は大井・浦和・川崎が持っていた。船橋だけ別の動き方をする。
大井の3条件を船橋が受けつけなかったのと同じ。

【測るときの注意】
move_sec.py が出す「順位を上げた18.1%・回収106%」はそのレースでの
動きなので、レースが終わってから分かること。前日の材料にはならない。
前日に使えるのは過去走の動き。この2つを混同しないこと。
"""
import json, re, statistics as st, sys
from collections import defaultdict

SRC, MODE = sys.argv[1], sys.argv[2]
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
GAP = {',': 1.1, '-': 2.4, '=': 3.6}      # 当てはめた馬身
SEC = 0.24                                 # 1馬身あたりの秒数
PT = {'up': 18.1, 'hold_in': 12.0, 'hold_out': 3.8, 'down': 3.3, 'na': 9.8}
PT_RANK = {'up': 18.1, 'hold': 10.6, 'down': 3.3, 'na': 9.8}


def parse(s):
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

# ── 1走ごとに、動きを4つに分ける ──
HIST = defaultdict(list)
for r in R:
    v = CM.get(r['rid'])
    sym, ranks = {}, {}
    if v:
        for key, lab in (('c1s', 1), ('c2s', 2), ('c3s', 3), ('c4s', 4)):
            p = parse(v.get(key))
            if p:
                sym[lab] = dict(p)
                ranks[lab] = {u: i + 1 for i, u in
                              enumerate(sorted(dict(p),
                                               key=lambda x: (dict(p)[x], x)))}
    # 記号が取れないときは、数字だけの通過順位（これまでのやり方）で代用
    if not sym:
        for key, lab in (('c1', 1), ('c2', 2), ('c3', 3), ('c4', 4)):
            c = r.get(key)
            if c:
                ranks[lab] = {u: i + 1 for i, u in enumerate(c)}
    if 4 not in ranks:
        continue
    fst = min(k for k in ranks)
    if fst == 4:
        continue
    has_sym = (4 in sym and fst in sym)
    for e in r['e']:
        if not e.get('f', '').isdigit():
            continue
        u = int(e['u'])
        a, b = ranks[fst].get(u), ranks[4].get(u)
        if not a or not b:
            continue
        mv = a - b
        if has_sym and u in sym[4] and u in sym[fst]:
            gain = (sym[fst][u] - sym[4][u]) * SEC
        else:
            gain = None
        if mv >= 1:
            kind = 'up'
        elif mv <= -1:
            kind = 'down'
        elif gain is None:
            kind = 'na'
        else:
            kind = 'hold_in' if gain > 0 else \
                   'hold_out' if gain < 0 else 'hold_in'
        HIST[e['nm']].append(dict(
            ymd=r['ymd'], ba=r['ba'], R=r['R'], dist=r['dist'],
            baba=r.get('baba'), pop=e.get('pop'), f=e['f'], ag=e.get('ag'),
            mv=mv, gain=gain, kind=kind, p4=b, n=len(ranks[4])))

if MODE == 'test':
    BA = sys.argv[3] if len(sys.argv) > 3 else '船橋'
    DIVF = {'船橋': 'div_funabashi.json', '大井': 'div_year.json'}
    try:
        DIV = json.load(open(f'{SP}/{DIVF[BA]}', encoding='utf-8'))
    except Exception:
        DIV = {}
    ROWS = []
    for r in R:
        if r['ba'] != BA:
            continue
        fk = dict((DIV.get(r['ymd'], {}).get(str(r['R']), {})).get('複勝', []))
        for e in r['e']:
            if not e.get('f', '').isdigit():
                continue
            past = [x for x in HIST.get(e['nm'], []) if x['ymd'] < r['ymd']][-5:]
            if len(past) < 3:
                continue
            pop = e.get('pop', '')
            ROWS.append(dict(
                hit=int(e['f']) <= 3,
                pop=int(pop) if pop.isdigit() else None,
                sc=st.mean(PT[x['kind']] for x in past),
                scr=st.mean(PT_RANK['up'] if x['mv'] >= 1 else
                            PT_RANK['down'] if x['mv'] <= -1 else
                            PT_RANK['hold'] for x in past),
                nrun=len(past),
                fuku=fk.get(str(int(e['u'])), 0), has=bool(fk)))
    P = [x for x in ROWS if x['pop'] and x['pop'] >= 6]
    base = 100 * sum(x['hit'] for x in P) / len(P)
    dd = [x for x in P if x['has']]
    print(f'■ {BA}　人気薄 {len(P)}頭　3着内 {base:.1f}%　'
          f'複勝の回収 {sum(x["fuku"] for x in dd)/len(dd):.0f}%\n')

    def show(lab, f, mn=120):
        v = [x for x in P if f(x)]
        if len(v) < mn:
            print(f'    {lab:<26} 材料不足({len(v)})')
            return
        i = sum(x['hit'] for x in v)
        d = [x for x in v if x['has']]
        roi = f'  回収 {sum(x["fuku"] for x in d)/len(d):5.0f}%' if d else ''
        print(f'    {lab:<26} {100*i/len(v):5.1f}%{roi}  ({i}/{len(v)})'
              f' {100*i/len(v)-base:+5.1f}pt')

    for key, lab in (('scr', '順位だけで点をつける（秒を使わない）'),
                     ('sc', '秒を足して点をつける')):
        print(f'  〈{lab}〉')
        q = sorted(x[key] for x in P)
        for nm, lo, hi in (('上位1/5', .8, 1.01), ('2/5', .6, .8),
                           ('3/5', .4, .6), ('4/5', .2, .4),
                           ('下位1/5', 0, .2)):
            a = q[int(len(q) * lo) - 1] if lo else q[0]
            b = q[min(int(len(q) * hi), len(q) - 1)]
            show(nm, lambda x, A=a, B=b, K=key: A <= x[K] <= B)
        print()
    # 高い点だけをさらに絞る
    q = sorted(x['sc'] for x in P)
    c90 = q[int(len(q) * .9)]
    print('  〈秒を足した点の上位1割〉')
    show(f'点 {c90:.1f}以上', lambda x: x['sc'] >= c90, mn=60)
    sys.exit()

# ── 出馬表に当てる ──
CARD, YMD = sys.argv[3], sys.argv[4]
C = json.load(open(CARD, encoding='utf-8'))
KJ = {'up': '上げた', 'hold_in': '同じ・詰めた', 'hold_out': '同じ・離された',
      'down': '下げた', 'na': '着差なし'}
rows = []
for k in sorted((x for x in C if str(x).isdigit()), key=int):
    r = C[k]
    for e in r['e']:
        past = [x for x in HIST.get(e['nm'], []) if x['ymd'] < YMD][-5:]
        sc = st.mean(PT[x['kind']] for x in past) if past else None
        rows.append((int(k), r, e, past, sc))
rows.sort(key=lambda x: (-(x[4] or 0), x[0]))

print(f'■ {YMD} の出走馬　近5走の動きを点にして並べる')
print(f'  点は1走あたりの3着内率。上げた18.1／同じでも詰めた12.0／'
      f'同じで離された3.8／下げた3.3／着差なし9.8')
print(f'  層（人気薄ぜんぶ）は9.8。{len(rows)}頭\n')
for i, (R_, r, e, past, sc) in enumerate(rows, 1):
    if sc is None:
        continue
    cnt = defaultdict(int)
    for x in past:
        cnt[x['kind']] += 1
    s = '  '.join(f'{KJ[kk]}{vv}' for kk, vv in
                  sorted(cnt.items(), key=lambda y: -PT[y[0]]))
    print(f'{i:>3}. {sc:>5.1f}点  {R_:>2}R {e["u"]:>2} {e["nm"]:<16}'
          f'父{(e.get("sire") or "")[:12]}')
    print(f'              {s}')
    for x in past:
        g = '　　　' if x['gain'] is None else f'{x["gain"]:+.2f}秒'
        print(f'              {x["ymd"][4:6]}/{x["ymd"][6:]} {x["ba"]} '
              f'{x["dist"]}m {x["baba"] or "":<3}{x["pop"] or "-":>3}人'
              f'{x["f"]:>3}着  順位{x["mv"]:>+3}  {g}  '
              f'4角{x["p4"]}/{x["n"]}  {KJ[x["kind"]]}')
