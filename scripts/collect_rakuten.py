"""楽天競馬(keiba.rakuten.co.jp)から「結果 + 三連複/三連単オッズ」を収集する。

出力は core/dataset.py の JSONL 形式(collect_data.py と同一)。build_dataset.py の
入力にできる。RACEID は日次一覧ページのリンクから抽出する経路を主とする。

⚠️ ローカル(要 requests / beautifulsoup4、要ネットワーク)で実行すること。
   本リポジトリの実行環境は egress プロキシで keiba.rakuten.co.jp が遮断されており
   未検証。実データを見ながら rakuten.py のセレクタ・URL・場コードを調整すること。

利用上の注意:
  - レート制限(client.py 既定 1.5 秒)を守り、サーバに負荷をかけない。
  - robots.txt と楽天競馬の利用規約を尊重し、個人利用の範囲にとどめる。

実行例(一覧ページの RACEID 群から自動収集):
    python3 scripts/collect_rakuten.py \
        --list-raceid 20240101180101 --out data/rakuten.jsonl

  --list-raceid には「その開催日の一覧ページ」を引ける任意の RACEID を渡す。
  一覧から各レースの RACEID を抽出し、結果とオッズを収集する。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import rakuten as R


def _race_to_record(race, trio_odds, trifecta_odds) -> dict:
    """ParsedRace + オッズ を dataset.py の JSONL レコードへ(collect_data.py と同形式)。"""
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


def collect(list_raceids: list[str], *, out: str = "data/rakuten.jsonl",
            with_odds: bool = True) -> None:
    client = PoliteClient(encoding="utf-8")  # 楽天は UTF-8
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out_path.open("a", encoding="utf-8") as f:
        for list_rid in list_raceids:
            # ① 一覧ページから各レースの RACEID を抽出
            try:
                list_html = client.get(R.RACE_LIST_URL.format(raceid=list_rid))
                raceids = R.extract_raceids(list_html)
            except Exception as e:  # noqa: BLE001
                print(f"  [skip list {list_rid}] {e}")
                continue

            for rid in raceids:
                # ② 結果ページ
                try:
                    race = R.parse_result_page(client.get(R.result_url(rid)), rid)
                except Exception:  # noqa: BLE001 ネット/パース失敗はスキップ
                    continue
                if not race.rows:
                    continue

                # ③ オッズ(任意)
                trio_odds, trifecta_odds = {}, {}
                if with_odds:
                    try:
                        trio_odds = R.parse_odds_html(
                            client.get(R.odds_url(rid, "trio")), bet_type="trio")
                        trifecta_odds = R.parse_odds_html(
                            client.get(R.odds_url(rid, "trifecta")), bet_type="trifecta")
                    except Exception:  # noqa: BLE001
                        pass

                f.write(json.dumps(_race_to_record(race, trio_odds, trifecta_odds),
                                   ensure_ascii=False) + "\n")
                n += 1
                if n % 50 == 0:
                    print(f"  collected {n} races...")
    print(f"done: {n} races -> {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="楽天競馬 結果+オッズ収集")
    ap.add_argument("--list-raceid", action="append", required=True,
                    help="開催日の一覧ページを引く RACEID(複数指定可)")
    ap.add_argument("--out", default="data/rakuten.jsonl")
    ap.add_argument("--no-odds", action="store_true", help="オッズを取得しない")
    args = ap.parse_args()
    collect(args.list_raceid, out=args.out, with_odds=not args.no_odds)


if __name__ == "__main__":
    main()
