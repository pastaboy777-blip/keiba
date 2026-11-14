# -*- coding: utf-8 -*-
"""条件を、今日確立した5つの検定に全部かける。

  python3 scripts/ana/judge.py <body.jsonl> [--year 2026]

2026-11-14 に、自分の数字を6回壊して作った関門。
このうち1つでも落ちたら採らない。

  ① 前半後半        該当馬それ自身の日付の中央で割る。層の中央ではない
                    各期の1着の頭数を出す。3頭未満なら検定不成立
  ② 馬単位の集中度   該当の上位n頭を、該当と層の両方から抜く
                    片側だけ抜くと、同じ1頭が頭数の少ない該当で何倍も効く
  ③ 日単位の集中度   日ごとにまとめて抜く
                    馬1頭ずつでは、同じ日に乗った複数の大穴が見えない
                    上位3日で払戻の半分を超えたら、日を当てているだけ
  ④ 偽薬200回       同じ鞍の人気薄から、該当馬を除いて引く
                    5回では分布の端が見えない。該当馬を含めると約14%で
                    自分を引いて水増しする
  ⑤ 人気帯そろえ     6〜7 / 8〜10 / 11番人気以降

落ちた実例（どれも一度は「残った」と判定していた）
  川崎 人気薄×ふだん前 251頭 単163.5%  → ③で3日抜き+2.8pt・5日抜き-22.1pt
  浦和 人気薄×軽い側1/3 593頭 157.8%  → ④で200回の95%点156.8%とほぼ同値
  船橋 人気薄×6〜7歳   624頭  93.1%  → ③で3日抜き-0.2pt（払戻の51%が3日）

人気薄の1着率は1.9%。母数20頭では1着0.38頭が期待値なので、
**母数ではなく1着の頭数で判定する。**
"""
import json
import random
import sys
from collections import defaultdict

SRC = sys.argv[1]
YEAR = sys.argv[sys.argv.index('--year') + 1] if '--year' in sys.argv else None
SEED = 20261114
PLACEBO = 200
MIN_WIN = 3          # 片期の1着がこれ未満なら検定不成立


def load(path=SRC, year=YEAR):
    R = [json.loads(l) for l in open(path, encoding='utf-8')]
    R = [x for x in R if x.get('ptan') is not None and x.get('n') and x['n'] >= 6]
    if year:
        R = [x for x in R if x['ymd'][:4] == year]
    return R


def key(x):
    return (x['rid'], x['u'])


def tan(S, drop=()):
    d = {key(y) for y in drop}
    S = [x for x in S if key(x) not in d]
    return (sum(x['ptan'] for x in S) / len(S)) if S else 0.0


def fuku(S):
    return (sum(x['pfuku'] for x in S) / len(S)) if S else 0.0


