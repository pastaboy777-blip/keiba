#!/usr/bin/env python3
"""【ボス理論・通年検証】2026年の南関競馬全体でボス理論を検証する。
§26は4-7月(1052R)だったが、1月からの通年で母数を倍増させ、さらに月別の安定性を見る。
※リーク無し(時系列順・各レース時点までの対戦のみ使用)。
※ウォームアップ期間(対戦履歴の蓄積)は評価対象外。

使い方: python3 scripts/hierarchy_year.py --from 2026-01-01 --to 2026-07-24 --warmup 2026-02-15
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
KEYS = ["★ボス(3戦+勝率60%+)", "中間", "子分(3戦+勝率30%-)", "対戦歴0"]


def cls_of(w, l):
    enc = w + l
    if enc == 0:
        return "対戦歴0"
    wr = w / enc
    if enc >= 3 and wr >= 0.6:
        return "★ボス(3戦+勝率60%+)"
    if enc >= 3 and wr <= 0.3:
        return "子分(3戦+勝率30%-)"
    return "中間"


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
    beat = defaultdict(int); met = defaultdict(int)
    ALL = {"base": [0, 0], "cells": defaultdict(lambda: [0, 0]), "nrace": 0}
    MON = defaultdict(lambda: {"base": [0, 0], "cells": defaultdict(lambda: [0, 0]), "nrace": 0})
    FIX = defaultdict(lambda: [0, 0])   # 序列固定度帯 -> [good,n]
    TRK = defaultdict(lambda: {"boss": [0, 0], "kobun": [0, 0], "base": [0, 0]})

    day = d0
    while day <= d1:
        ymd = day.strftime("%Y%m%d"); mo = day.strftime("%Y-%m")
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
                    tot = kn = 0
                    for i in range(len(names)):
                        for j in range(i + 1, len(names)):
                            tot += 1
                            if met[frozenset((names[i], names[j]))] > 0:
                                kn += 1
                    fixed = kn / tot if tot else 0
                    fb = "固定50%+" if fixed >= 0.5 else ("中20-50%" if fixed >= 0.2 else "未確定20%-")
                    ALL["nrace"] += 1; MON[mo]["nrace"] += 1
                    for name, fin, pop in rows:
                        if pop < a.usui:          # 0(欠落)も除外される
                            continue
                        g = 1 if fin <= 3 else 0
                        w = l = 0
                        for o in names:
                            if o == name:
                                continue
                            w += beat[(name, o)]; l += beat[(o, name)]
                        k = cls_of(w, l)
                        for S in (ALL, MON[mo]):
                            S["base"][0] += g; S["base"][1] += 1
                            S["cells"][k][0] += g; S["cells"][k][1] += 1
                        FIX[fb][0] += g; FIX[fb][1] += 1
                        T = TRK[tr]
                        T["base"][0] += g; T["base"][1] += 1
                        if k.startswith("★"):
                            T["boss"][0] += g; T["boss"][1] += 1
                        elif k.startswith("子分"):
                            T["kobun"][0] += g; T["kobun"][1] += 1
                for i in range(len(rows)):
                    for j in range(i + 1, len(rows)):
                        n1, f1, _ = rows[i]; n2, f2, _ = rows[j]
                        met[frozenset((n1, n2))] += 1
                        if f1 < f2:
                            beat[(n1, n2)] += 1
                        elif f2 < f1:
                            beat[(n2, n1)] += 1
        day += datetime.timedelta(days=1)

    def rate(cc):
        return cc[0] / cc[1] if cc[1] else 0
    b = rate(ALL["base"])
    print(f"=== ボス理論 通年検証 {a.warmup}〜{a.to}（南関4場・人気薄≥{a.usui}）===")
    print(f" 評価{ALL['nrace']}R / 人気薄n={ALL['base'][1]} / 対戦ペア{len(met)}組 / ベース複勝{b:.1%}")
    print(f" ※{a.frm}〜{a.warmup}は履歴蓄積(評価外)\n")
    print("--- 全体 ---")
    for k in KEYS:
        v = ALL["cells"].get(k)
        if not v or not v[1]:
            continue
        r = rate(v)
        print(f" {k:20s} {r:5.1%}({v[0]:>4}/{v[1]:>5}) lift{(r/b if b else 0):4.2f}")
    print("\n--- 月別安定性(★ボス / 子分 のlift) ---")
    print(f" {'月':9s} {'R数':>4s} {'人気薄n':>7s} {'ベース':>6s} {'★ボス':>16s} {'子分':>16s}")
    for mo in sorted(MON):
        S = MON[mo]; bb = rate(S["base"])
        if S["base"][1] < 50:
            continue
        bo = S["cells"].get("★ボス(3戦+勝率60%+)", [0, 0])
        ko = S["cells"].get("子分(3戦+勝率30%-)", [0, 0])
        lb = (rate(bo) / bb) if bb and bo[1] else 0
        lk = (rate(ko) / bb) if bb and ko[1] else 0
        print(f" {mo:9s} {S['nrace']:>4} {S['base'][1]:>7} {bb:>6.1%} "
              f"{rate(bo):5.1%}(n{bo[1]:>3})L{lb:4.2f} {rate(ko):5.1%}(n{ko[1]:>3})L{lk:4.2f}")
    print("\n--- レースの序列固定度別(人気薄の来やすさ) ---")
    for k in ["固定50%+", "中20-50%", "未確定20%-"]:
        v = FIX.get(k)
        if not v or not v[1]:
            continue
        r = rate(v)
        print(f" {k:12s} {r:5.1%}({v[0]:>4}/{v[1]:>5}) lift{(r/b if b else 0):4.2f}")
    print("\n--- トラック別(★ボス/子分) ---")
    for tr in TRACKS:
        T = TRK.get(tr)
        if not T or not T["base"][1]:
            continue
        bb = rate(T["base"])
        lb = (rate(T["boss"]) / bb) if bb and T["boss"][1] else 0
        lk = (rate(T["kobun"]) / bb) if bb and T["kobun"][1] else 0
        print(f" {tr} ベース{bb:5.1%}(n{T['base'][1]:>4}) ★ボス lift{lb:4.2f}(n{T['boss'][1]:>3}) "
              f"子分 lift{lk:4.2f}(n{T['kobun'][1]:>3})")


if __name__ == "__main__":
    main()
