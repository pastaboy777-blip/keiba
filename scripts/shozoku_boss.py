#!/usr/bin/env python3
"""【仮説検証】所属(主戦場)×遠征先で「ボスになりやすい」馬はいるか。
本人仮説：「下級条件だと船橋の馬が浦和でボスになりやすい」。
各馬の主戦場を近走の場の最頻値で判定し、開催場ごとに
 ①主戦場別の複勝率(人気薄) ②★ボス発火率 ③下級条件(前半R)/上級(後半R)別
を出す。南関はサーキットの格差(船橋・大井 > 浦和・川崎と言われる)があるかを実測する。

使い方: python3 scripts/shozoku_boss.py --from 2026-01-01 --warmup 2026-03-01 --to 2026-07-24
"""
import sys, argparse, datetime
from collections import defaultdict, Counter
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"
TRACKS = ["浦和", "船橋", "大井", "川崎"]


def home_of(e, n=6):
    """主戦場＝近走n走の場の最頻値(2走以上で確定)。"""
    ps = [pr.place for pr in (e.recent_runs or [])[:n] if pr.place]
    if not ps:
        return None
    c = Counter(ps).most_common(1)[0]
    return c[0] if c[1] >= 2 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--warmup", required=True)
    ap.add_argument("--to", dest="to", required=True)
    ap.add_argument("--usui", type=int, default=6)
    a = ap.parse_args()
    c = PoliteClient()
    d0 = datetime.date.fromisoformat(a.frm); d1 = datetime.date.fromisoformat(a.to)
    warm = datetime.date.fromisoformat(a.warmup)
    hist = defaultdict(int)
    # cell[(開催場, クラス帯, 主戦場)] = [good, n, boss数]
    cell = defaultdict(lambda: [0, 0, 0])
    base = defaultdict(lambda: [0, 0])   # (開催場, クラス帯)

    day = d0
    while day <= d1:
        ymd = day.strftime("%Y%m%d")
        for tr in TRACKS:
            try:
                idx = c.get(CARD.format(r=day_index_race_id(ymd, tr)), use_cache=True)
                races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[tr]))
            except Exception:
                races = {}
            for R, rid in sorted(races.items()):
                try:
                    rr = P.parse_result_page(c.get(PERF.format(r=rid), use_cache=True), rid)
                except Exception:
                    continue
                rows = [(x.horse_name.strip(), x.finish_pos, x.popularity or 0, x.umaban)
                        for x in rr.rows if x.horse_name and x.finish_pos]
                if len(rows) < 6:
                    continue
                names = [n for n, f, p, u in rows]
                if day >= warm:
                    try:
                        pc = P.parse_card_page(c.get(CARD.format(r=rid), use_cache=True), rid)
                        emap = {e.umaban: e for e in pc.entries if e.umaban}
                    except Exception:
                        emap = {}
                    cls = "下級(1-6R)" if R <= 6 else "上級(7-12R)"
                    for name, fin, pop, um in rows:
                        if pop < a.usui:
                            continue
                        e = emap.get(um)
                        if not e:
                            continue
                        hm = home_of(e)
                        if not hm or hm not in TRACKS:
                            continue
                        g = 1 if fin <= 3 else 0
                        base[(tr, cls)][0] += g; base[(tr, cls)][1] += 1
                        w = l = 0
                        for o in names:
                            if o == name:
                                continue
                            w += hist[(name, o)]; l += hist[(o, name)]
                        enc = w + l
                        boss = 1 if (enc >= 3 and w / enc >= 0.6) else 0
                        k = (tr, cls, hm)
                        cell[k][0] += g; cell[k][1] += 1; cell[k][2] += boss
                for i in range(len(rows)):
                    for j in range(i + 1, len(rows)):
                        n1, f1 = rows[i][0], rows[i][1]; n2, f2 = rows[j][0], rows[j][1]
                        if f1 < f2:
                            hist[(n1, n2)] += 1
                        elif f2 < f1:
                            hist[(n2, n1)] += 1
        day += datetime.timedelta(days=1)

    print(f"=== 主戦場×開催場×クラス帯 (人気薄≥{a.usui}) {a.warmup}〜{a.to} ===")
    print(" 主戦場=近走6走の場の最頻値(2走以上)。★ボス率=その群が★ボス判定になる割合\n")
    for tr in TRACKS:
        for cls in ["下級(1-6R)", "上級(7-12R)"]:
            b = base[(tr, cls)]
            if b[1] < 60:
                continue
            br = b[0] / b[1]
            print(f"■ 開催={tr} {cls}  母数{b[1]} ベース複勝{br:.1%}")
            rows_ = []
            for hm in TRACKS:
                v = cell[(tr, cls, hm)]
                if v[1] < 25:
                    continue
                r = v[0] / v[1]
                rows_.append((r / br if br else 0, hm, v, r))
            rows_.sort(reverse=True)
            for lift, hm, v, r in rows_:
                tagexp = "（地元）" if hm == tr else "（遠征）"
                print(f"    主戦場{hm}{tagexp} {r:5.1%}({v[0]:>3}/{v[1]:>4}) lift{lift:4.2f}  "
                      f"★ボス率{v[2]/v[1]:4.0%}")
            print()


if __name__ == "__main__":
    main()
