# -*- coding: utf-8 -*-
"""南関：日ごとの馬場差を実測し、走破タイムを『完タイム差』に直す。

考え方はトラックマンの時計比較表と同じ:

    完タイム差 ＝ タイム差 ＋ 馬場差（距離で按分） ＋ 補正値

  タイム差 … 勝ちタイム − その条件(場・距離・クラス)の標準
  馬場差   … その日1日を通した速さのズレ。1つの数字で持ち、距離に比例して効かせる
  補正値   … 展開など個別事情。ここでは扱わない（0とする）

なぜ必要か（2026-08-01 の失敗）:
  馬場を「良・稍・重・不」の発表で扱っていた。川崎7か月で測ると勝ち馬の上がりは
  良39.34／稍39.46／重39.78／不39.14 と 0.64秒しか動かず、しかも不良がいちばん速かった。
  発表の馬場は、その日の速さを表していない。
  日ごとに実測した1つの数字でなければ、時計は日をまたいで比較できない。

  馬場差が分かると副産物がある。「後方から上がり最速で負けた馬」を評価するとき、
  その上がりが本当に速かったのか、その日が全体的に速かっただけなのかを分離できる。

    python3 scripts/nankan_babasa.py --place 船橋 --from 2026-05-01 --to 2026-07-04
    python3 scripts/nankan_babasa.py --place 船橋 --from 2026-05-01 --to 2026-07-04 --races 2026-06-05
"""
from __future__ import annotations

import argparse
import re
import statistics as st
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping.race_id import NANKAN_CODES
from nankeiba.scraping import parser as P

from nankan_zubu_backtest import CARD, PERF, race_days

REF = 1400          # 馬場差を表示する基準距離


def sec(t):
    m = re.match(r"(\d+):(\d+)\.(\d)", t or "")
    return int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 10 if m else None


def grade(cls):
    """クラス表記を粗い級に落とす。Ｃ３五→C3、２歳二→2歳、３歳(七)→3歳。"""
    if not cls:
        return "?"
    c = cls.translate(str.maketrans("ＡＢＣ１２３", "ABC123"))
    if "歳" in c and not re.search(r"[ABC]", c):
        return re.sub(r".*?(\d)歳.*", r"\1歳", c)[:2] or "?"
    m = re.search(r"([ABC])\s*(\d)?", c)
    return (m.group(1) + (m.group(2) or "")) if m else "?"


def main():
    ap = argparse.ArgumentParser(description="南関の日ごと馬場差と完タイム差")
    ap.add_argument("--place", default="船橋", choices=list(NANKAN_CODES))
    ap.add_argument("--from", dest="d_from", required=True)
    ap.add_argument("--to", dest="d_to", required=True)
    ap.add_argument("--races", help="この日の各レースの完タイム差を明細で出す")
    args = ap.parse_args()

    client = PoliteClient(use_cache=True)
    days = race_days(client, args.place,
                     date.fromisoformat(args.d_from), date.fromisoformat(args.d_to))

    rec = []
    for d, rs in days:
        for rno, rid in sorted(rs.items()):
            try:
                html = client.get(PERF.format(r=rid))
                res = P.parse_result_page(html, rid)
                cls = P.parse_race_class(client.get(CARD.format(r=rid)))
            except Exception:
                continue
            w = next((r for r in res.rows if r.finish_pos == 1), None)
            t = sec(w.time) if w else None
            if t is None or not res.distance:
                continue
            rec.append(dict(d=d, rno=rno, dist=res.distance, g=grade(cls),
                            baba=res.baba, t=t, name=w.horse_name, pop=w.popularity))
        print(f"\r  収集 {d}", end="", flush=True)
    print("\r" + " " * 30 + "\r", end="")
    if not rec:
        raise SystemExit("データなし")

    # 標準タイム：場・距離・級ごとの中央値。同じ条件が3本未満なら距離だけで代用する。
    by_cond = defaultdict(list)
    by_dist = defaultdict(list)
    for r in rec:
        by_cond[(r["dist"], r["g"])].append(r["t"])
        by_dist[r["dist"]].append(r["t"])
    std = {k: st.median(v) for k, v in by_cond.items() if len(v) >= 3}
    std_d = {k: st.median(v) for k, v in by_dist.items()}

    for r in rec:
        base = std.get((r["dist"], r["g"]), std_d.get(r["dist"]))
        r["diff"] = round(r["t"] - base, 2) if base else None

    # 馬場差：その日のタイム差を1000mあたりに直した中央値。距離をまたいでも足並みが揃う。
    byday = defaultdict(list)
    for r in rec:
        if r["diff"] is not None:
            byday[r["d"]].append(r["diff"] / (r["dist"] / 1000))
    variant = {d: st.median(v) for d, v in byday.items()}

    for r in rec:
        if r["diff"] is not None:
            r["kan"] = round(r["diff"] - variant[r["d"]] * (r["dist"] / 1000), 2)

    if args.races:
        target = date.fromisoformat(args.races)
        v = variant.get(target)
        if v is None:
            raise SystemExit(f"{args.races} は対象外")
        print(f"\n■ {args.place} {target}　馬場差 {v * REF / 1000:+.1f}秒"
              f"（{REF}m換算／マイナスは速い馬場）\n")
        print(f"{'R':>3}{'距離':>6}{'級':>5}{'馬場':>4}{'勝ち馬':<16}"
              f"{'走破':>8}{'タイム差':>9}{'完タイム差':>11}")
        for r in sorted([x for x in rec if x["d"] == target], key=lambda x: x["rno"]):
            if r["diff"] is None:
                continue
            print(f"{r['rno']:>3}{r['dist']:>6}{r['g']:>5}{r['baba'] or '?':>4}"
                  f"{r['name']:<16}{r['t']:>8.1f}{r['diff']:>+9.2f}{r['kan']:>+11.2f}")
        return

    print(f"\n■ {args.place} {args.d_from}〜{args.d_to}　日ごとの馬場差"
          f"（{REF}m換算・マイナスが速い馬場）\n")
    print(f"{'日付':<12}{'発表馬場':<10}{'R':>3}{'馬場差':>9}{'完タイム差の幅':>16}")
    for d in sorted(variant):
        day = [r for r in rec if r["d"] == d and r["diff"] is not None]
        bb = "/".join(sorted({r["baba"] or "?" for r in day}))
        k = [r["kan"] for r in day]
        print(f"{str(d):<12}{bb:<10}{len(day):>3}{variant[d] * REF / 1000:>+9.2f}"
              f"{min(k):>+8.2f}〜{max(k):>+6.2f}")
    vs = [v * REF / 1000 for v in variant.values()]
    print(f"\n  馬場差の幅 {min(vs):+.2f}〜{max(vs):+.2f}秒（{max(vs)-min(vs):.2f}秒）")
    print("  ※標準タイムは同じ期間から作っているので、日数が少ないと自分自身に引きずられる。")


if __name__ == "__main__":
    main()
