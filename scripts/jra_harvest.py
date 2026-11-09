"""中央競馬の「結果 + ラップ + コーナー通過順 + 払戻」を期間まとめて集める(ローカル実行)。

    python3 scripts/jra_harvest.py --from 2023-11-09 --to 2026-11-08 --out data/jra/races.jsonl
    python3 scripts/jra_harvest.py --check 202605050211     # まず1ページだけ試す

1日ずつ:  db.netkeiba.com/race/list/<YYYYMMDD>/ でその日のレースIDを拾い、
          中央(場コード01〜10)だけ /race/<race_id>/ を取ってパースする。
出力:     1行=1レースの JSONL(scraping/db_race.py の形式。dataset.load_races で読める)。

守ること(scripts/ana/harvest.py に書いた 2026-10-24 の教訓と同じ):
  - 既定 3.0 秒間隔・1本ずつ。同時に走らせない
  - resumable: 出力済みの race_id と済んだ日付は飛ばすので、止めても積み上がる
  - 200 以外が返ったら**その場で止める**。リトライで粘らない。時間を空けて再開する
  - robots.txt と利用規約を尊重し、個人利用の範囲で使う

3年分 ≒ 開催日 約870日・約10,400鞍。3秒間隔で約9時間(日付一覧 +1時間弱)。
--newest-first で新しい日付から集めるので、途中で止めても直近が揃う。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.scraping.db_race import parse_db_race
from nankeiba.scraping.race_id import is_jra

LIST_URL = "https://db.netkeiba.com/race/list/{ymd}/"
RACE_URL = "https://db.netkeiba.com/race/{race_id}/"


class Stop(Exception):
    pass


class Fetcher:
    def __init__(self, sleep: float):
        try:
            import requests
        except ImportError:
            raise SystemExit("requests が必要です: pip install requests")
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "nankeiba-research/0.1 (personal use)"
        self.sleep = sleep
        self.last = 0.0

    def get(self, url: str) -> str:
        wait = self.sleep - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.time()
        r = self.s.get(url, timeout=20)
        if r.status_code != 200:
            raise Stop(f"HTTP {r.status_code}: {url}")
        r.encoding = "EUC-JP" if "euc" in (r.headers.get("content-type", "").lower() + r.text[:600].lower()) else (r.apparent_encoding or "utf-8")
        return r.text


def daterange(a: dt.date, b: dt.date, newest_first: bool):
    days = [a + dt.timedelta(n) for n in range((b - a).days + 1)]
    return reversed(days) if newest_first else days


def main() -> None:
    ap = argparse.ArgumentParser(description="中央競馬 結果+ラップ収集")
    ap.add_argument("--from", dest="frm")
    ap.add_argument("--to")
    ap.add_argument("--out", default="data/jra/races.jsonl")
    ap.add_argument("--sleep", type=float, default=3.0)
    ap.add_argument("--newest-first", action="store_true", default=True)
    ap.add_argument("--check", help="race_id 1つだけ取得して表示")
    a = ap.parse_args()
    f = Fetcher(a.sleep)

    if a.check:
        d = parse_db_race(f.get(RACE_URL.format(race_id=a.check)), a.check)
        if not d:
            print("着順表が見つかりません(パース失敗 or 未確定)")
            return
        print(f"{d['date']} {d['place']} {d['surface']}{d['distance']}m {d['baba']} {d['field_size']}頭")
        print("ラップ:", d["lap"])
        print("4角:", d["corners"].get("4"))
        print("三連複:", d["payouts"].get("trio"))
        for r in d["result"][:5]:
            print(r)
        return

    if not (a.frm and a.to):
        ap.error("--from と --to を指定してください(例 --from 2023-11-09 --to 2026-11-08)")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done_ids = set()
    if out.exists():
        for line in out.open(encoding="utf-8"):
            try:
                done_ids.add(json.loads(line)["race_id"])
            except Exception:  # noqa: BLE001
                pass
    days_path = out.with_suffix(".days")
    done_days = set(days_path.read_text().split()) if days_path.exists() else set()

    a0 = dt.date.fromisoformat(a.frm)
    b0 = dt.date.fromisoformat(a.to)
    n_new = 0
    try:
        with out.open("a", encoding="utf-8") as fo, days_path.open("a") as fd:
            for day in daterange(a0, b0, a.newest_first):
                ymd = day.strftime("%Y%m%d")
                if ymd in done_days:
                    continue
                ids = sorted({x for x in re.findall(r"/race/(\d{12})/", f.get(LIST_URL.format(ymd=ymd)))
                              if is_jra(x)})
                for rid in ids:
                    if rid in done_ids:
                        continue
                    d = parse_db_race(f.get(RACE_URL.format(race_id=rid)), rid)
                    if d:
                        fo.write(json.dumps(d, ensure_ascii=False) + "\n")
                        fo.flush()
                        done_ids.add(rid)
                        n_new += 1
                fd.write(ymd + "\n")
                fd.flush()
                if ids:
                    print(f"{day} {len(ids)}鞍  (累計 {len(done_ids)})", flush=True)
    except Stop as e:
        print(f"\n止めました: {e}\n時間を空けて同じコマンドで再開できます(済んだ分は飛ばします)。")
    except KeyboardInterrupt:
        print("\n中断。同じコマンドで再開できます。")
    print(f"今回 {n_new} 鞍 / 合計 {len(done_ids)} 鞍 → {out}")


if __name__ == "__main__":
    main()
