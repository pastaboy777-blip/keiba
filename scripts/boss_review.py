#!/usr/bin/env python3
"""【ボス理論・開催まるごと答え合わせ】指定開催の全レースで、ボス理論が何を言い、
実際どうだったかをレース順(若い順)に並べる。発火→的中/不発を全部見せる。
※対戦履歴は開催前日までで構築(リーク無し)。
使い方: python3 scripts/boss_review.py --place 川崎 --from 2026-07-06 --to 2026-07-10 --hist-from 2026-01-01
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


def payoff(html):
    txt = re.sub(r"[ \t]+", " ", BeautifulSoup(html, "html.parser").get_text("\n", strip=True))
    m = re.search(r"三連単\s*\n?([\d\-\s,]*?)\n?\s*([\d,]{3,})\s*円", txt)
    return int(m.group(2).replace(",", "")) if m else None


def build_hist(c, d0, d1):
    """d0〜d1(含む)の南関全結果から有向対戦履歴を作る。"""
    hist = defaultdict(list)
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
                rows = [(x.horse_name.strip(), x.finish_pos) for x in rr.rows
                        if x.horse_name and x.finish_pos]
                for i in range(len(rows)):
                    for j in range(i + 1, len(rows)):
                        n1, f1 = rows[i]; n2, f2 = rows[j]
                        if f1 < f2:
                            hist[(n1, n2)].append((day, 1)); hist[(n2, n1)].append((day, 0))
                        elif f2 < f1:
                            hist[(n2, n1)].append((day, 1)); hist[(n1, n2)].append((day, 0))
        day += datetime.timedelta(days=1)
    return hist


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", required=True)
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", dest="to", required=True)
    ap.add_argument("--hist-from", default="2026-01-01")
    ap.add_argument("--usui", type=int, default=6)
    a = ap.parse_args()
    c = PoliteClient()
    d0 = datetime.date.fromisoformat(a.frm); d1 = datetime.date.fromisoformat(a.to)
    hist = build_hist(c, datetime.date.fromisoformat(a.hist_from), d0 - datetime.timedelta(days=1))
    print(f"=== ボス理論 開催まるごと答え合わせ {a.place} {a.frm}〜{a.to} ===")
    print(f" 対戦履歴: {a.hist_from}〜{d0 - datetime.timedelta(days=1)} (リーク無し) / 有向ペア{len(hist)}組")
    print(f" 発火条件: 人気薄(≥{a.usui}番人気) × [★ボス=3戦+勝率60%+] or [下=今日の上位3人気に勝利歴]\n")
    tot_flag = tot_hit = 0
    hits = []
    day = d0
    while day <= d1:
        ymd = day.strftime("%Y%m%d")
        try:
            idx = c.get(CARD.format(r=day_index_race_id(ymd, a.place)), use_cache=True)
            races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[a.place]))
        except Exception:
            races = {}
        if races:
            print(f"■■ {day} ■■")
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
            names = [n for n, f, p, u in rows]
            top3 = {n for n, f, p, u in rows if p and 1 <= p <= 3}
            san = payoff(html)
            fired = []
            for name, fin, pop, um in rows:
                if pop < a.usui:
                    continue
                w = l = 0
                for o in names:
                    if o == name:
                        continue
                    h = hist[(name, o)]
                    if h:
                        wi = sum(1 for _, r_ in h if r_ == 1)
                        w += wi; l += len(h) - wi
                enc = w + l
                boss = enc >= 3 and (w / enc) >= 0.6
                geko = [o for o in top3 if o != name and hist[(name, o)]
                        and any(r_ == 1 for _, r_ in hist[(name, o)])]
                if boss or geko:
                    tag = ("★ボス" if boss else "") + ("下剋上" if geko else "")
                    fired.append((um, name, pop, fin, w, l, tag, geko))
            if not fired:
                continue
            good = [x for x in fired if x[3] <= 3]
            tot_flag += len(fired); tot_hit += len(good)
            mark = "◎的中" if good else "・不発"
            print(f" {R:>2}R 三連単{f'{san:,}円' if san else '?'}  発火{len(fired)}頭 → {mark}")
            for um, name, pop, fin, w, l, tag, geko in fired:
                hit = "★" if fin <= 3 else " "
                gk = f"(1-3人気{geko[0][:8]}に勝利)" if geko else ""
                print(f"   {hit} {um:>2} {name[:11]:11s} {pop:>2}人気 → {fin:>2}着  対戦{w}勝{l}敗 {tag}{gk}")
                if fin <= 3 and san:
                    hits.append((san, f"{day} {R}R {name[:10]} {pop}人気{fin}着"))
        day += datetime.timedelta(days=1)
    print(f"\n=== 集計 ===")
    print(f" 発火 {tot_flag}頭 → 3着内 {tot_hit}頭 (的中率 {tot_hit/max(1,tot_flag):.1%})")
    man = [x for x in hits if x[0] >= 10000]
    print(f" 的中が絡んだレースのうち三連単1万円超: {len(man)}件")
    for s, lab in sorted(man, reverse=True)[:8]:
        print(f"   {s:>10,}円  {lab}")


if __name__ == "__main__":
    main()
