#!/usr/bin/env python3
"""南関の開催を**1日ずつ**振り返る。日ごとの傾向をまとめて出す。

CLAUDE.md 恒久ルール1「結果が出たら必ずラップ（ペース）分析もする」に沿って、
着順の当たり外れではなく**その日の馬場と流れ**を出す。

各日について:
  当日馬場差B     … 勝ち馬par からの差[s/F]。マイナスが速い。
  ドリフト        … 開催前半→後半で馬場がどう動いたか。散水・砂の掘れ・気温で
                    同じ日でも動く。プラスなら遅くなってきている。
  ペース分布      … H（前傾＝速い入り）/ M / S（後傾＝上がり勝負）の本数
  決着傾向        … 前残り / 差し の本数
  時計水準        … 標準からの差の中央値[秒]。プラスが速い。
  上がり最速      … その日いちばん速い上がりを使った馬
  濃かったレース  … テン3F差＋上がり差（馬場補正後）が小さい順
  刺激レース      … 4着以下だった馬が次走〜次々走で3着内に来た割合

⚠️ 「濃さ」と「刺激」は別物。実測で上位の刺激レースは**時計が標準より遅い**
   ことが多い（§30）。並べて出すが、片方でもう片方を代用しないこと。

⚠️ 「刺激」は**その後**を使うので当日の予想には使えない。振り返り専用。

    python3 scripts/nankan_days.py --place 船橋 --from 2026-05-01 --to 2026-06-30
    python3 scripts/nankan_days.py --place 川崎 --from 2026-07-01 --brief
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from collections import Counter, defaultdict
from statistics import median

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import lap as lapmod                  # noqa: E402
from nankeiba.core import thickness as th                # noqa: E402
from nankeiba.core import track_bias                     # noqa: E402
from nankeiba.core.datapath import cache_dir             # noqa: E402
from nankeiba.scraping import rakuten as rk              # noqa: E402


def load_day_extras(cdir: str, place: str, lo: str, hi: str):
    """日ごとの生データ（馬場差の材料・上がり最速馬）を集める。"""
    day_win: dict = defaultdict(list)
    day_ag: dict = defaultdict(list)
    for pf in sorted(glob.glob(os.path.join(
            cdir, "race_performance_list_RACEID_*.html"))):
        rid = pf.rsplit("_", 1)[-1].removesuffix(".html")
        d = f"{rid[0:4]}-{rid[4:6]}-{rid[6:8]}"
        if not (lo <= d <= hi):
            continue
        cf = os.path.join(cdir, f"race_card_list_RACEID_{rid}.html")
        if not os.path.exists(cf):
            continue
        try:
            hd = rk.parse_card(open(cf, encoding="utf-8").read())["header"]
            res = rk.parse_result(open(pf, encoding="utf-8").read())
        except Exception:                                # noqa: BLE001
            continue
        if hd.get("place") != place or not hd.get("distance") or not res:
            continue
        if res[0].get("time_sec"):
            day_win[d].append(dict(race_no=hd.get("race_no") or 0, place=place,
                                   distance=hd["distance"],
                                   win_time=res[0]["time_sec"]))
        for r in res:
            if r.get("agari"):
                day_ag[d].append((r["agari"], r.get("name"), hd.get("race_no"),
                                  hd["distance"], r.get("finish")))
    return day_win, day_ag


def load_bounce(cdir: str):
    """馬ごとの全走と出走名簿（刺激レース用）。"""
    runs: dict = defaultdict(dict)
    roster: dict = {}
    for cf in sorted(glob.glob(os.path.join(cdir, "race_card_list_RACEID_*.html"))):
        try:
            card = rk.parse_card(open(cf, encoding="utf-8").read())
        except Exception:                                # noqa: BLE001
            continue
        for e in card["entries"]:
            for r in e["history"]:
                if r.finish_pos:
                    runs[e["name"]][r.date] = r
    for pf in sorted(glob.glob(os.path.join(
            cdir, "race_performance_list_RACEID_*.html"))):
        rid = pf.rsplit("_", 1)[-1].removesuffix(".html")
        cf = os.path.join(cdir, f"race_card_list_RACEID_{rid}.html")
        if not os.path.exists(cf):
            continue
        try:
            hd = rk.parse_card(open(cf, encoding="utf-8").read())["header"]
            res = rk.parse_result(open(pf, encoding="utf-8").read())
        except Exception:                                # noqa: BLE001
            continue
        if hd.get("place") and hd.get("distance") and res:
            roster[(f"{rid[0:4]}-{rid[4:6]}-{rid[6:8]}", hd["place"], hd["distance"])] = \
                [(r["name"], r["finish"]) for r in res if r.get("name")]
    return runs, roster


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", default="船橋")
    ap.add_argument("--from", dest="lo", required=True)
    ap.add_argument("--to", dest="hi", default="9999-99-99")
    ap.add_argument("--brief", action="store_true", help="1日1行にまとめる")
    ap.add_argument("--no-bounce", action="store_true", help="刺激レースを出さない")
    args = ap.parse_args()

    cdir = str(cache_dir())
    print("キャッシュを読み込み中…", file=sys.stderr)
    races = [r for r in th.scan()
             if r.place == args.place and args.lo <= r.date <= args.hi]
    if not races:
        print(f"{args.place} の {args.lo}〜{args.hi} がキャッシュに無い。", file=sys.stderr)
        sys.exit(1)
    day_win, day_ag = load_day_extras(cdir, args.place, args.lo, args.hi)
    runs = roster = None
    if not args.no_bounce:
        runs, roster = load_bounce(cdir)

    by_day: dict = defaultdict(list)
    for r in races:
        by_day[r.date].append(r)
    days = sorted(by_day)
    print(f"\n=== {args.place} {days[0]}〜{days[-1]} 全{len(days)}日 "
          f"/ {len(races)}レース ===\n")

    def bounce(r):
        """そのレースの敗戦馬が次走〜次々走で3着内に来た割合。"""
        if roster is None:
            return None
        ros = roster.get((r.date, r.place, r.distance))
        if not ros or len(ros) != r.field_size:
            return None
        h = n = 0
        for nm, f in ros:
            if f < 4:
                continue
            ds = sorted(x for x in runs.get(nm, {}) if x > r.date)[:2]
            if not ds:
                continue
            n += 1
            h += any(runs[nm][x].finish_pos <= 3 for x in ds)
        return (h, n) if n >= 4 else None

    for d in days:
        rs = sorted(by_day[d], key=lambda r: r.race_no or 0)
        tb = track_bias.measure(day_win.get(d, []), place=args.place)
        pace = Counter(r.pace for r in rs)
        bias = Counter(r.bias for r in rs if getattr(r, "bias", None))
        lv = [r.time_lv for r in rs if r.time_lv is not None]
        drift = tb.drift
        head = (f"■ {d}（{len(rs)}R）　馬場差 {tb.offset:+.2f} s/F {tb.label}"
                + (f"　ドリフト {drift:+.2f}" if drift is not None else "")
                + (f"　時計水準 {median(lv):+.2f}秒" if lv else ""))
        print(head)
        pl = " / ".join(f"{k}{v}本" for k, v in pace.most_common() if k)
        print(f"    ペース {pl}"
              + (f"　決着 " + " / ".join(f"{k}{v}" for k, v in bias.most_common())
                 if bias else ""))
        if drift is not None and abs(drift) >= 0.15:
            print(f"    ⚠️ 日中で馬場が {abs(drift):.2f} s/F "
                  f"{'遅く' if drift > 0 else '速く'}なっている。"
                  f"1日平均を後半レースに当てないこと")
        ag = sorted(day_ag.get(d, []))[:3]
        if ag and not args.brief:
            print("    上がり最速 " + " / ".join(
                f"{a:.1f} {nm}({rn}R {di}m {fi}着)" for a, nm, rn, di, fi in ag))
        thick = [r for r in rs if r.thick is not None]
        thick.sort(key=lambda r: r.thick)
        if thick and not args.brief:
            print("    濃いレース " + " / ".join(
                f"{r.race_no}R({r.distance}m) 濃さ{r.thick:+.1f}" for r in thick[:2]))
        if not args.no_bounce and not args.brief:
            bs = [(b, r) for r in rs if (b := bounce(r))]
            bs.sort(key=lambda x: -(x[0][0] / x[0][1]))
            if bs:
                print("    刺激レース " + " / ".join(
                    f"{r.race_no}R({r.distance}m) 敗戦馬{h}/{n}"
                    for (h, n), r in bs[:2]))
        print()

    # --- 期間まとめ ---------------------------------------------------------
    print("=== 期間まとめ ===")
    allp = Counter(r.pace for r in races if r.pace)
    allb = Counter(r.bias for r in races if getattr(r, "bias", None))
    print("  ペース " + " / ".join(f"{k}{v}本({v/len(races):.0%})"
                                  for k, v in allp.most_common()))
    if allb:
        print("  決着   " + " / ".join(f"{k}{v}本({v/len(races):.0%})"
                                      for k, v in allb.most_common()))
    offs = []
    for d in days:
        tb = track_bias.measure(day_win.get(d, []), place=args.place)
        offs.append((tb.offset, d, tb.n_races))
    offs.sort()
    print(f"  馬場差の中央値 {median([o for o, _, _ in offs]):+.2f} s/F")
    print("  いちばん速かった日 " + " / ".join(
        f"{d} {o:+.2f}" for o, d, _ in offs[:3]))
    print("  いちばん遅かった日 " + " / ".join(
        f"{d} {o:+.2f}" for o, d, _ in offs[-3:][::-1]))
    if not args.no_bounce:
        tot = [(b, r) for r in races if (b := bounce(r))]
        if tot:
            h = sum(x[0][0] for x in tot)
            n = sum(x[0][1] for x in tot)
            print(f"  敗戦馬の巻き返し 全体 {h}/{n} = {h/n:.1%}")
            tot.sort(key=lambda x: -(x[0][0] / x[0][1]))
            print("  刺激レース上位 " + " / ".join(
                f"{r.date} {r.race_no}R {r.distance}m {hh}/{nn}"
                for (hh, nn), r in tot[:5]))


if __name__ == "__main__":
    main()
