#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""1日単位の【馬場差】を出し、時計から差し引いて『完全タイム差』にする。

グリーンチャンネル トラックマンTVの「ダートのタイム比較」と同じ考え方。
  走破タイム → タイム差（基準比） → 馬場差を引く → 完全タイム差 → レベル評価

なぜ要るか:
  同じ「良」でも日によって時計の出方は違う。時計をそのまま比べると、
  速い日に走った馬を過大評価し、遅い日に走った馬を過小評価する。
  1日ぶんのレースをまとめて見れば、その日がどれだけ速かったかが分かる。
  それを差し引いて初めて、開催日をまたいで時計を比較できる。

  レベルは2軸で見る（トラックマンTVも「タイム」「メンバー」に分けている）:
    タイム側   … ここで出す完全タイム差
    メンバー側 … race_level.py の次走成績
  両方が高いレースが本当にレベルの高いレース。

基準タイムの作り方:
  南関はクラス表記が結果ページに無いので、R番号をクラスの代理に使う。
  低いRほど下級条件という並びが南関では概ね成立する。
  基準 = (場, 距離, R帯[1-4/5-8/9-12]) ごとの勝ちタイム中央値。

健全性チェック（2026南関1,940Rで実測して修正）:
  「ダートは湿るほど速い」は単調ではない。実測はU字：
      良 → 稍重(遅い) → 重(遅い) → 不良(速い)
  場×距離×R帯を固定した勝ちタイム中央値（良を0とした差）
      大井ダ1600  稍重+0.5 / 重-0.2 / 不良-0.4
      川崎ダ1400  稍重+0.1 / 重-0.1 / 不良-1.1
      船橋ダ1200  稍重+0.7 / 重+1.9 / 不良-0.6
      浦和ダ1400  稍重+0.7 / 重+0.5 / 不良-2.2
  半端に濡れた砂は重くなり、飽和して初めて脚抜きが良くなる。
  よってチェックは「不良が良より速いか」だけを見る。

使い方:
  python3 scripts/ana/baba_sa.py 船橋
  python3 scripts/ana/baba_sa.py 川崎 --from 2026-07-01
  python3 scripts/ana/baba_sa.py 船橋 --races        # レース別の完全タイム差も出す
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import h2h
from gyakubari import parse, sec


def rband(rn):
    return "1-4R" if rn <= 4 else ("5-8R" if rn <= 8 else "9-12R")


def klass(fn):
    """レース名からクラスを取る。data_intro の <h1> に入っている。
    平場は名前そのもの（例 C3三）、特別戦は括弧（例 桑島孝春記念(A2B1)）。
    ※<title> にはこの括弧が入らないので、h1 を見ること。"""
    t = open(fn, "rb").read().decode("euc-jp", errors="replace")
    m = re.search(r'class="data_intro".*?<h1>(.*?)</h1>', t, re.S)
    if not m:
        return None, None
    nm = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S)
    nm = re.sub(r"<[^>]+>", "", nm).strip()
    k = re.search(r"([ABC])\s?([1-4])", nm)
    if k:
        return nm, k.group(1) + k.group(2)
    a = re.search(r"([23]歳)", nm)
    return nm, (a.group(1) if a else None)


def collect(place, dfrom, dto):
    out = []
    for fn in sorted(glob.glob(os.path.join(h2h.CACHE, "2026*.html"))):
        if os.path.getsize(fn) < 20000:
            continue
        p = parse(fn)
        if not p or not p["dist"]:
            continue
        if place and p["place"] != place:
            continue
        if not (dfrom <= p["date"] <= dto):
            continue
        w = next((h for h in p["rows"] if h["chaku"] == 1), None)
        if not w or w["t"] is None:
            continue
        p["wt"] = w["t"]; p["winner"] = w["name"]; p["wnin"] = w["ninki"]
        p["rname"], p["klass"] = klass(fn)
        out.append(p)
    return out



