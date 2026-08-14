#!/usr/bin/env python3
"""南関のレースを BT値 で採点する（実走BT値・Phase 1〜2）。

    python3 scripts/bt.py --date 20260810 --place 浦和
    python3 scripts/bt.py --date 20260810 --place 浦和 --race 11
    python3 scripts/bt.py --build            # 基準タイム表を作り直す

BT値 = 55 ＋（統一基準タイム − 補正後タイム ＋ 年齢補正）÷ 距離係数 × 10

中心値55は**古馬Ｃ２で標準的な走り**。クラス標準の目安（実測）:

    A+ 74〜79 ／ Ｂ 66〜69 ／ Ｃ１ 59〜63 ／ Ｃ２ 55 ／ Ｃ３ 45〜49

⚠️ **JRAのBT値とは直接比べられない。**中心値55の置き方が「古馬中位条件」で
   共通なだけで、基準にした集団が違う（南関Ｃ２ 対 JRA古馬1〜2勝）。
   南関のＡ級標準が79と出るのは、南関の階級幅がJRAより広いから。

⚠️ **実装していない補正がある**（`core/bt.py` の冒頭を読むこと）。
   ペース補正ブレンド・コース形態係数・不利補正・Cap/Floor・馬場状態補正は未実装。
   とくに**ペース補正が無い**ので、スローの上がり勝負で楽をした馬と、
   ハイペースを先行して粘った馬が同じ扱いになる。ここが今の最大の穴。

⚠️ 係数（斤量の秒/kg、騎手ランク）は**まだ最適化していない初期値**。
   年齢補正だけは実測値に置き換えてある。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import bt                             # noqa: E402
from nankeiba.scraping import rakuten as rk              # noqa: E402

BASE_PATH = "data/bt/base.json"
RUNS_PATH = "data/bt/runs.jsonl"


def build(runs_path: str = RUNS_PATH, out: str = BASE_PATH) -> bt.BaseTime:
    if not os.path.exists(runs_path):
        print(f"{runs_path} が無い。先に scripts/bt_extract.py を回すこと。",
              file=sys.stderr)
        sys.exit(1)
    rows = [json.loads(l) for l in open(runs_path, encoding="utf-8")]
    B = bt.BaseTime.build(rows)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    B.dump(out)
    print(f"基準タイム {len(B.win)} マス → {out}", file=sys.stderr)
    return B


def fetch_day(date: str, place: str, races=range(1, 13)) -> list[dict]:
    """当日のレースを BT値の入力レコードに落とす（`bt_extract` と同じ形）。"""
    sys.path.insert(0, os.path.dirname(__file__))
    from bt_extract import corner4                       # noqa: E402

    cli = rk.KeibaRakuten()
    base_id = cli.find_race_id(date, place, 1)[:-2]
    out = []
    for rno in races:
        rid = f"{base_id}{rno:02d}"
        try:
            card = rk.fetch_card(cli, rid)
            res = rk.fetch_result(cli, rid)
            raw = cli.get(f"/race_performance/list/RACEID/{rid}") if res else ""
        except Exception:                                # noqa: BLE001
            continue
        if not res or not res[0].get("time_sec"):
            continue
        hd = card["header"]
        lp = rk.parse_lap(raw) or {}
        f = lp.get("furlongs") or []
        c4 = corner4(lp.get("corners"))
        ent = {e["name"]: e for e in card["entries"]}
        race = dict(rid=rid, date=hd.get("date") or f"{date[:4]}-{date[4:6]}-{date[6:]}",
                    place=hd["place"], race_no=hd.get("race_no"),
                    distance=hd["distance"], field_size=len(res),
                    baba=hd.get("baba") or rk.parse_baba(raw),
                    race_class=hd.get("race_class"), prize1=hd.get("prize1"),
                    condition=hd.get("condition"), win_time=res[0]["time_sec"],
                    laps=f, ten3f=(round(sum(f[:3]), 1) if len(f) >= 3 else None),
                    last3f_race=lp.get("agari3f"))
        for x in res:
            e = ent.get(x["name"]) or {}
            out.append({**race, "umaban": x.get("umaban"), "name": x["name"],
                        "age": e.get("age"), "sex": (x.get("sexage") or "")[:1],
                        "kinryo": x.get("kinryo") or e.get("kinryo"),
                        "jockey": x.get("jockey"), "finish": x.get("finish"),
                        "popularity": x.get("popularity"),
                        "time_sec": x.get("time_sec"), "agari": x.get("agari"),
                        "corner4": c4.get(x.get("umaban"))})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--place")
    ap.add_argument("--race", type=int)
    ap.add_argument("--build", action="store_true", help="基準タイム表を作り直す")
    ap.add_argument("--top", type=int, default=0, help="各レース上位N頭だけ出す")
    args = ap.parse_args()

    if args.build:
        build()
        if not args.date:
            return
    if not (args.date and args.place):
        ap.error("--date と --place が要る（または --build 単独）")
    if not os.path.exists(BASE_PATH):
        build()
    B = bt.BaseTime.load(BASE_PATH)

    rows = fetch_day(args.date, args.place,
                     [args.race] if args.race else range(1, 13))
    if not rows:
        print("結果が取れない。", file=sys.stderr)
        sys.exit(1)

    ratio = bt.day_ratio(rows, B)
    print(f"\n=== {args.date} {args.place}　BT値（実走・Phase 1〜2）===")
    print(f"  馬場 {rows[0].get('baba')}／馬場比 前半{ratio.early:.3f} "
          f"上がり{ratio.late:.3f}（{ratio.label}・{ratio.n_races}R から測定）")
    print(f"  中心値{bt.CENTER:.0f}＝古馬Ｃ２の標準。"
          f"目安 A+74〜79 ／ Ｂ66〜69 ／ Ｃ１59〜63 ／ Ｃ２55 ／ Ｃ３45〜49\n")

    for rno in sorted({r["race_no"] for r in rows}):
        rs = [r for r in rows if r["race_no"] == rno]
        got = []
        for r in rs:
            s = bt.score(r, B, ratio)
            if s:
                got.append((s.bt, r, s))
        if not got:
            continue
        got.sort(key=lambda t: -t[0])
        h = rs[0]
        lv = got[0][2].level
        print(f"■ {rno}R ダ{h['distance']}m {h['field_size']}頭 "
              f"{h.get('race_class') or '?'}　基準{got[0][2].base}秒 [{lv}]")
        for v, r, s in (got[:args.top] if args.top else got):
            print(f"   BT{v:>6.1f}  {r['finish']:>2}着 {r['name'][:13]:<14}"
                  f"{(str(r.get('popularity')) + '人気' if r.get('popularity') else ''):>6}"
                  f"  {r['time_sec']:>6.1f}（補正後{s.adjusted:.2f}）"
                  f" 斤量{r.get('kinryo')}"
                  + (f" 補正{s.parts['斤量']:+.2f}" if s.parts['斤量'] else "")
                  + (f" 年齢{s.parts['年齢']:+.2f}" if s.parts['年齢'] else ""))
        print()

    print("  ⚠️ ペース補正が未実装。スローの上がり勝負で楽をした馬と、")
    print("     ハイペースを先行して粘った馬が同じ扱いになっている。")


if __name__ == "__main__":
    main()
