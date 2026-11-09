"""エンドツーエンドのデモ(合成データ)。

南関の合成シーズンを生成し、「ズブい馬を走らせる」観点(出走間隔・叩き良化・
騎手/厩舎・条件替わり)を使うモデルで三連複/三連単をバックテストし、回収率を出す。

比較対象として「人気(オッズ)順に機械的に買う」素朴な戦略の回収率も出し、
観点ありモデルが市場の盲点を突けているかを確認する。

実行:
    python3 scripts/demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.core import synth, betting as bt, probability as pb
from nankeiba.core.backtest import run_backtest, Race
from nankeiba.core.features import ScoreWeights


def naive_favorite_roi(races: list[Race], *, top_k: int = 4, stake: float = 100.0) -> str:
    """素朴戦略: 三連複でオッズが低い(人気)上位 top_k 点を機械的に買う。"""
    spent = ret = 0.0
    hits = bets = 0
    for race in races:
        if not race.trio_odds:
            continue
        cheap = sorted(race.trio_odds.items(), key=lambda kv: kv[1])[:top_k]
        result = tuple(sorted(race.result_order[:3]))
        for combo, odds in cheap:
            spent += stake
            bets += 1
            if combo == result:
                ret += stake * odds
                hits += 1
    roi = ret / spent if spent else 0.0
    return f"bets={bets} hits={hits} spent={spent:.0f} returned={ret:.0f} ROI={roi:.1%}"


def main() -> None:
    print("=== 南関競馬 予測パイプライン デモ(合成データ)===\n")
    races, jockeys, trainers = synth.generate_season(n_races=600, seed=7)
    print(f"生成レース数: {len(races)}  競馬場: 大井/川崎/船橋/浦和  全ダート\n")

    weights = ScoreWeights()  # 既定(間隔・叩き・騎手・条件替わりすべて有効)

    for bet_type, label in [("trio", "三連複"), ("trifecta", "三連単")]:
        print(f"--- {label} ---")
        res = run_backtest(
            races,
            jockeys=jockeys,
            trainers=trainers,
            weights=weights,
            bet_type=bet_type,
            ev_threshold=1.3,
            max_bets=6,
            min_history=4,
        )
        print("  [観点あり EVモデル] " + res.summary())

    print("\n--- 比較: 素朴な人気順買い(三連複) ---")
    print("  [人気順4点] " + naive_favorite_roi(races))

    print("\n--- ケリー資金配分シミュレーション(三連複・複利)---")
    print("  固定額と違い、資金の一定割合を各点に張り、勝てば加速・負ければ減速する。")
    for frac in (0.10, 0.25, 0.50):
        res = run_backtest(
            races,
            jockeys=jockeys,
            trainers=trainers,
            weights=weights,
            bet_type="trio",
            ev_threshold=1.3,
            max_bets=6,
            min_history=4,
            kelly=True,
            bankroll=100000.0,
            kelly_fraction=frac,
        )
        print(f"  [{frac:.0%}ケリー] " + res.summary())
    print("  注: 分数ケリー係数が大きいほど期待成長は上がるが最大DD(下落)も増える。")

    print(
        "\n注: 合成データによるロジック検証です。ROIが100%超でも"
        "「コードが市場の歪みを突けている」ことの確認であり、"
        "実戦の利益を保証しません。リアルデータでの検証が必須です。"
    )


if __name__ == "__main__":
    main()
