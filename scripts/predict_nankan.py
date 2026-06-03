"""楽天競馬の出馬表から、南関の1レースを『走らせる』観点で予想する。

出馬表(各馬の前5走)→ core.features.horse_score で総合強さスコアを算出し、
Plackett-Luce で 上位3着確率 / 三連複・三連単確率に変換する。
想定馬場(--baba)を指定すると baba_fit(馬場適性)が効き、道悪巧者を評価できる。

オッズが開いていない先のレースでも予想できる(その場合は期待値ではなく
モデル確率での推奨。オッズ確定後は build_dataset/backtest 系で回収率検証へ)。

実行例:
    python3 scripts/predict_nankan.py --date 2026-06-04 --place 船橋 --race 11 --baba 不
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from nankeiba.scraping import enrich as E
from nankeiba.core import features as F
from nankeiba.core import probability as pb

CARD_URL = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{race_id}"
BABA_FULL = {"良": "良", "稍": "稍重", "重": "重", "不": "不良"}


def weights_for(mode: str) -> F.ScoreWeights:
    """予想モード別の重み。

    shomousen(消耗戦/時計のかかる馬場): 6/3 1R・2R の学びを反映。
    決着時計が遅い消耗戦では、ズブさ(タフネス)と短間隔(連闘・叩き上がり)で
    使い込まれた馬が浮上し、使い込み疲労のマイナスは出にくい。道悪適性も加点。
    """
    w = F.ScoreWeights()
    if mode == "shomousen":
        w.toughness = 0.9      # 0.3 → 大幅加点(ズブさ=最重要)
        w.interval_fit = 0.9   # 0.6 → 短間隔有利を強調
        w.tatakii = 1.3        # 1.0 → 叩き上がり
        w.baba_fit = 0.8       # 0.5 → 道悪適性
        w.senkou = 0.6         # 0.5 → 前で運べる(止まりにくい)を微増
        w.fatigue = 0.4        # 1.0 → 使い込みのマイナスを軽減
    return w


def trainer_stats_from_samples(paths) -> F.ConnStats:
    """蓄積済み充実データ(6/1・6/2 等)から調教師の好走率(3着内率)を推定。"""
    starts: dict[str, int] = {}
    hits: dict[str, int] = {}
    tot_s = tot_h = 0
    for p in paths:
        if not Path(p).exists():
            continue
        for line in open(p, encoding="utf-8"):
            rec = json.loads(line)
            fs = rec.get("field_size") or 0
            for h in rec["horses"]:
                t = h.get("trainer")
                fp = h.get("finish_pos")
                if not t or fp is None:
                    continue
                hit = 1 if fp <= 3 else 0
                starts[t] = starts.get(t, 0) + 1
                hits[t] = hits.get(t, 0) + hit
                tot_s += 1
                tot_h += hit
    if tot_s == 0:
        return F.ConnStats()
    prior = tot_h / tot_s
    pseudo = 10.0
    rates = {t: (hits[t] + pseudo * prior) / (starts[t] + pseudo) for t in starts}
    return F.ConnStats(rates=rates, default=prior)


def mark(rank: int) -> str:
    return {1: "◎", 2: "○", 3: "▲", 4: "△", 5: "△"}.get(rank, " ")


def main() -> None:
    ap = argparse.ArgumentParser(description="楽天競馬 南関 1レース予想(走らせる観点)")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--place", choices=list(NANKAN_CODES), required=True)
    ap.add_argument("--race", type=int, required=True)
    ap.add_argument("--baba", choices=list(BABA_FULL), default="良", help="想定馬場 良/稍/重/不")
    ap.add_argument("--mode", choices=["normal", "shomousen"], default="normal",
                    help="shomousen=消耗戦/時計のかかる馬場(タフネス・短間隔を加点)")
    ap.add_argument("--temp", type=float, default=1.0, help="確率の尖り(小さいほど自信)")
    ap.add_argument("--samples", nargs="*", default=[
        "data/samples/nankan_2026-06-01.jsonl", "data/samples/nankan_2026-06-02.jsonl"])
    args = ap.parse_args()

    ymd = args.date.replace("-", "")
    client = PoliteClient()
    idx = client.get(CARD_URL.format(race_id=day_index_race_id(ymd, args.place)))
    races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=NANKAN_CODES[args.place]))
    if args.race not in races:
        raise SystemExit(f"{args.date} {args.place} {args.race}R が見つかりません。あるR: {sorted(races)}")
    rid = races[args.race]
    card = P.parse_card_page(client.get(CARD_URL.format(race_id=rid)), rid)

    jockeys = E.jockey_stats_from_card(card)
    trainers = trainer_stats_from_samples(args.samples)
    weights = weights_for(args.mode)

    scores: dict[int, float] = {}
    rows = []
    for e in card.entries:
        ctx = F.RaceContext(date=card.date, place=card.place, distance=card.distance,
                            field_size=card.field_size, jockey=e.jockey,
                            trainer=e.trainer, baba=args.baba)
        records = E.past_runs_to_records(e)
        feats = F.horse_features(records, ctx, jockeys=jockeys, trainers=trainers)
        sc = F.horse_score(records, ctx, jockeys=jockeys, trainers=trainers, weights=weights)
        scores[e.umaban] = sc
        rows.append((e, feats, sc))

    strengths = pb.strengths_from_scores(scores, temperature=args.temp)
    top3 = {um: pb.top3_probability(strengths, um) for um in scores}
    trio = sorted(pb.trio_probabilities(strengths).items(), key=lambda kv: -kv[1])
    trifecta = sorted(pb.trifecta_probabilities(strengths).items(), key=lambda kv: -kv[1])

    ranked = sorted(rows, key=lambda r: -r[2])
    mode_label = "消耗戦(タフネス・短間隔を加点)" if args.mode == "shomousen" else "通常"
    print(f"\n=== {card.place} {args.race}R {card.surface}{card.distance}m "
          f"/ 想定馬場: {BABA_FULL[args.baba]} / モード: {mode_label} ===")
    print(f"{'印':<2}{'馬番':>3} {'馬名':<11}{'騎手':<6}{'上位3着%':>7} "
          f"{'道悪':>6}{'脚質':>6}{'間隔':>6}{'叩':>3}{'タフ':>6}")
    for i, (e, feats, sc) in enumerate(ranked, 1):
        sig = E.running_signals(e, F.RaceContext(date=card.date, place=card.place,
              distance=card.distance, field_size=card.field_size, jockey=e.jockey,
              trainer=e.trainer, baba=args.baba), E.past_runs_to_records(e))
        print(f"{mark(i):<2}{str(e.umaban):>3} {e.horse_name[:10]:<11}"
              f"{(e.jockey or '')[:5]:<6}{top3[e.umaban]*100:>6.1f}% "
              f"{feats['baba_fit']:>+6.2f}{feats['senkou']:>+6.2f}"
              f"{str(sig['days_since_last'])+'日':>6}{sig['tatakii_n']:>3}{sig['toughness']:>6.2f}")

    print("\n--- 推奨買い目(モデル確率上位)---")
    print("三連複: " + " / ".join(f"{'-'.join(map(str,k))}({v*100:.1f}%)" for k, v in trio[:6]))
    print("三連単: " + " / ".join(f"{'→'.join(map(str,k))}({v*100:.2f}%)" for k, v in trifecta[:6]))
    print("\n※ オッズ未開放のためモデル確率での推奨。オッズ確定後は期待値(回収率)モードで再評価可。")


if __name__ == "__main__":
    main()
