"""ペース適性 S / H / F / U（南関版TARGET）。

TARGET指数の「ペース適性」を南関データ（楽天：通過順・上がり3F・タイム有り）で再現する。

  - S (Slow) : スローで好走（瞬発力タイプ）
  - H (High) : ハイペースで好走（持続力タイプ）
  - F (Flex) : どんなペースでも対応（自在）
  - U (Unknown): 判断できない（データ不足）
  - 「激」    : 主に逃げてこそ（逃げ主体の馬）

各過去走の「レースのペース」を、前半3F（概算）と上がり3Fの差から推定し、
その馬が **どのペースで走れているか（好走しているか）** を集計して分類する。
※前半3Fは概算（区間ラップが無いため）。あくまで参考指標（TARGET同様）。

依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

from statistics import mean
from typing import Sequence

from .interval import RunRecord
from .hindex import estimate_first3f
from .composite import dominant_style


def race_pace(rec: RunRecord) -> str | None:
    """1走のレースペースを 'S'/'M'/'H' で推定する。判定不能は None。

    前半3F（概算）− 上がり3F が負に大きい＝前傾（ハイ）、正に大きい＝後傾（スロー）。
    """
    a3 = rec.last3f_sec
    if a3 is None:
        return None
    f3 = rec.first3f_sec or estimate_first3f(
        rec.time_sec, rec.distance, last3f_sec=a3,
        corner_pos=rec.corner_pos, field_size=rec.field_size,
    )
    if f3 is None:
        return None
    diff = f3 - a3
    if diff <= -0.8:
        return "H"          # 前半が速い＝ハイペース
    if diff >= 0.8:
        return "S"          # 前半が遅い＝スロー（上がり勝負）
    return "M"


def pace_aptitude(
    runs: Sequence[RunRecord],
    *,
    lookback: int = 8,
    min_runs: int = 3,
    good: float = 0.6,
    gap: float = 0.12,
) -> str:
    """過去走から得意ペース S/H/F/U を返す。

    各ペース（S/H）での「着順強さ（finish_strength）」平均を比べ、
    片側が明確に良ければ S or H、両側とも good 以上なら F（自在）、
    データ不足や差が無ければ U。
    """
    rs = list(runs)[:lookback]
    if len([r for r in rs if r.last3f_sec is not None]) < min_runs:
        return "U"
    buckets: dict[str, list[float]] = {"S": [], "M": [], "H": []}
    for r in rs:
        p = race_pace(r)
        if p:
            buckets[p].append(r.finish_strength())

    s = mean(buckets["S"]) if buckets["S"] else None
    h = mean(buckets["H"]) if buckets["H"] else None

    if s is not None and h is not None:
        if s >= good and h >= good:
            return "F"
        if s - h >= gap:
            return "S"
        if h - s >= gap:
            return "H"
        # 差が小さい：両方そこそこなら F、低調なら U
        return "F" if max(s, h) >= good else "U"
    if s is not None:
        return "S" if s >= good else "U"
    if h is not None:
        return "H" if h >= good else "U"
    return "U"


def pace_aptitude_mark(runs: Sequence[RunRecord], *, lookback: int = 8) -> str:
    """S/H/F/U に、逃げ主体なら「激」を付けて返す（例 'H激'）。"""
    apt = pace_aptitude(runs, lookback=lookback)
    style = dominant_style(runs, lookback=min(4, lookback))
    return apt + ("激" if style == "逃げ" else "")
