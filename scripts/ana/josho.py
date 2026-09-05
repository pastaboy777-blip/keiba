#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""個体の上昇度 ── その馬自身の過去と比べて、いま上がっているかを σ で出す。

なぜ「その馬自身」なのか:
  調教の末3Fは馬ごとに水準がまるで違う。速い馬は普段から速い。
  だから他馬と比べても「速い馬」が並ぶだけで、**状態の変化**は出てこない。
  知りたいのは「この馬が、この馬にしては、速くなっているか」。

だが自己比較だけでは足りない。条件が毎回違うから:
    脚色       強く追えば速くなる（返し馬の強度と同じ罠）
    コース系統  坂路とコースでは時計のスケールが違う
    馬場       重い日は遅い
    追い切りの距離 5F追いの3Fと4F追いの4Fが混ざる

そこで2段構えにする:

  ① 条件を剥がす（全馬まとめて最小二乗）
        末3F ≒ 馬の固有値 + 脚色 + コース系統 + 馬場 + 距離
     馬の固有値は各馬の平均を引いて消す（＝馬ごとの水準を持たせる）。
     残差＝条件で説明できない分。

  ② 残差の中で、その馬の過去と直近を比べる
        上昇度 = (過去の残差の中央値 − 直近の残差) ÷ 全体の残差SD
     ＋なら速くなっている＝上昇。σ単位なので馬をまたいで並べられる。

  ★ばらつきは【全体の残差SD】で割る。各馬のSDで割らない。
    1頭あたり5〜10本しかないので、自前のSDは推定が暴れる。

★プラセボを必ず取ること:
  各馬の中で時間の順序だけシャッフルして同じ計算をする。
  「上昇」の分布が実測とプラセボで変わらなければ、それは並べ替えの綾。