def _fit_par(R, verbose=False):
    """基準タイムを最小二乗で推定する。

        勝ちタイム ≒ base[(場, 距離)] + κ[クラス] × (距離/1000)

    クラスを距離あたりの係数として持つのが要点。こうするとA2の1700mが
    年間3レースしかなくても、全距離のA2からκが決まる。
    （場×距離×クラスの中央値だと母数が割れて基準が作れない条件が残る）

    馬場状態は入れない。その日の速さは馬場差として別に持つため
    （＝parは日をまたいだ共通の物差しでよい）。

    クラスが読めなかったレースは専用の水準に落とし、par_ok=False を立てて
    「標準タイムが当たっていない」と分かるようにする。
    """
    import numpy as np
    rs = [r for r in R if r["wt"] and r["dist"]]
    gs = sorted({(r["place"], r["dist"]) for r in rs})
    ks = sorted({(r["klass"] or "?") for r in rs})
    gi = {g: i for i, g in enumerate(gs)}
    ki = {k: i for i, k in enumerate(ks)}
    X = np.zeros((len(rs), len(gs) + len(ks)))
    y = np.array([r["wt"] for r in rs])
    for i, r in enumerate(rs):
        X[i, gi[(r["place"], r["dist"])]] = 1
        X[i, len(gs) + ki[r["klass"] or "?"]] = r["dist"] / 1000.0
    I = np.eye(X.shape[1]); I[:len(gs), :len(gs)] = 0        # クラス側だけ縮める
    beta = np.linalg.solve(X.T @ X + I, X.T @ y)
    resid = float(np.std(y - X @ beta))
    if verbose:
        c0 = beta[len(gs) + ki.get("C3", 0)]
        print(f"  基準の推定：{len(rs)}レース／残差SD {resid:.2f}秒")
        print("  クラス係数（秒/1000m・C3を0とした差／小さいほど速い）")
        for k in ks:
            print(f"    {k:<4}{beta[len(gs)+ki[k]] - c0:+6.2f}", end="")
        print()
    for r in R:
        g = gi.get((r["place"], r["dist"]))
        k = r["klass"] or "?"
        if g is None or k not in ki:
            r["par_ok"] = False; r["sa"] = None; continue
        par = beta[g] + beta[len(gs) + ki[k]] * (r["dist"] / 1000.0)
        r["par_ok"] = bool(r["klass"])
        r["sa"] = round(r["wt"] - par, 2)


def _fit_basa(byday):
    """馬場差は【1000mあたりの秒】で持ち、距離に比例して効かせる。
    完タイム差 = タイム差 − 馬場差 × 距離/1000
    （距離が延びるほど馬場の影響は積み上がるので、一律に引くのは誤り）"""
    for k, rs in byday.items():
        v = [x["sa"] / (x["dist"] / 1000.0) for x in rs
             if x["sa"] is not None and x.get("par_ok")]
        if len(v) < 4:                                  # 信用できる基準が少ない日は全部使う
            v = [x["sa"] / (x["dist"] / 1000.0) for x in rs if x["sa"] is not None]
        bs = round(st.median(v), 2) if v else 0.0
        for x in rs:
            x["basa"] = bs
            x["kt"] = round(x["sa"] - bs * (x["dist"] / 1000.0), 2)


def main():
    ap = argparse.ArgumentParser(description="1日単位の馬場差と完全タイム差")
    ap.add_argument("place", nargs="?", help="大井/川崎/船橋/浦和（省略で全場）")
    ap.add_argument("--from", dest="dfrom", default="2026-01-01")
    ap.add_argument("--to", dest="dto", default="2026-12-31")
    ap.add_argument("--races", action="store_true", help="レース別の完全タイム差も出す")
    ap.add_argument("--trackman", action="store_true", help="トラックマンTV形式の一覧を出す")
    args = ap.parse_args()

    if args.trackman:
        trackman(args.place, args.dfrom, args.dto)
        return

    R = collect(args.place, args.dfrom, args.dto)
    if not R:
        raise SystemExit("該当レースがキャッシュにない")
    _fit_par(collect(None, "2026-01-01", "2026-12-31"), verbose=True)
    _fit_par(R)

    byday = defaultdict(list)
    for r in R:
        if r["sa"] is not None:
            byday[(r["date"], r["place"])].append(r)
    _fit_basa(byday)

    print(f"■ 馬場差  {args.place or '南関全場'}  {args.dfrom}〜{args.dto}")
    print(f"  対象{len(R)}レース／基準が作れた条件 {len(par)}通り")
    print("  馬場差 ＝ その日の『勝ちタイム − 基準』の中央値。マイナスなら基準より速い日。\n")
    print(f"  {'日付':<11}{'場':<4}{'R数':>4}{'馬場':>5}{'馬場差':>8}   最も速かったレース（完全タイム差）")
    days = []
    for k in sorted(byday):
        rs = byday[k]
        bs = rs[0]["basa"]
        from collections import Counter
        baba = Counter(x["baba"] for x in rs).most_common(1)[0][0]
        best = min(rs, key=lambda z: z["kt"])
        days.append((k, bs, baba, len(rs)))
        print(f"  {k[0]:<11}{k[1]:<4}{len(rs):>4}{baba:>5}{bs:>+8.1f}   "
              f"{best['rn']:>2}R ダ{best['dist']} {best['winner']}({best['kt']:+.1f})")

    print("\n── 馬場状態別の馬場差（健全性チェック）──")
    bb = defaultdict(list)
    for k, bs, baba, n in days:
        bb[baba].append(bs)
    for b in ["良", "稍重", "重", "不良"]:
        if bb[b]:
            print(f"  {b:<4}{len(bb[b]):>3}日  中央{st.median(bb[b]):+.1f}秒  "
                  f"幅{min(bb[b]):+.1f}〜{max(bb[b]):+.1f}")
    if bb["良"] and bb["不良"]:
        ok = st.median(bb["不良"]) < st.median(bb["良"])
        print(f"  ※不良が良より速いか：{'OK' if ok else '要確認'}"
              f"（不良{st.median(bb['不良']):+.1f} / 良{st.median(bb['良']):+.1f}）")
    print("  ※稍重・重は良より遅くなるのが実測（U字）。単調を期待しないこと。")

    if args.races:
        allr = [x for rs in byday.values() for x in rs]
        allr.sort(key=lambda z: z["kt"])
        print(f"\n── 完全タイム差の速い順 上位25（{len(allr)}レース中）──")
        print(f"  {'日付':<11}{'場':<4}{'R':>3}{'距離':>7}{'馬場':>5}{'タイム差':>8}{'完全':>7}  勝ち馬")
        for x in allr[:25]:
            print(f"  {x['date']:<11}{x['place']:<4}{x['rn']:>3}{('ダ'+str(x['dist'])):>7}"
                  f"{x['baba']:>5}{x['sa']:>+8.1f}{x['kt']:>+7.1f}  {x['winner']}"
                  + (f"（{x['wnin']}人気）" if x['wnin'] else ""))




