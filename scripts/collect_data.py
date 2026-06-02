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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.scraping.race_id import build_race_id, NANKAN_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from nankeiba.scraping import odds as O

RESULT_URL = "https://nar.netkeiba.com/race/result.html?race_id={race_id}"


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


def collect(year: int, place: str, *, kai_range=range(1, 13), day_range=range(1, 13),
            race_range=range(1, 13), out: str = "data/results.jsonl",
            with_odds: bool = True) -> None:
    client = PoliteClient()
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out_path.open("a", encoding="utf-8") as f:
        for kai in kai_range:
            for day in day_range:
                for rno in race_range:
                    rid = build_race_id(year, place, kai, day, rno)
                    try:
                        html = client.get(RESULT_URL.format(race_id=rid))
                        race = P.parse_result_page(html, rid)
                    except Exception:  # noqa: BLE001 ネット/パース失敗はスキップ
                        continue
                    if not race.rows:
                        continue

                    trio_odds, trifecta_odds = {}, {}
                    if with_odds:
                        try:
                            trio_odds = O.parse_odds_payload(
                                client.get(O.odds_api_url(rid, "trio")), bet_type="trio")
                            trifecta_odds = O.parse_odds_payload(
                                client.get(O.odds_api_url(rid, "trifecta")), bet_type="trifecta")
                        except Exception:  # noqa: BLE001
                            pass

                    rec = _race_to_record(race, trio_odds, trifecta_odds)
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    n += 1
                    if n % 50 == 0:
                        print(f"  collected {n} races...")
    print(f"done: {n} races -> {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="南関競馬 結果+オッズ収集")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--place", choices=list(NANKAN_CODES), required=True)
    ap.add_argument("--out", default="data/results.jsonl")
    ap.add_argument("--no-odds", action="store_true", help="オッズを取得しない")
    args = ap.parse_args()
    collect(args.year, args.place, out=args.out, with_odds=not args.no_odds)


if __name__ == "__main__":
    main()
