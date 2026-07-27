"""当日の馬場差（トラックバイアス）の実測と、速度ショック基準への反映。

par（場×距離の基準 s/F）は**過去の中央値**なので、その日の馬場が速ければ
全レースが par より速く決まる。この差分を **当日の馬場差 offset [s/F]** として測り、
`shock.detect()` の基準テーブルを補正する。

⚠️ **基準は「勝ち馬 par」を使う（`data/par_win.json`）。**
`shock.PAR_PACE`（= `data/par_pace.json`）は**全出走馬**の中央値で、そちらは
「その馬自身の前走タイム」と比べる速度ショック用。当日の馬場差は**勝ちタイム**から
測るので、勝ち馬どうしで比べないと釣り合わない。
実際 2026-07-27 の川崎で取り違えて、常に約 -0.19 s/F の下駄を履いていた:
    勝ちタイム 13.157 s/F を 全馬par 13.443 にぶつけて **-0.29「高速馬場」** と誤判定
    → 正しくは 勝ち馬par 13.257 との差 **-0.10（ほぼ標準）**
このせいで ⚠️見かけ倒しの割引を 0.3 まで緩め、4Rで本来出ない🚀を2頭に付けていた。
両方のテーブルは `scripts/build_par_pace.py` が同時に生成する。

しくみ:
  ・高速馬場では「今走の想定ペース」が par より速くなるので、
    前走が緩かった馬はより大きな速度ショックを受ける＝**消しが強まる**。
  ・逆に「⚠️見かけ倒し（別条件の速い時計で指数が水増し）」は、
    **当日が高速馬場ならその速い時計が通用する**ため、割引を弱めるべき。

レースが進むほど実測本数が増えて精度が上がるので、**開催中に随時呼び直す**設計。
依存ライブラリなし。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from . import shock
from .datapath import data_path

# 判定しきい値（s/F）
FAST = -0.10        # これ以下なら高速馬場
SLOW = 0.10         # これ以上なら時計のかかる馬場

#: 勝ち馬のみで測った par。当日の馬場差の基準はこちら。
_WIN_PATH = data_path("par_win.json")


def _load_win_par() -> dict[str, float]:
    if _WIN_PATH.exists():
        try:
            return json.loads(_WIN_PATH.read_text(encoding="utf-8"))
        except Exception:                      # noqa: BLE001
            pass
    return {}


PAR_WIN = _load_win_par()


@dataclass
class TrackBias:
    offset: float                      # 当日の馬場差 [s/F]（マイナス＝速い）
    n_races: int                       # 実測に使ったレース数
    samples: list[tuple[int, float]] = field(default_factory=list)  # [(R, 差)]

    @property
    def label(self) -> str:
        if self.offset <= FAST:
            return "高速馬場"
        if self.offset >= SLOW:
            return "時計のかかる馬場"
        return "標準"

    @property
    def is_fast(self) -> bool:
        return self.offset <= FAST

    @property
    def drift(self) -> float | None:
        """開催前半 → 後半の変化量 [s/F]。プラスなら**遅くなってきている**。

        散水・砂の掘れ・気温で、同じ日でも馬場は動く。実測 2026-07-27 川崎:
        1R/2R が -0.10 だったのに 4R/5R は +0.27/+0.29 と、日中で 0.38 も動いた。
        1日の平均 +0.08 を残りのレースに当てるのは実態と合わない。
        """
        if self.n_races < 4:
            return None
        v = [d for _, d in self.samples]
        h = len(v) // 2
        return round(sum(v[h:]) / len(v[h:]) - sum(v[:h]) / h, 3)

    def summary(self) -> str:
        s = (f"当日の馬場差 {self.offset:+.2f} s/F（{self.n_races}R実測）"
             f" → {self.label}")
        d = self.drift
        if d is not None and abs(d) >= 0.15:
            s += f"　⚠️日中で{'遅く' if d > 0 else '速く'}なっている（{d:+.2f}）"
        return s

    def adjusted_par(self, table: dict[str, float] | None = None) -> dict[str, float]:
        """速度ショック用に補正した par テーブル。"""
        t = table if table is not None else shock.PAR_PACE
        return {k: v + self.offset for k, v in t.items()}


def measure(results: list[dict], *, table: dict[str, float] | None = None,
            place: str | None = None, recent: int | None = None) -> TrackBias:
    """終わったレースから当日の馬場差を測る。

    results の各要素: {"race_no", "place", "distance", "win_time"}
      win_time … 勝ち馬の走破タイム[秒]
    table を省くと **勝ち馬 par**(`PAR_WIN`) を使う。全馬 par を渡してはいけない
    （モジュール冒頭の警告を参照）。
    par が引けないレース（未登録の距離など）は自動的に除外する。

    recent に本数を渡すと、**直近その本数だけ**で offset を出す（`samples` は
    全レースぶん残るので `drift` は引き続き見られる）。日中で馬場が動く日は、
    これから走るレースに当てる基準としてこちらが実態に近い。
    """
    base = table if table is not None else (PAR_WIN or None)
    samples: list[tuple[int, float]] = []
    for r in results:
        dist = r.get("distance")
        t = r.get("win_time")
        pl = r.get("place") or place
        if not dist or not t or not pl:
            continue
        par = shock.par_pace(pl, dist, base)
        if par is None:
            continue
        sf = t / (dist / 200.0)
        samples.append((r.get("race_no") or 0, round(sf - par, 3)))
    if not samples:
        return TrackBias(offset=0.0, n_races=0)
    use = samples[-recent:] if recent else samples
    off = sum(d for _, d in use) / len(use)
    return TrackBias(offset=round(off, 3), n_races=len(use), samples=samples)


def mirage_discount(bias: TrackBias) -> float:
    """⚠️見かけ倒しの割引率（1.0＝通常どおり割り引く / 0.0＝割引なし）。

    高速馬場では「別条件の速い時計」がそのまま通用するので割引を弱める。
    ⚠️実測での裏付けはまだ1日ぶん（2026-07-27 川崎1R）しかない。
    **暫定の運用ルールであり、検証が必要。**
    """
    if bias.offset <= -0.20:
        return 0.3          # 明確な高速馬場 → ほぼ割り引かない
    if bias.offset <= FAST:
        return 0.6
    if bias.offset >= SLOW:
        return 1.2          # 時計がかかる日は水増し時計がより無意味
    return 1.0


def detect_with_bias(history, place, distance, bias: TrackBias):
    """当日の馬場差で補正した速度ショック判定。"""
    return shock.detect(history, place, distance, table=bias.adjusted_par())
