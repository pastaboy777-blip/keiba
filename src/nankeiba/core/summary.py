"""指数系サマリー(新聞上部の一覧)。

新聞の各サマリー欄を再現する:
  - 10走以内 指数上位一覧 (t4): 出走各馬の過去10走以内での最高指数を一覧化。
    馬番・日付・競馬場・距離・馬場・指数・何走前。近走不振でも過去に高指数の
    人気薄あぶり出しに使う。
  - 前3Fタイム上位 (t5): 近距離(今回の距離±200m)の過去5走内から前半3F上位。
  - 同競馬場 指数上位 (南関版): 同competition場で出した過去の指数上位の馬番。

依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .interval import RunRecord
from .hindex import SpeedIndexModel, estimate_first3f, normalize_going


# 今回の馬場に対して「同系統」とみなす馬場(渋った馬場はまとめて評価)
GOING_GROUP = {
    "良": {"良"},
    "稍": {"稍", "重"},
    "重": {"稍", "重", "不"},
    "不": {"重", "不"},
}


@dataclass
class GoingAptitude:
    umaban: int
    n: int                       # 同系統馬場での該当走数
    best_index: float | None     # そのうち最高指数
    avg_finish: float | None     # 平均着順
    in3_rate: float | None       # 複勝率(3着以内)


def going_aptitude(
    entries: Sequence[tuple[int, Sequence[RunRecord]]],
    model: SpeedIndexModel,
    today_going: str,
    *,
    lookback: int = 10,
) -> dict[int, GoingAptitude]:
    """今回の馬場と同系統の馬場での各馬の適性(最高指数・平均着順・複勝率)。"""
    group = GOING_GROUP.get(normalize_going(today_going) or "", set())
    out: dict[int, GoingAptitude] = {}
    for umaban, runs in entries:
        idxs: list[float] = []
        finishes: list[int] = []
        for rec in list(runs)[:lookback]:
            if normalize_going(rec.baba) not in group:
                continue
            finishes.append(rec.finish_pos)
            idx = model.index(rec)
            if idx is not None:
                idxs.append(idx)
        n = len(finishes)
        out[umaban] = GoingAptitude(
            umaban=umaban, n=n,
            best_index=max(idxs) if idxs else None,
            avg_finish=round(sum(finishes) / n, 1) if n else None,
            in3_rate=round(sum(1 for f in finishes if f <= 3) / n, 2) if n else None,
        )
    return out


@dataclass
class IndexRow:
    umaban: int
    date: str
    place: str
    distance: int
    baba: str | None
    index: float
    runs_ago: int          # 1=前走


@dataclass
class First3FRow:
    umaban: int
    date: str
    place: str
    distance: int
    first3f: float
    runs_ago: int


def top_index_last10(
    entries: Sequence[tuple[int, Sequence[RunRecord]]],
    model: SpeedIndexModel,
    *,
    lookback: int = 10,
    limit: int | None = None,
) -> list[IndexRow]:
    """各馬の過去 lookback 走以内での最高指数を集め、指数降順に並べる。"""
    rows: list[IndexRow] = []
    for umaban, runs in entries:
        best: IndexRow | None = None
        for i, rec in enumerate(list(runs)[:lookback]):
            idx = model.index(rec)
            if idx is None:
                continue
            if best is None or idx > best.index:
                best = IndexRow(
                    umaban=umaban, date=rec.date, place=rec.place,
                    distance=rec.distance, baba=rec.baba, index=idx, runs_ago=i + 1,
                )
        if best is not None:
            rows.append(best)
    rows.sort(key=lambda r: r.index, reverse=True)
    return rows[:limit] if limit else rows


def same_track_index_top(
    entries: Sequence[tuple[int, Sequence[RunRecord]]],
    model: SpeedIndexModel,
    place: str,
    *,
    lookback: int = 10,
    limit: int | None = None,
) -> list[IndexRow]:
    """今回の競馬場と同じ競馬場で出した過去の最高指数(馬番)を指数降順で。"""
    rows: list[IndexRow] = []
    for umaban, runs in entries:
        best: IndexRow | None = None
        for i, rec in enumerate(list(runs)[:lookback]):
            if rec.place != place:
                continue
            idx = model.index(rec)
            if idx is None:
                continue
            if best is None or idx > best.index:
                best = IndexRow(
                    umaban=umaban, date=rec.date, place=rec.place,
                    distance=rec.distance, baba=rec.baba, index=idx, runs_ago=i + 1,
                )
        if best is not None:
            rows.append(best)
    rows.sort(key=lambda r: r.index, reverse=True)
    return rows[:limit] if limit else rows


def first3f_top(
    entries: Sequence[tuple[int, Sequence[RunRecord]]],
    today_distance: int,
    *,
    lookback: int = 5,
    dist_tol: int = 200,
    limit: int = 10,
) -> list[First3FRow]:
    """近距離(±dist_tol)の過去 lookback 走内から前半3F上位(速い順)を返す。

    各馬のベスト前3Fを1つ採用し、速い順に最大 limit 頭。前3Fは概算。
    """
    rows: list[First3FRow] = []
    for umaban, runs in entries:
        best: First3FRow | None = None
        for i, rec in enumerate(list(runs)[:lookback]):
            if abs(rec.distance - today_distance) > dist_tol:
                continue
            f3 = rec.first3f_sec
            if f3 is None:
                f3 = estimate_first3f(
                    rec.time_sec, rec.distance,
                    last3f_sec=rec.last3f_sec, corner_pos=rec.corner_pos,
                    field_size=rec.field_size,
                )
            if f3 is None:
                continue
            if best is None or f3 < best.first3f:
                best = First3FRow(
                    umaban=umaban, date=rec.date, place=rec.place,
                    distance=rec.distance, first3f=f3, runs_ago=i + 1,
                )
        if best is not None:
            rows.append(best)
    rows.sort(key=lambda r: r.first3f)
    return rows[:limit]
