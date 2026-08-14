#!/usr/bin/env python3
"""Mの法則の考え方で出馬表を見る（鮮度と硬直）。

    python3 scripts/nankan_m.py --date 20260814 --place 大井
    python3 scripts/nankan_m.py --date 20260814 --place 大井 --result

鮮度（ショックの合計） − 硬直（前走の反動） を出す。
**買う材料と消す材料を両方持つ**のが要点で、こちらが自力で作った点火指数
（`shigeki.py`）には消す側が無かった。

⚠️ 今井雅宏氏の理論そのものではない。公開情報からの独自解釈（`core/mhousoku.py`）。
⚠️ 未検証。重みは初期値。
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import mhousoku as M                  # noqa: E402
from nankeiba.scraping import rakuten as rk              # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--race", type=int)
    ap.add_argument("--result", action="store_true")
    args = ap.parse_args()

    cli = rk.KeibaRakuten()
    base = cli.find_race_id(args.date, args.place, 1)[:-2]
    d = f"{args.date[:4]}-{args.date[4:6]}-{args.date[6:]}"

    print(f"\n=== {args.date} {args.place}　Mの法則（鮮度 − 硬直）===")
    print("  ショック＝距離変更／位置取り／内枠／休み明け／場替わり／乗替")
    print("  硬直＝前走が激走（人気薄で3着内）だった直後の反動\n")
    for rno in ([args.race] if args.race else range(1, 13)):
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
        n = len(card["entries"])
        got = []
        for e in card["entries"]:
            h = [r for r in (e.get("history") or []) if r.date and r.date < d]
            st = M.state(hd["place"], hd["distance"], e.get("jockey"),
                         e.get("umaban"), n, hd.get("race_class"), d, h)
            got.append((st, e))
        got.sort(key=lambda t: -t[0].score)
        print(f"■ {rno}R ダ{hd['distance']}m {hd.get('race_class') or ''}")
        for st, e in got:
            if abs(st.score) < 1.0 and not st.risks:
                continue
            f_, pop = fin.get(e["name"], (None, None))
            res = f"{f_:>2}着{pop or '?'}人気 " if f_ else ""
            mark = "◎" if (f_ and f_ <= 3) else ("×" if f_ else " ")
            od = f"{e['odds']}倍" if e.get("odds") else ""
            print(f" {mark}{st.score:>+5.1f} (鮮{st.fresh:.1f}/硬{st.stiff:.1f}) "
                  f"{e['umaban']:>2} {e['name'][:13]:<14}{od:>8} {res}{st.label()}")
            if st.shocks:
                print(f"        ショック: {' / '.join(st.shocks)}")
            if st.risks:
                print(f"        **硬直**: {' / '.join(st.risks)}")
        print()
    print("  ⚠️ 未検証。本家の理論そのものではない（公開情報からの独自解釈）。")


if __name__ == "__main__":
    main()
