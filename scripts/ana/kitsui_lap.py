#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""きついラップを走った組を追う ── 馬ではなく「レース」を単位にする。

考え方:
  緩まないラップを最後まで走らされたレースでは、出走馬【全員】が代償を払っている。
  着順も時計もその代償を含んだまま残るので、市場は組ごと安く売る。
  だから1頭ずつ拾うのではなく、そのレースの出走馬をまとめてマークして次走を待つ。

  理屈の裏づけ（taikan_lap.py の道具変数法・南関16,717走）:
      流れに1秒速く走らされると、上がりを 0.24秒 失う
      素直に回帰すると +0.007 でゼロに見える（調子の良し悪しが交絡している）
  ＝「走らされた代償」は実在する。ただし距離で全然違う:
      〜1000m -0.03（無し） / 1200m +0.12 / 1400-1500m +0.19 / 1600m〜 +0.03（無し）
  → 追跡対象は 1200〜1500m に限る。それ以外は代償が発生していない。

条件の作り方（2通り持って比べる）:
  【絶対】元の形。11秒台が3本以上 かつ ラップの最大-最小が1.5秒以内
  【相対】場と距離の差を吸収する形。
         基準タイムから引いた平均ハロンより速いハロンが3本以上 かつ 緩みが1.5秒以内
         11秒台が出る難易度は大井1200mと川崎1400mで違うので、
         絶対条件だと速い場ばかり拾って遅い場を取りこぼす。

「煮られた頭数」:
  公表ラップは先頭馬のもの。後ろの馬は息が入っている（8/2船橋5Rでは先頭36.1に対し
  8番手は37.5で1.4秒違った）。だから出走馬を全部追うのではなく、
  【体感テン（走破−上がり3F。1頭ごとの実測）が基準より速かった馬】だけを組とする。

★リークを塞ぐ:
  条件はすべてそのレースの中だけで決まる。次走の結果は一切見ない。
  条件を満たす鞍を機械的に全部拾うので、空振りした組も残る。

使い方:
  python3 scripts/ana/kitsui_lap.py --verify              # 組の次走成績を対照つきで測る
  python3 scripts/ana/kitsui_lap.py --list --from 2026-07-15
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

DIST_LO, DIST_HI = 1200, 1500      # 代償が発生する距離帯（IV推定より）
N_FAST = 3                          # 速いハロンが何本要るか
SPREAD = 1.5                        # 緩みの上限（秒）
HANPA = 10.0                        # これ未満のハロンは半端ハロンとして除く


def full_laps(r):
    return [x for x in r["laps"] if x >= HANPA]


def qualify(r, M, mode="相対"):
    """このレースが『きついラップ』か。返り値 (真偽, 速いハロン数, 緩み)"""
    L = full_laps(r)
    if len(L) < 5 or not (DIST_LO <= r["dist"] <= DIST_HI):
        return False, 0, None
    spread = max(L) - min(L)
    if mode == "絶対":
        fast = sum(1 for x in L if x < 12.0)
    else:
        par = bt.par_of(M["all"], r["place"], r["dist"], r["klass"]) if r["klass"] else None
        if not par:
            return False, 0, None
        avg = par / (r["dist"] / 200.0)          # 基準タイムから出した平均ハロン
        fast = sum(1 for x in L if x < avg)
    return (fast >= N_FAST and spread <= SPREAD), fast, spread


def cooked(r, M):
    """そのレースで実際に代償を払った馬。体感テンが基準より速かった馬。"""
    if not r["klass"] or r["dist"] <= 600:
        return []
    par = bt.par_of(M["ten"], r["place"], r["dist"], r["klass"])
    if not par:
        return []
    out = []
    for x in r["rows"]:
        if not (x["t"] and x["agari"]):
            continue
        if (x["t"] - x["agari"]) < par:          # 基準テンより速く走らされた
            out.append(x)
    return out


def history(R):
    h = defaultdict(list)
    for r in R:
        for x in r["rows"]:
            h[x["name"]].append((r["date"], r, x))
    for v in h.values():
        v.sort(key=lambda z: z[0])
    return h


def next_run(h, name, date):
    for d, r, x in h.get(name, []):
        if d > date:
            return r, x
    return None, None


