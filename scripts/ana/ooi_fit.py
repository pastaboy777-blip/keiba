# -*- coding: utf-8 -*-
"""「今日と同じ脚で足りる鞍はどこか」を出す。

  python3 scripts/ana/ooi_fit.py <card.json> <馬場> <out.md>

伸びそうな馬は探さない。馬の脚は変わらないものとして置き、
条件（距離×馬場）ごとの水準だけを動かして、普段の脚で足りる鞍を拾う。

水準は今年の大井 903鞍 10,639頭の実測から、距離×馬場ごとの
自前半（走破−自身の上り）と上り3Fの中央値。
馬の脚は、その馬の各走の「中央値からのズレ」。これは条件が変わっても
持ち越せる。ズレを明日の水準に足し直したものが見込み時計。

壁は鞍の中で決める（出走馬の見込み時計の3位）。クラスの絶対時計は
C2とB2で同じ1200mでも3秒違うので、絶対値では比べない。
"""
import collections, json, os, re, statistics as st, sys

CARD, BABA, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
ASOF = sys.argv[4] if len(sys.argv) > 4 else '99999999'   # この日より前の走だけ使う
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
WET = ('重', '不良')


def sec(t):
    m = re.match(r'^(?:(\d+):)?(\d+)\.(\d)$', t.strip()) if t else None
    if not m:
        return None
    return int(m.group(1) or 0) * 60 + int(m.group(2)) + int(m.group(3)) / 10


def fnum(x):
    try:
        return float(x)
    except Exception:
        return None


# ── 1. 今年の大井を1頭1走に開く ───────────────────────────────
runs = collections.defaultdict(list)          # 馬名 -> [走]
cell = collections.defaultdict(list)          # (dist, baba) -> [(自前半, 上り)]
for l in open(SP + '/ooi_2026_runs.jsonl', encoding='utf-8'):
    r = json.loads(l)
    if not r['dist']:
        continue
    for e in r['e']:
        t, a = sec(e['tm']), fnum(e['ag'])
        if not (t and a):
            continue
        cell[(r['dist'], r['baba'])].append((t - a, a))
    # その鞍の中央値。クラスの速さがそのまま入っているので、
    # ここからの差を取るとクラスを抜いた「相手との差」になる。
    v = [(sec(e['tm']), fnum(e['ag'])) for e in r['e']]
    v = [x for x in v if x[0] and x[1]]
    if len(v) < 5:
        continue
    ch, ca = st.median([x[0] - x[1] for x in v]), st.median([x[1] for x in v])
    for e in r['e']:
        t, a = sec(e['tm']), fnum(e['ag'])
        if not (t and a):
            continue
        runs[e['nm']].append(dict(
            ymd=r['ymd'], dist=r['dist'], baba=r['baba'], t=t, h=t - a, a=a,
            ch=(t - a) - ch, ca=a - ca,
            f=int(e['f']) if str(e['f']).isdigit() else None,
            pop=int(e['pop']) if str(e['pop']).isdigit() else None,
            wt=e['wt'], jk=e['jk'], tr=e['tr'], R=int(r['rid'][-2:])))
for v in runs.values():
    v.sort(key=lambda z: z['ymd'])

# ── 2. 距離×馬場の水準 ────────────────────────────────────────
# 薄いマスは 乾（良・稍重）／渋（重・不良）にまとめ、それでも薄ければ
# その距離ぜんぶの中央値に、全距離で測った渋りぶんの差を足す。
MED = {}
for k, v in cell.items():
    if len(v) >= 40:
        MED[k] = (st.median([x[0] for x in v]), st.median([x[1] for x in v]))
grp = collections.defaultdict(list)
for (d, b), v in cell.items():
    grp[(d, 'wet' if b in WET else 'dry')] += v
    grp[(d, 'all')] += v
GM = {k: (st.median([x[0] for x in v]), st.median([x[1] for x in v]))
      for k, v in grp.items() if len(v) >= 25}
