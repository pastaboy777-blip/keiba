"""1レースだけ取得して、パース結果と生HTMLの場所を確認するデバッグ用スクリプト。

本クロール(collect_data.py)の前に、これでセレクタが効いているか検証する。
うまく取れない/文字化けする場合は、表示される生HTMLのパス(data/cache/*.html)を
共有してもらえれば、parser.py のセレクタを実物に合わせて確定できる。

使い方(ローカル・要 requests/beautifulsoup4・要ネットワーク):
    pip install -r requirements.txt
    # 例: 2024年 大井 1回1日目 11R。実在する race_id を指定すること。
    python3 scripts/fetch_one.py --year 2024 --place 大井 --kai 1 --day 1 --race 11
    # または race_id を直接:
    python3 scripts/fetch_one.py --race-id 202444010111
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.scraping.race_id import build_race_id, NANKAN_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

RESULT_URL = "https://nar.netkeiba.com/race/result.html?race_id={race_id}"


def main() -> None:
    ap = argparse.ArgumentParser(description="1レース取得デバッグ")
    ap.add_argument("--race-id")
    ap.add_argument("--year", type=int)
    ap.add_argument("--place", choices=list(NANKAN_CODES))
    ap.add_argument("--kai", type=int, default=1)
    ap.add_argument("--day", type=int, default=1)
    ap.add_argument("--race", type=int, default=11)
    args = ap.parse_args()

    if args.race_id:
        rid = args.race_id
    elif args.year and args.place:
        rid = build_race_id(args.year, args.place, args.kai, args.day, args.race)
    else:
        ap.error("--race-id か (--year と --place) を指定してください")

    url = RESULT_URL.format(race_id=rid)
    print(f"race_id = {rid}")
    print(f"URL     = {url}\n")

    client = PoliteClient()
    html = client.get(url)
    cache_path = client._cache_path(url)
    print(f"取得HTML: {len(html)} 文字  保存先: {cache_path}")
    print("  (パースが空/文字化けなら、この保存先ファイルを共有してください)\n")

    try:
        race = P.parse_result_page(html, rid)
    except Exception as e:  # noqa: BLE001
        print(f"!! パース例外: {e}")
        print("生HTMLの先頭500字:\n" + html[:500])
        return

    print(f"日付={race.date} 場={race.place} 距離={race.distance} 頭数={race.field_size}")
    print(f"取得行数: {len(race.rows)}")
    print(" 着 馬番 馬ID        馬名             騎手     人気 オッズ")
    for r in race.rows[:20]:
        print(f" {r.finish_pos:2} {str(r.umaban):>3} {r.horse_id:<11} "
              f"{r.horse_name:<14} {r.jockey:<6} {str(r.popularity):>3} {str(r.odds):>6}")

    if not race.rows:
        print("\n→ 行が0件。parser.py のテーブルセレクタを実HTMLに合わせる必要があります。")
        print("生HTMLの先頭800字:\n" + html[:800])


if __name__ == "__main__":
    main()
