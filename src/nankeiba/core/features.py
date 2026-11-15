"""「ズブい馬をいかに走らせるか」を定量化する総合スコアモジュール。

南関競馬は、ズブい(タフで間隔を詰めて使われる)馬を、陣営が
「叩き良化・乗り替わり・競馬場替わり・距離変更」などの手を使って
今日のレースで走らせにいくゲーム、という捉え方に基づく。

馬1頭について、過去走(RunRecord 列)と今回のレース条件(RaceContext)から
強さスコアを算出する。スコアは Plackett-Luce のストレングス exp(score) に使う。

依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Sequence

from . import interval as iv


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _parse_date(s: str) -> date:
    y, m, d = (int(x) for x in s.split("-"))
    return date(y, m, d)


# ---------------------------------------------------------------------------
# 今回のレース条件 と 関係者の成績テーブル
# ---------------------------------------------------------------------------

@dataclass
class RaceContext:
    """今回出走するレースの条件。"""

    date: str
    place: str
    distance: int
    field_size: int
    jockey: str | None = None
    trainer: str | None = None
    baba: str | None = None   # 馬場状態 '良'/'稍'/'重'/'不'


@dataclass
class ConnStats:
    """騎手・調教師の成績テーブル。'追える力'/'仕上げ手腕' の代理指標。

    rates: 名前 -> 勝率(または好走率)0〜1。未知の名前は default を使う。
    """

    rates: dict[str, float] = field(default_factory=dict)
    default: float = 0.08

    def get(self, name: str | None) -> float:
        if name is None:
            return self.default
        return self.rates.get(name, self.default)


# ---------------------------------------------------------------------------
# 叩き良化(休み明けからの叩き○走目)
# ---------------------------------------------------------------------------

def starts_since_layoff(
    runs: Sequence[iv.RunRecord],
    upcoming_days: int | None,
    *,
    layoff_days: int = 61,
) -> int:
    """今回が「叩き何走目」かを返す。

    休み明け(間隔 >= layoff_days)を 1 走目とし、そこから詰めて使った数を数える。
    今回の出走間隔 upcoming_days が休み明けなら 1(叩き初戦)。
    """
    if upcoming_days is None or upcoming_days >= layoff_days:
        return 1
    runs = list(runs)
    iv._fill_intervals(runs)
    count = 1  # 今回ぶん
    for r in runs:
        count += 1
        # この走自体が休み明けだった(=ここが叩き初戦)なら打ち切り
        if r.days_since_last is None or r.days_since_last >= layoff_days:
            break
    return count


# 手設定の叩き加点プライア。2〜3走目をピークにする。
# 1走目(休み明け)はまだズブいので低め、2〜3走目で最大、その後は緩やかに低下。
# 実データからは priors.learn_tatakii_bonus で推定して差し替えられる。
TATAKII_PRIOR: dict[int, float] = {1: -0.10, 2: 0.10, 3: 0.12, 4: 0.05, 5: 0.0}


def tatakii_bonus(n: int, table: dict[int, float] | None = None) -> float:
    """叩き○走目に応じた加点。既定は手設定プライア、table で上書き可能。

    table を渡した場合、その最大キーを超える n はそのキーの値にクランプする
    (learn_tatakii_bonus は max_n 以上を1つに集約するため)。
    """
    if table is not None:
        if n in table:
            return table[n]
        max_key = max(table) if table else 0
        if n > max_key and max_key in table:
            return table[max_key]
        return 0.0
    if n in TATAKII_PRIOR:
        return TATAKII_PRIOR[n]
    return -0.05  # 使い込み気味


# ---------------------------------------------------------------------------
# 条件変化(乗り替わり・競馬場替わり・距離変更)
# ---------------------------------------------------------------------------

def jockey_change_signal(
    runs: Sequence[iv.RunRecord],
    ctx: RaceContext,
    jockeys: ConnStats,
) -> float:
    """乗り替わりの評価。強化乗り替わり(上位騎手へ)ほど高い。

    乗り替わりが無ければ 0。乗り替わりなら (今回騎手力 − 前走騎手力)。
    """
    runs = list(runs)
    if not runs or ctx.jockey is None or runs[0].jockey is None:
        return 0.0
    if ctx.jockey == runs[0].jockey:
        return 0.0
    return jockeys.get(ctx.jockey) - jockeys.get(runs[0].jockey)


def _place_aptitude(runs: Sequence[iv.RunRecord], place: str, baseline: float) -> float:
    vals = [r.finish_strength() - baseline for r in runs if r.place == place]
    return sum(vals) / len(vals) if vals else 0.0


def place_change_fit(
    runs: Sequence[iv.RunRecord],
    ctx: RaceContext,
    baseline: float,
) -> float:
    """競馬場替わりの評価。今回の競馬場での自身比相対成績。

    替わりが無くてもその舞台が得意なら加点。データが無ければ 0。
    """
    return _place_aptitude(runs, ctx.place, baseline)


def distance_change_fit(
    runs: Sequence[iv.RunRecord],
    ctx: RaceContext,
    baseline: float,
    *,
    band: int = 200,
) -> float:
    """距離変更の評価。今回距離に近い距離帯(±band)での自身比相対成績。"""
    vals = [
        r.finish_strength() - baseline
        for r in runs
        if abs(r.distance - ctx.distance) <= band
    ]
    return sum(vals) / len(vals) if vals else 0.0


# ---------------------------------------------------------------------------
# 使い込み疲労(タフネスの裏返し)
# ---------------------------------------------------------------------------

def fatigue_penalty(
    profile: iv.HorseProfile,
    upcoming_days: int | None,
    *,
    heavy_starts: int = 6,
    short_days: int = 12,
) -> float:
    """詰めすぎの反動。直近90日の出走過多 かつ 今回も超短間隔なら減点。"""
    if profile.starts_last_90d <= heavy_starts:
        return 0.0
    if upcoming_days is not None and upcoming_days <= short_days:
        over = profile.starts_last_90d - heavy_starts
        return -0.04 * over
    return 0.0


# ---------------------------------------------------------------------------
# 総合スコア
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 脚質(先行力)・末脚・馬場適性  ※通過順・上がり3F順位・馬場が必要
# ---------------------------------------------------------------------------

def _norm_baba(b: str | None) -> str | None:
    return b[0] if b else None


def senkou_power(runs: Sequence[iv.RunRecord], *, half_life: int = 3) -> float:
    """先行力。前で運ぶほど +、後方ほど −(中心化、データ無しは 0)。

    各走の最初のコーナー通過順位を頭数で正規化し、直近を重く加重平均する。
    南関の小回り・脚抜きの悪い良ダートでは前で運べる馬が有利。
    """
    runs = [r for r in runs if r.corner_pos]
    if not runs:
        return 0.0
    w = iv._recency_weights(len(runs), half_life=half_life)
    val = 0.0
    for wi, r in zip(w, runs):
        pos = r.corner_pos[0]
        val += wi * ((r.field_size - pos) / max(1, r.field_size - 1))
    return val - 0.5


def agari_sharpness(runs: Sequence[iv.RunRecord], *, half_life: int = 3) -> float:
    """末脚の鋭さ。上がり3F順位が速いほど +(中心化、データ無しは 0)。"""
    runs = [r for r in runs if r.agari_rank is not None]
    if not runs:
        return 0.0
    w = iv._recency_weights(len(runs), half_life=half_life)
    val = 0.0
    for wi, r in zip(w, runs):
        val += wi * ((r.field_size - r.agari_rank) / max(1, r.field_size - 1))
    return val - 0.5


def baba_fit(runs: Sequence[iv.RunRecord], ctx: "RaceContext", baseline: float) -> float:
    """馬場適性。今回と同じ馬場区分での自身比相対成績(データ無しは 0)。"""
    today = _norm_baba(ctx.baba)
    if today is None:
        return 0.0
    vals = [r.finish_strength() - baseline for r in runs if _norm_baba(r.baba) == today]
    return sum(vals) / len(vals) if vals else 0.0


# 特徴量の名前(重みベクトルと1対1対応)。学習はこの係数を最適化する。
FEATURE_NAMES: list[str] = [
    "ability",        # 着順ベースの地力
    "interval_fit",   # 出走間隔フィット
    "toughness",      # タフネス指数(中心化)
    "tatakii",        # 叩き良化
    "senkou",         # 先行力(脚質)
    "agari",          # 末脚の鋭さ
    "baba_fit",       # 馬場適性
    "jockey_change",  # 乗り替わり強化
    "jockey_power",   # 騎手の追える力
    "trainer",        # 厩舎の仕上げ手腕
    "place_fit",      # 競馬場替わり適性
    "distance_fit",   # 距離変更適性
    "fatigue",        # 使い込み疲労(負)
]


@dataclass
class ScoreWeights:
    """各特徴量の重み。既定値は手設定のプライア。learn で上書きできる。"""

    ability: float = 1.0
    interval_fit: float = 0.6
    toughness: float = 0.3
    tatakii: float = 1.0
    senkou: float = 0.5
    agari: float = 0.3
    baba_fit: float = 0.5
    jockey_change: float = 1.0
    jockey_power: float = 0.8
    trainer: float = 0.4
    place_fit: float = 0.5
    distance_fit: float = 0.5
    fatigue: float = 1.0

    def as_dict(self) -> dict[str, float]:
        return {f: getattr(self, f) for f in FEATURE_NAMES}

    @classmethod
    def from_dict(cls, d: dict[str, float]) -> "ScoreWeights":
        return cls(**{f: d.get(f, 0.0) for f in FEATURE_NAMES})


def horse_features(
    runs: Sequence[iv.RunRecord],
    ctx: RaceContext,
    *,
    jockeys: ConnStats | None = None,
    trainers: ConnStats | None = None,
    interval_prior: dict[str, float] | None = None,
    tatakii_table: dict[int, float] | None = None,
) -> dict[str, float]:
    """馬1頭の特徴量ベクトル(重みをかける前の生の値)。

    「ズブい馬を走らせる」観点を数値化したもの。スコア = Σ 重み×特徴量。
    interval_prior / tatakii_table を渡すと、間隔・叩きのプライアを
    実データ学習値(priors.learn_*)で上書きできる。
    """
    jockeys = jockeys or ConnStats()
    trainers = trainers or ConnStats()
    runs = list(runs)

    profile = iv.build_profile(runs)
    iv._fill_intervals(runs)
    upcoming_days = (
        (_parse_date(ctx.date) - _parse_date(runs[0].date)).days if runs else None
    )
    baseline = profile.ability_baseline
    n_tatakii = starts_since_layoff(runs, upcoming_days)

    return {
        "ability": profile.ability,
        "interval_fit": iv.interval_fit(profile, upcoming_days, prior=interval_prior),
        "toughness": profile.toughness - 0.5,
        "tatakii": tatakii_bonus(n_tatakii, tatakii_table),
        "senkou": senkou_power(runs),
        "agari": agari_sharpness(runs),
        "baba_fit": baba_fit(runs, ctx, baseline),
        "jockey_change": jockey_change_signal(runs, ctx, jockeys),
        "jockey_power": jockeys.get(ctx.jockey) - jockeys.default,
        "trainer": trainers.get(ctx.trainer) - trainers.default,
        "place_fit": place_change_fit(runs, ctx, baseline),
        "distance_fit": distance_change_fit(runs, ctx, baseline),
        "fatigue": fatigue_penalty(profile, upcoming_days),
    }


def horse_score(
    runs: Sequence[iv.RunRecord],
    ctx: RaceContext,
    *,
    jockeys: ConnStats | None = None,
    trainers: ConnStats | None = None,
    weights: ScoreWeights | None = None,
    interval_prior: dict[str, float] | None = None,
    tatakii_table: dict[int, float] | None = None,
) -> float:
    """馬1頭の総合強さスコア = 重み・特徴量の内積。

    Plackett-Luce には exp(このスコア) を渡す。
    """
    w = (weights or ScoreWeights()).as_dict()
    feats = horse_features(
        runs, ctx, jockeys=jockeys, trainers=trainers,
        interval_prior=interval_prior, tatakii_table=tatakii_table,
    )
    return sum(w[f] * feats[f] for f in FEATURE_NAMES)
