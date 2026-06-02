"""netkeiba 地方(南関4場)から「結果 + 三連複/三連単オッズ」を収集する。

出力は core/dataset.py の JSONL 形式。build_dataset.py の入力にできる。

ローカルで実行する(要 requests / beautifulsoup4、要ネットワーク)。
本リポジトリの実行環境はネット遮断・bs4未導入のため未検証。実データを見ながら
parser.py / odds.py のセレクタ・エンドポイントを調整すること。

利用上の注意:
  - レート制限(client.py 既定1.5秒)を守り、サーバに負荷をかけない。
  - robots.txt と netkeiba の利用規約を尊重し、個人利用の範囲にとどめる。

実行例:
    python3 scripts/collect_data.py --year 2024 --place 大井 --out data/results.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.scraping.race_id import build_race_id, is_nankan, NANKAN_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from nankeiba.scraping import odds as O

RESULT_URL = "https://nar.netkeiba.com/race/result.html?race_id={race_id}"
# 日次のレース一覧(ajax)。ここから実在 race_id を拾う(総当たりより堅実)。
RACE_LIST_URL = "https://nar.netkeiba.com/top/race_list_sub.html?kaisai_date={ymd}"


def existing_race_ids(path: Path) -> set[str]:
    """既存 JSONL から収集済み race_id を読み、再取得をスキップできるようにする。"""
    done: set[str] = set()
    if not path.exists():
        return done
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(json.loads(line)["race_id"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def _race_to_record(race: P.ParsedRace, trio_odds, trifecta_odds) -> dict:
    """ParsedRace + オッズ を dataset.py の JSONL レコードへ。"""
    return {
        "race_id": race.race_id,
        "date": race.date,
        "place": race.place,
        "distance": race.distance,
        "field_size": race.field_size,
        "result": [
            {
                "finish_pos": r.finish_pos,
                "umaban": r.umaban,
                "horse_id": r.horse_id,
                "horse_name": r.horse_name,
                "jockey": r.jockey,
                "trainer": r.trainer,
                "popularity": r.popularity,
            }
            for r in race.rows
        ],
        "trio_odds": {"-".join(map(str, k)): v for k, v in trio_odds.items()},
        "trifecta_odds": {"-".join(map(str, k)): v for k, v in trifecta_odds.items()},
    }


def _fetch_one(client: PoliteClient, rid: str, *, with_odds: bool) -> dict | None:
    """1 race_id を取得して JSONL レコードへ。取得不可/空なら None。"""
    try:
        html = client.get(RESULT_URL.format(race_id=rid))
        race = P.parse_result_page(html, rid)
    except Exception:  # noqa: BLE001 ネット/パース失敗はスキップ
        return None
    if not race.rows:
        return None

    trio_odds, trifecta_odds = {}, {}
    if with_odds:
        try:
            trio_odds = O.parse_odds_payload(
                client.get(O.odds_api_url(rid, "trio")), bet_type="trio")
            trifecta_odds = O.parse_odds_payload(
                client.get(O.odds_api_url(rid, "trifecta")), bet_type="trifecta")
        except Exception:  # noqa: BLE001
            pass
    return _race_to_record(race, trio_odds, trifecta_odds)


def _write_records(client: PoliteClient, race_ids, *, out: str, with_odds: bool) -> int:
    """race_id 群を取得して JSONL へ追記。収集済み(--out 内)はスキップ(再開可能)。"""
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = existing_race_ids(out_path)
    n = 0
    with out_path.open("a", encoding="utf-8") as f:
        for rid in race_ids:
            if rid in done:
                continue
            rec = _fetch_one(client, rid, with_odds=with_odds)
            if rec is None:
                continue
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            done.add(rid)
            n += 1
            if n % 50 == 0:
                print(f"  collected {n} races...")
    print(f"done: {n} races -> {out_path}")
    return n


def collect(year: int, place: str, *, kai_range=range(1, 13), day_range=range(1, 13),
            race_range=range(1, 13), out: str = "data/results.jsonl",
            with_odds: bool = True) -> None:
    """総当たり(年×回×日×R)で race_id を生成して収集する(フォールバック)。"""
    client = PoliteClient()
    race_ids = (
        build_race_id(year, place, kai, day, rno)
        for kai in kai_range for day in day_range for rno in race_range
    )
    _write_records(client, race_ids, out=out, with_odds=with_odds)


def collect_by_dates(start: date, end: date, *, out: str = "data/results.jsonl",
                     with_odds: bool = True) -> None:
    """日付範囲を巡回し、各開催日のレース一覧から実在 race_id を拾って収集する。

    総当たりと違い 404 を踏まないため効率的・サーバに優しい。南関4場のみ対象。
    """
    client = PoliteClient()

    def _race_ids():
        d = start
        while d <= end:
            ymd = d.strftime("%Y%m%d")
            try:
                html = client.get(RACE_LIST_URL.format(ymd=ymd))
                ids = P.parse_race_ids_from_list(html, nankan_only=True)
            except Exception:  # noqa: BLE001
                ids = []
            if ids:
                print(f"  {ymd}: {len(ids)} races")
            yield from ids
            d += timedelta(days=1)

    _write_records(client, _race_ids(), out=out, with_odds=with_odds)


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main() -> None:
    ap = argparse.ArgumentParser(description="南関競馬 結果+オッズ収集")
    ap.add_argument("--out", default="data/results.jsonl")
    ap.add_argument("--no-odds", action="store_true", help="オッズを取得しない")
    # モード1: 日付範囲(推奨。一覧から実在 race_id を取得)
    ap.add_argument("--from", dest="date_from", type=_parse_date,
                    help="開始日 YYYY-MM-DD(--to と併用)")
    ap.add_argument("--to", dest="date_to", type=_parse_date,
                    help="終了日 YYYY-MM-DD(--from と併用)")
    # モード2: 総当たり(フォールバック)
    ap.add_argument("--year", type=int, help="総当たり収集の対象年")
    ap.add_argument("--place", choices=list(NANKAN_CODES), help="総当たり収集の対象場")
    args = ap.parse_args()

    with_odds = not args.no_odds
    if args.date_from and args.date_to:
        collect_by_dates(args.date_from, args.date_to, out=args.out, with_odds=with_odds)
    elif args.year and args.place:
        collect(args.year, args.place, out=args.out, with_odds=with_odds)
    else:
        ap.error("(--from と --to) か (--year と --place) を指定してください")


if __name__ == "__main__":
    main()
