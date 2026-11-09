"""強さスコアのモデル比較(ヒューリスティック vs 線形学習 vs LightGBM)。

時系列分割(前半=学習 / 後半=検証)で、同じ特徴量・同じ確率モデル
(Plackett-Luce)・同じ期待値ロジックのまま、**強さスコアの出し方だけ**を
差し替えて回収率(ROI)を比較する。

比較するモデル:
  1. 既定ヒューリスティック … 手設定の重み・手設定プライア
  2. 線形学習(PL 尤度最大化)… 学習重み + データ学習プライア + 上積みConnStats
  3. LightGBM(lambdarank) … 非線形。要 lightgbm/numpy(未導入なら自動スキップ)

学習側(重み・プライア・関係者成績)はすべて **学習区間のレースだけ** から
作るのでリークしない。

実行:
    python3 scripts/compare_models.py
    # LightGBM も比較したい場合(ローカル): pip install lightgbm numpy
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.core import synth
from nankeiba.core.backtest import run_backtest
from nankeiba.core.dataset import derive_conn_stats, derive_conn_uplift
from nankeiba.core.priors import learn_priors
from nankeiba.core.learn import train_scorer
from nankeiba.core.features import ScoreWeights


BET_TYPE = "trio"
COMMON = dict(bet_type=BET_TYPE, ev_threshold=1.3, max_bets=6, min_history=4)


def main() -> None:
    print("=== モデル比較: ヒューリスティック vs 線形学習 vs LightGBM ===\n")
    races, jockeys_true, trainers_true = synth.generate_season(n_races=1400, seed=7)
    races.sort(key=lambda r: r.date)
    cut = int(len(races) * 0.65)
    train_races, test_races = races[:cut], races[cut:]
    print(f"学習: {len(train_races)} レース / 検証: {len(test_races)} レース(三連複)\n")

    # --- 学習区間だけから: 関係者成績(好走率)・上積み・プライア ---
    jockeys, trainers = derive_conn_stats(train_races, metric="place", place_k=3)
    j_up, t_up = derive_conn_uplift(train_races)
    interval_prior, tatakii_table = learn_priors(train_races)
    print("学習した間隔プライア(短間隔ほど有利ならデータと整合):")
    for b in ["rento", "naka1", "normal", "aki", "kyumei"]:
        print(f"  {b:10s} {interval_prior.get(b, 0.0):+.4f}")
    print()

    # --- 1) 既定ヒューリスティック(手設定の重み・プライア)---
    res_heur = run_backtest(
        test_races, jockeys=jockeys, trainers=trainers, weights=ScoreWeights(), **COMMON
    )

    # --- 2) 線形学習(学習重み + 学習プライア + 上積みConnStats)---
    scorer = train_scorer(
        train_races, jockeys=j_up, trainers=t_up,
        interval_prior=interval_prior, tatakii_table=tatakii_table,
        epochs=60, lr=0.2, l2=1e-3, top_k=3, min_history=4, seed=0,
    )
    res_lin = run_backtest(test_races, score_fn=scorer, **COMMON)

    print("線形学習の特徴量重要度(標準化係数・絶対値順 上位6):")
    for name, w in scorer.importances()[:6]:
        print(f"  {name:14s} {w:+.3f}")
    print()

    # --- 3) LightGBM(あれば)---
    res_lgbm = None
    lgbm_note = ""
    try:
        from nankeiba.core.learn_lgbm import train_lgbm_scorer
        lgbm = train_lgbm_scorer(
            train_races, jockeys=j_up, trainers=t_up,
            interval_prior=interval_prior, tatakii_table=tatakii_table,
            min_history=4, num_boost_round=200,
        )
        res_lgbm = run_backtest(test_races, score_fn=lgbm, **COMMON)
    except ImportError:
        lgbm_note = "  (lightgbm/numpy 未導入のためスキップ: pip install lightgbm numpy)"
    except Exception as ex:  # データ不足など
        lgbm_note = f"  (スキップ: {ex})"

    # --- 比較表示 ---
    print("検証データでの回収率(三連複):")
    print("  [1 ヒューリスティック] " + res_heur.summary())
    print("  [2 線形学習(PL)     ] " + res_lin.summary())
    if res_lgbm is not None:
        print("  [3 LightGBM(rank)   ] " + res_lgbm.summary())
    else:
        print("  [3 LightGBM(rank)   ] --" + lgbm_note)

    print(
        "\n注: 合成データでの比較。どのモデルが勝つかは乱数・条件に依存する。"
        "実データで ev_threshold / lr / l2 / num_boost_round をチューニングし、"
        "必ず時系列分割で検証すること(的中率でなく回収率で判断)。"
    )


if __name__ == "__main__":
    main()
