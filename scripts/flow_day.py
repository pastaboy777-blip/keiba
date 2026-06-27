"""前半レースの『失速幅』を測り、その日が差し有利(前崩壊)か前有利かを判定する。

戦略: 前半のレースでコーナー後の失速幅(コーナー出口の急加速→直線でどれだけ垂れたか)が
大きい=前崩壊=差し有利の流れの日。→ 後半は『差し馬から人気薄(ズブ穴)』を狙う。
失速幅 = 残り400-200m − 残り600-400m (楽天のハロンラップから)。南関(楽天)向け。

実行例:
    python3 scripts/flow_day.py --date 2026-06-26 --place 浦和 --through 6
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping import parser as P
import pace_day as PD


def metrics(laps):
    if len(laps) < 4:
        return None, None
    shissoku = round(laps[-2] - laps[-3], 2)            # 失速幅
    ca = round((laps[-4] + laps[-2]) / 2 - laps[-3], 2)  # CA加速スパイク
    return shissoku, ca


def main():
    ap = argparse.ArgumentParser(description="前半の失速幅で当日の流れ(差し/前)を判定")
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", choices=list(ALL_CODES), required=True)
    ap.add_argument("--through", type=int, default=6, help="前半=何R目まで見るか(既定6)")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    ymd = args.date.replace("-", "")
    c = PoliteClient(use_cache=not args.no_cache)
    races = dict(P.parse_race_links(
        c.get("https://keiba.rakuten.co.jp/race_card/list/RACEID/" + day_index_race_id(ymd, args.place)),
        date_yyyymmdd=ymd, jyo_code=ALL_CODES[args.place]))

    print(f"\n=== {args.date} {args.place} 当日の流れ判定(前半{args.through}Rの失速幅) ===")
    print(f"{'R':>3}{'距離':>7}{'失速幅':>7}{'CA':>7}  流れ")
    sh_vals = []
    for rno in sorted(races):
        if rno > args.through:
            break
        try:
            html = c.get("https://keiba.rakuten.co.jp/race_performance/list/RACEID/" + races[rno])
            res = P.parse_result_page(html, races[rno])
        except Exception:  # noqa: BLE001
            continue
        laps = PD.parse_laps(html)
        sh, ca = metrics(laps)
        if sh is None:
            print(f"{rno:>3}{('ダ'+str(res.distance)):>7}{'—':>7}{'—':>7}  (ラップ無)")
            continue
        sh_vals.append(sh)
        flow = "前崩壊(差し有利)" if sh >= 1.5 else "前残り(前有利)" if sh <= 0.7 else "中間"
        print(f"{rno:>3}{('ダ'+str(res.distance)):>7}{sh:>+7.2f}{ca:>+7.2f}  {flow}")

    if not sh_vals:
        print("\n判定不可(ラップ取得できず)")
        return
    avg = sum(sh_vals) / len(sh_vals)
    print(f"\n--- 前半{len(sh_vals)}R 平均失速幅 = {avg:+.2f} ---")
    if avg >= 1.5:
        print("★差し有利の日(前崩壊)→ 後半は『差し馬から人気薄(ズブ穴)』を狙う")
        print("  推奨: zubu_table/nk_zubu を --bias sashi --pop-min 6 で")
    elif avg <= 0.7:
        print("★前有利の日(前残り)→ 後半は『前で運べる人気薄』を狙う")
        print("  推奨: --bias front --pop-min 6")
    else:
        print("中間の日→ 脚質より枠・展開で個別判断")


if __name__ == "__main__":
    main()
