"""研究: 風(向き・強さ)でペースと時計のずれを説明できるか。直線の向きは決め打ちせず、場×芝ダごとに学習する。

    python3 scripts/jra_wind_kenkyu.py --data data/jra/races.jsonl

風 = 発走時刻(R番号から見積もり 10:05 + 33分×(R−1))の1時間ごとの値を data/jra/wind/<場>.json から。
風ベクトル(吹いていく向き) u=東向き, v=北向き [m/s]。場×芝ダごとに 目的のずれ ~ u + v を前半で学習し、後半で確かめる。
目的: 前後半差(ペース)、前半3F、後半3F、勝ちタイム(いずれも条件モデルとのずれ)。
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import jra_learn as J  # noqa: E402
from jra_pace_model import PaceModel  # noqa: E402
from jra_time_model import TimeModel, target  # noqa: E402
from nankeiba.scraping.db_race import pace_of  # noqa: E402

WIND = Path(__file__).resolve().parents[1] / "data" / "jra" / "wind"
_W: dict = {}


def wind_at(place: str, date: str, rno: int):
    if place not in _W:
        p = WIND / f"{place}.json"
        _W[place] = json.load(open(p)) if p.exists() else {}
    mins = 10 * 60 + 5 + 33 * (rno - 1)
    hh = round(mins / 60)
    w = _W[place].get(f"{date}T{hh:02d}:00")
    if not w:
        return None
    sp, dr = w
    rad = math.radians(dr)
    return (-sp * math.sin(rad), -sp * math.cos(rad), sp)   # 吹いていく向き(東, 北), 強さ


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/jra/races.jsonl")
    a = ap.parse_args()
    raw = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    raw = [d for d in raw if d.get("surface") in ("芝", "ダ") and pace_of(d.get("lap") or [], d["distance"])
           and d["result"][0].get("time")]
    raw.sort(key=lambda d: (d["date"], d["race_id"]))
    cut = raw[len(raw) // 2]["date"]
    tr = [d for d in raw if d["date"] < cut]
    pm = PaceModel().fit(tr)
    tms = {k: TimeModel(k).fit(tr) for k in ("front3", "last3", "time")}
    v = sorted(pace_of(d["lap"], d["distance"])["diff"] for d in tr)
    q = (v[len(v) // 3], v[2 * len(v) // 3])
    cl = lambda x: "H" if x < q[0] else ("S" if x > q[1] else "M")  # noqa: E731
    R = []
    for d in raw:
        w = wind_at(d["place"], d["date"], int(d["race_id"][-2:]))
        if not w:
            continue
        pc = pace_of(d["lap"], d["distance"])
        R.append({"d": d, "w": w, "key": (d["place"], d["surface"]),
                  "diff": (pc["diff"], pm.predict(d)),
                  "front3": (pc["front3"], tms["front3"].predict(d)), "last3": (pc["last3"], tms["last3"].predict(d)),
                  "time": (d["result"][0]["time"], tms["time"].predict(d))})
    print(f"風が取れた鞍 {len(R)}(境 {cut})。風の強さの平均 {st.mean(r['w'][2] for r in R):.1f}m/s")
    coef = {}
    for tgt, lab in (("diff", "前後半差(ペース)"), ("front3", "前半3F"), ("last3", "後半3F"), ("time", "勝ちタイム")):
        e0, e1, h0, h1, n = [], [], [], [], 0
        for key in sorted({r["key"] for r in R}):
            g_tr = [r for r in R if r["key"] == key and r["d"]["date"] < cut]
            g_te = [r for r in R if r["key"] == key and r["d"]["date"] >= cut]
            if len(g_tr) < 80 or not g_te:
                continue
            w = J.ols([[1.0, r["w"][0], r["w"][1]] for r in g_tr], [r[tgt][0] - r[tgt][1] for r in g_tr], l2=5.0)
            coef.setdefault(tgt, {})["|".join(key)] = w
            for r in g_te:
                add = w[0] + w[1] * r["w"][0] + w[2] * r["w"][1]
                e0.append(abs(r[tgt][0] - r[tgt][1]))
                e1.append(abs(r[tgt][0] - r[tgt][1] - add))
                if tgt == "diff":
                    h0.append(cl(r[tgt][1]) == cl(r[tgt][0]))
                    h1.append(cl(r[tgt][1] + add) == cl(r[tgt][0]))
            n += len(g_te)
        line = f"  {lab:<14s} 検証 {n}鞍  平均誤差 {st.mean(e0):.3f} → 風あり {st.mean(e1):.3f}秒"
        if h0:
            line += f"   3区分の的中 {st.mean(h0):.1%} → {st.mean(h1):.1%}"
        print(line)
    # 強い風の日だけ
    strong = [r for r in R if r["w"][2] >= 5 and r["d"]["date"] >= cut]
    print(f"\n  風が強い(5m/s以上)鞍だけ: 検証 {len(strong)}鞍")
    for tgt in ("diff", "last3"):
        e0 = [abs(r[tgt][0] - r[tgt][1]) for r in strong if "|".join(r["key"]) in coef.get(tgt, {})]
        e1 = []
        for r in strong:
            w = coef.get(tgt, {}).get("|".join(r["key"]))
            if w:
                e1.append(abs(r[tgt][0] - r[tgt][1] - (w[0] + w[1] * r["w"][0] + w[2] * r["w"][1])))
        if e0:
            print(f"    {tgt:<6s} 平均誤差 {st.mean(e0):.3f} → {st.mean(e1):.3f}秒")
    json.dump(coef, open(Path(__file__).resolve().parents[1] / "models" / "wind_model.json", "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
