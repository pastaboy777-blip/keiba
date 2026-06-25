"""楽天競馬(keiba.rakuten.co.jp)から南関4場の「結果 + 三連複/三連単オッズ」を収集する。

出力は core/dataset.py の JSONL 形式。build_dataset.py の入力にできる。

収集フロー(サイト内部の開催回採番に依存しない頑健な方式):
  1) 日付+場コードのインデックスページ(出馬表)を開く
  2) ページ内のリンクから、その日のレース RACEID を全て取得
  3) 各レースの競走成績ページ + 三連複/三連単オッズページを取得・パース

ローカルで実行する(要 requests / beautifulsoup4、要ネットワーク)。

利用上の注意:
  - レート制限(client.py 既定1.5秒)を守り、サーバに負荷をかけない。
  - robots.txt と楽天競馬の利用規約を尊重し、個人利用の範囲にとどめる。

実行例:
    python3 scripts/collect_data.py --start 2024-01-01 --end 2024-12-31 \
        --place 大井 --out data/results.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from nankeiba.scraping import odds as O

CARD_URL = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{race_id}"
RESULT_URL = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{race_id}"


def _race_to_record(race: P.ParsedRace, trio_odds, trifecta_odds,
                    win_odds=None, place_odds=None, wide_odds=None) -> dict:
    """ParsedRace + オッズ を dataset.py の JSONL レコードへ。"""
    win_odds = win_odds or {}
    place_odds = place_odds or {}
    wide_odds = wide_odds or {}
    return {
        "race_id": race.race_id,
        "date": race.date,
        "place": race.place,
        "distance": race.distance,
        "surface": race.surface,
        "field_size": race.field_size,
        "result": [
            {
                "finish_pos": r.finish_pos,
                "umaban": r.umaban,
                "waku": r.waku,
                "horse_id": r.horse_id,
                "horse_name": r.horse_name,
                "jockey": r.jockey,
                "trainer": r.trainer,
                "popularity": r.popularity,
                "time": r.time,
            }
            for r in race.rows
        ],
        "trio_odds": {"-".join(map(str, k)): v for k, v in trio_odds.items()},
        "trifecta_odds": {"-".join(map(str, k)): v for k, v in trifecta_odds.items()},
        # 単勝/複勝は {馬番: オッズ}、ワイドは {"a-b": オッズ}。複勝/ワイドはレンジ下限。
        "win_odds": {str(k): v for k, v in win_odds.items()},
        "place_odds": {str(k): v for k, v in place_odds.items()},
        "wide_odds": {"-".join(map(str, k)): v for k, v in wide_odds.items()},
    }


def _daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def collect(start: date, end: date, place: str, *,
            out: str = "data/results.jsonl", with_odds: bool = True) -> None:
    client = PoliteClient()
    code = NANKAN_CODES[place]
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out_path.open("a", encoding="utf-8") as f:
        for d in _daterange(start, end):
            ymd = d.strftime("%Y%m%d")
            index_rid = day_index_race_id(ymd, place)
            try:
                index_html = client.get(CARD_URL.format(race_id=index_rid))
            except Exception:  # noqa: BLE001 ネット失敗はその日をスキップ
                continue
            races = P.parse_race_links(index_html, date_yyyymmdd=ymd, jyo_code=code)
            if not races:
                continue  # 非開催日
            print(f"{d.isoformat()} {place}: {len(races)} races")
            for _rno, rid in races:
                try:
                    html = client.get(RESULT_URL.format(race_id=rid))
                    race = P.parse_result_page(html, rid)
                except Exception:  # noqa: BLE001
                    continue
                if not race.rows:
                    continue

                trio_odds, trifecta_odds = {}, {}
                win_odds, place_odds, wide_odds = {}, {}, {}
                if with_odds:
                    try:
                        trio_odds = O.parse_odds_html(
                            client.get(O.odds_url(rid, "trio")), bet_type="trio")
                        trifecta_odds = O.parse_odds_html(
                            client.get(O.odds_url(rid, "trifecta")), bet_type="trifecta")
                        tf = O.parse_tanfuku_html(client.get(O.odds_url(rid, "tanfuku")))
                        win_odds, place_odds = tf["win"], tf["place"]
                        wide_odds = O.parse_wide_html(client.get(O.odds_url(rid, "wide")))
                    except Exception:  # noqa: BLE001
                        pass

                rec = _race_to_record(race, trio_odds, trifecta_odds,
                                      win_odds=win_odds, place_odds=place_odds,
                                      wide_odds=wide_odds)
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1
    print(f"done: {n} races -> {out_path}")


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main() -> None:
    ap = argparse.ArgumentParser(description="楽天競馬 南関 結果+オッズ収集")
    ap.add_argument("--start", type=_parse_date, required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", type=_parse_date, required=True, help="YYYY-MM-DD")
    ap.add_argument("--place", choices=list(NANKAN_CODES), required=True)
    ap.add_argument("--out", default="data/results.jsonl")
    ap.add_argument("--no-odds", action="store_true", help="オッズを取得しない")
    args = ap.parse_args()
    collect(args.start, args.end, args.place, out=args.out, with_odds=not args.no_odds)


if __name__ == "__main__":
    main()
