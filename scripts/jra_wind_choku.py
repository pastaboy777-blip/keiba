"""風を「直線の向き」に投影して、向かい風/追い風・横風に分ける。向きは JRA の「先週の風傾向」から決める。

    python3 scripts/jra_wind_choku.py

直線の向き(馬が走っていく方位, 度)。JRA公式「先週の風傾向」(10/31-11/1, 11/7-8 の2週ぶん)から逆算:
  京都(右回り・スタンドは走る馬の左) … 北東=向かい、西南西〜西=追い、北北西=横(スタンド→内ラチ) → 65°
  東京(左回り・スタンドは右) … 北東=追い、南西=向かい、北北東=横(スタンド→内ラチ) → 290°
  福島(右回り・スタンドは左) … 西〜北西=横(スタンド→内ラチ) → 25°(左がスタンド=北西側になる向き)
head > 0 が向かい風 [m/s]、cross は横風の強さ。
"""

from __future__ import annotations

import argparse
import json
import math
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jra_pace_model import PaceModel  # noqa: E402
from jra_time_model import TimeModel  # noqa: E402
from jra_wind_kenkyu import wind_at  # noqa: E402
from nankeiba.scraping.db_race import pace_of  # noqa: E402

AXIS = {"京都": 65, "東京": 290, "福島": 25}


def head_cross(place, date, rno):
    w = wind_at(place, date, rno)
    if not w or place not in AXIS:
        return None
    u, v, sp = w                        # 吹いていく向き(東, 北)
    b = math.radians(AXIS[place])
    run = (math.sin(b), math.cos(b))    # 走る向き(東, 北)
    along = u * run[0] + v * run[1]     # +なら馬と同じ向きに吹く=追い風
    cross = abs(u * run[1] - v * run[0])
    head = -along
    return head, cross, sp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/jra/races.jsonl")
    ap.add_argument("--week", default="2026-10-31,2026-11-01,2026-11-07,2026-11-08")
    a = ap.parse_args()
    week = a.week.split(",")
    raw = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    raw = [d for d in raw if d.get("surface") in ("芝", "ダ") and pace_of(d.get("lap") or [], d["distance"])
           and d["result"][0].get("time")]
    tr = [d for d in raw if d["date"] < min(week)]
    pm = PaceModel().fit(tr)
    tl = TimeModel("last3").fit(tr)
    tf = TimeModel("front3").fit(tr)

    def res(d):
        pc = pace_of(d["lap"], d["distance"])
        return pc["front3"] - tf.predict(d), pc["last3"] - tl.predict(d), pc["diff"] - pm.predict(d)

    # 3年: 向かい風の強さで後半3Fのずれがどう変わるか(場×芝ダ)
    print("== 3年(先週より前): 向かい風成分と、前半3F・後半3Fのずれ(条件モデル比) ==")
    for place in ("京都", "東京", "福島"):
        for sf in ("芝", "ダ"):
            rows = []
            for d in tr:
                if d["place"] != place or d["surface"] != sf:
                    continue
                hc = head_cross(place, d["date"], int(d["race_id"][-2:]))
                if hc:
                    rows.append((hc[0],) + res(d))
            if len(rows) < 50:
                continue
            for lab, sel in (("追い風3m+", lambda h: h <= -3), ("ほぼ無風", lambda h: abs(h) < 1.5),
                             ("向かい3m+", lambda h: h >= 3)):
                g = [r for r in rows if sel(r[0])]
                if len(g) >= 10:
                    print(f"  {place}{sf} {lab:7s} n={len(g):4d}  前半3F {st.mean(r[1] for r in g):+.2f}  "
                          f"後半3F {st.mean(r[2] for r in g):+.2f}  前後差 {st.mean(r[3] for r in g):+.2f}")
    print("\n== 先週 1鞍ずつ (ずれ = 実際 − 条件モデル。後半3Fが+なら上がりがかかった) ==")
    for d in sorted((d for d in raw if d["date"] in week and d["place"] in AXIS), key=lambda d: d["race_id"]):
        hc = head_cross(d["place"], d["date"], int(d["race_id"][-2:]))
        f, l, df = res(d)
        h = "  ---" if not hc or hc[0] is None else f"{hc[0]:+5.1f}"
        c = f"{hc[1]:4.1f}" if hc else " ---"
        print(f"  {d['date'][5:]} {d['place']}{int(d['race_id'][-2:]):2d}R {d['surface']}{d['distance']:4d} {d.get('baba')} "
              f"向かい{h} 横{c}  前半{f:+5.2f} 後半{l:+5.2f} 前後差{df:+5.2f}")


if __name__ == "__main__":
    main()
