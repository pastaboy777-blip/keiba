"""① 予想層の強化: 関係者成績(騎手・調教師)を実データから導出して特徴量を作り直し、
重みを再学習して、素の充実データ版と精度比較する。

充実データには各馬の前5走(recent_runs)・騎手・調教師・着順が入っているので、
学習区間だけから 騎手/調教師の3着内率(ConnStats)を推定し(リーク防止)、
core.features.horse_features を計算し直す。これで死んでいた `trainer` 特徴量が活き、
`jockey_power`/`jockey_change` も場当たり(出馬表内)でなく通算成績で評価できる。

実行例:
    python3 scripts/train_recompute.py data/samples/nankan_2026-05.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.core import interval as iv
from nankeiba.core import learn as L
from nankeiba.core.features import FEATURE_NAMES, RaceContext, ConnStats, horse_features


def load_races(paths):
    races = []
    for p in paths:
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            races.append(r)
    races.sort(key=lambda r: r["date"])
    return races


def runrecords(h):
    out = []
    for pr in h.get("recent_runs", []):
        if not pr.get("date") or pr.get("finish_pos") is None or not pr.get("field_size"):
            continue
        out.append(iv.RunRecord(
            date=pr["date"], place=pr.get("place") or "", distance=pr.get("distance") or 0,
            field_size=pr["field_size"], finish_pos=pr["finish_pos"],
            jockey=pr.get("jockey"), popularity=pr.get("popularity"),
            baba=pr.get("baba"), corner_pos=list(pr.get("corner") or []),
        ))
    return out


def derive_conn(races, key, *, pseudo=15.0):
    """学習区間のレースから 関係者→3着内率 を推定(全体平均へ縮約)。"""
    starts, hits, ts, th = {}, {}, 0, 0
    for r in races:
        for h in r["horses"]:
            name = h.get(key)
            fp = h.get("finish_pos")
            if not name or fp is None:
                continue
            hit = 1 if fp <= 3 else 0
            starts[name] = starts.get(name, 0) + 1
            hits[name] = hits.get(name, 0) + hit
            ts += 1; th += hit
    prior = th / ts if ts else 0.25
    rates = {n: (hits[n] + pseudo * prior) / (starts[n] + pseudo) for n in starts}
    return ConnStats(rates=rates, default=prior)


def build_samples(races, jockeys, trainers):
    samples = []
    for r in races:
        order = {um: 0 for um in []}
        rows = []
        for h in r["horses"]:
            if h.get("finish_pos") is None:
                continue
            ctx = RaceContext(date=r["date"], place=r["place"], distance=r["distance"],
                              field_size=r["field_size"], jockey=h.get("jockey"),
                              trainer=h.get("trainer"))
            feat = horse_features(runrecords(h), ctx, jockeys=jockeys, trainers=trainers)
            rows.append(L._Row(feat=feat, pos=int(h["finish_pos"]),
                               n_hist=len(h.get("recent_runs", []))))
        if len(rows) >= 5:
            samples.append(rows)
    return samples


def evaluate(samples, weights, means, stds, *, min_history=3):
    hit = n = 0
    for rows in samples:
        elig = [r for r in rows if r.n_hist >= min_history]
        if len(elig) < 5:
            continue
        best = max(elig, key=lambda r: sum(
            weights[f] * ((r.feat[f] - means[f]) / stds[f]) for f in FEATURE_NAMES))
        hit += 1 if best.pos <= 3 else 0
        n += 1
    return (hit / n if n else 0.0), n


def main():
    paths = sys.argv[1:] or ["data/samples/nankan_2026-05.jsonl"]
    races = load_races(paths)
    cut = int(len(races) * 0.7)
    train, test = races[:cut], races[cut:]
    jockeys = derive_conn(train, "jockey")
    trainers = derive_conn(train, "trainer")
    print(f"レース {len(races)} 学習 {len(train)} 検証 {len(test)}  "
          f"騎手{len(jockeys.rates)}人 調教師{len(trainers.rates)}人 推定")

    tr = build_samples(train, jockeys, trainers)
    te = build_samples(test, jockeys, trainers)
    means, stds = L.compute_stats(tr, min_history=3)
    weights = L.fit_plackett_luce(tr, means, stds, epochs=80, lr=0.15, l2=2e-3,
                                  top_k=3, min_history=3)
    print("\n=== 再学習した重要度(関係者成績を導出して再計算)===")
    for f, w in sorted(weights.items(), key=lambda kv: -abs(kv[1])):
        print(f"  {f:<14} {w:+.3f}  {'■'*int(min(20,abs(w)*12))}")
    acc, n = evaluate(te, weights, means, stds)
    print(f"\n=== 検証(後半{n}R)トップ評価馬の3着内率: {100*acc:.1f}% "
          f"(従来57.5% / 1番人気71.1% と比較)")


if __name__ == "__main__":
    main()
