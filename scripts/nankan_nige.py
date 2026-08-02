# -*- coding: utf-8 -*-
"""出走表から『前半が速くなるか』を先に決める。

2026-08-02 の船橋で、同じ日に正反対の理由で高配当が2つ出た。

  8R … ①②が3走とも4角1番手の逃げ馬。2頭が競って前半36.2（今日2番目に速い）、
        上がり40.3（今日いちばん遅い）。4角1〜3番手が8着・6着・9着で全滅し、
        5番手以降が1〜5着を独占。9番人気の3着が複2,330円。
  9R … 4角1番手を続けている馬がいない。前半は落ち着き、上がり41.9の消耗戦。
        18日前に浦和を使って動けた11番人気が4角3番手を取り、そのまま2着で複1,850円。

  どちらも「後方型を買う」「前型を買う」の一本では取れない。分岐は出走表で立つ。

判定:
  逃げ馬 ＝ 直近3走のうち2走以上で4角1番手だった馬（1走だけなら『逃げ候補』）
  2頭以上 → ハナ争いになる → 前半が速くなる → 後方から押し上げる馬を狙う
  1頭以下 → 単騎で行ける → 前半が落ち着く → 前半分で運べる馬を狙う

  ★これは仮説である。--check で過去日に当てて、予測どおりの決着だったかを出す。
    当たっていなければ捨てること。

    python3 scripts/nankan_nige.py --date 2026-08-02 --place 船橋 --check
    python3 scripts/nankan_nige.py --date 2026-08-03 --place 船橋
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES
from nankeiba.scraping import parser as P

from nankan_baba import race_shape
from nankan_babasa import sec
from nankan_zubu_backtest import CARD, PERF, payouts

NANKAN = {"船橋", "川崎", "大井", "浦和"}


def style(runs):
    """直近3走の4角から脚質を数える。(逃げた回数, 前半分にいた回数, 走数)"""
    nige = zen = n = 0
    for r in runs[:3]:
        c = r.corner or []
        if not c or not r.field_size:
            continue
        n += 1
        if c[-1] == 1:
            nige += 1
        if c[-1] / r.field_size <= 0.4:
            zen += 1
    return nige, zen, n


def main():
    ap = argparse.ArgumentParser(description="出走表から前半の速さを先に決める")
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", default="船橋", choices=list(NANKAN_CODES))
    ap.add_argument("--check", action="store_true", help="結果と突き合わせて答え合わせする")
    args = ap.parse_args()

    d = date.fromisoformat(args.date)
    ymd = d.strftime("%Y%m%d")
    client = PoliteClient(use_cache=True)
    card = dict(P.parse_race_links(
        client.get(CARD.format(r=day_index_race_id(ymd, args.place))),
        date_yyyymmdd=ymd, jyo_code=NANKAN_CODES[args.place]))

    hits, rows = [], []
    for rno, rid in sorted(card.items()):
        page = P.parse_card_page(client.get(CARD.format(r=rid)), rid)
        ents = getattr(page, "entries", page)
        nige, kouho, sharp = [], [], []
        for e in ents:
            runs = e.recent_runs or []
            n, z, k = style(runs)
            if n >= 2:
                nige.append(e)
            elif n == 1:
                kouho.append(e)
            # ズブくない馬＝他場を使っていて間隔が短い
            if runs and runs[0].date and runs[0].place:
                try:
                    gap = (d - date.fromisoformat(str(runs[0].date))).days
                except Exception:
                    gap = None
                if gap is not None and gap <= 21 and runs[0].place != args.place:
                    sharp.append((e, gap, runs[0].place, runs[0].distance))
        shape = "崩れ" if len(nige) >= 2 else "落着"
        rows.append(dict(rno=rno, rid=rid, dist=page.distance, n=len(ents),
                         nige=nige, kouho=kouho, sharp=sharp, shape=shape))

    print(f"\n■ {args.place} {args.date}　逃げ馬の数から前半を先に決める\n")
    for r in rows:
        mark = "🔥 前半が速くなる → 後方から押し上げる馬" if r["shape"] == "崩れ" \
               else "　 前半は落ち着く → 前半分で運べる馬"
        print(f"{r['rno']:>3}R ダ{r['dist']} {r['n']}頭　逃げ{len(r['nige'])}頭"
              f"（候補{len(r['kouho'])}）　{mark}")
        if r["nige"]:
            print("      逃げ： " + "／".join(f"{e.umaban}{e.horse_name}" for e in r["nige"]))
        if r["sharp"]:
            print("      休んでいない： " + "／".join(
                f"{e.umaban}{e.horse_name}({pl}{ds}・{g}日)" for e, g, pl, ds in r["sharp"]))

    if not args.check:
        return

    # ---- 答え合わせ
    print("\n■ 答え合わせ\n")
    print(f"{'R':>3}{'予測':>6}{'逃げ':>5}{'前半':>8}{'上3F':>7}{'勝ち馬4角':>10}{'単':>7}  判定")
    firsts = {}
    for r in rows:
        html = client.get(PERF.format(r=r["rid"]))
        res = P.parse_result_page(html, r["rid"])
        tan, fuku = payouts(html)
        if not fuku:
            continue
        a3, order = race_shape(html)
        w = next(x for x in res.rows if x.finish_pos == 1)
        t = sec(w.time)
        if not (a3 and t and order):
            continue
        pos = (order.index(w.umaban) + 1) / len(order) if w.umaban in order else None
        firsts.setdefault(r["dist"], []).append((r, t - a3, a3, pos, list(tan.values())[0]))

    for dist, v in sorted(firsts.items()):
        if len(v) < 2:
            continue
        med = st.median(x[1] for x in v)
        for r, first, a3, pos, tan1 in v:
            # 予測が当たった＝崩れ予想の日は前半が同距離の中央値より速く、勝ち馬が後ろ
            fast = first < med
            ok = (r["shape"] == "崩れ") == fast
            print(f"{r['rno']:>3}{r['shape']:>6}{len(r['nige']):>5}{first:>8.1f}"
                  f"{a3:>7.1f}{(pos if pos else 0):>10.2f}{tan1:>7}  "
                  + ("○" if ok else "×") + f"（同距離の中央値 {med:.1f}）")
    print("\n  『崩れ』と読んだレースの前半が、同じ距離の中で速い側なら○。")


if __name__ == "__main__":
    main()
