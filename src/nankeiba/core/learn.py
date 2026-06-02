"""データから重みを学習する仕組み(Plackett-Luce 尤度最大化)。

各馬を特徴量ベクトル x で表し、線形スコア s = w·x を与える。
レースの着順は Plackett-Luce モデル
    P(着順) = Π_k  exp(s_{o_k}) / Σ_{j∈残り} exp(s_j)
に従うとし、観測された着順の対数尤度を最大化するように w を勾配上昇で学習する。
これは予測時に使う確率モデル(probability.py)と同一のモデルなので整合的。

特徴量は学習データ全体で標準化(平均0・分散1)してから学習し、
推論時も同じ統計量で標準化する(LearnedScorer)。

依存ライブラリなし(標準ライブラリのみ)。LightGBM 版は learn_lgbm.py。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from math import exp, log, sqrt
from typing import Sequence

from . import interval as iv
from .features import (
    FEATURE_NAMES, RaceContext, ConnStats, ScoreWeights, horse_features,
)
from .backtest import Race


# ---------------------------------------------------------------------------
# 学習データ作成(時系列・リーク無し)
# ---------------------------------------------------------------------------

@dataclass
class _Row:
    feat: dict[str, float]
    pos: int          # 着順(1 始まり)
    n_hist: int       # その時点での過去走数


def build_training_rows(
    races: Sequence[Race],
    *,
    jockeys: ConnStats | None = None,
    trainers: ConnStats | None = None,
    interval_prior: dict[str, float] | None = None,
) -> list[list[_Row]]:
    """時系列順に過去走だけから特徴量を作る。レースごとの行リストを返す。"""
    history: dict[int, list[iv.RunRecord]] = {}
    out: list[list[_Row]] = []

    for race in sorted(races, key=lambda r: r.date):
        pos_of = {hid: i + 1 for i, hid in enumerate(race.result_order)}
        rows: list[_Row] = []
        for e in race.entries:
            past = history.get(e.horse_id, [])
            ctx = RaceContext(
                date=race.date, place=race.place, distance=race.distance,
                field_size=race.field_size, jockey=e.jockey, trainer=e.trainer,
            )
            feat = horse_features(
                past, ctx, jockeys=jockeys, trainers=trainers, interval_prior=interval_prior
            )
            rows.append(_Row(feat=feat, pos=pos_of.get(e.horse_id, race.field_size),
                             n_hist=len(past)))
        out.append(rows)

        # 履歴更新(このレースの結果を追記)
        for e in race.entries:
            rec = iv.RunRecord(
                date=race.date, place=race.place, distance=race.distance,
                field_size=race.field_size, finish_pos=pos_of.get(e.horse_id, race.field_size),
                jockey=e.jockey, trainer=e.trainer,
            )
            history.setdefault(e.horse_id, []).insert(0, rec)

    return out


# ---------------------------------------------------------------------------
# 標準化
# ---------------------------------------------------------------------------

def compute_stats(
    samples: Sequence[Sequence[_Row]], *, min_history: int = 4
) -> tuple[dict[str, float], dict[str, float]]:
    """特徴量の平均・標準偏差を計算する(min_history 以上の行のみ)。"""
    sums = {f: 0.0 for f in FEATURE_NAMES}
    sqs = {f: 0.0 for f in FEATURE_NAMES}
    n = 0
    for race in samples:
        for row in race:
            if row.n_hist < min_history:
                continue
            n += 1
            for f in FEATURE_NAMES:
                v = row.feat[f]
                sums[f] += v
                sqs[f] += v * v
    if n == 0:
        return ({f: 0.0 for f in FEATURE_NAMES}, {f: 1.0 for f in FEATURE_NAMES})
    means = {f: sums[f] / n for f in FEATURE_NAMES}
    stds = {}
    for f in FEATURE_NAMES:
        var = max(1e-9, sqs[f] / n - means[f] ** 2)
        stds[f] = sqrt(var)
    return means, stds


def _standardize(feat: dict[str, float], means, stds) -> dict[str, float]:
    return {f: (feat[f] - means[f]) / stds[f] for f in FEATURE_NAMES}


# ---------------------------------------------------------------------------
# Plackett-Luce 尤度最大化(勾配上昇)
# ---------------------------------------------------------------------------

def fit_plackett_luce(
    samples: Sequence[Sequence[_Row]],
    means: dict[str, float],
    stds: dict[str, float],
    *,
    epochs: int = 40,
    lr: float = 0.2,
    l2: float = 1e-3,
    top_k: int = 3,
    min_horses: int = 5,
    min_history: int = 4,
    seed: int = 0,
    verbose: bool = False,
) -> dict[str, float]:
    """標準化済み特徴量に対する線形重みを学習して返す。

    top_k: 上位何着までを尤度に含めるか(3=三連系に直結)。
    """
    rng = random.Random(seed)
    w = {f: 0.0 for f in FEATURE_NAMES}
    w["ability"] = 1.0  # 地力は正の事前値から開始

    # 学習に使えるレースだけ抽出・標準化
    prepared: list[list[tuple[dict[str, float], int]]] = []
    for race in samples:
        horses = [(_standardize(r.feat, means, stds), r.pos)
                  for r in race if r.n_hist >= min_history]
        if len(horses) >= min_horses:
            horses.sort(key=lambda hp: hp[1])  # 着順昇順(1着が先頭)
            prepared.append(horses)

    for epoch in range(epochs):
        rng.shuffle(prepared)
        total_ll = 0.0
        for horses in prepared:
            scores = [sum(w[f] * x[f] for f in FEATURE_NAMES) for x, _ in horses]
            grad = {f: 0.0 for f in FEATURE_NAMES}
            K = min(top_k, len(horses) - 1)
            for k in range(K):
                rem_x = [horses[j][0] for j in range(k, len(horses))]
                rem_s = scores[k:]
                m = max(rem_s)
                exps = [exp(s - m) for s in rem_s]
                Z = sum(exps)
                p = [e / Z for e in exps]
                total_ll += (rem_s[0] - m) - log(Z)
                for f in FEATURE_NAMES:
                    expected = sum(p[j] * rem_x[j][f] for j in range(len(rem_x)))
                    grad[f] += rem_x[0][f] - expected
            for f in FEATURE_NAMES:
                w[f] += lr * grad[f] - lr * l2 * w[f]
        if verbose:
            print(f"  epoch {epoch + 1:3d}  LL={total_ll:.1f}")

    return w


# ---------------------------------------------------------------------------
# 学習済みスコアラー(backtest の score_fn に渡せる)
# ---------------------------------------------------------------------------

@dataclass
class LearnedScorer:
    weights: dict[str, float]
    means: dict[str, float]
    stds: dict[str, float]
    jockeys: ConnStats | None = None
    trainers: ConnStats | None = None
    interval_prior: dict[str, float] | None = None

    def __call__(self, past: list, ctx: RaceContext) -> float:
        feat = horse_features(
            past, ctx, jockeys=self.jockeys, trainers=self.trainers,
            interval_prior=self.interval_prior,
        )
        x = _standardize(feat, self.means, self.stds)
        return sum(self.weights[f] * x[f] for f in FEATURE_NAMES)

    def importances(self) -> list[tuple[str, float]]:
        """重みの絶対値で並べた特徴量重要度(標準化済みなので比較可能)。"""
        return sorted(self.weights.items(), key=lambda kv: abs(kv[1]), reverse=True)


def train_scorer(
    races: Sequence[Race],
    *,
    jockeys: ConnStats | None = None,
    trainers: ConnStats | None = None,
    interval_prior: dict[str, float] | None = None,
    min_history: int = 4,
    **fit_kwargs,
) -> LearnedScorer:
    """レース列から LearnedScorer を学習して返す(ワンストップ)。"""
    samples = build_training_rows(
        races, jockeys=jockeys, trainers=trainers, interval_prior=interval_prior
    )
    means, stds = compute_stats(samples, min_history=min_history)
    weights = fit_plackett_luce(samples, means, stds, min_history=min_history, **fit_kwargs)
    return LearnedScorer(
        weights=weights, means=means, stds=stds,
        jockeys=jockeys, trainers=trainers, interval_prior=interval_prior,
    )
