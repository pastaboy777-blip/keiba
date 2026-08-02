# -*- coding: utf-8 -*-
"""『上がり最速で負けた馬』は次走で儲かるか。そして上がりとは何の数字か。

きっかけ（2026-08-02、本人の指摘「どんな時でも同じ上がりだね、遅めの」）:
  船橋ダ1200を109レース測ると、上がり3Fは前半600mより平均 +2.50秒 遅く、
  上がりのほうが速かったレースは109本中2本しかない。しかも前半が2.01秒動く間に
  上がりは0.06秒しか動かない（r = -0.03）。
  つまりレース間の時計差はほぼ全部が前半で、上がり3Fはレースの情報を持っていない。

  レースの上がりが定数なら、個別の馬の上がりは何を測っているのか。
  後ろにいた馬ほど、止まった馬を抜くぶん数字が良く出るだけではないのか。
  だとすれば「上がり最速だったのに負けた馬」を次走で買っても増えないはずである。
  これは巷でいちばん使われている買い材料であり、こちらの逆バイアス軸の土台でもある。

測るもの:
  ① 4角の位置と、そのレース内での上がり順位の関係
     後ろにいるほど上がり順位が良い、が強く出るなら上がりは位置取りの写しである。
  ② 上がり最速で4着以下だった馬を次走で買った回収率
     比較対象は「同じレースで4着以下だった馬を無差別に次走で買う」。
     控除率のぶん元から75%前後に沈むので、100%ではなく無差別との差で見る。

    python3 scripts/nankan_agari_roi.py --from 2026-03-01 --to 2026-06-30
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

from nankan_baba import race_shape
from nankan_gyaku import result_rows
from nankan_racelevel import VENUES
from nankan_zubu_backtest import PERF, race_days, payouts


def pearson(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs)
    sx, sy = st.pstdev(xs), st.pstdev(ys)
    return cov / (sx * sy) if sx and sy else 0.0


def line(name, bets):
    w = sum(1 for b in bets if b["tan"])
    p = sum(1 for b in bets if b["fuku"])
    se = lambda k: st.pstdev([b[k] for b in bets]) / len(bets) ** 0.5
    print(f"{name:<26}{len(bets):>6}{w / len(bets) * 100:>7.1f}%{p / len(bets) * 100:>8.1f}%"
          f"{sum(b['tan'] for b in bets) / len(bets):>9.1f}%±{se('tan'):<5.0f}"
          f"{sum(b['fuku'] for b in bets) / len(bets):>8.1f}%±{se('fuku'):<4.0f}")


def main():
    ap = argparse.ArgumentParser(description="上がり最速で負けた馬の次走回収率")
    ap.add_argument("--from", dest="d_from", required=True)
    ap.add_argument("--to", dest="d_to", required=True)
    ap.add_argument("--tail", type=int, default=60, help="次走を探す余分な日数")
    args = ap.parse_args()

    client = PoliteClient(use_cache=True)
    d0, d1 = date.fromisoformat(args.d_from), date.fromisoformat(args.d_to)

    races, timeline = {}, defaultdict(list)
    for place in VENUES:
        days = race_days(client, place, d0, d1 + timedelta(days=args.tail))
        for i, (d, rs) in enumerate(days, 1):
            for rno, rid in sorted(rs.items()):
                try:
                    html = client.get(PERF.format(r=rid))
                    res = P.parse_result_page(html, rid)
                    rows = result_rows(html)
                except Exception:
                    continue
                _a3, order = race_shape(html)
                if len(rows) < 6:
                    continue
                # レース内の上がり順位。欠測はランクを付けない（除外して数える）。
                ok = [r for r in rows if r["agari"]]
                for rank, r in enumerate(sorted(ok, key=lambda r: r["agari"]), 1):
                    r["arank"] = rank
                n = len(rows)
                for r in rows:
                    r["pos4"] = ((order.index(r["umaban"]) + 1) / n
                                 if order and r["umaban"] in order else None)
                races[rid] = dict(date=d, place=place, rno=rno, dist=res.distance,
                                  n=n, rows=rows, nag=len(ok))
                for r in rows:
                    timeline[r["horse_id"]].append((d, rid))
            print(f"\r{place} {i}/{len(days)}日", end="", flush=True)
        print()
    for h in timeline:
        timeline[h].sort()
    print(f"\n収集 {len(races)}レース")

    # ---- ① 4角の位置と上がり順位
    xs, ys = [], []
    for rid, r in races.items():
        if not (d0 <= r["date"] <= d1):
            continue
        for row in r["rows"]:
            if row["pos4"] is None or "arank" not in row:
                continue
            xs.append(row["pos4"])                       # 0=前、1=後ろ
            ys.append(row["arank"] / r["nag"])           # 0=上がり最速、1=最遅
    print(f"\n■ ① 4角の位置と、そのレース内の上がり順位　{len(xs)}頭ぶん")
    print(f"   相関 r = {pearson(xs, ys):+.3f}"
          "（マイナスが強いほど『後ろにいた馬ほど上がり順位が良い』）")
    band = defaultdict(list)
    for x, y in zip(xs, ys):
        band[min(int(x * 5), 4)].append(y)
    for k in sorted(band):
        lo, hi = k * 20, k * 20 + 20
        print(f"   4角 上位{lo:>3}〜{hi:>3}%  n={len(band[k]):>5}  "
              f"上がり順位の平均 {st.mean(band[k]) * 100:.1f}%")

    # ---- ② 上がり最速で負けた馬を次走で買う
    groups = {"上がり最速で4着以下": [], "上がり2〜3位で4着以下": [], "4着以下を無差別": []}
    for rid, r in races.items():
        if not (d0 <= r["date"] <= d1):
            continue
        for row in r["rows"]:
            if row["fin"] < 4 or "arank" not in row:
                continue
            nxt = next((x for x in timeline[row["horse_id"]] if x[0] > r["date"]), None)
            if nxt is None or nxt[1] not in races:
                continue
            nr = races[nxt[1]]
            me = next((x for x in nr["rows"] if x["horse_id"] == row["horse_id"]), None)
            if me is None:
                continue
            try:
                tan, fuku = payouts(client.get(PERF.format(r=nxt[1])))
            except Exception:
                continue
            if not fuku:
                continue
            bet = dict(tan=float(tan.get(me["umaban"], 0)),
                       fuku=float(fuku.get(me["umaban"], 0)), pop=me["pop"])
            groups["4着以下を無差別"].append(bet)
            if row["arank"] == 1:
                groups["上がり最速で4着以下"].append(bet)
            elif row["arank"] in (2, 3):
                groups["上がり2〜3位で4着以下"].append(bet)

    print(f"\n■ ② 次走の回収率（100円あたり）")
    print(f"{'区分':<26}{'点数':>6}{'勝率':>8}{'複勝率':>9}{'単回収':>10}{'':<6}{'複回収':>8}")
    for k in ("上がり最速で4着以下", "上がり2〜3位で4着以下", "4着以下を無差別"):
        if len(groups[k]) >= 50:
            line(k, groups[k])
        else:
            print(f"{k:<26}標本 {len(groups[k])} で足りない")

    fast = groups["上がり最速で4着以下"]
    base = groups["4着以下を無差別"]
    if len(fast) >= 50 and len(base) >= 50:
        d = sum(b["fuku"] for b in fast) / len(fast) - sum(b["fuku"] for b in base) / len(base)
        print(f"\n   複勝回収の差（最速 − 無差別）= {d:+.1f}ポイント")
        print("   誤差の幅を超えていなければ、上がり最速に買う価値はない。")


if __name__ == "__main__":
    main()
