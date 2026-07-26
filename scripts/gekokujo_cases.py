#!/usr/bin/env python3
"""【下剋上シグナル・実例抽出】§28で最強だった「人気薄が今日の上位人気に過去勝っている」
シグナルの的中例を、誰にいつ勝っていたか＋配当付きで列挙する。
園田7/23のミスターエヌ型(1.8倍人気に3ヶ月前に勝っていた9番人気が1着)を機械的に探す。
使い方: python3 scripts/gekokujo_cases.py --from 2026-01-01 --warmup 2026-04-01 --to 2026-07-24
"""
import sys, re, argparse, datetime
from collections import defaultdict
from bs4 import BeautifulSoup
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"
TRACKS = ["浦和", "船橋", "大井", "川崎"]


def payouts(html):
    s = BeautifulSoup(html, "html.parser")
    txt = re.sub(r"[ \t]+", " ", s.get_text("\n", strip=True))
    out = {}
    for kind in ["三連単", "三連複", "馬連"]:
        m = re.search(kind + r"\s*\n?([\d\-\s,]*?)\n?\s*([\d,]{3,})\s*円", txt)
        if m:
            try:
                out[kind] = int(m.group(2).replace(",", ""))
            except Exception:
                pass
    return out


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
    hist = defaultdict(list)
    cases = []
    n_flag = n_hit = 0
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
                    html = c.get(PERF.format(r=rid), use_cache=True)
                    rr = P.parse_result_page(html, rid)
                except Exception:
                    continue
                rows = [(x.horse_name.strip(), x.finish_pos, x.popularity or 0, x.umaban)
                        for x in rr.rows if x.horse_name and x.finish_pos]
                if len(rows) < 6:
                    continue
                if day >= warm:
                    pay = payouts(html)
                    top3 = [(n, p, f) for n, f, p, u in rows if p and 1 <= p <= 3]
                    for name, fin, pop, um in rows:
                        if pop < a.usui:
                            continue
                        beaten = []
                        for on, op, of in top3:
                            if on == name:
                                continue
                            h = hist[(name, on)]
                            wins = [(dt) for dt, r_ in h if r_ == 1]
                            if wins:
                                beaten.append((on, op, of, wins[-1], len(wins), len(h) - len(wins)))
                        if not beaten:
                            continue
                        n_flag += 1
                        if fin <= 3:
                            n_hit += 1
                            cases.append({"date": day.isoformat(), "place": tr, "R": R, "um": um,
                                          "name": name, "pop": pop, "fin": fin, "beaten": beaten,
                                          "san": pay.get("三連単"), "f3": pay.get("三連複")})
                for i in range(len(rows)):
                    for j in range(i + 1, len(rows)):
                        n1, f1 = rows[i][0], rows[i][1]; n2, f2 = rows[j][0], rows[j][1]
                        if f1 < f2:
                            hist[(n1, n2)].append((day, 1)); hist[(n2, n1)].append((day, 0))
                        elif f2 < f1:
                            hist[(n2, n1)].append((day, 1)); hist[(n1, n2)].append((day, 0))
        day += datetime.timedelta(days=1)

    print(f"=== 下剋上シグナル 的中実例（人気薄≥{a.usui} × 今日の上位3人気に過去勝利）===")
    print(f" 期間 {a.warmup}〜{a.to} / 発火{n_flag}頭 → 3着内{n_hit}頭 (的中率{n_hit/max(1,n_flag):.1%})\n")
    man = [x for x in cases if x["san"] and x["san"] >= 10000]
    man.sort(key=lambda x: -(x["san"] or 0))
    print(f"■ 万馬券(三連単1万円超)に絡んだ的中: {len(man)}件 / 全的中{len(cases)}件\n")
    for x in man[:14]:
        print(f" {x['date']} {x['place']}{x['R']}R  {x['um']}番 {x['name'][:11]} "
              f"【{x['pop']}番人気 → {x['fin']}着】 三連単 {x['san']:,}円")
        for on, op, of, last, w, l in x["beaten"]:
            print(f"    ↳ 今日の{op}番人気 {on[:11]}({of}着) に {last} で勝利済({w}勝{l}敗)")
        print()
    if man:
        t = [x["san"] for x in man]
        print(f" 万馬券ケース: 平均{sum(t)//len(t):,}円 / 最高{max(t):,}円")


if __name__ == "__main__":
    main()
