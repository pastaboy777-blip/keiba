# -*- coding: utf-8 -*-
"""バイアスと逆の競馬をして、強い内容で負けた馬を拾う。

背景（2026-08-01 実測）:
  船橋5〜6月の12開催日は、12日すべてで勝ち馬の4角position が 0.5 を下回り、期間平均 0.30。
  つまり前に行った馬が残る場である。そこで後方から進めた馬は、それだけで不利を背負っている。

  市場は着順を読む。だから「後ろから行って届かず5着」は、着順どおりの評価しかされない。
  しかし前残りの日に後方から押し上げた馬は、着順が示すより強い競馬をしている。

拾う条件:
  ① 4角position が back 以上（＝後方にいた。この場のバイアスと逆）
  ② 1着ではない（＝負けた馬。勝ち馬は誰にでも見えて人気を被る）
  ③ 強い内容 … 4角から着順まで上がった幅（gain）が大きい、または上がりがレース上位
       ★着順そのものは条件にしない。大敗していても、後方から押し上げたか終いが上位なら拾う。
         前残りの場で後ろから行った時点で不利を背負っており、着順はその不利の結果でしかない。

    python3 scripts/nankan_gyaku.py --place 船橋 --from 2026-05-01 --to 2026-07-04
    python3 scripts/nankan_gyaku.py --place 船橋 --from 2026-05-01 --to 2026-07-04 --card 2026-08-02
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES
from nankeiba.scraping import parser as P

from nankan_baba import race_shape
from nankan_zubu_backtest import CARD, PERF, race_days


def result_rows(html):
    """着順・馬番・馬名・人気・上がりを結果表から拾う。"""
    s = BeautifulSoup(html, "html.parser")
    tb = P._find_result_table(s)
    if tb is None:
        return []
    out = []
    for tr in (tb.find("tbody") or tb).find_all("tr"):
        o = tr.find("td", class_="order")
        num = tr.find("td", class_="number")
        if o is None or num is None or not o.get_text(strip=True).isdigit():
            continue
        sp = tr.find("td", class_="spurt")
        rk = tr.find("td", class_="rank")
        a = tr.find("a", href=lambda h: h and "HORSEID/" in h)
        out.append(dict(
            fin=int(o.get_text(strip=True)), umaban=int(num.get_text(strip=True)),
            name=a.get_text(strip=True) if a else "",
            horse_id=P._href_id(a["href"]) if a else "",
            pop=int(rk.get_text(strip=True)) if rk and rk.get_text(strip=True).isdigit() else None,
            agari=float(sp.get_text(strip=True))
            if sp and re.match(r"[\d.]+$", sp.get_text(strip=True)) else None))
    return out


def main():
    ap = argparse.ArgumentParser(description="バイアスと逆で強い内容だった敗戦馬")
    ap.add_argument("--place", default="船橋", choices=list(NANKAN_CODES))
    ap.add_argument("--from", dest="d_from", required=True)
    ap.add_argument("--to", dest="d_to", required=True)
    ap.add_argument("--back", type=float, default=0.60,
                    help="4角position がこの値以上を『後方にいた』とみなす")
    ap.add_argument("--gain", type=float, default=0.25,
                    help="4角から着順までこれ以上押し上げたら『強い内容』")
    ap.add_argument("--card", help="この日の出走表と突き合わせ、該当馬だけ出す")
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    client = PoliteClient(use_cache=True)
    days = race_days(client, args.place,
                     date.fromisoformat(args.d_from), date.fromisoformat(args.d_to))

    hits = []
    for d, rs in days:
        for rno, rid in sorted(rs.items()):
            try:
                html = client.get(PERF.format(r=rid))
                res = P.parse_result_page(html, rid)
            except Exception:
                continue
            rows = result_rows(html)
            a3, order = race_shape(html)
            if not rows or not order:
                continue
            n = len(rows)
            ag = sorted((r["agari"] for r in rows if r["agari"]), reverse=False)
            for r in rows:
                if r["umaban"] not in order or r["fin"] == 1:
                    continue
                pos4 = (order.index(r["umaban"]) + 1) / n
                posf = r["fin"] / n
                gain = pos4 - posf
                arank = (ag.index(r["agari"]) + 1) if r["agari"] in ag else None
                if pos4 < args.back:
                    continue
                if gain < args.gain and not (arank and arank <= 2):
                    continue
                hits.append(dict(d=d, rno=rno, dist=res.distance, baba=res.baba, n=n,
                                 gain=gain, pos4=pos4, arank=arank, a3=a3, **r))

    if args.card:
        cd = date.fromisoformat(args.card)
        ymd = cd.strftime("%Y%m%d")
        card = dict(P.parse_race_links(
            client.get(CARD.format(r=day_index_race_id(ymd, args.place))),
            date_yyyymmdd=ymd, jyo_code=NANKAN_CODES[args.place]))
        today = {}
        for rno, rid in sorted(card.items()):
            page = P.parse_card_page(client.get(CARD.format(r=rid)), rid)
            for e in getattr(page, "entries", page):
                today[e.horse_id] = (rno, e.umaban, e.horse_name)
        hits = [h for h in hits if h["horse_id"] in today]
        print(f"\n■ {args.place} {args.d_from}〜{args.d_to} で"
              f"『後方から押し上げて負けた』馬のうち、{args.card} に出走する馬\n")
        hits.sort(key=lambda h: (today[h["horse_id"]][0], -h["gain"]))
        cur = None
        for h in hits[:args.top]:
            rno, um, nm = today[h["horse_id"]]
            if rno != cur:
                print(f"=== {args.card} {args.place}{rno}R")
                cur = rno
            print(f"  {um:>2} {nm:<14} ← {h['d']} {h['rno']}R ダ{h['dist']}{h['baba']} "
                  f"{h['fin']}着/{h['n']}頭 {h['pop']}人気　"
                  f"4角{h['pos4']:.2f}→着順{h['fin']/h['n']:.2f}（+{h['gain']:.2f}）"
                  f" 上{h['agari']} レース{h['arank']}位"
                  + ("★最速" if h['arank'] == 1 else ""))
        if not hits:
            print("  該当なし")
        return

    print(f"\n■ {args.place} {args.d_from}〜{args.d_to}"
          f"　後方(4角{args.back}以上)から押し上げて負けた馬 {len(hits)}件\n")
    hits.sort(key=lambda h: -h["gain"])
    for h in hits[:args.top]:
        print(f"  {h['d']} {h['rno']:>2}R ダ{h['dist']}{h['baba']} {h['name']:<14}"
              f"{h['fin']:>2}着/{h['n']}頭 {str(h['pop']):>2}人気　"
              f"4角{h['pos4']:.2f}→{h['fin']/h['n']:.2f}（+{h['gain']:.2f}）"
              f" 上{h['agari']} レース{h['arank']}位")


if __name__ == "__main__":
    main()
