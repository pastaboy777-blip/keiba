#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""出走表の【確定逃げ馬の数】でレースの型を分岐させる。

軸を1本に決めるのをやめるための道具。
同じ日でも、逃げ馬が2頭ぶつかるレースと1頭で行けるレースでは結果の出方が逆になる。

  前づけ馬 … 直近3走の4角順位の【中央値が2番手以内】

  ★定義は4通り試して選んだ（南関4場ダ1200m・前半3Fの中央値で比較）
      A 4角1番手が2回以上   0-1頭36.3(429R) / 2頭35.4(11R)  差+0.9 …母数が出ない
      B 4角1番手が1回以上   0-1頭36.5(299R) / 2頭36.0(81R)  差+0.5 …緩すぎて差が痩せる
      C 4角が全部2番手以内   0-1頭36.3(420R) / 2頭35.3(23R)  差+1.0 …母数が出ない
      D 4角中央値が2番手以内 0-1頭36.5(349R) / 2頭35.7(73R) / 3頭以上35.5(22R) 差+0.8 ←採用
    母数と効果の両立でDを採る。Aは概念としては正しいが、南関288鞍で2頭以上が8鞍しかない。
  逃げ2頭以上 → 前半が速くなる → 前が潰れる → 後ろから来る
  逃げ1頭以下 → 前半が落ち着く → 動ける馬が前を取ってそのまま

2026/8/2 船橋で観測（1200m戦のみ・距離をそろえた比較）:
    逃げ2頭 3R 37.2 / 5R 36.1 / 8R 36.2   ← 例外なく速い
    逃げ0-1頭 1R 38.9 / 2R 38.4 / 4R 39.0 / 7R 38.0
  勝ち馬の位置での的中は12鞍中9鞍。ペースの予測のほうが当たる。

前走からの位置取りは結果ページのコーナー通過順位だけで作れるので、
出馬表がなくても過去にさかのぼって検証できる（リークなし）。

使い方:
  python3 scripts/ana/nige_bunki.py 船橋            # 過去全開催で検証
  python3 scripts/ana/nige_bunki.py 川崎 --from 2026-06-01
"""
from __future__ import annotations

import argparse
import glob
import os
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import h2h
from gyakubari import parse
from nar_day import classify


def rank4(c4):
    import re
    out, r = {}, 0
    for tok in re.findall(r"\([^)]*\)|\d+", c4):
        ns = [int(v) for v in re.findall(r"\d+", tok)] if tok.startswith("(") else [int(tok)]
        for u in ns:
            r += 1
            out[u] = r
    return out


def main():
    ap = argparse.ArgumentParser(description="確定逃げ馬の数でレースの型を分岐")
    ap.add_argument("place", help="場。allで南関4場まとめて")
    ap.add_argument("--from", dest="dfrom", default="2026-01-01")
    ap.add_argument("--to", dest="dto", default="2026-12-31")
    ap.add_argument("--dist", type=int, help="距離を固定して比べる（既定は距離別に出す）")
    args = ap.parse_args()

    # 履歴は南関全場から作る。馬は場をまたいで走るので、対象場だけだと
    # 直近3走が拾えず確定逃げが数えられない（当初これで全部0-1頭になった）。
    R = []
    for fn in sorted(glob.glob(os.path.join(h2h.CACHE, "2026*.html"))):
        if os.path.getsize(fn) < 20000:
            continue
        p = parse(fn)
        if p:
            p["r4"] = rank4(p["c4"])
            R.append(p)
    R.sort(key=lambda z: (z["date"], z["place"], z["rn"]))

    hist = defaultdict(list)                 # 馬名 -> [4角順位, ...] 時系列
    rows = []
    for r in R:
        target = ((args.place == "all" or r["place"] == args.place)
                  and args.dfrom <= r["date"] <= args.dto)
        if not target:
            for h in r["rows"]:
                if h["ub"] in r["r4"]:
                    hist[h["name"]].append(r["r4"][h["ub"]])
            continue
        n = 0
        for h in r["rows"]:
            past = hist[h["name"]][-3:]      # 直近3走（このレースより前だけ）
            if len(past) >= 2 and st.median(past) <= 2:
                n += 1
        ls = r["laps"][1:] if (r["laps"] and r["laps"][0] < 10) else r["laps"]
        f3 = sum(ls[:3]) if len(ls) >= 3 else None
        w = next((h for h in r["rows"] if h["chaku"] == 1), None)
        wr = r["r4"].get(w["ub"]) if w else None
        rows.append(dict(date=r["date"], rn=r["rn"], dist=r["dist"], nige=n, f3=f3,
                         wrank=wr, field=len(r["rows"])))
        for h in r["rows"]:
            if h["ub"] in r["r4"]:
                hist[h["name"]].append(r["r4"][h["ub"]])

    rows = [x for x in rows if x["f3"] and x["wrank"] and x["field"] >= 6]
    print(f"■ {args.place} {args.dfrom}〜{args.dto}  {len(rows)}レース")

    print("\n── 確定逃げの数 × 前半3F（距離別・母数5R以上）──")
    g = defaultdict(lambda: defaultdict(list))
    for x in rows:
        k = "0-1頭" if x["nige"] <= 1 else ("2頭" if x["nige"] == 2 else "3頭以上")
        g[x["dist"]][k].append(x["f3"])
    print(f"  {'距離':>6}{'0-1頭':>16}{'2頭':>16}{'3頭以上':>16}")
    for d in sorted(g):
        if sum(len(v) for v in g[d].values()) < 15:
            continue
        _ = None
        row = []
        for k in ("0-1頭", "2頭", "3頭以上"):
            v = g[d][k]
            row.append(f"{st.median(v):.1f}({len(v)}R)" if len(v) >= 4 else "—")
        print(f"  {d:>6}" + "".join(f"{z:>16}" for z in row))

    print("\n── 確定逃げの数 × 勝ち馬の4角位置（相対）──")
    gg = defaultdict(list)
    for x in rows:
        k = "0-1頭" if x["nige"] <= 1 else ("2頭" if x["nige"] == 2 else "3頭以上")
        gg[k].append(x["wrank"] / x["field"])
    print(f"  {'区分':<10}{'R数':>5}{'勝ち馬の相対位置':>18}{'4角4番手以降から勝った率':>24}")
    for k in ("0-1頭", "2頭", "3頭以上"):
        v = gg[k]
        if len(v) < 8:
            continue
        back = sum(1 for x in rows
                   if (("0-1頭" if x["nige"] <= 1 else ("2頭" if x["nige"] == 2 else "3頭以上")) == k
                       and x["wrank"] >= 4))
        print(f"  {k:<10}{len(v):>5}{st.mean(v):>18.3f}{back/len(v)*100:>23.1f}%")
    print("\n  相対位置は 0に近いほど前から勝っている。0.5なら中団。")


if __name__ == "__main__":
    main()
