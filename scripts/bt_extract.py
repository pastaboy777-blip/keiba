#!/usr/bin/env python3
"""キャッシュ済みの南関ページを**一度だけ**走査して、BT値の入力に落とす。

    python3 scripts/bt_extract.py --out data/bt/runs.jsonl

出力は1行1頭（JSONL）。9,000レース超を毎回パースし直すと2分以上かかるので、
基準タイム作りや採点は**この中間データを読む**こと。

1行の中身:
    race: date place race_no distance field_size baba race_class prize1 condition
          win_time laps[] sectional_600 ten3f last3f_race pace
    horse: umaban name sex age kinryo jockey trainer weight weight_diff
           finish popularity time_sec agari corner4 apprentice

⚠️ `laps` は**先頭の**ハロンラップ。個々の馬の区間タイムではない。
   BT値の仕様が要求する「馬ごとのテン3F」は南関でも中央でも公開されていない。
   各馬の前半は `time_sec − agari`（＝上がり3F以外の全部）でしか出せない。

⚠️ 南関の結果ページに**不利（出遅れ・挟まれ等）のデータは無い**。実測で
   「不利」「出遅」の語がページ内に0件。BT値仕様の不利補正3層のうち、
   第2層（レース中の不利）と第3層（序盤不利ボーナス）は**南関では作れない**。
   中央（競馬ブック）には「発走状況他」があるので、そちらでは作れる。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import rakuten as rk              # noqa: E402

NANKAN = ("大井", "川崎", "船橋", "浦和")
#: 減量騎手の印。結果ページの騎手名に前置される。
_APPR = "☆★◇▲△◆"


def corner4(corners: str | None) -> dict:
    """通過順文字列 → {馬番: 4角の順位}。括弧は横並び（同順）。"""
    if not corners:
        return {}
    m = re.search(r"４角(.*?)(?:■|$)", corners)
    if not m:
        return {}
    pos, rank = {}, 1
    for a, b in re.findall(r"\(([^)]*)\)|(\d+)", m.group(1)):
        nums = [int(x) for x in re.findall(r"\d+", a or b)]
        for u in nums:
            pos.setdefault(u, rank)
        rank += len(nums)
    return pos


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="data/cache/rakuten")
    ap.add_argument("--out", default="data/bt/runs.jsonl")
    ap.add_argument("--places", default=",".join(NANKAN))
    args = ap.parse_args()
    places = set(args.places.split(","))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    pfs = sorted(glob.glob(os.path.join(
        args.cache, "race_performance_list_RACEID_*.html")))
    n_race = n_row = 0
    with open(args.out, "w", encoding="utf-8") as fo:
        for i, pf in enumerate(pfs):
            if i % 500 == 0:
                print(f"  {i}/{len(pfs)}…", file=sys.stderr)
            rid = pf.rsplit("_", 1)[-1].removesuffix(".html")
            cf = os.path.join(args.cache, f"race_card_list_RACEID_{rid}.html")
            if not os.path.exists(cf):
                continue
            try:
                card = rk.parse_card(open(cf, encoding="utf-8").read())
                raw = open(pf, encoding="utf-8").read()
                res = rk.parse_result(raw)
                lp = rk.parse_lap(raw) or {}
            except Exception:                            # noqa: BLE001
                continue
            hd = card["header"]
            if hd.get("place") not in places or not hd.get("distance") or not res:
                continue
            if not res[0].get("time_sec"):
                continue
            ent = {e["name"]: e for e in card["entries"]}
            c4 = corner4(lp.get("corners"))
            f = lp.get("furlongs") or []
            date = hd.get("date") or f"{rid[0:4]}-{rid[4:6]}-{rid[6:8]}"
            race = dict(
                rid=rid, date=date, place=hd["place"], race_no=hd.get("race_no"),
                distance=hd["distance"], field_size=len(res),
                baba=hd.get("baba") or rk.parse_baba(raw),
                race_class=hd.get("race_class"), prize1=hd.get("prize1"),
                condition=hd.get("condition"), win_time=res[0]["time_sec"],
                laps=f, ten3f=(round(sum(f[:3]), 1) if len(f) >= 3 else None),
                last3f_race=lp.get("agari3f"),
            )
            n_race += 1
            for x in res:
                e = ent.get(x["name"]) or {}
                jk = x.get("jockey") or ""
                fo.write(json.dumps({
                    **race,
                    "umaban": x.get("umaban"), "name": x["name"],
                    "sex": (x.get("sexage") or e.get("sex_age") or "")[:1],
                    "age": e.get("age"),
                    "kinryo": x.get("kinryo") or e.get("kinryo"),
                    "jockey": re.sub(r"\s*\(.*", "", jk).lstrip(_APPR) or None,
                    "apprentice": bool(jk[:1] in _APPR),
                    "trainer": x.get("trainer"),
                    "weight": x.get("weight"), "weight_diff": x.get("weight_diff"),
                    "finish": x.get("finish"), "popularity": x.get("popularity"),
                    "time_sec": x.get("time_sec"), "agari": x.get("agari"),
                    "corner4": c4.get(x.get("umaban")),
                }, ensure_ascii=False) + "\n")
                n_row += 1
    print(f"{n_race} レース / {n_row} 頭 → {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
