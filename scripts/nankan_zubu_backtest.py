# -*- coding: utf-8 -*-
"""南関ズブ穴（◎/○）の機械ルールを、期間まとめて単複均等買いで採点する。

なぜ書いたか（2026-08-01）:
  中央で「6日間で回収率88%」と喜んだ数字が、18日間に伸ばしたら72%まで落ちた。
  南関ズブ穴の 135.8% は3日・138頭、機械ルールの ◎153.7% は4日・46頭しかない。
  同じ罠に入っていないかを確かめないまま次を張るのは、ただの願望になる。
  そもそもその機械ルールがスクリプトとして残っていなかったので、まず再現可能にする。

ルール（前回の手集計と同じ並べ方）:
  対象   … 確定人気が pop_min 番人気以下（＝人気を被っていない馬）
  並べ方 … ① ana_recall のエッジ数 ② ana399 のスコア（勝ち圏の上がり再現力）
  ◎＝1位、○＝2位。それぞれ単勝100円・複勝100円の単複均等。

  ★人気は確定人気を使う。前日にはオッズが無いので、実運用では「6番人気以下になりそうな馬」を
    見込みで拾うことになる。ここで出る数字はその見込みが完璧だった場合の上限であり、
    実運用はこれより悪くなる。都合よく読まないこと。

    python3 scripts/nankan_zubu_backtest.py --place 川崎 --from 2026-05-01 --to 2026-07-31
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES
from nankeiba.scraping import parser as P

import statistics as st

import ana399 as A
import ana_recall as R

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"
_TAN = re.compile(r"単勝\s+(\d+)\s+([\d,]+)\s*円")
_FUKU = re.compile(r"複勝\s+((?:\d+\s+)+)((?:[\d,]+\s*円\s*)+)")


def payouts(html):
    """単勝・複勝の払戻を {馬番: 円} で返す。"""
    t = re.sub(r"\s+", " ", BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    tan, fuku = {}, {}
    if m := _TAN.search(t):
        tan[int(m.group(1))] = int(m.group(2).replace(",", ""))
    if m := _FUKU.search(t):
        nums = [int(x) for x in m.group(1).split()]
        yen = [int(x.replace(",", "")) for x in re.findall(r"([\d,]+)\s*円", m.group(2))]
        fuku = dict(zip(nums, yen))
    return tan, fuku


def race_days(client, place, d0, d1):
    """開催があった日だけを返す。"""
    out, d = [], d0
    while d <= d1:
        ymd = d.strftime("%Y%m%d")
        try:
            links = P.parse_race_links(client.get(CARD.format(r=day_index_race_id(ymd, place))),
                                       date_yyyymmdd=ymd, jyo_code=NANKAN_CODES[place])
            if links:
                out.append((d, dict(links)))
        except Exception:
            pass
        d += timedelta(days=1)
    return out


def main():
    ap = argparse.ArgumentParser(description="南関ズブ穴の機械ルール検証")
    ap.add_argument("--place", default="川崎", choices=list(NANKAN_CODES))
    ap.add_argument("--from", dest="d_from", required=True)
    ap.add_argument("--to", dest="d_to", required=True)
    ap.add_argument("--pop-min", type=int, default=6, help="この番人気以下だけを対象にする")
    ap.add_argument("--thr", type=float, default=40.5, help="ana399 の勝ち圏しきい値")
    ap.add_argument("--rule", default="edge", choices=["edge", "span"],
                    help="edge=エッジ数→399 / span=ブレ幅の小ささ→中心の速さ")
    ap.add_argument("--max-span", type=float, default=2.0,
                    help="span時：近5走の上がり(1400m相当)の最大−最小がこの値以下だけ候補にする")
    ap.add_argument("--out", help="1点ごとの明細を書き出す JSONL")
    args = ap.parse_args()

    pa, ba = A.load_adj()
    client = PoliteClient(use_cache=True)
    days = race_days(client, args.place,
                     date.fromisoformat(args.d_from), date.fromisoformat(args.d_to))
    print(f"■ {args.place} {args.d_from}〜{args.d_to}：開催 {len(days)}日\n")

    # mark -> [点数, 単的中, 複的中, 単払戻, 複払戻]
    acc = {"◎": [0, 0, 0, 0, 0], "○": [0, 0, 0, 0, 0]}
    base = [0, 0, 0, 0, 0]                 # 対象全頭を平等に買った場合＝並べ方の効果を測る土台
    by_pop, rows = {}, []
    for d, races in days:
        for rno, rid in sorted(races.items()):
            try:
                page = P.parse_card_page(client.get(CARD.format(r=rid)), rid)
                rhtml = client.get(PERF.format(r=rid))
                res = P.parse_result_page(rhtml, rid)
            except Exception:
                continue
            if not res.rows:
                continue
            tan, fuku = payouts(rhtml)
            if not fuku:
                continue                       # 未確定・払戻が読めない
            fin = {r.umaban: r for r in res.rows}
            tb = A.band(page.distance)
            cand = []
            for e in getattr(page, "entries", page):
                r_ = fin.get(e.umaban)
                if not r_ or not r_.popularity or r_.popularity < args.pop_min:
                    continue
                if args.rule == "edge":
                    tags, _cw = R.edges_for(e, page.distance, today=d)
                    ev = A.evaluate(e, tb, args.place, pa, ba, args.thr, False)
                    cand.append((len(tags), ev["score"], e, r_))
                else:
                    # ブレ幅＝近5走の上がりを「その場・1400m相当」に正規化した最大−最小。
                    # 小さい＝どんな馬場でも同じ脚を使える。ただしそれだけでは
                    # 「いつも同じくらい遅い馬」も拾ってしまうので、中心(中央値)の速さと2条件で見る。
                    norms = []
                    for pr in (e.recent_runs or []):
                        n = A.norm_agari(pr.agari, pr.place, A.band(pr.distance),
                                         args.place, pa, ba)
                        if n is not None and len(norms) < 5:
                            norms.append(n)
                    if len(norms) < 3:
                        continue
                    span = max(norms) - min(norms)
                    if span > args.max_span:
                        continue
                    # 1次キー：中心が速いほど上（符号を反転）。2次キー：ブレ幅が小さいほど上。
                    cand.append((-st.median(norms), -span, e, r_))
            # 並べ方に意味があるかは「対象全頭を平等に買った場合」と比べないと分からない。
            for _n, _sc, e, r_ in cand:
                base[0] += 1
                t0 = tan.get(e.umaban, 0) if r_.finish_pos == 1 else 0
                f0 = fuku.get(e.umaban, 0) if r_.finish_pos <= 3 else 0
                base[1] += 1 if t0 else 0
                base[2] += 1 if f0 else 0
                base[3] += t0
                base[4] += f0
            cand.sort(key=lambda x: (-x[0], -x[1]))
            for mark, item in zip("◎○", cand[:2]):
                _n, _sc, e, r_ = item
                a = acc[mark]
                a[0] += 1
                t = tan.get(e.umaban, 0) if r_.finish_pos == 1 else 0
                f = fuku.get(e.umaban, 0) if r_.finish_pos <= 3 else 0
                a[1] += 1 if t else 0
                a[2] += 1 if f else 0
                a[3] += t
                a[4] += f
                b = by_pop.setdefault(min(r_.popularity, 12), [0, 0, 0])
                b[0] += 1; b[1] += t; b[2] += f
                rows.append(dict(date=d.isoformat(), race=rno, mark=mark, umaban=e.umaban,
                                 name=e.horse_name, pop=r_.popularity, fin=r_.finish_pos,
                                 tan=t, fuku=f))
        print(f"\r{d} まで集計", end="", flush=True)
    print("\n")

    print(f"{'印':<4}{'点数':>6}{'勝率':>8}{'複勝率':>8}{'単回収':>9}{'複回収':>9}{'単複均等':>10}")
    tot = [0, 0, 0, 0, 0]
    for mark in "◎○":
        n, w, p, tp, fp = acc[mark]
        if not n:
            continue
        for i in range(5):
            tot[i] += acc[mark][i]
        print(f"{mark:<4}{n:>6}{w/n*100:>7.1f}%{p/n*100:>7.1f}%"
              f"{tp/(n*100)*100:>8.1f}%{fp/(n*100)*100:>8.1f}%{(tp+fp)/(n*200)*100:>9.1f}%")
    n, w, p, tp, fp = base
    if n:
        print(f"{'土台':<4}{n:>6}{w/n*100:>7.1f}%{p/n*100:>7.1f}%"
              f"{tp/(n*100)*100:>8.1f}%{fp/(n*100)*100:>8.1f}%{(tp+fp)/(n*200)*100:>9.1f}%"
              "  ← 対象全頭を平等に買った場合")
    n, w, p, tp, fp = tot
    if n:
        print(f"{'計':<4}{n:>6}{w/n*100:>7.1f}%{p/n*100:>7.1f}%"
              f"{tp/(n*100)*100:>8.1f}%{fp/(n*100)*100:>8.1f}%{(tp+fp)/(n*200)*100:>9.1f}%")
        print(f"\n  投資 {n*200:,}円 → 払戻 {tp+fp:,}円")

    print(f"\n■ 人気別（12番人気以上はまとめ）")
    print(f"  {'人気':>4}{'点数':>6}{'単回収':>9}{'複回収':>9}")
    for k in sorted(by_pop):
        n, t, f = by_pop[k]
        print(f"  {k:>4}{n:>6}{t/(n*100)*100:>8.1f}%{f/(n*100)*100:>8.1f}%")

    if args.out:
        Path(args.out).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows))
        print(f"\n明細 → {args.out}")


if __name__ == "__main__":
    main()
