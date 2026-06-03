"""EVバックテスト: 充実データ(完全な前5走特徴量)× 結果データ(三連複/三連単オッズ)。

充実JSONL(collect_nankan)= 各馬の特徴量と着順、結果JSONL(collect_data)= オッズと着順
を race_id で結合する。前半で重みを学習し(時系列・リーク無し)、後半で
「モデル確率 × オッズ > 閾値」の買い目だけ購入して回収率(ROI)を測る。

実行例:
    python3 scripts/ev_backtest.py \
        --enriched data/samples/nankan_2026-05.jsonl \
        --results  data/samples/results_2026-05.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.core.features import FEATURE_NAMES
from nankeiba.core import learn as L
from nankeiba.core import probability as pb
from nankeiba.core import betting as bt


def _combo(key, ordered):
    t = tuple(int(x) for x in key.split("-"))
    return t if ordered else tuple(sorted(t))


def load(enriched_paths, results_paths):
    enr = {}
    for p in enriched_paths:
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            horses = {}
            for h in r["horses"]:
                if h.get("features"):
                    horses[h["umaban"]] = ({f: float(h["features"].get(f, 0.0))
                                            for f in FEATURE_NAMES},
                                           len(h.get("recent_runs", [])))
            enr[r["race_id"]] = {"date": r["date"], "horses": horses}
    res = {}
    for p in results_paths:
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            res[r["race_id"]] = {
                "date": r["date"],
                "order": [int(x) for x in r["result_order"]] if r.get("result_order")
                else [x["umaban"] for x in sorted(r["result"], key=lambda z: z["finish_pos"])],
                "trio": {_combo(k, False): float(v) for k, v in r.get("trio_odds", {}).items()},
                "trifecta": {_combo(k, True): float(v) for k, v in r.get("trifecta_odds", {}).items()},
            }
    ids = sorted(set(enr) & set(res), key=lambda i: enr[i]["date"])
    return enr, res, ids


def main():
    ap = argparse.ArgumentParser(description="EVバックテスト(充実×オッズ)")
    ap.add_argument("--enriched", nargs="+", default=["data/samples/nankan_2026-05.jsonl"])
    ap.add_argument("--results", nargs="+", default=["data/samples/results_2026-05.jsonl"])
    ap.add_argument("--bet-type", choices=["trio", "trifecta"], default="trio")
    ap.add_argument("--min-history", type=int, default=3)
    args = ap.parse_args()

    enr, res, ids = load(args.enriched, args.results)
    cut = int(len(ids) * 0.7)
    train_ids, test_ids = ids[:cut], ids[cut:]
    print(f"結合レース {len(ids)}  学習 {len(train_ids)}  検証 {len(test_ids)}"
          f"({enr[test_ids[0]]['date']}〜{enr[test_ids[-1]]['date']})  馬券={args.bet_type}")

    # --- 学習(前半・充実特徴量から重み)---
    train_samples = []
    for i in train_ids:
        order = {um: k + 1 for k, um in enumerate(res[i]["order"])}
        rows = []
        for um, (feat, nh) in enr[i]["horses"].items():
            if um in order:
                rows.append(L._Row(feat=feat, pos=order[um], n_hist=nh))
        if len(rows) >= 5:
            train_samples.append(rows)
    means, stds = L.compute_stats(train_samples, min_history=args.min_history)
    weights = L.fit_plackett_luce(train_samples, means, stds, epochs=80, lr=0.15,
                                  l2=2e-3, top_k=3, min_history=args.min_history)

    def strengths_for(race_id):
        ran = set(res[race_id]["order"])          # 実出走馬(取消除外)
        sc = {}
        for um, (feat, nh) in enr[race_id]["horses"].items():
            if um is None or um not in ran:
                continue
            if nh < args.min_history:
                return None
            x = L._standardize(feat, means, stds)
            sc[um] = sum(weights[f] * x[f] for f in FEATURE_NAMES)
        return pb.strengths_from_scores(sc) if len(sc) >= 3 else None

    # --- 検証(後半・EV買い)---
    for thr in (1.1, 1.3, 1.5, 2.0):
        spent = returned = nbets = nhits = nbr = 0
        for i in test_ids:
            st = strengths_for(i)
            if st is None:
                continue
            if args.bet_type == "trio":
                probs = pb.trio_probabilities(st)
                odds = res[i]["trio"]
                key = tuple(sorted(res[i]["order"][:3]))
            else:
                probs = pb.trifecta_probabilities(st)
                odds = res[i]["trifecta"]
                key = tuple(res[i]["order"][:3])
            bets = bt.select_ev_bets(probs, odds, ev_threshold=thr,
                                     stake_per_bet=100.0, max_bets=8)
            if not bets:
                continue
            s, r = bt.settle(bets, key)
            spent += s; returned += r; nbets += len(bets); nbr += 1
            nhits += sum(1 for b in bets if b.combo == key)
        roi = returned / spent if spent else 0
        print(f"  EV閾値{thr}: {nbr}R購入 {nbets}点 的中{nhits}  "
              f"投資{spent:.0f} 払戻{returned:.0f} 回収率 {100*roi:.1f}%")


if __name__ == "__main__":
    main()
