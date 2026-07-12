"""LightGBM(lambdarank)による重み学習(任意・ローカル実行用)。

純Python版(learn.py)と同じ特徴量・同じ学習データ作成を使い、
線形モデルの代わりに勾配ブースティング決定木で「強さスコア」を学習する。
非線形な相互作用(例: 短間隔×叩き2走目だけ特に走る)を捉えられる。

要 lightgbm / numpy: pip install lightgbm numpy
本リポジトリの実行環境はネット遮断・未導入のため未検証。インターフェースは
learn.LearnedScorer と互換(backtest の score_fn にそのまま渡せる)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .features import FEATURE_NAMES, RaceContext, ConnStats, horse_features
from .backtest import Race
from .learn import build_training_rows


@dataclass
class LgbmScorer:
    model: object  # lightgbm.Booster
    jockeys: ConnStats | None = None
    trainers: ConnStats | None = None
    interval_prior: dict | None = None
    tatakii_table: dict | None = None

    def __call__(self, past: list, ctx: RaceContext) -> float:
        feat = horse_features(
            past, ctx, jockeys=self.jockeys, trainers=self.trainers,
            interval_prior=self.interval_prior, tatakii_table=self.tatakii_table,
        )
        x = [[feat[f] for f in FEATURE_NAMES]]
        return float(self.model.predict(x)[0])

    def importances(self) -> list[tuple[str, float]]:
        imp = self.model.feature_importance(importance_type="gain")
        return sorted(zip(FEATURE_NAMES, imp), key=lambda kv: kv[1], reverse=True)


def train_lgbm_scorer(
    races: Sequence[Race],
    *,
    jockeys: ConnStats | None = None,
    trainers: ConnStats | None = None,
    interval_prior: dict | None = None,
    tatakii_table: dict | None = None,
    min_history: int = 4,
    num_boost_round: int = 200,
    params: dict | None = None,
) -> LgbmScorer:
    """lambdarank で強さスコアを学習する。

    ラベルは「着順を反転した relevance(1着が最大)」、group はレース毎の頭数。
    """
    import lightgbm as lgb  # 遅延 import(未導入環境でも learn.py は動く)

    samples = build_training_rows(
        races, jockeys=jockeys, trainers=trainers,
        interval_prior=interval_prior, tatakii_table=tatakii_table,
    )

    X: list[list[float]] = []
    y: list[int] = []
    group: list[int] = []
    for race in samples:
        rows = [r for r in race if r.n_hist >= min_history]
        if len(rows) < 5:
            continue
        fs = len(rows)
        for r in rows:
            X.append([r.feat[f] for f in FEATURE_NAMES])
            # relevance: 上位ほど大(lambdarank は大きいほど良い)
            y.append(max(0, fs - r.pos))
        group.append(fs)

    if not X:
        raise ValueError("学習データが空です(履歴不足)。レース数や min_history を見直してください。")

    dataset = lgb.Dataset(X, label=y, group=group, feature_name=list(FEATURE_NAMES))
    default_params = {
        "objective": "lambdarank",
        "metric": "ndcg",
        "ndcg_eval_at": [3],
        "learning_rate": 0.05,
        "num_leaves": 15,
        "min_data_in_leaf": 30,
        "verbose": -1,
    }
    if params:
        default_params.update(params)
    booster = lgb.train(default_params, dataset, num_boost_round=num_boost_round)
    return LgbmScorer(
        model=booster, jockeys=jockeys, trainers=trainers,
        interval_prior=interval_prior, tatakii_table=tatakii_table,
    )