def cut(S):
    """該当馬それ自身の日付の中央で割る"""
    d = sorted({x['ymd'] for x in S})
    if not d:
        return [], []
    m = d[len(d) // 2]
    return [x for x in S if x['ymd'] < m], [x for x in S if x['ymd'] >= m]


def wins(S):
    return [x for x in S if x['ptan']]


def judge(S, POOL, label, verbose=True):
    """5つ全部にかけて、通ったかどうかを返す"""
    out = {'label': label, 'n': len(S), 'pass': True, 'why': []}
    if verbose:
        print(f'■ {label}')
    if len(S) < 20:
        out['pass'] = False
        out['why'].append(f'母数不足({len(S)})')
        if verbose:
            print(f'  母数{len(S)}頭。判定しない\n')
        return out
    h = sorted(wins(S), key=lambda x: -x['ptan'])
    out.update(tan=tan(S), fuku=fuku(S), base=tan(POOL), win=len(h))
    if verbose:
        print(f"  {len(S)}頭  単{tan(S):.1f}%  複{fuku(S):.1f}%  1着{len(h)}頭"
              f"   層 単{tan(POOL):.1f}%（{len(POOL)}頭）  {tan(S)-tan(POOL):+.1f}pt")

    # ① 前半後半
    a, b = cut(S)
    pa, pb = ([x for x in POOL if x['ymd'] < min((y['ymd'] for y in b), default='9')],
              [x for x in POOL if x['ymd'] >= min((y['ymd'] for y in b), default='9')])
    ha, hb = wins(a), wins(b)
    if verbose:
        for t, Q, PQ, hq in (('前半', a, pa, ha), ('後半', b, pb, hb)):
            ng = '  ← 1着3頭未満。検定不成立' if len(hq) < MIN_WIN else ''
            print(f"    ① {t} {len(Q):>5}頭 単{tan(Q):>7.1f}%（層{tan(PQ):>6.1f}%）"
                  f" 1着{len(hq):>3}頭{ng}")
    if min(len(ha), len(hb)) < MIN_WIN:
        out['pass'] = False
        out['why'].append(f'①検定不成立(1着 前{len(ha)}/後{len(hb)})')
    elif not (tan(a) > tan(pa) and tan(b) > tan(pb)):
        out['pass'] = False
        out['why'].append('①片期で層を下回る')

    # ② 馬単位の集中度
    line = []
    for k in (1, 2, 3, 5):
        line.append((k, tan(S, h[:k]) - tan(POOL, h[:k])))
    out['horse3'] = dict(line)[3]
    if verbose:
        print('    ② 馬単位 ' + '  '.join(f'{k}頭抜き{v:+.1f}pt' for k, v in line))
    if dict(line)[3] <= 0:
        out['pass'] = False
        out['why'].append('②上位3頭抜きで層以下')

    # ③ 日単位の集中度
    dd = defaultdict(int)
    for x in S:
        dd[x['ymd']] += x['ptan']
    days = [k for k, v in sorted(dd.items(), key=lambda y: -y[1]) if v > 0]
    tot = sum(x['ptan'] for x in S) or 1
    line = []
    for k in (1, 2, 3, 5):
        g = set(days[:k])
        line.append((k, tan([x for x in S if x['ymd'] not in g])
                     - tan([x for x in POOL if x['ymd'] not in g]),
                     100 * sum(dd[y] for y in days[:k]) / tot))
    out['day3'] = line[2][1]
    out['day3share'] = line[2][2]
    if verbose:
        print(f'    ③ 日単位（{len(days)}日に分布） '
              + '  '.join(f'{k}日抜き{v:+.1f}pt' for k, v, _ in line))
        print(f'       上位3日が払戻の{line[2][2]:.0f}%')
    if line[2][1] <= 0:
        out['pass'] = False
        out['why'].append('③上位3日抜きで層以下')
    if line[2][2] >= 50:
        out['pass'] = False
        out['why'].append(f'③払戻の{line[2][2]:.0f}%が3日に乗っている')

    # ④ 偽薬200回（該当馬を除いて引く）
    byr = defaultdict(list)
    for x in POOL:
        byr[x['rid']].append(x)
    v = []
    for s in range(PLACEBO):
        r = random.Random(SEED + s)
        Q = []
        for x in S:
            c = [y for y in byr.get(x['rid'], []) if y['u'] != x['u']]
            if c:
                Q.append(r.choice(c))
        v.append(tan(Q))
    v.sort()
    act = tan(S)
    over = sum(1 for t in v if t >= act)
    out['p95'] = v[int(PLACEBO * .95)]
    out['over'] = over
    if verbose:
        print(f"    ④ 偽薬{PLACEBO}回  5%点{v[PLACEBO//20]:.1f} / 中央{v[PLACEBO//2]:.1f}"
              f" / 95%点{v[int(PLACEBO*.95)]:.1f} / 最大{v[-1]:.1f}"
              f"　該当以上 {over}/{PLACEBO}")
    if over > PLACEBO * .05:
        out['pass'] = False
        out['why'].append(f'④偽薬の中({over}/{PLACEBO})')

    # ⑤ 人気帯をそろえる
    bad = []
    if verbose:
        print('    ⑤ 人気帯 ', end='')
    for lo, hi, t in ((6, 8, '6〜7番'), (8, 11, '8〜10番'), (11, 99, '11番〜')):
        q = [x for x in S if x.get('pop') and lo <= x['pop'] < hi]
        w = [x for x in POOL if x.get('pop') and lo <= x['pop'] < hi]
        if len(q) < 20:
            if verbose:
                print(f'{t}母数不足  ', end='')
            continue
        d = tan(q) - tan(w)
        if d <= 0:
            bad.append(t)
        if verbose:
            print(f'{t}{d:+.1f}pt  ', end='')
    if verbose:
        print()
    if bad:
        out['pass'] = False
        out['why'].append('⑤' + '・'.join(bad) + 'で層以下')

    if verbose:
        print(f"    {'→ 通った' if out['pass'] else '→ 落ちた：' + ' / '.join(out['why'])}\n")
    return out


if __name__ == '__main__':
    R = load()
    W = [x for x in R if x.get('pop') and x['pop'] >= 6]
    print(f'読んだ {len(R):,}頭　人気薄 {len(W):,}頭'
          f'　1着{len(wins(W))}頭（{100*len(wins(W))/len(W):.1f}%）'
          f"{'　※' + YEAR + '年のみ' if YEAR else ''}\n")
    res = []
    for ba in ('川崎', '大井', '船橋', '浦和'):
        P = [x for x in W if x['ba'] == ba]
        res.append(judge([x for x in P if x.get('hp') is not None and x['hp'] <= 1 / 3],
                         P, f'{ba} 人気薄 × ふだんの4角位置が上位1/3'))
    res.append(judge([x for x in W if x.get('age') and 6 <= x['age'] <= 7], W,
                     '南関4場 人気薄 × 6〜7歳'))
    print('─' * 72)
    for r in res:
        print(f"  {'通った' if r['pass'] else '落ちた'}  {r['label']}"
              + ('' if r['pass'] else f"  （{' / '.join(r['why'])}）"))
