#!/usr/bin/env python3
"""南関のレースを「レベルが高かったか」で並べる。

    # 7月の南関で中身が濃かったレース 上位20
    python3 scripts/nankan_level.py --month 202607

    # 川崎だけ／時計順／格順
    python3 scripts/nankan_level.py --month 202607 --place 川崎
    python3 scripts/nankan_level.py --month 202607 --by time
    python3 scripts/nankan_level.py --month 202607 --by grade

    # ある1日を全部
    python3 scripts/nankan_level.py --date 2026-07-30 --top 12 --by race

    # CSVに出す
    python3 scripts/nankan_level.py --month 202607 --csv out/level_202607.csv

物差しは3つ。**1つに畳まない。** 詳しくは `nankeiba.core.thickness` の docstring。

  濃さ     テン3F差 ＋ 上がり差（馬場補正後）。**マイナスほど濃い。**
  時計     標準（par_win）＋当日馬場差より何秒速いか。プラスが速い。
  格       出走馬の「そのレースより前の1着経験率」の中央値。

⚠️ 基準（同条件の中央値・当日馬場差）は**キャッシュ全体**から作る。--month は
   表示の絞り込みであって、基準を痩せさせないため読み込みは全期間で行う。
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import thickness as th             # noqa: E402

CSV_COLS = ["日付", "場", "R", "距離", "頭数", "馬場", "勝ちタイム", "当日馬場差",
            "テン3F差", "上がり差", "濃さ", "時計レベル", "格", "ペース",
            "メンバー最速上がり", "ラップ"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="YYYYMM で絞る（表示のみ）")
    ap.add_argument("--date", help="YYYY-MM-DD で絞る")
    ap.add_argument("--place", action="append", help="大井/川崎/船橋/浦和")
    ap.add_argument("--by", choices=("thick", "time", "grade", "race"),
                    default="thick", help="並べ方。race は日付・R順")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--min-field", type=int, default=0, help="頭数の下限")
    ap.add_argument("--csv", help="CSVの書き出し先")
    args = ap.parse_args()

    print("キャッシュを読み込み中…", file=sys.stderr)
    races = th.scan()
    print(f"  {len(races)}レース", file=sys.stderr)

    sel = races
    if args.month:
        ym = f"{args.month[:4]}-{args.month[4:6]}"
        sel = [r for r in sel if r.date.startswith(ym)]
    if args.date:
        sel = [r for r in sel if r.date == args.date]
    if args.place:
        sel = [r for r in sel if r.place in args.place]
    if args.min_field:
        sel = [r for r in sel if r.field_size >= args.min_field]
    if not sel:
        print("該当レースなし。", file=sys.stderr)
        sys.exit(1)

    hd = {"thick": "中身の濃かったレース（マイナスほど濃い）",
          "time": "時計の速かったレース（馬場補正後）",
          "grade": "メンバーの揃っていたレース",
          "race": "日付・R順"}[args.by]
    print(f"=== {hd} / 対象 {len(sel)}レース ===\n")

    if args.by == "race":
        rows = sorted(sel, key=lambda r: (r.date, r.place, r.race_no or 0))[:args.top]
    else:
        rows = th.rank(sel, by=args.by, top=args.top)

    n_ok = sum(1 for r in sel if r.thick is not None)
    for i, r in enumerate(rows, 1):
        print(f"{i:>3}. {r.line()}")
    print(f"\n（濃さを出せたのは {n_ok}/{len(sel)}レース。"
          f"距離が200で割り切れないレースはテン3Fが信用できないので除外）")

    if args.csv:
        os.makedirs(os.path.dirname(args.csv) or ".", exist_ok=True)
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(CSV_COLS)
            for r in sorted(sel, key=lambda r: (r.date, r.place, r.race_no or 0)):
                w.writerow([r.date, r.place, r.race_no, r.distance, r.field_size,
                            r.baba, r.win_time, round(r.bias, 3), r.ten_d, r.ag_d,
                            r.thick, r.time_lv, r.grade, r.pace, r.best_agari, r.lap])
        print(f"→ {args.csv}")


if __name__ == "__main__":
    main()
