"""中央競馬の展開予想サンプル(架空メンバー・オフラインで実行可能)。

同じ8頭が「中山 芝1200m」と「東京 芝1600m」を走った場合に、
ペース予想・隊列・各馬の展開利・最終スコア順がどう変わるかを示す。

  - メンバー構成: 逃げ馬1頭(A)だけ → 単騎逃げ濃厚でスロー寄り
  - 中山(直線310m)は前有利、東京(直線526m)は差し有利
  → 中山では逃げ・先行が浮上、東京では差し・追込の評価が上がる

馬名・成績は説明用の架空データ。実レースでは出馬表と各馬の過去走
(通過順・上がり順位・芝/ダ・馬場)を入れて使う。

実行: python3 scripts/tenkai_example.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.core.interval import RunRecord
from nankeiba.core.features import RaceContext, horse_score
from nankeiba.core import tenkai as tk
from nankeiba.core import probability as pb

RACE_DATE = "2026-11-15"

# 馬番 -> (馬名, [過去走 (日付, 場, 芝ダ, 距離, 頭数, 着, 通過順, 上り順)] 新しい順)
HORSES: dict[int, tuple[str, list[tuple]]] = {
    1: ("A(逃げ)", [
        ("2026-10-18", "東京", "芝", 1400, 16, 3, [1, 1], 9),
        ("2026-09-20", "中山", "芝", 1200, 16, 2, [1, 1], 7),
        ("2026-08-30", "新潟", "芝", 1400, 18, 6, [1, 1], 12),
    ]),
    2: ("B(先行)", [
        ("2026-10-25", "京都", "芝", 1400, 18, 4, [3, 3], 6),
        ("2026-09-28", "中山", "芝", 1200, 16, 3, [4, 3], 5),
        ("2026-09-07", "札幌", "芝", 1200, 14, 2, [2, 2], 4),
    ]),
    3: ("C(先行)", [
        ("2026-10-12", "東京", "芝", 1600, 16, 5, [4, 4], 8),
        ("2026-09-14", "中山", "芝", 1600, 16, 4, [3, 3, 3], 6),
        ("2026-08-17", "札幌", "芝", 1500, 14, 3, [3, 3, 2], 5),
    ]),
    4: ("D(差し)", [
        ("2026-10-18", "東京", "芝", 1400, 16, 2, [9, 8], 2),
        ("2026-09-21", "中山", "芝", 1200, 16, 6, [10, 9], 3),
        ("2026-08-23", "新潟", "芝", 1600, 18, 1, [11, 10], 1),
    ]),
    5: ("E(差し)", [
        ("2026-10-26", "東京", "芝", 1600, 18, 4, [10, 10], 3),
        ("2026-09-27", "中山", "芝", 1600, 16, 5, [8, 8, 7], 4),
        ("2026-08-31", "新潟", "芝", 1600, 18, 3, [12, 12], 2),
    ]),
    6: ("F(追込)", [
        ("2026-10-11", "東京", "芝", 1600, 16, 3, [15, 15], 1),
        ("2026-09-13", "中山", "芝", 1200, 16, 9, [16, 16], 2),
        ("2026-08-24", "新潟", "芝", 1600, 18, 2, [17, 17], 1),
    ]),
    7: ("G(中団)", [
        ("2026-10-19", "京都", "芝", 1600, 18, 6, [7, 7], 7),
        ("2026-09-28", "中山", "芝", 1600, 16, 5, [6, 6, 6], 6),
        ("2026-09-06", "札幌", "芝", 1500, 14, 4, [6, 6, 5], 5),
    ]),
    8: ("H(番手)", [
        ("2026-10-18", "東京", "芝", 1400, 16, 7, [2, 2], 10),
        ("2026-09-20", "中山", "芝", 1200, 16, 4, [2, 2], 8),
        ("2026-08-30", "新潟", "芝", 1400, 18, 8, [3, 3], 11),
    ]),
}


def build() -> dict[int, list[RunRecord]]:
    return {
        um: [
            RunRecord(date=d, place=p, distance=dist, field_size=fs, finish_pos=fp,
                      surface=sf, baba="良", corner_pos=cp, agari_rank=ar)
            for (d, p, sf, dist, fs, fp, cp, ar) in runs
        ]
        for um, (_, runs) in HORSES.items()
    }


def analyze(place: str, distance: int, surface: str, field: dict[int, list[RunRecord]]):
    fc = tk.forecast(field, place=place, distance=distance, surface=surface)
    print(f"\n==== {place} {surface}{distance}m  ({len(field)}頭) ====")
    print(fc.summary())
    print("予想隊列(前→後): " + " → ".join(f"{u}" for u in fc.order))

    scores = {}
    for um, runs in field.items():
        ctx = RaceContext(date=RACE_DATE, place=place, distance=distance,
                          field_size=len(field), surface=surface, baba="良",
                          tenkai_adv=fc.advantage[um])
        scores[um] = horse_score(runs, ctx)
    strengths = pb.strengths_from_scores(scores)
    order = sorted(scores, key=lambda u: scores[u], reverse=True)

    print(" 順 馬番 馬名       脚質  展開利  スコア  3着内率")
    for rank, um in enumerate(order, 1):
        st = fc.styles[um]
        print(f" {rank:2d}  {um:2d}  {HORSES[um][0]:<9s} {st.style:<3s} "
              f"{fc.advantage[um]:+.3f}  {scores[um]:+.3f}  "
              f"{pb.top3_probability(strengths, um):5.1%}")
    return order


def main() -> None:
    field = build()
    a = analyze("中山", 1200, "芝", field)
    b = analyze("東京", 1600, "芝", field)
    print("\n中山→東京 で順位が上がった馬: " +
          ", ".join(f"{u}{HORSES[u][0]}({a.index(u)+1}→{b.index(u)+1}位)"
                    for u in b if b.index(u) < a.index(u)))
    print("※架空データ。重みは未学習の既定値(tenkai=0.8)。実データで学習・検証すること。")


if __name__ == "__main__":
    main()
