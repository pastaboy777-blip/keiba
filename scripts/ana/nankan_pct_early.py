# -*- coding: utf-8 -*-
"""%Early（エネルギーの配り方）── Brohamer／Sartin の考え方を南関で。

  python3 scripts/ana/nankan_pct_early.py [場名...]

向こうの %E は「前半にエネルギーの何%を使ったか」を出して、
その場その距離の最適な帯に入っているかを見る。速い／遅いではなく
「配り方が合っているか」を見るのが、ほかの指標と違うところ。

本来は1頭ごとの区間タイムが要るが、南関にはない。そこで
  前半 … 走破時計 − 自身の上り3F（＝距離−600m ぶん）
  後半 … 自身の上り3F（＝600m ぶん）
の2つから各馬の速さを出し、

  %E ＝ 前半の速さ ÷（前半の速さ ＋ 後半の速さ）× 100

とする。比なので距離をまたいで比べられる。これが狙いどころ。

最適な帯は場×距離ごとに、3着内に入った馬の %E から決める。
"""
import json, re, statistics as st, sys
from collections import defaultdict

BA = sys.argv[1:] or ['船橋', '大井', '川崎', '浦和']
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
DIVF = {'船橋': 'div_funabashi.json', '大井': 'div_year.json'}


def sec(t):
    m = re.match(r'^(?:(\d+):)?(\d+)\.(\d)$', t.strip()) if t else None
    return None if not m else (int(m.group(1) or 0)) * 60 + int(m.group(2)) \
        + int(m.group(3)) / 10


def pct_early(dist, tm, ag):
    """1走ぶんの %E"""
    if dist <= 600 or tm is None or ag is None or tm <= ag:
        return None
    v_e = (dist - 600) / (tm - ag)
    v_l = 600 / ag
    return v_e / (v_e + v_l) * 100


R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R.sort(key=lambda r: (r['ymd'], r['rid']))

# ── 1周目：3着内に入った馬の %E から、場×距離の最適な帯を決める ──
GOOD = defaultdict(list)
for r in R:
    if not r.get('dist'):
        continue
    for e in r['e']:
        if not e.get('f', '').isdigit() or int(e['f']) > 3:
            continue
        p = pct_early(r['dist'], sec(e.get('tm')), sec(e.get('ag') or ''))
        if p:
            GOOD[(r['ba'], r['dist'])].append(p)
ZONE = {}
for k, v in GOOD.items():
    if len(v) >= 60:
        v = sorted(v)
        ZONE[k] = (v[len(v) // 4], v[3 * len(v) // 4])   # 真ん中の半分

print('■ 3着内に入った馬の %E ── 場×距離ごとの最適な帯（真ん中の半分）')
for k in sorted(ZONE):
    lo, hi = ZONE[k]
    print(f'  {k[0]} {k[1]:>5}m   {lo:.2f} 〜 {hi:.2f}   '
          f'（{len(GOOD[k])}頭から）')

# ── 2周目：その馬の普段の %E が帯に入っているかで、次走を見る ──
H = defaultdict(list)
ROWS = []
for r in R:
    if not r.get('dist'):
        continue
    z = ZONE.get((r['ba'], r['dist']))
    for e in r['e']:
        if not e.get('f', '').isdigit():
            continue
        past = H[e['nm']][-5:]
        pop = e.get('pop', '')
        if z and len(past) >= 3:
            me = st.median(past)
            ROWS.append(dict(ba=r['ba'], ymd=r['ymd'], R=r['R'], u=e['u'],
                             hit=int(e['f']) <= 3,
                             pop=int(pop) if pop.isdigit() else None,
                             inz=z[0] <= me <= z[1],
                             side=('前に寄りすぎ' if me > z[1] else
                                   '後ろに寄りすぎ' if me < z[0] else '帯の中'),
                             me=me))
    for e in r['e']:
        p = pct_early(r['dist'], sec(e.get('tm')), sec(e.get('ag') or ''))
        if p:
            H[e['nm']].append(p)

D = {}
for ba, fn in DIVF.items():
    try:
        D[ba] = json.load(open(f'{SP}/{fn}', encoding='utf-8'))
    except Exception:
        pass
for x in ROWS:
    d = D.get(x['ba'], {}).get(x['ymd'], {}).get(str(x['R']), {})
    fk = dict(d.get('複勝', []))
    x['fuku'] = fk.get(str(int(x['u'])), 0)
    x['has'] = bool(fk)

print()
for ba in BA:
    P = [x for x in ROWS if x['ba'] == ba and x['pop'] and x['pop'] >= 6]
    if len(P) < 500:
        print(f'■ {ba} 材料不足（{len(P)}頭）\n')
        continue
    base = 100 * sum(x['hit'] for x in P) / len(P)
    print(f'■ {ba}　人気薄 {len(P)}頭　3着内 {base:.1f}%')

    def show(lab, f, mn=150):
        v = [x for x in P if f(x)]
        if len(v) < mn:
            print(f'    {lab:<22} 材料不足({len(v)})')
            return
        i = sum(x['hit'] for x in v)
        dd = [x for x in v if x['has']]
        roi = f'  回収 {sum(x["fuku"] for x in dd)/len(dd):5.0f}%' if dd else ''
        print(f'    {lab:<22} {100*i/len(v):5.1f}%{roi}  ({i}/{len(v)})'
              f' {100*i/len(v)-base:+5.1f}pt')

    show('普段の%Eが帯の中', lambda x: x['inz'])
    show('前に寄りすぎ', lambda x: x['side'] == '前に寄りすぎ')
    show('後ろに寄りすぎ', lambda x: x['side'] == '後ろに寄りすぎ')
    print()
