# -*- coding: utf-8 -*-
"""ズブ穴 × 踏ん張り：人気にならない馬の中から「かかっても落ちない馬」を抜く。

狙い（2026-07-30）：
  砂が緩んで劣化しにくさの勝負になる日は、399（速い上がりを出せた下地）ではなく
  funbari（かかった上がりでも3着内に残った実績）が効く。そこにズブ穴の本体である
  「実力軸で上位に見えない＝人気にならない」を掛けると、市場と最も食い違う馬が残る。

必須条件（どれか欠けたら候補にしない）：
  ① 踏ん張り実績 ≥1回   … その場×距離帯の3着内中央値より遅い上がりで3着内に来た
  ② 実力軸が上位3位以内でない … 人気を被る馬を外す（＝ズブ穴の本体）

加点：最深(基準からどれだけ遅くて残せたか)・ブレ幅の小ささ・エッジ数・小型(≤466kg)。

    python3 scripts/zubu_funbari.py --date 2026-07-30 --place 川崎 --from 1 --to 12
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

import ana399 as A
import ana_recall as R
import funbari as F

CARD_URL = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{race_id}"
_ROW = re.compile(r"^[◎○▲△\s]*(\d+)\s+(\S+)\s+(\S+)\s+([\d.]+)%")


def ability_rank(date_s, place, race):
    """predict_nankan の 上位3着% 順位を {馬番: (順位, %)} で返す。"""
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "predict_nankan.py"),
         "--date", date_s, "--place", place, "--race", str(race)],
        capture_output=True, text=True, timeout=300).stdout
    rank = {}
    for line in out.splitlines():
        m = _ROW.match(line.strip())
        if m:
            rank[int(m.group(1))] = (len(rank) + 1, float(m.group(4)))
    return rank


def main():
    ap = argparse.ArgumentParser(description="ズブ穴×踏ん張り")
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", default="川崎", choices=list(NANKAN_CODES))
    ap.add_argument("--from", dest="r_from", type=int, default=1)
    ap.add_argument("--to", dest="r_to", type=int, default=12)
    ap.add_argument("--margin", type=float, default=0.3)
    ap.add_argument("--top-skip", type=int, default=3,
                    help="実力軸のこの順位までは人気を被るとみなして候補から外す")
    args = ap.parse_args()

    pa, ba = A.load_adj()
    client = PoliteClient(use_cache=False)
    ymd = date.fromisoformat(args.date).strftime("%Y%m%d")
    races = dict(P.parse_race_links(
        client.get(CARD_URL.format(race_id=day_index_race_id(ymd, args.place))),
        date_yyyymmdd=ymd, jyo_code=NANKAN_CODES[args.place]))
    today = date.fromisoformat(args.date)

    print(f"■ {args.date} {args.place}  ズブ穴 × 踏ん張り")
    print(f"  条件＝踏ん張り1回以上 かつ 実力軸{args.top_skip}位以内でない（人気を被る馬を外す）\n")

    for r in range(args.r_from, args.r_to + 1):
        if r not in races:
            continue
        page = P.parse_card_page(client.get(CARD_URL.format(race_id=races[r])), races[r])
        ents = getattr(page, "entries", page)
        rank = ability_rank(args.date, args.place, r)
        rows = []
        for e in ents:
            ev = F.evaluate(e, args.place, pa, ba, args.margin, 5)
            tags, cw = R.edges_for(e, page.distance, today=today)
            a399 = A.evaluate(e, A.band(page.distance), args.place, pa, ba, 40.5, False)
            rk, pct = rank.get(e.umaban, (99, 0.0))
            if ev["n"] < 1 or rk <= args.top_skip:
                rows.append((None, rk, pct, e, ev, tags, a399))
                continue
            small = 1.0 if (cw and cw <= 466) else 0.0
            tight = max(0.0, 2.0 - (ev["span"] if ev["span"] is not None else 2.0))
            score = (ev["n"] * 2.0 + (ev["deepest"] or 0) * 1.5
                     + len(tags) * 0.4 + small + tight + min(rk, 8) * 0.15)
            rows.append((score, rk, pct, e, ev, tags, a399))
        hit = [x for x in rows if x[0] is not None]
        hit.sort(key=lambda x: -x[0])
        print(f"=== {r}R ダ{page.distance} {len(ents)}頭　両立{len(hit)}頭")
        if not hit:
            print("   （該当なし＝踏ん張り実績のある馬が人気側に固まっている、または実績ゼロ）")
        for sc, rk, pct, e, ev, tags, a399 in hit:
            um = f"{e.umaban:>2}" if e.umaban is not None else " ?"
            span = f"{ev['span']:.2f}" if ev["span"] is not None else " - "
            print(f"  {sc:5.1f} {um} {e.horse_name:<12} 踏{ev['n']} 最深+{ev['deepest']:.2f} "
                  f"ブレ{span} 実力軸{rk}位({pct:.1f}%) {str(ev['weight'] or '-'):>4}kg "
                  f"{ev['leg']:<3} 399={a399['score']:.1f} E{len(tags)}")
            for f in sorted(ev["funbari"], key=lambda x: -x["gap"])[:2]:
                print(f"          {f['date'][5:]}{f['place']}{f['baba']} 上{f['agari']}"
                      f"(基準+{f['gap']}) {f['fin']}着{f['pop']}人")
        print()


if __name__ == "__main__":
    main()
