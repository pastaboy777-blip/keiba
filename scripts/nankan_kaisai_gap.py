# -*- coding: utf-8 -*-
"""開催が空くと、初日は本当に『ズブい』のか。

きっかけ（2026-08-02、本人の指摘）:
  この日の船橋は第5回第1日で、前開催の最終日 7/04 から29日空いていた。
  1200m戦の前半600mが平均37.69秒で、5〜6月の109鞍平均36.75秒より0.94秒遅い。
  上がりは38.97で平常（39.24）とほぼ同じ。つまり前半だけが遅い日だった。

  「間隔が空いて全体がズブくなり、誰も前半から動けない」なら、
  開催初日はどの開催でも同じことが起きているはずである。
  逆に今日だけの現象なら、それはただのメンバー構成である。

測るもの（開催初日 vs 2日目以降）:
  ① 前半600m（1200m戦のみ。距離を固定しないと比べられない）
  ② 上がり3F   … ここが動かなければ「前半だけ遅い」が確かめられる
  ③ 勝ち馬の4角position … 前が残ったかどうか
  ④ 走破タイムの標準からのズレ … 単に時計が遅い日なのかを分ける

  ★開催初日は「間隔が空いた日」であると同時に「馬場が新しい日」でもある。
    この2つはこの粒度では分けられない。上がりが動かず前半だけ遅いなら
    馬場より脚の問題に寄るが、断定はしない。

    python3 scripts/nankan_kaisai_gap.py --from 2026-01-01 --to 2026-08-02
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

from nankan_baba import race_shape
from nankan_babasa import grade, par_key, sec
from nankan_racelevel import VENUES
from nankan_zubu_backtest import CARD, PERF, race_days


def show(name, v):
    if len(v) < 5:
        return f"{name}  n={len(v)} で足りない"
    return (f"{name}  n={len(v):>4}  平均 {st.mean(v):6.2f}"
            f"  標準偏差 {st.pstdev(v):5.2f}")


def welch(a, b):
    """2群の平均差と、その誤差。標本数が違うので分散は別々に持つ。"""
    if len(a) < 5 or len(b) < 5:
        return None, None
    se = (st.pvariance(a) / len(a) + st.pvariance(b) / len(b)) ** 0.5
    return st.mean(a) - st.mean(b), se


def main():
    ap = argparse.ArgumentParser(description="開催間隔と初日のペース")
    ap.add_argument("--from", dest="d_from", default="2026-01-01")
    ap.add_argument("--to", dest="d_to", default="2026-08-02")
    ap.add_argument("--gap", type=int, default=10,
                    help="前の開催日からこの日数以上空いたら『開催初日』とみなす")
    args = ap.parse_args()

    client = PoliteClient(use_cache=True)
    d0, d1 = date.fromisoformat(args.d_from), date.fromisoformat(args.d_to)

    rows = []
    for place in VENUES:
        days = race_days(client, place, d0, d1)
        prev = None
        for i, (d, rs) in enumerate(days, 1):
            gap = (d - prev).days if prev else None
            prev = d
            for rno, rid in sorted(rs.items()):
                try:
                    html = client.get(PERF.format(r=rid))
                    res = P.parse_result_page(html, rid)
                    cls = P.parse_race_class(client.get(CARD.format(r=rid)))
                except Exception:
                    continue
                w = next((r for r in res.rows if r.finish_pos == 1), None)
                t = sec(w.time) if w else None
                a3, order = race_shape(html)
                if not (t and a3 and res.distance and gap):
                    continue
                n = len(order) if order else len(res.rows)
                pos = ((order.index(w.umaban) + 1) / n
                       if order and w.umaban in order else None)
                rows.append(dict(place=place, d=d, gap=gap, dist=res.distance,
                                 g=grade(cls), t=t, a3=a3, first=t - a3, pos=pos,
                                 opening=gap >= args.gap))
            print(f"\r{place} {i}/{len(days)}日", end="", flush=True)
        print()

    # 標準タイム。開催初日ばかりで作ると基準そのものが動くので、場ごとに全日から取る。
    byc = defaultdict(list)
    for r in rows:
        byc[(r["place"], par_key(r["dist"], r["g"]))].append(r["t"])
    std = {k: st.median(v) for k, v in byc.items() if len(v) >= 3}
    for r in rows:
        b = std.get((r["place"], par_key(r["dist"], r["g"])))
        r["diff"] = (r["t"] - b) / (r["dist"] / 1000) if b else None

    op = [r for r in rows if r["opening"]]
    reg = [r for r in rows if not r["opening"]]
    ndays_o = len({(r["place"], r["d"]) for r in op})
    ndays_r = len({(r["place"], r["d"]) for r in reg})
    print(f"\n収集 {len(rows)}レース／開催初日 {ndays_o}日 {len(op)}鞍"
          f"／2日目以降 {ndays_r}日 {len(reg)}鞍（境目 {args.gap}日）\n")

    for label, key, pick in (
            ("① 前半600m（1200m戦）", "first", lambda r: r["dist"] == 1200),
            ("② 上がり3F（1200m戦）", "a3", lambda r: r["dist"] == 1200),
            ("③ 勝ち馬の4角position", "pos", lambda r: r["pos"] is not None),
            ("④ 標準からのズレ（秒/1000m）", "diff", lambda r: r["diff"] is not None)):
        a = [r[key] for r in op if pick(r) and r[key] is not None]
        b = [r[key] for r in reg if pick(r) and r[key] is not None]
        print(f"■ {label}")
        print("   " + show("開催初日  ", a))
        print("   " + show("2日目以降", b))
        dm, se = welch(a, b)
        if dm is not None:
            z = dm / se if se else 0
            print(f"   差 {dm:+.3f}（誤差 ±{se:.3f}、z = {z:+.1f}）"
                  + ("　← 誤差を超えている" if abs(z) >= 2 else "　← 誤差の内側"))
        print()

    # 間隔の刻みでも見る。長く空くほど効くなら、階段状に出るはず。
    print("■ 間隔の刻みごと（1200m戦の前半600m）")
    band = defaultdict(list)
    for r in rows:
        if r["dist"] != 1200:
            continue
        k = ("1〜3日" if r["gap"] <= 3 else "4〜9日" if r["gap"] <= 9 else
             "10〜20日" if r["gap"] <= 20 else "21日以上")
        band[k].append(r["first"])
    for k in ("1〜3日", "4〜9日", "10〜20日", "21日以上"):
        if band[k]:
            print("   " + show(f"{k:<8}", band[k]))


if __name__ == "__main__":
    main()
