"""コンピ風ランク指数（日刊コンピ指数の再現・自前データ版）。

日刊コンピ指数は「レース内で全馬に重複なしの40〜90を割り振るランク指数」。
算出方法は非公開なので、ここでは **うちのスピード指数（絶対値）** を素材に、
コンピと同じ体裁のランク指数へ変換する（再現であって本物ではない）。

設計:
  ・レース内をスピード指数の高い順に並べる。
  ・1位のコンピ値は「2位との差(断トツ度)」で 76〜90 に決める
    （断トツ＝90寄り、混戦＝76寄り）。実コンピの「1強なら高い」性質を模す。
  ・以下は 1位値から 40 まで順位で線形に降ろす（重複なし）。

これで「1位指数の値」「指数の総和」「上位の並び」などコンピ理論の材料を
自前データで検証できる。依存ライブラリなし。
"""

from __future__ import annotations

from dataclasses import dataclass

CONPI_MAX = 90
CONPI_MIN = 40


def to_conpi(indices: dict[int, float]) -> dict[int, int]:
    """{馬番: スピード指数(高いほど強い)} → {馬番: コンピ風値(40〜90)}。"""
    ranked = sorted(indices.items(), key=lambda kv: -kv[1])
    n = len(ranked)
    if n == 0:
        return {}
    if n == 1:
        return {ranked[0][0]: CONPI_MAX}
    gap = ranked[0][1] - ranked[1][1]           # 1位と2位の指数差＝断トツ度
    top = min(CONPI_MAX, max(76, round(78 + gap * 0.4)))
    out: dict[int, int] = {}
    for i, (um, _) in enumerate(ranked):
        if i == 0:
            out[um] = top
        else:
            v = round(top - (top - CONPI_MIN) * i / (n - 1))
            # 重複回避（同値なら1下げる）
            while v in out.values() and v > CONPI_MIN:
                v -= 1
            out[um] = max(CONPI_MIN, v)
    return out


@dataclass
class ConpiFeatures:
    top: int                    # 1位のコンピ値（1強度）
    total: int                  # 全馬の総和
    gap12: int                  # 1位-2位差
    top3: int                   # 上位3頭の合計
    n: int                      # 頭数
    firm: str                   # 堅さラベル（コンピ理論の目安）

    @property
    def is_solid(self) -> bool:
        return self.top >= 85


def features(conpi: dict[int, int]) -> ConpiFeatures:
    vals = sorted(conpi.values(), reverse=True)
    top = vals[0] if vals else 0
    g12 = (vals[0] - vals[1]) if len(vals) > 1 else 0
    # コンピ理論の一般的な目安（1位値ベース）
    if top >= 85:
        firm = "堅い(1強)"
    elif top >= 79:
        firm = "中位"
    else:
        firm = "波乱含み(混戦)"
    return ConpiFeatures(top=top, total=sum(vals), gap12=g12,
                         top3=sum(vals[:3]), n=len(vals), firm=firm)
