#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""不良馬場のデータを集めて並べる（既定は2026年の川崎）。

なぜ不良を別に見るのか:
  南関のダートは 良→稍重→重→不良 で単調に遅くならない。**U字**になる。
      稍重 +0.20秒 / 重 +0.12秒 / 不良 -0.20秒（対 良・既存の較正値）
  水を含んで締まると、不良がいちばん速い。だから不良は「悪い馬場」ではなく
  【別の馬場】として扱う必要がある。

★母数の警告:
  2026年の川崎で不良は **422レース中12レース（2.8%）**、日にちで3日しかない。
  この規模で「不良に強い血統」「不良巧者」を割り出すことはできない。
  1頭が2回来ればそれだけで率が跳ねる。
  本ツールは【並べて見る】ためのもので、条件を作るためのものではない。

出すもの:
  ① 不良の全レースを、ラップ・通過順・上がりつきで1枚に
  ② 同じ距離の 良／稍重／重 と、勝ちタイム・上がり・前残り度を比較
  ③ 1番人気の信頼度（母数つき）

使い方:
    python3 scripts/ana/furyo.py
    python3 scripts/ana/furyo.py --place 大井 --baba 重
    python3 scripts/ana/furyo.py --csv out/furyo_kawasaki.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bt


def rel4(r, x):
    """4角の相対位置（0=先頭 1=最後方）。前残りかどうかを測るため。"""
    if not r.get("rk") or not x["ub"] or r["n"] < 2:
        return None
    k = r["rk"].get(x["ub"])
    return (k - 1) / (r["n"] - 1) if k else None


def summarize(R, label):
    """1つの馬場状態について、時計・上がり・前残り・人気の信頼度をまとめる。"""
    win, ag, pos, fav, n = [], [], [], [], 0
    for r in R:
        ts = [x["t"] for x in r["rows"] if x["t"]]
        if ts:
            win.append(min(ts))
        for x in r["rows"]:
            if x["chaku"] <= 3:
                if x["agari"]:
                    ag.append(x["agari"])
                p = rel4(r, x)
                if p is not None:
                    pos.append(p)
            if x["ninki"] == 1:
                fav.append(x["chaku"] <= 3)
        n += 1
    return dict(label=label, n=n,
                win=st.mean(win) if win else None,
                ag=st.mean(ag) if ag else None,
                pos=st.mean(pos) if pos else None,
                fav=(sum(fav) / len(fav) * 100) if fav else None, nfav=len(fav))


def main():
    ap = argparse.ArgumentParser(description="不良馬場のデータを集める")
    ap.add_argument("--place", default="川崎")
    ap.add_argument("--baba", default="不良")
    ap.add_argument("--from", dest="dfrom", default="2026-01-01")
    ap.add_argument("--to", dest="dto", default="2026-12-31")
    ap.add_argument("--csv")
    a = ap.parse_args()

    R = bt.load(a.dfrom, a.dto, places=[a.place])
    T = [r for r in R if r["baba"] == a.baba]
    print(f"■ {a.place} {a.dfrom}〜{a.dto}   全 {len(R)}R")
    for k in ("良", "稍重", "重", "不良"):
        m = [r for r in R if r["baba"] == k]
        print(f"   {k:<3}{len(m):>4}R  {len(m)/len(R)*100:>5.1f}%"
              + ("   ★これを見る" if k == a.baba else ""))
    if not T:
        print("該当なし")
        return
    print(f"\n   開催日 {len(sorted({r['date'] for r in T}))}日: "
          f"{'  '.join(sorted({r['date'] for r in T}))}")
    print(f"   ★母数が {len(T)}R しかない。条件を作るには足りない\n")

    # ---- ① 全レースを並べる ----
    print("■ ① 全レース")
    print(f"   {'日付':<11}{'R':>3}{'距離':>6}{'クラス':<6}{'頭':>3}"
          f"{'勝ち':>7}{'平均F':>7}{'上3F':>6}  {'1-3着の4角':<10}ラップ")
    for r in sorted(T, key=lambda z: (z["date"], z["rn"])):
        ts = [x["t"] for x in r["rows"] if x["t"]]
        w = min(ts) if ts else 0
        p = [rel4(r, x) for x in r["rows"] if x["chaku"] <= 3]
        p = [x for x in p if x is not None]
        lap = "-".join(f"{x:.1f}" for x in r["laps"]) if r["laps"] else "—"
        print(f"   {r['date']:<11}{r['rn']:>3}{r['dist']:>6}{(r['klass'] or '?'):<6}"
              f"{r['n']:>3}{w:>7.1f}{(w/(r['dist']/200)):>7.2f}"
              f"{(r['ag3'] or 0):>6.1f}  {(st.mean(p) if p else 0):>9.2f} {lap}")

    # ---- ② 馬場状態ごとの比較（同じ距離だけで比べる） ----
    print("\n■ ② 馬場状態ごと（★同じ距離の中だけで比べる。距離を混ぜると意味がない）")
    dists = sorted({r["dist"] for r in T})
    for d in dists:
        sub = [r for r in R if r["dist"] == d]
        if len(sub) < 8:
            continue
        print(f"\n   {d}m")
        print(f"      {'馬場':<5}{'R':>4}{'勝ちタイム':>10}{'上3F':>8}"
              f"{'1-3着の4角':>11}{'1番人気3着内':>13}")
        for k in ("良", "稍重", "重", "不良"):
            m = summarize([r for r in sub if r["baba"] == k], k)
            if not m["n"]:
                continue
            print(f"      {k:<5}{m['n']:>4}{(m['win'] or 0):>10.1f}"
                  f"{(m['ag'] or 0):>8.1f}{(m['pos'] or 0):>11.2f}"
                  f"{(m['fav'] or 0):>11.0f}% n{m['nfav']}")

    if a.csv:
        os.makedirs(os.path.dirname(a.csv) or ".", exist_ok=True)
        with open(a.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "place", "rn", "dist", "klass", "baba", "n",
                        "chaku", "umaban", "name", "jockey", "time", "agari",
                        "pass", "rel4", "odds", "ninki", "weight", "dw"])
            for r in sorted(T, key=lambda z: (z["date"], z["rn"])):
                for x in r["rows"]:
                    w.writerow([r["date"], r["place"], r["rn"], r["dist"],
                                r["klass"], r["baba"], r["n"], x["chaku"], x["ub"],
                                x["name"], x["jockey"], x["t"], x["agari"],
                                x["pas"], rel4(r, x), x["odds"], x["ninki"],
                                x["weight"], x["dw"]])
        print(f"\n→ {a.csv}  （1行1頭。ここから先は自分で切れる）")

    print("\n※ 不良は『悪い馬場』ではなく【別の馬場】。南関のダートはU字で、")
    print("  水を含んで締まった不良がいちばん速いことがある。良の延長で読まないこと。")


if __name__ == "__main__":
    main()
