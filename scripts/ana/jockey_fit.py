# -*- coding: utf-8 -*-
"""騎手と馬の噛み合いを測る。

  python3 scripts/ana/jockey_fit.py <body.jsonl> <raw.jsonl> [--year 2026]

発端は横山武史騎手の証言（2026-11-23 の調査）。
ヨーロピアンの「膝から下をぶらす」追い方は、馬の1完歩の中で動作が
終わらないと成立しない。1完歩が長い馬（ストライド型）には合い、
短い馬（ピッチ型）には合わない。**同じ騎手でも馬によって追い方を変えている。**

ここから出る仮説は「同じ馬の同じ能力に、騎手によって違う値がつく」。
CLAUDE.md の「相対とは尺度が毎回変わること」そのもの。

ただし南関のデータに完歩頻度はない。走法で分類はできない。
代わりに**馬を固定して騎手だけを動かす**形で測る。南関は乗り替わりが
78%あるので（5,461頭中4,260頭）、この形が大量に作れる。

測る形（先に決める。結果を見てから条件を選ばない）
  ① 継続騎乗か乗り替わりか
  ② その騎手がその馬に乗るのが何回目か（乗り慣れ）
  ③ 乗り替わりの方向（騎乗数の多い騎手へ替わったか、少ない騎手へ替わったか）

判定は judge.py の5つの関門。1つでも落ちたら採らない。
  ① 前半後半（該当馬自身の日付の中央。各期の1着3頭未満は検定不成立）
  ② 馬単位の集中度（該当と層の両方から同じ馬を抜く）
  ③ 日単位の集中度（上位3日で払戻の半分を超えたら日を当てているだけ）
  ④ 偽薬200回（該当馬を除いて引く）
  ⑤ 人気帯そろえ

未来の情報を入れない。騎乗歴はその日より前のものだけで作る。
"""
import json
import sys
from collections import defaultdict

sys.path.insert(0, '/home/user/keiba/scripts/ana')
BODY, RAW = sys.argv[1], sys.argv[2]
YEAR = sys.argv[sys.argv.index('--year') + 1] if '--year' in sys.argv else None

_j = open('/home/user/keiba/scripts/ana/judge.py', encoding='utf-8').read()
exec(_j.split("if __name__")[0].replace("SRC = sys.argv[1]", "SRC = BODY")
     .replace("YEAR = sys.argv[sys.argv.index('--year') + 1] "
              "if '--year' in sys.argv else None", ""))


def attach():
    """body に騎手を足し、その日より前の騎乗歴から ①②③ を作る"""
    jk = {}
    rows = sorted((json.loads(l) for l in open(RAW, encoding='utf-8')),
                  key=lambda r: (r['ymd'], r['rid']))
    for r in rows:
        for e in r['e']:
            if str(e.get('f', '')).isdigit() and e.get('jk'):
                jk[(r['rid'], str(e['u']))] = e['jk']

    B = [json.loads(l) for l in open(BODY, encoding='utf-8')]
    B.sort(key=lambda x: (x['ymd'], x['rid']))
    rides = defaultdict(int)          # 騎手 → 通算騎乗数（その日より前）
    last = {}                         # 馬名 → 前走の騎手
    pair = defaultdict(int)           # (馬名, 騎手) → 何回目か（その日より前）
    for x in B:
        j = jk.get((x['rid'], str(x['u'])))
        x['jk'] = j
        if not j:
            continue
        x['jk_rides'] = rides[j]                      # その騎手の通算（前日まで）
        prev = last.get(x['nm'])
        x['cont'] = (prev == j) if prev else None     # 継続騎乗か
        x['prev_jk'] = prev
        x['pair_n'] = pair[(x['nm'], j)]              # この馬に乗るのが何回目か（0=初）
        if prev and prev != j:
            x['jk_up'] = rides[j] - rides[prev]       # 替わった先の騎乗数の差
        rides[j] += 1
        pair[(x['nm'], j)] += 1
        last[x['nm']] = j
    return B


if __name__ == '__main__':
    B = attach()
    if YEAR:
        B = [x for x in B if x['ymd'][:4] == YEAR]
    B = [x for x in B if x.get('ptan') is not None and x.get('n') and x['n'] >= 6]
    W = [x for x in B if x.get('pop') and x['pop'] >= 6 and x.get('jk')]
    print(f'読んだ {len(B):,}頭　騎手あり人気薄 {len(W):,}頭'
          f'　1着{len(wins(W))}頭（{100*len(wins(W))/len(W):.1f}%）'
          f"{'　※' + YEAR + '年のみ' if YEAR else ''}\n")

    res = []
    # ① 継続騎乗か乗り替わりか
    res.append(judge([x for x in W if x.get('cont') is True], W, '人気薄 × 継続騎乗'))
    res.append(judge([x for x in W if x.get('cont') is False], W, '人気薄 × 乗り替わり'))
    # ② 乗り慣れ
    res.append(judge([x for x in W if x.get('pair_n') == 0], W,
                     '人気薄 × その騎手が初めてその馬に乗る'))
    res.append(judge([x for x in W if x.get('pair_n', 0) >= 3], W,
                     '人気薄 × その騎手で4回目以降'))
    # ③ 乗り替わりの方向
    up = [x for x in W if x.get('jk_up') is not None and x['jk_up'] > 0]
    dn = [x for x in W if x.get('jk_up') is not None and x['jk_up'] < 0]
    res.append(judge(up, W, '人気薄 × 騎乗数の多い騎手へ替わった'))
    res.append(judge(dn, W, '人気薄 × 騎乗数の少ない騎手へ替わった'))

    print('─' * 76)
    for r in res:
        print(f"  {'通った' if r['pass'] else '落ちた'}  {r['label']:<34}"
              + (f"  単{r.get('tan',0):>6.1f}%（層{r.get('base',0):.1f}%）"
                 f"1着{r.get('win',0)}頭" if r['n'] >= 20 else '')
              + ('' if r['pass'] else f"  ← {' / '.join(r['why'])}"))
