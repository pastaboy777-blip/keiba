#!/usr/bin/env python3
"""馬体重増減の穴検証(本人仮説:夏バテしない=前走比プラス体重の馬が人気薄で穴)。
前走比の増減で人気薄を層別し複勝率lift。月別(夏で強まるか)・叩き3+との重ねも。
使い方: python3 scripts/weight_val.py --from 2026-04-01 --to 2026-07-24
"""
import sys, argparse, datetime
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from ana_recall import tataki_n

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"


def wbucket(dw):
    """3走前比の増減(kg)。3走スパンなので境界を広めに。"""
    if dw is None:
        return "不明"
    if dw >= 10:
        return "大幅増(+10~)"
    if dw >= 4:
        return "増(+4~9)"
    if dw >= -3:
        return "維持(-3~+3)"
    if dw >= -9:
        return "減(-4~-9)"
    return "大幅減(~-10)"


ORDER = ["大幅増(+10~)", "増(+4~9)", "維持(-3~+3)", "減(-4~-9)", "大幅減(~-10)", "不明"]


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
    buck = {k: [0, 0] for k in ORDER}                 # 前走比増減バケツ(人気薄)
    incr_t3 = [0, 0]; incr_only = [0, 0]              # 増(+2~)×叩き3+ / 増単体
    by_month = {}                                     # mo -> {増:[g,n]}
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
                emap = {e.umaban: e for e in pc.entries if e.umaban}
                for row in rr.rows:
                    if not (row.umaban and row.finish_pos and row.popularity):
                        continue
                    if row.popularity < a.usui:
                        continue
                    e = emap.get(row.umaban)
                    if not e:
                        continue
                    recs = e.recent_runs or []
                    cw = e.horse_weight
                    # 3走前(recs[2])比。無ければ recs[:3] の最も古い実測にフォールバック。
                    pw = recs[2].horse_weight if len(recs) >= 3 and recs[2].horse_weight else None
                    if pw is None:
                        for pr in reversed(recs[:3]):
                            if pr.horse_weight:
                                pw = pr.horse_weight; break
                    dw = (cw - pw) if (cw and pw) else None
                    g = 1 if row.finish_pos <= 3 else 0
                    base[0] += g; base[1] += 1
                    bk = wbucket(dw); buck[bk][0] += g; buck[bk][1] += 1
                    is_incr = dw is not None and dw >= 4
                    n = tataki_n(e, day); is3 = isinstance(n, int) and n >= 3
                    if is_incr:
                        incr_only[0] += g; incr_only[1] += 1
                        if is3:
                            incr_t3[0] += g; incr_t3[1] += 1
                    mm = by_month.setdefault(mo, {"base": [0, 0], "incr": [0, 0]})
                    mm["base"][0] += g; mm["base"][1] += 1
                    if is_incr:
                        mm["incr"][0] += g; mm["incr"][1] += 1
        day += datetime.timedelta(days=1)

    def r(cc):
        return cc[0] / cc[1] if cc[1] else 0
    b = r(base)
    print(f"=== 馬体重(前走比)増減の穴検証 {a.frm}〜{a.to} ({a.tracks}) 人気薄≥{a.usui} 複勝率 ===")
    print(f" ベース {b:.1%}({base[0]}/{base[1]})")
    print("\n--- 前走比 増減バケツ別 ---")
    for k in ORDER:
        cc = buck[k]
        print(f" {k:12s} {r(cc):5.1%}({cc[0]:>3}/{cc[1]:>4}) lift{(r(cc)/b if b else 0):4.2f}")
    print("\n--- 体重増(+4kg~3走前比)×叩き3+ ---")
    print(f" 増 単体      {r(incr_only):5.1%}({incr_only[0]}/{incr_only[1]}) lift{r(incr_only)/b:4.2f}")
    print(f" 増 ×叩き3+   {r(incr_t3):5.1%}({incr_t3[0]}/{incr_t3[1]}) lift{r(incr_t3)/b:4.2f}")
    print("\n--- 体重増(+4kg~3走前比) 月別(夏で強まるか) ---")
    for mo in sorted(by_month):
        mm = by_month[mo]; bb = r(mm["base"])
        ci = mm["incr"]
        print(f" {mo} ベース{bb:5.1%} 増{r(ci):5.1%}({ci[0]:>2}/{ci[1]:>3}) lift{(r(ci)/bb if bb else 0):4.2f}")


if __name__ == "__main__":
    main()
