#!/usr/bin/env python3
"""条件シグネチャ検出器のlift検証。人気薄(popularity>=6)母集団の中で、
今日=ベスト距離帯(◎距)/ 個性ハマり(★=距離+場一致) の馬が実際に好走率を上げるか。
過去走はレース時点のもの(=カードのrecent_runs)なのでリークなし。
使い方: python3 scripts/horse_profile_val.py --place 大井 2026-07-22 2026-07-23 2026-07-24
"""
import sys, argparse
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from horse_profile import band, profile

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"
NINKI_USUI = 6  # 人気薄の定義(6番人気以下)


def rate(cell):
    g, n = cell
    return f"{g}/{n}={g/n:.0%}" if n else f"0/0"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dates", nargs="+")
    ap.add_argument("--place", default="大井")
    ap.add_argument("--usui", type=int, default=NINKI_USUI)
    a = ap.parse_args()
    c = PoliteClient()
    # セル = [好走数, 母数]。好走=finish<=3
    base = [0, 0]; md = [0, 0]; mp = [0, 0]; hit = [0, 0]; other = [0, 0]
    strong = [0, 0]  # ◎距 かつ その帯の好走率>=40%(=本物の得意)
    tan_md = [0, 0]  # ◎距 かつ 距離短縮(既存lift1.86シグナルとの重ね)
    n_races = 0
    for date in a.dates:
        ymd = date.replace("-", "")
        idx = c.get(CARD.format(r=day_index_race_id(ymd, a.place)), use_cache=True)
        races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[a.place]))
        for R, rid in sorted(races.items()):
            try:
                pc = P.parse_card_page(c.get(CARD.format(r=rid), use_cache=True), rid)
                rr = P.parse_result_page(c.get(PERF.format(r=rid), use_cache=True), rid)
            except Exception:
                continue
            dist = getattr(pc, "distance", None)
            if not dist:
                continue
            tb = band(dist)
            n_races += 1
            fin = {row.umaban: (row.finish_pos, row.popularity) for row in rr.rows if row.umaban}
            prof = {e.umaban: profile(e) for e in pc.entries if e.umaban}
            for e in pc.entries:
                if not e.umaban or e.umaban not in fin:
                    continue
                f, pop = fin[e.umaban]
                if not (f and pop and pop >= a.usui):  # 人気薄のみ
                    continue
                good = 1 if f <= 3 else 0
                base[0] += good; base[1] += 1
                bd, bp, ds, _ = prof[e.umaban]
                is_md = bool(bd and bd == tb)
                is_mp = bool(bp == a.place)
                if is_md:
                    md[0] += good; md[1] += 1
                    cell = ds.get(tb, [0, 0])
                    if cell[1] and cell[0] / cell[1] >= 0.40:
                        strong[0] += good; strong[1] += 1
                    dists = [pr.distance for pr in (e.recent_runs or []) if pr.distance]
                    if dists and dists[0] and dists[0] > dist:
                        tan_md[0] += good; tan_md[1] += 1
                if is_mp:
                    mp[0] += good; mp[1] += 1
                if is_md and is_mp:
                    hit[0] += good; hit[1] += 1
                if not is_md:
                    other[0] += good; other[1] += 1
    b = base[0] / base[1] if base[1] else 0
    def lift(cell):
        r = cell[0] / cell[1] if cell[1] else 0
        return f"{rate(cell):14s} lift{(r/b if b else 0):.2f}"
    print(f"=== 条件シグネチャ lift検証 ({a.place} {a.dates[0]}〜{a.dates[-1]}, {n_races}R) ===")
    print(f" 母集団 = 人気薄(≥{a.usui}番人気) / 好走 = 3着内")
    print(f" [ベース] 人気薄 全体   {rate(base):14s} (=lift1.00基準)")
    print(f" [◎距]   今日ベスト距離 {lift(md)}")
    print(f" [◎場]   大井ベスト場   {lift(mp)}")
    print(f" [★ハマり]距離+場一致   {lift(hit)}")
    print(f" [◎距★]  帯好走率≥40%   {lift(strong)}")
    print(f" [◎距×短縮]重ね        {lift(tan_md)}")
    print(f" [参考]  ◎距ではない    {lift(other)}")


if __name__ == "__main__":
    main()
