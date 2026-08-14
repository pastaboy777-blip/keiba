# -*- coding: utf-8 -*-
"""オッズ未開放の日に、各馬のエッジ集合＋399下地を一覧する（ズブ穴の相手選び用）。

ana_recall.edges_for（穴ファクター）と ana399.evaluate（勝ち圏の上がり再現力）を
同じ表に並べるだけの補助ツール。軸そのものは predict_nankan（実力軸）で決める。

    python3 scripts/zubu_edges.py --date 2026-07-29 --place 川崎 --from 1 --to 5
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from pace_day import parse_laps

import ana_recall as R
import ana399 as A

CARD_URL = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{race_id}"
PERF_URL = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{race_id}"

_DAY_CACHE: dict = {}


def prev_lap_index(client, ymd: str, place: str) -> dict:
    """前走日の全レースを走査し {馬名: 11秒台ラップ本数} を返す（『前走ハイレベル』判定用）。

    ラップは出馬表からは引けないため、前走当日の結果ページをまとめて読む。
    1日ぶん読めば同日の全馬に効くので、日単位でキャッシュする。
    """
    key = (ymd, place)
    if key in _DAY_CACHE:
        return _DAY_CACHE[key]
    idx: dict = {}
    try:
        html = client.get(CARD_URL.format(race_id=day_index_race_id(ymd, place)))
        races = dict(P.parse_race_links(html, date_yyyymmdd=ymd, jyo_code=ALL_CODES[place]))
    except Exception:
        races = {}
    for rid in races.values():
        try:
            rh = client.get(PERF_URL.format(race_id=rid))
        except Exception:
            continue
        laps = parse_laps(rh)
        if not laps:
            continue
        # 1本目が半端ハロン(50m等)だとスケールが壊れるので除外して数える
        eff = [t for t in laps if t >= 10.0] if laps[0] < 10.0 else laps
        c11 = sum(1 for t in eff if t < 12.0)
        for row in P.parse_result_page(rh, rid).rows:
            idx[row.horse_name] = c11
    _DAY_CACHE[key] = idx
    return idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", default="川崎")
    ap.add_argument("--from", dest="r_from", type=int, default=1)
    ap.add_argument("--to", dest="r_to", type=int, default=12)
    ap.add_argument("--thr", type=float, default=40.5)
    ap.add_argument("--no-prev-lap", action="store_true",
                    help="前走ハイレベル判定をやめる(前走日の走査を省いて高速化)")
    args = ap.parse_args()

    pa, ba = A.load_adj()
    client = PoliteClient(use_cache=False)
    ymd = date.fromisoformat(args.date).strftime("%Y%m%d")
    html = client.get(CARD_URL.format(race_id=day_index_race_id(ymd, args.place)))
    races = dict(P.parse_race_links(html, date_yyyymmdd=ymd,
                                    jyo_code=NANKAN_CODES[args.place]))
    today = date.fromisoformat(args.date)

    for r in range(args.r_from, args.r_to + 1):
        if r not in races:
            continue
        page = P.parse_card_page(client.get(CARD_URL.format(race_id=races[r])), races[r])
        ents = getattr(page, "entries", page)
        tb = A.band(page.distance)
        print(f"=== {r}R ダ{page.distance} {len(ents)}頭")
        rows = []
        for e in ents:
            c11 = None
            if not args.no_prev_lap:
                pr0 = e.recent_runs[0] if e.recent_runs else None
                if pr0 and pr0.date and pr0.place in ALL_CODES:
                    c11 = prev_lap_index(client, pr0.date.replace("-", ""),
                                         pr0.place).get(e.horse_name)
            tags, cw = R.edges_for(e, page.distance, today=today, prev_c11=c11)
            ev = A.evaluate(e, tb, args.place, pa, ba, args.thr, False)
            rows.append((len(tags), ev["score"], e, tags, ev, cw))
        for n, sc, e, tags, ev, bw in sorted(rows, key=lambda x: (-x[0], -x[1])):
            um = f"{e.umaban:>2}" if e.umaban is not None else " ?"
            print(f"  {um} {e.horse_name:<12} エッジ{n} 399={sc:4.1f} "
                  f"本物{ev['n_real']} 体重{bw or '-'} | {'・'.join(sorted(tags))}")
        print()


if __name__ == "__main__":
    main()
