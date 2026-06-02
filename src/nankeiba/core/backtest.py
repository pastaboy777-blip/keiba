"""時系列バックテスト。回収率(ROI)で評価する。

鉄則:
  - リーク厳禁: 各レースの予測には「そのレースより前」の成績だけを使う。
  - 時系列順に進める(未来の情報を混ぜない)。
  - 評価は的中率ではなく回収率(払戻総額 / 購入総額)。

依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

from . import interval as iv
from . import probability as pb
from . import betting as bt
from .features import RaceContext, ConnStats, horse_score, ScoreWeights


@dataclass
class Entry:
    """出走馬1頭。

    horse_id は馬の永続ID(履歴の突合に使う・レースをまたいで不変)。
    umaban は馬番(オッズ・着順のキー・レース内のみ有効)。
    実データでは両者は別物。umaban 省略時は horse_id を馬番として代用する。
    """

    horse_id: object
    umaban: int | None = None
    jockey: str | None = None
    trainer: str | None = None

    def num(self) -> object:
        """オッズ・着順照合に使う馬番(無ければ horse_id で代用)。"""
        return self.umaban if self.umaban is not None else self.horse_id


@dataclass
class Race:
    """1レース分。バックテスト/本番共通の入力形式。"""

    race_id: str
    date: str
    place: str
    distance: int
    field_size: int
    entries: list[Entry]
    result_order: list[int]                      # 着順に並べた馬番(>=3頭)
    trio_odds: dict[tuple[int, int, int], float]  # 三連複オッズ(昇順の馬番キー)
    trifecta_odds: dict[tuple[int, int, int], float]  # 三連単オッズ(着順の馬番キー)


@dataclass
class BacktestResult:
    n_races: int = 0
    n_bet_races: int = 0
    n_bets: int = 0
    n_hits: int = 0
    spent: float = 0.0
    returned: float = 0.0
    pnl_history: list[float] = field(default_factory=list)

    @property
    def roi(self) -> float:
        return self.returned / self.spent if self.spent > 0 else 0.0

    @property
    def hit_rate(self) -> float:
        return self.n_hits / self.n_bets if self.n_bets else 0.0

    def summary(self) -> str:
        return (
            f"races={self.n_races} bet_races={self.n_bet_races} "
            f"bets={self.n_bets} hits={self.n_hits} "
            f"hit_rate={self.hit_rate:.1%} spent={self.spent:.0f} "
            f"returned={self.returned:.0f} ROI={self.roi:.1%} "
            f"pnl={self.returned - self.spent:+.0f}"
        )


def run_backtest(
    races: Sequence[Race],
    *,
    jockeys: ConnStats | None = None,
    trainers: ConnStats | None = None,
    weights: ScoreWeights | None = None,
    score_fn: Optional[Callable[[list, RaceContext], float]] = None,
    bet_type: str = "trio",            # "trio"(三連複) or "trifecta"(三連単)
    ev_threshold: float = 1.2,
    stake_per_bet: float = 100.0,
    max_bets: int = 8,
    temperature: float = 1.0,
    min_history: int = 3,
) -> BacktestResult:
    """時系列にバックテストする。

    各レースで、出走各馬の「過去走」だけからスコア → 確率 → 期待値 → 買い目。
    確定結果で精算し ROI を集計する。履歴は精算後に更新する(リーク防止)。

    score_fn を渡すとスコア計算をそれに委譲する(学習済みスコアラー等)。
    None の場合は weights を使った horse_score を用いる。
    """
    history: dict[object, list[iv.RunRecord]] = {}
    res = BacktestResult()
    races = sorted(races, key=lambda r: r.date)

    for race in races:
        res.n_races += 1

        # --- 過去走だけでスコア化(スコアは馬番でキーづけ)---
        scores: dict[object, float] = {}
        enough = True
        for e in race.entries:
            past = history.get(e.horse_id, [])
            ctx = RaceContext(
                date=race.date,
                place=race.place,
                distance=race.distance,
                field_size=race.field_size,
                jockey=e.jockey,
                trainer=e.trainer,
            )
            if score_fn is not None:
                scores[e.num()] = score_fn(past, ctx)
            else:
                scores[e.num()] = horse_score(
                    past, ctx, jockeys=jockeys, trainers=trainers, weights=weights
                )
            if len(past) < min_history:
                enough = False

        if enough and len(scores) >= 3:
            strengths = pb.strengths_from_scores(scores, temperature=temperature)
            if bet_type == "trio":
                probs = pb.trio_probabilities(strengths)
                odds = race.trio_odds
                result_key = tuple(sorted(race.result_order[:3]))
            else:
                probs = pb.trifecta_probabilities(strengths)
                odds = race.trifecta_odds
                result_key = tuple(race.result_order[:3])

            bets = bt.select_ev_bets(
                probs, odds,
                ev_threshold=ev_threshold,
                stake_per_bet=stake_per_bet,
                max_bets=max_bets,
            )
            if bets:
                spent, ret = bt.settle(bets, result_key)  # type: ignore[arg-type]
                res.n_bet_races += 1
                res.n_bets += len(bets)
                res.n_hits += sum(1 for b in bets if b.combo == result_key)
                res.spent += spent
                res.returned += ret
                res.pnl_history.append(res.returned - res.spent)

        # --- 履歴更新(このレースの結果を各馬に追記。着順は馬番→順位)---
        pos_of = {um: i + 1 for i, um in enumerate(race.result_order)}
        for e in race.entries:
            rec = iv.RunRecord(
                date=race.date,
                place=race.place,
                distance=race.distance,
                field_size=race.field_size,
                finish_pos=pos_of.get(e.num(), race.field_size),
                jockey=e.jockey,
                trainer=e.trainer,
            )
            history.setdefault(e.horse_id, []).insert(0, rec)  # 先頭=最新

    return res
