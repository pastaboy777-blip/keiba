"""v2(騎手質+地力+先行)に『前走レベル(時計)』を足すと本線3着内率が上がるか検証。

improve_zubu と同じ流儀: 学習期間で標準化統計を作り、検証期間で各レースの本線
(人気薄の最上位1頭)が3着内に来た率を、重み w を変えて比較する。w=0 は現行v2。
w を上げて検証期間の本線的中が改善するなら、前走レベルは本採用の価値あり。

実行: python3 scripts/verify_level_combo.py
"""

from __future__ import annotations

import glob
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import predict_nankan as pn

FILES = sorted(glob.glob("data/samples/nankan_2026-0*.jsonl"))
CUTOFF = "2026-05-01"
POP_MIN = 6


def t2s(t):
    if not t or ":" not in str(t):
        return None
    m, s = str(t).split(":")
    try:
        return int(m) * 60 + float(s)
    except ValueError:
        return None


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    return None if n == 0 else (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2)


def build_baseline(records):
    buckets = {}
    for rec in records:
        for h in rec["horses"]:
            for r in h.get("recent_runs", []):
                sec, dist = t2s(r.get("time")), r.get("distance")
                if sec and dist:
                    key = (r.get("place"), dist, (r.get("baba") or "")[:1])
                    buckets.setdefault(key, []).append(sec / dist)
    return {k: st.median(v) for k, v in buckets.items() if len(v) >= 8}


def level_of(r, base):
    sec, dist = t2s(r.get("time")), r.get("distance")
    if not sec or not dist:
        return None
    b = base.get((r.get("place"), dist, (r.get("baba") or "")[:1]))
    return None if b is None else (b - sec / dist) * 1000


def main():
    records = [json.loads(l) for f in FILES for l in open(f, encoding="utf-8") if l.strip()]
    base = build_baseline(records)
    v2_stats = pn.zubu_v2_stats_from_samples(FILES, pop_min=POP_MIN)
    jrates = pn.jockey_top3_from_samples(FILES)

    # 前走レベルの標準化(学習期間の人気薄で)
    lv_tr = []
    for rec in records:
        if rec["date"] >= CUTOFF:
            continue
        for h in rec["horses"]:
            if (h.get("exp_pop") or 0) >= POP_MIN and h.get("recent_runs"):
                lv = level_of(h["recent_runs"][0], base)
                if lv is not None:
                    lv_tr.append(lv)
    lm, lsd = (sum(lv_tr) / len(lv_tr), st.pstdev(lv_tr)) if len(lv_tr) > 1 else (0.0, 1.0)

    def score(h, w):
        jq = h.get("jockey_top3_rate") or jrates.get(h.get("jockey"), 0.0)
        ability = (h.get("features") or {}).get("ability")
        senkou = pn._senkou_from_recent(h.get("recent_runs", []))
        agari = _median([r["agari"] for r in h.get("recent_runs", []) if r.get("agari")])
        s = pn.zubu_v2_score(jq, ability, senkou, agari, v2_stats)
        if w and h.get("recent_runs"):
            lv = level_of(h["recent_runs"][0], base)
            if lv is not None:
                s += w * (lv - lm) / (lsd or 1.0)
        return s

    print(f"検証期間({CUTOFF}以降) 本線(人気薄>={POP_MIN}の最上位1頭)3着内率 / 重みw別\n")
    print(f"{'w(前走レベル)':<14}{'本線3着内':>12}{'上位3頭3着内':>14}")
    for w in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]:
        head_hit = head_n = p_hit = p_n = 0
        for rec in records:
            if rec["date"] < CUTOFF:
                continue
            cand = [h for h in rec["horses"]
                    if (h.get("exp_pop") or 0) >= POP_MIN and h.get("finish_pos") is not None
                    and h.get("recent_runs")]
            if not cand:
                continue
            cand = sorted(cand, key=lambda h: -score(h, w))
            head_n += 1
            if cand[0]["finish_pos"] <= 3:
                head_hit += 1
            for h in cand[:3]:
                p_n += 1
                if h["finish_pos"] <= 3:
                    p_hit += 1
        tag = "(現行v2)" if w == 0 else ""
        print(f"{w:<14.1f}{head_hit}/{head_n}={100*head_hit/head_n:>4.1f}%   "
              f"{p_hit}/{p_n}={100*p_hit/p_n:>4.1f}%  {tag}")


if __name__ == "__main__":
    main()
