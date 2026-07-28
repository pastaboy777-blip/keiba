#!/usr/bin/env python3
"""レースの「メンバーの格」を事前計算して `data/race_grade.json` に書き出す。

格の定義:
    そのレースに出走した馬たちの **そのレースより前の1着経験率** の中央値。

  ・**後の結果を一切使わない**ので、前走が先週でも計算できる（実戦で使える）。
  ・「そのレースの出走馬がその後どれだけ走ったか」で測る版は実測で棄却した
    （lift 0.96〜1.02 で真っ平ら）。複勝率はどのレースでも3割前後に潰れるため。

実測（南関キャッシュ・**前走7着以下**の 31,867組、その層の次走複勝率 14.9%）:
    格 0.00〜  n=11,349  14.2%  lift 0.95
    格 0.08〜  n=12,585  14.9%  lift 1.00
    格 0.16〜  n=5,734   15.0%  lift 1.01
    格 0.24〜  n=1,228   16.2%  lift 1.09
    格 0.32〜  n=971     20.9%  lift **1.40**
⚠️ **前走で好走した馬には効かない**（前走1-3着の層では 0.96/1.02/1.08/0.97 と
   バラつくだけ）。着順が悪かった馬の「言い訳」を測る指標として使う。

出力は {"YYYY-MM-DD|場|距離": {"馬名": 過去1着率, ...}} 形式。
問い合わせ時に対象馬を除いて中央値を取れるようにするため、素の値を保存する。

    python3 scripts/build_race_grade.py
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import rakuten as rk        # noqa: E402

CACHE = "data/cache/rakuten"
OUT = "data/race_grade.json"
MIN_PAST = 3          # 過去これ未満の走しかない馬は格の計算に入れない


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    # 1) 全レースの出走馬名簿（結果ページ＝全頭載る）
    roster: dict[str, list[str]] = {}
    for pf in sorted(glob.glob(os.path.join(
            CACHE, "race_performance_list_RACEID_*.html"))):
        rid = pf.rsplit("_", 1)[-1].removesuffix(".html")
        cf = os.path.join(CACHE, f"race_card_list_RACEID_{rid}.html")
        if not os.path.exists(cf):
            continue
        try:
            hd = rk.parse_card(open(cf, encoding="utf-8").read())["header"]
            res = rk.parse_result(open(pf, encoding="utf-8").read())
        except Exception:                          # noqa: BLE001
            continue
        if not hd.get("place") or not hd.get("distance") or not res:
            continue
        key = f"{rid[0:4]}-{rid[4:6]}-{rid[6:8]}|{hd['place']}|{hd['distance']}"
        roster[key] = [r["name"] for r in res if r.get("name")]

    # 2) 馬ごとの全走（馬柱＝他場・古い走りも拾える）
    fin: dict[str, dict[str, int]] = defaultdict(dict)
    for cf in sorted(glob.glob(os.path.join(
            CACHE, "race_card_list_RACEID_*.html"))):
        try:
            card = rk.parse_card(open(cf, encoding="utf-8").read())
        except Exception:                          # noqa: BLE001
            continue
        for e in card["entries"]:
            for r in e["history"]:
                if r.finish_pos:
                    fin[e["name"]][r.date] = r.finish_pos

    # 3) 各レースの各馬について「そのレースより前の1着経験率」
    out: dict[str, dict[str, float]] = {}
    for key, names in roster.items():
        d = key.split("|")[0]
        cell = {}
        for nm in names:
            past = [f for dt, f in fin.get(nm, {}).items() if dt < d]
            if len(past) >= MIN_PAST:
                cell[nm] = round(sum(1 for f in past if f == 1) / len(past), 4)
        if len(cell) >= 4:
            out[key] = cell

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        f.write("\n")
    print(f"{len(out)}レース / 述べ{sum(len(v) for v in out.values())}頭 → {args.out}")


if __name__ == "__main__":
    main()
