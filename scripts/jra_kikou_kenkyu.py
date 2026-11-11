"""研究: 気候適性(note むねひろ の「気候／寒・涼・暖」)は効くか。

    python3 scripts/jra_kikou_kenkyu.py

発走時の気温(data/jra/kion、発走 10:05+33分×(R−1) の1時間値)で 寒<10 / 涼10-20 / 暖20-25 / 暑25+。
時系列で1頭ずつ「それまでの」成績を貯める(先の情報は使わない):
  全体の3着内率 と 今日と同じ気候での3着内率(2走以上) を比べ、
  「今日の気候で、他の気候より走れている」馬が、全体の力から見込むより走るかを測る。
人気は予想に使わない。穴(6番人気以下)で効くかを見る評価にだけ使う。
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KION = ROOT / "data" / "jra" / "kion"
_K: dict = {}


def temp_at(place, date, rno):
    if place not in _K:
        p = KION / f"{place}.json"
        _K[place] = json.load(open(p)) if p.exists() else {}
    mins = 10 * 60 + 5 + 33 * (rno - 1)
    return _K[place].get(f"{date}T{round(mins / 60):02d}:00")


def kikou(t):
    return None if t is None else ("寒" if t < 10 else "涼" if t < 20 else "暖" if t < 25 else "暑")


def main():
    raw = [json.loads(l) for l in open(ROOT / "data/jra/races.jsonl")]
    raw = [d for d in raw if d.get("surface") in ("芝", "ダ")]
    raw.sort(key=lambda d: (d["date"], d["race_id"]))
    H = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))   # horse -> class -> [runs, top3]
    out = collections.defaultdict(lambda: [0, 0.0, 0, 0, 0.0, 0])   # bin -> n, expected, top3 / 穴だけ
    cnt = collections.Counter()
    for d in raw:
        k = kikou(temp_at(d["place"], d["date"], int(d["race_id"][-2:])))
        cnt[k] += 1
        for r in d["result"]:
            h = H[r["horse_id"]]
            tot = [sum(v[0] for v in h.values()), sum(v[1] for v in h.values())]
            if k and tot[0] >= 4 and h[k][0] >= 2 and tot[0] - h[k][0] >= 2:
                rate_k = h[k][1] / h[k][0]
                rate_o = (tot[1] - h[k][1]) / (tot[0] - h[k][0])
                exp = (tot[1] + 1) / (tot[0] + 3)            # 全体の力から見込む3着内率
                g = rate_k - rate_o
                b = "今日の気候で ≥+0.30" if g >= 0.30 else "+0.10〜0.30" if g >= 0.10 else \
                    "±0.10" if g > -0.10 else "−0.10〜−0.30" if g > -0.30 else "≤−0.30(苦手)"
                hit = 1 if r["finish_pos"] <= 3 else 0
                o = out[b]
                o[0] += 1; o[1] += exp; o[2] += hit
                if (r.get("popularity") or 0) >= 6:
                    o[3] += 1; o[4] += exp; o[5] += hit
        for r in d["result"]:
            if k:
                H[r["horse_id"]][k][0] += 1
                H[r["horse_id"]][k][1] += 1 if r["finish_pos"] <= 3 else 0
    print("気候の鞍数", dict(cnt))
    print("気候の得手不得手        頭数   見込み 実際 (差)    | 6番人気以下: 頭数 見込み 実際 (差)")
    for b in ("今日の気候で ≥+0.30", "+0.10〜0.30", "±0.10", "−0.10〜−0.30", "≤−0.30(苦手)"):
        n, e, t, n2, e2, t2 = out[b]
        if n:
            print(f"  {b:16s} {n:6d}  {e/n:.3f} {t/n:.3f} ({(t-e)/n:+.3f})  | {n2:6d} {e2/max(1,n2):.3f} {t2/max(1,n2):.3f} ({(t2-e2)/max(1,n2):+.3f})")


if __name__ == "__main__":
    main()
