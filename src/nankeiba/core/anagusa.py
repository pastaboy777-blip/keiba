"""穴ぐさ流・条件フィルタ器（サラブレ「穴ぐさ」の核＝出現率70%の手口を移植）。

穴ぐさの主菜は **「過去走を"軸"で絞り込んだ部分集合で好走歴を提示する」** こと
（「芝1400ｍだと③③①着」「中6週以上だと②①①着」）。負けた凡走を無視して、
**今日の条件に一致するスライスでこの馬が実は走れている**ことを示す。

ここではその機械を実装する:
  1. 馬の過去走(RunRecord)を、今日の出走条件に関係する各"軸"で部分集合化する。
     軸 = 距離 / コース(場) / 芝ダ / 馬場(良・道悪) / 出走間隔バケット / 頭数帯。
  2. **今日の値に一致するスライスだけ**を候補にする（＝「今日の条件だと」の再現）。
  3. 各スライスの複勝率(3着内率)を測り、馬自身の全体baselineを上回るものを
     「穴ぐさ角度(AngleHit)」として、複勝率×サンプル数の順で返す。

これは interval.py の perf_by_bucket（間隔軸だけの相対成績）を全軸へ一般化したもの。

⚠️ 正直な注意（CLAUDE.md rule4）: これは後方視の部分集合で、軸の選び方でいくらでも
   良く見せられる（チェリーピック）。穴ぐさ自身 複勝率の平均は38.6%＝4〜5番人気水準で、
   単体で買える根拠ではない。**「複数角度が今日の条件で重なる」ことに価値**があり、
   採用は out-of-sample の複勝回収を測ってから。依存ライブラリなし。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .interval import RunRecord, interval_bucket

# 3着内＝複勝圏（穴ぐさは「③着以内」を好走の基準に使う）
FUKUSHO = 3

# 距離帯（延長短縮をまたがない大まかな括り）
_DIST_BANDS = [
    (1200, "スプリント(〜1200)"),
    (1400, "短距離(〜1400)"),
    (1800, "マイル〜中距離(〜1800)"),
    (2200, "中距離(〜2200)"),
    (9999, "長距離(2200〜)"),
]

# 頭数帯
_FIELD_BANDS = [
    (10, "少頭数(〜10)"),
    (14, "中頭数(11〜14)"),
    (99, "多頭数(15〜)"),
]


def _dist_band(d: int | None) -> str | None:
    if d is None:
        return None
    for up, label in _DIST_BANDS:
        if d <= up:
            return label
    return None


def _field_band(n: int | None) -> str | None:
    if n is None:
        return None
    for up, label in _FIELD_BANDS:
        if n <= up:
            return label
    return None


def _baba_group(baba: str | None) -> str | None:
    """馬場を『良』/『道悪』の2群に畳む（穴ぐさの良／道悪の使い分けに合わせる）。"""
    if not baba:
        return None
    head = baba[0]
    if head in ("良", "稍", "重", "不"):
        return "良" if head == "良" else "道悪"
    return None


def _circled(pos: int) -> str:
    """着順を丸囲み数字へ（①〜⑳、それ以外は素の数字）。穴ぐさ体裁の再現。"""
    if 1 <= pos <= 20:
        return "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"[pos - 1]
    return str(pos)


@dataclass(frozen=True)
class Condition:
    """今日の出走条件（この条件に一致する過去スライスを探す）。"""

    place: str | None = None
    distance: int | None = None
    surface: str | None = None          # '芝'/'ダ'
    baba: str | None = None             # '良'/'稍'/'重'/'不'
    days_since_last: int | None = None  # 出走間隔[日]
    field_size: int | None = None


@dataclass
class AngleHit:
    axis: str                 # 軸名（例 '距離' '馬場' '間隔'）
    value: str                # 今日の該当値（例 '芝1400' '道悪'）
    n: int                    # そのスライスの走数
    top3: int                 # うち3着内
    rate: float               # 複勝率(0〜1)
    finishes: list[int]       # 着順リスト（新しい順）
    lift: float               # 馬baselineからのリフト(rate - baseline)

    def record_str(self) -> str:
        """『③③①着』のような丸囲み着順表記。"""
        return "".join(_circled(p) for p in self.finishes) + "着"

    def describe(self) -> str:
        return (f"{self.value}だと{self.record_str()}"
                f"（複勝率{self.rate*100:.0f}% {self.top3}/{self.n}）")


@dataclass
class Anagusa:
    baseline: float               # 馬の全体複勝率
    n_runs: int
    hits: list[AngleHit] = field(default_factory=list)
    score: float = 0.0            # 穴ぐさ総合スコア（高いほど今日の条件が向く）

    @property
    def best(self) -> AngleHit | None:
        return self.hits[0] if self.hits else None

    def lines(self, k: int = 3) -> list[str]:
        return [h.describe() for h in self.hits[:k]]


def _slice_stats(runs: Sequence[RunRecord]) -> tuple[int, int, list[int]]:
    finishes = [r.finish_pos for r in runs]
    top3 = sum(1 for p in finishes if p <= FUKUSHO)
    return len(finishes), top3, finishes


def _axis_value(r: RunRecord, axis: str):
    """過去走 r の、指定軸での分類値。None は対象外。"""
    if axis == "距離":
        return f"{r.surface or ''}{r.distance}" if r.distance else None
    if axis == "距離帯":
        b = _dist_band(r.distance)
        return f"{r.surface or ''}{b}" if b else None
    if axis == "コース":
        return f"{r.place}{r.surface or ''}" if r.place else None
    if axis == "芝ダ":
        return r.surface
    if axis == "馬場":
        return _baba_group(r.baba)
    if axis == "間隔":
        b = interval_bucket(r.days_since_last)
        return b if b != "unknown" else None
    if axis == "頭数":
        return _field_band(r.field_size)
    return None


def _today_value(cond: Condition, axis: str):
    if axis == "距離":
        return f"{cond.surface or ''}{cond.distance}" if cond.distance else None
    if axis == "距離帯":
        b = _dist_band(cond.distance)
        return f"{cond.surface or ''}{b}" if b else None
    if axis == "コース":
        return f"{cond.place}{cond.surface or ''}" if cond.place else None
    if axis == "芝ダ":
        return cond.surface
    if axis == "馬場":
        return _baba_group(cond.baba)
    if axis == "間隔":
        b = interval_bucket(cond.days_since_last)
        return b if b != "unknown" else None
    if axis == "頭数":
        return _field_band(cond.field_size)
    return None


# 評価する軸（穴ぐさ出現率の高い順に並べる：距離・コース・馬場・間隔・頭数）
_AXES = ["距離", "距離帯", "コース", "芝ダ", "馬場", "間隔", "頭数"]


def analyze(
    runs: Sequence[RunRecord],
    cond: Condition,
    *,
    min_n: int = 2,
    min_lift: float = 0.0,
) -> Anagusa:
    """過去走と今日の条件から、穴ぐさ風の「今日の条件だと走れている」角度を抽出。

    - min_n:    スライスの最小走数（小さすぎるサンプルを弾く）
    - min_lift: baselineからの複勝率リフトの下限（0＝baseline以上なら採用）
    """
    runs = [r for r in runs if r.finish_pos and r.field_size]
    n = len(runs)
    if n == 0:
        return Anagusa(baseline=0.0, n_runs=0)
    base_top3 = sum(1 for r in runs if r.finish_pos <= FUKUSHO)
    baseline = base_top3 / n

    hits: list[AngleHit] = []
    seen_values: set[str] = set()
    for axis in _AXES:
        tv = _today_value(cond, axis)
        if tv is None:
            continue
        sub = [r for r in runs if _axis_value(r, axis) == tv]
        cnt, top3, finishes = _slice_stats(sub)
        if cnt < min_n:
            continue
        rate = top3 / cnt
        lift = rate - baseline
        if lift < min_lift:
            continue
        # 同一値の重複（距離と距離帯が同義になる等）を軽く抑制
        key = f"{axis}:{tv}"
        if key in seen_values:
            continue
        seen_values.add(key)
        hits.append(AngleHit(axis=axis, value=tv, n=cnt, top3=top3,
                             rate=rate, finishes=finishes, lift=lift))

    # 複勝率 → サンプル数 → リフト の順で強い角度を上に
    hits.sort(key=lambda h: (h.rate, h.n, h.lift), reverse=True)

    # 総合スコア: 上位角度のリフトをサンプル数で加重（穴の「今日は向く」度）
    score = 0.0
    for h in hits[:4]:
        score += h.lift * min(h.n, 5) / 5.0
    return Anagusa(baseline=baseline, n_runs=n, hits=hits, score=round(score, 3))
