#!/usr/bin/env python3
"""**その場・その馬場状態の物差しを作る。**（例：今年の川崎・不良）

    python3 scripts/nankan_baba.py --place 川崎 --baba 不良 \
        --from 20260101 --to 20260904
    python3 scripts/nankan_baba.py --place 川崎 --baba 不良 --from 20260101 \
        --to 20260904 --jsonl data/baba_kawasaki_furyo.jsonl

出力は「距離ごとの勝ちタイム・平均ハロン・上がり」と「前後の有利不利の実測」。

── ⚠️ 恒久ルール5 との関係 ────────────────────────────

ルール5は「過去開催で**検証**しない」＝ **回収率・勝率の集計はやらない**。
このファイルは**物差し作り**であって検証ではない:

    やる     その馬場でタイムが何秒かかるか、前と後ろのどちらが残るか
    やらない 何かの買い方が当たったか、回収率がいくらか

  → **予想の材料**として、これから来る開催に当てるために作る。
     馬券の当たり外れは一切数えない。数え始めたらルール5違反になる。

── ⚠️⚠️ 決着傾向は「実測」で出す ─────────────────────

`lap.analyze` の `bias`（テン3F−上がり3F を 0 と比べる）は**南関で使えない**。
小回りでは上がりが遅くなるのが構造なので、ほぼ全レースが H＝差し有利と出る。
2026-08-07 浦和は全12レースがそう判定されたが、実測は **4角7番手以降が
116頭中0頭**という極端な前有利だった。

  → ここでは `nankan_ana.measured_bias` と同じ**通過順と着順からの実測**を使う。
     ラベルは参考として併記するだけ。

── ⚠️ 馬場の取り方 ────────────────────────────────

`rakuten.parse_baba` はヘッダの「天候：晴 ダ：稍重」だけを見る。
**ページ内を「重」で検索してはいけない**（馬体重の「重」や馬柱の過去走の
馬場を誤爆し、実際に「全レース重馬場」という誤った分析を一度出している）。

⚠️ 不良は数が少ない。**出た数をそのまま書く。**少なければ少ないと言う。
"""

from __future__ import annotations

import argparse
import json
import os
import statistics as stt
import sys
from collections import defaultdict
from datetime import date as _date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nankeiba.core import lap                               # noqa: E402
from nankeiba.scraping import rakuten as rk                 # noqa: E402
from nankan_ana import measured_bias                        # noqa: E402


def days(lo: str, hi: str):
    d = _date(int(lo[:4]), int(lo[4:6]), int(lo[6:8]))
    e = _date(int(hi[:4]), int(hi[4:6]), int(hi[6:8]))
    while d <= e:
        yield d.strftime("%Y%m%d")
        d += timedelta(days=1)