# 渋りぶんの差（全距離・十分な母数のある距離だけ）
dw = [(GM[(d, 'wet')][0] - GM[(d, 'dry')][0], GM[(d, 'wet')][1] - GM[(d, 'dry')][1])
      for d in {x[0] for x in GM} if (d, 'wet') in GM and (d, 'dry') in GM]
DW = (st.median([x[0] for x in dw]), st.median([x[1] for x in dw]))


def med(dist, baba):
    """その距離・馬場の自前半と上りの中央値。"""
    w = 'wet' if baba in WET else 'dry'
    if (dist, baba) in MED:
        return MED[(dist, baba)]
    if (dist, w) in GM:
        return GM[(dist, w)]
    if (dist, 'all') in GM:
        b = GM[(dist, 'all')]
        return (b[0] + (DW[0] if w == 'wet' else 0),
                b[1] + (DW[1] if w == 'wet' else 0))
    return None


# ── 3. 馬ごとの脚 ─────────────────────────────────────────────
def legs(nm, n=5):
    """直近n走の、水準からのズレ。中央値＝普段の脚、最小＝いちばん出た日。"""
    al = [r for r in runs.get(nm, []) if r['ymd'] < ASOF]
    rs = [r for r in al if med(r['dist'], r['baba'])][-n:]
    if len(rs) < 2:
        return None
    pp = [r['pop'] for r in al[-3:] if r['pop']]
    for r in rs:
        m = med(r['dist'], r['baba'])
        r['dh'], r['da'] = r['h'] - m[0], r['a'] - m[1]
        r['mh'], r['ma'] = m
    return dict(n=len(rs), rs=rs, pp=(st.median(pp) if pp else None),
                dh=st.median([r['dh'] for r in rs]),
                da=st.median([r['da'] for r in rs]),
                ch=st.median([r['ch'] for r in rs]),
                ca=st.median([r['ca'] for r in rs]))


C = json.load(open(CARD, encoding='utf-8'))
o = ['# 大井 2026/10/27 ── 普段の脚で足りる鞍\n',
     f'馬場は **{BABA}** で置いた。水準は今年の大井 915鞍の距離×馬場ごとの中央値。\n',
     '各馬の自前半・上りは、**過去の実測をそのまま**明日の水準に置き直したもの。'
     '伸びる前提は置いていない。見込み＝自前半＋上り、壁＝その鞍の見込み3位。\n',
     '同じ距離・馬場でも鞍によって走破時計が3.6〜4.9秒ちがう（クラス。1200mなら上位1割と下位1割で3.6秒）。上のクラスほど'
     '上りが速いので、距離×馬場だけで測るとクラスを馬の脚として読んでしまう。'
     '**絶対（距離×馬場で補正した時計）と鞍内偏差（クラスを抜いた相手との差）を半々**'
     'で混ぜた。\n',
     '印は今年の大井 6,959頭での実測から（同じ層の平均との比）。\n',
     '  ◎ … 直近3走の人気が9番人気以下で、見込み3位以内（22.8%／層平均8.1%の2.8倍）\n',
     '  ○ … 直近3走の人気が6〜8番人気で、見込み3位以内（32.7%／層平均20.4%の1.6倍）\n',
     '  ・ … 見込み3位以内だが市場も見ている（42.2%／全体22.9%）\n']

