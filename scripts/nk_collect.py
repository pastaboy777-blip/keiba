"""中央(netkeiba)の1日の結果を取得・分析し、JSONLでデータストックする。

直近はライブ結果(race.netkeiba)から着順/馬番/人気/上り/通過(脚質)を取得・保存。
ラップ(失速幅/33ラップ)はdb反映後に別途追加可。場別に勝ち脚質バイアスも集計表示。

保存: data/samples/nk_central_<date>.jsonl (1行=1レース)

実行例:
    python3 scripts/nk_collect.py --date 2026-06-28
    python3 scripts/nk_collect.py --date 2026-06-28 --place 函館
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from nankeiba.scraping import netkeiba as N
import pace_day as PD


def surface_dist_baba(html):
    sf = di = ba = None
    m = re.search(r"(芝|ダ)\s*(?:右|左|直)?\s*(\d{3,4})m", html)
    if m:
        sf, di = m.group(1), int(m.group(2))
    bm = re.search(r"(良|稍重|重|不良)", html)
    if bm:
        ba = bm.group(1)
    return sf, di, ba


def style_from_pos(last_pos, field):
    if not last_pos or not field or field < 2:
        return "?"
    r = (last_pos - 1) / (field - 1)
    return "逃げ" if r <= 0.15 else "先行" if r <= 0.4 else "中団" if r <= 0.7 else "後方"


def main():
    ap = argparse.ArgumentParser(description="中央結果の収集・分析・ストック")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--place", default=None, help="場で絞る(既定=全場)")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    ymd = args.date.replace("-", "")
    client = N.make_client(use_cache=not args.no_cache)
    rids = [r for r in N.race_ids_for_date(client, ymd)
            if not args.place or N.place_of(r) == args.place]

    out_path = ROOT / "data" / "samples" / f"nk_central_{args.date}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    from collections import defaultdict
    styles = defaultdict(lambda: defaultdict(int))
    n_saved = 0
    with out_path.open("w", encoding="utf-8") as f:
        for rid in rids:
            try:
                html = client.get(N.RESULT_LIVE_URL.format(race_id=rid))
                res = N.parse_result_live(html)
            except Exception:  # noqa: BLE001
                continue
            if not res:
                continue
            order = N.last_corner_order_live(html)
            sf, di, ba = surface_dist_baba(html)
            field = len(res)
            for r in res:
                lp = (order.index(r["umaban"]) + 1) if r["umaban"] in order else None
                r["style"] = style_from_pos(lp, field)
            win = res[0]
            pl = N.place_of(rid)
            styles[pl][win["style"]] += 1
            rec = {"race_id": rid, "date": args.date, "place": pl,
                   "race_no": int(rid[10:12]), "surface": sf, "distance": di,
                   "baba": ba, "field_size": field, "rows": res}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_saved += 1

    print(f"\n保存: {out_path}  ({n_saved}レース)")
    print("\n=== 場別 勝ち脚質バイアス ===")
    for pl, sc in styles.items():
        tot = sum(sc.values())
        fronts = sc.get("逃げ", 0) + sc.get("先行", 0)
        print(f"  {pl}: 逃げ{sc.get('逃げ',0)}・先行{sc.get('先行',0)}・"
              f"中団{sc.get('中団',0)}・後方{sc.get('後方',0)} "
              f"→ 前(逃+先) {fronts}/{tot} = {100*fronts/tot:.0f}%" if tot else f"  {pl}: データなし")


if __name__ == "__main__":
    main()
