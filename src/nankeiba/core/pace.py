"""展開予想「3走以内の通過順」グリッド。

新聞の展開予想を、各馬の過去3走以内のコーナー通過順から 6 マスに振り分けて
再現する。仕様(新聞の解説より):

  まず各走を着順で 5着以内 / 6着以降 に分ける。
    ・5着以内だった走 … 逃げ / 3・4角3番手以内 / 4角3番手以内 / 4角4番手以降
    ・6着以降だった走 … 逃げ / 3・4角3番手以内
  合計 6 パターン(=6マス)。

  - 同じ馬が複数回同じマスに出ても表記は1つだけ(集合)。
  - 並びは馬番順(表記順に評価の上下は無い)。
  - 1マス最大10頭。超える場合はそのマスは表記しない(混戦=読み材料にならない)。

使い方(新聞の解説):
  能力上位馬と同じマスに入った他馬は高確率で潰される。相手は別マスから拾う。
  左2マス(=逃げ・先行で5着以内)が手薄なら前が止まらず人気薄も残りやすい。

依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .interval import RunRecord


# --- 6 マスの定義(左→右の表示順)---
# key, ラベル, 着順条件が5着以内か
BUCKETS: list[tuple[str, str, bool]] = [
    ("in5_nige",   "逃げ",          True),
    ("in5_senko",  "3・4角3番手以内", True),
    ("in5_sashi",  "4角3番手以内",    True),
    ("in5_oikomi", "4角4番手以降",    True),
    ("out_nige",   "逃げ",          False),
    ("out_senko",  "3・4角3番手以内", False),
]
BUCKET_KEYS = [b[0] for b in BUCKETS]
IN5_KEYS = [b[0] for b in BUCKETS if b[2]]
OUT_KEYS = [b[0] for b in BUCKETS if not b[2]]

MAX_PER_CELL = 10       # これを超えるマスは表記しない
LOOKBACK_RUNS = 3       # 「3走以内」


def _corner_positions(corner_pos: Sequence[int] | None):
    """コーナー通過順(前→後)から (先頭コーナー, 3角, 4角) の位置を返す。

    corner_pos は各コーナーの通過順位。コーナー数が少ない場合は最後の要素で代用。
    値が無ければ None。
    """
    cps = [c for c in (corner_pos or []) if c and c > 0]
    if not cps:
        return None
    c4 = cps[-1]                       # 最終(4)コーナー
    c3 = cps[-2] if len(cps) >= 2 else cps[-1]   # 3コーナー
    c_first = cps[0]                   # 最初のコーナー
    return c_first, c3, c4


def classify_run(rec: RunRecord) -> str | None:
    """1走を 6 マスのいずれかに分類する。該当なし・データ無しは None。

    - 逃げ    : 最初 or 3角で1番手(ペースを作った)
    - 先行good: (5着以内) 3角・4角ともに3番手以内
    - 差し    : (5着以内) 4角3番手以内・3角は4番手以降
    - 追込    : (5着以内) 4角4番手以降
    - 6着以降 : 逃げ・先行(3・4角3番手以内)のみ。後方凡走は掲載しない。
    """
    cp = _corner_positions(rec.corner_pos)
    if cp is None:
        return None
    c_first, c3, c4 = cp
    nige = (c3 == 1) or (c_first == 1)
    senko = (c3 <= 3) and (c4 <= 3)          # 3・4角ともに3番手以内
    sashi = (c4 <= 3) and (c3 >= 4)          # 4角のみ3番手以内
    in5 = rec.finish_pos <= 5

    if nige:
        return "in5_nige" if in5 else "out_nige"
    if senko:
        return "in5_senko" if in5 else "out_senko"
    if not in5:
        return None                          # 6着以降で前にいなかった走は対象外
    if sashi:
        return "in5_sashi"
    return "in5_oikomi"                       # 4角4番手以降(c4>=4)


@dataclass
class PaceCell:
    key: str
    label: str
    in5: bool
    umaban: list[int] = field(default_factory=list)   # 馬番順
    overflow: bool = False                             # 10頭超で非表示

    def display(self) -> str:
        if self.overflow:
            return "―"          # 頭数過多で非表示
        if not self.umaban:
            return ""
        return " ".join(str(u) for u in self.umaban)


@dataclass
class PaceGrid:
    cells: dict[str, PaceCell]

    def cell(self, key: str) -> PaceCell:
        return self.cells[key]

    def front_count(self) -> int:
        """左2マス(5着以内の逃げ・先行)の合計頭数。少ないほど前残り想定。"""
        c1, c2 = self.cells["in5_nige"], self.cells["in5_senko"]
        n = (0 if c1.overflow else len(c1.umaban)) + (0 if c2.overflow else len(c2.umaban))
        return n

    def pace_read(self) -> str:
        """前half の手薄さから簡易ペース読みを返す。"""
        n = self.front_count()
        if n <= 2:
            return "前少・前残り想定(人気薄の逃げ先行も一発警戒)"
        if n <= 4:
            return "前やや少・平均〜前残り"
        return "前多数・ハイペース〜差し有利想定"


def build_pace_grid(
    entries: Sequence[tuple[int, Sequence[RunRecord]]],
    *,
    lookback: int = LOOKBACK_RUNS,
    max_per_cell: int = MAX_PER_CELL,
) -> PaceGrid:
    """展開グリッドを組み立てる。

    Args:
        entries: (馬番, その馬の過去走[新しい順]) のリスト。
        lookback: 「n 走以内」を対象にする(既定3)。
    """
    members: dict[str, set[int]] = {k: set() for k in BUCKET_KEYS}
    for umaban, runs in entries:
        for rec in list(runs)[:lookback]:
            key = classify_run(rec)
            if key is not None:
                members[key].add(umaban)

    cells: dict[str, PaceCell] = {}
    for key, label, in5 in BUCKETS:
        nums = sorted(members[key])
        overflow = len(nums) > max_per_cell
        cells[key] = PaceCell(
            key=key, label=label, in5=in5,
            umaban=[] if overflow else nums,
            overflow=overflow,
        )
    return PaceGrid(cells=cells)
