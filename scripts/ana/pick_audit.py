# -*- coding: utf-8 -*-
"""出したカードを、最終結果で監査する。

  python3 scripts/ana/pick_audit.py <calls.jsonl> <raw.jsonl> <payout.jsonl> \
      [--ymd 20261125] [--ba 浦和] [--from-r 7] [--to-r 12]

カードを出した範囲が全鞍でないときは --from-r / --to-r で合わせる。
合わせないと、はじめから対象外の鞍まで「取りこぼし」に数えてしまう。

2026-11-25 にやらかした失敗を、二度と手で探さないための道具。

## 何が起きたか

宣言の条件「6番人気以降」は、**結果に記録される最終人気**で測ったもの。
だがカードは**当日朝のオッズ**で絞っていた。別のものを買っていた。

浦和 11/25 の全12鞍143頭で照合すると
  朝と最終で人気が一致   76頭（53.1%）
  ずれた              67頭（46.9%）
  2つ以上ずれた         41頭
  6番人気の線をまたいだ   16頭

その日のカードにも2頭まざっていた。
  ポケットシンデレラ  朝4人 → 最終7人  該当なのに落とした（4着）
  モンバイト       朝7人 → 最終5人  対象外なのに入れた（2着）

## この道具がやること

calls.jsonl に記録した該当馬リストと、確定した結果を突き合わせて

  ① 出した馬の着順と払戻
  ② **取りこぼし**（条件に合うのにカードに入れなかった馬）
  ③ **誤爆**（条件に合わないのにカードに入れた馬）
  ④ 朝の人気と最終人気のずれの量

を出す。②③がゼロでなければ、その日の成績は額面どおりではない。

**出した結果を自分に有利に数えないための道具。**
"""
import json
import re
import sys
from collections import defaultdict

CALLS, RAW, PAY = sys.argv[1], sys.argv[2], sys.argv[3]
YMD = sys.argv[sys.argv.index('--ymd') + 1] if '--ymd' in sys.argv else None
BA = sys.argv[sys.argv.index('--ba') + 1] if '--ba' in sys.argv else None
FR = int(sys.argv[sys.argv.index('--from-r') + 1]) if '--from-r' in sys.argv else 1
TO = int(sys.argv[sys.argv.index('--to-r') + 1]) if '--to-r' in sys.argv else 12
AGE_LO, AGE_HI, POP_MIN = 6, 7, 6     # 宣言の条件


def load_races(ymd, ba):
    R, P = {}, {}
    for l in open(RAW, encoding='utf-8'):
        r = json.loads(l)
        if r['ymd'] == ymd and r['ba'] == ba:
            R[r['R']] = r
    for l in open(PAY, encoding='utf-8'):
        d = json.loads(l)
        if d['ymd'] == ymd and d['ba'] == ba:
            P[d['R']] = d
    return R, P


def eligible(e):
    """最終人気ベースで条件に合うか"""
    m = re.match(r'(牡|牝|セ)(\d+)', e.get('sx') or '')
    p = str(e.get('pop', ''))
    if not (m and p.isdigit()):
        return False
    return AGE_LO <= int(m.group(2)) <= AGE_HI and int(p) >= POP_MIN


