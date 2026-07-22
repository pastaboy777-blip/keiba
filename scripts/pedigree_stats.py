#!/usr/bin/env python3
"""大系統×条件の複勝率を南関実データで実測し、血統の妙味を検証する。

  1) 楽天から南関の過去レースを収集(カード=父/母父・結果=着順/人気)
  2) 大系統 × 距離帯 の複勝率を集計
  3) 血統が「人気以上に走るか」を検証:
     - 各大系統の複勝率 vs その大系統馬の平均人気からの期待
     - 特に「父or母父サンデー系」の南関ダートでの実成績

    python3 scripts/pedigree_stats.py --start 20260721 --days 30 --out data/pedigree_stats.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import rakuten as rk        # noqa: E402
from nankeiba.core import pedigree as ped          # noqa: E402

NANKAN = ["大井", "川崎", "船橋", "浦和"]


def dist_band(d: int) -> str:
    if d <= 1400:
        return "短(〜1400)"
    if d <= 1700:
        return "中(1500-1700)"
    return "長(1800〜)"


def nankan_meetings(client, ymd):
    import html as _h
    try:
        h = client.get(f"/race_card/list/RACEID/{ymd}0000000000")
    except Exception:
        return {}
    out = {}
    for m in re.finditer(r'race_card/list/RACEID/(\d{18})"[^>]*>(.*?)</a>', h, re.S):
        t = _h.unescape(re.sub(r"<[^>]+>", "", m.group(2))).replace("　", "").strip()
        if t in NANKAN:
            out[t] = m.group(1)
    return out


def pop_hit_baseline(pop: int | None) -> float:
    """人気からの複勝期待(粗い基準)。南関の概算。"""
    table = {1: 0.62, 2: 0.48, 3: 0.40, 4: 0.32, 5: 0.27, 6: 0.22, 7: 0.18, 8: 0.15}
    return table.get(pop, 0.10) if pop else 0.20


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--out", default="data/pedigree_stats.json")
    args = ap.parse_args()

    client = rk.KeibaRakuten()
    d0 = date(int(args.start[:4]), int(args.start[4:6]), int(args.start[6:]))

    # (system) -> [starts, hit3, sum_expected]、(system,band)->[starts,hit3]
    S = {}
    SB = {}
    sunday_line = [0, 0]        # [starts, hit3]  父or母父サンデー系
    n_races = 0
    for off in range(args.days):
        d = d0 - timedelta(days=off)
        for place, mid in nankan_meetings(client, f"{d:%Y%m%d}").items():
            for rno in range(1, 13):
                rid = mid[:-2] + f"{rno:02d}"
                try:
                    card = rk.parse_card(client.get(f"/race_card/list/RACEID/{rid}"))
                    res = rk.parse_result(client.get(f"/race_performance/list/RACEID/{rid}"))
                except Exception:
                    continue
                E = card["entries"]
                if not E or not res:
                    continue
                dist = int(card["header"]["distance"] or 0)
                band = dist_band(dist)
                fin = {r["umaban"]: r["finish"] for r in res}
                pop = {r["umaban"]: r.get("popularity") for r in res}
                n_races += 1
                for e in E:
                    um = e["umaban"]
                    if um not in fin:
                        continue
                    sys_ = ped.classify(e.get("sire"))
                    bms_ = ped.classify(e.get("bms"))
                    hit = 1 if fin[um] <= 3 else 0
                    if sys_:
                        s = S.setdefault(sys_, [0, 0, 0.0])
                        s[0] += 1; s[1] += hit; s[2] += pop_hit_baseline(pop.get(um))
                        sb = SB.setdefault((sys_, band), [0, 0])
                        sb[0] += 1; sb[1] += hit
                    if sys_ == "sunday" or bms_ == "sunday":
                        sunday_line[0] += 1; sunday_line[1] += hit
        print(f"  {d:%Y%m%d}: races={n_races}", flush=True)

    print(f"\n=== 大系統 複勝率(南関ダート {n_races}R) ===")
    print(f"{'大系統':<12}{'出走':>5}{'複勝率':>7}{'人気期待':>8}{'妙味':>7}")
    rows = []
    for sys_, (st, h, exp) in sorted(S.items(), key=lambda t: -t[1][0]):
        if st < 20:
            continue
        rate = h / st
        expr = exp / st
        edge = rate - expr        # 人気期待を上回れば血統の妙味(正)
        rows.append((ped.system_name(sys_), st, rate, expr, edge))
        print(f"{ped.system_name(sys_):<12}{st:>5}{rate:>7.1%}{expr:>8.1%}{edge:>+7.1%}")

    print("\n=== 大系統×距離帯 複勝率 ===")
    for (sys_, band), (st, h) in sorted(SB.items(), key=lambda t: (-t[1][0])):
        if st < 15:
            continue
        print(f"  {ped.system_name(sys_):<12}{band:<14}{st:>4}走 複勝{h/st:>6.1%}")

    if sunday_line[0]:
        print(f"\n父or母父サンデー系(南関ダート): {sunday_line[1]}/{sunday_line[0]} "
              f"= {sunday_line[1]/sunday_line[0]:.1%}")

    out = {"n_races": n_races,
           "system": {k: {"starts": v[0], "hit3": v[1]} for k, v in S.items()},
           "system_band": {f"{k[0]}|{k[1]}": {"starts": v[0], "hit3": v[1]}
                           for k, v in SB.items()}}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n保存: {args.out}")


if __name__ == "__main__":
    main()
