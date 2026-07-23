#!/usr/bin/env python3
"""グリップ血統（中山×道悪）仮説を、夏のNARダートで実測検証する。

  父or母父が grip.GRIP_SIRES の馬の複勝率を、全体baselineおよび非該当馬と比較。
  「散水で湿ってタフ化する白砂で穴をあける」が本当かをデータで確かめる。

    python3 scripts/grip_backtest.py --start 20260723 --days 30 --places 大井 園田
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import html as _h
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import rakuten as rk        # noqa: E402
from nankeiba.core import grip                     # noqa: E402


def meetings(client, ymd, places):
    try:
        h = client.get(f"/race_card/list/RACEID/{ymd}0000000000")
    except Exception:
        return {}
    out = {}
    for m in re.finditer(r'race_card/list/RACEID/(\d{18})"[^>]*>(.*?)</a>', h, re.S):
        t = _h.unescape(re.sub(r"<[^>]+>", "", m.group(2))).replace("　", "").strip()
        if t in places:
            out[t] = m.group(1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--places", nargs="+", default=["大井", "園田"])
    args = ap.parse_args()

    client = rk.KeibaRakuten()
    d0 = date(int(args.start[:4]), int(args.start[4:6]), int(args.start[6:]))

    # [starts, hit3, sum_pop]
    grp = [0, 0, 0]      # 父or母父グリップ
    non = [0, 0, 0]      # 非該当
    grp_pop = {}         # 人気帯別の複勝(グリップ)
    n_races = 0
    for off in range(args.days):
        d = d0 - timedelta(days=off)
        for place, mid in meetings(client, f"{d:%Y%m%d}", args.places).items():
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
                fin = {r["umaban"]: r["finish"] for r in res}
                pop = {r["umaban"]: r.get("popularity") for r in res}
                n_races += 1
                for e in E:
                    um = e["umaban"]
                    if um not in fin:
                        continue
                    hit = 1 if fin[um] <= 3 else 0
                    g = grip.grip_of(e.get("sire"), e.get("bms"))
                    bucket = grp if g else non
                    bucket[0] += 1
                    bucket[1] += hit
                    p = pop.get(um) or 0
                    bucket[2] += p
                    if g:
                        band = "人気1-3" if 1 <= p <= 3 else ("人気4-7" if 4 <= p <= 7 else "人気8＋")
                        b = grp_pop.setdefault(band, [0, 0])
                        b[0] += 1; b[1] += hit
        print(f"  {d:%Y%m%d} 集計 races={n_races}", flush=True)

    def line(nm, s):
        if not s[0]:
            print(f"{nm:<18} 出走0"); return
        print(f"{nm:<18} 出走{s[0]:>4}  複勝{s[1]/s[0]:>6.1%}  平均人気{s[2]/s[0]:>4.1f}")

    print(f"\n=== グリップ血統 検証（{args.places} 直近{args.days}日 {n_races}R）===")
    line("グリップ(父or母父)", grp)
    line("非該当", non)
    base = (grp[1] + non[1]) / (grp[0] + non[0]) if (grp[0] + non[0]) else 0
    print(f"{'全体baseline':<18} 複勝{base:>6.1%}")
    if grp[0] and non[0]:
        edge = grp[1] / grp[0] - non[1] / non[0]
        print(f"\nグリップ − 非該当 = {edge:+.1%}  （正なら仮説を支持）")
    print("\n--- グリップ馬の人気帯別複勝 ---")
    for band in ("人気1-3", "人気4-7", "人気8＋"):
        b = grp_pop.get(band)
        if b and b[0]:
            print(f"  {band:<8} {b[0]:>4}走 複勝{b[1]/b[0]:>6.1%}")


if __name__ == "__main__":
    main()
