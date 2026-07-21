#!/usr/bin/env python3
"""楽天データで、指数と実結果を照合するバックテスト。

指定した開催日・競馬場の各レースについて:
  1) 出馬表(race_card)の馬柱からレース前の過去走だけで指数を算出(リーク防止)
  2) 各馬の「近5走以内の最高指数」で並べ、これを予想順位とする(=新聞の◎○▲)
  3) 競走成績(race_performance)の実着順と照合
して、指数がどれだけ当たっていたかを集計する。

    python3 scripts/backtest_rakuten.py --date 20260716 --place 浦和
    python3 scripts/backtest_rakuten.py --date 20260716 --place 浦和 --races 1-12

依存: 標準ライブラリのみ。※個人利用・節度ある取得。
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import rakuten as rk            # noqa: E402
from nankeiba.core.hindex import SpeedIndexModel        # noqa: E402


def best_index(runs, model, lookback=5):
    best = None
    for r in list(runs)[:lookback]:
        idx = model.index(r)
        if idx is not None and (best is None or idx > best):
            best = idx
    return best


def parse_races_arg(s: str, default_max: int = 12) -> list[int]:
    if not s:
        return list(range(1, default_max + 1))
    if "-" in s:
        a, b = s.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in s.split(",")]


def main():
    ap = argparse.ArgumentParser(description="指数と結果の照合バックテスト(楽天)")
    ap.add_argument("--date", required=True, help="開催日 YYYYMMDD")
    ap.add_argument("--place", default="浦和")
    ap.add_argument("--races", default="", help="対象レース 例 1-12 / 1,3,5 (既定=全R)")
    ap.add_argument("--lookback", type=int, default=5)
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    client = rk.KeibaRakuten()
    use_cache = not args.no_cache
    race_date = f"{args.date[:4]}-{args.date[4:6]}-{args.date[6:]}"

    meeting = client.find_race_id(args.date, args.place, 1)[:-2]  # 末尾RRを除いた開催
    races = parse_races_arg(args.races)

    print(f"=== {race_date} {args.place} 指数バックテスト ===\n")
    hdr = f"{'R':>3} | {'◎馬(指数)':<16} | {'着':>2} | {'1着馬(人気)':<14} | 勝馬の指数順位"
    print(hdr); print("-" * len(hdr))

    agg = {"n": 0, "anchor_win": 0, "anchor_in3": 0, "winner_in_top3": 0,
           "winner_rank_sum": 0, "winner_rank_n": 0}

    for rno in races:
        race_id = meeting + f"{rno:02d}"
        try:
            card = rk.parse_card(client.get(f"/race_card/list/RACEID/{race_id}", use_cache=use_cache))
            result = rk.parse_result(client.get(f"/race_performance/list/RACEID/{race_id}", use_cache=use_cache))
        except Exception as e:                                  # noqa: BLE001
            print(f"{rno:>3} | 取得失敗: {e}")
            continue
        entries = card["entries"]
        if not entries or not result:
            print(f"{rno:>3} | データ無し(未確定 or 中止)")
            continue

        # レース前の走だけで指数(リーク防止)
        pre = {e["umaban"]: [r for r in e["history"] if r.date < race_date] for e in entries}
        model = SpeedIndexModel.fit([r for rs in pre.values() for r in rs])
        idx = {um: best_index(rs, model, args.lookback) for um, rs in pre.items()}
        name = {e["umaban"]: e["name"] for e in entries}

        # 指数で予想順位(指数なしは最下位扱い)
        ranking = sorted(idx, key=lambda um: (idx[um] is not None, idx[um] if idx[um] is not None else -1e9),
                         reverse=True)
        rank_of = {um: i + 1 for i, um in enumerate(ranking)}
        anchor = ranking[0]                                     # ◎ = 指数1位

        fin_of = {r["umaban"]: r["finish"] for r in result}
        winner = next((r for r in result if r["finish"] == 1), None)
        if winner is None:
            continue
        agg["n"] += 1
        anchor_fin = fin_of.get(anchor)
        if anchor_fin == 1:
            agg["anchor_win"] += 1
        if anchor_fin is not None and anchor_fin <= 3:
            agg["anchor_in3"] += 1
        w_rank = rank_of.get(winner["umaban"])
        if w_rank:
            agg["winner_rank_sum"] += w_rank; agg["winner_rank_n"] += 1
            if w_rank <= 3:
                agg["winner_in_top3"] += 1

        aidx = idx.get(anchor)
        aidx_s = f"{aidx:+.0f}" if aidx is not None else "-"
        pop = winner.get("popularity")
        print(f"{rno:>3} | {anchor:>2}{name.get(anchor,'')[:6]:<6}({aidx_s:>4}) | "
              f"{anchor_fin if anchor_fin else '-':>2} | "
              f"{winner['umaban']:>2}{winner['name'][:6]:<6}({pop if pop else '?'}人) | "
              f"{w_rank if w_rank else '-'}番手/{len(ranking)}")

    n = agg["n"]
    print("\n=== 集計 ===")
    if n:
        print(f"対象レース: {n}")
        print(f"◎(指数1位)の勝率 : {agg['anchor_win']}/{n} = {agg['anchor_win']/n:.0%}")
        print(f"◎の複勝率(3着内): {agg['anchor_in3']}/{n} = {agg['anchor_in3']/n:.0%}")
        print(f"勝ち馬が指数上位3頭だった率: {agg['winner_in_top3']}/{n} = {agg['winner_in_top3']/n:.0%}")
        if agg["winner_rank_n"]:
            print(f"勝ち馬の平均指数順位: {agg['winner_rank_sum']/agg['winner_rank_n']:.1f}番手")
        print("\n(参考)◎を機械的に単勝で買った場合の的中率が上の◎勝率。")
        print("実際は展開・馬場・人気妙味を加味するので、これは指数“単体”の素の力。")
    else:
        print("対象データがありませんでした。")


if __name__ == "__main__":
    main()
