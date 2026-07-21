"""スピード指数(タイム指数)エンジン。

実物の南関競馬新聞(マキシマム競馬新聞)の「指数」を PDF から逆解析した結果、
これは走破タイムを距離・競馬場・馬場で標準化した **スピード指数(西田式ベース)** と
判明した。逆解析の根拠(大井のサンプル):

  - 大井1600 の同一馬4走が  指数 ≒ 410.5 − 4.0 × タイム秒  にほぼ完全一致
    (残差 < 0.5)。→ タイムに対して一次線形、係数 4.0 点/秒。
  - 距離が短いほど 1 秒あたりの点数が大きい(1400≒4.6、1200 はさらに大)。
    → 距離係数(distance_coef)でタイム差を点数へ変換する。
  - 同タイムでも馬場(良/稍/重/不)と開催日で指数が上下する。
    例) 大井1400良 91.7秒→-9  vs  大井1400重 91.7秒→-14。
    → 馬場差補正(going_offset + 開催日ごとの day-variant)を持つ。
  - 競馬場ごとに基準が違う(大井は速い=同タイムでも辛い、浦和は遅い)。
  - 値が負中心なのは、基準タイムを「強い時計」に置いているため
    (弱いレースはマイナスに出る)。

したがって指数の一般形は:

    指数 = (基準タイム − 走破タイム) × 距離係数 + 馬場差 + 基準値

基準タイム表・馬場差は本来その新聞の非公開定数だが、**データから自己校正**できる
(スピード指数の作り方そのもの)。`SpeedIndexModel.fit()` が競馬場×距離ごとの
基準タイムと開催日ごとの馬場差をリーク無しで推定する。手元にデータが無くても
南関のデフォルト基準タイムで概算指数を出せる。

依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Iterable, Sequence

from .interval import RunRecord


# ---------------------------------------------------------------------------
# 馬場(going)の正規化
# ---------------------------------------------------------------------------

def normalize_going(baba: str | None) -> str | None:
    """馬場文字列を '良'/'稍'/'重'/'不' に正規化する。先頭1文字で判定。"""
    if not baba:
        return None
    c = baba[0]
    if c in "良稍重不":
        return c
    table = {"稍": "稍", "や": "稍", "重": "重", "不": "不", "良": "良"}
    return table.get(c)


# 馬場差の既定オフセット[点]。濡れた馬場ほど時計が速く出る南関ダートでは、
# 同じタイムでも良馬場よりマイナス評価にする(=基準が速い)。fit で上書き可。
DEFAULT_GOING_OFFSET: dict[str, float] = {
    "良": 0.0,
    "稍": -2.0,
    "重": -4.0,
    "不": -6.0,
}


# ---------------------------------------------------------------------------
# 距離係数(1 秒あたりの点数)
# ---------------------------------------------------------------------------

# 逆解析のアンカー: 1600m で 4.0 点/秒。短距離ほど大きくする(タイム差が詰まるため)。
BASE_DISTANCE = 1600
BASE_PPS = 4.0


def distance_coef(distance: int, *, base_dist: int = BASE_DISTANCE,
                  base_pps: float = BASE_PPS) -> float:
    """距離[m]に対する 1 秒あたりの点数を返す。

    短距離ほど大(タイム差が詰まる)、長距離ほど小。基準距離で base_pps に一致。
    逆解析(1600m≒4.0点/秒)に整合する滑らかな反比例カーブ。
    """
    if distance <= 0:
        return base_pps
    return base_pps * (base_dist / distance)


# ---------------------------------------------------------------------------
# 前半3F(概算)
# ---------------------------------------------------------------------------

def estimate_first3f(
    time_sec: float | None,
    distance: int,
    *,
    last3f_sec: float | None = None,
    corner_pos: Sequence[int] | None = None,
    field_size: int | None = None,
) -> float | None:
    """前半3F(600m)タイムの概算[秒]。

    新聞と同様あくまで概算。走破タイムから終い3Fを引いた中間区間の平均ペースを
    もとに前半600mを推定し、道中の位置取り(前にいたほど前半が速い)で微補正する。
    """
    if time_sec is None or distance <= 0:
        return None
    if last3f_sec is not None and distance > 600:
        # 中間(距離-600m)の平均秒/m。前半600mも同ペースと仮置き。
        mid_pace = (time_sec - last3f_sec) / (distance - 600)
        base = mid_pace * 600
    else:
        base = time_sec * 600.0 / distance
    # 位置取り補正: 平均通過位置が前ほど前半速い(=タイム小)。
    if corner_pos and field_size and field_size > 1:
        avg_pos = sum(corner_pos) / len(corner_pos)
        mid = (field_size + 1) / 2
        base *= 1.0 + 0.015 * (avg_pos - mid)
    return round(base, 1)


# ---------------------------------------------------------------------------
# 南関のデフォルト基準タイム(良馬場, 秒)。データが無いときの概算用。
# 逆解析サンプルと一般的な標準時計から設定。fit() で上書きされる。
# ---------------------------------------------------------------------------

DEFAULT_STANDARD_TIME: dict[str, dict[int, float]] = {
    "大井": {1000: 61.0, 1200: 73.5, 1400: 87.5, 1500: 94.0, 1600: 100.5, 1700: 107.0, 1800: 113.5, 2000: 126.5},
    "川崎": {900: 55.5, 1400: 88.5, 1500: 95.0, 1600: 101.5, 2000: 128.0, 2100: 134.5},
    "船橋": {1000: 61.5, 1200: 74.0, 1500: 94.5, 1600: 101.0, 1700: 107.5, 1800: 114.0, 2400: 154.0},
    "浦和": {800: 48.5, 1300: 81.0, 1400: 88.5, 1500: 95.5, 1600: 102.0, 1900: 122.0, 2000: 128.5},
}
# 南関以外(概算・良馬場)。距離あたりの平均ペースから内挿する既定。
_FALLBACK_PACE_SEC_PER_M = 0.0632  # ≒ 良ダートの平均(1600m≒101秒)


def _fallback_standard(place: str | None, distance: int) -> float:
    """基準タイムが無い競馬場・距離のフォールバック(良馬場)。"""
    return round(distance * _FALLBACK_PACE_SEC_PER_M, 1)


@dataclass
class SpeedIndexModel:
    """スピード指数モデル。

    Attributes:
        standard:      基準タイム表 {競馬場: {距離: 秒}}(良馬場基準)。
        going_offset:  馬場カテゴリ別の点数補正。
        base:          出力の基準値(オフセット)。
        day_variant:   開催日×競馬場ごとの馬場差[点] {(date, place): 点}。
        base_dist/base_pps: 距離係数のパラメータ。
    """

    standard: dict[str, dict[int, float]] = field(default_factory=lambda: {
        p: dict(d) for p, d in DEFAULT_STANDARD_TIME.items()
    })
    going_offset: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_GOING_OFFSET))
    base: float = 0.0
    day_variant: dict[tuple, float] = field(default_factory=dict)
    base_dist: int = BASE_DISTANCE
    base_pps: float = BASE_PPS

    # --- 基準タイムの取得(近距離内挿つき)---
    def standard_time(self, place: str | None, distance: int) -> float:
        table = self.standard.get(place or "", {})
        if distance in table:
            return table[distance]
        if table:
            # 最寄り距離から平均ペースで内挿
            nd = min(table, key=lambda d: abs(d - distance))
            pace = table[nd] / nd
            return round(distance * pace, 1)
        return _fallback_standard(place, distance)

    def coef(self, distance: int) -> float:
        return distance_coef(distance, base_dist=self.base_dist, base_pps=self.base_pps)

    # --- 1走の指数 ---
    def index(self, rec: RunRecord) -> float | None:
        """1走分の指数を返す。走破タイムが無ければ None。"""
        if rec.time_sec is None:
            return None
        std = self.standard_time(rec.place, rec.distance)
        pts = (std - rec.time_sec) * self.coef(rec.distance)
        going = normalize_going(rec.baba)
        pts += self.going_offset.get(going, 0.0) if going else 0.0
        pts += self.day_variant.get((rec.date, rec.place), 0.0)
        v = round(pts + self.base, 0)
        return abs(v) if v == 0 else v      # -0.0 を 0.0 に正規化

    def index_of(self, runs: Sequence[RunRecord]) -> list[float | None]:
        return [self.index(r) for r in runs]

    # --- データからの自己校正 ---
    @classmethod
    def fit(
        cls,
        records: Iterable[RunRecord],
        *,
        fast_quantile: float = 0.15,
        base: float = 0.0,
        min_samples: int = 8,
        estimate_day_variant: bool = True,
        base_pps: float = BASE_PPS,
        base_dist: int = BASE_DISTANCE,
    ) -> "SpeedIndexModel":
        """走破タイム付きの過去走から基準タイム・馬場差を推定する。

        - 基準タイム: 競馬場×距離ごとに、良/稍の速い側 fast_quantile 分位のタイム。
          「強い時計」を基準に置くことで新聞同様マイナス中心のレンジになる。
          重/不(濡れ)は時計が速く出るため基準推定から除外する。
        - 馬場差(day_variant): 開催日×競馬場ごとに、その日の全走の
          (基準タイム−走破タイム)×距離係数 の中央値を「その日の速さ」として持つ。
          index() で差し引くことで日ごとの時計の出方を吸収する。
        """
        recs = [r for r in records if r.time_sec is not None]

        # 1) 基準タイム(良・稍のみ)
        groups: dict[tuple[str, int], list[float]] = {}
        for r in recs:
            g = normalize_going(r.baba)
            if g in ("重", "不"):
                continue
            groups.setdefault((r.place, r.distance), []).append(r.time_sec)
        standard: dict[str, dict[int, float]] = {
            p: dict(d) for p, d in DEFAULT_STANDARD_TIME.items()
        }
        for (place, dist), times in groups.items():
            if len(times) < min_samples:
                continue
            times = sorted(times)
            k = max(0, min(len(times) - 1, int(len(times) * fast_quantile)))
            standard.setdefault(place, {})[dist] = round(times[k], 1)

        model = cls(standard=standard, base=base, base_pps=base_pps, base_dist=base_dist)

        # 2) 開催日×競馬場ごとの馬場差
        if estimate_day_variant:
            day_pts: dict[tuple, list[float]] = {}
            for r in recs:
                std = model.standard_time(r.place, r.distance)
                raw = (std - r.time_sec) * model.coef(r.distance)
                going = normalize_going(r.baba)
                raw += model.going_offset.get(going, 0.0) if going else 0.0
                day_pts.setdefault((r.date, r.place), []).append(raw)
            model.day_variant = {
                k: round(median(v), 1) for k, v in day_pts.items() if len(v) >= 3
            }
        return model
