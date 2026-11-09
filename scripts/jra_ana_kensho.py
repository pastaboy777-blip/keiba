"""隊列・展開から「穴」を取るための集計(人気は予想に使わず、穴の定義と回収率の計算にだけ使う)。

    python3 scripts/jra_ana_kensho.py --data data/jra/races.jsonl

  1. コース(場×芝ダ)別: 隊列予想の前1/3の3着内率と、前1/3の穴(7番人気以下)の成績
  2. 隊列予想の前1/3の穴のうち、どんな条件の馬が来ているか(距離変更・芝ダ替わり・枠・前走位置・場替わり)
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.core import dataset as ds, tenkai as tk  # noqa: E402
from nankeiba.core.backtest import race_contexts, record_result  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/jra/races.jsonl")
    ap.add_argument("--ana", type=int, default=7, help="何番人気以下を穴とするか")
    a = ap.parse_args()
    raw = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    raw = [d for d in raw if d.get("surface") in ("芝", "ダ")]
    raw.sort(key=lambda d: (d["date"], d["race_id"]))

    h: dict = {}
    rows = []
    for d in raw:
        r = ds.race_from_dict(d)
        c = race_contexts(r, h)
        pasts = {e.num(): p for e, p, _ in c}
        fc = tk.forecast(pasts, place=r.place, distance=r.distance, surface=r.surface)
        known = sum(1 for s in fc.styles.values() if s.early is not None) / max(1, len(fc.styles))
        if known >= 0.7 and len(fc.order) >= 8:
            n = len(fc.order)
            res = {x["umaban"]: x for x in d["result"]}
            for i, u in enumerate(fc.order):
                x = res.get(u)
                if not x or not x.get("popularity"):
                    continue
                past = pasts[u]
                last = past[0] if past else None
                rows.append({
                    "course": f"{r.place}{r.surface}", "third": "前" if i < n / 3 else ("中" if i < 2 * n / 3 else "後"),
                    "top3": x["finish_pos"] <= 3, "win": x["finish_pos"] == 1,
                    "ana": x["popularity"] >= a.ana, "odds": x.get("win_odds") or 0,
                    "dist": ("延長" if last and r.distance > last.distance else
                             "短縮" if last and r.distance < last.distance else "同距離") if last else "-",
                    "surf": ("替わり" if last and last.surface and last.surface != r.surface else "同じ") if last else "-",
                    "gate": "内枠(前1/3)" if (x.get("umaban") or 0) <= n / 3 else ("外枠(後1/3)" if (x.get("umaban") or 0) > 2 * n / 3 else "中枠"),
                    "lastpos": ("前走4角 前" if last and last.corner_pos and (last.corner_pos[-1] - 1) / max(1, last.field_size - 1) < 0.33
                                else "前走4角 後ろ") if last and last.corner_pos else "-",
                    "place": ("場替わり" if last and last.place != r.place else "同じ場") if last else "-",
                })
        record_result(r, h)

    def line(g):
        t = sum(x["top3"] for x in g) / len(g) if g else 0
        roi = sum(x["odds"] for x in g if x["win"]) / len(g) if g else 0
        return f"3着内 {t:5.1%}  単勝回収率 {roi:6.1%}  (n={len(g)})"

    print(f"対象 {len(rows)} 頭(隊列予想が出せた鞍)  穴 = {a.ana}番人気以下\n")
    print("== 1. コース別: 隊列予想 前1/3 の成績(全体 / 穴) ==")
    by = collections.defaultdict(list)
    for x in rows:
        by[x["course"]].append(x)
    for k, g in sorted(by.items(), key=lambda kv: -len(kv[1])):
        f = [x for x in g if x["third"] == "前"]
        b = [x for x in g if x["third"] == "後"]
        fa = [x for x in f if x["ana"]]
        if len(f) < 80:
            continue
        ft = sum(x["top3"] for x in f) / len(f)
        bt = sum(x["top3"] for x in b) / max(1, len(b))
        print(f"  {k:<6s} 前1/3 3着内 {ft:5.1%} / 後1/3 {bt:5.1%}  (差 {ft - bt:+.1%})   前1/3の穴: {line(fa)}")

    print("\n== 2. 隊列予想 前1/3 の穴: 条件別 ==")
    fa = [x for x in rows if x["third"] == "前" and x["ana"]]
    print(f"  全体: {line(fa)}")
    for key in ("dist", "surf", "gate", "lastpos", "place"):
        g = collections.defaultdict(list)
        for x in fa:
            g[x[key]].append(x)
        for v, gg in sorted(g.items()):
            if len(gg) >= 40:
                print(f"  {v:<12s} {line(gg)}")
        print()


if __name__ == "__main__":
    main()