PICK = []
for R in sorted(C, key=int):
    r = C[R]
    D = r['dist']
    m = med(D, BABA)
    if not m:
        continue
    # 絶対（距離×馬場だけで補正した時計）と、鞍内偏差（クラスを抜いた相手との差）を
    # 半々で混ぜる。今年の大井で測ると、どちらか一方より半々がいちばん当たった。
    #   全馬 42.2%（絶対だけ40.6／鞍内だけ40.4）
    #   直近人気9番人気以下 22.8%（絶対だけ19.5／鞍内だけ18.2）
    gg = [(e, legs(e['nm'])) for e in r['e']]
    hv = [(e, g) for e, g in gg if g]
    if len(hv) < 3:
        continue
    lh = st.median([m[0] + g['dh'] for _, g in hv])    # この鞍の自前半の見当
    la = st.median([m[1] + g['da'] for _, g in hv])    # 同じく上り
    rows = []
    for e, g in gg:
        if not g:
            rows.append((None, e, None))
            continue
        ph = (m[0] + g['dh'] + lh + g['ch']) / 2
        pa = (m[1] + g['da'] + la + g['ca']) / 2
        rows.append((ph + pa, e, dict(g, ph=ph, pa=pa)))
    have = sorted([x for x in rows if x[0]], key=lambda z: z[0])
    bar = have[2][0] if len(have) >= 3 else None
    o.append(f"\n## {R}R　{D}m　{r['n']}頭"
             f"（水準 自前半{m[0]:.1f}＋上り{m[1]:.1f}＝{m[0]+m[1]:.1f}）\n")
    if bar:
        o.append(f'壁 **{bar:.1f}**\n')
    o.append('| 馬番 | 馬名 | 見込み | 自前半 | 上り | 直近人気 | 下り幅 | 直近3走（古→新） |')
    o.append('|---|---|---|---|---|---|---|---|')
    for pt, e, g in sorted(rows, key=lambda z: (z[0] is None, z[0] or 0)):
        if not g:
            o.append(f"| {e['u']} | {e['nm']} | － | | | | | 大井の実測が2走に足りない |")
            continue
        last = g['rs'][-1]
        rec = '／'.join(
            f"{x['dist']}{x['baba'][0]} {x['h']:.1f}+{x['a']:.1f} "
            f"{x['pop']}人{x['f']}着" for x in g['rs'][-3:] if x['f'] and x['pop'])
        # 前走の鞍と比べて、上りの水準がどれだけ下りてくるか
        drop = m[1] - last['ma']
        ok = bool(bar) and pt <= bar + 0.05
        pp = g['pp']
        mk = ''
        if ok and pp:
            mk = '◎ ' if pp >= 9 else ('○ ' if pp >= 6 else '・ ')
        elif ok:
            mk = '・ '
        o.append(f"| {mk}{e['u']} | {e['nm']} | **{pt:.1f}** | {g['ph']:.1f} "
                 f"| {g['pa']:.1f} | {('%g人' % pp) if pp else '－'} "
                 f"| {drop:+.1f} | {rec} |")
        if ok and pp and pp >= 6:
            PICK.append(dict(R=int(R), D=D, u=e['u'], nm=e['nm'], pt=pt, pp=pp,
                             ph=g['ph'], pa=g['pa'], bar=bar, rec=rec, drop=drop,
                             da=g['da'], last=last, mk=mk.strip(), sire=e['sire']))

o.append('\n---\n\n## 条件が下りてきた馬\n')
o.append('市場が低く見ている（直近3走の人気が6番人気以下）のに、'
         '普段の脚のままで壁を越える馬。\n')
o.append('| 印 | R | 距離 | 馬番 | 馬名 | 見込み | 壁 | 直近人気 | 下り幅 | 前走 |')
o.append('|---|---|---|---|---|---|---|---|---|---|')
for p in sorted(PICK, key=lambda z: (-z['pp'], z['R'])):
    L = p['last']
    o.append(f"| {p['mk']} | {p['R']}R | {p['D']} | {p['u']} | **{p['nm']}** "
             f"| {p['pt']:.1f} | {p['bar']:.1f} | {p['pp']:g}人 | {p['drop']:+.1f} "
             f"| {L['ymd'][4:6]}/{L['ymd'][6:]} {L['dist']}{L['baba']} "
             f"{L['h']:.1f}+{L['a']:.1f} {L['pop']}人{L['f']}着 |")
open(OUT, 'w', encoding='utf-8').write('\n'.join(o) + '\n')
json.dump(PICK, open(os.path.splitext(OUT)[0] + '.json', 'w', encoding='utf-8'),
          ensure_ascii=False, default=str)
print('書き出し', OUT, '◎', len(PICK), '頭')
