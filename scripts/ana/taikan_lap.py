#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""体感ラップ ── 「そのレースが速かった」ではなく「その馬にとって速かった」を測る。

★ユーザーの明示的な指示で回すもの。

公表されるラップは先頭馬が刻んだもの。10馬身後ろの馬はまったく違う流れを走っている。
米国のペース分析（Beyer / Brohamer）は各コーナーの着差から1頭ごとの区間を復元する。
南関は各コーナーの着差が出ないので順位から近似する ── のだが、
実は【近似が要らない部分】と【要る部分】がある。そこを混ぜないのが肝。

  ■ 近似ゼロで取れるもの（1頭ごとの実測）
      体感テン   = 走破タイム − 上がり3F     … その馬自身の前半(距離-600m)
      体感上がり = 上がり3F                  … その馬自身の後半600m
    上がり3Fは1頭ごとに公表されているので、2分割の体感ラップは完全に正確。

  ■ 近似が要るもの
      コーナーごとの細かい形。順位差を秒に直す必要がある。
      ただしここも【推測しない】。最終コーナーの順位と、体感テンの実測を
      突き合わせれば「1順位あたり何秒か」がデータから較正できる。
          体感テン(自分) − 体感テン(先頭) ≒ a × (最終コーナー順位 − 1)
      距離ごとに a を推定する。速度が違えば1馬身の秒数も違うため。

測るもの:
  ① 較正 … 1順位あたりの秒数（距離別）
  ② その馬の「エネルギー配分の代償」
       体感テンを自分の平常より速くしたとき、上がりをどれだけ失うか。
       傾きが急な馬＝一本調子。緩い馬＝速く行っても終いが持つ。
     ★ここは着順を一切使わない。実測タイムどうしの関係だけを見る。
  ③ その傾きが【次走に持ち越されるか】
       過去走だけから傾きを作り、次走で当てにいく。
       c≒1 なら本物、c≒0 ならただのブレ。

使い方:
  python3 scripts/ana/taikan_lap.py
  python3 scripts/ana/taikan_lap.py --show 2026-08-02 船橋 8
