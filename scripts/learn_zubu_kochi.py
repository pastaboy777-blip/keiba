"""高知ファイナル専用にズブ穴v2の重みを再学習する。

高知の各開催の最終R(ファイナル)だけを母集団に、logistic回帰で
「人気薄(exp_pop>=6)が3着内に来る」係数を学習。南関の現行重みと比較する。
高知ファイナルは差し天国(後方41%勝ち)なので、senkouの符号/大きさが
南関と変わるはず、という仮説の検証。

実行: python3 scripts/learn_zubu_kochi.py
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import predict_nankan as pn
import improve_zubu as iz
from learn_zubu import train_logistic, vec, eval_top1

FEATS = ["jockey", "ability", "senkou", "agari"]  # v2コア4種で南関と直接比較
KOCHI_GLOB = "data/samples/kochi_20*.jsonl"
SPLIT = "2026-04-01"  # これ以降を検証に


def load_finals():
    byday = {}
    for f in sorted(glob.glob(KOCHI_GLOB)):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            byday.setdefault(r["date"], []).append(r)
    finals = []
    for _d, rs in byday.items():
        finals.append(sorted(rs, key=lambda x: int(x["race_id"][-2:]))[-1])
    return finals


def vec4(row, stats):
    out = []
    for k in FEATS:
        v = row[3].get(k)
        m, sd = stats[k]
        out.append(0.0 if v is None else (v - m) / sd)
    return out


def main():
    finals = load_finals()
    jt = pn.jockey_top3_from_samples(sorted(glob.glob(KOCHI_GLOB)))
    rows = iz.build_rows(finals, jt)
    train = [r for r in rows if r[1] < SPLIT]
    test = [r for r in rows if r[1] >= SPLIT]
    stats = iz.standardize(train, FEATS)

    X = [vec4(r, stats) for r in train]
    y = [r[4] for r in train]
    w, b = train_logistic(X, y)

    print(f"■ 高知ファイナル {len(finals)}レース / 人気薄行 学習{len(train)}・検証{len(test)}"
          f" (split {SPLIT})\n")
    print("学習した係数(標準化後・大きいほど3着内に効く):")
    learned_w = dict(zip(FEATS, w))
    for k, wj in sorted(learned_w.items(), key=lambda kv: -kv[1]):
        arrow = ""
        cur = pn.ZUBU_V2_WEIGHTS.get(k)
        if cur is not None:
            arrow = f"   (南関: {cur:+.2f})"
        print(f"  {k:<9}{wj:+.3f}{arrow}")

    # 評価: 学習重み vs 南関現行 vs 手設定A (検証期間のみ)
    def scorer_learned(r):
        return b + sum(w[j] * vec4(r, stats)[j] for j in range(len(FEATS)))

    def scorer_weights(weights):
        return lambda r: sum(
            weights.get(k, 0.0) * ((r[3][k] - stats[k][0]) / stats[k][1])
            for k in FEATS if r[3].get(k) is not None)

    print(f"\n{'スコア':<20}{'本線3着内':>10}{'上位5頭':>10}")
    for name, fn in [
        ("南関の現行v2重み", scorer_weights(pn.ZUBU_V2_WEIGHTS)),
        ("学習(高知ファイナル)", scorer_learned),
    ]:
        h, nh, top5 = eval_top1(test, fn)
        print(f"{name:<20}{h:>9.1f}%{top5:>9.1f}%   (n={nh})")
    print("\n※ 学習・標準化は学習期間のみ=リーク無し。検証は2026-04以降のファイナル。")

    # 正規化した重み(和で割って解釈用)
    tot = sum(abs(v) for v in learned_w.values()) or 1
    print("\n解釈用(絶対値正規化):", {k: round(v / tot, 2) for k, v in learned_w.items()})


if __name__ == "__main__":
    main()
