#!/usr/bin/env python3
"""叩き2〜3戦目仮説の検証。夏バテで休み明け直後より2〜3戦叩いた馬が人気薄で穴を開けるか。
叩きN戦目 = 過去走の間隔に60日以上の休み明けがあり、その復帰から数えて今日がN戦目。
使い方: python3 scripts/tataki_val.py --place 大井 2026-07-22 2026-07-23 2026-07-24
"""
import sys, argparse, datetime
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from ana_recall import tataki_n, _REST_DAYS as REST  # 判定ロジックは本体に集約(§20)

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"


def rate(cell):
    g, n = cell
    return f"{g}/{n}={g/n:.0%}" if n else "0/0"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dates", nargs="+")
    ap.add_argument("--place", default="大井")
    ap.add_argument("--usui", type=int, default=6)
    a = ap.parse_args()
    c = PoliteClient()
    base = [0, 0]
    buckets = {1: [0, 0], 2: [0, 0], 3: [0, 0], "4+": [0, 0], "0(連続/不明)": [0, 0],
               "23合算": [0, 0], "3+合算": [0, 0]}
    n_races = 0
    for date in a.dates:
        ymd = date.replace("-", ""); today = datetime.date.fromisoformat(date)
        idx = c.get(CARD.format(r=day_index_race_id(ymd, a.place)), use_cache=True)
        races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[a.place]))
        for R, rid in sorted(races.items()):
            try:
                pc = P.parse_card_page(c.get(CARD.format(r=rid), use_cache=True), rid)
                rr = P.parse_result_page(c.get(PERF.format(r=rid), use_cache=True), rid)
            except Exception:
                continue
            n_races += 1
            fin = {row.umaban: (row.finish_pos, row.popularity) for row in rr.rows if row.umaban}
            for e in pc.entries:
                if not e.umaban or e.umaban not in fin:
                    continue
                f, pop = fin[e.umaban]
                if not (f and pop and pop >= a.usui):
                    continue
                good = 1 if f <= 3 else 0
                base[0] += good; base[1] += 1
                n = tataki_n(e, today)
                key = n if n in (1, 2, 3) else ("4+" if isinstance(n, int) and n >= 4 else "0(連続/不明)")
                buckets[key][0] += good; buckets[key][1] += 1
                if n in (2, 3):
                    buckets["23合算"][0] += good; buckets["23合算"][1] += 1
                if isinstance(n, int) and n >= 3:
                    buckets["3+合算"][0] += good; buckets["3+合算"][1] += 1
    b = base[0] / base[1] if base[1] else 0
    def lift(cell):
        r = cell[0] / cell[1] if cell[1] else 0
        return f"{rate(cell):14s} lift{(r/b if b else 0):.2f}"
    print(f"=== 叩きN戦目 lift検証 ({a.place} {a.dates[0]}〜{a.dates[-1]}, {n_races}R) ===")
    print(f" 母集団 = 人気薄(≥{a.usui}番人気) / 好走 = 3着内 / 休み明け={REST}日+")
    print(f" [ベース] 人気薄 全体   {rate(base):14s} (=lift1.00)")
    for k in [1, 2, 3, "4+", "23合算", "3+合算", "0(連続/不明)"]:
        lab = {1: "叩き1(復帰戦)", 2: "叩き2戦目", 3: "叩き3戦目", "4+": "叩き4戦目+",
               "23合算": "叩き2-3戦目", "3+合算": "叩き3戦目以降", "0(連続/不明)": "休明射程外"}[k]
        print(f" [{lab:10s}] {lift(buckets[k])}")


if __name__ == "__main__":
    main()
