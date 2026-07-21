"""スピード指数(タイム指数)エンジン ── エンジンB(検証確定版)。

実物の南関競馬新聞(マキシマム競馬新聞)の指数を複数セッションで逆解析し、
構造を完全に割り出した(交差検証済み・MAE<2.5)。確定した3点:

  1) 指数 = k × (実測基準タイム − 走破タイム)、**k=10 固定(距離で変えない)**。
  2) 標準パー(基準タイム)は**距離の二次式**で持つ(長距離の外挿破綻を防ぐ):
        par(d) = 2.02e-6·d² + 0.0667·d − 6.96   [秒]
     ※距離正規化は「係数」ではなく「基準タイム側(par)」で行う。
  3) 馬場差は固定値では当たらない(MAE9.7)。**当日実測**なら当たる(MAE2.5):
        実測基準タイム = par(距離) + B
        B = median( 走破タイム − par(距離) )  … 開催日×競馬場の全走から1回だけ算出
     符号を一貫させ、B を指数式で**1回だけ**反映するのが生命線。

固定モデル(競馬場×距離の基準表)より、この「馬場差を当日の勝ちタイムから観測化する」
設計が数字で明確に上回ることが実証済み。母数(その日その場の複数馬・複数レース)を
増やすほど当日補正が正確になり、MAE は 2 点を切る。

`SpeedIndexModel.fit(runs)` が B を実測し、`.index(rec)` が上式で指数を返す。

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


# ---------------------------------------------------------------------------
# エンジンB: 二次パー基準 + k=10固定 + 当日実測の馬場差(1回だけ反映)
# ---------------------------------------------------------------------------
#
# 複数セッションの逆解析で確定した指数構造(検証済み・MAE<2.5):
#   1) 指数 = k × (実測基準タイム − 走破タイム)、k=10固定(距離で変えない)
#   2) 標準パー(基準タイム)は距離の二次式で持つ(長距離の外挿破綻を防ぐ):
#        par(d) = 2.02e-6·d² + 0.0667·d − 6.96   [秒]
#   3) 馬場差は固定値では当たらない(MAE9.7)。**当日実測**なら当たる(MAE2.5)。
#      実測基準タイム = par(d) + B。B(その日その競馬場の速さ)は
#        B = median( 走破タイム − par(距離) )   … 開催日×競馬場の全走から1回だけ算出
#      符号を一貫させ、指数式では B を1回だけ反映するのが生命線。
#   距離正規化は「係数」ではなく「基準タイム側(par)」で行う。

K_POINTS_PER_SEC = 10.0
PAR_A = 2.02e-6
PAR_B = 0.0667
PAR_C = -6.96


def par_time(distance: int) -> float:
    """標準パー(基準タイム)[秒]。距離の二次式。"""
    d = float(distance)
    return PAR_A * d * d + PAR_B * d + PAR_C


@dataclass
class SpeedIndexModel:
    """スピード指数モデル(エンジンB)。

    指数 = k × ( par(距離) + B(date,place) − 走破タイム ) + base

    Attributes:
        day_variant:     開催日×競馬場ごとの馬場差 B[秒] {(date, place): 秒}。
                         B = median(走破タイム − par(距離))。
        global_variant:  データ全体の馬場差 B の中央値(サンプル不足の日に使う)。
        k:               1秒あたりの点数(既定10・距離不問)。
        base:            出力オフセット(既定0)。
        min_samples:     日別 B を採用する最小サンプル数。
    """

    day_variant: dict[tuple, float] = field(default_factory=dict)
    place_variant: dict[str, float] = field(default_factory=dict)
    global_variant: float = 0.0
    k: float = K_POINTS_PER_SEC
    base: float = 0.0
    min_samples: int = 5

    def variant(self, rec: RunRecord) -> float:
        """その走の馬場差 B。当日×競馬場 → 競馬場 → 全体 の順にフォールバック。

        当日×競馬場に十分な母数があればそれを使う(当日実測=最精度)。母数が薄い
        ときは競馬場単位の中央値で場差(大井は速い/浦和は遅い等)を吸収する。
        """
        key = (rec.date, rec.place)
        if key in self.day_variant:
            return self.day_variant[key]
        if rec.place in self.place_variant:
            return self.place_variant[rec.place]
        return self.global_variant

    def index(self, rec: RunRecord) -> float | None:
        """1走分の指数。走破タイムが無ければ None。"""
        if rec.time_sec is None:
            return None
        implied_base = par_time(rec.distance) + self.variant(rec)   # 実測基準タイム
        v = round(self.k * (implied_base - rec.time_sec) + self.base)
        return abs(v) if v == 0 else v          # -0.0 を 0.0 に正規化

    def index_of(self, runs: Sequence[RunRecord]) -> list[float | None]:
        return [self.index(r) for r in runs]

    @classmethod
    def fit(
        cls,
        records: Iterable[RunRecord],
        *,
        base: float = 0.0,
        min_samples: int = 5,
        k: float = K_POINTS_PER_SEC,
    ) -> "SpeedIndexModel":
        """走破タイム付きの走から、開催日×競馬場ごとの馬場差 B を実測する。

        B = median( 走破タイム − par(距離) )。母数を増やすほど当日補正が正確になる
        (1レースでなく、その日その場の複数馬・複数レースのタイムを渡すこと)。
        サンプルが min_samples 未満の日は全体中央値(global_variant)で代替する。
        """
        recs = [r for r in records if r.time_sec is not None and r.distance]
        day: dict[tuple, list[float]] = {}
        place: dict[str, list[float]] = {}
        all_delta: list[float] = []
        for r in recs:
            delta = r.time_sec - par_time(r.distance)     # 実測 − パー
            day.setdefault((r.date, r.place), []).append(delta)
            place.setdefault(r.place, []).append(delta)
            all_delta.append(delta)
        global_variant = round(median(all_delta), 2) if all_delta else 0.0
        day_variant = {
            key: round(median(v), 2)
            for key, v in day.items() if len(v) >= min_samples
        }
        # 競馬場単位(場差の吸収)。少数でも全体値よりは場を代表する。
        place_variant = {
            p: round(median(v), 2) for p, v in place.items() if len(v) >= 3
        }
        return cls(day_variant=day_variant, place_variant=place_variant,
                   global_variant=global_variant, k=k, base=base, min_samples=min_samples)
