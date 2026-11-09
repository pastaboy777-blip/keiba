#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""市場の誤差だけを的にするモデル（Benter方式）。

なぜこの形か:
  指数を作って市場と比べる、という順番だと、市場が既に知っていることを
  もう一度独立に推定することになる。だから順番を逆にする。

      logit(勝つ) = log( 市場の確率 / (1-市場の確率) )  +  β・特徴量
                     ↑ オフセット（固定・推定しない）

  こうすると市場の言い換えでしかない特徴量は自動的に係数ゼロになり、
  残るのは【市場が見落としている分】だけになる。
  「この指数は市場に勝てるか」を、測る前に構造で保証できる。

★主観の重みを置かない。
  8/18川崎で、手で決めた重み（下げなさ×3.0 − 濃さ×1.0 …）でカードを組んだところ
  ◎が12鞍0勝・回収0%、▲が4勝・回収207%と順序が逆転した。
  重みはデータから推定する。

特徴量は【転移することを実測した量】だけを入れる:
      下げなさ（ドリフト残差）  前走→今走の自己相関 +0.421
      上がりの濃さ            +0.290
      4角位置                +0.452
      馬体重の直近トレンド      3着内 27.9%(+8kg以上) vs 22.6%(横ばい)
      他馬の前づけ密度         今走の位置への係数 +0.205
      前走の③（前が楽だったか）
  入れないもの:
      上がりのトレンド … 自己相関 -0.014。持ち越されない
      ペース適性      … c=+0.087
      走行位置の癖     … r=+0.129

検証:
  期間を前後に割り、前半で推定して後半で当てる。同じ期間で測らない。

使い方:
  python3 scripts/ana/market_model.py
  python3 scripts/ana/market_model.py --split 2026-06-15 --target p3
