#!/usr/bin/env python3
"""【H2Hアラート検証】「今日の上位人気に1戦でも先着している人気薄」を対戦回数で層別。
本人の体感：高知ファイナルで「1-0の弱いアラート」が2着3着を当て、「完封を根拠にした軸」が飛んだ。
→ 1戦だけの勝ちは本当に弱いのか？完封の方が強いのか？を実測する。

層別：
 A. 1戦1勝のみ(そのライバルと1回だけ対戦し勝った)
 B. 完封(2戦以上・全勝)
 C. 勝ち越し(2戦以上・勝率>50%だが負けもある)
 D. 五分/負け越しだが勝ちはある(mixed)
 E. アラート無し(上位人気に勝利歴なし)

使い方: python3 scripts/h2h_alert.py --from 2026-01-01 --warmup 2026-07-01 --to 2026-07-24
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
    ap.add_argument("--topn", type=int, default=3, help="「上位人気」の範囲")
    a = ap.parse_args()
    c = PoliteClient()
    d0 = datetime.date.fromisoformat(a.frm); d1 = datetime.date.fromisoformat(a.to)
    warm = datetime.date.fromisoformat(a.warmup)
    hist = defaultdict(list)     # (A,B) -> [(date, 1=Aの勝ち/0=負け)]
    base = [0, 0]
    C = {}
    def add(k, g):
        cc = C.setdefault(k, [0, 0]); cc[0] += g; cc[1] += 1

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
                rows = [(x.horse_name.strip(), x.finish_pos, x.popularity or 0)
                        for x in rr.rows if x.horse_name and x.finish_pos]
                if len(rows) < 6:
                    continue
                if day >= warm:
                    tops = [n for n, f, p in rows if p and 1 <= p <= a.topn]
                    fav = next((n for n, f, p in rows if p == 1), None)
                    for name, fin, pop in rows:
                        if pop < a.usui:
                            continue
                        g = 1 if fin <= 3 else 0
                        base[0] += g; base[1] += 1
                        # 上位人気それぞれとの対戦成績を集める
                        best = None      # このアラートの「質」
                        onefight = False; kanpu = False; katikoshi = False; mixed = False
                        for o in tops:
                            if o == name:
                                continue
                            h = hist[(name, o)]
                            if not h:
                                continue
                            w = sum(1 for _, r_ in h if r_ == 1)
                            n = len(h)
                            if w == 0:
                                continue
                            if n == 1:
                                onefight = True
                            elif w == n:
                                kanpu = True
                            elif w > n / 2:
                                katikoshi = True
                            else:
                                mixed = True
                        any_alert = onefight or kanpu or katikoshi or mixed
                        if not any_alert:
                            add("E.アラート無し(上位人気に勝利歴なし)", g)
                            continue
                        add("◆アラート全体", g)
                        # 最良の質で分類(完封>勝ち越し>1戦1勝>mixed)
                        if kanpu:
                            add("B.完封(2戦以上・全勝)", g)
                        elif katikoshi:
                            add("C.勝ち越し(2戦以上)", g)
                        elif onefight:
                            add("A.1戦1勝のみ", g)
                        else:
                            add("D.負け越しだが勝ちあり", g)
                        # 1番人気限定版
                        if fav and fav != name:
                            h = hist[(name, fav)]
                            if h and any(r_ == 1 for _, r_ in h):
                                w = sum(1 for _, r_ in h if r_ == 1)
                                add("★1番人気に勝利(1戦1勝)" if len(h) == 1 else
                                    ("★1番人気を完封" if w == len(h) else "★1番人気に勝ちあり(複数戦)"), g)
                for i in range(len(rows)):
                    for j in range(i + 1, len(rows)):
                        n1, f1 = rows[i][0], rows[i][1]; n2, f2 = rows[j][0], rows[j][1]
                        if f1 < f2:
                            hist[(n1, n2)].append((day, 1)); hist[(n2, n1)].append((day, 0))
                        elif f2 < f1:
                            hist[(n2, n1)].append((day, 1)); hist[(n1, n2)].append((day, 0))
        day += datetime.timedelta(days=1)

    b = base[0] / base[1] if base[1] else 0
    print(f"=== H2Hアラート検証 {a.warmup}〜{a.to}（南関・人気薄≥{a.usui}・上位{a.topn}人気が対象）===")
    print(f" 人気薄n={base[1]} ベース複勝{b:.1%}  ※対戦履歴は{a.frm}から蓄積\n")
    for k in ["◆アラート全体", "A.1戦1勝のみ", "B.完封(2戦以上・全勝)", "C.勝ち越し(2戦以上)",
              "D.負け越しだが勝ちあり", "E.アラート無し(上位人気に勝利歴なし)"]:
        v = C.get(k)
        if not v or not v[1]:
            print(f" {k:30s} n0"); continue
        r = v[0] / v[1]
        print(f" {k:30s} {r:5.1%}({v[0]:>3}/{v[1]:>4}) lift{(r/b if b else 0):4.2f}")
    print("\n--- 1番人気限定 ---")
    for k in ["★1番人気に勝利(1戦1勝)", "★1番人気を完封", "★1番人気に勝ちあり(複数戦)"]:
        v = C.get(k)
        if not v or not v[1]:
            print(f" {k:30s} n0"); continue
        r = v[0] / v[1]
        print(f" {k:30s} {r:5.1%}({v[0]:>3}/{v[1]:>4}) lift{(r/b if b else 0):4.2f}")


if __name__ == "__main__":
    main()
