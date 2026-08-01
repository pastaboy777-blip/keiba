#!/usr/bin/env python3
"""その日の傾向と**真逆の競馬**をして、強い内容で負けた馬を拾う。

ユーザー指定（2026-08-01）:
    「その傾向と真逆の競馬して強い内容で負けた馬をピックアップして」

南関の実測（2026年5〜6月 船橋 144レース）で分かった傾向は2つ。

  ① ペースは **H が87%**。`lap` の判定では H ＝ **差し・追込有利（前が垂れる
     消耗戦）**。つまり船橋は「前が飛ばして垂れ、後ろが差す」のが平常運転。
  ② **12日中7日で日中に馬場が速くなる**（ドリフトがマイナス）。
     つまり**前半レースほど遅い馬場**を走らされている。

⚠️ ①を「前が止まらない流れ」と読み違えないこと。**H は前が垂れる流れ**であって、
   前有利ではない。逆に取ると、拾う馬が真逆になる（実際やらかした）。

したがって**傾向と真逆の競馬**とは

    「前が垂れる流れを、それでも前で受けて、僅差で粘った馬」
    「しかも遅い時間帯の馬場で、それをやった馬」

差して届かなかった馬は**流れに乗って負けた**だけで、逆らってはいない。

拾い方:
    上がり順位が**下位**（＝前で運んだ代理） かつ 着順4着以下 かつ 勝ち馬との差が小さい

⚠️ **南関の結果ページには通過順が無い**（楽天も競馬ブックも ** でマスクされる）ので、
   脚質を直接は確認できない。**「上がりが遅いのに僅差」＝前で粘った**を代理にしている。
   `--style close` で逆（上がり最速で着外＝流れに乗って届かなかった馬）も出せる。

⚠️ ペース判定 H/M/S はこの母集団では **87%がH** で、ほとんど区別になっていない。
   `lap._judge` の閾値が中央向けのままで、南関のダート短距離に合っていない。
   なので「Hだから逆らった」とは言い切れない。フィルタとしては弱い。

⚠️ 「その後どうだったか」を出すのは**振り返りのため**。当日の予想には使えない。

    python3 scripts/nankan_against.py --place 船橋 --from 2026-05-01 --to 2026-06-30
    python3 scripts/nankan_against.py --place 川崎 --from 2026-07-01 --agari-rank 1
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from collections import defaultdict
from statistics import median

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import lap as lapmod                  # noqa: E402
from nankeiba.core import thickness as th                # noqa: E402
from nankeiba.core import track_bias                     # noqa: E402
from nankeiba.core.datapath import cache_dir             # noqa: E402
from nankeiba.scraping import rakuten as rk              # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", default="船橋")
    ap.add_argument("--from", dest="lo", required=True)
    ap.add_argument("--to", dest="hi", default="9999-99-99")
    ap.add_argument("--style", choices=("front", "close"), default="front",
                    help="front=前で粘って負けた(傾向と真逆) / close=差して届かなかった")
    ap.add_argument("--agari-frac", type=float, default=0.6,
                    help="front: 上がり順位が頭数のこの割合より下なら『前で運んだ』")
    ap.add_argument("--agari-rank", type=int, default=2,
                    help="close: 上がり順位の上限")
    ap.add_argument("--from-finish", type=int, default=4, help="何着以下を対象にするか")
    ap.add_argument("--max-margin", type=float, default=1.0,
                    help="勝ち馬との差の上限[秒]。これ以内なら『強い内容』とみなす")
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    cdir = str(cache_dir())
    print("キャッシュを読み込み中…", file=sys.stderr)

    # その後の走り（振り返り用）
    runs: dict = defaultdict(dict)
    for cf in sorted(glob.glob(os.path.join(cdir, "race_card_list_RACEID_*.html"))):
        try:
            card = rk.parse_card(open(cf, encoding="utf-8").read())
        except Exception:                                # noqa: BLE001
            continue
        for e in card["entries"]:
            for r in e["history"]:
                if r.finish_pos:
                    runs[e["name"]][r.date] = r

    lv = {r.key: r for r in th.scan()}
    day_win: dict = defaultdict(list)
    raws = []
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
            raw = open(pf, encoding="utf-8").read()
            res = rk.parse_result(raw)
        except Exception:                                # noqa: BLE001
            continue
        if hd.get("place") != args.place or not hd.get("distance") or not res:
            continue
        if res[0].get("time_sec"):
            day_win[d].append(dict(race_no=hd.get("race_no") or 0, place=args.place,
                                   distance=hd["distance"],
                                   win_time=res[0]["time_sec"]))
        raws.append((d, hd, res, lapmod.analyze(res, hd["distance"], rk.parse_lap(raw))))

    drift = {d: track_bias.measure(v, place=args.place).drift for d, v in day_win.items()}

    hits = []
    for d, hd, res, la in raws:
        di, rno = hd["distance"], hd.get("race_no") or 0
        wt = res[0].get("time_sec")
        ags = sorted(r["agari"] for r in res if r.get("agari"))
        if not wt or len(ags) < 4:
            continue
        r_lv = lv.get((d, args.place, di, len(res)))
        dr = drift.get(d)
        for r in res:
            a, t, f = r.get("agari"), r.get("time_sec"), r.get("finish")
            if not a or not t or not f or f < args.from_finish:
                continue
            arank = ags.index(a) + 1
            margin = round(t - wt, 1)
            if margin > args.max_margin:
                continue
            if args.style == "front":
                if arank < len(ags) * args.agari_frac:
                    continue                     # 上がりが速い＝流れに乗った側
            elif arank > args.agari_rank:
                continue
            # 逆行度
            tags = []
            if la.pace == "H":
                tags.append("前が垂れる流れ(H)を前で受けた"
                            if args.style == "front" else "前が垂れる流れ(H)に乗った")
            if dr is not None and dr < -0.10 and rno <= 6:
                tags.append(f"馬場が遅い時間帯(ドリフト{dr:+.2f})")
            if r_lv and r_lv.thick is not None and r_lv.thick <= -1.0:
                tags.append(f"濃いレース({r_lv.thick:+.1f})")
            nx = [runs[r["name"]][x]
                  for x in sorted(y for y in runs.get(r["name"], {}) if y > d)[:2]]
            hits.append(dict(date=d, rno=rno, dist=di, fld=len(res), name=r["name"],
                             fin=f, agari=a, arank=arank, margin=margin,
                             pop=r.get("popularity"), tags=tags, nx=nx,
                             score=(len(tags), -margin, -arank)))

    if not hits:
        print("該当なし。", file=sys.stderr)
        sys.exit(1)
    hits.sort(key=lambda h: h["score"], reverse=True)

    bounced = sum(1 for h in hits if any(x.finish_pos <= 3 for x in h["nx"]))
    tracked = sum(1 for h in hits if h["nx"])
    print(f"\n=== {args.place} {args.lo}〜{args.hi} "
          + ("傾向（差し有利）に逆らい、前で粘って負けた馬 "
             if args.style == "front" else "流れに乗って差して届かなかった馬 ")
          + f"{len(hits)}頭 ===")
    cond = (f"上がり順位が下位{1-args.agari_frac:.0%}（＝前で運んだ代理）"
            if args.style == "front" else f"上がり{args.agari_rank}位以内")
    print(f"  条件: {cond} × {args.from_finish}着以下 × "
          f"勝ち馬との差{args.max_margin}秒以内")
    if tracked:
        print(f"  その後: 次走〜次々走で3着内 {bounced}/{tracked} = {bounced/tracked:.0%}"
              f"（4着以下の馬ぜんぶだと 26.9%）\n")

    for h in hits[:args.top]:
        nx = " / ".join(f"{x.date} {x.place}{x.distance}m {x.finish_pos}着"
                        for x in h["nx"]) or "その後の出走なし"
        mark = "◎" if any(x.finish_pos <= 3 for x in h["nx"]) else "　"
        print(f"{mark}{h['date']} {args.place}{h['rno']:>2}R {h['dist']}m {h['fld']}頭  "
              f"{h['name']:<14} {h['fin']:>2}着 差{h['margin']:+.1f} "
              f"上がり{h['agari']}({h['arank']}位)"
              + (f" {h['pop']}人気" if h["pop"] else ""))
        if h["tags"]:
            print(f"        逆行: {' / '.join(h['tags'])}")
        print(f"        その後: {nx}")


if __name__ == "__main__":
    main()