def main() -> None:
    ap = argparse.ArgumentParser(description="その場・その馬場の物差しを作る")
    ap.add_argument("--place", required=True)
    ap.add_argument("--baba", default="不良",
                    help="良 / 稍重 / 重 / 不良（カンマ区切りで複数可）")
    ap.add_argument("--from", dest="lo", required=True, help="YYYYMMDD")
    ap.add_argument("--to", dest="hi", required=True, help="YYYYMMDD")
    ap.add_argument("--jsonl")
    args = ap.parse_args()
    want = set(args.baba.split(","))

    cli = rk.KeibaRakuten()
    out = open(args.jsonl, "w", encoding="utf-8") if args.jsonl else None
    hits, scanned, meets = [], 0, 0

    for ymd in days(args.lo, args.hi):
        try:
            base = cli.find_race_id(ymd, args.place, 1)[:-2]
        except Exception:                                   # noqa: BLE001
            continue
        meets += 1
        for rno in range(1, 13):
            rid = f"{base}{rno:02d}"
            try:
                raw = cli.get(f"/race_performance/list/RACEID/{rid}")
                res = rk.parse_result(raw)
            except Exception:                               # noqa: BLE001
                continue
            if not res:
                continue
            scanned += 1
            baba = rk.parse_baba(raw)
            if baba not in want:
                continue
            try:
                card = rk.parse_card(cli.get(f"/race_card/list/RACEID/{rid}"))
                hdr = card.get("header") or {}
            except Exception:                               # noqa: BLE001
                hdr = {}
            dist = hdr.get("distance")
            if not dist:
                continue
            la = lap.analyze(res, dist, rk.parse_lap(raw))
            # ⚠️⚠️ **`parse_result` は通過順を持っていない。**本文の別ブロックに
            #    ある「コーナー通過順位」を `rk.corner4` で拾う。これを忘れると
            #    決着傾向が**全レース「測れない」**になる（実際に146レース全部が
            #    そうなった）。
            c4 = rk.corner4(raw)
            rows = [{"p": c4[x["umaban"]], "f": x["finish"]}
                    for x in res
                    if x.get("umaban") in c4 and x.get("finish")]
            win = next((x for x in res if x.get("finish") == 1), None)
            rec = {
                "date": ymd, "place": args.place, "race": rno, "baba": baba,
                "distance": dist, "race_class": hdr.get("race_class"),
                "field": len(res),
                "win_time": la.win_time, "avg_furlong": la.avg_furlong,
                "ten3f": la.ten3f, "last3f": la.last3f, "balance": la.balance,
                "pace_label": la.pace_label,
                "bias_measured": measured_bias(rows),
                "win_pop": (win or {}).get("popularity"),
                "win_name": (win or {}).get("name"),
                "top3_pop": [x.get("popularity") for x in
                             sorted((y for y in res if y.get("finish")),
                                    key=lambda y: y["finish"])[:3]],
            }
            hits.append(rec)
            if out:
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if out:
        out.close()

    print(f"\n■ {args.place}　{args.lo}〜{args.hi}")
    print(f"  開催 {meets}日／レース {scanned}／**{'・'.join(want)} は {len(hits)}レース**")
    if not hits:
        print("  該当なし。")
        return

    print("\n── 距離ごとの勝ちタイム ─────────────────────")
    by = defaultdict(list)
    for r in hits:
        if r["win_time"]:
            by[r["distance"]].append(r)
    for d in sorted(by):
        ts = [r["win_time"] for r in by[d]]
        fs = [r["avg_furlong"] for r in by[d] if r["avg_furlong"]]
        ls = [r["last3f"] for r in by[d] if r["last3f"]]
        print(f"  {d}m  n={len(ts):>2}  勝ちタイム 中央{stt.median(ts):.1f}"
              f"（{min(ts):.1f}〜{max(ts):.1f}）"
              + (f"  平均{stt.median(fs):.2f}秒/F" if fs else "")
              + (f"  上がり中央{stt.median(ls):.1f}" if ls else ""))

    print("\n── 前後の有利不利（**実測**・通過順と着順から）─────────")
    c = defaultdict(int)
    for r in hits:
        c[r["bias_measured"].split("（")[0]] += 1
    for k, v in sorted(c.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<28} {v:>3}レース")

    print("\n── 荒れたか ──────────────────────────────")
    pops = [r["win_pop"] for r in hits if r["win_pop"]]
    if pops:
        print(f"  勝ち馬の人気  中央 {stt.median(pops):.0f}番人気"
              f"／1〜3人気が勝った {sum(1 for p in pops if p<=3)}/{len(pops)}"
              f"／7人気以下が勝った {sum(1 for p in pops if p>=7)}/{len(pops)}")

    print("\n── 1レースずつ ────────────────────────────")
    for r in sorted(hits, key=lambda x: (x["date"], x["race"])):
        print(f"  {r['date']} {r['race']:>2}R {r['distance']}m "
              f"{(r['race_class'] or ''):<6}"
              + (f"{r['win_time']:.1f}秒 " if r["win_time"] else "―     ")
              + f"{r['win_name'] or '':<12}{r['win_pop'] or '-':>2}人気  "
              f"{r['bias_measured']}")

    print("\n⚠️ これは**物差し**であって検証ではない。馬券の当たり外れは数えていない。")
    print("⚠️ 決着傾向は通過順と着順からの実測。lap.analyze のラベルは南関では"
          "ほぼ全部『差し有利』と出るので使っていない。")


if __name__ == "__main__":
    main()
