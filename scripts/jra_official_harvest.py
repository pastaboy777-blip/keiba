"""JRA公式(www.jra.go.jp)から中央の「結果 + ラップ + コーナー通過順 + 払戻」を月単位で集める。

    python3 scripts/jra_official_harvest.py --from 2023-11 --to 2026-11 --out data/jra/races.jsonl

月 → 開催日 → レース の順にページ内リンクをたどる(src/nankeiba/scraping/jra_official.py)。
出力は netkeiba 版(jra_harvest.py)と同じ JSONL 形式・同じ race_id なので同じファイルに足せる。
既にある race_id は飛ばす。新しい月から順に集める。

守ること: 既定 3.0 秒間隔・1本ずつ。503 は60秒あけて1回だけやり直し、それ以外の 200 以外はその場で止める。
済んだ開催日は official.days に記録して次回は飛ばす。
robots.txt は Disallow なし(2026-11-10 確認)。個人利用の範囲で。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.scraping.jra_official import links, month_checksums, parse_race, race_id_of  # noqa: E402

URL = "https://www.jra.go.jp/JRADB/accessS.html"
SEARCH = "pw01skl00999999/B3"


class Stop(Exception):
    pass


class Fetcher:
    def __init__(self, sleep: float):
        import requests
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "nankeiba-research/0.1 (personal use)"
        self.sleep, self.last = sleep, 0.0

    def post(self, cname: str) -> str:
        wait = self.sleep - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.time()
        r = self.s.post(URL, data={"cname": cname}, timeout=30)
        if r.status_code == 503:          # 一時的な混雑。1回だけ60秒あけてやり直す
            time.sleep(60)
            self.last = time.time()
            r = self.s.post(URL, data={"cname": cname}, timeout=30)
        if r.status_code != 200:
            raise Stop(f"HTTP {r.status_code}: {cname}")
        return r.content.decode("shift_jis", errors="replace")


def months(frm: str, to: str):
    y, m = map(int, to.split("-"))
    y0, m0 = map(int, frm.split("-"))
    while (y, m) >= (y0, m0):
        yield y, m
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default="2023-11")
    ap.add_argument("--to", default="2026-11")
    ap.add_argument("--out", default="data/jra/races.jsonl")
    ap.add_argument("--sleep", type=float, default=3.0)
    a = ap.parse_args()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        for line in out.open(encoding="utf-8"):
            try:
                d = json.loads(line)
                if d.get("distance"):
                    done.add(d["race_id"])
            except Exception:  # noqa: BLE001
                pass
    days_path = out.with_name("official.days")
    done_days = set(days_path.read_text().split()) if days_path.exists() else set()
    f = Fetcher(a.sleep)
    n_new = 0
    try:
        ck = month_checksums(f.post(SEARCH))
        with out.open("a", encoding="utf-8") as fo:
            for y, m in months(a.frm, a.to):
                key = f"{y % 100:02d}{m:02d}"
                if key not in ck:
                    continue
                prefix = "pw01skl00" if (y, m) >= (2026, 11) else "pw01skl10"
                days = links(f.post(f"{prefix}{y:04d}{m:02d}/{ck[key]}"), "pw01srl")
                for day in days:
                    if day in done_days:
                        continue
                    races = links(f.post(day), "pw01sde")
                    todo = [c for c in races if race_id_of(c) and race_id_of(c) not in done]
                    for c in todo:
                        rid = race_id_of(c)
                        d = parse_race(f.post(c), rid)
                        if d:
                            fo.write(json.dumps(d, ensure_ascii=False) + "\n")
                            fo.flush()
                            done.add(rid)
                            n_new += 1
                    with days_path.open("a") as fd:
                        fd.write(day + "\n")
                    done_days.add(day)
                    if todo:
                        print(f"{y}-{m:02d} {day[9:]} {len(todo)}鞍  (累計 {len(done)})", flush=True)
    except Stop as e:
        print(f"\n止めました: {e}\n時間を空けて同じコマンドで再開できます(済んだ分は飛ばします)。")
    except KeyboardInterrupt:
        print("\n中断。同じコマンドで再開できます。")
    print(f"今回 {n_new} 鞍 / 合計 {len(done)} 鞍 → {out}")


if __name__ == "__main__":
    main()
