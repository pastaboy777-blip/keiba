#!/usr/bin/env python3
"""激走★の学習版：南関の過去レースから学習し、アウトオブサンプル検証する。

  1) 楽天から南関(大井/川崎/船橋/浦和)の過去レースを収集(カード＋結果=2fetch/race)
  2) レース前特徴量 + ラベル(複勝圏=3着以内)で SparkModel を学習
  3) 学習に使っていない後半期間で、激走(予測上位)の複勝率を人気/無作為と比較

    python3 scripts/train_spark.py --start 20260720 --days 60 --max-races 300

※個人利用・節度ある取得。カードは1fetchで全馬履歴入りなので効率的。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import rakuten as rk                       # noqa: E402
from nankeiba.core.hindex import SpeedIndexModel                   # noqa: E402
from nankeiba.core.spark_learn import SparkModel, extract_features  # noqa: E402

NANKAN = ["大井", "川崎", "船橋", "浦和"]


def nankan_meetings(client: rk.KeibaRakuten, ymd: str) -> dict[str, str]:
    """その日の南関の {競馬場: 開催id(...00)} を返す。"""
    import html as _html
    try:
        h = client.get(f"/race_card/list/RACEID/{ymd}0000000000")
    except Exception:
        return {}
    out = {}
    for m in re.finditer(r'race_card/list/RACEID/(\d{18})"[^>]*>(.*?)</a>', h, re.S):
        t = _html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).replace("　", "").strip()
        if t in NANKAN:
            out[t] = m.group(1)
    return out


def collect(client, start: str, days: int, max_races: int, use_cache=True):
    rows, ys, meta = [], [], []
    d0 = date(int(start[:4]), int(start[4:6]), int(start[6:]))
    got = 0
    for off in range(days):
        d = d0 - timedelta(days=off)
        ymd = f"{d:%Y%m%d}"
        dd = f"{d:%Y-%m-%d}"
        meets = nankan_meetings(client, ymd)
        for place, mid in meets.items():
            for rno in range(1, 13):
                rid = mid[:-2] + f"{rno:02d}"
                try:
                    card = rk.parse_card(client.get(f"/race_card/list/RACEID/{rid}", use_cache=use_cache))
                    res = rk.parse_result(client.get(f"/race_performance/list/RACEID/{rid}", use_cache=use_cache))
                except Exception:
                    continue
                E = card["entries"]
                if not E or not res:
                    continue
                dist = int(card["header"]["distance"] or 0)
                pre = {e["umaban"]: [r for r in e["history"] if r.date < dd] for e in E}
                model = SpeedIndexModel.fit([r for rs in pre.values() for r in rs])
                fin = {r["umaban"]: r["finish"] for r in res}
                pop = {r["umaban"]: r.get("popularity") for r in res}
                for um, runs in pre.items():
                    if um not in fin:
                        continue
                    feat = extract_features(runs, model, place, dist, dd)
                    rows.append(feat)
                    ys.append(1 if fin[um] <= 3 else 0)
                    meta.append({"date": dd, "race": rid, "um": um,
                                 "fin": fin[um], "pop": pop.get(um)})
                got += 1
                if got >= max_races:
                    print(f"  収集 {got}R (target {max_races})", flush=True)
                    return rows, ys, meta
        print(f"  {ymd}: 累計{got}R", flush=True)
    return rows, ys, meta


def evaluate(model, rows, ys, meta, k=3):
    """レースごとに激走(予測上位k)を選び、複勝率を集計。"""
    by_race = {}
    for r, y, m in zip(rows, ys, meta):
        by_race.setdefault(m["race"], []).append((model.prob(r), y, m))
    spark_hit = spark_n = 0
    pop_hit = pop_n = 0
    ana_hit = ana_n = 0        # 激走のうち6番人気以下
    for race, items in by_race.items():
        items.sort(key=lambda t: t[0], reverse=True)
        for p, y, m in items[:k]:
            spark_n += 1; spark_hit += y
            if m["pop"] and m["pop"] >= 6:
                ana_n += 1; ana_hit += y
        pops = sorted([it for it in items if it[2]["pop"]], key=lambda t: t[2]["pop"])
        for p, y, m in pops[:k]:
            pop_n += 1; pop_hit += y
    return dict(spark=(spark_hit, spark_n), pop=(pop_hit, pop_n), ana=(ana_hit, ana_n))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="収集開始日(新→古) YYYYMMDD")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--max-races", type=int, default=300)
    ap.add_argument("--out", default="data/spark_model.json")
    args = ap.parse_args()

    client = rk.KeibaRakuten()
    print("[1/3] 収集中…")
    rows, ys, meta = collect(client, args.start, args.days, args.max_races)
    n = len(rows)
    print(f"      {n} 頭ぶん / {len(set(m['race'] for m in meta))} レース / 複勝率(全体) {sum(ys)/max(1,n):.1%}")
    if n < 200:
        print("データ不足。--days を増やしてください。"); return

    # 時系列split(古い側で学習・新しい側で検証)
    order = sorted(range(n), key=lambda i: meta[i]["date"])
    cut = int(n * 0.65)
    tr = order[:cut]; te = order[cut:]
    print(f"[2/3] 学習 {len(tr)} / 検証 {len(te)}")
    model = SparkModel.train([rows[i] for i in tr], [ys[i] for i in tr])
    for name, w in model.importances()[:8]:
        print(f"      {name:<12}{w:+.2f}")

    print("[3/3] アウトオブサンプル検証(激走=予測上位3頭/レース)")
    ev = evaluate(model, [rows[i] for i in te], [ys[i] for i in te], [meta[i] for i in te])
    sh, sn = ev["spark"]; ph, pn = ev["pop"]; ah, an = ev["ana"]
    print(f"  激走(上位3)複勝率 : {sh}/{sn} = {sh/max(1,sn):.1%}")
    print(f"  人気(上位3)複勝率 : {ph}/{pn} = {ph/max(1,pn):.1%} (baseline)")
    print(f"  激走のうち6番人気以下 複勝率: {ah}/{an} = {ah/max(1,an):.1%}  ← 穴の的中力")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(model.to_json())
    print(f"モデル保存: {args.out}")


if __name__ == "__main__":
    main()
