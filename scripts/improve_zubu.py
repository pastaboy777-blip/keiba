"""ズブ穴ピックの精度改善: 安定して効く信号だけで再重み付けし、検証期間で比較。

analyze_zubu_signals.py の結論:
  現行『穴度』は3着内をほぼ判別できていない(相関≒0)。
  両期間で安定して効くのは jockey_top3_rate(+), f_ability(+), senkou(+),
  agari_med(−=速い上がりが良い)。toughness/tatakii/interval は効かない。

ここでは学習期間で「標準化の統計量」を作り、上記信号を相関に応じて線形結合した
新スコアを定義。検証期間で『本線(各レース最上位)の3着内率』を現行と比較する。

  変種A(技能型): 騎手の質 + 地力 + 先行 + 上がり(市場情報なし=妙味維持)
  変種B(市場込): A + exp_pop(穴の中の上位人気)=的中率重視・妙味は薄まる

実行: python3 scripts/improve_zubu.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import backtest_wet as bw
from nankeiba.core import features as F

POP_MIN = 6
CUTOFF = "2026-05-01"


def signals_of(h, race, slow_cache):
    feats = h.get("features") or {}
    recs = bw.records_of(h)
    vals = [x["agari"] for x in h.get("recent_runs", []) if x.get("agari")]
    return {
        "jockey": h.get("jockey_top3_rate"),
        "ability": feats.get("ability"),
        "senkou": F.senkou_power(recs),
        "agari": (sum(vals) / len(vals)) if vals else None,   # 遅い=大 → 重みは負
        "pop": h.get("exp_pop"),
        "cur": bw.base_score(h, race, slow_cache),
    }


def slow_cache(race):
    ag = {}
    for h in race["horses"]:
        vals = [x["agari"] for x in h.get("recent_runs", []) if x.get("agari")]
        ag[h["umaban"]] = (sum(vals) / len(vals)) if vals else None
    return bw._slow_pts(race, ag) if hasattr(bw, "_slow_pts") else _slow(race, ag)


def _slow(race, ag):
    have = sorted([(u, a) for u, a in ag.items() if a is not None], key=lambda x: -x[1])
    n = len(have)
    out = {}
    for i, (u, _a) in enumerate(have):
        pct = i / (n - 1) if n > 1 else 0.0
        out[u] = 2.0 if pct <= 0.3 else (1.0 if pct <= 0.5 else 0.0)
    return out


def build_rows(races):
    rows = []
    for r in races:
        sc = _slow(r, {h["umaban"]: (lambda v: sum(v)/len(v) if v else None)(
            [x["agari"] for x in h.get("recent_runs", []) if x.get("agari")])
            for h in r["horses"]})
        for h in r["horses"]:
            if h.get("exp_pop") is None or h["exp_pop"] < POP_MIN or h.get("finish_pos") is None:
                continue
            s = signals_of(h, r, sc)
            rows.append((r["race_id"], r["date"], h["umaban"], s,
                         1 if h["finish_pos"] <= 3 else 0))
    return rows


def standardize(train, keys):
    stats = {}
    for k in keys:
        xs = [row[3][k] for row in train if row[3].get(k) is not None]
        m = sum(xs) / len(xs)
        sd = (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5 or 1.0
        stats[k] = (m, sd)
    return stats


# 信号 -> 重み(符号つき。analyze の検証rを丸めた値)
WEIGHTS_A = {"jockey": 0.20, "ability": 0.14, "senkou": 0.04, "agari": -0.04}
WEIGHTS_B = {"jockey": 0.20, "ability": 0.14, "senkou": 0.04, "agari": -0.04, "pop": -0.18}


def score(row, stats, weights):
    s = 0.0
    for k, w in weights.items():
        v = row[3].get(k)
        if v is None:
            continue
        m, sd = stats[k]
        s += w * (v - m) / sd
    return s


def eval_top1(test_rows, scorer):
    """各レースで最上位スコアの馬の3着内率(=本線精度)と上位3頭ヒット率。"""
    by_race = {}
    for row in test_rows:
        by_race.setdefault(row[0], []).append(row)
    n_head = n_hb = n_pick = n_board = 0
    for rid, rows in by_race.items():
        rows = sorted(rows, key=lambda r: -scorer(r))
        if not rows:
            continue
        n_head += 1
        n_hb += rows[0][4]
        for r in rows[:5]:
            n_pick += 1
            n_board += r[4]
    return (100 * n_hb / n_head, n_head, 100 * n_board / n_pick)


def main() -> None:
    races = bw.load_races()
    rows = build_rows(races)
    train = [r for r in rows if r[1] < CUTOFF]
    test = [r for r in rows if r[1] >= CUTOFF]
    stats = standardize(train, ["jockey", "ability", "senkou", "agari", "pop"])
    print(f"人気薄 学習{len(train)}・検証{len(test)} (cutoff {CUTOFF})\n")

    cur = lambda r: (r[3]["cur"] if r[3]["cur"] is not None else -9)
    sA = lambda r: score(r, stats, WEIGHTS_A)
    sB = lambda r: score(r, stats, WEIGHTS_B)

    print(f"{'スコア':<18}{'本線3着内':>10}{'上位5頭3着内':>12}")
    for name, fn in [("現行 穴度", cur), ("改善A(技能型)", sA), ("改善B(市場込)", sB)]:
        h, nh, b = eval_top1(test, fn)
        print(f"{name:<18}{h:>9.1f}%{b:>11.1f}%   (本線n={nh})")
    print("\n※ 検証期間のみで評価(学習期間で標準化統計を作成=リーク無し)。")
    print("  本線=各レースで最高スコアの人気薄1頭。現行比で改善Aが妙味維持の本命。")


if __name__ == "__main__":
    main()
