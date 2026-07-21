#!/usr/bin/env python3
"""中央(JRA)の指数を実結果と照合するバックテスト(keibabook /cyuou/)。

    python3 scripts/jra_backtest.py --date 20260719 --place 函館 --races 1-12

各レースで、レース前の過去走(同じ馬場種)だけから JraIndexModel で指数を算出し、
指数上位=予想順として実着順と照合する。※会員本人の個人利用の範囲で。
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import keibabook as kb          # noqa: E402
from nankeiba.core.jra_index import JraIndexModel, _norm_surface  # noqa: E402


def today_surface(syutuba_html: str) -> str | None:
    m = re.search(r"(芝|ダート|ダ)\s*\d{3,4}", syutuba_html) or \
        re.search(r"(\d{3,4})m[^<]{0,8}(芝|ダ)", syutuba_html)
    if not m:
        return None
    return "芝" if "芝" in m.group(0) else "ダ"


def best_index(runs, model, surface, lookback=8):
    best = None
    for r in list(runs)[:lookback]:
        if surface and _norm_surface(r.surface) != surface:
            continue
        idx = model.index(r)
        if idx is not None and (best is None or idx > best):
            best = idx
    return best


def parse_races(s):
    if "-" in s:
        a, b = s.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in s.split(",")] if s else list(range(1, 13))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--races", default="1-12")
    ap.add_argument("--cookie", default="data/.keibabook_cookie")
    args = ap.parse_args()

    client = kb.KeibabookClient.from_cookie_file(args.cookie)
    race_ids = kb.find_meeting_cyuou(client, args.date, args.place)
    race_date = f"{args.date[:4]}-{args.date[4:6]}-{args.date[6:]}"
    races = parse_races(args.races)

    print(f"=== {race_date} {args.place}(中央) 指数バックテスト ===")
    print(f"{'R':>2} | ◎馬(指数)          | 着 | 1着馬(人気/指数順) ")
    print("-" * 60)
    agg = dict(n=0, win=0, in3=0, wtop3=0, rsum=0, rn=0)

    for rno in races:
        rid = race_ids[rno - 1]
        try:
            syu = client.get(f"/cyuou/syutuba/{rid}")
            entries = kb.parse_entries(syu)
            surface = today_surface(syu)
            res = kb.parse_result_cyuou(client.get(f"/cyuou/seiseki/{rid}"))
        except Exception as e:                       # noqa: BLE001
            print(f"{rno:>2} | 取得失敗: {e}")
            continue
        if not entries or not res:
            print(f"{rno:>2} | データ無(未確定/取消?)")
            continue

        # 各馬の過去走(レース前・同surface)
        pre = {}
        allruns = []
        for e in entries:
            try:
                hist = kb.parse_history(client.get(f"/db/uma/{e['umacd']}/seiseki"),
                                        limit=12, drop_turf=False)
            except Exception:
                hist = []
            hist = [r for r in hist if r.date < race_date]
            pre[e["umaban"]] = hist
            allruns += hist
        name_of = {e["umaban"]: e["name"] for e in entries}
        um_of_name = {e["name"]: e["umaban"] for e in entries}

        model = JraIndexModel.fit(allruns)
        idx = {um: best_index(rs, model, surface) for um, rs in pre.items()}
        ranking = sorted(idx, key=lambda um: (idx[um] is not None,
                         idx[um] if idx[um] is not None else -1e9), reverse=True)
        rank_of = {um: i + 1 for i, um in enumerate(ranking)}
        anchor = ranking[0]

        # 実着順(馬名→馬番)
        fin_um = {}
        for r in res:
            um = um_of_name.get(r["name"])
            if um:
                fin_um[um] = r["finish"]
        winner = next((r for r in res if r["finish"] == 1), None)
        if winner is None:
            continue
        wu = um_of_name.get(winner["name"])
        agg["n"] += 1
        af = fin_um.get(anchor)
        if af == 1:
            agg["win"] += 1
        if af is not None and af <= 3:
            agg["in3"] += 1
        wr = rank_of.get(wu)
        if wr:
            agg["rsum"] += wr; agg["rn"] += 1
            if wr <= 3:
                agg["wtop3"] += 1
        ai = idx.get(anchor)
        print(f"{rno:>2} | {anchor:>2}{name_of.get(anchor,'')[:6]:<6}"
              f"({('%+d'%ai) if ai is not None else '-':>4}) | {af if af else '-':>2} | "
              f"{winner['name'][:7]}({winner.get('popularity','?')}人/指{wr or '-'})")

    n = agg["n"]
    print(f"\n=== 集計({n}R・{args.place}) ===")
    if n:
        print(f"◎(指数1位)勝率 : {agg['win']}/{n} = {agg['win']/n:.0%}")
        print(f"◎複勝率(3着内) : {agg['in3']}/{n} = {agg['in3']/n:.0%}")
        print(f"勝ち馬が指数上位3: {agg['wtop3']}/{n} = {agg['wtop3']/n:.0%}")
        if agg["rn"]:
            print(f"勝ち馬の平均指数順位: {agg['rsum']/agg['rn']:.1f}番手")


if __name__ == "__main__":
    main()
