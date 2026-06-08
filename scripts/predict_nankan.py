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
RESULT_URL = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{race_id}"
BABA_FULL = {"良": "良", "稍": "稍重", "重": "重", "不": "不良"}


def _t2s(t):
    if not t or ":" not in str(t):
        return None
    m, s = str(t).split(":")
    return int(m) * 60 + float(s)


def day_target_time(client, races, distance):
    """当日の決着時計トレンドから、この距離の『想定勝ち時計(秒)』を逆算する。

    同距離の確定レースがあればその中央値、無ければ全確定レースの秒/1000m中央値×距離。
    返り値: (想定秒, 説明) / 確定レースが無ければ (None, ...)。
    """
    same, idx = [], []
    for _rno, rid in races:
        try:
            res = P.parse_result_page(client.get(RESULT_URL.format(race_id=rid)), rid)
        except Exception:  # noqa: BLE001
            continue
        if not res.rows:
            continue
        sec = _t2s(res.rows[0].time)
        if not sec:
            continue
        if res.distance == distance:
            same.append(sec)
        idx.append(sec / res.distance * 1000)
    import statistics as st
    if same:
        return st.median(same), f"同距離{len(same)}R中央値"
    if idx:
        return st.median(idx) * distance / 1000, f"全{len(idx)}R秒/1000m換算"
    return None, "確定レースなし"


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
        w.senkou = 0.9         # 0.5 → 前で運べる馬を大幅加点(上がり使えない=前残り)
        w.agari = 0.0          # 0.3 → 切れ味は無効(上がりが使えない馬場)
        w.fatigue = 0.4        # 1.0 → 使い込みのマイナスを軽減
    elif mode == "zenzan":
        # 前残り/上がり使えない馬場の"中庸"版: 地力(ability)は残したまま、
        # 前で運べる脚質と道悪適性だけ上乗せ、切れ味は無効。堅い決着を壊さない。
        w.senkou = 0.9         # 前で運べる馬を加点
        w.agari = 0.0          # 切れ味は無効
        w.baba_fit = 0.7       # 道悪適性
    return w


def agari_style_adjust(card, *, scale: float = 0.35):
    """上がりが使えない(前残り)馬場向けの脚質補正。

    各馬の近走の上がり(中央値)をレース内で比較し、**遅い=持続/前型を加点**、
    **速い=切れ味/差し型を割引**する。上がりが使えない馬場では切れる脚は不発で、
    前で粘れる持続型が残るため。返り値: {馬番: 補正スコア(±scale程度)}。
    """
    med = {}
    for e in card.entries:
        if e.umaban is None:
            continue
        vals = [pr.agari for pr in e.recent_runs if pr.agari]
        if vals:
            med[e.umaban] = _median(vals)
    if len(med) < 3:
        return {}
    order = sorted(med, key=lambda um: -med[um])   # 遅い順
    n = len(order)
    return {um: scale * (1 - 2 * i / (n - 1)) for i, um in enumerate(order)}


def jockey_top3_from_samples(paths) -> dict:
    """蓄積データから騎手の3着内率(%)を推定。

    出馬表に騎手成績が未反映(発走直前まで0%)の時のフォールバックに使う。
    返り値: {騎手名: 3着内率%}(全体平均へ縮約)。
    """
    starts: dict[str, int] = {}
    hits: dict[str, int] = {}
    tot_s = tot_h = 0
    for p in paths:
        if not Path(p).exists():
            continue
        for line in open(p, encoding="utf-8"):
            rec = json.loads(line)
            for h in rec["horses"]:
                j, fp = h.get("jockey"), h.get("finish_pos")
                if not j or fp is None:
                    continue
                starts[j] = starts.get(j, 0) + 1
                hits[j] = hits.get(j, 0) + (1 if fp <= 3 else 0)
                tot_s += 1
                tot_h += 1 if fp <= 3 else 0
    if tot_s == 0:
        return {}
    prior = tot_h / tot_s
    pseudo = 15.0
    return {j: 100.0 * (hits[j] + pseudo * prior) / (starts[j] + pseudo) for j in starts}


def trainer_stats_from_samples(paths) -> F.ConnStats:
    """蓄積済み充実データから調教師の好走率(3着内率)を推定。"""
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


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    return None if n == 0 else (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2)


def _best_time_at(entry, distance):
    """この距離での自己最速タイム(秒)。無ければ None。"""
    ts = [_t2s(pr.time) for pr in entry.recent_runs if pr.distance == distance and _t2s(pr.time)]
    return min(ts) if ts else None


