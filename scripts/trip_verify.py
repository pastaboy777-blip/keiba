"""トリップ・エンジンの検証: 前走のトリップ(道中ロス)が今走の好走/妙味を生むか。

各馬について:
  - 前走のトリップ判定: 前走の失速幅(流れ)×前走の脚質(通過順) →
      流れ逆風=不利(+) / 流れ向き=恵まれ(−) / 中立
  - 今走(対象レース)の結果: 3着内か / 複勝払戻
前走トリップ別に 今走3着内率・複勝ROI を比較。
『前走不利』が『恵まれ』より今走で走る/儲かるなら、トリップ・エンジンは本物。
中央(db.netkeiba・前走ラップ要)向け。重いので対象を絞って実行。

実行例:
    python3 scripts/trip_verify.py --date 2026-06-21 --place 函館
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from nankeiba.scraping import netkeiba as N
import nk_zubu
import lap33 as L33
import flow_eval as FE


def trip_of(flow, style):
    favored = "後" if flow == "前崩壊" else "前" if flow == "前残り" else None
    if favored is None or style is None:
        return 0
    return 1 if style != favored else -1     # +1=不利 / -1=恵まれ


def main():
    ap = argparse.ArgumentParser(description="トリップ・エンジン検証")
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", default=None)
    ap.add_argument("--races", default=None, help="対象R(カンマ。既定=全R)")
    args = ap.parse_args()

    client = N.make_client(use_cache=True)
    rids = N.race_ids_for_date(client, args.date.replace("-", ""))
    if args.place:
        rids = [r for r in rids if N.place_of(r) == args.place]
    if args.races:
        tr = {int(x) for x in args.races.split(",")}
        rids = [r for r in rids if int(r[10:12]) in tr]

    lap_cache = {}

    def shissoku(prid):
        if prid not in lap_cache:
            h = L33.get_result_html(client, prid)
            laps = N.parse_laps(h) if h else []
            lap_cache[prid] = (round(laps[-2] - laps[-3], 2) if len(laps) >= 4 else None)
        return lap_cache[prid]

    # bucket -> [投資, 払戻, 的中, 頭数]
    acc = {"前走不利": [0, 0, 0, 0], "前走恵まれ": [0, 0, 0, 0], "前走中立": [0, 0, 0, 0]}
    n_runner = 0
    for rid in rids:
        try:
            res = N.parse_result(client.get(N.RESULT_URL.format(race_id=rid)))
            pay = N.parse_payoffs(client.get(N.RESULT_URL.format(race_id=rid)))
        except Exception:  # noqa: BLE001
            continue
        if not res:
            continue
        place_o = pay.get("place", {})
        det = FE.past_details(client.get(nk_zubu.PAST_URL.format(race_id=rid)))
        for r in res:
            um = r["umaban"]
            past = det.get(um) or []
            if not past:
                continue
            prid, pfin, pfield, plast = past[0]      # 前走
            if not (pfield and plast):
                continue
            sh = shissoku(prid)
            if sh is None:
                continue
            flow = "前崩壊" if sh >= 1.5 else "前残り" if sh <= 0.7 else "中間"
            pstyle = "前" if plast / pfield <= 0.4 else "後" if plast / pfield >= 0.6 else "中"
            t = trip_of(flow, pstyle)
            bucket = "前走不利" if t == 1 else "前走恵まれ" if t == -1 else "前走中立"
            b = acc[bucket]
            b[0] += 100
            b[3] += 1
            if r["finish_pos"] <= 3:
                b[2] += 1
                b[1] += place_o.get(um, 0)
            n_runner += 1

    print(f"\n=== トリップ検証 {args.date} {args.place or '全場'} (出走{n_runner}頭) ===")
    print(f"{'前走トリップ':<10}{'頭数':>5}{'3着内':>6}{'3着内率':>8}{'複勝ROI':>9}")
    for name, (inv, ret, hit, n) in acc.items():
        if not n:
            continue
        print(f"{name:<10}{n:>5}{hit:>6}{100*hit/n:>7.1f}%{(100*ret/inv if inv else 0):>8.1f}%")
    print("\n※『前走不利』が『前走恵まれ』より3着内率/ROIで上回れば、トリップ・エンジンは有効。")


if __name__ == "__main__":
    main()
