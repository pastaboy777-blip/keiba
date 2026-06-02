"""出走間隔(レース間隔)を軸にした「ズブさ/タフネス」評価モジュール。

南関競馬(大井・川崎・船橋・浦和)は開催頻度が高く、馬は出走間隔を詰めて
(連闘・中1週など)使われることが多い。体質がズブい=タフな馬は短間隔でも
パフォーマンスが落ちず、むしろ使われ続けて調子を維持する。一方で間隔が
空く(休み明け)とズブくて動かない=仕上がりが鈍く本来の力を出せない馬がいる。

ここでは2つの観点を両立させる:
  (1) 全体傾向(プライア): 南関は短間隔ほど有利・休み明けは割引、という事前バイアス。
      実データがあれば学習値で上書きできる(INTERVAL_PRIOR を差し替える)。
  (2) 馬ごとの間隔適性: その馬が「連闘で好走/休み明けで凡走」かを過去走から個別に学習。

依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _parse_date(s: str) -> date:
    y, m, d = (int(x) for x in s.split("-"))
    return date(y, m, d)


# ---------------------------------------------------------------------------
# 出走間隔のバケット分け
# ---------------------------------------------------------------------------

# (上限日数, ラベル) ※下から順に判定。最後の None は「それ以上」
_BUCKETS: list[tuple[int | None, str]] = [
    (10, "rento"),       # 連闘・詰め(〜10日)
    (20, "naka1"),       # 中1〜2週(11〜20日)
    (35, "normal"),      # 標準(21〜35日)
    (60, "aki"),         # 間隔開き(36〜60日)
    (120, "kyumei"),     # 休み明け(61〜120日)
    (None, "long_kyuyo"),  # 長期休養明け(121日〜)
]


def interval_bucket(days: int | None) -> str:
    """出走間隔[日]をバケットラベルに変換する。days が None なら 'unknown'。"""
    if days is None:
        return "unknown"
    for upper, label in _BUCKETS:
        if upper is None or days <= upper:
            return label
    return "long_kyuyo"


# 全体傾向プライア: 南関は短間隔ほど有利、休み明けは割引。
# 値は強さスコアへの加点(任意単位)。実データがあれば学習値に差し替える。
INTERVAL_PRIOR: dict[str, float] = {
    "rento": 0.15,
    "naka1": 0.08,
    "normal": 0.0,
    "aki": -0.05,
    "kyumei": -0.12,
    "long_kyuyo": -0.20,
    "unknown": 0.0,
}


def global_interval_prior(days: int | None, prior: dict[str, float] | None = None) -> float:
    """今回の出走間隔に対する全体傾向の加点を返す。"""
    table = prior if prior is not None else INTERVAL_PRIOR
    return table.get(interval_bucket(days), 0.0)


# ---------------------------------------------------------------------------
# 過去走データ
# ---------------------------------------------------------------------------

@dataclass
class RunRecord:
    """1走分の成績。スクレイピング結果をこの形に正規化して渡す。

    Attributes:
        date:        開催日 'YYYY-MM-DD'(間隔計算に使う)
        place:       競馬場名('大井' など)
        distance:    距離[m]
        field_size:  出走頭数
        finish_pos:  着順(1 始まり)
        jockey:      騎手名(任意。乗り替わり判定に使う)
        trainer:     調教師名(任意)
        popularity:  人気順(任意。期待との乖離を見るのに使える)
        days_since_last: 前走からの間隔[日]。None なら build_profile が日付列から補完。
    """

    date: str
    place: str
    distance: int
    field_size: int
    finish_pos: int
    jockey: str | None = None
    trainer: str | None = None
    popularity: int | None = None
    days_since_last: int | None = None

    def finish_strength(self) -> float:
        """着順ベースの強さ。1着=1.0、最下位=~0.0。"""
        return _clamp((self.field_size - self.finish_pos) / max(1, self.field_size - 1))


# ---------------------------------------------------------------------------
# 馬プロフィール
# ---------------------------------------------------------------------------

@dataclass
class HorseProfile:
    n_runs: int
    ability: float                       # 着順ベースの地力(直近加重)
    starts_last_90d: int                 # 直近90日の出走数(使われ具合=タフさの素)
    toughness: float                     # ズブさ/タフネス指数 0〜1
    perf_by_bucket: dict[str, float]     # 間隔バケット別の相対成績(自身の平均からの差)
    ability_baseline: float              # 相対成績の基準(全走の平均強さ)


def _recency_weights(n: int, half_life: int = 3) -> list[float]:
    if n == 0:
        return []
    decay = 0.5 ** (1.0 / max(1, half_life))
    raw = [decay ** i for i in range(n)]  # i=0 が最新
    s = sum(raw)
    return [w / s for w in raw]


def _fill_intervals(runs: list[RunRecord]) -> None:
    """日付列から days_since_last を補完する(新しい順に並んでいる前提)。"""
    for i, r in enumerate(runs):
        if r.days_since_last is not None:
            continue
        if i + 1 < len(runs):
            r.days_since_last = (_parse_date(r.date) - _parse_date(runs[i + 1].date)).days
        # 最古の走は前走不明なので None のまま


def build_profile(
    runs: Sequence[RunRecord],
    *,
    half_life: int = 3,
    short_days: int = 20,
    freq_target: int = 5,
) -> HorseProfile:
    """過去走(新しい順)から間隔中心のプロフィールを構築する。

    - ability: 着順強さの直近加重平均
    - perf_by_bucket: 間隔バケットごとの「自身の平均からの相対成績」
        正なら「その間隔で(自分比)走れる」、負なら「その間隔は苦手」
    - toughness: 出走頻度 + 短間隔での相対成績で決まるズブさ/タフネス
    """
    runs = list(runs)
    n = len(runs)
    if n == 0:
        return HorseProfile(0, 0.5, 0, 0.5, {}, 0.5)

    _fill_intervals(runs)
    w = _recency_weights(n, half_life=half_life)
    ability = sum(wi * r.finish_strength() for wi, r in zip(w, runs))
    baseline = sum(r.finish_strength() for r in runs) / n

    # 間隔バケット別の相対成績(自身の平均 baseline からの差)
    bucket_vals: dict[str, list[float]] = {}
    for r in runs:
        b = interval_bucket(r.days_since_last)
        if b == "unknown":
            continue
        bucket_vals.setdefault(b, []).append(r.finish_strength() - baseline)
    perf_by_bucket = {b: sum(v) / len(v) for b, v in bucket_vals.items()}

    # 直近90日の出走数(最新走を起点に遡る)
    latest = _parse_date(runs[0].date)
    starts_last_90d = sum(1 for r in runs if (latest - _parse_date(r.date)).days <= 90)

    # 短間隔(<= short_days)での相対成績
    short_rel_vals = [
        r.finish_strength() - baseline
        for r in runs
        if r.days_since_last is not None and r.days_since_last <= short_days
    ]
    short_rel = sum(short_rel_vals) / len(short_rel_vals) if short_rel_vals else 0.0

    freq_norm = _clamp(starts_last_90d / max(1, freq_target))
    # タフネス: よく使われ(freq)、短間隔でも崩れない(short_rel>=0)馬ほど高い
    toughness = _clamp(0.5 * freq_norm + 0.5 * (0.5 + short_rel))

    return HorseProfile(
        n_runs=n,
        ability=ability,
        starts_last_90d=starts_last_90d,
        toughness=toughness,
        perf_by_bucket=perf_by_bucket,
        ability_baseline=baseline,
    )


def interval_fit(
    profile: HorseProfile,
    upcoming_days: int | None,
    *,
    prior: dict[str, float] | None = None,
) -> float:
    """今回の出走間隔に対するフィット度(任意単位)。

    全体傾向プライア + その馬のそのバケットでの相対成績。
    データが無いバケットはプライアのみで評価する。
    """
    g = global_interval_prior(upcoming_days, prior)
    b = interval_bucket(upcoming_days)
    horse = profile.perf_by_bucket.get(b, 0.0)
    return g + horse


def strength_score(
    profile: HorseProfile,
    upcoming_days: int | None,
    *,
    prior: dict[str, float] | None = None,
    interval_lambda: float = 0.6,
    toughness_lambda: float = 0.3,
) -> float:
    """予測用の強さスコア(任意実数)。

    地力 + interval_lambda × 間隔フィット + toughness_lambda ×(タフネス−0.5)。
    interval_lambda/toughness_lambda を上げるほど「出走間隔」観点を強く効かせる。
    Plackett-Luce のストレングスには exp(この値) を使う。
    """
    return (
        profile.ability
        + interval_lambda * interval_fit(profile, upcoming_days, prior=prior)
        + toughness_lambda * (profile.toughness - 0.5)
    )
