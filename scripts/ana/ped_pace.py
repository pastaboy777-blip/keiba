# -*- coding: utf-8 -*-
"""血統ペース理論を測る ── 先頭に立った馬と配合が似ている馬は走るか。

  python3 scripts/ana/ped_pace.py [場名...]

MASA氏の血統ペース理論（中島国治氏の形相遺伝を下敷きにしたもの）の
実務的な言い換えはこう。
  「逃げ馬と似たような配合の馬を探せば大きくはブレないのかもしれない」

形相遺伝そのもの（形・相・質・料）は人の判断なので数字にできないが、
この言い換えなら測れる。ここでは父と母父の2代ぶんで「似ている」を
数える。

  先頭馬の父  == その馬の父
  先頭馬の父  == その馬の母父
  先頭馬の母父 == その馬の父
  先頭馬の母父 == その馬の母父
この4つのうちいくつ当てはまるかを重なりの数とする。

この比べ方は条件が良い。同じレースに出ている同世代どうしを比べるので、
以前つまずいた「古い馬は5代でNasrullahまで届くが今の種牡馬は届かない」
という世代の深さの問題が起きない。

2段階で見る。
  ① 実際に先頭に立った馬で測る（終わってから分かること。効き目の有無を見る）
  ② 前走までの位置から先頭を予想して測る（前日に分かること。使えるかを見る）
①で何も出なければ②を試す意味はない。
"""
import json, statistics as st, sys
from collections import defaultdict

BA = sys.argv[1:] or ['大井', '浦和', '川崎', '船橋']
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
DIVF = {'船橋': 'div_funabashi.json', '大井': 'div_year.json'}

PED = {}
for fn in ('ped_all.jsonl', 'ped2026.jsonl', 'ped_extra.jsonl'):
    try:
        for l in open(f'{SP}/{fn}', encoding='utf-8'):
            v = json.loads(l)
            if v.get('nm') and v.get('sire'):
                PED[v['nm']] = (v['sire'], v.get('bms') or '')
    except FileNotFoundError:
        pass
R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
R.sort(key=lambda r: (r['ymd'], r['rid']))


def overlap(a, b):
    """2頭の父・母父の重なりの数（0〜4）"""
    (s1, b1), (s2, b2) = a, b
    n = 0
    for x in (s1, b1):
        if not x:
            continue
        for y in (s2, b2):
            if y and x == y:
                n += 1
    return n


# 前走までの4角位置から、今日の先頭を予想する材料
HIST = defaultdict(list)
ROWS = []
for r in R:
    c = r.get('c3') or r.get('c4')
    if not c or r['ba'] not in BA:
        continue
    byu = {int(e['u']): e for e in r['e'] if e.get('f', '').isdigit()}
    led = byu.get(int(c[0]))                      # ① 実際に先頭だった馬
    # ② 前走までの位置から先頭を予想（4角の位置の割合がいちばん前の馬）
    pred, best = None, 9
    for e in r['e']:
        v = [x for x in HIST.get(e['nm'], []) if x[0] < r['ymd']][-5:]
        if len(v) >= 2:
            m = st.median(x[1] for x in v)
            if m < best:
                best, pred = m, e
    if led and led['nm'] in PED:
        lp = PED[led['nm']]
        pp = PED.get(pred['nm']) if (pred and pred['nm'] in PED) else None
        fk = dict((json.load(open(f'{SP}/{DIVF[r["ba"]]}', encoding='utf-8'))
                   .get(r['ymd'], {}).get(str(r['R']), {})).get('複勝', [])) \
            if False else {}
        for e in r['e']:
            if not e.get('f', '').isdigit() or e['nm'] not in PED:
                continue
            if e['nm'] == led['nm']:
                continue
            pop = e.get('pop', '')
            ROWS.append(dict(
                ba=r['ba'], ymd=r['ymd'], R=r['R'], u=int(e['u']), nm=e['nm'],
                hit=int(e['f']) <= 3,
                pop=int(pop) if pop.isdigit() else None,
                ov=overlap(PED[e['nm']], lp),
                ovp=overlap(PED[e['nm']], pp) if pp else None,
                same_pred=(pred is not None and pred['nm'] == led['nm'])))
    # 履歴を更新
    i4 = {u: (i + 1) / len(r.get('c4') or [1])
          for i, u in enumerate(r.get('c4') or [])}
    for e in r['e']:
        if int(e['u']) in i4:
            HIST[e['nm']].append((r['ymd'], i4[int(e['u'])]))

D = {}
for ba, fn in DIVF.items():
    try:
        D[ba] = json.load(open(f'{SP}/{fn}', encoding='utf-8'))
    except Exception:
        pass
for x in ROWS:
    fk = dict((D.get(x['ba'], {}).get(x['ymd'], {})
               .get(str(x['R']), {})).get('複勝', []))
    x['fuku'] = fk.get(str(x['u']), 0)
    x['has'] = bool(fk)

sp = [x for x in ROWS if x['ovp'] is not None]
print(f'材料 {len(ROWS)}頭　（父と母父が分かる馬どうし）')
if sp:
    print('  前走までの位置から当てた先頭が、実際の先頭と一致した割合 '
          f'{100*sum(x["same_pred"] for x in sp)/len(sp):.0f}%')


def blk(lab, P, key):
    if len(P) < 300:
        print(f'\n■ {lab} 材料不足（{len(P)}頭）')
        return
    base = 100 * sum(x['hit'] for x in P) / len(P)
    d = [x for x in P if x['has']]
    br = f'　複勝の回収 {sum(x["fuku"] for x in d)/len(d):.0f}%' if d else ''
    print(f'\n■ {lab}　{len(P)}頭　3着内 {base:.1f}%{br}')
    for n in (0, 1, 2, 3):
        v = [x for x in P if x[key] == n]
        if len(v) < 60:
            print(f'    重なり{n}つ                 材料不足({len(v)})')
            continue
        i = sum(x['hit'] for x in v)
        dd = [x for x in v if x['has']]
        roi = f'  回収 {sum(x["fuku"] for x in dd)/len(dd):5.0f}%' if dd else ''
        print(f'    重なり{n}つ　{len(v):>5}頭      {100*i/len(v):5.1f}%{roi}'
              f' {100*i/len(v)-base:+5.1f}pt')
    v = [x for x in P if x[key] >= 1]
    if len(v) >= 60:
        i = sum(x['hit'] for x in v)
        dd = [x for x in v if x['has']]
        roi = f'  回収 {sum(x["fuku"] for x in dd)/len(dd):5.0f}%' if dd else ''
        print(f'    重なり1つ以上 {len(v):>5}頭     {100*i/len(v):5.1f}%{roi}'
              f' {100*i/len(v)-base:+5.1f}pt')


print('\n──① 実際に先頭だった馬と比べる（終わってから分かること）──')
blk('全馬', ROWS, 'ov')
blk('人気薄（6番人気以降）', [x for x in ROWS if x['pop'] and x['pop'] >= 6], 'ov')
for ba in BA:
    blk(f'{ba} 人気薄',
        [x for x in ROWS if x['ba'] == ba and x['pop'] and x['pop'] >= 6], 'ov')
