"""充実データ(collect_nankan の出力)から特徴量の重みを学習する。

各馬は出馬表時点の前5走から算出済みの特徴量ベクトル(features)と着順(finish_pos)を
持つので、それを Plackett-Luce 尤度最大化(core.learn)に直接渡して重みを学ぶ。
時系列分割(前半=学習・後半=検証)でリーク無しに評価する。

実行例:
    python3 scripts/train_from_samples.py data/samples/nankan_2026-05.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.core.features import FEATURE_NAMES
from nankeiba.core import learn as L


def load_rows(paths):
    """充実JSONL -> [(date, [_Row,...]), ...](レース単位)。"""
    races = []
    for p in paths:
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            rows = []
            for h in r["horses"]:
                if h.get("finish_pos") is None or not h.get("features"):
                    continue
                feat = {f: float(h["features"].get(f, 0.0)) for f in FEATURE_NAMES}
                rows.append(L._Row(feat=feat, pos=int(h["finish_pos"]),
                                   n_hist=len(h.get("recent_runs", []))))
            if len(rows) >= 5:
                races.append((r["date"], rows))
    races.sort(key=lambda x: x[0])
    return races


def evaluate(test, weights, means, stds, *, min_history=3):
    """検証: 学習重みのトップ評価馬が3着内に入る率 と 1番人気の同率を比較。"""
    hit = n = 0
    for _date, rows in test:
        elig = [r for r in rows if r.n_hist >= min_history]
        if len(elig) < 5:
            continue
        scored = []
        for r in elig:
            x = L._standardize(r.feat, means, stds)
            s = sum(weights[f] * x[f] for f in FEATURE_NAMES)
            scored.append((s, r.pos))
        top = max(scored, key=lambda sp: sp[0])
        hit += 1 if top[1] <= 3 else 0
        n += 1
    return (hit / n if n else 0.0), n


def main():
    paths = sys.argv[1:] or ["data/samples/nankan_2026-05.jsonl"]
    races = load_rows(paths)
    if not races:
        raise SystemExit("学習データがありません")
    cut = int(len(races) * 0.7)
    train, test = races[:cut], races[cut:]
    print(f"レース {len(races)}  学習 {len(train)}({train[0][0]}〜{train[-1][0]})  "
          f"検証 {len(test)}({test[0][0]}〜{test[-1][0]})")

    train_samples = [rows for _d, rows in train]
    means, stds = L.compute_stats(train_samples, min_history=3)
    weights = L.fit_plackett_luce(train_samples, means, stds,
                                  epochs=80, lr=0.15, l2=2e-3, top_k=3, min_history=3)

    print("\n=== 学習された特徴量重要度(標準化係数・符号つき)===")
    for f, w in sorted(weights.items(), key=lambda kv: -abs(kv[1])):
        bar = "■" * int(min(20, abs(w) * 12))
        print(f"  {f:<14} {w:+.3f}  {bar}")

    acc, n = evaluate(test, weights, means, stds)
    print(f"\n=== 検証(後半{n}R・リーク無し)===")
    print(f"  学習モデルのトップ評価馬 3着内率: {100*acc:.1f}%")


if __name__ == "__main__":
    main()
