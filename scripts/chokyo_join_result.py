#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""調教(整備済み) × 楽天結果(着順/厩舎/人気) を結合。

入力: data/samples/chokyo_tidy_{tag}.jsonl（tidy_chokyo.py の出力）
出力: data/samples/chokyo_joined_{tag}.jsonl（調教特徴＋着順/厩舎/人気/好走フラグ）
使い方: python3 scripts/chokyo_join_result.py --tag urawa --place 浦和
楽天は PoliteClient(1.5s)。結果ページ列: 着(0)/枠/馬番(2)/馬名(3)/性齢/斤量/馬体重/騎手/タイム/着差/上がり(10)/調教師(11)/人気(12)。
"""
from __future__ import annotations
import argparse, json, os, re, sys
from collections import defaultdict
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES  # noqa: E402
from nankeiba.scraping.client import PoliteClient  # noqa: E402
from nankeiba.scraping import parser as P  # noqa: E402

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
RES = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"


def parse_result(html: str) -> dict:
    """馬番 → {着, 厩舎, 人気} を返す。"""
    s = BeautifulSoup(html, "html.parser")
    out = {}
    for tr in s.select("table tr"):
        c = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(c) >= 13 and re.fullmatch(r"\d+", c[0]) and re.fullmatch(r"\d+", c[2]):
            chaku = int(c[0]); umaban = int(c[2])
            trainer = c[11] if len(c) > 11 else ""
            pop = int(c[12]) if len(c) > 12 and c[12].isdigit() else None
            out[umaban] = {"着順": chaku, "厩舎": trainer, "人気": pop}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--place", default="浦和")
    ap.add_argument("--out-dir", default="data/samples")
    args = ap.parse_args()

    tidy = os.path.join(args.out_dir, f"chokyo_tidy_{args.tag}.jsonl")
    rows = [json.loads(l) for l in open(tidy, encoding="utf-8")]
    by_dr = defaultdict(list)  # (date, race_no) -> rows
    for r in rows:
        by_dr[(r["date"], r["race_no"])].append(r)
    dates = sorted({d for d, _ in by_dr})
    print(f"結合対象: {len(rows)}行 / {len(by_dr)}レース / {len(dates)}日", file=sys.stderr)

    c = PoliteClient()
    code = NANKAN_CODES[args.place]
    joined, hit, miss = [], 0, 0
    for ymd in dates:
        try:
            idx = c.get(CARD.format(r=day_index_race_id(ymd, args.place)))
            races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=code))
        except Exception as e:
            print(f"[{ymd}] race一覧失敗: {e}", file=sys.stderr); continue
        for rno in sorted({rn for (d, rn) in by_dr if d == ymd}):
            rid = races.get(rno)
            if not rid:
                continue
            try:
                res = parse_result(c.get(RES.format(r=rid)))
            except Exception as e:
                print(f"[{ymd} {rno}R] 結果失敗: {e}", file=sys.stderr); continue
            for r in by_dr[(ymd, rno)]:
                m = res.get(r["umaban"])
                if m:
                    r2 = dict(r, **m, 好走=(m["着順"] <= 3))
                    joined.append(r2); hit += 1
                else:
                    joined.append(dict(r, 着順=None, 厩舎=None, 人気=None, 好走=None)); miss += 1
        print(f"[{ymd}] 結合 {sum(1 for j in joined if j['date']==ymd)}行", file=sys.stderr)

    out = os.path.join(args.out_dir, f"chokyo_joined_{args.tag}.jsonl")
    with open(out, "w", encoding="utf-8") as w:
        for j in joined:
            w.write(json.dumps(j, ensure_ascii=False) + "\n")
    print(f"完了: 結合{len(joined)}行 (着順取得 {hit} / 欠損 {miss}) → {out}")


if __name__ == "__main__":
    main()
