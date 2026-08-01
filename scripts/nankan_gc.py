#!/usr/bin/env python3
"""グリーンチャンネル「トラックマンTV／ダートのタイム比較」形式の表を南関で作る。

    レース 距離 優勝馬 2着 頭数 走破タイム タイム差 補正値 完全タイム差 レベル(タイム/メンバー)
    ……
    2026-07-04 馬場差 = -0秒3

計算式は本家の表から数字で逆算した（2026-08-01・第1回札幌1日目/2日目で検算）。

    完全タイム差 = タイム差 − 馬場差 × (距離 ÷ 基準距離) + 補正値

  例）7/25 札幌 馬場差 −1秒0
      3R 1700m  タイム差 +0.1 → +0.1 + 1.0            = +1.1 ✓
      1R 1000m  タイム差 −0.7 → −0.7 + 1.0×(1000/1700) = −0.11 → −0.1 ✓
      12R 1700m タイム差 +0.5 → +0.5 + 1.0 − 0.6(補正) = +0.9 ✓

**要点は「馬場差を距離で按分する」こと。** 1000mのレースに1700m分の馬場差を
そのまま当てない。このモジュールは馬場差を s/F（1ハロンあたり秒）で持つので、
距離を掛けるだけで按分になる。

本家との違い:
  * 本家の馬場差は**1日1つ**。ここでは**前半(1〜6R)/後半(7〜12R)で分けて**出す。
    船橋2026年5〜6月は12日中7日で日中に馬場が速くなっており、5/8は 0.29 s/F
    （1700m換算で約2.5秒）動いた。1日1つでは前半レースを過小評価する。
  * 本家の「補正値」は**人が入れる欄**（極端なペース・不利など）。自動では
    拾えないので、ここは常に空欄にしてある。埋めるのは人の仕事。
  * レベルA〜Eは本家では**条件（クラス）ごとの相対**だが、南関の結果ページには
    クラス表記が無い。ここでは
      タイム   … その場の全レースの完全タイム差の分位
      メンバー … 出走馬の過去1着経験率の中央値（`race_level`）の分位
    で代用している。**クラスをまたいだ絶対比較には使えない。**

    python3 scripts/nankan_gc.py --place 船橋 --last
    python3 scripts/nankan_gc.py --place 川崎 --from 2026-07-27 --to 2026-07-30
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from collections import defaultdict
from statistics import median

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import thickness as th                # noqa: E402
from nankeiba.core import track_bias                     # noqa: E402
from nankeiba.core.datapath import cache_dir             # noqa: E402
from nankeiba.scraping import rakuten as rk              # noqa: E402

#: レベルの分位。本家の見た目（A1 B1 C3 D3 E2 / 10レース）に近づけた。
GRADES = ((0.10, "A"), (0.30, "B"), (0.70, "C"), (0.90, "D"), (1.01, "E"))
#: 馬場差を「◯秒◯」で表示するときの基準距離。
REF_DIST = 1600


def grade(value: float | None, dist: list[float], *, higher_is_better=False) -> str:
    """分布の中での位置を A〜E に落とす。値が無ければ '-'。"""
    if value is None or not dist:
        return "-"
    below = sum(1 for x in dist if x < value)
    q = below / len(dist)
    if higher_is_better:
        q = 1.0 - q
    for hi, g in GRADES:
        if q < hi:
            return g
    return "E"


def sec(x: float) -> str:
    """-1.0 → '-1秒0'（本家の表記に合わせる）。"""
    s = "-" if x < 0 else "+"
    a = abs(x)
    return f"{s}{int(a)}秒{round((a - int(a)) * 10):.0f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", default="船橋")
    ap.add_argument("--from", dest="lo")
    ap.add_argument("--to", dest="hi", default="9999-99-99")
    ap.add_argument("--last", action="store_true", help="直近の開催をまとめて出す")
    ap.add_argument("--ref", type=int, default=REF_DIST, help="馬場差表示の基準距離")
    args = ap.parse_args()

    cdir = str(cache_dir())
    print("キャッシュを読み込み中…", file=sys.stderr)
    allr = [r for r in th.scan() if r.place == args.place]
    if not allr:
        print(f"{args.place} がキャッシュに無い。", file=sys.stderr)
        sys.exit(1)

    days = sorted({r.date for r in allr})
    if args.last:
        # 直近の開催 = 最終日から3日以内に連なる日をひとまとまりとみなす
        import datetime as dt
        def d(x):
            return dt.date.fromisoformat(x)
        block = [days[-1]]
        for x in reversed(days[:-1]):
            if (d(block[0]) - d(x)).days <= 3:
                block.insert(0, x)
            else:
                break
        lo, hi = block[0], block[-1]
    else:
        lo, hi = (args.lo or days[0]), args.hi
    sel = [r for r in allr if lo <= r.date <= hi]
    if not sel:
        print("該当なし。", file=sys.stderr)
        sys.exit(1)

    # 勝ち馬・2着馬の名前を引く
    names: dict = {}
    win_by_day: dict = defaultdict(list)
    for pf in sorted(glob.glob(os.path.join(
            cdir, "race_performance_list_RACEID_*.html"))):
        rid = pf.rsplit("_", 1)[-1].removesuffix(".html")
        dd = f"{rid[0:4]}-{rid[4:6]}-{rid[6:8]}"
        if not (lo <= dd <= hi):
            continue
        cf = os.path.join(cdir, f"race_card_list_RACEID_{rid}.html")
        if not os.path.exists(cf):
            continue
        try:
            hd = rk.parse_card(open(cf, encoding="utf-8").read())["header"]
            res = rk.parse_result(open(pf, encoding="utf-8").read())
        except Exception:                                # noqa: BLE001
            continue
        if hd.get("place") != args.place or not res:
            continue
        names[(dd, hd.get("race_no"))] = (
            res[0].get("name"), res[1].get("name") if len(res) > 1 else None)
        if res[0].get("time_sec"):
            win_by_day[dd].append(dict(race_no=hd.get("race_no") or 0,
                                       place=args.place, distance=hd["distance"],
                                       win_time=res[0]["time_sec"]))

    # レベルの分布は**その場の全レース**から作る（開催内だけだと基準が痩せる）
    tdist = [-r.time_lv for r in allr if r.time_lv is not None]   # 完全タイム差
    mdist = [r.grade for r in allr if r.grade is not None]

    print(f"\n{'=' * 78}")
    print(f"  {args.place} タイム比較　{lo} 〜 {hi}"
          f"（レベルの基準は {args.place} 全{len(allr)}レース）")
    print(f"{'=' * 78}")

    for dd in sorted({r.date for r in sel}):
        rs = sorted([r for r in sel if r.date == dd], key=lambda r: r.race_no or 0)
        rows = win_by_day.get(dd, [])
        tb = track_bias.measure(rows, place=args.place)
        first = track_bias.measure([x for x in rows if x["race_no"] <= 6],
                                   place=args.place)
        late = track_bias.measure([x for x in rows if x["race_no"] >= 7],
                                  place=args.place)

        print(f"\n■ {dd}　{rs[0].baba or ''}")
        print(f"  {'R':>3}{'距離':>6} {'優勝馬':<12}{'2着':<12}{'頭':>3}"
              f"{'走破ﾀｲﾑ':>8}{'ﾀｲﾑ差':>7}{'補正':>5}{'完全ﾀｲﾑ差':>10}"
              f"  ﾚﾍﾞﾙ ﾀｲﾑ/ﾒﾝﾊﾞｰ")
        for r in rs:
            w, s = names.get((dd, r.race_no), (None, None))
            par = track_bias.PAR_WIN.get(f"{args.place}|{r.distance}")
            f = r.distance / 200.0
            td = (r.win_time - par * f) if (par and r.win_time) else None
            full = -r.time_lv if r.time_lv is not None else None
            print(f"  {r.race_no or 0:>3}{r.distance:>5}m "
                  f"{(w or '')[:11]:<12}{(s or '')[:11]:<12}{r.field_size:>3}"
                  f"{r.win_time or 0:>8.1f}"
                  f"{(f'{td:+.1f}' if td is not None else '  -'):>7}"
                  f"{'—':>5}"
                  f"{(f'{full:+.1f}' if full is not None else '  -'):>10}"
                  f"    {grade(full, tdist):>2} / "
                  f"{grade(r.grade, mdist, higher_is_better=True):<2}")
        b = tb.offset * (args.ref / 200.0)
        line = f"  → 馬場差 = {sec(b)}（{args.ref}m換算 / {tb.offset:+.2f} s/F）{tb.label}"
        print(line)
        if first.n_races and late.n_races:
            fb = first.offset * (args.ref / 200.0)
            lb = late.offset * (args.ref / 200.0)
            print(f"     前半1〜6R {sec(fb)} / 後半7〜12R {sec(lb)}"
                  + ("　⚠️ 日中で動いている。1日1つの馬場差を全レースに当てない"
                     if abs(fb - lb) >= 0.5 else ""))

    print(f"\n  レベル … タイムは完全タイム差の分位（A=速い上位10%…E=下位10%）")
    print(f"           メンバーは出走馬の過去1着経験率の中央値の分位")
    print(f"  ⚠️ 補正値は**人が入れる欄**（極端なペース・不利）。自動では出せない。")
    print(f"  ⚠️ 南関の結果ページにクラス表記が無いため、本家のような"
          f"「条件ごとの相対」にはなっていない。クラスをまたいだ比較には使えない。")


if __name__ == "__main__":
    main()
