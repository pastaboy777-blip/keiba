#!/usr/bin/env python3
"""指定日・競馬場の全レースを1ファイルの新聞にまとめて出力する(楽天データ)。

    python3 scripts/make_paper_all.py --date 20260722 --place 大井 --out out/oi_all.html
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import rakuten as rk            # noqa: E402
from nankeiba.core.hindex import SpeedIndexModel        # noqa: E402
from nankeiba.core import newspaper as nb               # noqa: E402
from nankeiba.core import rivals as rv                  # noqa: E402


def build_one(client, race_id, date, place, race_no, rival_index=None):
    card = rk.fetch_card(client, race_id)
    hd = card["header"]
    entries = card["entries"]
    if not entries:
        return None
    runs = [r for e in entries for r in e["history"]]
    model = SpeedIndexModel.fit(runs)
    pe = [nb.PaperEntry(umaban=e["umaban"], name=e["name"], history=e["history"], sire=e.get("sire"), bms=e.get("bms"))
          for e in entries]
    header = nb.RaceHeader(
        place=hd.get("place") or place, distance=hd.get("distance") or 0,
        date=f"{date[:4]}-{date[4:6]}-{date[6:]}", race_no=hd.get("race_no") or race_no,
        baba=None, post_time=hd.get("post_time"), race_name=hd.get("race_name"),
    )
    return nb.render_html(nb.build_card(header, pe, model, rival_index))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", default="大井")
    ap.add_argument("--races", default="1-12")
    ap.add_argument("--out", default="out/paper_all.html")
    args = ap.parse_args()

    a, b = (args.races.split("-") + [args.races])[:2]
    rnos = list(range(int(a), int(b) + 1)) if "-" in args.races else [int(x) for x in args.races.split(",")]

    client = rk.KeibaRakuten()
    print("索引を作成中（前走で先着した相手の、その後）…")
    ridx = rv.Index()
    meeting = client.find_race_id(args.date, args.place, 1)[:-2]

    style = None
    papers = []
    for rno in rnos:
        try:
            doc = build_one(client, meeting + f"{rno:02d}", args.date, args.place,
                            rno, ridx)
        except Exception as e:                       # noqa: BLE001
            print(f"  R{rno}: 失敗 {e}")
            continue
        if not doc:
            print(f"  R{rno}: 出馬表未発表")
            continue
        if style is None:
            m = re.search(r"<style>.*?</style>", doc, re.S)
            style = m.group(0) if m else ""
        body = re.search(r"<body>(.*)</body>", doc, re.S)
        papers.append(body.group(1) if body else "")
        print(f"  R{rno}: OK")

    if not papers:
        print("生成なし(発表前?)"); return

    nav = " ".join(f'<a href="#r{i}">{i}R</a>' for i in rnos)
    sections = "".join(
        f'<div id="r{rnos[i]}" class="race-sec">{p}</div>' for i, p in enumerate(papers)
    )
    title = f"{args.place} {args.date[4:6]}/{args.date[6:]} 全レース 指数＆展開予想"
    out_html = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
{style}
<style>
body{{background:#f3f2ee;}}
.topnav{{position:sticky;top:0;z-index:9;background:#111;color:#fff;padding:8px 12px;
  font-weight:700;display:flex;gap:6px;flex-wrap:wrap;align-items:center;}}
.topnav .t{{margin-right:10px;}}
.topnav a{{color:#fff;background:#333;border-radius:4px;padding:2px 9px;text-decoration:none;font-size:13px;}}
.topnav a:hover{{background:#c00;}}
.race-sec{{padding:6px 0 22px;}}
</style></head><body>
<div class="topnav"><span class="t">🏇 {title}</span>{nav}</div>
{sections}
</body></html>"""

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(out_html)
    print(f"✅ {len(papers)}レースを書き出し: {args.out}")


if __name__ == "__main__":
    main()
