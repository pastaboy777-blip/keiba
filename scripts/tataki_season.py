#!/usr/bin/env python3
"""叩き3+効果の季節性検証(夏バテ仮説の本丸)。月別に人気薄の複勝率ベース・叩き3+・叩き3相性穴の
liftを出し、春→夏で効果が強まるか見る。データは全キャッシュ前提で高速。
使い方: python3 scripts/tataki_season.py --from 2026-04-01 --to 2026-07-24
"""
import sys, argparse, datetime
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from ana_recall import tataki_n, edges_for, field_pace, agari_pattern

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", dest="to", required=True)
    ap.add_argument("--usui", type=int, default=6)
    ap.add_argument("--tracks", default="浦和,船橋,大井,川崎")
    a = ap.parse_args()
    c = PoliteClient()
    tracks = a.tracks.split(",")
    d0 = datetime.date.fromisoformat(a.frm); d1 = datetime.date.fromisoformat(a.to)
    # month -> {"base":[g,n], "t3":[g,n], "combo":[g,n]}
    M = {}

    def cell(mo, key):
        return M.setdefault(mo, {"base": [0, 0], "t3": [0, 0], "combo": [0, 0]})[key]

    day = d0
    while day <= d1:
        ymd = day.strftime("%Y%m%d"); mo = day.strftime("%Y-%m")
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
                    rr = P.parse_result_page(c.get(PERF.format(r=rid), use_cache=True), rid)
                except Exception:
                    continue
                if not rr.rows or not rr.rows[0].finish_pos:
                    continue
                dist = getattr(pc, "distance", None)
                if not dist:
                    continue
                try:
                    from rakuten_ped import attach as _apd
                    _apd(_ch, pc.entries)
                except Exception:
                    pass
                pace, _ = field_pace(pc.entries)
                apct = agari_pattern(pc.entries)
                emap = {e.umaban: e for e in pc.entries if e.umaban}
                for row in rr.rows:
                    if not (row.umaban and row.finish_pos and row.popularity):
                        continue
                    if row.popularity < a.usui:
                        continue
                    e = emap.get(row.umaban)
                    if not e:
                        continue
                    g = 1 if row.finish_pos <= 3 else 0
                    cb = cell(mo, "base"); cb[0] += g; cb[1] += 1
                    n = tataki_n(e, day)
                    tags, _ = edges_for(e, dist, pace=pace, agari_pct=apct.get(row.umaban), today=day)
                    if isinstance(n, int) and n >= 3:
                        ct = cell(mo, "t3"); ct[0] += g; ct[1] += 1
                    if "叩き3相性穴" in tags:
                        cc = cell(mo, "combo"); cc[0] += g; cc[1] += 1
        day += datetime.timedelta(days=1)

    def r(cc):
        return cc[0] / cc[1] if cc[1] else 0
    print(f"=== 叩き3+効果の季節性 {a.frm}〜{a.to} ({a.tracks}) 人気薄≥{a.usui} 複勝率 ===")
    print(f" {'月':8s} {'ベース':>16s} {'叩き3+':>18s} {'叩き3相性穴':>20s}")
    for mo in sorted(M):
        d = M[mo]; b = r(d["base"])
        cb, ct, cc = d["base"], d["t3"], d["combo"]
        l3 = r(ct) / b if b else 0
        lc = r(cc) / b if b else 0
        print(f" {mo:8s} {r(cb):5.1%}({cb[0]:>3}/{cb[1]:>4}) "
              f"{r(ct):5.1%}({ct[0]:>2}/{ct[1]:>3})L{l3:4.2f} "
              f"{r(cc):5.1%}({cc[0]:>2}/{cc[1]:>3})L{lc:4.2f}")


if __name__ == "__main__":
    main()
