#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ライブ穴スコア採点：指定日・会場の全馬に穴スコアを当て、高スコア馬を炙り出す。

前提: その日の調教が chokyo_tidy_{tag} に整備済み（keibabook収集→tidy_chokyo.py）。
      厩舎は楽天カード(出馬表)から取得。人気は当日オッズで各自確認。
使い方: python3 scripts/live_ana_score.py --date 20260713 --place 浦和 --tag urawa
"""
import sys, os, json, argparse
sys.path.insert(0, "scripts")
sys.path.insert(0, "src")
import ana_score as A
from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from bs4 import BeautifulSoup

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"


def parse_trainers(html):
    """楽天カード → {馬番: 調教師}。性齢セル(【…%】を含む)の末尾語が調教師。"""
    s = BeautifulSoup(html, "html.parser")
    out = {}
    for tr in s.select("table tr"):
        cs = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if not cs or not cs[0].isdigit():
            continue
        prof = next((x for x in cs if "【" in x), "")
        name = prof.split("】")[-1].strip().split()[-1] if "】" in prof else ""
        out[int(cs[0])] = name
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYYMMDD")
    ap.add_argument("--place", default="浦和")
    ap.add_argument("--tag", default="urawa")
    args = ap.parse_args()

    pool = A.load_pool()
    stable_rate = A.stable_ana_rate(pool)
    funa_med = A.funabashi_baseline()

    tidy = [json.loads(l) for l in open(f"data/samples/chokyo_tidy_{args.tag}.jsonl", encoding="utf-8")]
    day = {(r["race_no"], r["umaban"]): r for r in tidy if r["date"] == args.date}
    if not day:
        raise SystemExit(f"{args.date} の調教データが chokyo_tidy_{args.tag} にありません")

    c = PoliteClient()
    idx = c.get(CARD.format(r=day_index_race_id(args.date, args.place)))
    races = dict(P.parse_race_links(idx, date_yyyymmdd=args.date, jyo_code=NANKAN_CODES[args.place]))

    print(f"■ {args.date} {args.place} 穴スコア（全馬採点・人気は当日オッズで確認）")
    print(f"  基準厩舎数{len(stable_rate)} / 船橋下地保有{len(funa_med)}頭\n")
    for rno in sorted(races):
        trainers = parse_trainers(c.get(CARD.format(r=races[rno])))
        scored = []
        for umaban, tr_name in trainers.items():
            row = day.get((rno, umaban))
            if not row:
                continue
            sc, br = A.score_row(dict(row, 厩舎=tr_name), stable_rate, funa_med)
            scored.append((sc, umaban, row.get("馬名"), tr_name, br))
        scored.sort(reverse=True)
        print(f"── {rno}R ──")
        for sc, umaban, name, tr_name, br in scored:
            if sc >= 1 or sc <= -2:
                mark = "★" if sc >= 3 else ("○" if sc >= 1 else "✕")
                print(f"  {mark}{sc:+4.1f} {umaban:>2}番 {name}({tr_name}) [{' '.join(br)}]")
        if all(s < 1 for s, *_ in scored):
            print("  （score≥1なし＝調教的な穴候補薄）")
        print()


if __name__ == "__main__":
    main()
