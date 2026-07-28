"""前走のレースレベル（メンバーの格）— 着順の「言い訳」を測る指標。

ユーザー発案（2026-07-28）:「前走レベルを大切にしたい。それを指数化して」

定義:
    そのレースに出走した馬たちの **そのレースより前の1着経験率** の中央値。
    対象馬自身は除いて計算する。

なぜこの定義か（他の2案は実測で棄却した）:
  ✕ 「出走馬がその後どれだけ走ったか（複勝率）」 … lift 0.96〜1.02 で真っ平ら。
      複勝率はどのレースでも3割前後に潰れるので、格の違いが数字に出ない。
      さらに前走が先週だと「その後」がほぼ空で、実戦で一番使いたい場面で使えない。
  ✕ 「1〜3着馬のその後の複勝率」 … lift 0.98〜1.04。同じ理由で棄却。
  ○ **過去の実績だけで決まる**ので前走が直近でも計算でき、分布も潰れない。

実測（南関 / **前走7着以下** 31,867組・その層の次走複勝率 14.9% ＝ lift 1.00）:
    格 0.00〜  n=11,349  14.2%  lift 0.95
    格 0.08〜  n=12,585  14.9%  lift 1.00
    格 0.16〜  n=5,734   15.0%  lift 1.01
    格 0.24〜  n=1,228   16.2%  lift 1.09
    格 0.32〜  n=971     20.9%  lift **1.40**

⚠️ **前走で好走した馬には効かない。** 前走1-3着の層では 0.96/1.02/1.08/0.97 と
   バラつくだけ。これは「着順が悪かったことの言い訳」を測る指標であって、
   強い馬を見つける指標ではない。

`adjust.revenge()`（前走大敗×前々のポジション）とは**独立**に効く（30,322組）:

    ハイレベル  前々   組       次走複勝  lift
       ○      ○     483    24.8%   1.67
       ×      ○    7096    20.0%   1.35
       ○      ×    1666    16.0%   1.08
       ×      ×   21077    12.8%   0.86

  → 「相手が強かったか（格）」と「勝負になっていたか（位置取り）」は別の情報。
    両方揃った馬が最も巻き返す。両方ダメな層が **ただ弱いだけ** の 0.86。

⚠️ 収録範囲: `data/race_grade.json` はキャッシュ済みのレースぶんだけ。
   中央や未取得の地方場が前走だと `None` を返す。**None を「低レベル」と
   読み替えてはいけない**（測れていないだけ）。

依存ライブラリなし。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .datapath import data_path

_PATH = data_path("race_grade.json")

#: この値以上を「ハイレベル戦」とみなす（実測で lift が跳ねる境界）
HIGH = 0.32
#: 格の計算に必要な他馬の最少頭数
MIN_OTHERS = 4


def _load() -> dict[str, dict[str, float]]:
    if _PATH.exists():
        try:
            return json.loads(_PATH.read_text(encoding="utf-8"))
        except Exception:                          # noqa: BLE001
            pass
    return {}


TABLE = _load()


@dataclass
class Level:
    grade: float            # メンバーの格（過去1着率の中央値）
    n_others: int           # 計算に使った他馬の頭数
    key: str

    @property
    def is_high(self) -> bool:
        return self.grade >= HIGH

    def label(self) -> str:
        if self.grade >= HIGH:
            return "ハイレベル戦"
        if self.grade >= 0.24:
            return "やや骨っぽい"
        return "平凡"

    def summary(self) -> str:
        return f"前走の格 {self.grade:.2f}（{self.label()}・他{self.n_others}頭）"


def level_of(date: str | None, place: str | None, distance: int | None,
             exclude: str | None = None,
             *, table: dict | None = None) -> Level | None:
    """そのレースのメンバーの格。収録が無ければ None（＝低レベルではない）。"""
    t = TABLE if table is None else table
    if not date or not place or not distance:
        return None
    key = f"{date}|{place}|{distance}"
    cell = t.get(key)
    if not cell:
        return None
    vals = sorted(v for nm, v in cell.items() if nm != exclude)
    if len(vals) < MIN_OTHERS:
        return None
    return Level(grade=round(vals[len(vals) // 2], 4), n_others=len(vals), key=key)


def prev_level(history, name: str | None = None, *, table: dict | None = None):
    """馬柱の先頭（＝前走）のレースレベル。"""
    if not history:
        return None
    p = history[0]
    return level_of(p.date, p.place, p.distance, name, table=table)