def tally(v, label):
    if not v:
        return f"{label:<26} 該当なし"
    n = len(v)
    w = sum(1 for a, b, o in v if a)
    p = sum(1 for a, b, o in v if b)
    ret = sum((o * 100 if a and o else 0) for a, b, o in v)
    return (f"{label:<26}{n:>6}回  1着{w:>4}({w/n*100:>5.1f}%)  "
            f"3着内{p:>4}({p/n*100:>5.1f}%)  単回収{ret/n:>7.1f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="dfrom", default="2026-01-01")
    ap.add_argument("--to", dest="dto", default="2026-12-31")
    ap.add_argument("--mode", default="相対", choices=["相対", "絶対"])
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    M = json.load(open(bt.MODEL))
    R = bt.load("2026-01-01", "2026-12-31")
    H = history(R)
    T = [r for r in R if a.dfrom <= r["date"] <= a.dto]

    Q = []
    for r in T:
        ok, fast, sp = qualify(r, M, a.mode)
        if ok:
            Q.append((r, fast, sp, cooked(r, M)))
    print(f"■ {len(T):,}レース中 {len(Q)}鞍が条件に該当（{a.mode}条件・{DIST_LO}〜{DIST_HI}m）")
    if not Q:
        return
    print(f"   煮られた馬 のべ {sum(len(c) for _, _, _, c in Q)}頭"
          f"（1鞍あたり {sum(len(c) for _,_,_,c in Q)/len(Q):.1f}頭 / 出走の"
          f"{sum(len(c) for _,_,_,c in Q)/sum(r['n'] for r,_,_,_ in Q)*100:.0f}%）\n")

    if a.list:
        for r, fast, sp, c in sorted(Q, key=lambda z: z[0]["date"], reverse=True)[:12]:
            print(f"■ {r['date']} {r['place']}{r['rn']}R {r['dist']}m {r['baba']} "
                  f"【{r['klass']}】 速いハロン{fast}本 緩み{sp:.1f}秒")
            print("   ラップ " + "-".join(f"{x:.1f}" for x in r["laps"]))
            for x in sorted(c, key=lambda z: z["chaku"]):
                nr, nx = next_run(H, x["name"], r["date"])
                s = (f"→ {nr['date']} {nr['place']}{nr['rn']}R {nx['chaku']}着"
                     f"({nx['ninki']}人気)") if nr else "→ 次走まだ"
                print(f"     {x['chaku']:>2}着 {x['name']:<14}{x['ninki'] or 0:>3}人気  {s}")
            print()
        return

    if a.verify:
        grp, ctl = [], []
        gband, cband = defaultdict(list), defaultdict(list)
        mark = {(r["date"], id(x)) for r, _, _, c in Q for x in c}
        for r, _, _, c in Q:
            for x in c:
                nr, nx = next_run(H, x["name"], r["date"])
                if nr:
                    v = (nx["chaku"] == 1, nx["chaku"] <= 3, nx["odds"])
                    grp.append(v)
                    nk = nx["ninki"] or 99
                    gband["1-2番人気" if nk <= 2 else ("3-5番人気" if nk <= 5 else "6番人気以下")].append(v)
        # 対照：同じ期間の全馬の「次走」
        for r in T:
            for x in r["rows"]:
                nr, nx = next_run(H, x["name"], r["date"])
                if nr:
                    v = (nx["chaku"] == 1, nx["chaku"] <= 3, nx["odds"])
                    ctl.append(v)
                    nk = nx["ninki"] or 99
                    cband["1-2番人気" if nk <= 2 else ("3-5番人気" if nk <= 5 else "6番人気以下")].append(v)
        print("■ 組の次走 vs 全馬の次走")
        print("  " + tally(grp, "きついラップ組"))
        print("  " + tally(ctl, "対照（同期間の全馬）"))
        print("\n■ 人気帯で揃えて比べる（次走の人気で分ける）")
        print(f"  {'':<14}{'組の3着内':>12}{'対照の3着内':>13}{'組の単回収':>12}{'対照の単回収':>13}")
        for k in ("1-2番人気", "3-5番人気", "6番人気以下"):
            g, cc = gband[k], cband[k]
            if len(g) < 20:
                continue
            f = lambda v: (sum(1 for a_, b_, o in v if b_) / len(v) * 100,
                           sum((o * 100 if a_ and o else 0) for a_, b_, o in v) / len(v))
            gp, gr = f(g); cp, cr = f(cc)
            print(f"  {k:<14}{gp:>10.1f}%(n{len(g)}){cp:>10.1f}%(n{len(cc)})"
                  f"{gr:>11.0f}%{cr:>12.0f}%")


if __name__ == "__main__":
    main()
