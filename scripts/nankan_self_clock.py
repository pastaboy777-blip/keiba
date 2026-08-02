# -*- coding: utf-8 -*-
"""その日の出走馬が『自分の過去の時計』に対してどう走ったかを見る。

きっかけ（2026-08-02 船橋8R、本人の指摘）:
  マルヒロユートピアは 7/02 とまったく同じ 1:16.8 で走り、着順は 8着/10 から 3着/9 になった。
  3走前の良（5/05）は 1:16.4 で 8着/12 だったので、0.4秒遅い時計で着順は5つ上。
  同じ馬・同じ場・同じ距離・同じ斤量で、相手だけが落ちたことになる。

  これが1頭の例外なのか、開催全体で起きているのかを分ける。

  各馬について
      Δ時計 ＝ 今日の走破 − 同じ場・同じ距離での過去の中央値
      Δ着順 ＝ 今日の着順position − 過去の着順positionの中央値
  を出し、Δ時計がほぼゼロなのに Δ着順 がマイナス（＝着順が上がった）に寄るなら、
  相手が落ちている。全体の平均で見る。

  ★馬場が違うと時計は比べられない。良の日だけに絞った版も併せて出す。
    ダートは湿ると速いので、湿った日を混ぜると過去の中央値が速く出て、
    今日が実際より悪く見える。

    python3 scripts/nankan_self_clock.py --date 2026-08-02 --place 船橋
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

from nankan_babasa import sec
from nankan_zubu_backtest import CARD, PERF, payouts


def summary(name, v, key):
    if len(v) < 8:
        print(f"  {name:<22}n={len(v)} で足りない")
        return
    x = [r[key] for r in v]
    se = st.pstdev(x) / len(x) ** 0.5
    print(f"  {name:<22}n={len(v):>3}  平均 {st.mean(x):+6.2f}  誤差 ±{se:.2f}"
          f"  z={st.mean(x) / se if se else 0:+5.1f}")


def main():
    ap = argparse.ArgumentParser(description="出走馬が自分の過去の時計に対してどう走ったか")
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", default="船橋", choices=list(NANKAN_CODES))
    ap.add_argument("--min-past", type=int, default=2, help="過去の同条件走がこの数以上")
    args = ap.parse_args()

    d = date.fromisoformat(args.date)
    ymd = d.strftime("%Y%m%d")
    client = PoliteClient(use_cache=True)
    card = dict(P.parse_race_links(
        client.get(CARD.format(r=day_index_race_id(ymd, args.place))),
        date_yyyymmdd=ymd, jyo_code=NANKAN_CODES[args.place]))

    out = []
    for rno, rid in sorted(card.items()):
        try:
            html = client.get(PERF.format(r=rid))
            res = P.parse_result_page(html, rid)
            page = P.parse_card_page(client.get(CARD.format(r=rid)), rid)
        except Exception:
            continue
        if not payouts(html)[1] or not res.distance:
            continue
        ent = {e.horse_id: e for e in getattr(page, "entries", page)}
        n = len([r for r in res.rows if r.finish_pos])
        for r in res.rows:
            if not r.finish_pos or not r.time:
                continue
            t = sec(r.time)
            e = ent.get(r.horse_id)
            if t is None or e is None:
                continue
            past, past_good, ranks = [], [], []
            for pr in e.recent_runs or []:
                if (pr.place != args.place or pr.distance != res.distance
                        or not pr.time or not pr.finish_pos or not pr.field_size):
                    continue
                pt = sec(pr.time)
                if pt is None:
                    continue
                past.append(pt)
                ranks.append(pr.finish_pos / pr.field_size)
                if (pr.baba or "").startswith("良"):
                    past_good.append(pt)
            if len(past) < args.min_past:
                continue
            out.append(dict(rno=rno, name=r.horse_name, fin=r.finish_pos, n=n,
                            t=t, dtime=t - st.median(past),
                            dtime_good=(t - st.median(past_good)) if past_good else None,
                            drank=r.finish_pos / n - st.median(ranks),
                            pop=r.popularity))

    if not out:
        raise SystemExit("同条件の過去走が足りない。")
    print(f"\n■ {args.place} {args.date}　同じ場・同じ距離の過去走が"
          f"{args.min_past}回以上ある {len(out)}頭\n")
    print("Δ時計＝今日の走破 − 自分の過去の中央値（プラスが遅い）")
    print("Δ着順＝今日の着順position − 自分の過去の中央値（マイナスが着順を上げた）\n")
    summary("Δ時計（全馬場）", out, "dtime")
    g = [r for r in out if r["dtime_good"] is not None]
    if g:
        summary("Δ時計（過去は良のみ）", g, "dtime_good")
    summary("Δ着順", out, "drank")

    # 着順は相対なので、全体の平均は構造上ほぼ動かない。
    # 意味があるのは「自分比で時計が落ちなかった馬ほど着順を上げたか」のほう。
    xs = [r["dtime"] for r in out]
    ys = [r["drank"] for r in out]
    mx, my = st.mean(xs), st.mean(ys)
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / len(xs)
    sx, sy = st.pstdev(xs), st.pstdev(ys)
    print(f"\n  Δ時計とΔ着順の相関 r = {cov / (sx * sy) if sx and sy else 0:+.2f}"
          "（プラスなら『遅かった馬ほど着順を落とした』＝ふつうの話）")

    print("\n  ── 時計が横ばい（±0.5秒）だった馬だけ ──")
    flat = [r for r in out if abs(r["dtime"]) <= 0.5]
    summary("Δ着順", flat, "drank")

    print("\n  ── 着順を大きく上げた馬（Δ着順 −0.2以下） ──")
    up = sorted([r for r in out if r["drank"] <= -0.2], key=lambda r: r["drank"])
    for r in up[:15]:
        print(f"    {r['rno']:>2}R {r['name']:<15}{r['fin']:>2}着/{r['n']}頭 "
              f"{str(r['pop']):>2}人  Δ時計{r['dtime']:+.2f}  Δ着順{r['drank']:+.2f}")


if __name__ == "__main__":
    main()
