"""ある日・ある場のズブ穴v2ピックを、出馬表からライブ算出して複勝/ワイドROIで採点する。

zubu_roi.py は事前収集の enriched JSONL を使うが、本ツールは出馬表ページから直接
v2ランキングを作る(=zubu_table と同じ計算)ので、enriched が無い地方場でも検証できる。
各レースで人気薄(exp_pop>=pop_min)を v2 で並べ、確定結果＋複勝/ワイドオッズで
「v2第1位/上位3頭の複勝」「上位K頭のワイドBOX」を買った時の回収率を出す。

複勝/ワイドはレンジ下限採用=保守的ROI。結果確定直後は --no-cache 推奨。

実行例:
    python3 scripts/verify_roi_day.py --date 2026-06-25 --place 笠松 --from 1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from nankeiba.scraping import enrich as E
from nankeiba.scraping import odds as O

import predict_nankan as pn

STAKE = 100


def main() -> None:
    ap = argparse.ArgumentParser(description="1日分 ズブ穴v2 複勝/ワイド ライブROI検証")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--place", choices=list(ALL_CODES), required=True)
    ap.add_argument("--baba", choices=list(pn.BABA_FULL), default="良")
    ap.add_argument("--from", dest="from_r", type=int, default=1)
    ap.add_argument("--to", dest="to_r", type=int, default=12)
    ap.add_argument("--pop-min", type=int, default=6)
    ap.add_argument("--min-v2", type=float, default=None,
                    help="本命v2がこの値未満のレースは見送る(確信度フィルタ)")
    ap.add_argument("--no-cache", action="store_true", help="キャッシュを使わず再取得")
    ap.add_argument("--samples", nargs="*", default=[
        f"data/samples/nankan_2026-{m}.jsonl" for m in ("02", "03", "04", "05", "06")])
    args = ap.parse_args()

    ymd = args.date.replace("-", "")
    client = PoliteClient(use_cache=not args.no_cache)
    idx = client.get(pn.CARD_URL.format(race_id=day_index_race_id(ymd, args.place)))
    races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[args.place]))
    if not races:
        raise SystemExit(f"{args.date} {args.place} のレースが見つかりません。")

    jrates = pn.jockey_top3_from_samples(args.samples)
    stats = pn.zubu_v2_stats_from_samples(args.samples, pop_min=args.pop_min)

    acc = {k: [0, 0, 0, 0] for k in
           ("複勝_本命", "複勝_上位3", "ワイドBOX_3", "ベース_穴複勝全")}
    rows_out = []
    n = 0
    for rno in sorted(races):
        if rno < args.from_r or rno > args.to_r:
            continue
        rid = races[rno]
        card = P.parse_card_page(client.get(pn.CARD_URL.format(race_id=rid)), rid)
        res = P.parse_result_page(client.get(pn.RESULT_URL.format(race_id=rid)), rid)
        top3 = {r.umaban for r in res.rows if r.finish_pos and r.finish_pos <= 3}
        if not top3:
            continue
        try:
            place_o = O.parse_tanfuku_html(client.get(O.odds_url(rid, "tanfuku")))["place"]
            wide_o = O.parse_wide_html(client.get(O.odds_url(rid, "wide")))
        except Exception:  # noqa: BLE001
            place_o, wide_o = {}, {}

        jockeys = E.jockey_stats_from_card(card)
        picks = pn.zubu_ana_picks(card, jockeys, target_time=None, jockey_rates=jrates,
                                  pop_min=args.pop_min, bias="front", baba=args.baba,
                                  v2_stats=stats, v2_weights=pn.ZUBU_V2_WEIGHTS)
        picks = [(e.umaban, sc) for e, sc, _t in picks if e.umaban is not None]
        if not picks:
            continue
        if args.min_v2 is not None and picks[0][1] < args.min_v2:
            continue
        n += 1

        um1, v1 = picks[0]
        hit1 = um1 in top3
        po1 = place_o.get(um1)
        if po1:
            b = acc["複勝_本命"]
            b[0] += STAKE; b[3] += 1
            if hit1:
                b[1] += po1 * STAKE; b[2] += 1
        rows_out.append((rno, um1, v1, hit1, int(po1 * STAKE) if (hit1 and po1) else None))

        b = acc["複勝_上位3"]; bought = False
        for um, _v in picks[:3]:
            if um not in place_o:
                continue
            b[0] += STAKE; bought = True
            if um in top3:
                b[1] += place_o[um] * STAKE; b[2] += 1
        if bought:
            b[3] += 1

        ums = [um for um, _ in picks[:3]]
        b = acc["ワイドBOX_3"]; rb = False
        for i in range(len(ums)):
            for j in range(i + 1, len(ums)):
                pair = tuple(sorted((ums[i], ums[j])))
                if pair not in wide_o:
                    continue
                b[0] += STAKE; rb = True
                if pair[0] in top3 and pair[1] in top3:
                    b[1] += wide_o[pair] * STAKE; b[2] += 1
        if rb:
            b[3] += 1

        b = acc["ベース_穴複勝全"]; ab = False
        for um, _v in picks:
            if um not in place_o:
                continue
            b[0] += STAKE; ab = True
            if um in top3:
                b[1] += place_o[um] * STAKE; b[2] += 1
        if ab:
            b[3] += 1

    print(f"\n=== {args.date} {args.place} ズブ穴v2 ライブROI検証 "
          f"({args.from_r}〜{args.to_r}R・人気薄>={args.pop_min}) ===")
    print("レース別 v2第1位(本命)の複勝:")
    for rno, um, v1, hit, pay in rows_out:
        tag = f"的中 複勝{pay}円" if hit else "外れ"
        print(f"  {rno:>2}R  ◇{um:<2} v2{v1:+.2f}  {tag}")
    print(f"\n検証 {n}R / 払戻はレンジ下限=保守的")
    print(f"{'戦略':<14}{'対象R':>6}{'投資':>8}{'払戻':>9}{'的中':>6}{'回収率':>8}")
    for name, (inv, ret, hit, nr) in acc.items():
        roi = (ret / inv * 100) if inv else 0.0
        flag = " ★+" if roi >= 100 else ""
        print(f"{name:<14}{nr:>6}{inv:>8}{int(ret):>9}{hit:>6}{roi:>7.1f}%{flag}")


if __name__ == "__main__":
    main()
