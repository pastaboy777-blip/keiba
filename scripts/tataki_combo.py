#!/usr/bin/env python3
"""叩き3+×他タグの"化ける組合せ"が本物のシナジーか、タグ単体の力かを切り分ける。
各タグXについて人気薄内で: X単体lift / 叩き3+単体lift / 併用lift、さらに
"Xの中で叩き3+が上乗せしてるか"(X&3+ の複勝率 vs X&非3+ の複勝率)を出す。
使い方: python3 scripts/tataki_combo.py --from 2026-04-01 --to 2026-07-24
"""
import sys, argparse, datetime
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from ana_recall import tataki_n, edges_for, field_pace, agari_pattern

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"
TAGS = ["持続巡航", "差し想定", "強差し", "血統湿", "道悪巧者", "斤量減", "距離短縮",
        "持続血統", "小型", "上がりP×短縮", "グリップ穴", "上がりP上位", "差し"]


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
    base = [0, 0]
    # タグごと: [X&3+], [X&非3+], [X全体]  各[good,n]
    cell = {t: {"x3": [0, 0], "xn": [0, 0], "x": [0, 0]} for t in TAGS}
    t3all = [0, 0]
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
                    base[0] += g; base[1] += 1
                    n = tataki_n(e, day)
                    is3 = isinstance(n, int) and n >= 3
                    if is3:
                        t3all[0] += g; t3all[1] += 1
                    tags, _ = edges_for(e, dist, pace=pace, agari_pct=apct.get(row.umaban), today=day)
                    for t in TAGS:
                        if t in tags:
                            cell[t]["x"][0] += g; cell[t]["x"][1] += 1
                            k = "x3" if is3 else "xn"
                            cell[t][k][0] += g; cell[t][k][1] += 1
        day += datetime.timedelta(days=1)
    b = base[0] / base[1] if base[1] else 0

    def r(cc):
        return cc[0] / cc[1] if cc[1] else 0
    print(f"=== 叩き3+×タグ シナジー切り分け {a.frm}〜{a.to} ({a.tracks}) ===")
    print(f" 人気薄(≥{a.usui})母数{base[1]} ベース複勝{b:.1%} / 叩き3+単体 {r(t3all):.1%} lift{r(t3all)/b:.2f}")
    print(f"\n {'タグ':10s} {'X単体':>16s} {'X&叩き3+':>16s} {'X&非3+':>14s}  判定")
    for t in TAGS:
        cx = cell[t]["x"]; c3 = cell[t]["x3"]; cn = cell[t]["xn"]
        lx = r(cx) / b if b else 0
        l3 = r(c3) / b if b else 0
        # Xの中で叩き3+が上乗せしてるか= X&3+ 率 vs X&非3+ 率
        up = r(c3) - r(cn)
        verdict = "★真シナジー" if (c3[1] >= 8 and up > 0.02) else ("－上乗せ無" if c3[1] >= 8 else "n小")
        print(f" {t:10s} {r(cx):5.1%}({cx[0]:>3}/{cx[1]:>4})L{lx:4.2f} "
              f"{r(c3):5.1%}({c3[0]:>2}/{c3[1]:>3})L{l3:4.2f} "
              f"{r(cn):5.1%}({cn[0]:>3}/{cn[1]:>4})  {verdict}(差{up:+.1%})")


if __name__ == "__main__":
    main()
