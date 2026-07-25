"""体感速度ショック（1ハロンあたり秒数の差分）— 除外フィルタ。

仮説（ユーザー発案）: 効くのは「距離の増減」ではなく **馬が実際に感じる1Fあたりの
速度の差分**。前走スローで流れた馬が、今走で1F=1秒速い流れに放り込まれると
ついていけない。距離短縮そのものが効かない理由がこれで説明できる。

  shock = 今走の想定ペース(s/F) − 前走の実ペース(s/F)
      shock < 0 … 今走のほうが速い＝ついていけない（不利）
      shock > 0 … 今走のほうが楽

実測（南関17,539頭走・2026キャッシュ全期間）:
  ・**マイナス側は本物**。shock ≤ -0.6 の複勝率は人気帯で層別しても一貫して低い。
      全体 lift0.44 / 1-3人気 0.92 / 4-6人気 0.76 / **人気薄 0.64**(5.3% vs 8.3%)
      距離短縮組だけに絞っても人気薄 lift0.64 ＝「距離が縮んだから」ではなく
      **速度差の大きさ**が効いている、と確認できた。
  ・**プラス側は交絡でボツ**。shock＞0 は「前走を今日のparより速く走った」＝ただの
      速い馬で、スピード指数の言い換え。人気で層別すると人気薄で lift0.99 に消える
      （市場が織り込み済み）。→ **買い材料には使わない。**

したがって本モジュールは **「消し」専用** として使う。§15の
「指数上位3頭→⚠️見かけ倒し除外→最人気薄を複勝」に、この除外を重ねる用途。

依存ライブラリなし。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .interval import RunRecord

# 実測 par テーブル（(場,距離)→ 1Fあたり秒数の中央値）。data/par_pace.json があれば読む。
_PAR_PATH = Path("data/par_pace.json")

# フォールバック用の代表値（南関ダート）。JSONが無い環境でも動くように。
_PAR_FALLBACK: dict[str, float] = {
    "大井|1200": 12.75, "大井|1400": 12.95, "大井|1600": 13.02,
    "大井|1800": 13.08, "大井|2000": 13.21,
    "川崎|1400": 13.44, "川崎|1500": 13.23, "川崎|1600": 13.33, "川崎|2000": 13.72,
    "船橋|1000": 12.56, "船橋|1200": 12.87, "船橋|1500": 13.36,
    "船橋|1600": 13.13, "船橋|1700": 13.09, "船橋|1800": 13.20,
    "浦和|1300": 13.29, "浦和|1400": 13.06, "浦和|1500": 13.09, "浦和|2000": 13.46,
}


def _load_par() -> dict[str, float]:
    if _PAR_PATH.exists():
        try:
            return json.loads(_PAR_PATH.read_text(encoding="utf-8"))
        except Exception:                      # noqa: BLE001
            pass
    return dict(_PAR_FALLBACK)


PAR_PACE = _load_par()

# 判定しきい値（実測で lift が明確に落ちる境界）
SHOCK_HARD = -0.6      # 大幅に速くなる＝消し
SHOCK_SOFT = -0.2      # やや速い＝注意


def pace_per_furlong(time_sec: float | None, distance: int | None) -> float | None:
    """走破タイムと距離から 1F(200m)あたりの秒数を出す。"""
    if not time_sec or not distance or distance <= 0:
        return None
    return time_sec / (distance / 200.0)


def par_pace(place: str | None, distance: int | None,
             table: dict[str, float] | None = None) -> float | None:
    """(場, 距離) の基準ペース(s/F)。無ければ同じ場の最も近い距離で代用する。"""
    if not place or not distance:
        return None
    t = table if table is not None else PAR_PACE
    key = f"{place}|{distance}"
    if key in t:
        return t[key]
    # 同一場の最近傍距離にフォールバック
    best = None
    for k, v in t.items():
        p, _, d = k.partition("|")
        if p != place or not d.isdigit():
            continue
        gap = abs(int(d) - distance)
        if best is None or gap < best[0]:
            best = (gap, v)
    return best[1] if best and best[0] <= 400 else None


@dataclass
class ShockTag:
    value: float                # shock（＋なら今走のほうが楽）
    level: int                  # 0=問題なし / 1=注意 / 2=消し
    prev_pace: float
    today_pace: float

    @property
    def tag(self) -> str:
        return {2: "🚀速度ショック", 1: "△速い流れ"}.get(self.level, "")

    @property
    def note(self) -> str:
        if self.level == 0:
            return ""
        return (f"前走{self.prev_pace:.2f}s/F → 今走想定{self.today_pace:.2f}s/F "
                f"({self.value:+.2f}s/F)")

    def __bool__(self) -> bool:
        return self.level > 0


def detect(history: list[RunRecord], place: str | None, distance: int | None,
           *, table: dict[str, float] | None = None) -> ShockTag | None:
    """前走との体感速度差から、今走の速度ショックを判定する。

    ⚠️ プラス側（楽になる）は買い材料にしない — 実測で市場に織り込み済みのため、
    level は 0 のままにして「消し」だけを返す。
    """
    today = par_pace(place, distance, table)
    if today is None or not history:
        return None
    prev = history[0]
    pp = pace_per_furlong(prev.time_sec, prev.distance)
    if pp is None:
        return None
    v = today - pp
    level = 2 if v <= SHOCK_HARD else (1 if v <= SHOCK_SOFT else 0)
    return ShockTag(value=round(v, 3), level=level,
                    prev_pace=round(pp, 3), today_pace=round(today, 3))
