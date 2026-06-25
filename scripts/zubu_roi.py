"""ズブ穴v2ピックの『回収率(ROI)』を複勝・ワイドBOXで測るバックテスト。

充実JSONL(features付き=v2ピックの計算元)と、collect_data で集めた結果JSONL
(複勝/ワイドオッズ付き)を race_id で結合する。各レースで人気薄(exp_pop>=pop_min)を
v2(騎手質+地力+先行)で並べ、上位を 複勝/ワイドBOX で買った時の回収率を出す。

v2の素点・標準化は predict_nankan と同一(=本番の出し方と一致)。複勝/ワイドの
払戻はレンジ下限を採用しているため、ここで出るROIは保守的(実際はこれ以上)。

買い目:
  - 複勝: v2上位1頭 / 上位3頭それぞれ100円
  - ワイドBOX: v2上位K頭の総当たり(K=2→1点, K=3→3点)各100円
  - 比較用ベース: 人気薄(穴)全頭の複勝フラット買い(v2の上乗せ効果を見る)

実行例:
    python3 scripts/zubu_roi.py \
        --enriched data/samples/nankan_2026-04.jsonl data/samples/nankan_2026-05.jsonl \
        --odds data/odds/results_odds_2026-0405.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import predict_nankan as pn

STAKE = 100  # 1点あたりの賭け金(円)


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    return None if n == 0 else (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2)


def load_jsonl(path):
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def v2_of(h, jrates, stats):
    """1頭の v2 スコアを predict_nankan と同じ手順で算出する。"""
    jq = h.get("jockey_top3_rate") or jrates.get(h.get("jockey"), 0.0)
    ability = (h.get("features") or {}).get("ability")
    senkou = pn._senkou_from_recent(h.get("recent_runs", []))
    agari_med = _median([r["agari"] for r in h.get("recent_runs", []) if r.get("agari")])
    return pn.zubu_v2_score(jq, ability, senkou, agari_med, stats)


def ranked_ana(race, jrates, stats, pop_min):
    """人気薄(exp_pop>=pop_min)を v2 降順に並べた [(umaban, v2)] を返す。"""
    scored = []
    for h in race["horses"]:
        if h.get("umaban") is None:
            continue
        pop = h.get("exp_pop")
        if pop is None or pop < pop_min:
            continue
        scored.append((h["umaban"], v2_of(h, jrates, stats)))
    scored.sort(key=lambda x: -x[1])
    return scored


def main() -> None:
    ap = argparse.ArgumentParser(description="ズブ穴v2 複勝/ワイドBOX 回収率バックテスト")
    ap.add_argument("--enriched", nargs="+", required=True, help="features付き充実JSONL")
    ap.add_argument("--odds", required=True, help="結果+複勝/ワイドオッズ JSONL")
    ap.add_argument("--pop-min", type=int, default=6, help="穴の人気しきい値(既定6)")
    ap.add_argument("--place", default=None, help="場で絞る(例: 浦和)")
    ap.add_argument("--samples", nargs="*", default=None,
                    help="v2標準化の母集団(既定=--enriched と同じ)")
    args = ap.parse_args()

    samples = args.samples or args.enriched
    jrates = pn.jockey_top3_from_samples(samples)
    stats = pn.zubu_v2_stats_from_samples(samples, pop_min=args.pop_min)

    # race_id -> 払戻(複勝/ワイド) と 3着内馬番
    odds = {}
    for r in load_jsonl(args.odds):
        top3 = {row["umaban"] for row in r.get("result", [])
                if row.get("finish_pos") and row["finish_pos"] <= 3}
        place = {int(k): v for k, v in (r.get("place_odds") or {}).items()}
        wide = {tuple(sorted(int(x) for x in k.split("-"))): v
                for k, v in (r.get("wide_odds") or {}).items()}
        odds[r["race_id"]] = {"top3": top3, "place": place, "wide": wide,
                              "place_name": r.get("place")}

    # 集計箱: (投資, 払戻, 的中, レース数)
    acc = {k: [0, 0, 0, 0] for k in
           ("複勝_本命", "複勝_上位3", "ワイドBOX_2", "ワイドBOX_3", "ベース_穴複勝全")}

    n_join = 0
    for race in load_jsonl_multi(args.enriched):
        o = odds.get(race["race_id"])
        if o is None or not o["top3"]:
            continue
        if args.place and o.get("place_name") != args.place:
            continue
        picks = ranked_ana(race, jrates, stats, args.pop_min)
        if not picks:
            continue
        n_join += 1
        top3, place_o, wide_o = o["top3"], o["place"], o["wide"]

        # --- 複勝: 本命(1位) ---
        um1 = picks[0][0]
        if um1 in place_o:
            box = acc["複勝_本命"]
            box[0] += STAKE
            box[3] += 1
            if um1 in top3:
                box[1] += place_o[um1] * STAKE
                box[2] += 1

        # --- 複勝: v2上位3頭それぞれ ---
        box = acc["複勝_上位3"]
        bought = False
        for um, _v in picks[:3]:
            if um not in place_o:
                continue
            box[0] += STAKE
            bought = True
            if um in top3:
                box[1] += place_o[um] * STAKE
                box[2] += 1
        if bought:
            box[3] += 1

        # --- ワイドBOX: 上位K頭の総当たり ---
        for K, key in ((2, "ワイドBOX_2"), (3, "ワイドBOX_3")):
            ums = [um for um, _ in picks[:K]]
            if len(ums) < 2:
                continue
            box = acc[key]
            race_bought = False
            for i in range(len(ums)):
                for j in range(i + 1, len(ums)):
                    pair = tuple(sorted((ums[i], ums[j])))
                    if pair not in wide_o:
                        continue
                    box[0] += STAKE
                    race_bought = True
                    if pair[0] in top3 and pair[1] in top3:
                        box[1] += wide_o[pair] * STAKE
                        box[2] += 1
            if race_bought:
                box[3] += 1

        # --- ベース: 穴(pop>=min)全頭の複勝フラット ---
        box = acc["ベース_穴複勝全"]
        any_bought = False
        for um, _v in picks:
            if um not in place_o:
                continue
            box[0] += STAKE
            any_bought = True
            if um in top3:
                box[1] += place_o[um] * STAKE
                box[2] += 1
        if any_bought:
            box[3] += 1

    place_tag = f" / 場={args.place}" if args.place else ""
    print(f"\n結合レース {n_join}R(人気薄>={args.pop_min}{place_tag})"
          f" / 払戻はレンジ下限=保守的\n")
    print(f"{'戦略':<16}{'対象R':>6}{'投資':>9}{'払戻':>10}{'的中':>6}{'回収率':>8}")
    for name, (inv, ret, hit, nr) in acc.items():
        roi = (ret / inv * 100) if inv else 0.0
        flag = " ★+" if roi >= 100 else ""
        print(f"{name:<16}{nr:>6}{inv:>9}{int(ret):>10}{hit:>6}{roi:>7.1f}%{flag}")
    print("\n※ 複勝/ワイドは確定ページのレンジ下限。実際の払戻はこれ以上になる。")


def load_jsonl_multi(paths):
    for p in paths:
        yield from load_jsonl(p)


if __name__ == "__main__":
    main()
