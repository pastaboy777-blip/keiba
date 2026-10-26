# -*- coding: utf-8 -*-
"""明日の走破時計を鞍ごとに見当づける。

  python3 scripts/ana/ooi_times.py <card.json> <馬場> [asof]

出走馬の過去（距離×馬場で補正した絶対時計のズレ）の中央値から鞍のレベルを
推し、その距離・馬場の中央値に足す。今年の大井613鞍で相関 +0.81、
1鞍あたりの外れは 0.62秒。勝ち時計と3着時計は、レベルごとの
「中央との開き」を当てはめて出す。
"""
import collections, json, re, statistics as st, sys

CARD, BABA = sys.argv[1], sys.argv[2]
ASOF = sys.argv[3] if len(sys.argv) > 3 else '99999999'
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
WET = ('重', '不良')


def sec(t):
    m = re.match(r'^(?:(\d+):)?(\d+)\.(\d)$', t.strip()) if t else None
    return None if not m else (int(m.group(1) or 0)) * 60 + int(m.group(2)) \
        + int(m.group(3)) / 10


def mmss(x):
    return f'{int(x // 60)}:{x % 60:04.1f}' if x >= 60 else f'{x:.1f}'


R2 = [json.loads(l) for l in open(SP + '/ooi_2026_runs.jsonl', encoding='utf-8')]
R2 = [r for r in R2 if r['dist']]
R2.sort(key=lambda r: (r['ymd'], r['rid']))
cell = collections.defaultdict(list)
for r in R2:
    for e in r['e']:
        t = sec(e['tm'])
        if t:
            cell[(r['dist'], r['baba'])].append(t)
M = {k: st.median(v) for k, v in cell.items() if len(v) >= 40}
G = collections.defaultdict(list)
for (d, b), v in cell.items():
    G[(d, 'wet' if b in WET else 'dry')] += v
GM = {k: st.median(v) for k, v in G.items() if len(v) >= 25}


def med(d, b):
    return M.get((d, b)) or GM.get((d, 'wet' if b in WET else 'dry'))


# 各馬の実力（絶対時計のズレ）と、鞍のレベル別の「中央と勝ち・3着の開き」
H = collections.defaultdict(list)
gap = []
for r in R2:
    m = med(r['dist'], r['baba'])
    ts = sorted(sec(e['tm']) for e in r['e'] if sec(e['tm']))
    if m and len(ts) >= 7:
        L = st.median(ts) - m
        gap.append((L, st.median(ts) - ts[0], st.median(ts) - ts[2]))
    if r['ymd'] < ASOF:
        for e in r['e']:
            t = sec(e['tm'])
            if t and m:
                H[e['nm']].append(t - m)
g1 = st.linear_regression([x[0] for x in gap], [x[1] for x in gap])   # 勝ちの開き
g3 = st.linear_regression([x[0] for x in gap], [x[2] for x in gap])   # 3着の開き

# 直近3走の人気（市場がその馬をどう見ているか）
POP = {}
for r in R2:
    if r['ymd'] >= ASOF:
        continue
    for e in r['e']:
        if str(e['pop']).isdigit():
            POP.setdefault(e['nm'], []).append(int(e['pop']))
POP = {k: st.median(v[-3:]) for k, v in POP.items()}

C = json.load(open(CARD, encoding='utf-8'))
print(f'大井 {BABA} の見当　（613鞍で相関 +0.81、1鞍あたりの外れ 0.62秒）\n')
print(f'{"R":>3}{"距離":>6}{"頭":>4} {"材料":>5}  {"レベル":>7}   '
      f'{"勝ち":>8}{"3着":>8}{"中央":>8}')
out = {}
for R in sorted(C, key=int):
    r = C[R]
    m = med(r['dist'], BABA)
    pw = [st.median(H[e['nm']][-5:]) for e in r['e'] if len(H[e['nm']]) >= 2]
    if not m or len(pw) < max(4, r['n'] * 0.5):
        print(f'{R:>3}{r["dist"]:>6}{r["n"]:>4} {len(pw):>4}頭  '
              f'{"材料が足りない":>18}')
        continue
    L = 0.88 * st.median(pw) - 0.20
    cen = m + L
    w, t3 = cen - (g1.slope * L + g1.intercept), cen - (g3.slope * L + g3.intercept)
    out[R] = dict(dist=r['dist'], L=round(L, 2), win=round(w, 1),
                  t3=round(t3, 1), cen=round(cen, 1), n=len(pw))
    print(f'{R:>3}{r["dist"]:>6}{r["n"]:>4} {len(pw):>4}頭  {L:>+7.2f}   '
          f'{mmss(w):>8}{mmss(t3):>8}{mmss(cen):>8}')
json.dump(out, open(f'{SP}/ooi_times_{BABA}.json', 'w', encoding='utf-8'),
          ensure_ascii=False)

# ── 予想した3着時計に、普段の脚のままで届く馬 ──────────────────
print('\n\n普段の脚で3着時計に届く馬（カッコ内は予想3着との差）\n')
for R in sorted(out, key=int):
    r, o = C[R], out[R]
    hit = []
    for e in r['e']:
        h = H[e['nm']][-5:]
        if len(h) < 2:
            continue
        pt = med(r['dist'], BABA) + 0.88 * st.median(h) - 0.20
        if pt <= o['t3'] + 0.3:
            pp = POP.get(e['nm'])
            hit.append((int(e['u']), e['nm'], pt, pt - o['t3'],
                        len([x for x in H[e['nm']] if x]), pp))
    hit.sort()
    head = f"{R:>3}R {o['dist']}m  3着 {mmss(o['t3'])}"
    if not hit:
        print(f'{head}  … 届く馬なし')
        continue
    print(head)
    for u, nm, pt, d, n, pp in hit:
        mk = '◎' if (pp and pp >= 9) else ('○' if (pp and pp >= 6) else ' ')
        print(f'   {mk}  {u:>2} {nm:<14} {mmss(pt):>7}  ({d:+.1f})  {n}走  '
              f'直近{(f"{pp:g}人" if pp else "－")}')
