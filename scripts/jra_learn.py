"""集めた中央競馬データ(jra_harvest.py の JSONL)で「全部」学習・検証する。

    python3 scripts/jra_learn.py --data data/jra/races.jsonl
    python3 scripts/jra_learn.py --data data/jra/races.jsonl --surface 芝 --min-dist 2200

やること(すべて時系列。前 2/3 で学習、後 1/3 で検証。各レースは過去走だけを使う):

 1. 展開(ペース)の検証と学習
    - 今の tenkai.forecast の pace_index が、実際のラップ(前半3F − 後半3F)と合っているか
    - メンバー構成(逃げ率合計・先行勢の割合・距離・直線・頭数)→ 実際の前後半差 を
      線形回帰で学習し、検証区間で当たるか。係数を data/jra/pace_model.json に保存
 2. 展開利の検証 … 展開利と着順の相関(距離帯・実際のペース別)
 3. 着順モデルの学習 … 13+2 特徴量(展開利・芝ダ適性を含む)の重みを Plackett-Luce で学習。
    重みを data/jra/weights.json に保存
 4. 回収率の検証
    - 単勝: 予測勝率 × 確定単勝オッズ > 閾値 の馬だけ買う
    - 三連複: 予測上位5頭のBOX(10点)。払戻は実際の配当
    - 比較: 人気上位5頭のBOX
    ※ 確定オッズで判定しているので実戦より甘い(発走前オッズとはずれる)。
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.core import dataset as ds
from nankeiba.core import tenkai as tk
from nankeiba.core import course as cs
from nankeiba.core import probability as pb
from nankeiba.core.backtest import race_contexts, record_result
from nankeiba.core.learn import train_scorer
from nankeiba.scraping.db_race import pace_of


def corr(xs, ys):
    if len(xs) < 3:
        return float("nan")
    mx, my = st.mean(xs), st.mean(ys)
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy) if sx and sy else float("nan")


def rank_corr(xs, ys):
    rk = lambda v: {i: r for r, i in enumerate(sorted(range(len(v)), key=lambda i: v[i]))}  # noqa: E731
    rx, ry = rk(xs), rk(ys)
    return corr([rx[i] for i in range(len(xs))], [ry[i] for i in range(len(ys))])


def ols(X, y, l2=1e-6):
    """最小二乗(正規方程式 + ガウス消去)。X は切片列込み。"""
    k = len(X[0])
    A = [[sum(r[i] * r[j] for r in X) + (l2 if i == j else 0) for j in range(k)] for i in range(k)]
    b = [sum(r[i] * t for r, t in zip(X, y)) for i in range(k)]
    for i in range(k):
        p = max(range(i, k), key=lambda r: abs(A[r][i]))
        A[i], A[p], b[i], b[p] = A[p], A[i], b[p], b[i]
        for r in range(k):
            if r != i and A[i][i]:
                f = A[r][i] / A[i][i]
                A[r] = [a - f * c for a, c in zip(A[r], A[i])]
                b[r] -= f * b[i]
    return [b[i] / A[i][i] if A[i][i] else 0.0 for i in range(k)]


PACE_FEATS = ["1", "nige_sum", "front_share", "dist_km", "front_bias", "field", "known_share"]


def pace_features(fc: tk.PaceForecast, place, dist, surface, n) -> dict:
    known = [s for s in fc.styles.values() if s.early is not None]
    return {
        "1": 1.0,
        "nige_sum": sum(s.nige_rate for s in known),
        "front_share": sum(1 for s in known if s.early <= 0.35) / max(1, n),
        "dist_km": dist / 1000,
        "front_bias": cs.front_bias(place, surface),
        "field": n / 18,
        "known_share": len(known) / max(1, n),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="中央競馬 学習・検証")
    ap.add_argument("--data", default="data/jra/races.jsonl")
    ap.add_argument("--surface", choices=["芝", "ダ"])
    ap.add_argument("--min-dist", type=int, default=0)
    ap.add_argument("--max-dist", type=int, default=9999)
    ap.add_argument("--train-frac", type=float, default=2 / 3)
    ap.add_argument("--min-history", type=int, default=2)
    ap.add_argument("--win-ev", type=float, default=1.2)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--outdir", default="data/jra")
    a = ap.parse_args()

    raw = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    raw = [d for d in raw if d.get("surface") in ("芝", "ダ") and d.get("result")]
    raw.sort(key=lambda d: (d["date"], d["race_id"]))
    races = [ds.race_from_dict(d) for d in raw]
    cut = raw[int(len(raw) * a.train_frac)]["date"] if raw else ""
    sel = lambda d: ((not a.surface or d["surface"] == a.surface)  # noqa: E731
                     and a.min_dist <= d["distance"] <= a.max_dist)
    print(f"読み込み {len(raw)} 鞍  期間 {raw[0]['date']}〜{raw[-1]['date']}  学習/検証の境 {cut}")
    print(f"評価対象: {a.surface or '芝ダ'} {a.min_dist}〜{a.max_dist}m\n")

    # ---------- 1周目: 過去走だけで展開を予想し、実際のラップ・着順と並べる ----------
    history: dict = {}
    P = []   # ペース行
    A = []   # 展開利行 (adv, 着順の強さ, 実際の diff)
    for d, race in zip(raw, races):
        ctxs = race_contexts(race, history)
        pasts = {e.num(): p for e, p, _ in ctxs}
        fc = tk.forecast(pasts, place=race.place, distance=race.distance, surface=race.surface)
        pc = pace_of(d.get("lap") or [], race.distance)
        if sel(d) and pc:
            P.append({"date": d["date"], "pi": fc.pace_index, "y": pc["diff"],
                      "x": pace_features(fc, race.place, race.distance, race.surface, race.field_size),
                      "dist": race.distance})
            pos = {u: i for i, u in enumerate(race.result_order)}
            n = race.field_size
            for u, adv in fc.advantage.items():
                if fc.styles[u].early is not None and u in pos:
                    A.append((adv, 1 - pos[u] / max(1, n - 1), pc["diff"], d["date"]))
        record_result(race, history)

    print("== 1. 展開(ペース)の検証 ==")
    print(f"  ラップのある鞍: {len(P)}")
    if P:
        r = corr([p["pi"] for p in P], [p["y"] for p in P])
        print(f"  今の pace_index と実際(前半3F−後半3F)の相関: {r:+.3f}"
              "   ※ハイ予想ほど前半が速い(diff が小さい)なら負になるのが正解")
        tr = [p for p in P if p["date"] < cut]
        te = [p for p in P if p["date"] >= cut]
        if len(tr) > 20 and te:
            w = ols([[p["x"][f] for f in PACE_FEATS] for p in tr], [p["y"] for p in tr])
            pred = lambda p: sum(wi * p["x"][f] for wi, f in zip(w, PACE_FEATS))  # noqa: E731
            print(f"  学習したペースモデル(検証区間)の相関: {corr([pred(p) for p in te], [p['y'] for p in te]):+.3f}")
            print(f"  ベースライン(今の pace_index・検証区間): {corr([p['pi'] for p in te], [p['y'] for p in te]):+.3f}")
            print("  係数(+ ほど後傾=スロー寄り):")
            for f, wi in zip(PACE_FEATS, w):
                print(f"    {f:<12s} {wi:+.3f}")
            Path(a.outdir).mkdir(parents=True, exist_ok=True)
            json.dump({"features": PACE_FEATS, "coef": w, "cut": cut, "n_train": len(tr)},
                      open(Path(a.outdir) / "pace_model.json", "w"), ensure_ascii=False, indent=1)
        # 距離帯別
        for lo, hi in [(0, 1400), (1401, 1800), (1801, 2200), (2201, 9999)]:
            g = [p for p in P if lo <= p["dist"] <= hi]
            if len(g) > 10:
                print(f"    {lo:>4}〜{hi:<4}m  n={len(g):5d}  相関 {corr([p['pi'] for p in g], [p['y'] for p in g]):+.3f}"
                      f"  実際の前後半差 平均 {st.mean(p['y'] for p in g):+.2f}秒")

    print("\n== 2. 展開利の検証(展開利 vs 着順の強さ) ==")
    if A:
        print(f"  全体 n={len(A)}  順位相関 {rank_corr([x[0] for x in A], [x[1] for x in A]):+.3f}")
        q = st.quantiles([x[2] for x in A], n=3)
        for name, f in [("実際ハイ(前傾)", lambda x: x[2] <= q[0]),
                        ("実際ミドル", lambda x: q[0] < x[2] <= q[1]),
                        ("実際スロー(後傾)", lambda x: x[2] > q[1])]:
            g = [x for x in A if f(x)]
            print(f"  {name:<12s} n={len(g):6d}  順位相関 {rank_corr([x[0] for x in g], [x[1] for x in g]):+.3f}")

    # ---------- 3. 着順モデルの学習 ----------
    print("\n== 3. 着順モデルの学習 ==")
    train = [r for r in races if r.date < cut]
    jockeys, trainers = ds.derive_conn_stats(train)
    scorer = train_scorer(train, jockeys=jockeys, trainers=trainers,
                          epochs=a.epochs, lr=0.2, l2=1e-3, top_k=3, min_history=a.min_history)
    for name, w in scorer.importances():
        print(f"    {name:<14s} {w:+.3f}")
    json.dump({"weights": scorer.weights, "means": scorer.means, "stds": scorer.stds, "cut": cut},
              open(Path(a.outdir) / "weights.json", "w"), ensure_ascii=False, indent=1)

    # ---------- 4. 回収率の検証(検証区間) ----------
    print("\n== 4. 回収率(検証区間・確定オッズ/実配当) ==")
    history = {}
    win = {"bet": 0, "ret": 0.0, "hit": 0}
    box = {"bet": 0, "ret": 0.0, "hit": 0}
    pop = {"bet": 0, "ret": 0.0, "hit": 0}
    top1 = fav1 = nr = 0
    for d, race in zip(raw, races):
        if race.date >= cut and sel(d):
            ctxs = race_contexts(race, history)
            if all(len(p) >= a.min_history for _, p, _ in ctxs) and len(ctxs) >= 5:
                nr += 1
                scores = {e.num(): scorer(p, c) for e, p, c in ctxs}
                s = pb.strengths_from_scores(scores)
                tot = sum(s.values())
                odds = {r["umaban"]: r.get("win_odds") for r in d["result"]}
                popu = {r["umaban"]: r.get("popularity") or 99 for r in d["result"]}
                winner = race.result_order[0]
                order = sorted(scores, key=scores.get, reverse=True)
                top1 += order[0] == winner
                fav1 += min(popu, key=popu.get) == winner
                for u, sv in s.items():
                    o = odds.get(u)
                    if o and sv / tot * o > a.win_ev:
                        win["bet"] += 100
                        if u == winner:
                            win["ret"] += o * 100
                            win["hit"] += 1
                trio_pay = d.get("payouts", {}).get("trio", {})
                hit_key = tuple(sorted(race.result_order[:3]))
                for name, pick, acc in [("model", order[:5], box),
                                        ("pop", sorted(popu, key=popu.get)[:5], pop)]:
                    for c in combinations(sorted(pick), 3):
                        acc["bet"] += 100
                        if c == hit_key:
                            acc["ret"] += sum(trio_pay.values()) if len(trio_pay) == 1 else \
                                trio_pay.get("-".join(map(str, c)), 0)
                            acc["hit"] += 1
        record_result(race, history)

    roi = lambda x: x["ret"] / x["bet"] if x["bet"] else 0.0  # noqa: E731
    print(f"  対象 {nr} 鞍")
    print(f"  1着的中(予測1位) {top1 / max(1, nr):.1%}   参考: 1番人気 {fav1 / max(1, nr):.1%}")
    print(f"  単勝 EV>{a.win_ev}  {win['bet'] // 100}点  的中 {win['hit']}  回収率 {roi(win):.1%}")
    print(f"  三連複 予測上位5頭BOX  的中 {box['hit']}/{nr}  回収率 {roi(box):.1%}")
    print(f"  三連複 人気上位5頭BOX  的中 {pop['hit']}/{nr}  回収率 {roi(pop):.1%}")
    print("\n※確定オッズ・実配当での後付け検証。発走前のオッズとはずれるので実戦はこれより厳しい。")


if __name__ == "__main__":
    main()
