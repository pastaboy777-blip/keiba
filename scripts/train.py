"""データから重みを学習し、未来レースで検証するデモ。

時系列分割(前半=学習 / 後半=検証)で:
  1. 学習データから Plackett-Luce 尤度最大化で重みを学習
  2. 学習した重みの重要度を表示
  3. 検証データで「既定重み」と「学習重み」の回収率を比較

実行:
    python3 scripts/train.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.core import synth
from nankeiba.core.backtest import run_backtest
from nankeiba.core.learn import train_scorer
from nankeiba.core.features import ScoreWeights


def main() -> None:
    print("=== 重み学習デモ(時系列分割)===\n")
    races, jockeys, trainers = synth.generate_season(n_races=1200, seed=7)
    races.sort(key=lambda r: r.date)
    cut = int(len(races) * 0.65)
    train_races, test_races = races[:cut], races[cut:]
    print(f"学習: {len(train_races)} レース / 検証: {len(test_races)} レース\n")

    # --- 学習 ---
    scorer = train_scorer(
        train_races, jockeys=jockeys, trainers=trainers,
        epochs=60, lr=0.2, l2=1e-3, top_k=3, min_history=4, seed=0,
    )

    print("学習された特徴量の重要度(標準化済み係数の絶対値順):")
    for name, w in scorer.importances():
        bar = "#" * int(abs(w) * 20)
        print(f"  {name:14s} {w:+.3f}  {bar}")

    # --- 検証(三連複)---
    print("\n検証データでの回収率(三連複):")
    res_default = run_backtest(
        test_races, jockeys=jockeys, trainers=trainers, weights=ScoreWeights(),
        bet_type="trio", ev_threshold=1.3, max_bets=6, min_history=4,
    )
    res_learned = run_backtest(
        test_races, jockeys=jockeys, trainers=trainers, score_fn=scorer,
        bet_type="trio", ev_threshold=1.3, max_bets=6, min_history=4,
    )
    print("  [既定重み  ] " + res_default.summary())
    print("  [学習重み  ] " + res_learned.summary())

    print(
        "\n注: 合成データでの検証。学習が常に勝つわけではなく、"
        "実データでのチューニング(lr/l2/top_k/ev_threshold)が必要。"
    )


if __name__ == "__main__":
    main()
