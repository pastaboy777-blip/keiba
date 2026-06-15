"""ズブ穴(人気薄)の3着内を実際に予測できる信号を、学習/検証期間で選別する。

やみくもな特徴量追加は過学習で消える(重馬場・内枠で実証)。そこで:
  1. 現行『穴度』スコアの較正: スコア四分位ごとの3着内率を検証期間で測る
     (右肩上がりでなければ、そもそもピック順位が機能していない)。
  2. 各信号の判別力(点双列相関 r = 信号と『3着内か』の相関)を
     学習期間と検証期間で別々に計算し、両期間で同符号・有意な信号だけ採用候補にする。

対象は人気薄(exp_pop>=pop_min)のみ。南関全場(母数確保)。
日付 cutoff より前=学習、以降=検証。

実行: python3 scripts/analyze_zubu_signals.py
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
CUTOFF = "2026-05-01"   # < 学習 / >= 検証


def horse_rows(races):
    """人気薄の各馬を (信号dict, 3着内0/1, 日付) に展開。"""
    rows = []
    for r in races:
        ag = {}
        for h in r["horses"]:
            vals = [x["agari"] for x in h.get("recent_runs", []) if x.get("agari")]
            ag[h["umaban"]] = (sum(vals) / len(vals)) if vals else None
        for h in r["horses"]:
            if h.get("exp_pop") is None or h["exp_pop"] < POP_MIN:
                continue
            if h.get("finish_pos") is None:
                continue
            sig = h.get("signals") or {}
            feats = h.get("features") or {}
            recs = bw.records_of(h)
            s = {
                "穴度(現行)": bw.base_score(h, r, _slow_pts(r, ag)),
                "senkou(先行力)": F.senkou_power(recs),
                "toughness": sig.get("toughness"),
                "days_since_last": sig.get("days_since_last"),
                "tatakii_n": sig.get("tatakii_n"),
                "starts_last_90d": sig.get("starts_last_90d"),
                "weight_diff": sig.get("weight_diff"),
                "jockey_top3_rate": h.get("jockey_top3_rate"),
                "exp_pop": h.get("exp_pop"),
                "exp_odds": h.get("exp_odds"),
                "f_ability": feats.get("ability"),
                "f_interval_fit": feats.get("interval_fit"),
                "f_tatakii": feats.get("tatakii"),
                "f_baba_fit": feats.get("baba_fit"),
                "f_place_fit": feats.get("place_fit"),
                "f_distance_fit": feats.get("distance_fit"),
                "agari_med(遅い+)": ag.get(h["umaban"]),
            }
            rows.append((s, 1 if h["finish_pos"] <= 3 else 0, r["date"]))
    return rows


def _slow_pts(race, ag):
    have = sorted([(u, a) for u, a in ag.items() if a is not None], key=lambda x: -x[1])
    n = len(have)
    out = {}
    for i, (u, _a) in enumerate(have):
        pct = i / (n - 1) if n > 1 else 0.0
        out[u] = 2.0 if pct <= 0.3 else (1.0 if pct <= 0.5 else 0.0)
    return out


def pbcorr(pairs):
    """点双列相関(連続値xと2値yの相関)。None除外。n<30はNone。"""
    xs = [(x, y) for x, y in pairs if x is not None]
    n = len(xs)
    if n < 30:
        return None, n
    mx = sum(x for x, _ in xs) / n
    my = sum(y for _, y in xs) / n
    sx = (sum((x - mx) ** 2 for x, _ in xs) / n) ** 0.5
    sy = (sum((y - my) ** 2 for _, y in xs) / n) ** 0.5
    if sx == 0 or sy == 0:
        return None, n
    cov = sum((x - mx) * (y - my) for x, y in xs) / n
    return cov / (sx * sy), n


def calibration(rows, keyname="穴度(現行)", q=4):
    vals = sorted([(s[keyname], y) for s, y, _ in rows if s.get(keyname) is not None])
    n = len(vals)
    print(f"\n=== 現行『{keyname}』の較正(検証期間・{q}分位)===")
    for i in range(q):
        lo, hi = n * i // q, n * (i + 1) // q
        seg = vals[lo:hi]
        t = sum(y for _, y in seg)
        rng = f"{seg[0][0]:.1f}〜{seg[-1][0]:.1f}"
        print(f"  Q{i+1} ({rng}): 3着内 {100*t/len(seg):.1f}% (n={len(seg)})")


def main() -> None:
    races = bw.load_races()
    rows = horse_rows(races)
    train = [r for r in rows if r[2] < CUTOFF]
    test = [r for r in rows if r[2] >= CUTOFF]
    print(f"人気薄(>={POP_MIN}人) 総{len(rows)}頭 / 学習{len(train)}(〜{CUTOFF})・検証{len(test)}")

    calibration(test, "穴度(現行)")

    keys = list(rows[0][0].keys())
    print(f"\n=== 各信号の判別力(点双列相関 r / 3着内=正)===")
    print(f"  {'信号':<20}{'学習r':>8}{'検証r':>8}  安定?")
    res = []
    for k in keys:
        rtr, _ = pbcorr([(s.get(k), y) for s, y, _ in train])
        rte, nte = pbcorr([(s.get(k), y) for s, y, _ in test])
        res.append((k, rtr, rte, nte))
    # 検証rの絶対値で並べる
    res.sort(key=lambda x: -(abs(x[2]) if x[2] is not None else -1))
    for k, rtr, rte, nte in res:
        if rtr is None or rte is None:
            continue
        stable = "◎安定" if (rtr * rte > 0 and abs(rte) >= 0.03) else (
            "×不安定(符号逆)" if rtr * rte < 0 else "△弱い")
        print(f"  {k:<20}{rtr:>+8.3f}{rte:>+8.3f}  {stable}")
    print("\n※ r>0=値が大きいほど3着内に来やすい。両期間で同符号かつ|検証r|≥0.03を採用候補とする。")


if __name__ == "__main__":
    main()