def main():
    picks = []
    for l in open(CALLS, encoding='utf-8'):
        d = json.loads(l)
        if d.get('kind') == '該当馬' and d.get('picks'):
            if YMD and d.get('ts', '').replace('-', '') != YMD:
                continue
            picks.append(d)
    if not picks:
        print('該当馬の記録が見つからない')
        return
    for d in picks:
        ymd = d['ts'].replace('-', '')
        ba = BA or ('浦和' if '浦和' in (d.get('race') or '') else None)
        if not ba:
            print(f"{d['ts']} 場が特定できない。--ba で指定する")
            continue
        R, P = load_races(ymd, ba)
        if not R:
            print(f'{ymd} {ba} の結果がまだ入っていない')
            continue
        named = {(p[0], p[2]) for p in d['picks']}
        print(f"\n■ {d['ts']} {ba}　カードに出した {len(d['picks'])}頭を監査"
              + (f"（{FR}R〜{TO}Rを対象）" if (FR, TO) != (1, 12) else '') + "\n")

        # ── ① 出した馬 ──
        print(f"  {'R':>3} {'馬':<16}{'出した人気':>9}{'最終人気':>8}{'着':>5}{'払戻':>7}")
        bad = []
        for p in d['picks']:
            Rn, nm, mp = p[0], p[2], p[3]
            r = R.get(Rn)
            e = next((x for x in (r['e'] if r else []) if x['nm'] == nm), None)
            if not e:
                print(f'  {Rn:>3} {nm:<16} 出走が見つからない')
                continue
            fp = str(e.get('pop', ''))
            fpi = int(fp) if fp.isdigit() else None
            f = e.get('f')
            u = str(e.get('u'))
            pay = P.get(Rn, {}).get('tan', {}).get(u, 0)
            ng = '' if eligible(e) else '  ← 条件外（誤爆）'
            if ng:
                bad.append((Rn, nm, mp, fpi, f))
            print(f"  {Rn:>3} {nm:<16}{mp:>8}人{(fpi or '—'):>7}人{str(f):>4}着{pay:>7}{ng}")

        # ── ② 取りこぼし ──
        miss = []
        for Rn, r in sorted(R.items()):
            if not FR <= Rn <= TO:
                continue
            for e in r['e']:
                if eligible(e) and (Rn, e['nm']) not in named:
                    miss.append((Rn, e['nm'], e.get('pop'), e.get('f')))
        print(f"\n  ② 取りこぼし {len(miss)}頭"
              + ('（条件に合うのにカードに入れなかった馬）' if miss else ''))
        for Rn, nm, p, f in miss:
            print(f'     {Rn:>3}R {nm:<16}最終{p:>3}人気  {f:>2}着')

        # ── ③ 誤爆 ──
        print(f"  ③ 誤爆 {len(bad)}頭" + ('（条件外なのにカードに入れた馬）' if bad else ''))
        for Rn, nm, mp, fp, f in bad:
            print(f'     {Rn:>3}R {nm:<16}出した{mp}人気 → 最終{fp}人気  {f}着')

        # ── ④ 最終人気ベースで数え直す ──
        true = [(Rn, e) for Rn, r in R.items() if FR <= Rn <= TO
                for e in r['e'] if eligible(e)]
        wins = [(Rn, e) for Rn, e in true if str(e.get('f', '')) == '1']
        ret = sum(P.get(Rn, {}).get('tan', {}).get(str(e.get('u')), 0)
                  for Rn, e in true)
        print(f"\n  ④ 最終人気で数え直すと　該当 {len(true)}頭　1着 {len(wins)}頭"
              f"　単勝回収 {ret/len(true) if true else 0:.1f}%")
        if bad or miss:
            print('     カードの額面とは違う。報告するときはこちらの数字を使う')

        # ── ⑤ 人気のずれ ──
        print('\n  ⑤ 出したときの人気と最終人気のずれ')
        mv = [(p[3], int(str(next((x for x in R[p[0]]['e'] if x['nm'] == p[2]),
                                 {'pop': '0'}).get('pop', '0')) or 0))
              for p in d['picks'] if p[0] in R]
        mv = [(a, b) for a, b in mv if b]
        if mv:
            s = sum(1 for a, b in mv if a == b)
            c = sum(1 for a, b in mv if (a >= POP_MIN) != (b >= POP_MIN))
            print(f'     照合 {len(mv)}頭　一致 {s}頭（{100*s/len(mv):.0f}%）'
                  f'　{POP_MIN}番人気の線をまたいだ {c}頭')


if __name__ == '__main__':
    main()
