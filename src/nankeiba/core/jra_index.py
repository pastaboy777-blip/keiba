"""中央(JRA)専用スピード指数 ── エンジンBの芝/ダ・競馬場対応版。

南関版(hindex.SpeedIndexModel)と同じ思想:
    指数 = k × ( par(馬場種, 距離) + 当日馬場差B − 走破タイム )
だが中央は芝とダートで基準時計が大きく違い、競馬場も10場あるため:

  1) par は **馬場種(芝/ダ)ごと** に距離の二次式で持つ。定数はデータから最小二乗で
     自己校正する(南関の外挿破綻を防ぐのと同じ)。
  2) 当日馬場差 B = median( 走破タイム − par(surface, 距離) ) を
     **(開催日 × 競馬場 × 馬場種)** ごとに1回だけ算出。母数が薄い場合は
     (競馬場×馬場種) → (馬場種) の順にフォールバック。
  3) k=10 固定。

芝とダートは別物なので、指数は同一 surface 内での比較に使う(馬柱・展開・買い目)。

依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Iterable, Sequence

from .interval import RunRecord

K_POINTS_PER_SEC = 10.0

# データが少ないとき用の既定二次par(良馬場, 秒)。fitで上書きされる。
# 芝: 1600m≒95.5s, ダ: 1600m≒100.5s あたりを通る緩い曲線。
_DEFAULT_PAR = {
    "芝": (1.6e-6, 0.0560, -3.0),
    "ダ": (1.9e-6, 0.0640, -4.5),
}


def _fit_quadratic(xs: list[float], ys: list[float]) -> tuple[float, float, float] | None:
    """y ≈ a x² + b x + c の最小二乗(正規方程式・3x3)。標準ライブラリのみ。"""
    n = len(xs)
    if n < 6:
        return None
    S0 = n
    S1 = sum(xs); S2 = sum(x * x for x in xs)
    S3 = sum(x ** 3 for x in xs); S4 = sum(x ** 4 for x in xs)
    T0 = sum(ys); T1 = sum(x * y for x, y in zip(xs, ys))
    T2 = sum(x * x * y for x, y in zip(xs, ys))
    # 正規方程式 A·[a,b,c]... 並びは [c,b,a] で解く
    A = [[S0, S1, S2, T0],
         [S1, S2, S3, T1],
         [S2, S3, S4, T2]]
    # ガウス消去
    for i in range(3):
        piv = A[i][i]
        if abs(piv) < 1e-18:
            return None
        for k in range(i, 4):
            A[i][k] /= piv
        for j in range(3):
            if j != i:
                f = A[j][i]
                for k in range(i, 4):
                    A[j][k] -= f * A[i][k]
    c, b, a = A[0][3], A[1][3], A[2][3]
    return (a, b, c)


def _norm_surface(s: str | None) -> str | None:
    if not s:
        return None
    if "芝" in s:
        return "芝"
    if "ダ" in s:
        return "ダ"
    return None


@dataclass
class JraIndexModel:
    par_coef: dict[str, tuple[float, float, float]] = field(
        default_factory=lambda: dict(_DEFAULT_PAR))
    day_variant: dict[tuple, float] = field(default_factory=dict)      # (date,place,surf)->B
    track_variant: dict[tuple, float] = field(default_factory=dict)    # (place,surf)->B
    surf_variant: dict[str, float] = field(default_factory=dict)       # surf->B
    k: float = K_POINTS_PER_SEC
    base: float = 0.0
    min_samples: int = 6

    def par(self, surface: str | None, distance: int) -> float | None:
        s = _norm_surface(surface)
        if s is None or not distance:
            return None
        a, b, c = self.par_coef.get(s, _DEFAULT_PAR.get(s, (0, 0, 0)))
        d = float(distance)
        return a * d * d + b * d + c

    def variant(self, rec: RunRecord) -> float:
        s = _norm_surface(rec.surface)
        for key, table in (((rec.date, rec.place, s), self.day_variant),
                           ((rec.place, s), self.track_variant),
                           (s, self.surf_variant)):
            if key in table:
                return table[key]
        return 0.0

    def index(self, rec: RunRecord) -> float | None:
        if rec.time_sec is None:
            return None
        p = self.par(rec.surface, rec.distance)
        if p is None:
            return None
        v = round(self.k * (p + self.variant(rec) - rec.time_sec) + self.base)
        return abs(v) if v == 0 else v

    def index_of(self, runs: Sequence[RunRecord]) -> list[float | None]:
        return [self.index(r) for r in runs]

    @classmethod
    def fit(cls, records: Iterable[RunRecord], *, base: float = 0.0,
            min_samples: int = 6, k: float = K_POINTS_PER_SEC) -> "JraIndexModel":
        recs = [r for r in records
                if r.time_sec is not None and r.distance and _norm_surface(r.surface)]
        # 1) 馬場種ごとに par を二次でフィット(良/稍のみ=速い側で基準を作る)
        par_coef = dict(_DEFAULT_PAR)
        by_surf_xy: dict[str, tuple[list, list]] = {"芝": ([], []), "ダ": ([], [])}
        for r in recs:
            s = _norm_surface(r.surface)
            by_surf_xy[s][0].append(float(r.distance))
            by_surf_xy[s][1].append(r.time_sec)
        for s, (xs, ys) in by_surf_xy.items():
            coef = _fit_quadratic(xs, ys)
            if coef is not None:
                par_coef[s] = coef
        model = cls(par_coef=par_coef, base=base, min_samples=min_samples, k=k)

        # 2) 馬場差B(実測−par)の中央値: 日×場×種 / 場×種 / 種
        day: dict[tuple, list[float]] = {}
        track: dict[tuple, list[float]] = {}
        surf: dict[str, list[float]] = {}
        for r in recs:
            s = _norm_surface(r.surface)
            delta = r.time_sec - model.par(s, r.distance)
            day.setdefault((r.date, r.place, s), []).append(delta)
            track.setdefault((r.place, s), []).append(delta)
            surf.setdefault(s, []).append(delta)
        model.day_variant = {kk: round(median(v), 2) for kk, v in day.items()
                             if len(v) >= min_samples}
        model.track_variant = {kk: round(median(v), 2) for kk, v in track.items()
                               if len(v) >= 3}
        model.surf_variant = {kk: round(median(v), 2) for kk, v in surf.items()}
        return model
