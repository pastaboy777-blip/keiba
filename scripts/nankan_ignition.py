#!/usr/bin/env python3
"""出馬表から**点火指数**（穴馬が走るタイミング）を出す。

    python3 scripts/nankan_ignition.py --date 20260810 --place 浦和
    python3 scripts/nankan_ignition.py --date 20260810 --place 浦和 --race 11

変化（距離・騎手・競馬場・間隔）と、前走に出ていた予熱の兆候を足す。
**変化した当日ではなく、その次が本番**という考え方。

⚠️ **未検証。**重みは根拠のない初期値（`core/shigeki.py` 参照）。
⚠️ 人気は指数に入れていない。人気薄かどうかは**外で**見ること。
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import shigeki                        # noqa: E402
from nankeiba.scraping import rakuten as rk              # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--race", type=int)
    ap.add_argument("--min", type=float, default=0.0, help="この点以上だけ出す")
    ap.add_argument("--result", action="store_true",
                    help="結果と突き合わせる（レース確定後の振り返り用）")
    args = ap.parse_args()

    cli = rk.KeibaRakuten()
    base = cli.find_race_id(args.date, args.place, 1)[:-2]
    d = f"{args.date[:4]}-{args.date[4:6]}-{args.date[6:]}"
    races = [args.race] if args.race else range(1, 13)

    print(f"\n=== {args.date} {args.place}　点火指数 ===")
    print("  変化（場/騎手/距離/間隔）＋ 前走の予熱の兆候。**未検証の重み**\n")
    for rno in races:
        rid = f"{base}{rno:02d}"
        try:
            card = rk.fetch_card(cli, rid)
        except Exception:                                # noqa: BLE001
            continue
        hd = card["header"]
        if not hd.get("distance"):
            continue
        fin = {}
        if args.result:
            try:
                for x in rk.fetch_result(cli, rid):
                    fin[x["name"]] = (x.get("finish"), x.get("popularity"))
            except Exception:                            # noqa: BLE001
                pass
        got = []
        for e in card["entries"]:
            h = [r for r in (e.get("history") or []) if r.date and r.date < d]
            ig = shigeki.ignition(hd["place"], hd["distance"],
                                  e.get("jockey"), d, h)
            if ig.score >= args.min:
                got.append((ig, e))
        if not got:
            continue
        got.sort(key=lambda t: -t[0].score)
        print(f"■ {rno}R ダ{hd['distance']}m {hd.get('race_class') or ''}")
        for ig, e in got:
            od = f"{e['odds']}倍" if e.get("odds") else "オッズ未"
            f_, pop = fin.get(e["name"], (None, None))
            res = (f"{f_:>2}着{pop or '?'}人気 " if f_ else "")
            mark = "◎" if (f_ and f_ <= 3) else ("×" if f_ else " ")
            print(f" {mark} {ig.score:>5.1f}点 ({ig.change:.1f}+{ig.preheat:.1f}) "
                  f"{e['umaban']:>2} {e['name'][:13]:<14}{od:>9} {res}{ig.label()}")
            if ig.tags:
                print(f"          変化: {' / '.join(ig.tags)}")
            if ig.warm:
                print(f"          予熱: {' / '.join(ig.warm)}")
        print()
    print("  ⚠️ 未検証。重みは初期値。人気は外で掛けること。")


if __name__ == "__main__":
    main()
