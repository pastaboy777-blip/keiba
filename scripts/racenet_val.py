#!/usr/bin/env python3
"""【変態ファクター①】レースレベル伝播ネットワークの OOS 検証。
学習(4-6月)のレースだけでネットワークを構築→各馬のnet_powerを確定させ、
7月ホールドアウトで「net_power上位の人気薄」が実際に好走したかをlift検証。
リーク防止：7月のレース結果はネットワーク構築に一切使わない。

使い方: python3 scripts/racenet_val.py
"""
import sys, datetime
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from racenet import scan, build

USUI = 6


def main():
    # 学習: 4-6月のみでネットワーク構築(7月は一切見ない=リーク無し)
    L = scan(datetime.date(2026, 4, 1), datetime.date(2026, 6, 30))
    level, power, runs = build(L, iters=6)
    print(f"=== 学習(4-6月) {len(L)}R / {len(power)}頭のnet_power確定 ===")

    # 検証: 7月のレース結果で答え合わせ
    T = scan(datetime.date(2026, 7, 1), datetime.date(2026, 7, 31))
    print(f"=== 7月ホールドアウト {len(T)}R ===")
    base = [0, 0]
    # net_power をレース内で相対化(そのレースの出走馬中の順位)して層別
    cells = {"NP1位": [0, 0], "NP2-3位": [0, 0], "NP下位半分": [0, 0], "NP不明": [0, 0]}
    known_top = [0, 0]      # net_power >= +0.3 の人気薄
    for rid, r in T.items():
        # そのレースの出走馬のうち、学習済みnet_powerを持つ馬
        known = [(power[n], n) for n, f, p in r["rows"] if n in power]
        known.sort(reverse=True)
        rank = {n: i + 1 for i, (v, n) in enumerate(known)}
        for name, fin, pop in r["rows"]:
            if pop < USUI:          # 人気薄のみ
                continue
            g = 1 if fin <= 3 else 0
            base[0] += g; base[1] += 1
            if name not in rank:
                cells["NP不明"][0] += g; cells["NP不明"][1] += 1
                continue
            rk = rank[name]; n_known = len(known)
            if rk == 1:
                cells["NP1位"][0] += g; cells["NP1位"][1] += 1
            elif rk <= 3:
                cells["NP2-3位"][0] += g; cells["NP2-3位"][1] += 1
            elif rk > n_known / 2:
                cells["NP下位半分"][0] += g; cells["NP下位半分"][1] += 1
            if power[name] >= 0.3:
                known_top[0] += g; known_top[1] += 1
    b = base[0] / base[1] if base[1] else 0
    print(f"\n 母集団=人気薄(≥{USUI}番人気) 好走=3着内")
    print(f" [ベース] {b:.1%}({base[0]}/{base[1]})")
    for k, c in cells.items():
        if not c[1]:
            print(f" {k:12s} n0"); continue
        r_ = c[0] / c[1]
        print(f" {k:12s} {r_:5.1%}({c[0]:>3}/{c[1]:>4}) lift{(r_/b if b else 0):4.2f}")
    if known_top[1]:
        r_ = known_top[0] / known_top[1]
        print(f" {'NP絶対値≥0.3':12s} {r_:5.1%}({known_top[0]}/{known_top[1]}) lift{(r_/b if b else 0):4.2f}")


if __name__ == "__main__":
    main()
