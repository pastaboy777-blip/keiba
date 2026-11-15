#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""父（種牡馬）が【市場のオッズに入っていない情報】を持っているかを測る。

なぜこの形か:
  「パイロ産駒はダートが得意」は当たっていても買えない。
  誰でも知っていることは、既にオッズに入っているから。
  だから父の成績そのものではなく、【市場の確率からのズレ】を父で束ねる。

      残差 = 実際に勝ったか(0/1) − 市場の勝率
      父ごとに残差を平均する。ゼロから離れれば、市場が父を読み違えている

  ★市場の勝率は【そのレースの全出走馬】の単勝オッズで正規化する。
    測れる馬だけで割ると確率が水増しされる（market_model.py と同じ落とし穴）。

★測り方を2つ持つ。判定は【後者】でする:

  ① ばらつき検定 … 父ごとの平均残差が、シャッフルより大きくばらつくか
  ② 転移検定    … 前半で出た父のズレが、後半でも同じ向きに出るか

  ①だけでは足りない。48種に割れば意味が無くてもばらつくし、
  実測がプラセボ95%上限のすぐ上か下かは【乱数の種で入れ替わる】。
  持ち越されなければ、そのズレは来週の馬券には使えない。

実測（2026年の南関 / 父の判明した19,807走）:

  ① ばらつき  実測 0.02049 ／ プラセボ95%上限 0.02017〜0.02089（種で動く）
              超過率 3.4〜6.0%。**5%の線をまたいでいて、判定が定まらない**

  ② 転移      前半→後半の相関  40走以上 +0.003 ／ 60走以上 +0.019 ／ 80走以上 +0.111
              プラセボ95%上限   +0.201 ／ +0.216 ／ +0.281
              **どれも大きく内側。持ち越されない**

  → **父の残差は、市場の外の情報としては検出できない。**
     順位表（パイロ +0.045、サトノアラジン -0.046）は前半後半で入れ替わる。
     これは「今年たまたまそう出た」であって、父の性質ではない。

  ※「ルヴァンスレーヴは3着内38.9%なのに残差 -0.039＝走るが買われすぎ」という
    読みも同じ理由で成り立たない。次の期間まで持ち越されないため。

  南関で安定して測れるのは条件側であって馬側ではない、という
  `kensho_0816_matome.md` §D④ の結論が、血統でも繰り返された。

★条件で割ると即座に枯渇する（この道具の限界）:
  馬場状態で割ると比較できる父が13種、砂厚で割ると11種しか残らない。
  各セル40〜100走では符号が入れ替わる（ホッコータルマエが不良で＋、12cmで−）。
  1年ぶんでは【父×条件】は測れない。全体の傾きだけが読める。

使い方:
    python3 scripts/ana/chichi.py
    python3 scripts/ana/chichi.py --min 100 --shuffle 500
    python3 scripts/ana/chichi.py --split baba      # 馬場状態で割る（枯渇の確認用）
    python3 scripts/ana/chichi.py --split atsusa    # 砂厚で割る（同上）
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bt

SIREMAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "siremap.json")

# 砂厚（cm）。2022年6月に川崎が8.5→10cmになった以降の値。
DEPTH = {"船橋": 12, "大井": 10, "川崎": 10, "浦和": 10}


def collect(R, sire):
    """1走 = {父, 市場の勝率, 勝った/3着内, 場, 馬場} に落とす。"""
    rows = []
    for r in R:
        den = sum(1.0 / x["odds"] for x in r["rows"] if x["odds"] and x["odds"] > 0)
        if den <= 0:
            continue
        for x in r["rows"]:
            if not x["odds"] or x["odds"] <= 0:
                continue
            f = sire.get(x["name"])
            if not f:
                continue
            mp = (1.0 / x["odds"]) / den
            rows.append(dict(sire=f, mp=mp, win=float(x["chaku"] == 1), date=r["date"],
                             p3=float(x["chaku"] <= 3), res=float(x["chaku"] == 1) - mp,
                             place=r["place"], baba=r["baba"], depth=DEPTH.get(r["place"])))
    return rows


def spread(rows, mn):
    """父ごとの平均残差を出し、そのばらつき（母標準偏差）を返す。"""
    by = defaultdict(list)
    for q in rows:
        by[q["sire"]].append(q)
    keep = {k: v for k, v in by.items() if len(v) >= mn}
    if len(keep) < 3:
        return None, {}
    mean = {k: st.mean(q["res"] for q in v) for k, v in keep.items()}
    return st.pstdev(mean.values()), keep


def placebo(rows, mn, n, seed=0):
    """父の欄だけシャッフルして、同じ計算をやり直す。"""
    rnd = random.Random(seed)
    labs = [q["sire"] for q in rows]
    out = []
    for _ in range(n):
        rnd.shuffle(labs)
        for q, s in zip(rows, labs):
            q["_s"] = s
        by = defaultdict(list)
        for q in rows:
            by[q["_s"]].append(q["res"])
        v = [st.mean(w) for w in by.values() if len(w) >= mn]
        if len(v) >= 3:
            out.append(st.pstdev(v))
    return sorted(out)


def corr(A, B):
    ma, mb = st.mean(A), st.mean(B)
    sa, sb = st.pstdev(A), st.pstdev(B)
    if sa == 0 or sb == 0:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(A, B)) / len(A) / (sa * sb)