"""
from __future__ import annotations

import argparse
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bt
import agari_sotai as AS

FEATS = ["下げなさ", "上がりの濃さ", "4角位置", "馬体重トレンド", "前づけ密度", "前走の③"]


def build(R, A):
    """2パス。1回目で位置→ドリフトの較正、2回目で時系列に沿って特徴量を作る。"""
    # --- パス1：較正定数 ---
    S, D = [], []
    per = {}
    for r in R:
        v, m, tk = AS.koi(r, A)
        if v is None:
            continue
        for z in v:
            p = [int(x) for x in re.findall(r"\d+", z["h"].get("pas") or "")]
            if len(p) < 2 or r["n"] < 6:
                continue
            s = (p[0] - 1) / (r["n"] - 1)
            d = (p[-1] - p[0]) / (r["n"] - 1)
            S.append(s); D.append(d)
            per[(r["date"], r["place"], r["rn"], z["h"]["name"])] = (s, d, z, tk)
    mx, my = st.mean(S), st.mean(D)
    b = sum((x - mx) * (y - my) for x, y in zip(S, D)) / sum((x - mx) ** 2 for x in S)

    # --- パス2：時系列に沿って ---
    H = defaultdict(list)
    rows = []
    denom = {}
    for r in sorted(R, key=lambda z: z["date"]):
        v, m, tk = AS.koi(r, A)
        if v is None:
            continue
        ent = []
        for z in v:
            h = z["h"]
            key = (r["date"], r["place"], r["rn"], h["name"])
            if key not in per:
                continue
            w = H[h["name"]]
            pm = st.mean(q["rel"] for q in w[-3:]) if w else None
            ent.append((z, h, key, w, pm))
        fwd = sum(1 for z, h, k, w, pm in ent if pm is not None and pm <= 0.30)
        # 正規化の分母は【全出走馬】から作る（測れない馬も含める）
        denom[(r["date"], r["place"], r["rn"])] = sum(
            1.0 / x["odds"] for x in r["rows"] if x["odds"] and x["odds"] > 0)
        for z, h, key, w, pm in ent:
            s, d, _, _ = per[key]
            if len(w) >= 3 and h["odds"] and h["odds"] > 0:
                r3 = w[-3:]
                dw = (r3[-1]["w"] - r3[0]["w"]) if all(q["w"] for q in r3) else 0
                own = 1 if (pm is not None and pm <= 0.30) else 0
                rows.append(dict(
                    date=r["date"], race=(r["date"], r["place"], r["rn"]),
                    x=[st.mean(q["sage"] for q in w), st.mean(q["koi"] for q in r3),
                       pm, dw / 10.0, (fwd - own) / max(1, len(ent) - 1), r3[-1]["tk"]],
                    odds=h["odds"], win=float(h["chaku"] == 1), p3=float(h["chaku"] <= 3),
                    nin=h["ninki"] or 99))
            H[h["name"]].append(dict(rel=z["rel"], koi=z["koi"], tk=tk, w=h["weight"],
                                     sage=-(d - (b * (s - mx) + my))))
    return rows, denom


def market_p(rows, denom):
    """単勝オッズをレース内で正規化して市場の勝率にする（控除率を落とす）。

    ★正規化は【そのレースの全出走馬】で行う。
      測れる馬だけで割ると確率が水増しされ、定数項がそれを吸って較正が壊れる
      （実測：定数 -4.12、検証期間の対数尤度が市場より悪化した）。
    """
    for q in rows:
        q["mp"] = (1.0 / q["odds"]) / denom[q["race"]]


def fit(X, y, off, iters=30):
    """オフセット付きロジスティック（IRLS）。オフセットは推定しない。"""
    n, k = X.shape
    Xa = np.hstack([X, np.ones((n, 1))])
    beta = np.zeros(k + 1)
    for _ in range(iters):
        eta = off + Xa @ beta
        p = 1.0 / (1.0 + np.exp(-np.clip(eta, -30, 30)))
        W = np.clip(p * (1 - p), 1e-8, None)
        g = Xa.T @ (y - p)
        Hm = Xa.T @ (Xa * W[:, None]) + np.eye(k + 1) * 1e-6
        step = np.linalg.solve(Hm, g)
        beta += step
        if np.max(np.abs(step)) < 1e-8:
            break
    return beta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="2026-06-15")
    ap.add_argument("--target", default="win", choices=["win", "p3"])
    a = ap.parse_args()
    R = bt.load("2026-01-01", "2026-12-31")
    A = AS.calib(R)
    rows, denom = build(R, A)
    market_p(rows, denom)
    tr = [q for q in rows if q["date"] < a.split]
    te = [q for q in rows if q["date"] >= a.split]
    print(f"■ {len(rows):,}走   学習 {len(tr):,}（〜{a.split}）／検証 {len(te):,}\n")

    Xtr = np.array([q["x"] for q in tr], float)
    mu, sd = Xtr.mean(0), Xtr.std(0)
    sd[sd == 0] = 1
    ytr = np.array([q[a.target] for q in tr], float)
    otr = np.log(np.clip([q["mp"] for q in tr], 1e-6, 1 - 1e-6) /
                 (1 - np.clip([q["mp"] for q in tr], 1e-6, 1 - 1e-6)))
    beta = fit((Xtr - mu) / sd, ytr, otr)

    print("■ 推定された係数（市場のオッズをオフセットに固定したうえでの上積み）")
    print("   ゼロに近い＝市場の言い換え。ゼロから離れる＝市場が見落としている分")
    for nm, b_ in zip(FEATS, beta[:-1]):
        bar = "■" * int(min(abs(b_) * 40, 30))
        print(f"   {nm:<14}{b_:>+8.4f}  {bar}")
    print(f"   {'（定数）':<14}{beta[-1]:>+8.4f}")

    # --- 検証 ---
    Xte = (np.array([q["x"] for q in te], float) - mu) / sd
    yte = np.array([q[a.target] for q in te], float)
    mpte = np.clip([q["mp"] for q in te], 1e-6, 1 - 1e-6)
    ote = np.log(mpte / (1 - mpte))
    p_mkt = 1.0 / (1.0 + np.exp(-ote))
    p_mod = 1.0 / (1.0 + np.exp(-np.clip(ote + np.hstack([Xte, np.ones((len(te), 1))]) @ beta, -30, 30)))
    ll = lambda p: float(np.mean(yte * np.log(np.clip(p, 1e-9, 1)) + (1 - yte) * np.log(np.clip(1 - p, 1e-9, 1))))
    print(f"\n■ 検証期間の対数尤度（1走あたり・大きいほど良い）")
    print(f"   市場だけ        {ll(p_mkt):.5f}")
    print(f"   市場＋モデル     {ll(p_mod):.5f}   差 {ll(p_mod)-ll(p_mkt):+.5f}")
    print("   差がプラスなら、市場に無い情報を足せている")

    if a.target == "win":
        print("\n■ 期待値で買ったとき（モデルの確率 ÷ 市場の確率 が閾値以上の馬を単勝）")
        ratio = p_mod / p_mkt
        for th in (1.05, 1.10, 1.20, 1.35):
            m = ratio >= th
            n = int(m.sum())
            if n < 30:
                print(f"   閾値{th:.2f}  n{n:>5}  該当が少ない")
                continue
            pay = sum(te[i]["odds"] * 100 for i in range(len(te)) if m[i] and te[i]["win"])
            hit = sum(1 for i in range(len(te)) if m[i] and te[i]["win"])
            print(f"   閾値{th:.2f}  n{n:>5}  的中{hit:>4}({hit/n*100:>5.1f}%)  単回収 {pay/n/100*100:>6.1f}%")
        n = len(te)
        pay = sum(q["odds"] * 100 for q in te if q["win"])
        print(f"   【対照】全部買う n{n:>5}  的中{int(yte.sum()):>4}({yte.mean()*100:>5.1f}%)  "
              f"単回収 {pay/n/100*100:>6.1f}%")


if __name__ == "__main__":
    main()
