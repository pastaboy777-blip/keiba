#!/usr/bin/env python3
"""出走馬を「その馬自身の過去の時計」と比べる ── 馬場か、相手か、を分ける物差し。

    python3 scripts/nankan_selfruler.py --date 20260803 --place 船橋

⚠️ **勝ち時計と par の差では「馬場が遅い」と「相手が遅い」を区別できない。**
   区別するには同じ馬の同条件の時計を並べるしかない。

きっかけ（2026-08-02 船橋8R）:
    マルヒロユートピアが 7/02 と**まったく同じ 76.8秒**で 8着 → 3着。
    3走前の良（5/05）の 76.4秒に対しても **0.4秒遅い**のに着順は5つ上。
    → 馬場は5月の良と同じ速さ。落ちたのは相手。

全頭で見ると例外ではなかった（8/2・比較できた65頭）:

    着順      頭数  自己比の中央値  自己更新した割合
    1着        4     +0.5秒         25%
    2〜3着    14     +0.2秒         36%
    4〜5着    13     +0.7秒         23%
    6着以下   34     +1.6秒         15%

    **勝ち馬ですら自分のベストより0.5秒遅い。** 1番人気が3頭とも
    自己比 +1.7〜+3.3秒で馬券圏内（7R ナムラペルル +3.3 など）。
    自己更新できたのは2頭だけで、どちらも他場帰り。

距離帯でも差が出た（同じ日・1〜3着馬の自己比）:

    1200m +0.4秒 / 1500m +0.1秒 / 1600m +0.8秒 / 1800m +0.0秒

    par 基準で見た 1200m +0.200 s/F 対 1500m +0.067 s/F と同じ向き。
    **別々の測り方で同じ結論**が出たので、見かけではない。
    開催が29日空いてズブい馬場では、1200mの忙しさに対応できず、
    1500m以上なら流れが落ち着いて自分の走りができる、と読める。

比較は **同距離・良馬場** に限る。湿ったダートは速いので混ぜない。
    自己比 = 今回の走破タイム − その馬の同距離・良馬場のベスト
    プラス＝自分の過去より遅い / マイナス＝自己更新

⚠️ 良馬場の過去走が無い馬は比較できない（8/2は110頭中65頭のみ）。
   キャリアの浅い馬・他場ばかり使う馬は落ちる。母数を必ず併記すること。
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from statistics import median

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import rakuten as rk              # noqa: E402


def collect(cli, date: str, place: str, races=range(1, 13)):
    base = cli.find_race_id(date, place, 1)[:-2]
    rows = []
    for rno in races:
        rid = f"{base}{rno:02d}"
        try:
            card = rk.fetch_card(cli, rid)
            res = rk.parse_result(cli.get(f"/race_performance/list/RACEID/{rid}"))
        except Exception:                                # noqa: BLE001
            continue
        if not res:
            continue
        di = card["header"]["distance"]
        ent = {e["name"]: e for e in card["entries"]}
        for x in res:
            t = x.get("time_sec")
            e = ent.get(x["name"])
            if not t or not e:
                continue
            h = e.get("history") or []
            good = [r for r in h if r.distance == di and r.time_sec
                    and (r.baba or "").startswith("良")]
            rows.append(dict(rno=rno, di=di, name=x["name"], fin=x.get("finish"),
                             pop=x.get("popularity"), t=t, n_good=len(good),
                             best=(min(r.time_sec for r in good) if good else None)))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYYMMDD")
    ap.add_argument("--place", default="船橋")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    cli = rk.KeibaRakuten()
    rows = collect(cli, args.date, args.place)
    if not rows:
        print("結果がまだ出ていない（または取得できない）。", file=sys.stderr)
        sys.exit(1)
    G = [r for r in rows if r["best"]]
    for r in G:
        r["sd"] = round(r["t"] - r["best"], 1)

    print(f"=== {args.date} {args.place}　自分の過去の時計と比べる"
          f"（同距離・良馬場のベスト基準） ===")
    print(f"  比較できたのは {len(G)}頭 / 全{len(rows)}頭\n")
    print(f"  {'着順':<10}{'頭数':>5}{'自己比の中央値':>15}{'自己更新した割合':>17}")
    for lo, hi, nm in ((1, 1, "1着"), (2, 3, "2〜3着"), (4, 5, "4〜5着"), (6, 99, "6着以下")):
        s = [r for r in G if r["fin"] and lo <= r["fin"] <= hi]
        if not s:
            continue
        up = sum(1 for r in s if r["sd"] < 0)
        print(f"  {nm:<10}{len(s):>5}{median(r['sd'] for r in s):>+14.1f}秒"
              f"{up / len(s):>16.0%}")
    print("\n  ※ プラス＝自分の過去より遅い。1〜3着でもプラスなら「相手が落ちた」話。")

    print("\n=== 距離帯で分ける ===")
    print(f"  {'距離':>7}{'頭数':>5}{'自己比の中央値':>15}{'1〜3着の自己比':>16}")
    for di in sorted({r["di"] for r in G}):
        s = [r for r in G if r["di"] == di]
        top = [r for r in s if r["fin"] and r["fin"] <= 3]
        if len(s) < 4:
            continue
        tv = f"{median(r['sd'] for r in top):+.1f}秒" if top else "―"
        print(f"  {di:>6}m{len(s):>5}{median(r['sd'] for r in s):>+14.1f}秒{tv:>16}")

    print("\n=== 1〜3着馬（自己比の悪い順＝相手に恵まれた順） ===")
    top = [r for r in G if r["fin"] and r["fin"] <= 3]
    for r in sorted(top, key=lambda x: -x["sd"])[:args.top]:
        print(f"  {r['rno']:>2}R {r['di']}m {r['name'][:12]:<13}{r['fin']}着 "
              f"{(str(r['pop']) + '人気' if r['pop'] else '?'):>6} "
              f"今回{r['t']:.1f} 自己ベスト{r['best']:.1f}（良{r['n_good']}走）"
              f" 自己比{r['sd']:+.1f}秒")


if __name__ == "__main__":
    main()
