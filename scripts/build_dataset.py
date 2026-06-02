"""収集済みデータ(JSONL)から学習→検証まで一気通貫で回す。

    python3 scripts/build_dataset.py --data data/results.jsonl

JSONL の形式は core/dataset.py を参照。collect_data.py の出力を入力にできる。
データがまだ無い場合は --demo で合成データを JSONL に書き出して試せる。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.core import dataset as ds
from nankeiba.core import synth
from nankeiba.core.backtest import run_backtest
from nankeiba.core.learn import train_scorer
from nankeiba.core.features import ScoreWeights


def run(races, *, bet_type: str, train_frac: float = 0.65) -> None:
    races = sorted(races, key=lambda r: r.date)
    cut = int(len(races) * train_frac)
    train, test = races[:cut], races[cut:]
    print(f"総レース {len(races)}  学習 {len(train)} / 検証 {len(test)}")

    # 関係者成績は学習区間だけから推定(リーク防止)
    jockeys, trainers = ds.derive_conn_stats(train)

    scorer = train_scorer(
        train, jockeys=jockeys, trainers=trainers,
        epochs=60, lr=0.2, l2=1e-3, top_k=3, min_history=4,
    )
    print("\n学習された特徴量の重要度:")
    for name, w in scorer.importances():
        print(f"  {name:14s} {w:+.3f}")

    label = "三連複" if bet_type == "trio" else "三連単"
    print(f"\n検証データでの回収率({label}):")
    res_def = run_backtest(test, jockeys=jockeys, trainers=trainers, weights=ScoreWeights(),
                           bet_type=bet_type, ev_threshold=1.3, max_bets=6, min_history=4)
    res_lrn = run_backtest(test, jockeys=jockeys, trainers=trainers, score_fn=scorer,
                           bet_type=bet_type, ev_threshold=1.3, max_bets=6, min_history=4)
    print("  [既定重み] " + res_def.summary())
    print("  [学習重み] " + res_lrn.summary())


def main() -> None:
    ap = argparse.ArgumentParser(description="収集データから学習→検証")
    ap.add_argument("--data", help="JSONL ファイル(core/dataset.py 形式)")
    ap.add_argument("--bet-type", choices=["trio", "trifecta"], default="trio")
    ap.add_argument("--demo", action="store_true", help="合成データで試す(--data 不要)")
    args = ap.parse_args()

    if args.demo or not args.data:
        print("=== demo モード: 合成データを生成して実行 ===")
        races, _, _ = synth.generate_season(n_races=1200, seed=7)
    else:
        print(f"=== {args.data} を読み込み ===")
        races = ds.load_races(args.data)

    run(races, bet_type=args.bet_type)


if __name__ == "__main__":
    main()
