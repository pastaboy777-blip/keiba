"""スマート出馬表（血統ビーム／亀谷敬正）の要素を南関データで再現。

  - テンT (テン持ちタイム): 近走のテン(前半3F)最速タイム。小さいほど先行力・
    速いラップ追走経験。今回出走中の順位も出す。
  - 上がりT (上がり持ちタイム): 近走の上がり3F最速タイム。小さいほど速い末脚経験。
  - ロ (ローテ): 前走→今回の距離変化で 延(延長)/同(同距離)/短(短縮)。

使い方(亀谷式): 差し決着になりそうなレース(展開グリッドが「差し有利想定」)では
上がりT上位が突っ込む。上がりT × 短縮 で人気薄の一発を掬える(雲雀S=3連単117万の例)。

前半3Fは概算(区間ラップが無いため)。あくまで実用重視の参考指標。
依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .interval import RunRecord
from .hindex import estimate_first3f


def rotation(prev_distance: int | None, today_distance: int) -> str:
    """前走距離→今回距離のローテ記号。延/同/短。前走不明は ''。"""
    if not prev_distance or not today_distance:
        return ""
    if today_distance > prev_distance:
        return "延"
    if today_distance < prev_distance:
        return "短"
    return "同"


def ten_time(runs: Sequence[RunRecord], *, lookback: int = 3) -> float | None:
    """近 lookback 走のテン(前半3F概算)の最速[秒]。"""
    best = None
    for r in list(runs)[:lookback]:
        f3 = r.first3f_sec or estimate_first3f(
            r.time_sec, r.distance, last3f_sec=r.last3f_sec,
            corner_pos=r.corner_pos, field_size=r.field_size)
        if f3 is not None and (best is None or f3 < best):
            best = f3
    return round(best, 1) if best is not None else None


def agari_time(runs: Sequence[RunRecord], *, lookback: int = 3) -> float | None:
    """近 lookback 走の上がり3Fの最速[秒]。"""
    vals = [r.last3f_sec for r in list(runs)[:lookback] if r.last3f_sec is not None]
    return round(min(vals), 1) if vals else None


@dataclass
class SmartRow:
    umaban: int
    ten_t: float | None
    agari_t: float | None
    ten_rank: int | None = None       # 今回出走中のテンT順位(速い=1)
    agari_rank: int | None = None     # 今回出走中の上がりT順位(速い=1)
    rot: str = ""                     # 延/同/短

    def fmt(self) -> str:
        t = f"テン{self.ten_t}({self.ten_rank})" if self.ten_t else "テン―"
        a = f"上り{self.agari_t}({self.agari_rank})" if self.agari_t else "上り―"
        r = f" {self.rot}" if self.rot else ""
        return f"{t} {a}{r}"


def smart_table(
    entries: Sequence[tuple[int, Sequence[RunRecord]]],
    today_distance: int,
    *,
    lookback: int = 3,
) -> dict[int, SmartRow]:
    """各馬の テンT/上がりT/ローテ と、場内順位を付けて返す。"""
    rows: dict[int, SmartRow] = {}
    for um, runs in entries:
        runs = list(runs)
        prev = runs[0].distance if runs else None
        rows[um] = SmartRow(
            umaban=um,
            ten_t=ten_time(runs, lookback=lookback),
            agari_t=agari_time(runs, lookback=lookback),
            rot=rotation(prev, today_distance),
        )
    # 場内順位(速い=1)。半数を下回る順位のみ有効にするのは表示側で判断。
    for key, attr in (("ten_t", "ten_rank"), ("agari_t", "agari_rank")):
        ranked = sorted((r for r in rows.values() if getattr(r, key) is not None),
                        key=lambda r: getattr(r, key))
        for i, r in enumerate(ranked):
            setattr(r, attr, i + 1)
    return rows


def agari_t_top(
    entries: Sequence[tuple[int, Sequence[RunRecord]]],
    *,
    lookback: int = 3,
    limit: int = 10,
) -> list[tuple[int, float]]:
    """上がりT上位(速い順)を [(馬番, 上がりT), ...] で返す。"""
    vals = [(um, agari_time(runs, lookback=lookback)) for um, runs in entries]
    vals = [(um, a) for um, a in vals if a is not None]
    vals.sort(key=lambda t: t[1])
    return vals[:limit]
