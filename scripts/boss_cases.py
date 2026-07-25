#!/usr/bin/env python3
"""【ボス理論・実例抽出】集団の記憶(直接対決の勝ち越し)で獲れた万馬券の実例を出す。
時系列で対戦グラフを構築し、各レースで「人気薄(6番人気以下)なのに今日の相手に勝ち越している馬」
を検出。その馬が3着内に来て、かつ三連単が万馬券だったケースを列挙する。
※リーク無し(各レース時点までの対戦のみ使用)。

使い方: python3 scripts/boss_cases.py --from 2026-04-01 --to 2026-07-24 --warmup 2026-05-15
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
    """払戻: {券種: 円}。三連単/三連複/馬連 を拾う。"""
    s = BeautifulSoup(html, "html.parser")
    out = {}
    txt = re.sub(r"[ \t]+", " ", s.get_text("\n", strip=True))
    for kind in ["三連単", "三連複", "馬単", "馬連", "ワイド", "単勝"]:
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
    ap.add_argument("--to", dest="to", required=True)
    ap.add_argument("--warmup", default="2026-05-15")
    ap.add_argument("--usui", type=int, default=6)
    ap.add_argument("--min-enc", type=int, default=3, help="今日の相手との最低対戦数")
    ap.add_argument("--min-wr", type=float, default=0.6, help="勝ち越し判定の勝率")
    a = ap.parse_args()
    c = PoliteClient()
    d0 = datetime.date.fromisoformat(a.frm); d1 = datetime.date.fromisoformat(a.to)
    warm = datetime.date.fromisoformat(a.warmup)
    beat = defaultdict(int)
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
                rows = [(r.horse_name.strip(), r.finish_pos, r.popularity or 99, r.umaban)
                        for r in rr.rows if r.horse_name and r.finish_pos]
                if len(rows) < 6:
                    continue
                names = [n for n, f, p, u in rows]
                if day >= warm:
                    pay = payouts(html)
                    for name, fin, pop, um in rows:
                        if pop < a.usui:
                            continue
                        w = l = 0
                        detail = []
                        for o in names:
                            if o == name:
                                continue
                            wi, li = beat[(name, o)], beat[(o, name)]
                            w += wi; l += li
                            if wi or li:
                                detail.append(f"{o[:7]}{wi}勝{li}敗")
                        enc = w + l
                        if enc >= a.min_enc and w / enc >= a.min_wr:
                            n_flag += 1
                            if fin <= 3:
                                n_hit += 1
                                cases.append({"date": day.isoformat(), "place": tr, "R": R,
                                              "name": name, "um": um, "pop": pop, "fin": fin,
                                              "w": w, "l": l, "detail": detail[:4],
                                              "san": pay.get("三連単"), "fuku3": pay.get("三連複"),
                                              "umaren": pay.get("馬連")})
                # 履歴更新
                for i in range(len(rows)):
                    for j in range(i + 1, len(rows)):
                        n1, f1, _, _ = rows[i]; n2, f2, _, _ = rows[j]
                        if f1 < f2:
                            beat[(n1, n2)] += 1
                        elif f2 < f1:
                            beat[(n2, n1)] += 1
        day += datetime.timedelta(days=1)

    print(f"=== ボス理論の実例（人気薄≥{a.usui} × 今日の相手に{a.min_enc}戦以上で勝率{a.min_wr:.0%}以上）===")
    print(f" 期間 {a.warmup}〜{a.to} / 発火{n_flag}頭 → 3着内{n_hit}頭 (的中率{n_hit/max(1,n_flag):.1%})\n")
    # 万馬券(三連単10000円超)になったケースを優先表示
    man = [x for x in cases if x["san"] and x["san"] >= 10000]
    man.sort(key=lambda x: -(x["san"] or 0))
    print(f"■ 万馬券(三連単1万円超)に絡んだ実例: {len(man)}件 / 全的中{len(cases)}件\n")
    for x in man[:15]:
        print(f" {x['date']} {x['place']}{x['R']}R  {x['um']}番 {x['name'][:10]} "
              f"【{x['pop']}番人気 → {x['fin']}着】")
        print(f"    対戦成績 {x['w']}勝{x['l']}敗 : " + " / ".join(x["detail"]))
        print(f"    三連単 {x['san']:,}円" + (f" / 三連複 {x['fuku3']:,}円" if x["fuku3"] else "") +
              (f" / 馬連 {x['umaren']:,}円" if x["umaren"] else ""))
        print()
    if man:
        tot = [x["san"] for x in man if x["san"]]
        print(f" 万馬券ケースの三連単 平均{sum(tot)//len(tot):,}円 / 最高{max(tot):,}円")


if __name__ == "__main__":
    main()