# ── トラックマンTV形式の一覧（別エントリ） ─────────────────────────
def trackman(place, dfrom, dto):
    """グリーンチャンネル トラックマンTVの『ダートのタイム比較』と同じ形で出す。

    完タイム差 = タイム差 − (その日の馬場差 × 距離/1000)
      馬場差は各日の全12レースから実測した1つの数字で、距離に比例して効かせる。
    時計   = 完タイム差の分位（A=上位10%）
    メンバー = そのレースで4着以下だった馬のその後の成績（A=上位10%）
      ※この2つは別物として持つ。時計が速くてもメンバーが薄い日はある。
    """
    from collections import Counter
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from race_level import add_elo, load_races, next_form

    R = collect(place, dfrom, dto)
    ALL = collect(None, "2026-01-01", "2026-12-31")      # 基準は南関全場・年間で作る
    _fit_par(ALL, verbose=True)
    byday_all = defaultdict(list)
    for r in ALL:
        if r["sa"] is not None:
            byday_all[(r["date"], r["place"])].append(r)
    _fit_basa(byday_all)

    # 分位は同じ場の中で取る（場が違えば時計の出方も違うため）
    kts = sorted(x["kt"] for rs in byday_all.values() for x in rs
                 if not place or x["place"] == place)

    def grade(v, arr, rev=False):
        import bisect
        q = bisect.bisect_left(arr, v) / len(arr)
        if rev:
            q = 1 - q
        return "A" if q < 0.10 else "B" if q < 0.30 else "C" if q < 0.70 else "D" if q < 0.90 else "E"

    lv = load_races(); next_form(lv); add_elo(lv)
    mem = {(r["date"], r["place"], r["rn"]): r for r in lv}
    lrates = sorted((r["lo_win"] / r["lo_n"]) for r in lv if r["lo_n"] >= 4)

    days = sorted({(r["date"], r["place"]) for r in R})
    for k in days:
        rs = sorted(byday_all.get(k, []), key=lambda z: z["rn"])
        if not rs:
            continue
        baba = Counter(x["baba"] for x in rs).most_common(1)[0][0]
        bs = rs[0]["basa"]
        tag = "速い" if bs <= -0.25 else ("重い" if bs >= 0.25 else "標準")
        print(f"\n■ {k[1]} {k[0]}（発表{baba}）   馬場差 {bs:+.2f}秒/1000m  {tag}")
        print(f"  {'R':>3}{'距離':>6} {'優勝馬':<15}{'条件':<5}{'ﾀｲﾑ差':>7}{'完ﾀｲﾑ差':>9}  {'時計':<4}{'ﾒﾝﾊﾞｰ':<5} 2着")
        for x in rs:
            w = next((h for h in x["rows"] if h["chaku"] == 1), None)
            s2 = next((h for h in x["rows"] if h["chaku"] == 2), None)
            m = mem.get((x["date"], x["place"], x["rn"]))
            mg = "-"
            if m and m["lo_n"] >= 4:
                mg = grade(m["lo_win"] / m["lo_n"], lrates, rev=True)
            mark = "" if x["par_ok"] else " ※"
            print(f"  {x['rn']:>3}{x['dist']:>6} {(w['name'] if w else '?'):<15}"
                  f"{(x['klass'] or '?'):<5}{x['sa']:>+7.2f}{x['kt']:>+9.2f}  "
                  f"{grade(x['kt'], kts):<4}{mg:<5} {(s2['name'] if s2 else '-')}{mark}")
    ng = [x for rs in byday_all.values() for x in rs
          if not x["par_ok"] and (x["date"], x["place"]) in set(days)]
    print("\n  ※＝条件が読めておらず標準タイムが当たっていない。その完ﾀｲﾑ差と時計評価は信用しない。")
    if ng:
        print("    該当：" + "／".join(f"{x['date']} {x['rn']}R {x['rname'] or ''}" for x in ng))
    print("  メンバー欄の「-」は4着以下の後続が4頭に満たず判定不能。時間が経つほど埋まる。")
    print("  発表馬場と馬場差は対応しない。半端に濡れた砂は重くなり、飽和して初めて速くなる。")



if __name__ == "__main__":
    main()
