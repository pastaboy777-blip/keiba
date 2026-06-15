"""指定日・指定場のズブ穴ピックを、その日の実結果で検証する。

predict_nankan.py のズブ穴ロジック(zubu_ana_picks 他)をそのまま再利用し、
各レースの上位ピックが3着内に来たか、本線(穴度1位)の着順、
実際の三連複払戻を集計する。

実行例:
    python3 scripts/verify_zubu_day.py --date 2026-06-15 --place 川崎 --baba 重 --bias front
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import predict_nankan as pn  # ズブ穴ロジックを再利用
from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from nankeiba.scraping import enrich as E
from nankeiba.scraping import odds as O
from nankeiba.core import features as F

CARD_URL = pn.CARD_URL
RESULT_URL = pn.RESULT_URL


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", choices=list(NANKAN_CODES), required=True)
    ap.add_argument("--baba", choices=list(pn.BABA_FULL), default="重")
    ap.add_argument("--bias", choices=["front", "sashi", "auto"], default="front")
    ap.add_argument("--jw", type=float, default=12.0)
    ap.add_argument("--pop-min", type=int, default=6)
    ap.add_argument("--topn", type=int, default=5, help="検証するピック数(穴度上位)")
    ap.add_argument("--wet-ana", action="store_true",
                    help="重馬場の穴特徴量を有効化(既定OFF・エッジ無しと判明)")
    ap.add_argument("--samples", nargs="*", default=[
        "data/samples/nankan_2026-02.jsonl", "data/samples/nankan_2026-03.jsonl",
        "data/samples/nankan_2026-04.jsonl", "data/samples/nankan_2026-05.jsonl",
        "data/samples/nankan_2026-06.jsonl"])
    args = ap.parse_args()

    ymd = args.date.replace("-", "")
    client = PoliteClient()
    idx = client.get(CARD_URL.format(race_id=day_index_race_id(ymd, args.place)))
    races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd,
                                    jyo_code=NANKAN_CODES[args.place]))
    jrates = pn.jockey_top3_from_samples(args.samples)
    wet_stats = (pn.wet_ana_stats_from_samples(args.samples, pop_min=args.pop_min)
                 if args.wet_ana else None)

    n_pick = n_board = 0          # 検証ピック総数 / うち3着内
    n_head = n_head_board = 0     # 本線(穴度1位)数 / うち3着内
    n_win = 0                     # ピックから勝ち馬が出た回数
    hit_trios = []               # (R, 払戻) ピック5頭ボックスで三連複的中したR

    for rno in sorted(races):
        rid = races[rno]
        try:
            card = P.parse_card_page(client.get(CARD_URL.format(race_id=rid)), rid)
            res = P.parse_result_page(client.get(RESULT_URL.format(race_id=rid)), rid)
        except Exception as ex:  # noqa: BLE001
            print(f"R{rno}: 取得失敗 {ex}")
            continue
        if not res.rows:
            continue

        jockeys = E.jockey_stats_from_card(card)
        tt, _note = pn.day_target_time(client, list(races.items()), card.distance)
        bias = pn.class_to_bias(card.race_class) if args.bias == "auto" else args.bias
        picks = pn.zubu_ana_picks(card, jockeys, target_time=tt, jockey_rates=jrates,
                                  jockey_div=args.jw, pop_min=args.pop_min, bias=bias,
                                  baba=args.baba, wet_stats=wet_stats)
        picks = picks[:args.topn]

        top3 = {r.umaban for r in res.rows[:3]}
        winner = res.rows[0].umaban
        order_str = " ".join(
            f"{r.finish_pos}着{r.umaban}{r.horse_name}({r.popularity}人)"
            for r in res.rows[:3])
        print("=" * 70)
        print(f"川崎 {rno}R {card.surface}{card.distance}m  結果: {order_str}")

        pick_set = set()
        for i, (e, score, _tags) in enumerate(picks, 1):
            n_pick += 1
            pick_set.add(e.umaban)
            hit = e.umaban in top3
            if hit:
                n_board += 1
            if i == 1:
                n_head += 1
                if hit:
                    n_head_board += 1
            fp = next((r.finish_pos for r in res.rows if r.umaban == e.umaban), None)
            head = "本線" if i == 1 else "  "
            fps = f"{fp}着" if fp else "圏外"
            print(f"  {head} ◇{e.umaban:>2} {e.horse_name[:10]:<11}"
                  f"({e.exp_pop}人) 穴度{score:.1f} → {fps}{' ★' if hit else ''}")
        if winner in pick_set:
            n_win += 1
        # ピック5頭ボックスで三連複が当たったか + 払戻
        if top3 and top3.issubset(pick_set):
            try:
                o = O.parse_odds_html(client.get(O.odds_url(rid, "trio")), bet_type="trio")
                pay = o.get(tuple(sorted(top3)))
            except Exception:  # noqa: BLE001
                pay = None
            hit_trios.append((rno, pay))
            print(f"  → ★ピック{args.topn}頭BOXで三連複的中! "
                  f"払戻 {('%.1f倍' % pay) if pay else '不明'}")

    print("=" * 70)
    nr = n_head
    print(f"【集計 {args.place} {args.date} / bias={args.bias}】")
    print(f"  ピック {n_pick}頭中 3着内 {n_board}頭 "
          f"({100*n_board/n_pick:.1f}%)" if n_pick else "  ピックなし")
    print(f"  本線(穴度1位)の3着内: {n_head_board}/{nr}R "
          f"({100*n_head_board/nr:.0f}%)" if nr else "")
    print(f"  ピックに勝ち馬: {n_win}/{nr}R")
    if hit_trios:
        print(f"  {args.topn}頭BOX三連複 的中: "
              + ", ".join(f"{r}R({('%.0f倍'%p) if p else '?'})" for r, p in hit_trios))


if __name__ == "__main__":
    main()
