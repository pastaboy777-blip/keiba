#!/usr/bin/env python3
"""1日の中で馬場がどう動いたか（ドリフト）を、レース単位で使える形に出す。

    完タイム差 = タイム差 − 馬場差 × 距離/1000

この「馬場差」を**1日1つ**にすると、日中で馬場が動く日に前半/後半どちらかが必ず
ずれる。散水・砂の掘れ・気温で実際に動く。実測 2026-07-02 船橋は
前半 +0.1秒 → 後半 −0.7秒（1600m換算）で 0.8秒動いた。1日平均 −0.1 を
後半レースに当てると補正が足りず、**後半レースを過大評価する**。

出すもの:
  レースごとの実測差   … 勝ち時計 s/F − par。**1レース1標本なので生値はノイズ**。
  ならし値             … 前後2レースを含む5レースの中央値。これを実用に使う。
  前半(1〜6R)/後半(7〜12R) … ブロックで持ちたいとき用。
  スイング             … 前半と後半の差。0.5秒以上なら1日1つの馬場差は使えない。

⚠️ **レース単位の生値は信用しないこと。** その日その距離で「強いレースだった」
   のか「馬場が速かった」のかは1レースでは分離できない。5レースならしても
   完全には分離できないが、単発よりはるかにまし。

⚠️ ならし値はレース番号の順に並べたときの中央値であって、時刻ではない。
   距離の違いは s/F にしてあるので吸収済み。

    python3 scripts/nankan_drift.py --place 船橋 --from 2026-06-28 --to 2026-07-04
    python3 scripts/nankan_drift.py --place 川崎 --from 2026-07-30 --ref 1000
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from collections import defaultdict
from statistics import median

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import shock, track_bias              # noqa: E402
from nankeiba.core.datapath import cache_dir             # noqa: E402
from nankeiba.scraping import rakuten as rk              # noqa: E402

#: ならしに使う窓（中心のレース ± この本数）。
WIN = 2


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", default="船橋")
    ap.add_argument("--from", dest="lo", required=True)
    ap.add_argument("--to", dest="hi", default="9999-99-99")
    ap.add_argument("--ref", type=int, default=1000,
                    help="表示の基準距離[m]。既定1000（完タイム差 = タイム差 − 馬場差×距離/1000）")
    ap.add_argument("--win", type=int, default=WIN, help="ならしの窓（±本数）")
    args = ap.parse_args()

    cdir = str(cache_dir())
    print("キャッシュを読み込み中…", file=sys.stderr)
    days: dict = defaultdict(list)
    for pf in sorted(glob.glob(os.path.join(
            cdir, "race_performance_list_RACEID_*.html"))):
        rid = pf.rsplit("_", 1)[-1].removesuffix(".html")
        d = f"{rid[0:4]}-{rid[4:6]}-{rid[6:8]}"
        if not (args.lo <= d <= args.hi):
            continue
        cf = os.path.join(cdir, f"race_card_list_RACEID_{rid}.html")
        if not os.path.exists(cf):
            continue
        try:
            hd = rk.parse_card(open(cf, encoding="utf-8").read())["header"]
            res = rk.parse_result(open(pf, encoding="utf-8").read())
        except Exception:                                # noqa: BLE001
            continue
        if hd.get("place") != args.place or not hd.get("distance") or not res:
            continue
        t = res[0].get("time_sec")
        par = shock.par_pace(args.place, hd["distance"], track_bias.PAR_WIN or None)
        if not t or par is None:
            continue
        days[d].append((hd.get("race_no") or 0, hd["distance"],
                        round(t / (hd["distance"] / 200.0) - par, 3)))
    if not days:
        print("該当なし。", file=sys.stderr)
        sys.exit(1)

    k = args.ref / 200.0          # s/F → 基準距離の秒
    print(f"\n=== {args.place} 馬場差のドリフト　{min(days)} 〜 {max(days)} ===")
    print(f"  単位は {args.ref}m 換算の秒（完タイム差 = タイム差 − 馬場差×距離/{args.ref}）")
    print(f"  ならし = 前後{args.win}レースを含む{args.win * 2 + 1}レースの中央値\n")

    for d in sorted(days):
        rs = sorted(days[d])
        nos = [r for r, _, _ in rs]
        raw = {r: v for r, _, v in rs}
        sm = {}
        for i, (r, _, _) in enumerate(rs):
            w = [v for _, _, v in rs[max(0, i - args.win): i + args.win + 1]]
            sm[r] = median(w)
        whole = track_bias.measure(
            [dict(race_no=r, place=args.place, distance=di,
                  win_time=(v + shock.par_pace(args.place, di, track_bias.PAR_WIN)) * (di / 200.0))
             for r, di, v in rs], place=args.place)
        fh = [v for r, _, v in rs if r <= 6]
        lh = [v for r, _, v in rs if r >= 7]
        print(f"■ {d}　1日1つなら {whole.offset * k:+.2f}秒　"
              f"（{whole.offset:+.3f} s/F・{whole.n_races}R）")
        print("   R   " + " ".join(f"{r:>6}" for r in nos))
        print("   実測 " + " ".join(f"{raw[r] * k:>+6.2f}" for r in nos))
        print("   なら " + " ".join(f"{sm[r] * k:>+6.2f}" for r in nos))
        if fh and lh:
            a, b = median(fh) * k, median(lh) * k
            print(f"   前半1〜6R {a:+.2f}秒 / 後半7〜12R {b:+.2f}秒 / "
                  f"スイング {b - a:+.2f}秒"
                  + ("　⚠️ 1日1つの馬場差は使えない" if abs(b - a) >= 0.5 else ""))
        print()

    print("  使い方: 各レースの『なら』の値を、そのレースの馬場差として使う。")
    print("  ⚠️ 『実測』は1レース1標本。強いレースだったのか馬場が速かったのかは")
    print("     1レースでは分離できない。**生値を単独で使わないこと。**")


if __name__ == "__main__":
    main()
