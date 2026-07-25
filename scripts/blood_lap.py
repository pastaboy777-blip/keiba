#!/usr/bin/env python3
"""血統×ラップ形の適性検証(本人着眼:「⑤で緩むと食う」適性は血統に出るか)。
各レースを「中盤インジェクション有(締)/無(緩)」で分類し、父ごとに
"緩レース複勝率 − 締レース複勝率(=差)"を出す。プラス大=緩むと食う血(折り合い/差し)、
マイナス=締まる流れ向き(先行/持続)。netkeiba不要(rakutenラップ=pace_day.parse_laps)。
使い方: python3 scripts/blood_lap.py --from 2026-04-01 --to 2026-07-24
"""
import sys, argparse, datetime
from collections import defaultdict
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
import pace_day as PD

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"


def race_shape(laps):
    """'緩'(中盤インジェクション無=減速基調) / '締'(中盤に早い区間=再加速) / None。
    定義: 序盤最速(2-3F目のmin)より速い内部区間(4F目〜終い-1)があれば'締'(インジェクション)。"""
    if len(laps) < 5:
        return None
    early = min(laps[1], laps[2])            # 序盤の速い区間
    interior = laps[3:-1]                     # 4F目〜ラスト1F手前(道中〜勝負どころ)
    if not interior:
        return None
    inj = any(x <= early for x in interior)  # 道中で序盤最速以上に締め直した=インジェクション
    return "締" if inj else "緩"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", dest="to", required=True)
    ap.add_argument("--min-n", type=int, default=25)
    ap.add_argument("--tracks", default="浦和,船橋,大井,川崎")
    ap.add_argument("--usui", type=int, default=0, help=">0で人気薄限定")
    a = ap.parse_args()
    c = PoliteClient()
    tracks = a.tracks.split(",")
    d0 = datetime.date.fromisoformat(a.frm); d1 = datetime.date.fromisoformat(a.to)
    # sire -> {"緩":[good,n], "締":[good,n]}
    sire = defaultdict(lambda: {"緩": [0, 0], "締": [0, 0]})
    base = {"緩": [0, 0], "締": [0, 0]}
    nrace = {"緩": 0, "締": 0}
    day = d0
    while day <= d1:
        ymd = day.strftime("%Y%m%d")
        for tr in tracks:
            try:
                idx = c.get(CARD.format(r=day_index_race_id(ymd, tr)), use_cache=True)
                races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[tr]))
            except Exception:
                races = {}
            for R, rid in sorted(races.items()):
                try:
                    _ch = c.get(CARD.format(r=rid), use_cache=True)
                    pc = P.parse_card_page(_ch, rid)
                    html = c.get(PERF.format(r=rid), use_cache=True)
                    rr = P.parse_result_page(html, rid)
                except Exception:
                    continue
                if not rr.rows or not rr.rows[0].finish_pos:
                    continue
                shape = race_shape(PD.parse_laps(html))
                if shape is None:
                    continue
                nrace[shape] += 1
                try:
                    from rakuten_ped import attach as _apd
                    _apd(_ch, pc.entries)
                except Exception:
                    pass
                emap = {e.umaban: e for e in pc.entries if e.umaban}
                for row in rr.rows:
                    if not (row.umaban and row.finish_pos):
                        continue
                    if a.usui and (not row.popularity or row.popularity < a.usui):
                        continue
                    e = emap.get(row.umaban)
                    if not e or not e.sire:
                        continue
                    g = 1 if row.finish_pos <= 3 else 0
                    base[shape][0] += g; base[shape][1] += 1
                    s = e.sire.strip()
                    sire[s][shape][0] += g; sire[s][shape][1] += 1
        day += datetime.timedelta(days=1)

    def r(cell):
        return cell[0] / cell[1] if cell[1] else 0
    bq, bt = r(base["緩"]), r(base["締"])
    tag = f"人気薄≥{a.usui}" if a.usui else "全馬"
    print(f"=== 血統×ラップ形 {a.frm}〜{a.to}({a.tracks}) {tag} ===")
    print(f" レース分類: 緩(中だるみ){nrace['緩']}R / 締(インジェクション){nrace['締']}R")
    print(f" ベース複勝: 緩{bq:.1%} 締{bt:.1%}")
    rows = []
    for s, d in sire.items():
        nq, nt = d["緩"][1], d["締"][1]
        if nq + nt < a.min_n or nq < 8 or nt < 8:
            continue
        diff = r(d["緩"]) - r(d["締"])
        rows.append((diff, s, d))
    rows.sort(reverse=True)
    print(f"\n[緩むと食う血 TOP10 (緩複勝−締複勝 が大)]  n>={a.min_n}")
    print(f" {'父':16s} {'緩(中だるみ)':>16s} {'締(締まる)':>14s} {'差':>6s}")
    for diff, s, d in rows[:10]:
        print(f" {s[:16]:16s} {r(d['緩']):5.1%}({d['緩'][0]:>2}/{d['緩'][1]:>3}) {r(d['締']):5.1%}({d['締'][0]:>2}/{d['締'][1]:>3}) {diff:+5.1%}")
    print(f"\n[締まる流れ向きの血 BOTTOM10 (差がマイナス)]")
    for diff, s, d in rows[-10:][::-1]:
        print(f" {s[:16]:16s} {r(d['緩']):5.1%}({d['緩'][0]:>2}/{d['緩'][1]:>3}) {r(d['締']):5.1%}({d['締'][0]:>2}/{d['締'][1]:>3}) {diff:+5.1%}")


if __name__ == "__main__":
    main()
