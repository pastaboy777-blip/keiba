#!/usr/bin/env python3
"""【統合検証】ズブ穴(エッジ体系) × ボス理論(集団の序列) は掛け合わさるか。
ズブ穴＝ana_recall.edges_for のタグ数(既存の穴検出体系)。
ボス＝§27/§28の対戦グラフ(★ボス/子分/下剋上=上位3人気に勝利歴)。
両者が独立なら重ねたときliftが乗算的に伸びる。冗長なら伸びない。

対戦履歴は 1/1〜6/30 で蓄積し、7月を評価(リーク無し)。
使い方: python3 scripts/zubu_boss.py --from 2026-01-01 --warmup 2026-07-01 --to 2026-07-24
"""
import sys, argparse, datetime
from collections import defaultdict
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from ana_recall import edges_for, field_pace, agari_pattern

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"
TRACKS = ["浦和", "船橋", "大井", "川崎"]


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
                rows = [(x.horse_name.strip(), x.finish_pos, x.popularity or 0, x.umaban)
                        for x in rr.rows if x.horse_name and x.finish_pos]
                if len(rows) < 6:
                    continue
                names = [n for n, f, p, u in rows]
                if day >= warm:
                    try:
                        _ch = c.get(CARD.format(r=rid), use_cache=True)
                        pc = P.parse_card_page(_ch, rid)
                        try:
                            from rakuten_ped import attach as _apd
                            _apd(_ch, pc.entries)
                        except Exception:
                            pass
                        dist = getattr(pc, "distance", None)
                        pace, _ = field_pace(pc.entries)
                        apct = agari_pattern(pc.entries)
                        emap = {e.umaban: e for e in pc.entries if e.umaban}
                    except Exception:
                        emap = {}; dist = None; pace = None; apct = {}
                    top3 = {n for n, f, p, u in rows if p and 1 <= p <= 3}
                    for name, fin, pop, um in rows:
                        if pop < a.usui or not dist:
                            continue
                        e = emap.get(um)
                        if not e:
                            continue
                        g = 1 if fin <= 3 else 0
                        base[0] += g; base[1] += 1
                        # --- ズブ穴エッジ ---
                        try:
                            tags, _cw = edges_for(e, dist, pace=pace, agari_pct=apct.get(um), today=day)
                        except Exception:
                            tags = set()
                        zubu = len(tags) >= 2                      # 既存のズブ穴基準
                        zubu3 = len(tags) >= 3                     # 濃いズブ穴
                        # --- ボス度 ---
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
                        kobun = enc >= 3 and (w / enc) <= 0.3
                        # --- 下剋上(上位3人気に勝利歴) ---
                        geko = any(hist[(name, o)] and any(r_ == 1 for _, r_ in hist[(name, o)])
                                   for o in top3 if o != name)
                        # --- 単独 ---
                        add("ズブ穴(エッジ2+)" if zubu else "ズブ穴外", g)
                        if boss:
                            add("★ボス単独", g)
                        if kobun:
                            add("子分単独", g)
                        if geko:
                            add("下剋上単独", g)
                        # --- 掛け合わせ ---
                        if zubu and boss:
                            add("◎ズブ穴×★ボス", g)
                        if zubu and geko:
                            add("◎ズブ穴×下剋上", g)
                        if zubu3 and (boss or geko):
                            add("◎◎濃ズブ穴(3+)×ボスor下剋上", g)
                        if zubu and kobun:
                            add("ズブ穴×子分(矛盾)", g)
                        if zubu and not (boss or geko):
                            add("ズブ穴のみ(ボス信号なし)", g)
                        if (boss or geko) and not zubu:
                            add("ボス信号のみ(ズブ穴外)", g)
                # 履歴更新
                for i in range(len(rows)):
                    for j in range(i + 1, len(rows)):
                        n1, f1 = rows[i][0], rows[i][1]; n2, f2 = rows[j][0], rows[j][1]
                        if f1 < f2:
                            hist[(n1, n2)].append((day, 1)); hist[(n2, n1)].append((day, 0))
                        elif f2 < f1:
                            hist[(n2, n1)].append((day, 1)); hist[(n1, n2)].append((day, 0))
        day += datetime.timedelta(days=1)

    b = base[0] / base[1] if base[1] else 0
    print(f"=== ズブ穴 × ボス理論 統合検証 {a.warmup}〜{a.to}（南関・人気薄≥{a.usui}）===")
    print(f" 人気薄n={base[1]} ベース複勝{b:.1%}  ※対戦履歴は{a.frm}から蓄積\n")
    order = ["--単独--", "ズブ穴(エッジ2+)", "ズブ穴外", "★ボス単独", "下剋上単独", "子分単独",
             "--掛け合わせ--", "◎ズブ穴×★ボス", "◎ズブ穴×下剋上", "◎◎濃ズブ穴(3+)×ボスor下剋上",
             "--対照--", "ズブ穴のみ(ボス信号なし)", "ボス信号のみ(ズブ穴外)", "ズブ穴×子分(矛盾)"]
    for k in order:
        if k.startswith("--"):
            print(k); continue
        v = C.get(k)
        if not v or not v[1]:
            print(f" {k:28s} n0"); continue
        r = v[0] / v[1]
        print(f" {k:28s} {r:5.1%}({v[0]:>3}/{v[1]:>4}) lift{(r/b if b else 0):4.2f}")


if __name__ == "__main__":
    main()
