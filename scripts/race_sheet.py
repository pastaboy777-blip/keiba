#!/usr/bin/env python3
"""南関の全レースを1行ずつ数値化する（レース台帳）。

ユーザー指定（2026-07-28）:
  「7月の南関競馬のレースをすべて数値化して」
  「ラップや時計や走った馬がそれからどうなったか」
  「数値化にするためのファクターはたくさんインプットしたはず」

これまでに入れてもらったファクターを、**レース単位**で1行に畳む。

  [時計]   勝ちタイム / s per F / 勝ち馬par差 / 当日その場の馬場差
  [ラップ] 実測ハロン / テン3F / 上がり3F / 前後半バランス / ペース判定 H・M・S
  [上がり] 上位3頭の平均上がり / メンバー最速上がり / 同場同距離の平均との差
  [決着]   1-5着のタイム差（密度） / 勝ち馬の脚質（通過順） / 勝ち馬の人気
  [メンバー] 出走頭数 / 未出走馬の数 / メンバーの格（過去1着経験率の中央値）
  [その後] 出走馬のその後の 1着数・3着内数・**特別/重賞での3着内**（頭数と馬名）

⚠️ 「その後」は**レース後の情報**なので、予想には使えない（リークする）。
   これは**レースを振り返って評価する**ための欄。予想に使うなら
   「メンバーの格」までにとどめること。

    python3 scripts/race_sheet.py --month 202607 --out out/race_sheet_202607.csv
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
import re
import sys
from collections import defaultdict
from statistics import median

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import lap as lapmod           # noqa: E402
from nankeiba.core import race_level as rl        # noqa: E402
from nankeiba.core import rivals as rv            # noqa: E402
from nankeiba.core import shock, track_bias       # noqa: E402
from nankeiba.scraping import rakuten as rk       # noqa: E402

CACHE = "data/cache/rakuten"
NANKAN = ("大井", "川崎", "船橋", "浦和")

COLS = [
    "日付", "場", "R", "距離", "馬場", "頭数",
    "勝ちタイム", "sperF", "par差", "当日馬場差",
    "テン3F", "上がり3F", "バランス", "ペース", "決着傾向", "ラップ",
    "上位3頭平均上がり", "メンバー最速上がり", "上がり同条件差",
    "1-5着差", "勝ち馬通過", "勝ち馬脚質", "勝ち馬人気",
    "未出走馬数", "メンバーの格",
    "その後1着数", "その後3着内数", "その後特別3着内", "特別で走った馬",
]


def _rows(month: str, places: tuple):
    for pf in sorted(glob.glob(os.path.join(
            CACHE, "race_performance_list_RACEID_*.html"))):
        rid = pf.rsplit("_", 1)[-1].removesuffix(".html")
        if month and not rid.startswith(month):
            continue
        cf = os.path.join(CACHE, f"race_card_list_RACEID_{rid}.html")
        if not os.path.exists(cf):
            continue
        try:
            raw_c = open(cf, encoding="utf-8").read()
            raw_p = open(pf, encoding="utf-8").read()
            card = rk.parse_card(raw_c)
            res = rk.parse_result(raw_p)
        except Exception:                          # noqa: BLE001
            continue
        hd = card["header"]
        if hd.get("place") not in places or not hd.get("distance") or not res:
            continue
        yield rid, hd, card, res, raw_c, raw_p


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default="202607")
    ap.add_argument("--places", nargs="+", default=list(NANKAN))
    ap.add_argument("--out", default="out/race_sheet.csv")
    args = ap.parse_args()
    places = tuple(args.places)

    print("索引を作成中（出走馬名簿とその後の走り）…")
    idx = rv.Index()

    # 同条件（場×距離）の上がり平均を出しておく
    ag_by = defaultdict(list)
    day_by = defaultdict(list)
    cache = []
    for rid, hd, card, res, raw_c, raw_p in _rows(args.month, places):
        cache.append((rid, hd, card, res, raw_c, raw_p))
        a = [r["agari"] for r in res[:3] if r.get("agari")]
        if a:
            ag_by[f"{hd['place']}|{hd['distance']}"].append(sum(a) / len(a))
        if res[0].get("time_sec"):
            day_by[(rid[:8], hd["place"])].append(
                dict(race_no=hd.get("race_no") or 0, place=hd["place"],
                     distance=hd["distance"], win_time=res[0]["time_sec"]))
    ag_par = {k: median(v) for k, v in ag_by.items() if len(v) >= 5}
    day_bias = {k: track_bias.measure(v).offset for k, v in day_by.items()}
    print(f"  {len(cache)}レース / 上がり基準 {len(ag_par)}条件")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(COLS)
        for rid, hd, card, res, raw_c, raw_p in cache:
            d = f"{rid[0:4]}-{rid[4:6]}-{rid[6:8]}"
            pl, di = hd["place"], hd["distance"]
            la = lapmod.analyze(res, di, rk.parse_lap(raw_p))
            wt = res[0].get("time_sec")
            sf = wt / (di / 200.0) if wt else None
            wpar = track_bias.PAR_WIN.get(f"{pl}|{di}")
            a3 = [r["agari"] for r in res[:3] if r.get("agari")]
            aall = [r["agari"] for r in res if r.get("agari")]
            a3m = sum(a3) / len(a3) if a3 else None
            apar = ag_par.get(f"{pl}|{di}")
            ts = [r["time_sec"] for r in res if r.get("time_sec")]

            ents = {e["umaban"]: e for e in card["entries"]}
            we = ents.get(res[0]["umaban"])
            wc = we["history"][0].corner_pos if (we and we["history"]) else []
            # 勝ち馬の当日の脚質は結果ページに通過順が無いので、近走から推定
            pos = None
            if we:
                ps = [r.corner_pos[0] / max(1, r.field_size)
                      for r in we["history"][:5] if r.corner_pos and r.field_size]
                pos = sum(ps) / len(ps) if ps else None
            style = ("?" if pos is None else "逃げ" if pos <= .18 else
                     "先行" if pos <= .40 else "差し" if pos <= .70 else "追込")

            lv = rl.level_of(d, pl, di)
            nodebut = sum(1 for e in card["entries"] if not e["history"])

            # その後
            w1 = w3 = ws = 0
            names = []
            for nm, _f in idx.roster.get((d, pl, di), []):
                for dt, (_d2, p2, d2, f2, n2) in idx.runs.get(nm, {}).items():
                    if dt <= d:
                        continue
                    w1 += f2 == 1
                    w3 += f2 <= 3
                    if f2 <= 3 and rv.is_stakes(n2):
                        ws += 1
                        names.append(f"{nm}({n2}{f2}着)")

            w.writerow([
                d, pl, hd.get("race_no"), di,
                rk.parse_baba(raw_p) or rk.parse_baba(raw_c) or "",
                len(res),
                wt, round(sf, 3) if sf else "",
                round(sf - wpar, 3) if (sf and wpar) else "",
                day_bias.get((rid[:8], pl), ""),
                la.ten3f or "", la.last3f or "", la.balance or "",
                la.pace, la.bias, la.lap_curve(),
                round(a3m, 2) if a3m else "",
                min(aall) if aall else "",
                round(a3m - apar, 2) if (a3m and apar) else "",
                round(ts[min(4, len(ts) - 1)] - ts[0], 1) if len(ts) >= 2 else "",
                "-".join(map(str, wc)), style, res[0].get("popularity") or "",
                nodebut, lv.grade if lv else "",
                w1, w3, ws, " / ".join(sorted(set(names))[:6]),
            ])
    print(f"→ {args.out}")


if __name__ == "__main__":
    main()
