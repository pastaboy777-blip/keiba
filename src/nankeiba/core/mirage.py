"""見かけ倒し指数（mirage）検知。

高い指数が「今日のコース（＝当地）の実績」で裏付けられているかを判定する。
指数を押し上げている好走が **中央(JRA)や他場・他距離の速い時計**由来で、
当地の実績がそれに伴っていない場合、その指数は本番で飛びやすい＝“見かけ倒し”。

実例:
  ・大井7R アリステア +58 → 4着（好指数は中央Ｊ新潟/中山の時計、大井は前走13着）
  ・園田11R ナムラジミー +91 → 4着（別条件の高指数）

判定材料（RunRecordから）:
  ・最高指数を出した過去走の place が今日と違う / 中央(Ｊ〜)か
  ・当地(place)での自己ベスト指数と、頭の指数の乖離
  ・当地の距離帯での実績有無

依存ライブラリなし。
"""

from __future__ import annotations

from dataclasses import dataclass

from .hindex import SpeedIndexModel
from .interval import RunRecord


def is_central(place: str | None) -> bool:
    """中央(JRA)開催か。楽天の馬柱では中央は 'Ｊ東京' 'Ｊ中山' 等（全角Ｊ接頭）。"""
    if not place:
        return False
    return place[0] in ("Ｊ", "J")


@dataclass
class Mirage:
    level: int                 # 0=問題なし 1=要注意 2=見かけ倒し
    tag: str                   # 表示用（''/'△要注意'/'⚠️見かけ倒し'）
    reasons: list[str]
    head_idx: float            # 指数を支える最高指数
    same_place_best: float | None   # 当地の自己ベスト指数

    def __bool__(self) -> bool:
        return self.level > 0


def detect(history: list[RunRecord], model: SpeedIndexModel, place: str,
           distance: int, *, lookback: int = 10, gap_warn: float = 8.0) -> Mirage:
    """1頭の履歴から見かけ倒し判定を返す。"""
    scored = [(r, model.index(r)) for r in history[:lookback]]
    scored = [(r, ix) for r, ix in scored if ix is not None]
    if not scored:
        return Mirage(0, "", [], 0.0, None)

    scored.sort(key=lambda x: -x[1])
    best_run, head = scored[0]
    same = [ix for r, ix in scored if r.place == place]
    same_best = max(same) if same else None

    level = 0
    reasons: list[str] = []

    if is_central(best_run.place):
        level = 2
        reasons.append(f"最高指数が中央({best_run.place})の時計")
    elif best_run.place != place:
        level = max(level, 1)
        reasons.append(f"最高指数が他場({best_run.place})の時計")

    if same_best is None:
        level = max(level, 2)
        reasons.append(f"当地({place})の実績なし")
    elif head - same_best >= gap_warn:
        level = max(level, 1)
        reasons.append(f"当地ベスト{same_best:+.0f}に対し頭でっかち(差{head - same_best:+.0f})")

    tag = "" if level == 0 else ("⚠️見かけ倒し" if level >= 2 else "△要注意")
    return Mirage(level, tag, reasons, head, same_best)
