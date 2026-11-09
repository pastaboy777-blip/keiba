"""展開予想(ペース・隊列・展開利)。中央(JRA)・南関(NAR)共通。

競馬の着順は「能力」だけでなく「展開」で大きく変わる。同じ能力でも
  - 逃げ・先行馬が多い → 前がやり合ってハイペース → 差し・追込が届く
  - 逃げ馬が1頭だけ(単騎逃げ)→ スローで楽に運べる → 前残り
  - 直線が短い(中山・小倉・南関)→ 前有利 / 長い(東京・新潟外)→ 差し有利
という構造がある。オッズ(世間)は馬の能力・人気は織り込むが、メンバー構成で
決まる「今日の展開」は織り込み切れないことがある——そこが回収率の勝ち筋。

ここでは各馬の過去走の通過順位(RunRecord.corner_pos)から脚質を推定し、
メンバー全体から
  (1) ペース予想(ハイ/ミドル/スロー)
  (2) 隊列予想(序盤の位置取り順)
  (3) 各馬の展開利(今日の展開がその馬の脚質に向くか)
を出す。展開利は features の 'tenkai' 特徴量としてスコアに入る。

依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from . import course as cs
from .interval import RunRecord, _recency_weights


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# 脚質
# ---------------------------------------------------------------------------

# 序盤位置(0=先頭, 1=最後方)の境界 → 脚質
STYLE_BOUNDS: list[tuple[float, str]] = [
    (0.12, "逃げ"),
    (0.35, "先行"),
    (0.65, "差し"),
    (1.01, "追込"),
]


@dataclass
class StyleProfile:
    """1頭の脚質プロフィール。"""

    early: float | None   # 序盤の位置(0=先頭〜1=最後方)の直近加重平均。データ無しは None
    nige_rate: float      # 1角(最初の通過)を先頭で通過した割合(直近加重)
    n: int                # 通過順のある走数

    @property
    def style(self) -> str:
        if self.early is None:
            return "不明"
        for bound, name in STYLE_BOUNDS:
            if self.early <= bound:
                return name
        return "追込"

    def early_or(self, default: float = 0.5) -> float:
        return default if self.early is None else self.early


def style_profile(runs: Sequence[RunRecord], *, half_life: int = 3) -> StyleProfile:
    """過去走(新しい順)の最初の通過順位から脚質を推定する。"""
    runs = [r for r in runs if r.corner_pos and r.field_size > 1]
    if not runs:
        return StyleProfile(None, 0.0, 0)
    w = _recency_weights(len(runs), half_life=half_life)
    early = 0.0
    nige = 0.0
    for wi, r in zip(w, runs):
        pos = min(r.corner_pos[0], r.field_size)
        early += wi * ((pos - 1) / (r.field_size - 1))
        nige += wi * (1.0 if pos == 1 else 0.0)
    return StyleProfile(early, nige, len(runs))


# ---------------------------------------------------------------------------
# ペース・隊列予想
# ---------------------------------------------------------------------------

@dataclass
class PaceForecast:
    pace: str                          # 'ハイ' / 'ミドル' / 'スロー'
    pace_index: float                  # + ハイ寄り / − スロー寄り(−1〜+1)
    front_bias: float                  # コース形状の先行有利度(+ 前有利)
    leaders: list[object]              # 逃げ候補(ハナを主張しそうな馬)
    lone_leader: object | None         # 単騎逃げが見込める馬(いなければ None)
    order: list[object]                # 予想隊列(序盤の位置取り 前→後)
    styles: dict[object, StyleProfile] = field(default_factory=dict)
    advantage: dict[object, float] = field(default_factory=dict)  # 展開利

    def summary(self) -> str:
        lead = "・".join(str(x) for x in self.leaders) or "なし"
        solo = f" / 単騎逃げ濃厚: {self.lone_leader}" if self.lone_leader is not None else ""
        bias = "前有利" if self.front_bias > 0.05 else ("差し有利" if self.front_bias < -0.05 else "平坦")
        return (f"ペース予想: {self.pace}(index {self.pace_index:+.2f})"
                f" / コース: {bias}({self.front_bias:+.2f})"
                f" / 逃げ候補: {lead}{solo}")


def _distance_pace_shift(distance: int) -> float:
    """距離による基礎ペース傾向。短距離ほどテンが速くハイになりやすい。"""
    if distance <= 1200:
        return 0.15
    if distance <= 1600:
        return 0.05
    if distance >= 2200:
        return -0.15
    return 0.0


def forecast(
    field_runs: Mapping[object, Sequence[RunRecord]],
    *,
    place: str,
    distance: int,
    surface: str | None = None,
    inner: bool = False,
    leader_rate: float = 0.35,
    adv_scale: float = 0.6,
    lone_bonus: float = 0.15,
) -> PaceForecast:
    """出走馬全体(馬番→過去走)から展開を予想する。

    pace_index: 逃げ候補の多さ(ハナ争いの激しさ)と先行勢の厚み、距離から算出。
    展開利:     (前にいる度合い) × (コース先行有利 − ペース) で、
                スロー×短い直線 → 前の馬が +、ハイ×長い直線 → 後ろの馬が +。
                単騎逃げ濃厚の馬には lone_bonus を加点。
    通過順データの無い馬は序盤位置 0.5(中団)扱い = 展開利ほぼ 0(ニュートラル)。
    """
    styles = {k: style_profile(v) for k, v in field_runs.items()}
    known = {k: s for k, s in styles.items() if s.early is not None}
    n_field = max(1, len(styles))

    # ハナ争いの圧力: 逃げ率の合計(=ハナを主張する頭数の期待値)
    nige_sum = sum(s.nige_rate for s in known.values())
    # 先行勢の厚み: 序盤 35% 以内にいる馬の割合
    front_share = (sum(1 for s in known.values() if s.early <= 0.35) / n_field) if known else 0.3

    pace_index = _clamp(
        0.5 * (nige_sum - 1.0)          # 逃げ馬 1 頭が基準。2 頭以上で競り合い
        + 1.0 * (front_share - 0.3)     # 先行勢が多いほど流れる
        + _distance_pace_shift(distance)
    )
    if not known:
        pace_index = _distance_pace_shift(distance)
    pace = "ハイ" if pace_index > 0.25 else ("スロー" if pace_index < -0.25 else "ミドル")

    leaders = sorted(
        (k for k, s in known.items() if s.nige_rate >= leader_rate),
        key=lambda k: (-known[k].nige_rate, known[k].early),
    )
    lone = None
    if len(leaders) == 1:
        others = max((s.nige_rate for k, s in known.items() if k != leaders[0]), default=0.0)
        if others < leader_rate * 0.6:
            lone = leaders[0]
            pace_index = _clamp(pace_index - 0.2)  # 競りかける馬がいない → 落ち着く
            pace = "ハイ" if pace_index > 0.25 else ("スロー" if pace_index < -0.25 else "ミドル")

    order = sorted(styles, key=lambda k: (styles[k].early_or(), -styles[k].nige_rate))

    fb = cs.front_bias(place, surface, inner=inner)
    tilt = fb - pace_index  # + なら前の馬に向く展開、− なら後ろの馬に向く展開
    advantage: dict[object, float] = {}
    for k, s in styles.items():
        frontness = 0.5 - s.early_or()          # +0.5(先頭)〜 −0.5(最後方)
        adv = adv_scale * frontness * tilt
        if k == lone:
            adv += lone_bonus
        advantage[k] = adv

    return PaceForecast(
        pace=pace, pace_index=pace_index, front_bias=fb,
        leaders=leaders, lone_leader=lone, order=order,
        styles=styles, advantage=advantage,
    )


def tenkai_advantages(
    field_runs: Mapping[object, Sequence[RunRecord]],
    *,
    place: str,
    distance: int,
    surface: str | None = None,
) -> dict[object, float]:
    """馬番 → 展開利 だけを返す簡易版(backtest/learn 用)。"""
    return forecast(field_runs, place=place, distance=distance, surface=surface).advantage
