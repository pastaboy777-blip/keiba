# -*- coding: utf-8 -*-
"""○（2番手の印）の作り方を複数並べて比べる。◎は現行のまま固定する。

なぜ:
  現行の○（エッジ数→399 の2位）は川崎7か月448点で単複均等 33.4%。
  土台（6番人気以下を平等に買う）79.1% の半分以下で、ここが最大の穴。

注意（今日いちばんの教訓）:
  候補を並べて一番良かったものを選ぶ行為そのものが、偶然を拾う。だから
  期間を前半・後半に割って両方を出す。**片方だけ良い案は採らない。**
  そして土台を必ず併記する。土台を超えないなら「○は凝らずに拾うだけ」が答え。

    python3 scripts/nankan_maru.py --place 川崎 --from 2026-01-01 --to 2026-07-31 --split 2026-04-20
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

import ana399 as A
import ana_recall as R
from nankan_zubu_backtest import CARD, PERF, payouts, race_days


def norms_of(entry, place, pa, ba, n=5):
    out = []
    for pr in (entry.recent_runs or []):
        v = A.norm_agari(pr.agari, pr.place, A.band(pr.distance), place, pa, ba)
        if v is not None and len(out) < n:
            out.append(v)
    return out


def main():
    ap = argparse.ArgumentParser(description="○の作り方の比較")
    ap.add_argument("--place", default="川崎")
    ap.add_argument("--from", dest="d_from", required=True)
    ap.add_argument("--to", dest="d_to", required=True)
    ap.add_argument("--split", required=True, help="この日より前を前半、以降を後半")
    ap.add_argument("--pop-min", type=int, default=6)
    ap.add_argument("--thr", type=float, default=40.5)
    args = ap.parse_args()

    pa, ba = A.load_adj()
    client = PoliteClient(use_cache=True)
    split = date.fromisoformat(args.split)
    days = race_days(client, args.place,
                     date.fromisoformat(args.d_from), date.fromisoformat(args.d_to))

    # (rule, 期) -> [点数, 1着, 3着内, 単払戻, 複払戻]
    acc = defaultdict(lambda: [0, 0, 0, 0.0, 0.0])

    for d, races in days:
        half = "前半" if d < split else "後半"
        for rno, rid in sorted(races.items()):
            try:
                page = P.parse_card_page(client.get(CARD.format(r=rid)), rid)
                rhtml = client.get(PERF.format(r=rid))
                res = P.parse_result_page(rhtml, rid)
            except Exception:
                continue
            tan, fuku = payouts(rhtml)
            if not fuku or not res.rows:
                continue
            fin = {r.umaban: r for r in res.rows}
            tb = A.band(page.distance)
            cand = []
            for e in getattr(page, "entries", page):
                r_ = fin.get(e.umaban)
                if not r_ or not r_.popularity or r_.popularity < args.pop_min:
                    continue
                tags, _cw = R.edges_for(e, page.distance, today=d)
                ev = A.evaluate(e, tb, args.place, pa, ba, args.thr, False)
                nm = norms_of(e, args.place, pa, ba)
                cand.append(dict(e=e, r=r_, edge=len(tags), s399=ev["score"], nm=nm,
                                 span=(max(nm) - min(nm)) if len(nm) >= 3 else None,
                                 mid=st.median(nm) if nm else None))
            if len(cand) < 3:
                continue

            def tally(key, c):
                a = acc[key]
                a[0] += 1
                if c["r"].finish_pos == 1:
                    a[1] += 1
                    a[3] += tan.get(c["e"].umaban, 0)
                if c["r"].finish_pos <= 3:
                    a[2] += 1
                    a[4] += fuku.get(c["e"].umaban, 0)

            for c in cand:
                tally(("土台", half), c)

            order = sorted(cand, key=lambda c: (-c["edge"], -c["s399"]))
            honmei = order[0]
            tally(("◎(現行)", half), honmei)
            rest = [c for c in cand if c is not honmei]
            if not rest:
                continue

            picks = {
                "A 現行(同じ物差しの2位)": order[1],
                "B 399スコア最上位": max(rest, key=lambda c: c["s399"]),
                "C 中心の速さ最上位": min([c for c in rest if c["mid"] is not None],
                                          key=lambda c: c["mid"], default=None),
                "D ブレ幅2.0以下×中心": min([c for c in rest
                                             if c["span"] is not None and c["span"] <= 2.0],
                                            key=lambda c: c["mid"], default=None),
                "E いちばん人気薄": max(rest, key=lambda c: c["r"].popularity),
                "F エッジ数最少": min(rest, key=lambda c: c["edge"]),
            }
            for k, c in picks.items():
                if c is not None:
                    tally((k, half), c)

    keys = ["土台", "◎(現行)", "A 現行(同じ物差しの2位)", "B 399スコア最上位",
            "C 中心の速さ最上位", "D ブレ幅2.0以下×中心", "E いちばん人気薄", "F エッジ数最少"]
    print(f"\n■ {args.place} {args.d_from}〜{args.d_to}（分割 {args.split}）")
    print(f"\n{'':<26}{'前半 点数':>10}{'単複均等':>10}{'後半 点数':>12}{'単複均等':>10}{'通算':>10}")
    for k in keys:
        a, b = acc[(k, "前半")], acc[(k, "後半")]
        if not a[0] and not b[0]:
            continue
        f = lambda x: (x[3] + x[4]) / (x[0] * 200) * 100 if x[0] else 0
        tot = [a[i] + b[i] for i in range(5)]
        print(f"{k:<26}{a[0]:>10}{f(a):>9.1f}%{b[0]:>12}{f(b):>9.1f}%{f(tot):>9.1f}%")
    print("\n※ 前半・後半の両方で土台を超えないものは採らない。片方だけなら偶然と見る。")


if __name__ == "__main__":
    main()
