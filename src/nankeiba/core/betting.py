"""期待値(EV)ベースの買い目選定。

回収率で勝つ唯一の道は「モデル確率 × オッズ が控除率を超える買い目だけ買う」こと。
EV = 的中確率 × オッズ。EV > ev_threshold の組み合わせのみ購入対象とする。
ev_threshold = 1.0 が損益分岐、1.1 なら 10% のマージンを要求(過信への保険)。

オプションでケリー基準による配分も提供する。

依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


Combo = tuple[int, ...]


@dataclass
class Bet:
    combo: Combo
    prob: float
    odds: float
    ev: float
    stake: float


def select_ev_bets(
    probs: Mapping[Combo, float],
    odds: Mapping[Combo, float],
    *,
    ev_threshold: float = 1.1,
    stake_per_bet: float = 100.0,
    max_bets: int | None = None,
    kelly: bool = False,
    bankroll: float = 10000.0,
    kelly_fraction: float = 0.25,
) -> list[Bet]:
    """期待値プラスの買い目を選ぶ。

    Args:
        probs: 組み合わせ -> モデル確率
        odds:  組み合わせ -> オッズ(払戻倍率。的中で stake*odds が戻る)
        ev_threshold: この EV を超えた買い目だけ購入
        stake_per_bet: ケリー無効時の1点あたり購入額
        max_bets: 購入点数の上限(EV 降順で上位のみ)
        kelly: True ならケリー基準(分数ケリー)で配分
        bankroll: ケリー時の総資金
        kelly_fraction: 分数ケリー係数(0.25=クォーターケリー)

    Returns:
        購入する Bet のリスト(EV 降順)。
    """
    candidates: list[Bet] = []
    for combo, p in probs.items():
        o = odds.get(combo)
        if o is None or o <= 0:
            continue
        ev = p * o
        if ev <= ev_threshold:
            continue
        candidates.append(Bet(combo=combo, prob=p, odds=o, ev=ev, stake=0.0))

    candidates.sort(key=lambda b: b.ev, reverse=True)
    if max_bets is not None:
        candidates = candidates[:max_bets]

    for b in candidates:
        if kelly:
            # ケリー: f* = (p*(odds-1) - (1-p)) / (odds-1) = (p*odds - 1)/(odds-1)
            b_odds = b.odds - 1.0
            f = (b.prob * b.odds - 1.0) / b_odds if b_odds > 0 else 0.0
            f = max(0.0, f) * kelly_fraction
            b.stake = round(bankroll * f, 1)
        else:
            b.stake = stake_per_bet
    # ステークが 0 のものは除外
    return [b for b in candidates if b.stake > 0]


def settle(bets: list[Bet], result: Combo) -> tuple[float, float]:
    """確定結果に対して購入分を精算する。

    Args:
        bets:   購入した Bet 群
        result: 的中組み合わせ(三連複は昇順タプル、三連単は着順タプル)
    Returns:
        (総購入額, 総払戻額)
    """
    spent = sum(b.stake for b in bets)
    ret = 0.0
    for b in bets:
        if b.combo == result:
            ret += b.stake * b.odds
    return spent, ret
