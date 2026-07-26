#!/usr/bin/env python3
"""【仮説検証】ボスに立ち向かう"負けん気"の血統は存在するか。
2つの角度で測る：
 ①反骨型：今日の相手に負け越している(子分)のに走る父 = 序列を覆す血
 ②下剋上型：下剋上シグナル(今日の上位3人気に過去勝利)が出た時、実際に走る父
さらに「格上と戦った経験」の指標として、レース内の相対的な格差も見る。

使い方: python3 scripts/gekokujo_blood.py --from 2026-01-01 --warmup 2026-03-01 --to 2026-07-24
"""
import sys, argparse, datetime
from collections import defaultdict
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"
TRACKS = ["浦和", "船橋", "大井", "川崎"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--warmup", required=True)
    ap.add_argument("--to", dest="to", required=True)
    ap.add_argument("--usui", type=int, default=6)
    ap.add_argument("--min-n", type=int, default=15)
    a = ap.parse_args()
    c = PoliteClient()
    d0 = datetime.date.fromisoformat(a.frm); d1 = datetime.date.fromisoformat(a.to)
    warm = datetime.date.fromisoformat(a.warmup)
    hist = defaultdict(list)
    base = [0, 0]
    S = defaultdict(lambda: {"all": [0, 0], "kobun": [0, 0], "geko": [0, 0], "vsboss": [0, 0]})

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
                    top3 = {n for n, f, p, u in rows if p and 1 <= p <= 3}
                    # レース内に★ボスがいるか(格上の存在)
                    has_boss = False
                    for nm, fn, pp, uu in rows:
                        w = l = 0
                        for o in names:
                            if o == nm:
                                continue
                            h = hist[(nm, o)]
                            if h:
                                wi = sum(1 for _, r_ in h if r_ == 1)
                                w += wi; l += len(h) - wi
                        if w + l >= 3 and w / (w + l) >= 0.6:
                            has_boss = True
                            break
                    for name, fin, pop, um in rows:
                        if pop < a.usui:
                            continue
                        e = emap.get(um)
                        if not e or not e.sire:
                            continue
                        sire = e.sire.strip()
                        g = 1 if fin <= 3 else 0
                        base[0] += g; base[1] += 1
                        w = l = 0
                        for o in names:
                            if o == name:
                                continue
                            h = hist[(name, o)]
                            if h:
                                wi = sum(1 for _, r_ in h if r_ == 1)
                                w += wi; l += len(h) - wi
                        enc = w + l
                        geko = any(hist[(name, o)] and any(r_ == 1 for _, r_ in hist[(name, o)])
                                   for o in top3 if o != name)
                        d = S[sire]
                        d["all"][0] += g; d["all"][1] += 1
                        if enc >= 3 and w / enc <= 0.3:
                            d["kobun"][0] += g; d["kobun"][1] += 1      # ①反骨: 負け越しなのに走るか
                        if geko:
                            d["geko"][0] += g; d["geko"][1] += 1        # ②下剋上発火時に走るか
                        if has_boss:
                            d["vsboss"][0] += g; d["vsboss"][1] += 1    # ③格上がいるレースで走るか
                for i in range(len(rows)):
                    for j in range(i + 1, len(rows)):
                        n1, f1 = rows[i][0], rows[i][1]; n2, f2 = rows[j][0], rows[j][1]
                        if f1 < f2:
                            hist[(n1, n2)].append((day, 1)); hist[(n2, n1)].append((day, 0))
                        elif f2 < f1:
                            hist[(n2, n1)].append((day, 1)); hist[(n1, n2)].append((day, 0))
        day += datetime.timedelta(days=1)

    b = base[0] / base[1] if base[1] else 0
    def r(cc):
        return cc[0] / cc[1] if cc[1] else 0
    print(f"=== ボスに立ち向かう血統 {a.warmup}〜{a.to} 人気薄≥{a.usui} ===")
    print(f" 人気薄n={base[1]} ベース複勝{b:.1%}\n")
    for key, title, note in [
        ("kobun", "①反骨の血：今日の相手に負け越し(子分)なのに走る父",
         "※子分全体のliftは0.65。それを大きく上回る父＝序列を覆す血"),
        ("geko", "②下剋上の血：格上(上位3人気)に勝利歴がある時に走る父",
         "※下剋上全体のliftは1.49-1.55"),
        ("vsboss", "③格上がいるレースで走る父", "※レース内に★ボスが存在する状況"),
    ]:
        print(f"--- {title} ---")
        print(f" {note}")
        rows_ = [(r(d[key]) / b if b else 0, s, d) for s, d in S.items() if d[key][1] >= a.min_n]
        rows_.sort(reverse=True)
        for lift, s, d in rows_[:8]:
            la = r(d["all"]) / b if b else 0
            print(f" {s[:16]:16s} {r(d[key]):5.1%}({d[key][0]:>3}/{d[key][1]:>4}) lift{lift:4.2f} "
                  f"(父全体lift{la:4.2f} 上乗せ{lift-la:+5.2f})")
        print()


if __name__ == "__main__":
    main()