"""
from __future__ import annotations

import argparse
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bt          # パーサだけ借りる


def rows_of(r):
    """1レースぶんを (馬, 体感テン, 上がり, 最終コーナー順位) に開く。"""
    out = []
    for x in r["rows"]:
        if not (x["t"] and x["agari"]):
            continue
        p = [int(v) for v in re.findall(r"\d+", x.get("pas") or "")]
        out.append((x, x["t"] - x["agari"], x["agari"], p[-1] if p else None, p))
    return out


def calib(R, verbose=False):
    """1順位あたり何秒か を距離別にデータから較正する。

    体感テンは実測なので、先頭との差は真の値。それを最終コーナーの順位差に回帰する。
    """
    by = defaultdict(list)
    for r in R:
        v = [z for z in rows_of(r) if z[3]]
        if len(v) < 6:
            continue
        lead = min(v, key=lambda z: z[3])          # 最終コーナーで先頭だった馬
        for x, ten, ag, rk, _ in v:
            if rk == lead[3]:
                continue
            by[r["dist"]].append((rk - lead[3], ten - lead[1]))
    out = {}
    for d, v in by.items():
        if len(v) < 200:
            continue
        mx = st.mean(a for a, _ in v); my = st.mean(b for _, b in v)
        sxx = sum((a - mx) ** 2 for a, _ in v)
        out[d] = sum((a - mx) * (b - my) for a, b in v) / sxx if sxx else None
    if verbose:
        print("■ 較正：最終コーナーで1順位後ろにいると、前半タイムが何秒遅いか")
        for d in sorted(out):
            n = len(by[d])
            print(f"    {d:>5}m  {out[d]:+.3f} 秒/順位   （{n:,}走から）")
    return out


def show(R, date, place, rn, A):
    """1レースを取り出して、公表ラップと各馬の体感ラップを並べる。"""
    r = next((x for x in R if x["date"] == date and x["place"] == place and x["rn"] == rn), None)
    if not r:
        print("該当レースなし"); return
    a = A.get(r["dist"])
    v = [z for z in rows_of(r) if z[3]]
    lead = min(v, key=lambda z: z[3])
    print(f"■ {r['date']} {r['place']}{r['rn']}R {r['dist']}m {r['baba']} 【{r['klass']}】")
    print(f"  公表ラップ（先頭馬）  {'-'.join(f'{x:.1f}' for x in r['laps'])}")
    print(f"  先頭の体感  テン{lead[1]:.1f} → 上がり{lead[2]:.1f}\n")
    print(f"  {'着':>3} {'馬名':<14}{'4角':>4}{'体感テン':>9}{'体感上がり':>10}"
          f"{'先頭とのテン差':>12}{'順位から予想される差':>18}")
    for x, ten, ag, rk, p in sorted(v, key=lambda z: z[0]["chaku"]):
        exp = (a * (rk - lead[3])) if a else 0
        print(f"  {x['chaku']:>3} {x['name']:<14}{rk:>4}{ten:>9.1f}{ag:>10.1f}"
              f"{ten - lead[1]:>+12.1f}{exp:>+18.1f}")
    print("\n  ※『順位から予想される差』とズレた分が、順位では説明できない部分。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-prior", type=int, default=5)
    ap.add_argument("--show", nargs=3, metavar=("日付", "場", "R"))
    a = ap.parse_args()
    R = bt.load("2026-01-01", "2026-12-31")
    print(f"■ 南関 {len(R):,}レース\n")
    A = calib(R, verbose=True)
    print()

    if a.show:
        show(R, a.show[0], a.show[1], int(a.show[2]), A)
        return

    # ---- ② エネルギー配分の代償（着順を一切使わない） ----
    # 体感テン・体感上がりを 距離で正規化して 秒/1000m に揃える
    H = defaultdict(list)
    for r in R:
        if r["dist"] <= 600:
            continue
        for x, ten, ag, rk, _ in rows_of(r):
            H[x["name"]].append(dict(date=r["date"],
                                     ten=ten / ((r["dist"] - 600) / 1000.0),
                                     ag=ag / 0.6, dist=r["dist"], chaku=x["chaku"],
                                     n=r["n"], ninki=x["ninki"], odds=x["odds"]))
    for v in H.values():
        v.sort(key=lambda z: z["date"])

    slopes = []
    for nm, v in H.items():
        if len(v) < a.min_prior:
            continue
        mt = st.mean(z["ten"] for z in v); ma = st.mean(z["ag"] for z in v)
        sxx = sum((z["ten"] - mt) ** 2 for z in v)
        if sxx < 1e-6:
            continue
        b = sum((z["ten"] - mt) * (z["ag"] - ma) for z in v) / sxx
        slopes.append(b)
    print("■ エネルギー配分の代償（体感テンを1秒速めると、上がりを何秒失うか）")
    print(f"    {len(slopes):,}頭   中央 {st.median(slopes):+.2f}   "
          f"5%tile {sorted(slopes)[len(slopes)//20]:+.2f}   "
          f"95%tile {sorted(slopes)[-len(slopes)//20]:+.2f}")
    print(f"    代償が負（速く行くほど上がりも速い）の馬 "
          f"{sum(1 for b in slopes if b < 0)/len(slopes)*100:.0f}%")
    print("    ※ 傾きが負なら、テンの速さは『調子が良い』の表れで、代償になっていない\n")

    # ---- ③ 傾きは次走に持ち越されるか ----
    X, Y = [], []
    for nm, v in H.items():
        for i in range(a.min_prior, len(v)):
            pri = v[:i]
            mt = st.mean(z["ten"] for z in pri); ma = st.mean(z["ag"] for z in pri)
            sxx = sum((z["ten"] - mt) ** 2 for z in pri)
            if sxx < 1e-6:
                continue
            b = sum((z["ten"] - mt) * (z["ag"] - ma) for z in pri) / sxx
            X.append(b * (v[i]["ten"] - mt))       # 傾きから予想される上がりのズレ
            Y.append(v[i]["ag"] - ma)              # 実際の上がりのズレ
    if len(X) > 200:
        mx = st.mean(X); my = st.mean(Y)
        sxx = sum((x - mx) ** 2 for x in X)
        c = sum((x - mx) * (y - my) for x, y in zip(X, Y)) / sxx
        print("■ その傾きは次走に持ち越されるか")
        print(f"    n={len(X):,}   c = {c:+.3f}")
        print("    c≒1 … 馬ごとの配分特性は本物")
        print("    c≒0 … 過去のブレを拾っただけ")


if __name__ == "__main__":
    main()
