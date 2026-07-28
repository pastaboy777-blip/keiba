#!/usr/bin/env python3
"""レースの中身（ラップ・着順・上がり）だけでレースレベルを指数化する。

ユーザー発案（2026-07-28）:「レースをラップと馬や着順・上りから指数化できない？」

**なぜこちらが必要か**: 先に作った「メンバーの格」版（`race_grade.json`）は
出走馬の**過去実績**を使うので、その馬たちの履歴がキャッシュに無いと測れない。
実際 2026-07-28 川崎11R 3着の ③クラウニングカップ（11番人気）は、前走が
**船橋1500の1着**という骨っぽい内容だったのに、船橋のそのレースが未収録で
**格が測れなかった**（＝低評価ではなく測定不能）。

こちらは**そのレースの結果ページ1枚**だけで完結するので、
船橋でも中央でも、キャッシュがあれば必ず値が出る。

指数の中身（すべて「そのレース自身」から取れるもの）:
    time   … 勝ちタイム(s/F) が勝ち馬par からどれだけ速いか
    agari  … 上位3頭の平均上がり3F が その場・距離の平均からどれだけ速いか
    dense  … 1着〜5着のタイム差の小ささ（詰まっているほど骨っぽい）
それぞれ場×距離ごとに標準化して足す。

出力: {"YYYY-MM-DD|場|距離": {"power": float, "time": .., "agari": .., "dense": ..}}

    python3 scripts/build_race_power.py
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import defaultdict
from statistics import median, pstdev

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import rakuten as rk        # noqa: E402

CACHE = "data/cache/rakuten"
OUT = "data/race_power.json"
MIN_PER_GROUP = 20          # 場×距離でこの本数未満なら標準化できないので捨てる


def collect() -> list[dict]:
    rows = []
    for pf in sorted(glob.glob(os.path.join(
            CACHE, "race_performance_list_RACEID_*.html"))):
        rid = pf.rsplit("_", 1)[-1].removesuffix(".html")
        cf = os.path.join(CACHE, f"race_card_list_RACEID_{rid}.html")
        if not os.path.exists(cf):
            continue
        try:
            hd = rk.parse_card(open(cf, encoding="utf-8").read())["header"]
            res = rk.parse_result(open(pf, encoding="utf-8").read())
        except Exception:                          # noqa: BLE001
            continue
        place, dist = hd.get("place"), hd.get("distance")
        if not place or not dist or len(res) < 5:
            continue
        ts = [r["time_sec"] for r in res if r.get("time_sec")]
        ag = [r["agari"] for r in res[:3] if r.get("agari")]
        if len(ts) < 5 or not ag:
            continue
        f = dist / 200.0
        rows.append(dict(
            key=f"{rid[0:4]}-{rid[4:6]}-{rid[6:8]}|{place}|{dist}",
            grp=f"{place}|{dist}",
            sf=ts[0] / f,                      # 勝ちタイム s/F（小さいほど速い）
            ag=sum(ag) / len(ag),              # 上位3頭の平均上がり（小さいほど速い）
            gap=ts[min(4, len(ts) - 1)] - ts[0],   # 1着〜5着のタイム差（小さいほど密）
        ))
    return rows


def _z(vals: list[float]) -> tuple[float, float]:
    m = median(vals)
    s = pstdev(vals) or 1.0
    return m, s


def build(rows: list[dict]) -> dict[str, dict]:
    by = defaultdict(list)
    for r in rows:
        by[r["grp"]].append(r)
    out = {}
    for grp, rs in by.items():
        if len(rs) < MIN_PER_GROUP:
            continue
        msf, ssf = _z([r["sf"] for r in rs])
        mag, sag = _z([r["ag"] for r in rs])
        mgp, sgp = _z([r["gap"] for r in rs])
        for r in rs:
            # いずれも「速い/密」ほど正になるよう符号を反転
            t = (msf - r["sf"]) / ssf
            a = (mag - r["ag"]) / sag
            d = (mgp - r["gap"]) / sgp
            out[r["key"]] = {
                "power": round(t + a + d, 3),
                "time": round(t, 3), "agari": round(a, 3), "dense": round(d, 3),
            }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    rows = collect()
    table = build(rows)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(table, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        f.write("\n")
    pl = defaultdict(int)
    for k in table:
        pl[k.split("|")[1]] += 1
    print(f"{len(table)}レース → {args.out}")
    print("  " + "  ".join(f"{k}{v}" for k, v in sorted(pl.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    main()
