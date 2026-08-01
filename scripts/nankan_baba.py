# -*- coding: utf-8 -*-
"""南関：開催日ごとに『その日どういう決着だったか』をまとめる。

馬場状態（良・稍・重・不）は主催者の発表であって、決着の中身とは別物である。
2026-08-01 の測定では、川崎の勝ち馬の上がりは良39.34／稍39.46／重39.78／不39.14 で
ほとんど動かず、しかも不良がいちばん速かった（ダートは湿ると速い）。
だから「今日は渋っているから差しが決まる」式の読みは、発表だけでは立たない。

そこで結果ページから実際の決着を拾って日ごとに並べる:

  上がり3F   … レース自身の上がり。その日どこで決着したか
  4角position … 勝ち馬が4角で何番手だったかを頭数で割った値
                 小さいほど前残り。0.5より大きい日は差しが届いた日
  前で勝った率 … 勝ち馬が4角3番手以内だった割合
  勝ち馬の人気 … 荒れたか堅かったか

    python3 scripts/nankan_baba.py --place 船橋 --from 2026-05-01 --to 2026-06-30
"""
from __future__ import annotations

import argparse
import re
import statistics as st
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping.race_id import NANKAN_CODES
from nankeiba.scraping import parser as P

from nankan_zubu_backtest import PERF, race_days

_A3F = re.compile(r"上がり\s*4F\s*([\d.]+)\s*-\s*3F\s*([\d.]+)")
_C4 = re.compile(r"４角\s*([0-9,()\-= ]+?)\s*■")


def race_shape(html):
    """レースの上がり3Fと、4角の通過順（馬番の並び）を返す。"""
    t = re.sub(r"\s+", " ", BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    m = _A3F.search(t)
    a3 = float(m.group(2)) if m else None
    order = []
    if m4 := _C4.search(t):
        # "(1,7,6),(3,8,10,9)-(2,4,5)" → 並び順に馬番を展開する。
        # 括弧は横並びを意味するが、順位付けには載っている順で足りる。
        for x in re.split(r"[,\-=()\s]+", m4.group(1)):
            if x.isdigit():
                order.append(int(x))
    return a3, order


def main():
    ap = argparse.ArgumentParser(description="南関の日ごとの決着傾向")
    ap.add_argument("--place", default="船橋", choices=list(NANKAN_CODES))
    ap.add_argument("--from", dest="d_from", required=True)
    ap.add_argument("--to", dest="d_to", required=True)
    args = ap.parse_args()

    client = PoliteClient(use_cache=True)
    days = race_days(client, args.place,
                     date.fromisoformat(args.d_from), date.fromisoformat(args.d_to))

    print(f"\n■ {args.place} {args.d_from}〜{args.d_to}\n")
    print(f"{'日付':<12}{'馬場':<8}{'R':>3}{'上がり3F':>9}{'4角position':>12}"
          f"{'前で勝ち':>9}{'勝ち馬人気':>11}")
    rows = []
    for d, rs in days:
        babas, a3s, poss, front, pops = [], [], [], 0, []
        for rno, rid in sorted(rs.items()):
            try:
                html = client.get(PERF.format(r=rid))
                res = P.parse_result_page(html, rid)
            except Exception:
                continue
            if not res.rows:
                continue
            w = next((r for r in res.rows if r.finish_pos == 1), None)
            if not w:
                continue
            babas.append(res.baba or "?")
            if w.popularity:
                pops.append(w.popularity)
            a3, order = race_shape(html)
            if a3:
                a3s.append(a3)
            if order and w.umaban in order:
                p = (order.index(w.umaban) + 1) / len(order)
                poss.append(p)
                if order.index(w.umaban) < 3:
                    front += 1
        if not a3s:
            continue
        bb = "/".join(f"{k}{v}" for k, v in Counter(babas).most_common())
        rows.append(dict(d=d, bb=bb, n=len(a3s), a3=st.mean(a3s),
                         pos=st.mean(poss) if poss else None,
                         front=front / len(poss) if poss else None,
                         pop=st.mean(pops) if pops else None))
        print(f"\r  収集 {d}", end="", flush=True)

    print("\r" + " " * 30 + "\r", end="")
    if rows:
        for r in rows:
            print(f"{str(r['d']):<12}{r['bb']:<8}{r['n']:>3}{r['a3']:>9.2f}"
                  f"{(r['pos'] if r['pos'] is not None else 0):>12.2f}"
                  f"{(r['front'] * 100 if r['front'] is not None else 0):>8.0f}%"
                  f"{(r['pop'] if r['pop'] is not None else 0):>11.1f}")
        a = [r["a3"] for r in rows]
        p = [r["pos"] for r in rows if r["pos"] is not None]
        print(f"\n  期間平均  上がり3F {st.mean(a):.2f}（幅 {min(a):.2f}〜{max(a):.2f}）"
              f"／4角position {st.mean(p):.2f}")
        print("  4角position が 0.5 より小さい日＝前残り、大きい日＝差しが届いた日。")


if __name__ == "__main__":
    main()
