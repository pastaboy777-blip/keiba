# -*- coding: utf-8 -*-
"""『前走から何かが変わった馬』は買えるか。

きっかけ（2026-08-02 船橋、本人の指摘「刺激がある馬が穴？」）:
  全110頭を「転入・乗り替わり・距離変更」の数で割ると、
      変化ゼロ 32頭 → 0勝・単0%
      変化1つ  35頭 → 4勝・単56.6%
      変化2つ  26頭 → 5勝・単154.6%
      変化3つ  17頭 → 3勝・単314.1%
  12勝すべてが変化のあった馬だった。

  理屈は立つ。市場は前走を見て値段を付けるので、何も変わっていない馬は前走どおりに
  評価され、変わった馬は前走が当てにならないぶん値段が付かない。

  ★ただし1日ぶんである。しかも「転入」だけを21,394走で測ったときは逆に出た
    （開催初日の転入馬は勝率5.8%で、その日の全馬9.5%を下回った）。
    単独で効かなかったものが、束ねると効くとは限らない。複数日で確かめる。

    python3 scripts/nankan_change_roi.py --place 船橋 --from 2026-03-01 --to 2026-07-31
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
from nankeiba.scraping.race_id import NANKAN_CODES
from nankeiba.scraping import parser as P

from nankan_zubu_backtest import CARD, PERF, race_days, payouts


def jn(x):
    """減量記号を落とす。付けたまま比べると同じ騎手が乗替に見える。"""
    return (x or "").lstrip("▲☆△★◇◎○ ").strip()


def line(name, v):
    if len(v) < 30:
        print(f"{name:<20}n={len(v)} で足りない")
        return
    w = sum(1 for x in v if x["fin"] == 1)
    p = sum(1 for x in v if x["fuku"])
    se = lambda k: st.pstdev([x[k] for x in v]) / len(v) ** 0.5
    print(f"{name:<20}{len(v):>6}{w / len(v) * 100:>7.1f}%{p / len(v) * 100:>8.1f}%"
          f"{sum(x['tan'] for x in v) / len(v):>9.1f}%±{se('tan'):<5.0f}"
          f"{sum(x['fuku'] for x in v) / len(v):>8.1f}%±{se('fuku'):<4.0f}")


def main():
    ap = argparse.ArgumentParser(description="前走からの変化の数と回収率")
    ap.add_argument("--place", default="船橋", choices=list(NANKAN_CODES))
    ap.add_argument("--from", dest="d_from", default="2026-03-01")
    ap.add_argument("--to", dest="d_to", default="2026-07-31")
    args = ap.parse_args()

    client = PoliteClient(use_cache=True)
    days = race_days(client, args.place,
                     date.fromisoformat(args.d_from), date.fromisoformat(args.d_to))
    runs = []
    for i, (d, rs) in enumerate(days, 1):
        for rno, rid in sorted(rs.items()):
            try:
                html = client.get(PERF.format(r=rid))
                res = P.parse_result_page(html, rid)
                tan, fuku = payouts(html)
                card = P.parse_card_page(client.get(CARD.format(r=rid)), rid)
            except Exception:
                continue
            if not fuku or not res.distance:
                continue
            ent = {e.horse_id: e for e in getattr(card, "entries", card)}
            for r in res.rows:
                if not r.finish_pos or r.umaban is None:
                    continue
                e = ent.get(r.horse_id)
                pr = (e.recent_runs or [None])[0] if e else None
                if pr is None:
                    continue
                tr = bool(pr.place and pr.place != args.place)
                jk = bool(pr.jockey and e.jockey and jn(pr.jockey) != jn(e.jockey))
                dd = bool(pr.distance and pr.distance != res.distance)
                runs.append(dict(fin=r.finish_pos, tr=tr, jk=jk, dd=dd, n=tr + jk + dd,
                                 tan=float(tan.get(r.umaban, 0)),
                                 fuku=float(fuku.get(r.umaban, 0))))
        print(f"\r  {i}/{len(days)}日 {len(runs)}走", end="", flush=True)
    print("\r" + " " * 30 + "\r", end="")

    print(f"\n■ {args.place} {args.d_from}〜{args.d_to}　延べ{len(runs):,}走\n")
    print(f"{'区分':<20}{'頭数':>6}{'勝率':>7}{'複勝率':>8}{'単回収':>10}{'':<6}{'複回収':>8}")
    line("全馬", runs)
    for k in range(4):
        line(f"変化{k}つ", [x for x in runs if x["n"] == k])
    print("── 種類別 ──")
    line("転入", [x for x in runs if x["tr"]])
    line("乗り替わり", [x for x in runs if x["jk"]])
    line("距離が変わる", [x for x in runs if x["dd"]])
    print("\n  控除率のぶん、無差別に買えば75%前後に沈む。見るのは『全馬』の行との差。")


if __name__ == "__main__":
    main()
