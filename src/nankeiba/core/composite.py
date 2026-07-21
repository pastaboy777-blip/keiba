"""総合指数 = スピード指数(素) + 展開補正 ± 馬場補正。

素のスピード指数(hindex)は「タイムの速さ」だけを見る。実戦では同じ時計でも
その日の展開(前残りか差し有利か)と馬場適性で価値が変わる。ここでは:

  総合指数 = 素指数 + 展開補正(脚質×ペースバイアス) + 馬場補正(馬場適性)

を計算する。補正はいずれも数点規模で、素指数の序列を土台にしつつ、展開・馬場が
噛み合う馬を押し上げ、噛み合わない馬を割り引く。

依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .interval import RunRecord
from .hindex import normalize_going
from . import pace as pc
from . import summary as sm


# 補正の大きさ(点)。素指数レンジ(概ね -30〜+20)に対して控えめに効かせる。
PACE_PTS = 3.0        # 脚質×ペースの最大加点
GOING_PTS = 4.0       # 馬場適性の最大加点


FRONT_STYLES = {"逃げ", "先行"}
CLOSER_STYLES = {"差し", "追込"}


def dominant_style(runs: Sequence[RunRecord], *, lookback: int = 4) -> str | None:
    """直近の通過順から脚質(逃げ/先行/差し/追込)を判定する。

    3コーナー(無ければ最初のコーナー)の位置を頭数で正規化した平均で決める。
    通過順データが無ければ None。
    """
    ratios: list[float] = []
    for r in list(runs)[:lookback]:
        cps = [c for c in (r.corner_pos or []) if c and c > 0]
        if not cps or not r.field_size:
            continue
        c3 = cps[-2] if len(cps) >= 2 else cps[-1]
        ratios.append(c3 / max(2, r.field_size))
    if not ratios:
        return None
    avg = sum(ratios) / len(ratios)
    if avg <= 0.15:
        return "逃げ"
    if avg <= 0.40:
        return "先行"
    if avg <= 0.70:
        return "差し"
    return "追込"


@dataclass
class PaceContext:
    """今日のレースの展開・馬場コンテキスト。"""
    front_bias: int          # +1=前有利, 0=中立, -1=差し有利
    going: str | None        # 良/稍/重/不

    @classmethod
    def from_grid(cls, grid: pc.PaceGrid, going: str | None) -> "PaceContext":
        n = grid.front_count()
        wet = (normalize_going(going) or "") in ("重", "不")
        # 前(5着内の逃げ・先行)が少ないほど前残り。重・不良は前有利側へシフト。
        if n <= 2:
            bias = 1
        elif n >= 5:
            bias = -1
        else:
            bias = 0
        if wet:
            bias = min(1, bias + 1)      # 湿走は前残り方向へ
        return cls(front_bias=bias, going=normalize_going(going))


def pace_bonus(style: str | None, ctx: PaceContext) -> float:
    """脚質とペースバイアスの噛み合いによる加点(±PACE_PTS)。"""
    if style is None or ctx.front_bias == 0:
        return 0.0
    if style in FRONT_STYLES:
        return PACE_PTS * ctx.front_bias      # 前有利(+)なら前脚質は加点
    if style in CLOSER_STYLES:
        return -PACE_PTS * ctx.front_bias     # 前有利なら差し脚質は減点
    return 0.0


def going_bonus(apt: sm.GoingAptitude | None, going: str | None) -> float:
    """馬場適性(今回の馬場での複勝率)による加点(±GOING_PTS)。

    今回が渋った馬場(稍/重/不)のときのみ効かせる(良は大半の走が該当し差が出にくい)。
    複勝率 0.33 を基準に、上振れ・下振れを点数化。実績が無い馬は0(中立)。
    """
    if apt is None or apt.n == 0:
        return 0.0
    if (normalize_going(going) or "") not in ("稍", "重", "不"):
        return 0.0
    if apt.in3_rate is None:
        return 0.0
    val = GOING_PTS * (apt.in3_rate - 0.33) / 0.67   # 複勝率100%で+GOING、0%で約-1.6
    return max(-GOING_PTS, min(GOING_PTS, round(val, 1)))


@dataclass
class Composite:
    base: float | None       # 素指数(近5走以内の最高)
    style: str | None
    pace: float              # 展開補正
    going: float             # 馬場補正
    total: float | None      # 総合指数

    def breakdown(self) -> str:
        if self.base is None:
            return "指数なし"
        parts = [f"{self.base:+.0f}"]
        if self.pace:
            parts.append(f"展開{self.pace:+.0f}")
        if self.going:
            parts.append(f"馬場{self.going:+.0f}")
        return " ".join(parts)


def composite_index(
    base_index: float | None,
    runs: Sequence[RunRecord],
    ctx: PaceContext,
    apt: sm.GoingAptitude | None,
) -> Composite:
    """1頭分の総合指数を計算する。"""
    style = dominant_style(runs)
    pb = pace_bonus(style, ctx)
    gb = going_bonus(apt, ctx.going)
    total = None if base_index is None else round(base_index + pb + gb, 0)
    return Composite(base=base_index, style=style, pace=pb, going=gb, total=total)
