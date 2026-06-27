"""33ラップ理論(鈴木ショータ)の計算ツール。中央(netkeiba)のラップから算出。

33ラップ = (残り1200-600mの3F) − (残り600m-ゴールの3F) = ラップ[-6:-3]の和 − ラップ[-3:]の和。
  + = 瞬発力勝負(中盤緩み上がり速い) / − = 持久力勝負(早め加速・持続)。
1200m(6F)は前半3F − 後半3F。コース別の平均33ラップでコースの質を、各レースの33ラップで
その日の質を把握する(馬の適性マッチに使う)。

実行例:
    python3 scripts/lap33.py --date 2026-06-21 --place 東京            # その日のレース別
    python3 scripts/lap33.py --date 2026-06-21 --place 東京 --course   # コース平均(芝/ダ×距離)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nankeiba.scraping import netkeiba as N


def lap33(laps):
    """ラップ列(全ハロン)から33ラップ値を返す。6F未満は None。"""
    if len(laps) < 6:
        return None
    return round(sum(laps[-6:-3]) - sum(laps[-3:]), 2)


def surface_dist(html):
    """結果ページから 芝/ダ と距離を取り出す。"""
    m = re.search(r"(芝|ダ)\s*(?:右|左|直)?\s*(\d{3,4})m", html)
    if m:
        return m.group(1), int(m.group(2))
    m = re.search(r"(芝|ダート)(\d{3,4})", html)
    return (m.group(1)[0], int(m.group(2))) if m else (None, None)


def label(v):
    if v is None:
        return "—"
    if v >= 1.0:
        return "瞬発力(+)"
    if v <= -1.0:
        return "持久力(−)"
    return "中間"


def get_result_html(client, rid):
    """ラップが取れる結果ページを返す。過去走(古い)はdbにラップ有り→db優先。"""
    for url in (N.RESULT_URL, N.RESULT_LIVE_URL):
        try:
            h = client.get(url.format(race_id=rid))
            if N.parse_laps(h):
                return h
        except Exception:  # noqa: BLE001
            continue
    return None


def main():
    ap = argparse.ArgumentParser(description="33ラップ計算(中央)")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD(複数はカンマ区切り)")
    ap.add_argument("--place", default=None)
    ap.add_argument("--course", action="store_true", help="コース別平均33ラップを集計")
    ap.add_argument("--min-n", type=int, default=1, help="コース表で最低R数(既定1)")
    args = ap.parse_args()

    client = N.make_client(use_cache=True)
    dates = [d.strip() for d in args.date.split(",") if d.strip()]
    rids = []
    for d in dates:
        for r in N.race_ids_for_date(client, d.replace("-", "")):
            if not args.place or N.place_of(r) == args.place:
                rids.append(r)

    rows = []
    for rid in rids:
        h = get_result_html(client, rid)
        if not h:
            continue
        laps = N.parse_laps(h)
        sf, dist = surface_dist(h)
        v = lap33(laps)
        rows.append((N.place_of(rid), int(rid[10:12]), sf, dist, v))

    if args.course:
        from collections import defaultdict
        agg = defaultdict(list)
        for pl, rno, sf, dist, v in rows:
            if v is not None and sf and dist:
                agg[(pl, sf, dist)].append(v)
        print(f"\n=== コース別 平均33ラップ ({len(dates)}日集計) ===")
        print(f"{'コース':<16}{'平均33ラップ':>12}{'質':>10}{'R数':>5}")
        for key in sorted(agg):
            vs = agg[key]
            if len(vs) < args.min_n:
                continue
            m = sum(vs) / len(vs)
            print(f"{key[0]+key[1]+str(key[2]):<16}{m:>+12.2f}{label(m):>10}{len(vs):>5}")
    else:
        print(f"\n=== {args.date} {args.place or '中央'} レース別 33ラップ ===")
        print(f"{'場':>4}{'R':>3}{'コース':>8}{'33ラップ':>9}{'質':>10}")
        for pl, rno, sf, dist, v in rows:
            c = f"{sf or '?'}{dist or '?'}"
            print(f"{pl:>4}{rno:>3}{c:>8}{(f'{v:+.2f}' if v is not None else '—'):>9}{label(v):>10}")


if __name__ == "__main__":
    main()
