#!/usr/bin/env python3
"""【ボス理論・改善版】下剋上シグナル＋直近対戦の重み付け。
§27で確定した素のボス度(全相手との平均勝率)には2つの弱点がある：
 ①平均が信号を殺す：園田7/23でミスターエヌ(1着9人気)はベラジオアブロード(1人気4着)に
   直接勝っていたのに、他馬への負けで平均50%に薄まり無印。逆に負けた側が★ボスになった。
 ②時系列が見えない：3ヶ月前の1勝と前走の1勝を同じ1勝として数えている。

そこで以下を検証する：
 A. 下剋上シグナル = 人気薄が「今日の1番人気」に過去直接勝っている(ピンポイント)
 B. 下剋上(直近)   = 1番人気との最新の対戦が勝ち
 C. 上位3人気に勝利 = 対象を上位3人気に広げた版
 D. 直近重み付けボス度 = 対戦を半減期60日で減衰させた勝率(素のボス度と比較)

使い方: python3 scripts/gekokujo.py --from 2026-01-01 --to 2026-07-24 --warmup 2026-02-15
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
HALF_LIFE = 60.0     # 直近重み付けの半減期(日)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", dest="to", required=True)
    ap.add_argument("--warmup", required=True)
    ap.add_argument("--usui", type=int, default=6)
    a = ap.parse_args()
    c = PoliteClient()
    d0 = datetime.date.fromisoformat(a.frm); d1 = datetime.date.fromisoformat(a.to)
    warm = datetime.date.fromisoformat(a.warmup)
    # hist[(A,B)] = [(date, 1=Aの勝ち / 0=Aの負け), ...]
    hist = defaultdict(list)
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
                names = [n for n, f, p in rows]
                if day >= warm:
                    fav = next((n for n, f, p in rows if p == 1), None)          # 1番人気
                    top3 = {n for n, f, p in rows if 1 <= p <= 3}                 # 上位3人気
                    for name, fin, pop in rows:
                        if pop < a.usui:
                            continue
                        g = 1 if fin <= 3 else 0
                        base[0] += g; base[1] += 1
                        # --- 素のボス度(比較対象・§27と同じ) ---
                        w = l = 0
                        wsum = wwin = 0.0
                        for o in names:
                            if o == name:
                                continue
                            for dt, res in hist[(name, o)]:
                                if res == 1:
                                    w += 1
                                else:
                                    l += 1
                                # 直近重み付け(半減期HALF_LIFE日)
                                days = (day - dt).days
                                wt = 0.5 ** (days / HALF_LIFE)
                                wsum += wt; wwin += wt * res
                        enc = w + l
                        if enc >= 3:
                            wr = w / enc
                            if wr >= 0.6:
                                add("[素]★ボス", g)
                            elif wr <= 0.3:
                                add("[素]子分", g)
                            # --- D: 直近重み付けボス度 ---
                            wwr = wwin / wsum if wsum else 0
                            if wwr >= 0.6:
                                add("[重]★ボス(直近重み)", g)
                            elif wwr <= 0.3:
                                add("[重]子分(直近重み)", g)
                            # 素と重みの食い違いセル(序列が動いている馬)
                            if wr >= 0.6 and wwr < 0.5:
                                add("[動]通算ボスだが直近負け越し", g)
                            if wr <= 0.4 and wwr >= 0.55:
                                add("[動]通算劣勢だが直近勝ち越し=下剋上中", g)
                        # --- A/B: 下剋上シグナル(今日の1番人気に直接勝利) ---
                        if fav and fav != name:
                            h = hist[(name, fav)]
                            if h:
                                wins = sum(1 for _, r_ in h if r_ == 1)
                                add("[下]1番人気と対戦歴あり", g)
                                if wins > 0:
                                    add("★[下]1番人気に勝利歴あり", g)
                                    if h[-1][1] == 1:
                                        add("★[下]1番人気に直近勝利", g)
                                else:
                                    add("[下]1番人気に全敗", g)
                        # --- C: 上位3人気のいずれかに勝利 ---
                        won_top = False; met_top = False
                        for o in top3:
                            if o == name:
                                continue
                            h = hist[(name, o)]
                            if h:
                                met_top = True
                                if any(r_ == 1 for _, r_ in h):
                                    won_top = True
                        if met_top:
                            add("★[下]上位3人気に勝利歴" if won_top else "[下]上位3人気に全敗", g)
                # 履歴更新
                for i in range(len(rows)):
                    for j in range(i + 1, len(rows)):
                        n1, f1, _ = rows[i]; n2, f2, _ = rows[j]
                        if f1 < f2:
                            hist[(n1, n2)].append((day, 1)); hist[(n2, n1)].append((day, 0))
                        elif f2 < f1:
                            hist[(n2, n1)].append((day, 1)); hist[(n1, n2)].append((day, 0))
        day += datetime.timedelta(days=1)

    b = base[0] / base[1] if base[1] else 0
    print(f"=== ボス理論・改善版(下剋上シグナル/直近重み) {a.warmup}〜{a.to} 人気薄≥{a.usui} ===")
    print(f" 人気薄n={base[1]} ベース複勝{b:.1%}  半減期{HALF_LIFE:.0f}日\n")
    groups = [
        ("【比較】素のボス度(§27)", ["[素]★ボス", "[素]子分"]),
        ("【D】直近重み付けボス度", ["[重]★ボス(直近重み)", "[重]子分(直近重み)"]),
        ("【動】序列が動いている馬", ["[動]通算ボスだが直近負け越し", "[動]通算劣勢だが直近勝ち越し=下剋上中"]),
        ("【A/B】下剋上=今日の1番人気に勝利歴", ["★[下]1番人気に勝利歴あり", "★[下]1番人気に直近勝利",
                                              "[下]1番人気に全敗", "[下]1番人気と対戦歴あり"]),
        ("【C】上位3人気に勝利歴", ["★[下]上位3人気に勝利歴", "[下]上位3人気に全敗"]),
    ]
    for title, keys in groups:
        print(f"--- {title} ---")
        for k in keys:
            v = C.get(k)
            if not v or not v[1]:
                print(f" {k:32s} n0"); continue
            r = v[0] / v[1]
            print(f" {k:32s} {r:5.1%}({v[0]:>4}/{v[1]:>5}) lift{(r/b if b else 0):4.2f}")
        print()


if __name__ == "__main__":
    main()
