# -*- coding: utf-8 -*-
"""踏ん張り指数：上がりがかかった中でも3着内に残った実績を数える（399の裏返し）。

背景（2026-07-30 本人の読み）：
  砂が緩んで「走りやすい」と「踏ん張れない」が同時に来る日は、決め手ではなく劣化しにくさの勝負になる。
  7/29川崎12Rの2着⑤アマビリティは上がり41.4で"メンバー最速"＝誰も切れていない中で落ち幅が最小だっただけ。
  455kg・467kgのワンツーも「軽いから沈まない＝落ち幅が小さい」で説明がつく。

そこで見るべきは上がりの速さではなく、次の2つ。
  ① 踏ん張り実績 … 上がりがかかった(=遅い)のに3着内へ来た走りの回数。推測ゼロ・馬柱の事実だけ。
  ② 上がりのブレ幅 … 近走の上がり(川崎1400m相当に正規化)の最大−最小。小さいほど劣化しにくい。

比較のため場×距離帯の実測補正で全部「川崎1400m相当」に揃える（ana399 と同じ物差し）。

    python3 scripts/funbari.py --date 2026-07-30 --place 川崎 --from 1 --to 12
    python3 scripts/funbari.py --date 2026-07-30 --place 川崎 --slow 40.8   # 網をもっと"かかった"側に
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

import ana399 as A

REF = json.loads((Path(__file__).resolve().parents[1] / "data" / "samples"
                  / "top3_agari_ref.json").read_text())

CARD_URL = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{race_id}"


def leg(runs):
    """近走の4角位置から脚質を1語で。"""
    rs = [r for r in runs if r.corner and r.field_size]
    if not rs:
        return "?"
    v = statistics.median(r.corner[-1] / r.field_size for r in rs[:5])
    return "前" if v < 0.35 else ("中団" if v < 0.62 else "後方")


def weight_of(entry):
    if entry.horse_weight:
        return entry.horse_weight
    for r in (entry.recent_runs or []):
        if r.horse_weight:
            return r.horse_weight
    return None


def evaluate(entry, home, pa, ba, margin, n_recent):
    norms, funbari = [], []
    for r in (entry.recent_runs or []):
        b = A.band(r.distance)
        n = A.norm_agari(r.agari, r.place, b, home, pa, ba)
        if n is not None and len(norms) < n_recent:
            norms.append(n)
        # ★踏ん張り＝その場・その距離帯の「3着内の標準的な上がり」より遅いのに3着内。
        #   帯ごとに基準が違う(川崎900は38.0・川崎1400は40.6)ので実測の基準表で判定する。
        ref = REF.get(f"{r.place}|{b}") if b else None
        if (ref and r.agari and r.finish_pos and r.finish_pos <= 3
                and r.agari >= ref + margin):
            funbari.append(dict(date=r.date, place=r.place, baba=r.baba, agari=r.agari,
                                norm=n, ref=ref, gap=round(r.agari - ref, 2),
                                fin=r.finish_pos, pop=r.popularity))
    span = round(max(norms) - min(norms), 2) if len(norms) >= 3 else None
    deepest = max((f["gap"] for f in funbari), default=None)  # 基準からどれだけ遅くて残せたか
    return dict(
        n=len(funbari), funbari=funbari, deepest=deepest,
        span=span, n_norm=len(norms),
        weight=weight_of(entry), leg=leg(entry.recent_runs or []),
    )


def main():
    ap = argparse.ArgumentParser(description="踏ん張り指数")
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", default="川崎", choices=list(NANKAN_CODES))
    ap.add_argument("--from", dest="r_from", type=int, default=1)
    ap.add_argument("--to", dest="r_to", type=int, default=12)
    ap.add_argument("--margin", type=float, default=0.3,
                    help="場×距離帯の3着内中央値より何秒遅ければ『かかった』とみなすか")
    ap.add_argument("--recent", type=int, default=5, help="ブレ幅を測る近走数")
    args = ap.parse_args()

    pa, ba = A.load_adj()
    client = PoliteClient(use_cache=False)
    ymd = date.fromisoformat(args.date).strftime("%Y%m%d")
    races = dict(P.parse_race_links(
        client.get(CARD_URL.format(race_id=day_index_race_id(ymd, args.place))),
        date_yyyymmdd=ymd, jyo_code=NANKAN_CODES[args.place]))

    print(f"■ {args.date} {args.place}  踏ん張り指数"
          f"（その場×距離帯の3着内中央値より{args.margin}秒以上遅い上がりで3着内に来た回数）")
    print("  最深＝基準からどれだけ遅い上がりで3着内に残せたか。ブレ幅＝近5走の上がり(1400m相当)の最大−最小。\n")

    for r in range(args.r_from, args.r_to + 1):
        if r not in races:
            continue
        page = P.parse_card_page(client.get(CARD_URL.format(race_id=races[r])), races[r])
        ents = getattr(page, "entries", page)
        rows = [(evaluate(e, args.place, pa, ba, args.margin, args.recent), e) for e in ents]
        rows.sort(key=lambda x: (-x[0]["n"], x[0]["span"] if x[0]["span"] is not None else 99))
        print(f"=== {r}R ダ{page.distance} {len(ents)}頭")
        for ev, e in rows:
            um = f"{e.umaban:>2}" if e.umaban is not None else " ?"
            span = f"{ev['span']:.2f}" if ev["span"] is not None else "  - "
            deep = f"+{ev['deepest']:.2f}" if ev["deepest"] else "  -  "
            print(f"  {um} {e.horse_name:<12} 踏ん張り{ev['n']} 最深{deep} "
                  f"ブレ{span} {str(ev['weight'] or '-'):>4}kg {ev['leg']:<3}")
            for f in sorted(ev["funbari"], key=lambda x: -x["gap"])[:3]:
                print(f"        {f['date'][5:]}{f['place']}{f['baba']} 上{f['agari']}"
                      f"(基準{f['ref']}/+{f['gap']}) {f['fin']}着{f['pop']}人")
        print()


if __name__ == "__main__":
    main()
