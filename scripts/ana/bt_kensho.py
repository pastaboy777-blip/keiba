#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BT値の検証 ── 過去のBT値で次走を当てられるか。

★これはユーザーの明示的な指示があったときだけ回す。
  CLAUDE.md の「過去開催のバックテストはしない」は日々の予想に対するルールで、
  道具そのものの性能を測るのは指示があった場合のみ。

測り方（リークを塞ぐ）:
  対象レースの【前日以前】のBT値だけを使って各馬を並べ、
  そのレースの結果と突き合わせる。同日・当該レースのBT値は絶対に使わない。

★対照を必ず置く。
  「BT1位が25%勝ちました」だけでは何も言えない。1番人気が何%勝つかを
  同じレース集合で並べて初めて、BT値が市場より上か下かが分かる。

使い方:
  python3 scripts/ana/bt_kensho.py --from 2026-07-01 --to 2026-08-02
  python3 scripts/ana/bt_kensho.py --from 2026-07-01 --to 2026-08-02 --place 船橋
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bt


def hist_of(R):
    """馬名 → [(日付, BT値)] の履歴。全期間ぶん作っておく。"""
    M = json.load(open(bt.MODEL))
    h = defaultdict(list)
    for r in R:
        for x in r["rows"]:
            b = bt.bt_of(r, x, M)
            if b:
                h[x["name"]].append((r["date"], b[0]))
    for v in h.values():
        v.sort()
    return h


def before(hist, name, date):
    """その日より前のBT値だけを返す。"""
    return [v for d, v in hist.get(name, []) if d < date]


def tally(rows, label):
    """rows = [(勝ったか, 3着内か, 単勝オッズ)]"""
    n = len(rows)
    if not n:
        return f"{label:<16} 該当なし"
    w = sum(1 for a, b, o in rows if a)
    p = sum(1 for a, b, o in rows if b)
    ret = sum((o * 100 if a and o else 0) for a, b, o in rows)
    return (f"{label:<16} {n:>5}回  1着{w:>4} ({w/n*100:>5.1f}%)  "
            f"3着内{p:>4} ({p/n*100:>5.1f}%)  単回収 {ret/n:>6.1f}%")


def main():
    ap = argparse.ArgumentParser(description="BT値の検証（前走までのBT値で次走を当てられるか）")
    ap.add_argument("--from", dest="dfrom", default="2026-07-01")
    ap.add_argument("--to", dest="dto", default="2026-08-02")
    ap.add_argument("--place")
    ap.add_argument("--min-runs", type=int, default=1, help="過去BT値が何走ぶん必要か")
    a = ap.parse_args()

    ALL = bt.load("2026-01-01", "2026-12-31")
    hist = hist_of(ALL)
    T = [r for r in ALL if a.dfrom <= r["date"] <= a.dto and (not a.place or r["place"] == a.place)]
    print(f"■ 対象 {len(T)}レース（{a.dfrom}〜{a.dto}"
          + (f"・{a.place}" if a.place else "・南関4場") + f"）／履歴のある馬 {len(hist):,}頭\n")

    best, last, avg3, pop, rnd = [], [], [], [], []
    rank_hit = defaultdict(list)
    cover = []
    for r in T:
        cand = []
        for h in r["rows"]:
            v = before(hist, h["name"], r["date"])
            if len(v) >= a.min_runs:
                cand.append((h, max(v), v[-1], st.mean(v[-3:])))
        cover.append(len(cand) / max(1, len(r["rows"])))
        if len(cand) < 4:                       # 半数以上に履歴が無いレースは測らない
            continue
        res = lambda h: (h["chaku"] == 1, h["chaku"] <= 3, h["odds"])
        best.append(res(max(cand, key=lambda z: z[1])[0]))
        last.append(res(max(cand, key=lambda z: z[2])[0]))
        avg3.append(res(max(cand, key=lambda z: z[3])[0]))
        # 対照①：1番人気（同じレース集合で）
        f = next((h for h in r["rows"] if h["ninki"] == 1), None)
        if f:
            pop.append(res(f))
        # 対照②：履歴のある馬から馬番順の先頭を機械的に選ぶ（当てずっぽうの水準）
        rnd.append(res(sorted(cand, key=lambda z: z[0]["ub"] or 99)[0][0]))
        # BT順位ごとの成績
        for i, (h, _, _, _) in enumerate(sorted(cand, key=lambda z: -z[1])[:6]):
            rank_hit[i + 1].append(res(h))

    print(f"  出走馬のうち過去BT値を持つ割合 中央 {st.median(cover)*100:.0f}%\n")
    print("■ その馬の【過去BT値】で1頭選んだとき")
    print("  " + tally(best, "BT最高値 1位"))
    print("  " + tally(last, "BT直近値 1位"))
    print("  " + tally(avg3, "BT直近3走平均"))
    print("\n■ 対照")
    print("  " + tally(pop, "1番人気"))
    print("  " + tally(rnd, "馬番の若い馬"))
    print("\n■ BT最高値の順位別")
    for i in sorted(rank_hit):
        print("  " + tally(rank_hit[i], f"BT {i}位"))


if __name__ == "__main__":
    main()
