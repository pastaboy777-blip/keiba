#!/usr/bin/env python3
"""楽天競馬から実データを取得して、指数＆展開予想の新聞を生成する(完全版)。

楽天の出馬表は馬柱にタイムも通過順もインラインで持つため、1レース1取得で
スピード指数と展開予想グリッドの両方が作れる(Cookie 不要・無料)。

    python3 scripts/fetch_rakuten.py --date 20260722 --place 大井 --race 11 \
        --out out/oi11_rakuten.html --text

    # race_id を直接指定してもよい:
    python3 scripts/fetch_rakuten.py --race-id 202607222015060311 --out out/x.html

※ 節度を持って個人利用の範囲で。取得データの再配布はしない。
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import rakuten as rk            # noqa: E402
from nankeiba.core.hindex import SpeedIndexModel        # noqa: E402
from nankeiba.core import newspaper as nb               # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="楽天競馬から新聞(指数＆展開予想)生成")
    ap.add_argument("--date", help="開催日 YYYYMMDD")
    ap.add_argument("--place", default="大井", help="競馬場 (既定: 大井)")
    ap.add_argument("--race", type=int, help="レース番号")
    ap.add_argument("--race-id", help="楽天 race_id を直接指定(18桁)")
    ap.add_argument("--out", default="out/rakuten.html")
    ap.add_argument("--text", action="store_true")
    ap.add_argument("--baba", choices=["良", "稍", "重", "不"],
                    help="今回の想定馬場。重・不良で展開を前残り寄りに補正し馬場適性を表示")
    ap.add_argument("--base", type=float, default=0.0, help="指数の基準値オフセット")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    client = rk.KeibaRakuten()
    use_cache = not args.no_cache

    if args.race_id:
        race_id = args.race_id
    else:
        if not (args.date and args.race):
            ap.error("--race-id か、--date と --race の両方が必要です")
        print(f"[1/3] {args.date} {args.place} の開催を検索中…")
        race_id = client.find_race_id(args.date, args.place, args.race)
    print(f"      race_id = {race_id}")

    print("[2/3] 出馬表(馬柱つき)を取得中…")
    html = client.get(f"/race_card/list/RACEID/{race_id}", use_cache=use_cache)
    card = rk.parse_card(html)
    hd = card["header"]
    entries = card["entries"]
    print(f"      {hd.get('place')} {hd.get('race_no')}R {hd.get('distance')}m / {len(entries)}頭")
    for e in entries:
        n_corner = sum(1 for r in e["history"] if r.corner_pos)
        print(f"      {e['umaban']:>2} {e['name']:<12} 過去{len(e['history'])}走 "
              f"(タイム{sum(1 for r in e['history'] if r.time_sec)}/通過順{n_corner})")

    print("[3/3] 指数を自己校正して新聞を生成中…")
    all_runs = [r for e in entries for r in e["history"]]
    model = SpeedIndexModel.fit(all_runs, base=args.base)

    paper_entries = [
        nb.PaperEntry(umaban=e["umaban"], name=e["name"], history=e["history"])
        for e in entries
    ]
    date = args.date or (race_id[:4] + "-" + race_id[4:6] + "-" + race_id[6:8])
    if args.date:
        date = f"{args.date[:4]}-{args.date[4:6]}-{args.date[6:]}"
    header = nb.RaceHeader(
        place=hd.get("place") or args.place,
        distance=hd.get("distance") or 0,
        date=date,
        race_no=hd.get("race_no") or args.race,
        baba=args.baba,
        post_time=hd.get("post_time"),
        race_name=hd.get("race_name"),
    )
    ncard = nb.build_card(header, paper_entries, model)

    has_corner = any(r.corner_pos for e in paper_entries for r in e.history)
    note = None if has_corner else "※ 通過順が取得できませんでした(ページ構造変更の可能性)。"

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(nb.render_html(ncard, pace_note=note))
    print(f"✅ HTML を書き出しました: {args.out}")

    if args.text:
        print()
        print(nb.render_text(ncard))


if __name__ == "__main__":
    main()
