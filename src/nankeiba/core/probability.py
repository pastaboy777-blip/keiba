"""強さスコア → 着順確率(三連複・三連単)への変換。

Plackett-Luce モデル: 各馬のストレングス s_i から、着順(順列)の確率を
逐次的に計算する。
  P(1着a,2着b,3着c) = s_a/Z * s_b/(Z-s_a) * s_c/(Z-s_a-s_b)
三連複(順不同の上位3頭)はその6通りの順列の和。

依存ライブラリなし(標準ライブラリのみ)。
頭数は南関の最大16頭程度を想定。三連単順列 16*15*14=3360、三連複 C(16,3)=560 で十分高速。
"""

from __future__ import annotations

from itertools import combinations, permutations
from math import exp
from typing import Iterable


def strengths_from_scores(scores: dict[int, float], *, temperature: float = 1.0) -> dict[int, float]:
    """スコア(任意実数)を Plackett-Luce のストレングス exp(score/T) に変換。

    temperature を上げると確率が平準化(自信が下がる)、下げると尖る。
    """
    # オーバーフロー防止に最大値を引く
    mx = max(scores.values())
    return {h: exp((s - mx) / temperature) for h, s in scores.items()}


def trifecta_probabilities(strengths: dict[int, float]) -> dict[tuple[int, int, int], float]:
    """三連単(順序つき上位3頭)の確率。キーは (1着,2着,3着) の馬番タプル。"""
    total = sum(strengths.values())
    horses = list(strengths)
    out: dict[tuple[int, int, int], float] = {}
    for a, b, c in permutations(horses, 3):
        sa = strengths[a]
        sb = strengths[b]
        sc = strengths[c]
        z1 = total
        z2 = total - sa
        z3 = total - sa - sb
        if z2 <= 0 or z3 <= 0:
            continue
        out[(a, b, c)] = (sa / z1) * (sb / z2) * (sc / z3)
    return out


def trio_probabilities(strengths: dict[int, float]) -> dict[tuple[int, int, int], float]:
    """三連複(順不同の上位3頭)の確率。キーは昇順の馬番タプル。"""
    tri = trifecta_probabilities(strengths)
    out: dict[tuple[int, int, int], float] = {}
    for (a, b, c), p in tri.items():
        key = tuple(sorted((a, b, c)))  # type: ignore[assignment]
        out[key] = out.get(key, 0.0) + p
    return out


def top3_probability(strengths: dict[int, float], horse: int) -> float:
    """ある馬が3着以内に入る確率(軸馬選定の参考に)。"""
    p = 0.0
    for combo, prob in trio_probabilities(strengths).items():
        if horse in combo:
            p += prob
    return p
