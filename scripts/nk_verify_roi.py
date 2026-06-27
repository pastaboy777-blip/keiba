"""netkeiba中央: 脚質ベースのズブ穴(人気薄)を複勝/ワイドROIで日次検証する。

各レースで shutuba_past から脚質を出し、結果ページの人気で人気薄(>=pop_min)に絞り、
バイアス(差し/前)で並べた本命/上位3の複勝、上位3のワイドBOXを買った時の回収率を、
確定結果＋払戻(複勝/ワイド)で採点する。地方の verify_roi_day の中央版。

実行例:
    python3 scripts/nk_verify_roi.py --date 2026-06-21 --place 函館 --bias sashi
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

STAKE = 100


def main() -> None:
    ap = argparse.ArgumentParser(description="netkeiba中央 ズブ穴 複勝/ワイドROI検証")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--place", required=True, help="場(東京/函館/小倉 等)")
    ap.add_argument("--from", dest="from_r", type=int, default=1)
    ap.add_argument("--to", dest="to_r", type=int, default=12)
    ap.add_argument("--pop-min", type=int, default=6, help="人気薄しきい値(既定6)")
    ap.add_argument("--bias", choices=["front", "sashi"], default="sashi")
    ap.add_argument("--draw", choices=["all", "inner"], default="all")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    client = N.make_client(use_cache=not args.no_cache)
    rids = [r for r in N.race_ids_for_date(client, args.date.replace("-", ""))
            if N.place_of(r) == args.place and args.from_r <= int(r[10:12]) <= args.to_r]
    if not rids:
        raise SystemExit("対象レースなし")

    acc = {k: [0, 0, 0, 0] for k in ("複勝_本命", "複勝_上位3", "ワイドBOX3", "ベース_穴複勝全")}
    rows = []
    n = 0
    for rid in rids:
        past = nk_zubu.parse_past_table(client.get(nk_zubu.PAST_URL.format(race_id=rid)))
        res = N.parse_result(client.get(N.RESULT_URL.format(race_id=rid)))
        pay = N.parse_payoffs(client.get(N.RESULT_URL.format(race_id=rid)))
        if not past or not res:
            continue
        pop = {r["umaban"]: r["popularity"] for r in res if r["popularity"]}
        top3 = {r["umaban"] for r in res if r["finish_pos"] and r["finish_pos"] <= 3}
        place_o, wide_o = pay["place"], pay["wide"]
        field = len(past)
        thr = round(field * 0.6)

        # 人気薄に絞り、バイアスで並べる
        cands = [h for h in past if pop.get(h["umaban"], 99) >= args.pop_min]
        if args.draw == "inner":
            cands = [h for h in cands if h["umaban"] <= thr]
        cands.sort(key=lambda h: h["senkou"], reverse=(args.bias == "front"))
        if not cands:
            continue
        n += 1
        ums = [h["umaban"] for h in cands]

        # 複勝/ワイド払戻は3着内の組しか無いので「賭けは常に成立、的中時のみ払戻」。
        um1 = ums[0]
        hit1 = um1 in top3
        b = acc["複勝_本命"]; b[0] += STAKE; b[3] += 1
        if hit1:
            b[1] += place_o.get(um1, 0); b[2] += 1
        rows.append((N.place_of(rid), int(rid[10:12]), um1, cands[0]["senkou"],
                     hit1, place_o.get(um1) if hit1 else None))

        b = acc["複勝_上位3"]; b[3] += 1
        for um in ums[:3]:
            b[0] += STAKE
            if um in top3:
                b[1] += place_o.get(um, 0); b[2] += 1

        b = acc["ワイドBOX3"]; b[3] += 1
        top = ums[:3]
        for i in range(len(top)):
            for j in range(i + 1, len(top)):
                pr = tuple(sorted((top[i], top[j])))
                b[0] += STAKE
                if pr[0] in top3 and pr[1] in top3:
                    b[1] += wide_o.get(pr, 0); b[2] += 1

        b = acc["ベース_穴複勝全"]; b[3] += 1
        for um in ums:
            b[0] += STAKE
            if um in top3:
                b[1] += place_o.get(um, 0); b[2] += 1

    tag = "差し優先" if args.bias == "sashi" else "前残り優先"
    dtag = "・内〜中枠" if args.draw == "inner" else ""
    print(f"\n=== {args.date} {args.place} 中央ズブ穴ROI検証({tag}{dtag}・人気薄>={args.pop_min}) ===")
    print("レース別 本命(人気薄・脚質1位)の複勝:")
    for pl, r, um, sen, hit, payv in rows:
        print(f"  {r:>2}R ◇{um:<2} 脚質{sen:+.2f}  {'的中 複勝'+str(payv)+'円' if hit else '外れ'}")
    print(f"\n検証 {n}R")
    print(f"{'戦略':<14}{'対象R':>6}{'投資':>8}{'払戻':>9}{'的中':>6}{'回収率':>8}")
    for name, (inv, ret, hit, nr) in acc.items():
        roi = (ret / inv * 100) if inv else 0.0
        print(f"{name:<14}{nr:>6}{inv:>8}{int(ret):>9}{hit:>6}{roi:>7.1f}%{' ★+' if roi>=100 else ''}")


if __name__ == "__main__":
    main()
