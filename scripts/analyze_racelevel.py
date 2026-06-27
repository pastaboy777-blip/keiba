"""前走の『レースレベル(決着の速さ)』と人気薄の3着内の関係を2期間で検定する。

レースレベルは時計で代用: 各馬の走破タイムを 秒/m に直し、(場・距離・馬場)ごとの
基準(中央値)からの速さで標準化する。速い=高レベル戦を経験(または好時計)。
仮説『前走が高レベル(速い決着)だった人気薄は狙える』を検証する。

ラップ/勝ち馬の質での判別は南関データに無い(中央dbのみ)ため、ここは時計ベース。
対象は人気薄(exp_pop>=pop_min)。学習/検証2期間で安定性を確認(過学習回避)。

実行: python3 scripts/analyze_racelevel.py
"""

from __future__ import annotations

import glob
import json
import statistics as st

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


def pbcorr(xs, ys):
    n = len(xs)
    if n < 30:
        return None, n
    mx, my = sum(xs) / n, sum(ys) / n
    sx = (sum((x - mx) ** 2 for x in xs) / n) ** 0.5
    sy = (sum((y - my) ** 2 for y in ys) / n) ** 0.5
    if sx == 0 or sy == 0:
        return None, n
    return sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / (n * sx * sy), n


def main():
    # Pass1: (場,距離,馬場)ごとの 秒/m 基準(中央値)を全 recent_runs から作る
    buckets = {}
    for fp in FILES:
        for line in open(fp, encoding="utf-8"):
            if not line.strip():
                continue
            for h in json.loads(line)["horses"]:
                for r in h.get("recent_runs", []):
                    sec, dist = t2s(r.get("time")), r.get("distance")
                    if sec and dist:
                        key = (r.get("place"), dist, (r.get("baba") or "")[:1])
                        buckets.setdefault(key, []).append(sec / dist)
    base = {k: st.median(v) for k, v in buckets.items() if len(v) >= 8}

    def level_of(r):
        """前走レベル = 基準より何秒/m 速いか(正=速い=高レベル) ×1000 で見やすく。"""
        sec, dist = t2s(r.get("time")), r.get("distance")
        if not sec or not dist:
            return None
        key = (r.get("place"), dist, (r.get("baba") or "")[:1])
        b = base.get(key)
        if b is None:
            return None
        return (b - sec / dist) * 1000   # +なら基準より速い

    # Pass2: 人気薄の前走レベル vs 3着内
    seg_data = {"train": ([], []), "test": ([], [])}
    quart = []
    for fp in FILES:
        for line in open(fp, encoding="utf-8"):
            if not line.strip():
                continue
            rec = json.loads(line)
            seg = "train" if rec["date"] < CUTOFF else "test"
            for h in rec["horses"]:
                pop, fpos = h.get("exp_pop"), h.get("finish_pos")
                rr = h.get("recent_runs", [])
                if pop is None or pop < POP_MIN or fpos is None or not rr:
                    continue
                lv = level_of(rr[0])     # 前走(最新)のレベル
                if lv is None:
                    continue
                hit = 1 if fpos <= 3 else 0
                seg_data[seg][0].append(lv)
                seg_data[seg][1].append(hit)
                quart.append((lv, hit))

    print(f"人気薄(>={POP_MIN}番人気) 前走レースレベル(時計) vs 3着内 / 2期間検定\n")
    rtr, ntr = pbcorr(*seg_data["train"])
    rte, nte = pbcorr(*seg_data["test"])
    print(f"前走レベル(速さ): 学習 r={rtr:+.3f}(n={ntr}) / 検証 r={rte:+.3f}(n={nte})")
    if (rtr > 0) == (rte > 0) and min(abs(rtr), abs(rte)) >= 0.03:
        print("  → ★両期間で同符号・有意。前走の決着が速い人気薄は3着内に来やすい")
    else:
        print("  → 弱い/不安定")

    quart.sort()
    n = len(quart)
    print(f"\n前走レベルの四分位別 3着内率 (n={n}):")
    for i, lab in enumerate(["Q1(最も遅い=低レベル)", "Q2", "Q3", "Q4(最も速い=高レベル)"]):
        s = quart[i * n // 4:(i + 1) * n // 4]
        if s:
            rate = 100 * sum(h for _, h in s) / len(s)
            print(f"  {lab:<22} レベル{s[0][0]:+.0f}〜{s[-1][0]:+.0f}  3着内 {rate:.1f}% (n={len(s)})")


if __name__ == "__main__":
    main()