def time_fit(entry, distance, target_time):
    """タイム適性: 当日想定勝ち時計に対し『今日の決着に間に合う持ち時計か』。

    時計は"足切り＋小さな加点"として使う(最速=勝ちではないので過大評価しない)。
    返り値: (flag, bonus, tag) ── flag 'fail' は足切り対象。
    """
    if target_time is None:
        return "na", 0.0, None
    best = _best_time_at(entry, distance)
    if best is None:
        return "na", 0.0, None        # 当該距離の持ち時計なし=判定不能(切らない)
    if best <= target_time:
        return "ok", 1.0, f"時計足りる(自己最速{best:.1f}≦想定{target_time:.1f})"
    if best <= target_time + 0.8:
        return "edge", 0.5, f"時計際どい({best:.1f})"
    return "fail", 0.0, f"時計不足({best:.1f}>想定{target_time:.1f})"


def zubu_ana_picks(card, jockeys, *, pop_min: int = 6, target_time=None,
                   jockey_rates=None, jockey_div: float = 8.0):
    """『ズブい馬を走らせる』観点 ＋ タイム適性フィルターで人気薄(穴)を拾う。

    方針:
      - タイム適性: 当日想定勝ち時計に間に合わない馬は足切り、間に合う馬に小加点
        (着順は無視。"着順は悪いが時計は足りている"人気薄を救うのが狙い)
      - 上がりの遅い馬を重視(切れ味より前粘り・持続型=ズブさ)
      - 乗り替わり(特に上位騎手への強化)
      - 出走間隔: 連闘/中1〜2週で詰めてきた or 適度な間隔
      - 場替わり・距離短縮(条件を合わせてきた=走らせにきた)
    """
    # レース内の上がり順位(遅い=高ポイント)
    ag = {}
    for e in card.entries:
        vals = [pr.agari for pr in e.recent_runs if pr.agari]
        ag[e.umaban] = _median(vals)
    have = sorted([(um, a) for um, a in ag.items() if a is not None], key=lambda x: -x[1])
    n = len(have)
    slow_pts = {}
    for i, (um, _a) in enumerate(have):
        pct = i / (n - 1) if n > 1 else 0.0   # 0=最も遅い
        slow_pts[um] = 2.0 if pct <= 0.3 else (1.0 if pct <= 0.5 else 0.0)

    picks = []
    for e in card.entries:
        if e.umaban is None:
            continue   # 馬番が取れない行はスキップ
        if e.exp_pop is not None and e.exp_pop < pop_min:
            continue   # 人気サイドは穴ピックの対象外
        records = E.past_runs_to_records(e)
        sig = E.running_signals(e, F.RaceContext(
            date=card.date, place=card.place, distance=card.distance,
            field_size=card.field_size, jockey=e.jockey, trainer=e.trainer),
            records)
        tf_flag, tf_bonus, tf_tag = time_fit(e, card.distance, target_time)
        if tf_flag == "fail":
            continue   # 当日の決着に間に合わない=足切り
        score = tf_bonus
        tags = [tf_tag] if tf_tag else []
        sp = slow_pts.get(e.umaban, 0.0)
        if sp:
            score += sp
            tags.append("上がり遅い(持続型)" if sp >= 2 else "上がりやや遅")
        d = sig["days_since_last"]
        if d is not None and d <= 14:
            score += 1.0
            tags.append(f"連闘/詰め({d}日)")
        elif d is not None and 15 <= d <= 20:
            score += 1.5
            tags.append(f"中1-2週({d}日)")
        elif d is not None and d >= 35:
            score += 1.0
            tags.append(f"間隔あけ({d}日)")
        if sig["jockey_changed"]:
            up = jockeys.get(e.jockey) - jockeys.get(sig["prev_jockey"])
            if up > 0.01:
                score += 1.5
                tags.append(f"乗替強化→{e.jockey}")
            else:
                score += 0.5
                tags.append(f"乗替→{e.jockey}")
        if sig["place_changed"]:
            score += 0.5
            tags.append("場替わり")
        if sig["distance_change"] is not None and sig["distance_change"] < 0:
            score += 0.5
            tags.append(f"距離短縮({sig['distance_change']}m)")
        # 前で運べる脚質(前残り馬場で穴になる・検証で人気薄+2.0/道悪+2.7)
        sen = F.senkou_power(records)
        if sen >= 0.2:
            score += sen * 2.5
            tags.append(f"前で運べる(脚質{sen:+.2f})")
        elif sen <= -0.15:
            score += sen * 1.5          # 後方型は減点(人気薄で-1.4)
        # ★主軸: 騎手の質(上位騎手が人気薄に乗る=市場が過小評価)。3ヶ月検証で
        #   人気薄3着内率+12.7%、トップピック的中12.0%→16.4%(/6重み)に改善。
        jq = e.jockey_top3_rate or 0.0
        if jq <= 0 and jockey_rates:          # カード未反映時は蓄積データで代替
            jq = jockey_rates.get(e.jockey, 0.0)
        if jq > 0:
            score += jq / jockey_div          # 重みは --jw で調整(大=弱める)
            if jq >= 25:
                tags.insert(0, f"上位騎手({e.jockey}・3着内{jq:.0f}%)")
        if score > 0:
            picks.append((e, score, tags))
    picks.sort(key=lambda x: -x[1])
    return picks


