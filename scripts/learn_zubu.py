"""ズブ穴ランキングの重みをロジスティック回帰で学習する(標準ライブラリのみ)。

improve_zubu.py の手設定重み(A)を、データから最適化した係数で置き換えられるか検証する。
特徴量は「走らせる」観点で安定して効くものに限定:
  jockey(騎手の質) / ability(地力) / senkou(先行) / agari(上がり,負) /
  upgrade(乗り替わり強化) / tatakii_jq(叩き2-3×上位騎手)
人気薄(exp_pop>=6)のみ。学習期間で標準化+学習、検証期間で本線3着内率を比較。

実行: python3 scripts/learn_zubu.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import backtest_wet as bw
import predict_nankan as pn
import improve_zubu as iz

FEATS = ["jockey", "ability", "senkou", "agari", "upgrade", "tatakii_jq"]
CUTOFF = iz.CUTOFF


def vec(row, stats):
    out = []
    for k in FEATS:
        v = row[3].get(k)
        m, sd = stats[k]
        out.append(0.0 if v is None else (v - m) / sd)   # 欠損は平均(=0)で補完
    return out


def train_logistic(X, y, *, epochs=300, lr=0.3, l2=1e-3):
    n, d = len(X), len(X[0])
    w = [0.0] * d
    b = 0.0
    for _ in range(epochs):
        gw = [0.0] * d
        gb = 0.0
        for xi, yi in zip(X, y):
            z = b + sum(w[j] * xi[j] for j in range(d))
            p = 1.0 / (1.0 + math.exp(-z))
            e = p - yi
            for j in range(d):
                gw[j] += e * xi[j]
            gb += e
        for j in range(d):
            w[j] = w[j] - lr * (gw[j] / n + l2 * w[j])
        b -= lr * gb / n
    return w, b


def eval_top1(test_rows, scorer):
    by = {}
    for r in test_rows:
        by.setdefault(r[0], []).append(r)
    nh = hb = npick = nb = 0
    for _rid, rs in by.items():
        rs = sorted(rs, key=lambda r: -scorer(r))
        nh += 1
        hb += rs[0][4]
        for r in rs[:5]:
            npick += 1
            nb += r[4]
    return 100 * hb / nh, nh, 100 * nb / npick


def main() -> None:
    races = bw.load_races()
    jt = pn.jockey_top3_from_samples(bw.FILES)
    rows = iz.build_rows(races, jt)
    train = [r for r in rows if r[1] < CUTOFF]
    test = [r for r in rows if r[1] >= CUTOFF]
    stats = iz.standardize(train, FEATS)

    X = [vec(r, stats) for r in train]
    y = [r[4] for r in train]
    w, b = train_logistic(X, y)

    print(f"人気薄 学習{len(train)}・検証{len(test)} (cutoff {CUTOFF})\n")
    print("学習した係数(標準化後・大きいほど3着内に効く):")
    for k, wj in sorted(zip(FEATS, w), key=lambda kv: -kv[1]):
        print(f"  {k:<12}{wj:+.3f}")

    learned = lambda r: b + sum(w[j] * vec(r, stats)[j] for j in range(len(FEATS)))
    handA = lambda r: iz.score(r, stats, iz.WEIGHTS_A)
    cur = lambda r: (r[3]["cur"] if r[3]["cur"] is not None else -9)

    print(f"\n{'スコア':<22}{'本線3着内':>10}{'上位5頭':>10}")
    for name, fn in [("現行 穴度", cur), ("手設定A", handA), ("学習(logistic)", learned)]:
        h, nh, top5 = eval_top1(test, fn)
        print(f"{name:<22}{h:>9.1f}%{top5:>9.1f}%   (n={nh})")
    print("\n※ 検証期間のみで評価(標準化・学習は学習期間のみ=リーク無し)。")


if __name__ == "__main__":
    main()
