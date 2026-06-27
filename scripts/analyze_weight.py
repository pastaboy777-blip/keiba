"""近走の馬体重増減と『人気薄の3着内』の関係を、学習/検証2期間で検定する。

過学習を避けるため、各馬体重特徴と『3着内か(1/0)』の点双列相関を学習期間・検証期間で
別々に計算し、両期間で同符号・同程度に出る信号だけを"効く"と判断する。
対象は人気薄(exp_pop>=pop_min)。南関の充実JSONL(recent_runs.horse_weight)を使う。

実行: python3 scripts/analyze_weight.py
"""

from __future__ import annotations

import glob
import json

FILES = sorted(glob.glob("data/samples/nankan_2026-0*.jsonl"))
CUTOFF = "2026-05-01"
POP_MIN = 6


def pbcorr(xs, ys):
    n = len(xs)
    if n < 30:
        return None, n
    mx, my = sum(xs) / n, sum(ys) / n
    sx = (sum((x - mx) ** 2 for x in xs) / n) ** 0.5
    sy = (sum((y - my) ** 2 for y in ys) / n) ** 0.5
    if sx == 0 or sy == 0:
        return None, n
    r = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / (n * sx * sy)
    return r, n


def features(weights):
    """新しい順の体重リスト→特徴量。2点未満は None。"""
    w = [x for x in weights if x]
    if len(w) < 2:
        return None
    import statistics as st
    return {
        "直近増減(前走比)": w[0] - w[1],
        "近走トレンド(最古→直近)": w[0] - w[-1],
        "体重ボラ(std)": st.pstdev(w) if len(w) >= 3 else abs(w[0] - w[1]),
        "絶対体重(平均)": sum(w) / len(w),
    }


def main():
    keys = ["直近増減(前走比)", "近走トレンド(最古→直近)", "体重ボラ(std)", "絶対体重(平均)"]
    bins = {seg: {k: ([], []) for k in keys} for seg in ("train", "test")}
    # 四分位3着内率用に直近増減を貯める
    quart = {"x": [], "hit": []}
    for fp in FILES:
        for line in open(fp, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            seg = "train" if rec["date"] < CUTOFF else "test"
            for h in rec["horses"]:
                pop, fpos = h.get("exp_pop"), h.get("finish_pos")
                if pop is None or pop < POP_MIN or fpos is None:
                    continue
                ws = [r.get("horse_weight") for r in h.get("recent_runs", [])]
                f = features(ws)
                if not f:
                    continue
                hit = 1 if fpos <= 3 else 0
                for k in keys:
                    bins[seg][k][0].append(f[k])
                    bins[seg][k][1].append(hit)
                quart["x"].append(f["直近増減(前走比)"])
                quart["hit"].append(hit)

    print(f"人気薄(>={POP_MIN}番人気)の3着内 vs 近走馬体重特徴 の点双列相関")
    print(f"(学習={CUTOFF}より前 / 検証=以降。両期間で同符号・有意なら『効く』)\n")
    print(f"{'特徴量':<22}{'学習r(n)':>16}{'検証r(n)':>16}  判定")
    for k in keys:
        rtr, ntr = pbcorr(*bins["train"][k])
        rte, nte = pbcorr(*bins["test"][k])
        def fmt(r, n):
            return f"{r:+.3f}({n})" if r is not None else f"—({n})"
        verdict = "—"
        if rtr is not None and rte is not None:
            if (rtr > 0) == (rte > 0) and min(abs(rtr), abs(rte)) >= 0.03:
                verdict = "★両期間で同符号(効く可能性)"
            elif (rtr > 0) != (rte > 0):
                verdict = "符号反転=ノイズ"
            else:
                verdict = "弱い"
        print(f"{k:<22}{fmt(rtr, ntr):>16}{fmt(rte, nte):>16}  {verdict}")

    # 直近増減の四分位ごと3着内率
    xs = sorted(zip(quart["x"], quart["hit"]))
    n = len(xs)
    print(f"\n直近増減(前走比)の四分位別 3着内率 (n={n}):")
    for i, lab in enumerate(["Q1(最も減)", "Q2", "Q3", "Q4(最も増)"]):
        seg = xs[i * n // 4:(i + 1) * n // 4]
        if seg:
            lo, hi = seg[0][0], seg[-1][0]
            rate = 100 * sum(h for _, h in seg) / len(seg)
            print(f"  {lab:<10} 増減{lo:+d}〜{hi:+d}kg  3着内 {rate:.1f}% (n={len(seg)})")


if __name__ == "__main__":
    main()
