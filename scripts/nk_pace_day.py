"""netkeiba(中央/JRA)の結果から、ある開催日×場の展開(トラックバイアス)を読む。

地方の pace_day.py の中央版。中央は全レースにラップ(全ハロン)があるので
前半3F/上がり3Fのペース判定が正確。各馬の『通過』列(最終コーナー位置)で
勝ち脚質を判定し、当日の前残り/差し傾向をまとめる。

実行例:
    python3 scripts/nk_pace_day.py --date 2026-06-21 --place 函館
    python3 scripts/nk_pace_day.py --date 2026-06-21          # 全場
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from nankeiba.scraping import netkeiba as N
import pace_day as pd   # pace_label / style 判定を流用


def style_from_pos(last_pos, field):
    """最終コーナー位置/頭数から脚質を判定。"""
    if not last_pos or not field or field < 2:
        return "?"
    r = (last_pos - 1) / (field - 1)
    if r <= 0.15:
        return "逃げ"
    if r <= 0.4:
        return "先行"
    if r <= 0.7:
        return "中団"
    return "後方"


def main() -> None:
    ap = argparse.ArgumentParser(description="netkeiba中央 1日 展開読み")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--place", default=None, help="場で絞る(例: 東京/函館/阪神)")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    ymd = args.date.replace("-", "")
    client = N.make_client(use_cache=not args.no_cache)
    rids = N.race_ids_for_date(client, ymd)
    if args.place:
        rids = [r for r in rids if N.place_of(r) == args.place]
    if not rids:
        raise SystemExit(f"{args.date} {args.place or ''} のレースが見つかりません。")

    styles = {"逃げ": 0, "先行": 0, "中団": 0, "後方": 0, "?": 0}
    pace_counts = {"前傾": 0, "後傾": 0, "平均": 0}
    print(f"\n=== {args.date} {args.place or '中央全場'} 展開読み(netkeiba) ===")
    print(f"{'場':>4}{'R':>3} {'勝T':>8} {'上3F':>5} {'脚質':<5}{'前3F':>5} {'ラップ展開':<16}人気/勝ち馬")
    for rid in rids:
        try:
            html = client.get(N.RESULT_URL.format(race_id=rid))
            res = N.parse_result(html)
        except Exception:  # noqa: BLE001
            continue
        if not res:
            continue
        win = res[0]
        field = len(res)
        st = style_from_pos(win["last_corner_pos"], field)
        styles[st] = styles.get(st, 0) + 1
        laps = N.parse_laps(html)
        if len(laps) >= 6:
            f3, l3 = sum(laps[:3]), sum(laps[-3:])
            lab = pd.pace_label(f3, l3)
            f3s = f"{f3:.1f}"
        else:
            lab, f3s = "—", "—"
        if "前傾" in lab:
            pace_counts["前傾"] += 1
        elif "後傾" in lab:
            pace_counts["後傾"] += 1
        elif lab == "平均":
            pace_counts["平均"] += 1
        ag = f"{win['agari']:.1f}" if win["agari"] else "—"
        print(f"{N.place_of(rid):>4}{int(rid[10:12]):>3} {(win['time'] or '—'):>8} "
              f"{ag:>5} {st:<5}{f3s:>5} {lab:<16}{win['popularity']}番人気 {win['horse']}")

    classified = sum(v for k, v in styles.items() if k != "?")
    print(f"\n--- サマリー({sum(styles.values())}R) ---")
    if classified == 0:
        print("勝ち脚質: 判定不可")
        return
    fronts = styles["逃げ"] + styles["先行"]
    print(f"勝ち脚質: 逃げ{styles['逃げ']}・先行{styles['先行']}・中団{styles['中団']}・後方{styles['後方']}")
    print(f"ラップ形状: 前傾{pace_counts['前傾']}・平均{pace_counts['平均']}・後傾{pace_counts['後傾']}")
    ratio = fronts / classified
    if ratio >= 0.6:
        v = "★前残り傾向→前で運べる馬を厚く"
    elif ratio <= 0.35:
        v = "★差し決まる傾向→差し・展開崩れ狙い"
    else:
        v = "フラット→展開・枠で個別判断"
    print(f"前(逃げ+先行)勝率 {fronts}/{classified} = {ratio*100:.0f}%  {v}")


if __name__ == "__main__":
    main()
