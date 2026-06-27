"""コーナー上り時計(800-200m)など、コーナー立ち回りに特化したラップ指標を出す。

普通の上り3F(残り600-0m)はゴール前の失速を含むため、立ち回りの上手さが薄まる。
そこで残り800-200mの3ハロン=「コーナー上り3F」で、コーナーを抜ける速さだけを見る。

指標(ラップ列 L = 全ハロン・スタート→ゴール順):
  上り3F          = L[-3]+L[-2]+L[-1]            (残り600-0m, 従来)
  コーナー上り3F  = L[-4]+L[-3]+L[-2]            (残り800-200m, ゴール前200m除く)
  CA(加速スパイク)= (L[-4]+L[-2])/2 - L[-3]      (コーナー出口1Fが前後より何秒速いか. 大=立ち回り勝負)
  コーナー33ラップ= (L[-7..-5]の和) - コーナー上り3F (残り1400-800 − 800-200. 7F以上)

入力: --laps "12.6-11.8-..."(手入力) または --race-id <12桁>(netkeiba中央から取得)。

実行例:
    python3 scripts/corner_lap.py --laps 12.6-11.8-13.5-12.8-13.1-13.5-13.7-12.5-13.8-13.3
    python3 scripts/corner_lap.py --race-id 202602010411
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def metrics(L):
    """ラップ列からコーナー系指標を算出。Lはスタート→ゴール順の全ハロン。"""
    n = len(L)
    out = {"n_furlong": n, "dist_m": n * 200}
    if n >= 3:
        out["上り3F"] = round(sum(L[-3:]), 2)
    if n >= 4:
        out["コーナー上り3F"] = round(sum(L[-4:-1]), 2)            # 残り800-200m
        out["最終200m"] = L[-1]
        out["CA加速スパイク"] = round((L[-4] + L[-2]) / 2 - L[-3], 2)
    if n >= 7:
        out["コーナー33ラップ"] = round(sum(L[-7:-4]) - sum(L[-4:-1]), 2)
    return out


def show(label, L):
    m = metrics(L)
    print(f"\n=== {label} ({m['dist_m']}m / {m['n_furlong']}F) ===")
    print("  ラップ: " + "-".join(f"{x}" for x in L))
    if "コーナー上り3F" in m:
        print(f"  上り3F(残り600-0m)        : {m['上り3F']}")
        print(f"  コーナー上り3F(残り800-200): {m['コーナー上り3F']}  ← 立ち回り評価の本指標")
        print(f"  最終200m(ゴール前)         : {m['最終200m']}")
        diff = round(m["コーナー上り3F"] - m["上り3F"], 2)
        print(f"  差(コーナー上り − 上り)    : {diff:+.2f}"
              f"  ({'コーナーの方が速い=立ち回り型' if diff < 0 else '直線まで脚が続く=持続/瞬発型'})")
        ca = m["CA加速スパイク"]
        print(f"  CA加速スパイク             : {ca:+.2f}"
              f"  ({'大=コーナーで一気に動いて直線失速=立ち回り勝負' if ca >= 0.8 else '小=直線勝負寄り'})")
    if "コーナー33ラップ" in m:
        print(f"  コーナー33ラップ           : {m['コーナー33ラップ']:+.2f}")


def main():
    ap = argparse.ArgumentParser(description="コーナー上り時計など立ち回り特化ラップ指標")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--laps", help="ハロンラップを - 区切りで(例 12.6-11.8-...)")
    g.add_argument("--race-id", help="netkeiba中央の12桁レースID")
    args = ap.parse_args()

    if args.laps:
        L = [float(x) for x in re.split(r"[-\s]+", args.laps.strip()) if x]
        show("手入力ラップ", L)
    else:
        from nankeiba.scraping import netkeiba as N
        import lap33 as L33
        client = N.make_client(use_cache=True)
        h = L33.get_result_html(client, args.race_id)
        if not h:
            raise SystemExit("ラップが取得できません(直近はdb未反映の場合あり)")
        L = N.parse_laps(h)
        show(f"{N.place_of(args.race_id)} {int(args.race_id[10:12])}R", L)


if __name__ == "__main__":
    main()
