"""netkeiba 地方(南関4場)からレース結果を収集するスケルトン。

ローカルで実行する(要 requests / beautifulsoup4、要ネットワーク)。
本リポジトリの実行環境はネット遮断のため未検証。実データを見ながら
parser.py のセレクタと race_id の列挙範囲を調整すること。

利用上の注意:
  - レート制限(client.py 既定1.5秒)を守り、サーバに負荷をかけない。
  - robots.txt と netkeiba の利用規約を尊重し、個人利用の範囲にとどめる。

実行例:
    python3 scripts/collect_data.py --year 2024 --place 大井
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

# netkeiba 地方の結果ページURL(要確認)
RESULT_URL = "https://nar.netkeiba.com/race/result.html?race_id={race_id}"


def collect(year: int, place: str, *, kai_range=range(1, 13), day_range=range(1, 13),
            race_range=range(1, 13), out: str = "data/results.jsonl") -> None:
    client = PoliteClient()
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out_path.open("a", encoding="utf-8") as f:
        for kai in kai_range:
            for day in day_range:
                for rno in race_range:
                    rid = build_race_id(year, place, kai, day, rno)
                    url = RESULT_URL.format(race_id=rid)
                    try:
                        html = client.get(url)
                        race = P.parse_result_page(html, rid)
                    except Exception as e:  # noqa: BLE001 ネットワーク/パース失敗はスキップ
                        continue
                    if not race.rows:
                        continue
                    f.write(json.dumps(race.__dict__, ensure_ascii=False, default=lambda o: o.__dict__) + "\n")
                    n += 1
                    if n % 50 == 0:
                        print(f"  collected {n} races...")
    print(f"done: {n} races -> {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="南関競馬 結果収集")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--place", choices=list(NANKAN_CODES), required=True)
    ap.add_argument("--out", default="data/results.jsonl")
    args = ap.parse_args()
    collect(args.year, args.place, out=args.out)


if __name__ == "__main__":
    main()
