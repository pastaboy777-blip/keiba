# -*- coding: utf-8 -*-
"""斤量補正の係数を、決め打ちせずデータから探す。

背景（2026-08-01）:
  時計指数はハンデ戦で機能しなかった。ハンデ戦は過去の実績を斤量で相殺するために
  作られた競走なので、斤量を見ない実績指数は「ハンデキャッパーが既に課税した分」を
  測って強いと言っていることになる。

直し方:
  過去走の指数を「今回の斤量なら何秒で走れるか」に引き直す。

      補正後 = 指数 + (その走りの斤量 − 今回の斤量) × k        [秒/kg]

  k は 1kg=0.2秒 のような通説があるが、それを信じずに k を振って、
  ハンデ戦・定量戦それぞれで指数1位の成績が最大になる k を実測する。
  k=0 が最良なら「斤量は入れないほうがいい」という結論も同じ土俵で出る。

    python3 scripts/jra_kin_tune.py 20260725 20260726 20260718 20260719 20260711 20260712
"""
from __future__ import annotations

import argparse
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jra_ana import collect_day, fit
from jra_backtest import result
from win5_board import sec

KS = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40]


def main():
    ap = argparse.ArgumentParser(description="斤量補正係数の探索")
    ap.add_argument("dates", nargs="+")
    args = ap.parse_args()

    # (k, ハンデ/定量, 指標, 順位) -> [出走, 1着, 3着内, 単払戻, 複払戻]
    acc = defaultdict(lambda: [0, 0, 0, 0.0, 0.0])
    nr = defaultdict(int)

    for ymd in args.dates:
        print(f"\n===== {ymd} =====")
        D = collect_day(ymd)
        par = fit(D)
        for rid, r in D.items():
            res = result(rid)
            if not res:
                continue
            m = re.search(r"(芝|ダ)(\d+)m", r["data1"])
            if not m:
                continue
            surf, dist = m.group(1), int(m.group(2))
            fin = {x["umaban"]: x for x in res}
            hcp = "ハンデ" if "ハンデ" in r["data2"] else "定量"

            runners = []
            for h in r["horses"]:
                if h["umaban"] not in fin or not h["kin"]:
                    continue
                ps = []
                for p in h["past"]:
                    b, t = par(p.get("place"), p.get("surf"), p.get("dist"), p.get("baba", "良")), sec(p.get("time"))
                    if b is None or t is None or not p.get("kin"):
                        continue
                    p["fig"] = round(b - t, 2)
                    ps.append(p)
                if len(ps) < 3:
                    continue
                runners.append((h, ps, fin[h["umaban"]]))
            if len(runners) < 6:
                continue
            nr[hcp] += 1

            for k in KS:
                rows = []
                for h, ps, R in runners:
                    adj = [p["fig"] + (p["kin"] - h["kin"]) * k for p in ps]
                    cond = [p["fig"] + (p["kin"] - h["kin"]) * k for p in ps
                            if p.get("surf") == surf and abs(p.get("dist", 0) - dist) <= 200]
                    rows.append((st.mean(sorted(adj, reverse=True)[:2]),
                                 max(cond) if cond else None, R))
                for key, lst in (("top2", sorted(rows, key=lambda x: -x[0])),
                                 ("cond", sorted([x for x in rows if x[1] is not None],
                                                 key=lambda x: -x[1]))):
                    for i, (_, _, R) in enumerate(lst[:3], 1):
                        d = acc[(k, hcp, key, i)]
                        d[0] += 1
                        if R["fin"] == 1:
                            d[1] += 1
                            d[3] += (R["odds"] or 0) * 100
                        if R["fin"] <= 3:
                            d[2] += 1
                            d[4] += R["fuku"]

    print(f"\n{'='*78}")
    print(f"■ 定量 {nr['定量']}レース ／ ハンデ {nr['ハンデ']}レース\n")
    for hcp in ("定量", "ハンデ"):
        for key, lab in (("top2", "上位2走平均"), ("cond", "該当条件指数")):
            print(f"-- {hcp} × {lab} の1位")
            print(f"   {'k(秒/kg)':>9} {'出走':>5} {'勝率':>7} {'複勝率':>7} {'単回収':>8} {'複回収':>8}")
            for k in KS:
                n, w, p3, tp, fp = acc[(k, hcp, key, 1)]
                if n:
                    print(f"   {k:9.2f} {n:5} {w/n*100:6.1f}% {p3/n*100:6.1f}% "
                          f"{tp/(n*100)*100:7.1f}% {fp/(n*100)*100:7.1f}%")
            print()


if __name__ == "__main__":
    main()
