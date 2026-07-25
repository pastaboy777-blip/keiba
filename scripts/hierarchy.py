#!/usr/bin/env python3
"""【変態ファクター】集団の序列＝ボス理論。
南関は同じ相手と何度も当たる＝群れの中に序列(ヒエラルキー)が固定化する、という仮説。
「誰が誰に勝ったか」の有向グラフを時系列で構築し、各レースで:
  ・ボス度 = 今日の出走メンバーに対する過去の直接対決勝率
  ・序列固定度 = 今日のメンバー間で既に対戦済みのペア比率(高い=序列決着=堅い/低い=荒れる)
  ・下剋上 = 以前負けていた相手に最近勝ち始めた(序列が動いている)
を算出し、人気薄での複勝率liftを検証する。
※リーク防止：各レース時点で"それ以前"の対戦のみ使用(時系列順に処理)。

使い方: python3 scripts/hierarchy.py --from 2026-04-01 --to 2026-07-24
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
    ap.add_argument("--to", dest="to", required=True)
    ap.add_argument("--usui", type=int, default=6)
    ap.add_argument("--warmup", default="2026-05-15", help="この日以降を検証対象(前半は対戦履歴の蓄積に使う)")
    a = ap.parse_args()
    c = PoliteClient()
    d0 = datetime.date.fromisoformat(a.frm); d1 = datetime.date.fromisoformat(a.to)
    warm = datetime.date.fromisoformat(a.warmup)

    beat = defaultdict(int)        # (勝者,敗者) -> 回数
    met = defaultdict(int)         # frozenset({A,B}) -> 対戦回数
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
                rows = [(r.horse_name.strip(), r.finish_pos, r.popularity or 99)
                        for r in rr.rows if r.horse_name and r.finish_pos]
                if len(rows) < 6:
                    continue
                names = [n for n, f, p in rows]
                # ---- 評価(この時点までの履歴のみ使用) ----
                if day >= warm:
                    # 序列固定度: 既に対戦済みペアの比率
                    tot = 0; known = 0
                    for i in range(len(names)):
                        for j in range(i + 1, len(names)):
                            tot += 1
                            if met[frozenset((names[i], names[j]))] > 0:
                                known += 1
                    fixed = known / tot if tot else 0
                    for name, fin, pop in rows:
                        if pop < a.usui:
                            continue
                        g = 1 if fin <= 3 else 0
                        base[0] += g; base[1] += 1
                        # ボス度: 今日の相手に対する過去直接対決の勝率
                        w = l = 0
                        for o in names:
                            if o == name:
                                continue
                            w += beat[(name, o)]
                            l += beat[(o, name)]
                        enc = w + l
                        if enc == 0:
                            add("初対戦だらけ(対戦歴0)", g)
                        else:
                            wr = w / enc
                            if enc >= 3 and wr >= 0.6:
                                add("★ボス(対戦3+勝率60%+)", g)
                            elif enc >= 3 and wr <= 0.3:
                                add("子分(対戦3+勝率30%-)", g)
                            add(f"対戦歴有 勝率{'高' if wr>=0.5 else '低'}", g)
                        # レース単位の序列固定度で層別
                        add("序列固定(既対戦50%+)" if fixed >= 0.5 else
                            ("序列中(20-50%)" if fixed >= 0.2 else "序列未確定(20%未満)"), g)
                # ---- 履歴更新(このレースの結果を反映) ----
                for i in range(len(rows)):
                    for j in range(i + 1, len(rows)):
                        n1, f1, _ = rows[i]; n2, f2, _ = rows[j]
                        met[frozenset((n1, n2))] += 1
                        if f1 < f2:
                            beat[(n1, n2)] += 1
                        elif f2 < f1:
                            beat[(n2, n1)] += 1
        day += datetime.timedelta(days=1)

    b = base[0] / base[1] if base[1] else 0
    print(f"=== 集団の序列(ボス理論) {a.warmup}〜{a.to} 人気薄≥{a.usui} ===")
    print(f" ※{a.frm}〜{a.warmup}は対戦履歴の蓄積期間(評価対象外)")
    print(f" [ベース] 複勝{b:.1%}({base[0]}/{base[1]})  対戦ペア記録{len(met)}組\n")
    order = ["★ボス(対戦3+勝率60%+)", "子分(対戦3+勝率30%-)", "対戦歴有 勝率高", "対戦歴有 勝率低",
             "初対戦だらけ(対戦歴0)", "序列固定(既対戦50%+)", "序列中(20-50%)", "序列未確定(20%未満)"]
    for k in order:
        v = C.get(k)
        if not v or not v[1]:
            print(f" {k:24s} n0"); continue
        r = v[0] / v[1]
        print(f" {k:24s} {r:5.1%}({v[0]:>3}/{v[1]:>4}) lift{(r/b if b else 0):4.2f}")


if __name__ == "__main__":
    main()