def transfer(rows, mn, n=200, seed=7):
    """前半で出た父のズレが後半にも出るか。プラセボは父の欄のシャッフル。

    ばらつき検定より厳しく、そしてこちらのほうが馬券に直結する。
    持ち越されないズレは、来週の父を見ても使えない。
    """
    rows = sorted(rows, key=lambda q: q["date"])
    half = len(rows) // 2

    def split(labs):
        a, b = defaultdict(list), defaultdict(list)
        for i, (q, s) in enumerate(zip(rows, labs)):
            (a if i < half else b)[s].append(q["res"])
        k = [x for x in a if len(a[x]) >= mn and len(b.get(x, [])) >= mn]
        if len(k) < 10:
            return None, 0
        return corr([st.mean(a[x]) for x in k], [st.mean(b[x]) for x in k]), len(k)

    real, nk = split([q["sire"] for q in rows])
    rnd = random.Random(seed)
    labs = [q["sire"] for q in rows]
    ps = []
    for _ in range(n):
        rnd.shuffle(labs)
        c, _ = split(labs)
        if c is not None:
            ps.append(c)
    ps.sort()
    return real, nk, ps


def main():
    ap = argparse.ArgumentParser(description="父は市場の外に情報を持っているか")
    ap.add_argument("--from", dest="dfrom", default="2026-01-01")
    ap.add_argument("--to", dest="dto", default="2026-12-31")
    ap.add_argument("--min", type=int, default=150, help="この走数以上の父だけを見る")
    ap.add_argument("--shuffle", type=int, default=300)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--split", choices=["baba", "atsusa"], help="条件で割る（枯渇の確認）")
    a = ap.parse_args()

    sire = json.load(open(SIREMAP))
    R = bt.load(a.dfrom, a.dto)
    rows = collect(R, sire)
    allrun = sum(len(r["rows"]) for r in R)
    print(f"■ {a.dfrom}〜{a.dto}  {len(R):,}レース／{allrun:,}走")
    print(f"   父が判明 {len(rows):,}走（{len(rows)/allrun*100:.0f}%）"
          f"／{len(set(q['sire'] for q in rows)):,}種\n")

    sd, keep = spread(rows, a.min)
    if sd is None:
        print("該当する父が少なすぎる")
        return
    ps = placebo(rows, a.min, a.shuffle)
    hi = ps[int(len(ps) * 0.95)]
    over = sum(1 for x in ps if x >= sd) / len(ps) * 100
    print(f"■ ① ばらつき検定（{a.min}走以上の {len(keep)} 種）")
    print(f"   実測          {sd:.5f}")
    print(f"   プラセボ中央   {st.median(ps):.5f}")
    print(f"   プラセボ95%上限 {hi:.5f}")
    print(f"   超過率 {over:.1f}%   ← 5%の線に近いと、乱数の種で判定が入れ替わる")

    print(f"\n■ ② 転移検定（前半で出たズレが後半にも出るか）★判定はこちら")
    for mn in (40, 60, 80):
        real, nk, tp = transfer(rows, mn)
        if real is None:
            continue
        thi = tp[int(len(tp) * 0.95)]
        print(f"   {mn:>3}走以上 {nk:>3}種   相関 {real:+.3f}   "
              f"プラセボ95%上限 {thi:+.3f}   "
              f"{'持ち越される' if real > thi else '持ち越されない'}")
    print("   持ち越されないなら、下の順位表は【今年たまたまそう出た】であって父の性質ではない\n")

    mean = {k: st.mean(q["res"] for q in v) for k, v in keep.items()}
    order = sorted(mean.items(), key=lambda z: -z[1])
    print(f"   {'父':<18}{'走':>5}{'残差':>9}{'3着内':>7}{'平均市場勝率':>13}")
    for k, v in order[:a.top] + [("…", None)] + order[-a.top:]:
        if v is None:
            print(f"   {'…':<18}")
            continue
        w = keep[k]
        print(f"   {k:<18}{len(w):>5}{v:>+9.4f}{st.mean(q['p3'] for q in w)*100:>6.1f}%"
              f"{st.mean(q['mp'] for q in w)*100:>12.1f}%")
    print("\n   ＋＝市場が過小評価／−＝過大評価。ただし②で持ち越されないと出た以上、")
    print("   この並びを来週の予想に持ち込んではいけない。今年の結果の言い換えでしかない")

    if a.split:
        key = (lambda q: q["baba"]) if a.split == "baba" else (lambda q: q["depth"])
        cell = defaultdict(lambda: defaultdict(list))
        for q in rows:
            cell[key(q)][q["sire"]].append(q["res"])
        cs = sorted(cell, key=lambda c: -sum(len(w) for w in cell[c].values()))
        mn = max(30, a.min // 3)
        common = None
        for c in cs:
            s = {k for k, w in cell[c].items() if len(w) >= mn}
            common = s if common is None else (common & s)
        print(f"\n■ {a.split} で割ったとき（各セル {mn}走以上）")
        print(f"   全ての区分で母数の足りる父は {len(common or [])} 種しか残らない")
        if not common:
            return
        hdr = "".join(f"{str(c):>12}" for c in cs)
        print(f"   {'父':<18}{hdr}")
        for k in sorted(common, key=lambda k: -st.mean(cell[cs[0]][k])):
            line = "".join(f"{st.mean(cell[c][k]):>+8.3f}({len(cell[c][k]):>2})" for c in cs)
            print(f"   {k:<18}{line}")
        print("\n   ※各セルが数十走では符号が偶然で入れ替わる。1年ぶんでは父×条件は測れない")


if __name__ == "__main__":
    main()
