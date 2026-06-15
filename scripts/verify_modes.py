"""同一日の全レースを複数モード(通常 / 消耗戦)でランキングし、実結果と比較する。

消耗戦モード(shomousen: キレ無効・先行/タフネス/道悪を加点)が、前残り・上がりの
かかる馬場で本当に的中を改善するかを検証する。各レースでモデル上位(◎=1位/上位3頭)
が実際の3着内に入った数を集計し、モード間で比較する。

実行: python3 scripts/verify_modes.py --date 2026-06-15 --place 川崎 --baba 重
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import predict_nankan as pn
from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from nankeiba.scraping import enrich as E
from nankeiba.core import features as F

MODES = ["normal", "shomousen"]


def rank_for_mode(card, jockeys, trainers, mode, baba):
    weights = pn.weights_for(mode)
    agari_adj = pn.agari_style_adjust(card) if mode in ("shomousen", "zenzan") else {}
    scores = {}
    for e in card.entries:
        if e.umaban is None:
            continue
        ctx = F.RaceContext(date=card.date, place=card.place, distance=card.distance,
                            field_size=card.field_size, jockey=e.jockey,
                            trainer=e.trainer, baba=baba)
        records = E.past_runs_to_records(e)
        sc = F.horse_score(records, ctx, jockeys=jockeys, trainers=trainers,
                           weights=weights)
        sc += agari_adj.get(e.umaban, 0.0)
        scores[e.umaban] = sc
    order = sorted(scores, key=lambda u: -scores[u])
    return order


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", choices=list(NANKAN_CODES), required=True)
    ap.add_argument("--baba", choices=list(pn.BABA_FULL), default="重")
    ap.add_argument("--samples", nargs="*", default=[
        "data/samples/nankan_2026-04.jsonl", "data/samples/nankan_2026-05.jsonl",
        "data/samples/nankan_2026-06.jsonl"])
    args = ap.parse_args()

    ymd = args.date.replace("-", "")
    client = PoliteClient()
    idx = client.get(pn.CARD_URL.format(race_id=day_index_race_id(ymd, args.place)))
    races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd,
                                    jyo_code=NANKAN_CODES[args.place]))
    trainers = pn.trainer_stats_from_samples(args.samples)

    # 集計: モード別の ◎(1位)的中・上位3頭の3着内ヒット数
    agg = {m: {"hon": 0, "hon_board": 0, "top3hit": 0, "races": 0} for m in MODES}
    print(f"{'R':>3} {'結果(3着)':<22} " + " ".join(f"{m+'◎/上位3着内':<16}" for m in MODES))
    for rno in sorted(races):
        rid = races[rno]
        try:
            card = P.parse_card_page(client.get(pn.CARD_URL.format(race_id=rid)), rid)
            res = P.parse_result_page(client.get(pn.RESULT_URL.format(race_id=rid)), rid)
        except Exception as ex:  # noqa: BLE001
            print(f"R{rno}: 取得失敗 {ex}")
            continue
        if not res.rows:
            continue
        jockeys = E.jockey_stats_from_card(card)
        top3 = {r.umaban for r in res.rows[:3]}
        name = {r.umaban: r.horse_name for r in res.rows}
        finish = {r.umaban: r.finish_pos for r in res.rows}
        res_str = "-".join(str(r.umaban) for r in res.rows[:3])

        cells = []
        for m in MODES:
            order = rank_for_mode(card, jockeys, trainers, m, args.baba)
            hon = order[0]
            n_in = sum(1 for u in order[:3] if u in top3)
            agg[m]["races"] += 1
            agg[m]["hon"] += 1
            agg[m]["hon_board"] += 1 if hon in top3 else 0
            agg[m]["top3hit"] += n_in
            hon_fp = finish.get(hon)
            cells.append(f"◎{hon}({hon_fp}着){'★' if hon in top3 else ''}/{n_in}頭")
        print(f"{rno:>3} {res_str:<22} " + " ".join(f"{c:<16}" for c in cells))

    print("=" * 70)
    for m in MODES:
        a = agg[m]
        r = a["races"]
        print(f"[{m}] ◎の3着内 {a['hon_board']}/{r}R "
              f"({100*a['hon_board']/r:.0f}%) / "
              f"上位3頭の3着内ヒット計 {a['top3hit']}/{r*3} "
              f"({100*a['top3hit']/(r*3):.0f}%)")


if __name__ == "__main__":
    main()
