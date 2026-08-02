#!/usr/bin/env python3
"""出走馬を「その馬自身の過去の時計」と比べる。

    python3 scripts/nankan_selfruler.py --date 20260803 --place 船橋

    自己比 = 今回の走破タイム − その馬の同距離・良馬場のベスト
    プラス＝自分の過去より遅い / マイナス＝自己更新

⚠️⚠️ **この物差しで「今日は特別だった」と言ってはいけない。**（2026-08-03 追記）

   最初この道具は「勝ち時計と par の差では馬場が遅いのか相手が遅いのか
   区別できない、同じ馬を並べれば分かる」という触れ込みで作った。
   実際 8/02 船橋（開催初日・29日ぶり）で全110頭を測り、
   「勝ち馬ですら自分のベストより0.5秒遅い＝馬がズブい」と結論した。

   **対照日を置いたら消えた。** 1〜3着馬と7着以下の自己比の差:

       8/02 開催初日・29日空き・良   1〜3着 −0.28 / 7着以下 +0.80 / 差 1.08秒
       7/04 開催4日目・稍           1〜3着 −0.03 / 7着以下 +1.00 / 差 1.03秒
       7/02 開催3日目・不           1〜3着 −0.37 / 7着以下 +0.34 / 差 0.72秒
       6/29 開催2日目・不           1〜3着 −0.56 / 7着以下 −0.02 / 差 0.54秒

   1. **「着順が良い馬は自分の平均より速い」は定義上そうなる。** 同義反復。
      しかも 8/02 の −0.28 は 7/02・6/29 より**弱い**。
   2. 差 1.08秒は、なんでもない開催4日目 7/04 の 1.03秒とほぼ同じ。
   3. 全体の水準は **馬場状態の順に並ぶ**（濡れたダートは速い）。
      ズブさではなく水分を測っていた。

⚠️ **基準の取り方で符号がひっくり返る。** 同じ 8/02 の 1〜3着馬が
   自己ベスト基準では **+0.40秒**、自己平均基準では **−0.28秒**。
   物差しで逆に出る量を、日の性質の証拠にしないこと。
   （`best` を使うのは max 推定量と同じ罠。1本の外れ値に基準が張り付く。）

⚠️ **「落ち幅が小さい馬を買う」は使えない。** 落ち幅は走った後にしか出ない。

使ってよい範囲:
   * **1頭の振り返り**。同じ馬の同距離・同馬場の時計を並べて見る。
     例）マルヒロユートピア 5/05良 76.4(8着) → 7/02不 76.8(8着) → 8/02良 76.8(3着)。
     「同じ時計で着順が5つ上がった」という**事実**の確認まではしてよい。
     そこから「だから馬場がズブい」に進むには、対照日が要る。
   * 母数の確認。良馬場の過去走が無い馬は落ちる（8/2は110頭中65頭のみ）。
     キャリアの浅い馬・他場ばかり使う馬は測れない。母数を必ず併記すること。

⚠️ 集計（着順帯別の中央値）を根拠に使うなら、**必ず対照日を2〜3日並べる**こと。
   単日だけ見ると必ず「1〜3着はマイナス、下位はプラス」が出る。毎日出る。

比較は **同距離・良馬場** に限る。湿ったダートは速いので混ぜない。
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
