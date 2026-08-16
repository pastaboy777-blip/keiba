#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下げない馬を探す ── 道中で位置を落とさない馬を順に並べる。

考え方（ユーザーの観察を数値化したもの）:
  力まずに追走できている馬は、道中で位置を下げない。
  苦しい馬は3〜4角で後退する。
  「下げなさ」は結果（時計・上がり）ではなく【追走のコスト】なので、
  展開に汚染されにくく、馬の性質として残る。

実測（南関20,314走）:
  履歴を前半・後半に割った相関
      下げなさ（ドリフト残差） +0.421   ← 馬の個体差として検出できた唯一の指標
      4角位置                +0.622
      上がりの濃さ            +0.486
      【プラセボ】シャッフル      +0.026
  ※ペース適性 c=+0.087、走行位置の癖 r=+0.129 はどちらも検出できなかった。

  過去3走の「下げなさ」で三分割した次走成績
      下げない側 3着内 32.8% ／ 中間 23.2% ／ 下げる側 14.1%   （2.3倍）

★使い方の注意（7/1〜8/16の南関433レースで確認）:
  ① 二値（一度も下げていない）にすると効かない。該当が2割で差が3ポイントしかない。
     連続値で【下位を切る】ほうが強い（3つ以上下げた走がある＝3着内21.5%・単回収52%）。
  ② 後方の馬には使えない。「下げない×出だしは後方」は3着内20.3%で全体を下回る。
     下げなくても届かないため。前めにいる馬に限って価値が出る。
  ③ 単勝回収は伸びない（74%）。的中率で効く指標であって、配当はつかない。
     使うなら軸選びと消し。

ドリフトの作り方:
      ドリフト = (最終コーナーの順位 − 最初のコーナーの順位) / (頭数-1)
                ＋なら下げた／−なら上げた
  後方から出れば上げやすいので、出だしの位置に回帰して残差を取る。

使い方:
  python3 scripts/ana/sagenai.py                       # 上位を並べる
  python3 scripts/ana/sagenai.py --since 2026-07-01    # 直近に走っている馬だけ
  python3 scripts/ana/sagenai.py --horse コスモトロイメル
"""
from __future__ import annotations

import argparse
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bt
import agari_sotai as AS

MIN_RUNS = 5


def collect(R, A):
    H = defaultdict(list)
    for r in sorted(R, key=lambda z: z["date"]):
        v, m, tk = AS.koi(r, A)
        if v is None:
            continue
        for z in v:
            h = z["h"]
            p = [int(x) for x in re.findall(r"\d+", h.get("pas") or "")]
            if len(p) < 2 or r["n"] < 6:
                continue
            H[h["name"]].append(dict(
                d=r["date"], place=r["place"], dist=r["dist"], n=r["n"],
                drift=(p[-1] - p[0]) / (r["n"] - 1),
                worst=max(p[i] - p[i - 1] for i in range(1, len(p))),
                start=(p[0] - 1) / (r["n"] - 1), rel=z["rel"], koi=z["koi"],
                ch=h["chaku"], nin=h["ninki"] or 99, pas=h["pas"], jk=h["jockey"]))
    return H


def main():
    ap = argparse.ArgumentParser(description="下げない馬を探す")
    ap.add_argument("--since", default="2026-07-01", help="この日以降に走っている馬に絞る")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--horse")
    ap.add_argument("--forward", action="store_true", help="出だしが前め(0.5以下)の馬だけ")
    a = ap.parse_args()

    R = bt.load("2026-01-01", "2026-12-31")
    A = AS.calib(R)
    H = collect(R, A)
    al = [q for w in H.values() for q in w]

    # 出だしの位置 → ドリフト を回帰して残差にする
    X = [q["start"] for q in al]; Y = [q["drift"] for q in al]
    mx, my = st.mean(X), st.mean(Y)
    sxx = sum((x - mx) ** 2 for x in X)
    b = sum((x - mx) * (y - my) for x, y in zip(X, Y)) / sxx
    for q in al:
        q["res"] = q["drift"] - (b * (q["start"] - mx) + my)
    print(f"■ 南関 {len(al):,}走 / {len(H):,}頭   出だし→ドリフトの傾き {b:+.3f}")
    print(f"   下げなさ = 残差の符号を反転（大きいほど下げない）\n")

    if a.horse:
        w = sorted(H.get(a.horse, []), key=lambda z: z["d"])
        if not w:
            print("該当なし"); return
        print(f"■ {a.horse}  {len(w)}走   下げなさ {-st.mean(q['res'] for q in w):+.3f}")
        for q in w:
            print(f"   {q['d']} {q['place']}{q['dist']}m {q['n']:>2}頭 {q['ch']:>2}着 "
                  f"{q['nin']:>2}人 {q['jk']:<9}通過{q['pas']:<10} 最大の下げ{q['worst']:+d} "
                  f"残差{q['res']:+.3f}")
        return

    rows = []
    for nm, w in H.items():
        if len(w) < MIN_RUNS or max(q["d"] for q in w) < a.since:
            continue
        sg = -st.mean(q["res"] for q in w)
        stt = st.mean(q["start"] for q in w)
        if a.forward and stt > 0.5:
            continue
        rows.append((sg, nm, len(w), stt, st.mean(q["rel"] for q in w),
                     st.mean(q["koi"] for q in w),
                     sum(1 for q in w if q["ch"] <= 3) / len(w) * 100,
                     max(q["d"] for q in w), max(q["worst"] for q in w)))
    rows.sort(reverse=True)
    print(f"■ 下げない順（{MIN_RUNS}走以上・{a.since}以降に出走した {len(rows):,}頭）")
    print(f"   {'馬名':<16}{'走':>3}{'下げなさ':>9}{'出だし':>7}{'4角':>6}{'濃さ':>7}"
          f"{'3着内':>7}{'最大の下げ':>7}  直近")
    for sg, nm, n, stt, rel, koi, p3, last, w in rows[:a.top]:
        fw = "前め" if stt <= 0.45 else ("中団" if stt <= 0.6 else "後方")
        print(f"   {nm:<16}{n:>3}{sg:>+9.3f}{stt:>7.2f}({fw}){rel:>6.2f}{koi:>+7.2f}"
              f"{p3:>6.0f}%{w:>7d}  {last}")
    print("\n   ※ 出だしが【後方】の馬は、下げなくても届かない（3着内20.3%で全体以下）。")
    print("     価値が出るのは前め〜中団の馬。--forward で絞れる。")


if __name__ == "__main__":
    main()
