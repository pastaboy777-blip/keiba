"""ローテーション由来のフラグ — 叩き何戦目 / 他場からの遠征。

ユーザー指定のファクター（2026-07-28）:
  ・**叩き3戦目**が良い
  ・**船橋からの遠征馬**が良い

叩き何戦目:
    直近から遡り、**60日を超える間隔**が出たところを「休み明け」とみなして数える。
    今走を含めた本数を返す（休み明け初戦＝1、次＝2、その次＝3）。

遠征:
    前走の開催場が今走と違えば遠征。南関4場は行き来が多いので、
    「どこから来たか」を場名で持つ。

依存ライブラリなし。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

#: これを超える間隔があったら「休み明け」とみなす[日]
LAYOFF_DAYS = 60


def _d(s: str) -> date:
    y, m, dd = (int(x) for x in s.split("-"))
    return date(y, m, dd)


@dataclass
class Rotation:
    nth: int                    # 叩き何戦目（今走を含む。0=初出走）
    days: int | None            # 前走からの間隔[日]
    from_place: str | None      # 前走の開催場（今走と違えば遠征元）
    away: bool                  # 他場からの遠征か

    def label(self) -> str:
        p = []
        if self.nth:
            p.append(f"叩き{self.nth}戦目")
        if self.days is not None:
            p.append(f"中{self.days}日")
        if self.away and self.from_place:
            p.append(f"{self.from_place}から遠征")
        return " / ".join(p)


def rotation(history, today: str, place: str | None = None) -> Rotation:
    """馬柱と今走の日付・場から、叩き何戦目・間隔・遠征元を返す。"""
    if not history:
        return Rotation(nth=0, days=None, from_place=None, away=False)
    t = _d(today)
    prev = history[0]
    days = (t - _d(prev.date)).days

    nth = 1
    if days <= LAYOFF_DAYS:
        nth = 2
        for a, b in zip(history, history[1:]):
            if (_d(a.date) - _d(b.date)).days > LAYOFF_DAYS:
                break
            nth += 1

    return Rotation(nth=nth, days=days, from_place=prev.place,
                    away=bool(place and prev.place and prev.place != place))


def is_nth(history, today: str, n: int) -> bool:
    """叩き n 戦目か。"""
    return rotation(history, today).nth == n


def from_place(history, today: str, place: str, src: str) -> bool:
    """`src` の競馬場からの遠征か（例: 船橋 → 川崎）。"""
    r = rotation(history, today, place)
    return r.away and r.from_place == src
