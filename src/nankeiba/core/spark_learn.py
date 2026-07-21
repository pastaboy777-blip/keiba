"""激走★の学習版：特徴量抽出 + ロジスティック回帰（標準ライブラリのみ）。

手調整の激走(spark.py)は検証で無作為以下だった。ここでは「複勝圏(3着以内)」を
教師ラベルに、レース前の特徴量から P(好走) を学習する。予測確率で各馬を並べ、
上位を 激走1/2/3番 とする。人気(オッズ)は特徴に入れない＝穴の激走も拾える。

学習後は必ずアウトオブサンプル(学習に使っていない開催)で、激走馬の複勝率・回収率が
無作為/人気を上回るかを検証すること(scripts/train_spark.py)。

依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date
from statistics import mean, pstdev
from typing import Sequence

from .interval import RunRecord
from .hindex import SpeedIndexModel
from .composite import dominant_style


def _pdate(s: str) -> date:
    y, m, d = (int(x) for x in s.split("-"))
    return date(y, m, d)


# 特徴量名(順序固定)
FEATURES = [
    "best5", "gap5_2", "dist_fit", "tatakii2", "tatakii3", "rebound",
    "closing", "nige", "senko", "sashi", "oikomi", "short_iv",
    "n_runs", "recent_form",
]


def extract_features(
    runs: Sequence[RunRecord],
    model: SpeedIndexModel,
    today_place: str,
    today_distance: int,
    today_date: str,
) -> dict[str, float]:
    """1頭のレース前特徴量。人気/オッズは含めない。"""
    runs = list(runs)
    idxs = [model.index(r) for r in runs]
    idx5 = [x for x in idxs[:5] if x is not None]
    idx2 = [x for x in idxs[:2] if x is not None]
    best5 = max(idx5) if idx5 else -30.0
    best2 = max(idx2) if idx2 else -30.0

    # 好指数を出した走(近5)
    brun = None
    bi = None
    for r in runs[:5]:
        i = model.index(r)
        if i is not None and (bi is None or i > bi):
            bi, brun = i, r
    dist_fit = 1.0 if (brun and abs(brun.distance - today_distance) <= 200) else 0.0

    # 叩き
    tat2 = tat3 = 0.0
    short_iv = 0.0
    try:
        iv0 = (_pdate(today_date) - _pdate(runs[0].date)).days if runs else None
        iv1 = (_pdate(runs[0].date) - _pdate(runs[1].date)).days if len(runs) >= 2 else None
        iv2 = (_pdate(runs[1].date) - _pdate(runs[2].date)).days if len(runs) >= 3 else None
        if iv0 is not None and iv0 <= 20:
            short_iv = 1.0
        if iv1 and iv1 >= 45 and iv0 is not None and iv0 <= 40:
            tat2 = 1.0
        elif iv2 and iv2 >= 45 and iv1 and iv1 <= 40 and iv0 is not None and iv0 <= 40:
            tat3 = 1.0
    except (ValueError, IndexError):
        pass

    rebound = 0.0
    if runs and runs[0].field_size:
        rebound = min(1.0, runs[0].finish_pos / max(1, runs[0].field_size))

    closing = 0.0
    agaris = [r.last3f_sec for r in runs[:6] if r.last3f_sec is not None]
    if runs and runs[0].last3f_sec is not None and len(agaris) >= 3:
        if runs[0].last3f_sec <= min(agaris) + 0.1:
            closing = 1.0

    style = dominant_style(runs)
    recent = [r.finish_strength() for r in runs[:3]]

    return {
        "best5": best5, "gap5_2": best5 - best2, "dist_fit": dist_fit,
        "tatakii2": tat2, "tatakii3": tat3, "rebound": rebound, "closing": closing,
        "nige": 1.0 if style == "逃げ" else 0.0,
        "senko": 1.0 if style == "先行" else 0.0,
        "sashi": 1.0 if style == "差し" else 0.0,
        "oikomi": 1.0 if style == "追込" else 0.0,
        "short_iv": short_iv,
        "n_runs": float(min(len(runs), 10)),
        "recent_form": mean(recent) if recent else 0.0,
    }


@dataclass
class SparkModel:
    """ロジスティック回帰(標準化つき)。"""
    weights: list[float] = field(default_factory=lambda: [0.0] * len(FEATURES))
    bias: float = 0.0
    mu: list[float] = field(default_factory=lambda: [0.0] * len(FEATURES))
    sd: list[float] = field(default_factory=lambda: [1.0] * len(FEATURES))

    def _x(self, feat: dict[str, float]) -> list[float]:
        return [(feat[k] - self.mu[i]) / self.sd[i] for i, k in enumerate(FEATURES)]

    def prob(self, feat: dict[str, float]) -> float:
        z = self.bias + sum(w * x for w, x in zip(self.weights, self._x(feat)))
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))

    def importances(self) -> list[tuple[str, float]]:
        return sorted(zip(FEATURES, self.weights), key=lambda t: -abs(t[1]))

    def to_json(self) -> str:
        return json.dumps({"weights": self.weights, "bias": self.bias,
                           "mu": self.mu, "sd": self.sd})

    @classmethod
    def from_json(cls, s: str) -> "SparkModel":
        d = json.loads(s)
        return cls(weights=d["weights"], bias=d["bias"], mu=d["mu"], sd=d["sd"])

    @classmethod
    def train(cls, rows: Sequence[dict], labels: Sequence[int], *,
              epochs: int = 300, lr: float = 0.3, l2: float = 1e-3) -> "SparkModel":
        n = len(rows)
        if n == 0:
            return cls()
        mu = [mean(r[k] for r in rows) for k in FEATURES]
        sd = [pstdev(r[k] for r in rows) or 1.0 for k in FEATURES]
        m = cls(mu=mu, sd=sd)
        X = [m._x(r) for r in rows]
        for _ in range(epochs):
            gw = [0.0] * len(FEATURES)
            gb = 0.0
            for x, y in zip(X, labels):
                z = m.bias + sum(w * xi for w, xi in zip(m.weights, x))
                p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
                e = p - y
                for i in range(len(FEATURES)):
                    gw[i] += e * x[i]
                gb += e
            for i in range(len(FEATURES)):
                m.weights[i] -= lr * (gw[i] / n + l2 * m.weights[i])
            m.bias -= lr * (gb / n)
        return m
