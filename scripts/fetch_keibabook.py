#!/usr/bin/env python3
"""競馬ブックから実データを取得して、指数＆展開予想の新聞を生成する。

会員 Cookie(既定 data/.keibabook_cookie)で、指定日・競馬場・レースの出馬表と
各馬の過去走を取得し、スピード指数を付けて新聞 HTML を出力する。

    python3 scripts/fetch_keibabook.py --date 20260722 --place 大井 --race 11 \
        --out out/oi11.html --text

※ 通過順(コーナー通過位置)はこのプランでは非公開(****)のため、展開予想グリッドは
   注記付きで空になる(指数・指数サマリーはすべて実データで生成)。
※ 会員本人の個人利用の範囲で、節度を持って利用すること。
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import keibabook as kb          # noqa: E402
from nankeiba.core.hindex import SpeedIndexModel        # noqa: E402
from nankeiba.core import newspaper as nb               # noqa: E402

POST_ORDER_HINT = ""


def main():
    ap = argparse.ArgumentParser(description="競馬ブックから新聞(指数＆展開予想)生成")
    ap.add_argument("--date", required=True, help="開催日 YYYYMMDD (例 20260722)")
    ap.add_argument("--place", default="大井", help="競馬場 (既定: 大井)")
    ap.add_argument("--race", type=int, required=True, help="レース番号 (例 11)")
    ap.add_argument("--cookie", default="data/.keibabook_cookie", help="Cookie ファイル")
    ap.add_argument("--out", default="out/keibabook.html")
    ap.add_argument("--text", action="store_true")
    ap.add_argument("--history", type=int, default=12, help="各馬の取得過去走数")
    ap.add_argument("--base", type=float, default=0.0, help="指数の基準値オフセット")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    client = kb.KeibabookClient.from_cookie_file(args.cookie)
    use_cache = not args.no_cache

    print(f"[1/4] 日程から {args.place} の開催を検索中…")
    race_ids = kb.find_meeting(client, args.date, args.place)
    race_id = race_ids[args.race - 1]
    print(f"      race_id = {race_id}")

    print("[2/4] 出馬表を取得中…")
    syutuba_html = client.get(f"/chihou/syutuba/{race_id}", use_cache=use_cache)
    hdr = kb.parse_race_header(syutuba_html) or {}
    entries_raw = kb.parse_entries(syutuba_html)
    print(f"      {len(entries_raw)} 頭")
    if not entries_raw:
        print("出馬表が空。まだ発表前か、ページ構造が変わった可能性。", file=sys.stderr)
        sys.exit(1)

    print("[3/4] 各馬の過去走(DB成績)を取得中…")
    paper_entries = []
    all_runs = []
    for e in entries_raw:
        hist_html = client.get(f"/db/uma/{e['umacd']}/seiseki", use_cache=use_cache)
        runs = kb.parse_history(hist_html, limit=args.history)
        all_runs.extend(runs)
        paper_entries.append(nb.PaperEntry(
            umaban=e["umaban"], name=e["name"], history=runs,
            sex_age=e.get("sex_age"),
        ))
        print(f"      {e['umaban']:>2} {e['name']:<12} 過去{len(runs)}走 "
              f"(タイム有 {sum(1 for r in runs if r.time_sec)})")

    print("[4/4] 指数を自己校正して新聞を生成中…")
    model = SpeedIndexModel.fit(all_runs, base=args.base)

    # 距離・馬場・発走はヘッダから(取得できる範囲で)
    dist = _guess_distance(syutuba_html)
    header = nb.RaceHeader(
        place=hdr.get("place", args.place), distance=dist or 0,
        date=f"{args.date[:4]}-{args.date[4:6]}-{args.date[6:]}",
        race_no=hdr.get("race_no", args.race),
        baba=None, post_time=_guess_post_time(syutuba_html),
        race_name=hdr.get("race_name"),
    )
    card = nb.build_card(header, paper_entries, model)

    has_corner = any(r.corner_pos for e in paper_entries for r in e.history)
    note = None
    if not has_corner:
        note = ("※ 通過順（コーナー通過位置）は現在の会員プランでは非公開（****）のため、"
                "展開予想グリッドは空です。指数・指数サマリーは実データで生成しています。"
                "通過順が取得できれば pace.py がそのままグリッドを描画します。")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(nb.render_html(card, pace_note=note))
    print(f"✅ HTML を書き出しました: {args.out}")

    if args.text:
        print()
        print(nb.render_text(card))
        if note:
            print("\n" + note)


def _guess_distance(html: str) -> int | None:
    import re
    m = re.search(r"(\d{3,4})\s*m", html)
    return int(m.group(1)) if m else None


def _guess_post_time(html: str) -> str | None:
    import re
    m = re.search(r"発走\s*([0-2]?\d:\d\d)", html)
    return m.group(1) if m else None


if __name__ == "__main__":
    main()
