"""1レースだけ取得して、楽天競馬のパース結果を確認するデバッグ用スクリプト。

本クロール(collect_data.py)の前に、これでパーサが効いているか検証する。
うまく取れない/文字化けする場合は、保存された生HTML(data/cache/*.html)を
共有してもらえれば、parser.py / odds.py を実物に合わせて調整できる。

使い方(ローカル・要 requests/beautifulsoup4・要ネットワーク):
    pip install -r requirements.txt
    # RACEID を直接指定(18桁):
    python3 scripts/fetch_one.py --race-id 202606021914030201
    # または 日付+場 で当日の一覧から R を選ぶ:
    python3 scripts/fetch_one.py --date 2026-06-02 --place 船橋 --race 1
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from nankeiba.scraping import odds as O

CARD_URL = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{race_id}"
RESULT_URL = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{race_id}"


def _resolve_race_id(client, args) -> str:
    if args.race_id:
        return args.race_id
    if not (args.date and args.place):
        raise SystemExit("--race-id か (--date と --place) を指定してください")
    ymd = date.fromisoformat(args.date).strftime("%Y%m%d")
    index_rid = day_index_race_id(ymd, args.place)
    html = client.get(CARD_URL.format(race_id=index_rid))
    races = dict(P.parse_race_links(html, date_yyyymmdd=ymd,
                                    jyo_code=NANKAN_CODES[args.place]))
    if not races:
        raise SystemExit(f"{args.date} {args.place}: 開催が見つかりません")
    if args.race not in races:
        raise SystemExit(f"{args.race}R が見つかりません。あるR: {sorted(races)}")
    return races[args.race]


def main() -> None:
    ap = argparse.ArgumentParser(description="楽天競馬 1レース取得デバッグ")
    ap.add_argument("--race-id")
    ap.add_argument("--date", help="YYYY-MM-DD")
    ap.add_argument("--place", choices=list(NANKAN_CODES))
    ap.add_argument("--race", type=int, default=11)
    ap.add_argument("--no-odds", action="store_true")
    args = ap.parse_args()

    client = PoliteClient()
    rid = _resolve_race_id(client, args)
    url = RESULT_URL.format(race_id=rid)
    print(f"race_id = {rid}")
    print(f"URL     = {url}\n")

    html = client.get(url)
    print(f"取得HTML: {len(html)} 文字  保存先: {client._cache_path(url)}\n")

    race = P.parse_result_page(html, rid)
    print(f"日付={race.date} 場={race.place} {race.surface}{race.distance}m 頭数={race.field_size}")
    print(" 着 馬番 枠 馬ID        馬名             騎手     調教師   人気 タイム")
    for r in race.rows[:20]:
        print(f" {r.finish_pos:2} {str(r.umaban):>3} {str(r.waku):>2} {r.horse_id:<11} "
              f"{r.horse_name:<14} {r.jockey:<6} {str(r.trainer):<6} {str(r.popularity):>3} "
              f"{r.time or ''}")
    if not race.rows:
        print("\n→ 行が0件。parser.py の着順表セレクタを実HTMLに合わせる必要があります。")
        return

    if not args.no_odds:
        for bt, label in (("trio", "三連複"), ("trifecta", "三連単")):
            try:
                od = O.parse_odds_html(client.get(O.odds_url(rid, bt)), bet_type=bt)
                sample = sorted(od.items(), key=lambda kv: kv[1])[:5]
                print(f"\n{label}: {len(od)} 組  最低オッズ例: "
                      + ", ".join(f"{'-'.join(map(str,k))}={v}" for k, v in sample))
            except Exception as e:  # noqa: BLE001
                print(f"\n{label}: 取得失敗 {e}")


if __name__ == "__main__":
    main()
