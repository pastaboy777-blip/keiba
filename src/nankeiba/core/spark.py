"""激走マーク(激走予定馬ランク) ── ⚠️実験的・未検証(要学習)。

競馬の天才/TARGET指数の「激走★」に相当。近く好走が期待できる馬を自動抽出し、
上位を 激走1番/2番/3番 とランク付けする。狙いは指数“単体”では拾えない上昇馬・
条件替わり・巻き返し(=人気薄の一発)を掬うこと。

⚠️ 重要(正直な検証結果): 下記の手調整シグナル・重みは **未検証** で、大井2026-07-21
   の実測では「激走1-3番が3着内」= 50% と、無作為3頭(≒55%)を下回った。本家の激走★は
   大量データで学習した予測モデルであり、手調整の重みでは再現できない。実用にするには
   ラベル付きデータ(実際に人気以上に走ったか)で重みを学習し、アウトオブサンプル検証で
   複勝率/回収率が無作為を上回ることを確認する必要がある。現状は学習版の足場(特徴量
   抽出)として置く。

激走スコアは「地力(指数)」より **上昇気配・条件フィット** を重く見る:
  - 潜在ギャップ : 近5走最高指数 − 近2走最高指数(近走で地力を出せていない)
  - 距離フィット : 好指数を出した距離が今回に近い(条件が向く)
  - 叩き良化     : 休み明け→2〜3走目(南関のピーク)
  - 巻き返し余地 : 前走大敗だが地力(指数)は場内上位
  - 末脚上昇     : 前走の上がり3Fが自己ベスト級(脚を余した/上向き)
  - 地力(従)    : 指数の場内相対(強い馬も好走はする、ただし従属的に)

依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from statistics import median
from typing import Sequence

from .interval import RunRecord
from .hindex import SpeedIndexModel


def _pdate(s: str) -> date:
    y, m, d = (int(x) for x in s.split("-"))
    return date(y, m, d)


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# 各シグナルの重み(上昇気配を重く、地力は従属)
W_HIDDEN = 1.0
W_DIST = 0.8
W_TATAKII = 0.7
W_REBOUND = 0.9
W_CLOSING = 0.7
W_ABILITY = 0.5


@dataclass
class Spark:
    umaban: int
    score: float
    rank: int | None = None          # 激走1/2/3番(上位のみ)。無印は None
    reasons: list[str] = field(default_factory=list)

    @property
    def mark(self) -> str:
        return f"激{self.rank}番" if self.rank else ""


def _best_index(runs: Sequence[RunRecord], model: SpeedIndexModel, lookback: int):
    best = None
    for r in list(runs)[:lookback]:
        idx = model.index(r)
        if idx is not None and (best is None or idx > best):
            best = idx
    return best


def _best_run(runs: Sequence[RunRecord], model: SpeedIndexModel, lookback: int):
    best, brun = None, None
    for r in list(runs)[:lookback]:
        idx = model.index(r)
        if idx is not None and (best is None or idx > best):
            best, brun = idx, r
    return brun


def spark_ranking(
    entries: Sequence[tuple[int, Sequence[RunRecord]]],
    model: SpeedIndexModel,
    today_place: str,
    today_distance: int,
    today_date: str,
    *,
    n_marks: int = 3,
) -> dict[int, Spark]:
    """各馬の激走スコアを計算し、上位 n_marks 頭を激走1..n番にする。"""
    # 場内の地力分布(巻き返し判定・地力正規化に使う)
    best5_map = {um: _best_index(runs, model, 5) for um, runs in entries}
    vals = [v for v in best5_map.values() if v is not None]
    med5 = median(vals) if vals else 0.0
    lo5, hi5 = (min(vals), max(vals)) if vals else (0.0, 1.0)
    span = max(1e-6, hi5 - lo5)

    out: dict[int, Spark] = {}
    for um, runs in entries:
        runs = list(runs)
        reasons: list[str] = []
        score = 0.0

        best5 = best5_map[um]
        best2 = _best_index(runs, model, 2)

        # 潜在ギャップ(近走で地力を出せていない)
        if best5 is not None and best2 is not None:
            gap = best5 - best2
            if gap >= 6:
                s = _clamp(gap / 15.0)
                score += W_HIDDEN * s
                reasons.append(f"潜在+{gap:.0f}(近走不振)")

        # 距離フィット(好指数の距離が今回に近い)
        brun = _best_run(runs, model, 5)
        if brun is not None and abs(brun.distance - today_distance) <= 200:
            # 前走が今回距離から離れているほど「条件が向く」度合い大
            prev_gap = abs(runs[0].distance - today_distance) if runs else 0
            s = _clamp(0.4 + prev_gap / 600.0)
            score += W_DIST * s
            if prev_gap >= 200:
                reasons.append(f"好指数の{brun.distance}mに戻る")

        # 叩き良化(前走が休み明け→今回2走目 / 2走前が休み明け→3走目)
        if runs:
            try:
                iv0 = (_pdate(today_date) - _pdate(runs[0].date)).days
                iv1 = (_pdate(runs[0].date) - _pdate(runs[1].date)).days if len(runs) >= 2 else 0
                iv2 = (_pdate(runs[1].date) - _pdate(runs[2].date)).days if len(runs) >= 3 else 0
                if iv1 >= 45 and iv0 <= 40:
                    score += W_TATAKII * 1.0
                    reasons.append("叩き2走目")
                elif iv2 >= 45 and iv1 <= 40 and iv0 <= 40:
                    score += W_TATAKII * 0.7
                    reasons.append("叩き3走目")
            except (ValueError, IndexError):
                pass

        # 巻き返し余地(前走大敗だが地力は場内上位)
        if runs and runs[0].field_size:
            fin, fs = runs[0].finish_pos, runs[0].field_size
            if fin >= fs * 0.6 and best5 is not None and best5 >= med5:
                score += W_REBOUND * _clamp((best5 - med5) / span + 0.4)
                reasons.append("前走大敗も地力上位")

        # 末脚上昇(前走の上がりが自己ベスト級)
        agaris = [r.last3f_sec for r in runs[:6] if r.last3f_sec is not None]
        if runs and runs[0].last3f_sec is not None and len(agaris) >= 3:
            if runs[0].last3f_sec <= min(agaris) + 0.1:
                score += W_CLOSING * 1.0
                reasons.append("前走 上がり自己ベスト級")

        # 地力(従属・正規化)
        if best5 is not None:
            score += W_ABILITY * ((best5 - lo5) / span)

        out[um] = Spark(umaban=um, score=round(score, 3), reasons=reasons)

    # ランク付け(スコア上位 n_marks・シグナルが1つ以上ある馬のみ)
    ranked = sorted(
        [s for s in out.values() if s.reasons],
        key=lambda s: s.score, reverse=True,
    )
    for i, s in enumerate(ranked[:n_marks]):
        s.rank = i + 1
    return out
