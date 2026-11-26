"""実データから「間隔プライア」「叩き良化」を推定する。

手設定の `interval.INTERVAL_PRIOR` と `features.tatakii_bonus` は南関の全体傾向を
表す事前値だが、実レースの着順があれば **データから直接推定** できる。

推定の考え方(レース内相対で測る):
  各走の強さは finish_strength = (頭数−着順)/(頭数−1) で 0〜1 に正規化され、
  1レース内での平均は必ず 0.5 になる(頭数に依らず race-centered)。
  よって「あるバケット(間隔/叩き走目)に属する走の finish_strength の平均 − 0.5」は、
  そのバケットの馬が**同じレースの平均に対して**どれだけ上/下に走るかを表す。
  = そのバケットの相対的な有利/不利。これをそのまま加点プライアに使える。

少サンプルの偏りを避けるため、各バケットの推定値は 0 に向けて pseudo 件ぶん縮約する
(ベイズ的スムージング)。時系列の「過去走だけ」で間隔・叩き走目を判定するので、
渡すのは **学習区間のレースだけ** にすること(リーク防止)。

依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

from typing import Sequence

from . import interval as iv
from .backtest import Race
from .features import RaceContext, starts_since_layoff


def _parse_date(s: str):
    return iv._parse_date(s)


def _iter_bucketed(races: Sequence[Race]):
    """時系列に過去走だけを積みながら、各出走の
    (間隔バケット, 叩き走目, finish_strength) を yield する。

    間隔・叩き走目は「そのレース時点の過去走」から判定する(リーク無し)。
    """
    history: dict[object, list[iv.RunRecord]] = {}
    for race in sorted(races, key=lambda r: r.date):
        pos_of = {um: i + 1 for i, um in enumerate(race.result_order)}
        for e in race.entries:
            past = history.get(e.horse_id, [])
            upcoming_days = (
                (_parse_date(race.date) - _parse_date(past[0].date)).days if past else None
            )
            bucket = iv.interval_bucket(upcoming_days)
            n_tatakii = starts_since_layoff(past, upcoming_days)
            pos = pos_of.get(e.num(), race.field_size)
            fs = (race.field_size - pos) / max(1, race.field_size - 1)
            yield bucket, n_tatakii, fs
        # 履歴更新(このレース結果を各馬に追記)
        for e in race.entries:
            rec = iv.RunRecord(
                date=race.date, place=race.place, distance=race.distance,
                field_size=race.field_size, finish_pos=pos_of.get(e.num(), race.field_size),
                jockey=e.jockey, trainer=e.trainer,
            )
            history.setdefault(e.horse_id, []).insert(0, rec)


def _shrunk_means(
    pairs: dict[object, list[float]], *, pseudo: float, scale: float
) -> dict[object, float]:
    """キー -> 値リスト から、0 に縮約した平均 × scale を返す。"""
    out: dict[object, float] = {}
    for k, vals in pairs.items():
        n = len(vals)
        mean = sum(vals) / n if n else 0.0
        out[k] = scale * mean * (n / (n + pseudo))  # 0 へ縮約
    return out


def learn_interval_prior(
    races: Sequence[Race], *, pseudo: float = 40.0, scale: float = 1.0
) -> dict[str, float]:
    """間隔バケット別の相対成績から `INTERVAL_PRIOR` を推定する。

    返り値は `interval.global_interval_prior(days, prior=...)` や
    `horse_features(..., interval_prior=...)` にそのまま渡せる。
    'unknown' は常に 0(初出走は前提を置かない)。
    """
    by_bucket: dict[str, list[float]] = {}
    for bucket, _n, fs in _iter_bucketed(races):
        if bucket == "unknown":
            continue
        by_bucket.setdefault(bucket, []).append(fs - 0.5)
    prior = _shrunk_means(by_bucket, pseudo=pseudo, scale=scale)
    prior["unknown"] = 0.0
    # 未観測バケットは 0 で補完(キーの網羅性を保つ)
    for _upper, label in iv._BUCKETS:
        prior.setdefault(label, 0.0)
    return prior


def learn_tatakii_bonus(
    races: Sequence[Race], *, pseudo: float = 40.0, scale: float = 1.0, max_n: int = 6
) -> dict[int, float]:
    """叩き○走目別の相対成績から `tatakii` 加点テーブルを推定する。

    max_n 走目以上はまとめて max_n のキーに集約する(サンプル確保)。
    返り値は `horse_features(..., tatakii_table=...)` に渡せる。
    """
    by_n: dict[int, list[float]] = {}
    for _bucket, n, fs in _iter_bucketed(races):
        key = min(n, max_n)
        by_n.setdefault(key, []).append(fs - 0.5)
    return _shrunk_means(by_n, pseudo=pseudo, scale=scale)


def learn_priors(
    races: Sequence[Race], *, pseudo: float = 40.0, scale: float = 1.0
) -> tuple[dict[str, float], dict[int, float]]:
    """間隔プライアと叩き加点をまとめて推定する(ワンストップ)。"""
    return (
        learn_interval_prior(races, pseudo=pseudo, scale=scale),
        learn_tatakii_bonus(races, pseudo=pseudo, scale=scale),
    )
