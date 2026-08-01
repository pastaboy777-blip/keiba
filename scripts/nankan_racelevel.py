# -*- coding: utf-8 -*-
"""南関：どのレースがレベルが高かったかを『出走馬のその後』で測る。

なぜこの測り方か（2026-08-01）:
  この日、時計から作った指標は中央493レース・川崎911点でどれも控除率の帯に収まった。
  さらに「勝ち馬の上がりが遅い日は人気薄が浮く」は循環（人気薄が勝つと上がりが遅く出る）で、
  条件の作り方に結果が混ざっていた。

  レースレベルを『そのレースの中で起きたこと（時計・着差）』で測ると、同じ罠に入る。
  そこで、レースの**後**に起きたことだけで測る。

      レベル ＝ そのレースの出走馬が、その日より後のレースでどれだけ走ったか

  これは定義上そのレースの中身を含まないので循環しない。そして市場は「その馬の着順」を見るが
  「その着順がどんな相手の中でのものか」は値段に入りきらない。ここが狙い目になる。

指標:
  各馬の後続1走ごとに 着順スコア ＝ 1 −(着順−1)/(頭数−1)  … 1着=1.0、最下位=0.0
  レースレベル ＝ 出走馬の後続スコアの平均（後続が取れた馬だけで平均）
  併せて「後続で勝った馬の数」も出す。こちらは解釈しやすい。

  ★後続が溜まるまで時間が要るので、直近のレースほどレベルは測れない。
    最低 min-runs 頭ぶんの後続が無いレースは出さない。

    python3 scripts/nankan_racelevel.py --from 2026-05-01 --to 2026-07-31
    python3 scripts/nankan_racelevel.py --from 2026-05-01 --to 2026-07-31 --place 川崎 --top 30
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping.race_id import NANKAN_CODES
from nankeiba.scraping import parser as P

from nankan_zubu_backtest import CARD, PERF, race_days

VENUES = ["川崎", "船橋", "大井", "浦和"]


def collect(client, venues, d0, d1):
    """南関各場の確定結果を集めて、レースと馬のタイムラインを作る。"""
    races, timeline = {}, defaultdict(list)
    for place in venues:
        days = race_days(client, place, d0, d1)
        for i, (d, rs) in enumerate(days, 1):
            for rno, rid in sorted(rs.items()):
                try:
                    res = P.parse_result_page(client.get(PERF.format(r=rid)), rid)
                except Exception:
                    continue
                rows = [r for r in res.rows if r.horse_id and r.finish_pos]
                if len(rows) < 5:
                    continue
                n = len(rows)
                races[rid] = dict(date=d, place=place, rno=rno, dist=res.distance,
                                  n=n, rows=rows)
                for r in rows:
                    # 着順スコア：1着=1.0、最下位=0.0。頭数の違いを吸収する。
                    timeline[r.horse_id].append(
                        (d, rid, 1.0 - (r.finish_pos - 1) / (n - 1), r.finish_pos))
            print(f"\r{place} {i}/{len(days)}日", end="", flush=True)
        print()
    for h in timeline:
        timeline[h].sort()
    return races, timeline


def main():
    ap = argparse.ArgumentParser(description="南関レースレベル（出走馬のその後で測る）")
    ap.add_argument("--from", dest="d_from", required=True)
    ap.add_argument("--to", dest="d_to", required=True)
    ap.add_argument("--place", help="表示を1場に絞る（収集は常に南関4場）")
    ap.add_argument("--min-runs", type=int, default=5,
                    help="後続が取れた馬がこの頭数未満のレースは判定しない")
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    client = PoliteClient(use_cache=True)
    races, timeline = collect(client, VENUES,
                              date.fromisoformat(args.d_from), date.fromisoformat(args.d_to))
    print(f"\n収集 {len(races)}レース／延べ {sum(len(v) for v in timeline.values())}走\n")

    out = []
    for rid, r in races.items():
        scores, wins, cover = [], 0, 0
        for row in r["rows"]:
            later = [x for x in timeline[row.horse_id] if x[0] > r["date"]]
            if not later:
                continue
            cover += 1
            scores.append(st.mean(x[2] for x in later))
            wins += sum(1 for x in later if x[3] == 1)
        if cover < args.min_runs:
            continue
        out.append(dict(rid=rid, level=st.mean(scores), cover=cover, wins=wins, **r))

    if not out:
        raise SystemExit("後続が足りない。期間を早めに取るか --min-runs を下げること。")
    lv = [o["level"] for o in out]
    mu, sd = st.mean(lv), st.pstdev(lv)
    print(f"■ 判定できた {len(out)}レース／レベルの平均 {mu:.3f} 標準偏差 {sd:.3f}\n")

    show = [o for o in out if not args.place or o["place"] == args.place]
    show.sort(key=lambda o: -o["level"])
    print(f"{'':<22}{'頭数':>5}{'後続が':>7}{'後続の':>7}{'レベル':>8}{'偏差':>7}")
    print(f"{'レース':<22}{'':>5}{'取れた':>7}{'勝利数':>7}{'':>8}{'':>7}")
    for o in show[:args.top]:
        z = (o["level"] - mu) / sd if sd else 0
        print(f"{str(o['date'])+' '+o['place']+str(o['rno'])+'R ダ'+str(o['dist']):<22}"
              f"{o['n']:>5}{o['cover']:>7}{o['wins']:>7}{o['level']:>8.3f}{z:>+7.2f}")
    print("  ── 下位 ──")
    for o in show[-5:]:
        z = (o["level"] - mu) / sd if sd else 0
        print(f"{str(o['date'])+' '+o['place']+str(o['rno'])+'R ダ'+str(o['dist']):<22}"
              f"{o['n']:>5}{o['cover']:>7}{o['wins']:>7}{o['level']:>8.3f}{z:>+7.2f}")

    print("\n■ 使い方：この表で偏差+1.0以上のレースに出ていた馬は、着順が悪くても"
          "相手が強かっただけかもしれない。逆に−1.0以下のレースの勝ち馬は割引く。")


if __name__ == "__main__":
    main()
