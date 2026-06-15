"""v2ランキングのロバスト性検証: 場別・人気帯別に本線3着内率を現行と比較する。

検証期間(CUTOFF以降)で、各レースの最上位1頭(本線)が3着内に来た率を
現行『穴度』とv2で比較。場をまたいで効くか、人気帯で効くかを確認する。

結果(2026 2-6月): 川崎12.5→22.2 / 大井11.6→21.7 / 船橋14.8→26.9 で有効、
浦和のみ例外(n小)。人気6-8/9-11/12-の全帯でv2上位が改善。

実行: python3 scripts/validate_v2_robustness.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import backtest_wet as bw
import predict_nankan as pn
import improve_zubu as iz

CUTOFF = iz.CUTOFF


def main() -> None:
    races = bw.load_races()
    jt = pn.jockey_top3_from_samples(bw.FILES)
    rows = iz.build_rows(races, jt)
    meta = {r["race_id"]: (r["place"], r["date"]) for r in races}
    train = [r for r in rows if r[1] < CUTOFF]
    test = [r for r in rows if r[1] >= CUTOFF]
    stats = iz.standardize(train, ["jockey", "ability", "senkou", "agari", "pop"])
    v2 = lambda r: iz.score(r, stats, iz.WEIGHTS_A)
    cur = lambda r: (r[3]["cur"] if r[3]["cur"] is not None else -9)

    def top1(rowset, fn):
        by = {}
        for r in rowset:
            by.setdefault(r[0], []).append(r)
        nh = hb = 0
        for _rid, rs in by.items():
            rs = sorted(rs, key=lambda x: -fn(x))
            nh += 1
            hb += rs[0][4]
        return (100 * hb / nh if nh else 0, nh)

    print(f"検証期間({CUTOFF}以降)・本線(最上位1頭)3着内率  現行→v2\n [場別]")
    for pl in ["川崎", "大井", "船橋", "浦和"]:
        sub = [r for r in test if meta[r[0]][0] == pl]
        (c, _), (v, n) = top1(sub, cur), top1(sub, v2)
        flag = "" if v >= c else "  ←効かず"
        print(f"   {pl}: {c:.1f}% → {v:.1f}%  (n={n}R){flag}")

    print(" [人気帯別(全場)・v2上位20%の3着内率]")
    for lab, lo, hi in [("6-8人気", 6, 8), ("9-11人気", 9, 11), ("12人気-", 12, 99)]:
        sub = [r for r in test if lo <= r[3]["pop"] <= hi]
        base = sum(x[4] for x in sub) / len(sub) if sub else 0
        vs = sorted(sub, key=lambda x: -v2(x))[:max(1, len(sub) // 5)]
        tq = sum(x[4] for x in vs) / len(vs) if vs else 0
        print(f"   {lab}: ベース{base*100:.1f}% → v2上位20%が{tq*100:.1f}% (n={len(sub)})")


if __name__ == "__main__":
    main()
