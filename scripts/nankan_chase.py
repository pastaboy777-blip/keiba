#!/usr/bin/env python3
"""きついラップを走った組を追跡する。

    # 前開催（7/20-7/24 大井）から抽出して、8/14 の出馬表を追う
    python3 scripts/nankan_chase.py --place 大井 --from 2026-07-20 --to 2026-07-24 \
        --chase 20260814

    # 抽出だけ（どのレースがきつかったか見る）
    python3 scripts/nankan_chase.py --place 大井 --from 2026-07-20 --to 2026-07-24

    # 追跡した結果を照合する（レース確定後）
    python3 scripts/nankan_chase.py --place 大井 --from 2026-07-20 --to 2026-07-24 \
        --chase 20260814 --result

抽出条件は **11秒台が N本以上 かつ 最遅−最速が S秒以内**（既定 3本 / 1.5秒）。
`--min-sub12` `--max-spread` で変えられる。

⚠️ **指数ではない。**レースを単位に集団を追う道具。
⚠️ 実測は1勝1敗（`core/kitsui.py` の冒頭）。この考え方をまだ信用しないこと。
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import kitsui                         # noqa: E402
from nankeiba.scraping import rakuten as rk              # noqa: E402


def load(cache: str, place: str, lo: str, hi: str) -> list:
    """キャッシュから期間内のレースを1頭1行に落とす。"""
    sys.path.insert(0, os.path.dirname(__file__))
    from bt_extract import corner4                       # noqa: E402
    out = []
    for pf in sorted(glob.glob(os.path.join(
            cache, "race_performance_list_RACEID_*.html"))):
        rid = pf.rsplit("_", 1)[-1].removesuffix(".html")
        d = f"{rid[0:4]}-{rid[4:6]}-{rid[6:8]}"
        if not (lo <= d <= hi):
            continue
        cf = os.path.join(cache, f"race_card_list_RACEID_{rid}.html")
        if not os.path.exists(cf):
            continue
        try:
            hd = rk.parse_card(open(cf, encoding="utf-8").read())["header"]
            raw = open(pf, encoding="utf-8").read()
            res = rk.parse_result(raw)
            lp = rk.parse_lap(raw) or {}
        except Exception:                                # noqa: BLE001
            continue
        if hd.get("place") != place or not hd.get("distance") or not res:
            continue
        c4 = corner4(lp.get("corners"))
        for x in res:
            out.append(dict(rid=rid, date=d, place=place,
                            race_no=hd.get("race_no"), distance=hd["distance"],
                            laps=lp.get("furlongs") or [], name=x["name"],
                            finish=x.get("finish"), popularity=x.get("popularity"),
                            time_sec=x.get("time_sec"),
                            corner4=c4.get(x.get("umaban"))))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", required=True)
    ap.add_argument("--from", dest="lo", required=True)
    ap.add_argument("--to", dest="hi", default="9999-99-99")
    ap.add_argument("--chase", help="追う日 YYYYMMDD")
    ap.add_argument("--result", action="store_true", help="結果と突き合わせる")
    ap.add_argument("--cache", default="data/cache/rakuten")
    ap.add_argument("--min-sub12", type=int, default=kitsui.MIN_SUB12)
    ap.add_argument("--max-spread", type=float, default=kitsui.MAX_SPREAD)
    args = ap.parse_args()

    rows = load(args.cache, args.place, args.lo, args.hi)
    races = kitsui.collect(rows, min_sub12=args.min_sub12,
                           max_spread=args.max_spread)
    n_race = len({r["rid"] for r in rows})
    print(f"\n=== {args.place} {args.lo}〜{args.hi}　きついラップのレース ===")
    print(f"  条件: 11秒台{args.min_sub12}本以上 かつ 最速差{args.max_spread}秒以内")
    print(f"  {n_race}鞍中 {len(races)}鞍が該当\n")
    for kr in races:
        print(f"■ {kr.label()}")
        print("   ラップ " + " ".join(f"{x:.1f}" for x in kr.shape.laps)
              + (f"　前3F {kr.shape.ten3f}" if kr.shape.ten3f else ""))
        for x in kr.runners:
            print(f"     {x['finish']:>2}着 {x['name'][:13]:<14}"
                  f"{x['popularity'] or '?':>3}人気  {x['time_sec']}")
        print()

    if not args.chase:
        return
    cli = rk.KeibaRakuten()
    base = cli.find_race_id(args.chase, args.place, 1)[:-2]
    entries, fin = {}, {}
    for rno in range(1, 13):
        rid = f"{base}{rno:02d}"
        try:
            card = rk.fetch_card(cli, rid)
        except Exception:                                # noqa: BLE001
            continue
        if not card["entries"]:
            continue
        entries[rno] = [e["name"] for e in card["entries"]]
        if args.result:
            try:
                fin[rno] = {x["name"]: x for x in rk.fetch_result(cli, rid)}
            except Exception:                            # noqa: BLE001
                pass

    hits = kitsui.chase(races, entries)
    tot = ok = 0
    print(f"=== {args.chase} {args.place} でこの組がどこに出るか ===\n")
    for rno in sorted(hits):
        print(f"■ {rno}R　この組 {len(hits[rno])}頭 / {len(entries[rno])}頭立て")
        for nm, kr, x in hits[rno]:
            r = fin.get(rno, {}).get(nm)
            mark = " "
            if r:
                tot += 1
                good = (r.get("finish") or 99) <= 3
                ok += good
                mark = "◎" if good else "×"
                res = f"→ {r['finish']:>2}着 {r.get('popularity')}人気"
            else:
                res = ""
            print(f"   {mark} {nm[:13]:<14} 出典 {kr.date} {kr.race_no}R "
                  f"（{x['finish']}着 {x['popularity']}人気）{res}")
        print()
    if tot:
        print(f"=== 追跡 {tot}頭中 3着内 {ok}頭 = {ok/tot:.0%} ===")
        print("  ⚠️ 素の3着内率は12〜16頭立てで20%前後。そこと比べること。")


if __name__ == "__main__":
    main()
