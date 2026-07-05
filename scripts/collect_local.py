"""楽天競馬から地方全場(南関＋地方)の「出馬表 + 結果」を収集する。

collect_nankan.py を全場対応にした版。場コードは race_id.ALL_CODES を使う
(浦和/船橋/大井/川崎 + 門別/盛岡/水沢/金沢/笠松/名古屋/園田/高知/佐賀)。
南関専用の collect_nankan.py は変更しない。高知(31)など地方場の収集に使う。

各馬の近走履歴(前5走)から特徴量を算出し、結果(着順)をラベルとして付けて
JSONL に貯める(build_enriched_race)。非開催日・非開催場は自動スキップ。

出力(1行=1レース):
    {race_id, date, place, distance, surface, field_size, race_name,
     result_order, horses:[{umaban, horse_id, jockey, finish_pos,
                            signals:{...}, features:{...}, recent_runs:[...]}]}

実行例:
    # 高知の1日をテスト収集
    python3 scripts/collect_local.py --start 2026-06-30 --end 2026-06-30 \
        --place 高知 --out data/samples/kochi_test.jsonl
    # 高知の1ヶ月をまとめて(非開催日は自動スキップ)
    python3 scripts/collect_local.py --start 2025-07-01 --end 2025-07-31 \
        --place 高知 --out data/samples/kochi_2025-07.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from nankeiba.scraping import enrich as E

CARD_URL = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{race_id}"
RESULT_URL = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{race_id}"


def _daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def collect(start: date, end: date, places, *, out: str) -> None:
    client = PoliteClient()
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_races = 0
    with out_path.open("a", encoding="utf-8") as f:
        for d in _daterange(start, end):
            ymd = d.strftime("%Y%m%d")
            for place in places:
                code = ALL_CODES[place]
                try:
                    index_html = client.get(CARD_URL.format(
                        race_id=day_index_race_id(ymd, place)))
                except Exception:  # noqa: BLE001
                    continue
                races = P.parse_race_links(index_html, date_yyyymmdd=ymd, jyo_code=code)
                if not races:
                    continue  # 非開催
                print(f"{d.isoformat()} {place}: {len(races)} races")
                for _rno, rid in races:
                    try:
                        card = P.parse_card_page(
                            client.get(CARD_URL.format(race_id=rid)), rid)
                    except Exception:  # noqa: BLE001
                        continue
                    result = None
                    try:  # 結果は確定後のみ。未確定でも出馬表だけ貯める
                        result = P.parse_result_page(
                            client.get(RESULT_URL.format(race_id=rid)), rid)
                        if not result.rows:
                            result = None
                    except Exception:  # noqa: BLE001
                        pass
                    rec = E.build_enriched_race(card, result)
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    n_races += 1
    print(f"done: {n_races} races -> {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="楽天競馬 地方全場 出馬表+結果 充実化収集")
    ap.add_argument("--start", type=date.fromisoformat, required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", type=date.fromisoformat, required=True, help="YYYY-MM-DD")
    ap.add_argument("--place", choices=list(ALL_CODES))
    ap.add_argument("--all", action="store_true", help="全場(南関＋地方)すべて")
    ap.add_argument("--out", default="data/local_enriched.jsonl")
    args = ap.parse_args()
    if args.all:
        places = list(ALL_CODES)
    elif args.place:
        places = [args.place]
    else:
        ap.error("--place か --all を指定してください")
    collect(args.start, args.end, places, out=args.out)


if __name__ == "__main__":
    main()