使い方:
    python3 scripts/ana/josho.py out/cyokyo_2026101101_0907.json
    python3 scripts/ana/josho.py out/*.json --top 30
"""
from __future__ import annotations

import argparse
import glob
import json
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cyokyo_jikei import kind, f3_of

MIN_RUNS = 3          # 上昇度を出すのに要る【走数】（1走1本に落とすため）
RECENT = 1            # 「直近」として扱う本数


def load(paths):
    """★1走につき1本（その走で最も速い＝本追い）に落とす。

    走の中の乗り込みと本追いを両方並べると、走をまたいだ比較が壊れる。
    実例: 同じ「馬なり」でも 1ハロン15.0秒（乗り込み）と 12.8秒（本追い）が混ざる。
    """
    rows = []
    for p in paths:
        D = json.load(open(p))
        for rid, hs in D.items():
            for ub, h in hs.items():
                for i, q in enumerate(h["rows"]):
                    f3 = f3_of(q.get("cum"), q.get("course"))     # 保存済みJSONも作り直さず判定し直す
                    if not f3:
                        continue
                    rows.append(dict(
                        horse=h["name"], race=q.get("rid", rid), cur=rid, ub=int(ub),
                        f3=float(f3), ashi=q.get("ashi") or "不明",
                        kind=kind(q.get("course")), baba=(q.get("baba") or "不明")[:2],
                        nleg=len(q.get("cum") or []),      # 累積の本数＝追った距離の代理
                        y=q.get("_y", 0), mm=q["mm"], dd=q["dd"]))
    # 走ごとに最速の1本だけ残し、その走に何本記録されていたかを持たせる
    g = defaultdict(list)
    for r in rows:
        g[(r["horse"], r["race"])].append(r)
    keep = []
    for v in g.values():
        b = min(v, key=lambda r: r["f3"] if r["kind"] != "坂路" else r["f3"] + 100)
        b["nrec"] = len(v)                # ★本数が多いほど速い本が混ざる＝要補正
        keep.append(b)
    # 末尾からの位置（-1が直近）。★全馬で直近ほど速いという癖があるので要補正
    h = defaultdict(list)
    for r in keep:
        h[r["horse"]].append(r)
    for w in h.values():
        w.sort(key=lambda q: (q["y"], q["mm"], q["dd"]))
        for i, r in enumerate(w):
            r["pos"] = i - len(w)
    return keep


def design(rows):
    """条件をダミー変数に。馬の固有値は平均を引いて消す。"""
    lev = {}
    for k in ("ashi", "kind", "baba"):
        vs = sorted({r[k] for r in rows})[1:]        # 1つを基準に落とす
        for v in vs:
            lev[(k, v)] = len(lev)
    # ＋距離 ＋その走の記録本数 ＋末尾からの位置（3つとも系統的な偏りの源）
    ncol = len(lev) + 3
    X = np.zeros((len(rows), ncol))
    for i, r in enumerate(rows):
        for k in ("ashi", "kind", "baba"):
            j = lev.get((k, r[k]))
            if j is not None:
                X[i, j] = 1.0
        X[i, -3] = r["nleg"]
        X[i, -2] = r["nrec"]
        X[i, -1] = r["pos"]
    return X, lev


def strip(rows):
    """馬ごとの平均を引いてから条件係数を推定し、残差を返す（馬固定効果）。"""
    X, lev = design(rows)
    y = np.array([r["f3"] for r in rows])
    idx = defaultdict(list)
    for i, r in enumerate(rows):
        idx[r["horse"]].append(i)
    Xd, yd = X.copy(), y.copy()
    for ii in idx.values():                          # within変換
        Xd[ii] -= Xd[ii].mean(0)
        yd[ii] -= yd[ii].mean()
    beta, *_ = np.linalg.lstsq(Xd, yd, rcond=None)
    res = y - X @ beta
    for ii in idx.values():                          # 馬の水準を残差から除く
        res[ii] -= res[ii].mean()
    for r, v in zip(rows, res):
        r["res"] = float(v)
    return beta, lev, float(np.std(res))


def rise(rows, sd, shuffle=False, seed=0):
    """馬ごとの上昇度。＋なら「その馬にしては速くなっている」。"""
    by = defaultdict(list)
    for r in rows:
        by[r["horse"]].append(r)
    rnd = random.Random(seed)
    out = []
    for nm, w in by.items():
        if len(w) < MIN_RUNS:
            continue
        w = sorted(w, key=lambda q: (q["y"], q["mm"], q["dd"]))
        v = [q["res"] for q in w]
        if shuffle:
            rnd.shuffle(v)
        past, now = v[:-RECENT], st.mean(v[-RECENT:])
        out.append(dict(horse=nm, n=len(w), z=(st.median(past) - now) / sd,
                        race=w[-1]["cur"], ub=w[-1]["ub"],
                        last=f"{w[-1]['mm']}/{w[-1]['dd']}",
                        ashi=w[-1]["ashi"], kind=w[-1]["kind"]))
    return out


def main():
    ap = argparse.ArgumentParser(description="調教から個体の上昇度を出す")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--shuffle", type=int, default=200)
    a = ap.parse_args()

    paths = [p for g in a.paths for p in glob.glob(g)]
    rows = load(paths)
    print(f"■ {len(paths)}ファイル / 追い切り {len(rows):,}本 / "
          f"{len({r['horse'] for r in rows}):,}頭\n")
    if len(rows) < 50:
        print("× 本数が足りません。先に cyokyo_shushu.py で集めてください。")
        return

    beta, lev, sd = strip(rows)
    print("■ ① 剥がした条件（末3Fへの効き・秒）")
    for (k, v), j in sorted(lev.items(), key=lambda x: x[1]):
        print(f"   {k:<6}{v:<8}{beta[j]:>+7.2f}")
    print(f"   {'距離':<6}{'(累積本数)':<8}{beta[-3]:>+7.2f}")
    print(f"   {'記録数':<6}{'(走内の本数)':<8}{beta[-2]:>+7.2f}  ★多いほど速い本が混ざる分")
    print(f"   {'位置':<6}{'(末尾からの)':<8}{beta[-1]:>+7.2f}  ★直近ほど速いという全馬共通の癖")
    print(f"   残差SD {sd:.2f}秒  ← 上昇度はこれで割る\n")

    real = rise(rows, sd)
    if not real:
        print(f"× {MIN_RUNS}本以上ある馬がいません。")
        return
    ps = [q["z"] for s in range(a.shuffle) for q in rise(rows, sd, True, s)]
    hi = sorted(ps)[int(len(ps) * 0.95)]
    print(f"■ ② プラセボ（各馬の中で順序だけシャッフル／{a.shuffle}回）")
    print(f"   実測の上位5%    {sorted(q['z'] for q in real)[int(len(real)*0.95)]:+.2f}σ")
    print(f"   プラセボの95%点 {hi:+.2f}σ   ← これを超えた馬だけ意味がある\n")

    real.sort(key=lambda q: -q["z"])
    print(f"■ ③ 上昇度（{MIN_RUNS}本以上の {len(real)}頭）")
    print(f"   {'馬名':<15}{'本':>3}{'上昇度':>8}   {'直近':>6} {'脚色':<5}{'系統':<5}{'鞍'}")
    for q in real[:a.top]:
        mk = "★" if q["z"] > hi else " "
        print(f" {mk} {q['horse']:<15}{q['n']:>3}{q['z']:>+8.2f}σ  {q['last']:>6} "
              f"{q['ashi']:<5}{q['kind']:<5}{int(q['race'][10:12])}R{q['ub']}番")
    print("\n   ＋＝その馬にしては速くなっている／−＝落ちている")
    print("   ★＝プラセボの95%点を超えた。それ以外は並べ替えの綾と区別がつかない")


if __name__ == "__main__":
    main()
