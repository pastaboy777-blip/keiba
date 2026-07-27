"""場×距離ごとの基準ペース par [s/F] を、キャッシュ済みの結果ページから測り直す。

**2種類の par を別々に作る。混ぜてはいけない。**

  data/par_pace.json … **全出走馬**の走破タイムの中央値。
      `core/shock.py` 用。速度ショックは「その馬自身の前走タイム」と比べるので、
      基準も着順を問わない全馬ぶんでないと釣り合わない。
  data/par_win.json  … **勝ち馬**の走破タイムの中央値。
      `core/track_bias.py` 用。当日の馬場差は勝ちタイムから測るので、
      基準も勝ち馬でないと釣り合わない。

⚠️ この2つを取り違えると、**常に約 -0.19 s/F の下駄**を履く。実際 2026-07-27 の
川崎で、勝ちタイムを全馬 par にぶつけたせいで「当日の馬場差 -0.29 = 高速馬場」と
誤判定し、⚠️見かけ倒しの割引を緩めすぎ、4Rで本来出ないはずの🚀を2頭に付けていた。
正しくは -0.10（ほぼ標準）だった。

⚠️ **par に無い距離は丸ごと判定不能になる**。同じ日、900m の par が未登録だった
せいで 3R が馬場差の実測から落ち、9R・11R の速度ショックが全頭 None になっていた。
開催場に新しい距離が増えたら必ず流し直すこと。

使い方:
    python3 scripts/build_par_pace.py --dry-run     # 差分だけ表示
    python3 scripts/build_par_pace.py --fill-only   # 未登録の場×距離だけ追記（安全）
    python3 scripts/build_par_pace.py               # 全面的に上書き
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import defaultdict
from statistics import median

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import rakuten as rk   # noqa: E402

CACHE = "data/cache/rakuten"
OUT_FIELD = "data/par_pace.json"
OUT_WIN = "data/par_win.json"
MIN_N = 8          # これ未満のサンプル数の場×距離は採用しない


def collect(cache_dir: str = CACHE) -> tuple[dict[str, list[float]],
                                              dict[str, list[float]]]:
    """({"場|距離": [全馬の s/F]}, {"場|距離": [勝ち馬の s/F]}) を返す。"""
    field: dict[str, list[float]] = defaultdict(list)
    win: dict[str, list[float]] = defaultdict(list)
    for pf in sorted(glob.glob(os.path.join(
            cache_dir, "race_performance_list_RACEID_*.html"))):
        rid = pf.rsplit("_", 1)[-1].removesuffix(".html")
        cf = os.path.join(cache_dir, f"race_card_list_RACEID_{rid}.html")
        if not os.path.exists(cf):
            continue
        try:
            hd = rk.parse_card(open(cf, encoding="utf-8").read())["header"]
            res = rk.parse_result(open(pf, encoding="utf-8").read())
        except Exception:                        # noqa: BLE001
            continue
        place, dist = hd.get("place"), hd.get("distance")
        if not place or not dist or not res:
            continue
        ts = [r["time_sec"] for r in res if r.get("time_sec")]
        if not ts:
            continue
        key = f"{place}|{dist}"
        f = dist / 200.0
        field[key] += [round(t / f, 3) for t in ts]
        win[key].append(round(ts[0] / f, 3))
    return field, win


def build(samples: dict[str, list[float]], min_n: int = MIN_N) -> dict[str, float]:
    return {k: round(median(v), 3) for k, v in sorted(samples.items())
            if len(v) >= min_n}


def _write(path: str, table: dict[str, float], samples: dict[str, list[float]],
           *, label: str, fill_only: bool, dry_run: bool) -> None:
    old = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    if fill_only:
        table = {**table, **old}          # 既存値を優先し、欠けている鍵だけ足す
    added = sorted(set(table) - set(old))
    dropped = sorted(set(old) - set(table))
    moved = sorted(k for k in set(table) & set(old)
                   if abs(table[k] - old[k]) >= 0.05)
    print(f"\n=== {label} ({path}) ===")
    print(f"{len(table)}件  新規{len(added)} 消滅{len(dropped)} 変動{len(moved)}")
    for k in added:
        print(f"  + {k}: {table[k]}  (n={len(samples[k])})")
    for k in dropped:
        print(f"  - {k}: {old[k]}  (n={len(samples.get(k, []))})")
    for k in moved:
        print(f"  ~ {k}: {old[k]} → {table[k]}  (n={len(samples[k])})")
    if dry_run:
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(table, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    print(f"  → 書き出しました")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fill-only", action="store_true",
                    help="既存の値は触らず、未登録の場×距離だけ追記する")
    ap.add_argument("--min-n", type=int, default=MIN_N)
    args = ap.parse_args()

    field, win = collect()
    print(f"実測レース {sum(len(v) for v in win.values())}  "
          f"述べ出走 {sum(len(v) for v in field.values())}")
    _write(OUT_FIELD, build(field, args.min_n), field, label="全出走馬par(shock用)",
           fill_only=args.fill_only, dry_run=args.dry_run)
    _write(OUT_WIN, build(win, args.min_n), win, label="勝ち馬par(track_bias用)",
           fill_only=args.fill_only, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