def main() -> None:
    ap = argparse.ArgumentParser(description="楽天競馬 南関 1レース予想(走らせる観点)")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--place", choices=list(NANKAN_CODES), required=True)
    ap.add_argument("--race", type=int, required=True)
    ap.add_argument("--baba", choices=list(BABA_FULL), default="良", help="想定馬場 良/稍/重/不")
    ap.add_argument("--mode", choices=["normal", "shomousen", "zenzan"], default="normal",
                    help="shomousen=消耗戦/時計のかかる馬場(タフネス・短間隔を加点)")
    ap.add_argument("--temp", type=float, default=1.0, help="確率の尖り(小さいほど自信)")
    ap.add_argument("--ana", action="store_true",
                    help="ズブ穴ピックアップ(タイム適性フィルター＋上がり遅さ・乗替・間隔詰めで人気薄を拾う)")
    ap.add_argument("--target-time", type=float, default=None,
                    help="想定勝ち時計[秒](未指定なら当日トレンドから自動逆算)")
    ap.add_argument("--jw", type=float, default=8.0,
                    help="騎手の質の弱め係数(大きいほど騎手ファクターを下げる。既定8)")
    ap.add_argument("--pop-min", type=int, default=6,
                    help="ズブ穴の人気しきい値(この人気以下が対象。既定6=6番人気以下)")
    ap.add_argument("--samples", nargs="*", default=[
        "data/samples/nankan_2026-04.jsonl", "data/samples/nankan_2026-05.jsonl",
        "data/samples/nankan_2026-06.jsonl"])
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
    # 上がりが使えない(前残り)馬場では、本ランキングにも脚質補正を効かせる
    agari_adj = agari_style_adjust(card) if args.mode in ("shomousen", "zenzan") else {}

    scores: dict[int, float] = {}
    rows = []
    for e in card.entries:
        if e.umaban is None:
            continue   # 馬番が取れない行(取消・パース欠け)はスキップ
        ctx = F.RaceContext(date=card.date, place=card.place, distance=card.distance,
                            field_size=card.field_size, jockey=e.jockey,
                            trainer=e.trainer, baba=args.baba)
        records = E.past_runs_to_records(e)
        feats = F.horse_features(records, ctx, jockeys=jockeys, trainers=trainers)
        sc = F.horse_score(records, ctx, jockeys=jockeys, trainers=trainers, weights=weights)
        sc += agari_adj.get(e.umaban, 0.0)   # 遅い上がり=持続型を加点 / 速い=割引
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
    if args.ana:
        tt = args.target_time
        note = "手動指定"
        if tt is None:
            tt, note = day_target_time(client, list(races.items()), card.distance)
        jrates = jockey_top3_from_samples(args.samples)
        picks = zubu_ana_picks(card, jockeys, target_time=tt, jockey_rates=jrates,
                               jockey_div=args.jw, pop_min=args.pop_min)
        tt_s = f"{tt:.1f}秒({note})" if tt else "算出不可(確定レースなし)"
        print(f"\n--- ★ズブ穴ピックアップ(タイム適性フィルター＋走らせる)/ 想定勝ち時計 {tt_s} ---")
        if not picks:
            print("  該当なし")
        for e, score, tags in picks[:5]:
            print(f"  ◇{e.umaban:>2} {e.horse_name[:10]:<11}({e.exp_pop}人気) "
                  f"穴度{score:.1f}  {'・'.join(tags)}")

    print("\n※ オッズ未開放のためモデル確率での推奨。オッズ確定後は期待値(回収率)モードで再評価可。")


if __name__ == "__main__":
    main()
