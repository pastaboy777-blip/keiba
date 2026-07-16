"""予測パイプラインの出力から「初速の出る X 投稿文」を生成して表示する。

X で再生数(インプレッション)が伸び悩む原因の多くは、
  ・本文に外部リンク(netkeiba/note/ツイキャス/LINE)を貼って表示が絞られる
  ・1行目が弱くタイムラインで飛ばされる
の2つ。このスクリプトは予測結果から、逆張り本命・根拠3点・断言の1行目・
検証予告を組み立て、リンクは必ずセルフリプライ側に置いた下書きを出力する。

実行:
    python3 scripts/tweet_gen.py
    python3 scripts/tweet_gen.py --link https://twitcasting.tv/xxxx --roi 128

出馬表は predict_example.py と同じ船橋のサンプルを流用。実運用では HORSES を
差し替える(または collect_data の出力から HorseEntry を組む)。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.core import tweet as tw
from nankeiba.core.features import RaceContext, ScoreWeights

# predict_example と同じ船橋・ダ1000m・14頭のサンプル出馬表を再利用する。
from predict_example import HORSES, RACE_DATE, PLACE, DISTANCE, BABA, FIELD  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="予測結果から初速の出るツイート下書きを生成")
    p.add_argument("--race-label", default="11R", help="レース番号などの表示ラベル(例: 11R)")
    p.add_argument("--link", default=None, help="誘導リンク(セルフリプに置く。本文には入れない)")
    p.add_argument("--roi", type=float, default=None, help="直近の回収率%(数字フック用)")
    p.add_argument("--interval-weight", action="store_true",
                   help="短間隔重視の重みで評価する(南関方針)")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    entries = tw.entries_from_tuples(HORSES)
    ctx = RaceContext(date=RACE_DATE, place=PLACE, distance=DISTANCE,
                      field_size=FIELD, baba=BABA)
    weights = (ScoreWeights(interval_fit=1.8, toughness=0.6, tatakii=1.3)
               if args.interval_weight else ScoreWeights())

    plan = tw.generate(entries, ctx, weights=weights, race_label=args.race_label,
                       link=args.link, roi_pct=args.roi)

    print(f"■ {PLACE}{args.race_label} ダ{DISTANCE}m {BABA} {FIELD}頭  {RACE_DATE}")
    print(f"■ 逆張り本命: ◎{plan.honmei.um} {plan.honmei.name}"
          f"({plan.honmei.popularity}番人気 / 単勝{plan.honmei.win_odds}倍)")
    if plan.favorite_downgraded:
        print("  → 1番人気をモデルは格下げ。逆張りの旗を立てられるレース。")
    print("■ 相手: " + ", ".join(f"{e.um}{e.name}({e.popularity}人気)" for e in plan.partners))
    print("■ 根拠3点:")
    for r in plan.reasons:
        print(f"   ・{r}")

    print("\n" + "=" * 56)
    print("ツイート下書き(本文にリンクを入れない / リンクはリプへ)")
    print("=" * 56)
    for d in plan.drafts:
        warn = "  ⚠️文字数オーバー" if d.over_limit else ""
        print(f"\n--- {tw.STYLE_LABEL.get(d.style, d.style)} "
              f"[{d.weighted_len}/280]{warn} ---")
        print(d.render())

    print("\n" + "-" * 56)
    print("運用メモ: 発走30〜60分前に投稿 / 1行目は断言・逆張り・数字 /")
    print("          リンクは必ずリプ / 画像(馬柱or収支グラフ)を1枚添付。")


if __name__ == "__main__":
    main()
