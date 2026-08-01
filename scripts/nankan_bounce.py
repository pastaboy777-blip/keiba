#!/usr/bin/env python3
"""「負けた馬が次走・次々走で馬券になった」レースを探す ── 刺激レース。

ユーザー指定（2026-08-01）:
    「負けた馬たちが次やその次のレースで馬券になった刺激となったレース」

    巻き返し率 = 4着以下だった馬のうち、次走か次々走で3着以内に来た馬の割合

**勝ち馬は数えない。** 勝った馬は昇級して負けるだけでノイズになる。狙いは
「強い相手に揉まれて着順を落とし、次に人気を落として出てくる馬」なので、
測るべきは敗戦馬のその後だけ。

⚠️ **「全出走馬の次走勝率」で測ってはいけない。** それだと2つ壊れる。
   1. クラスと逆相関する。実測で メンバーの格 × 次走勝率 = **−0.194**。
      A級の馬は次走もA級で勝ちにくく、C3の馬は次走もC3で勝ちやすい。
      次走勝率で並べると**下級条件が上位に来る**。「レベルが高い」の逆。
   2. 再現しない。1レースの出走馬を奇数/偶数に割り、奇数馬の次走勝率で
      並べて偶数馬の成績を見ると、南関286レースで相関 **−0.113**
      （上位1/5→4.2% / 下位1/5→9.9% / 全体7.4%）。逆向きだった。
      ※ 南関は同じメンバーが次走でまた当たる（共食い）ので、逆向きを
        そのまま「有害」とは言えない。だが「実在する」証拠にはならない。

   敗戦馬の3着内に絞ると向きが正しくなる（下の `--check` で毎回確認できる）。

⚠️ これは**振り返り専用**。「その後」を使うので当日の予想には使えない。
   過去のレースを評価して、そこの敗戦馬を次に拾う、という使い方。

⚠️ 上位を選んだ時点で選択バイアスが乗る。Wilson下限は母数の小ささには効くが、
   **多数から上位を選ぶバイアスには効かない**。必ず `--check` を通すこと。

    python3 scripts/nankan_bounce.py --place 船橋 --year 2026
    python3 scripts/nankan_bounce.py --place 川崎 --top 20 --detail 5 --check
"""

from __future__ import annotations

import argparse
import glob
import math
import os
import statistics as st
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import thickness as th                # noqa: E402
from nankeiba.core.datapath import cache_dir             # noqa: E402
from nankeiba.scraping import rakuten as rk              # noqa: E402


def load(cdir: str):
    """馬ごとの全走と、レースごとの出走名簿を作る。"""
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


def wilson_lo(k: int, n: int, z: float = 1.28) -> float:
    """勝率の下側信頼限界（90%）。母数の小さいレースが上位を占めるのを防ぐ。

    ⚠️ これで防げるのは母数の小ささだけ。**選択バイアスは防げない。**
    """
    if not n:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    return ((p + z * z / (2 * n))
            - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", default="船橋")
    ap.add_argument("--year", default="2026")
    ap.add_argument("--lose-from", type=int, default=4, help="何着以下を敗戦馬とみなすか")
    ap.add_argument("--look", type=int, default=2, help="次走から何走先まで見るか")
    ap.add_argument("--hit", type=int, default=3, help="何着以内を『馬券になった』とするか")
    ap.add_argument("--min-losers", type=int, default=5, help="その後を追えた敗戦馬の下限")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--detail", type=int, default=3, help="中身を出すレース数")
    ap.add_argument("--check", action="store_true", help="半分こテストで再現性を見る")
    args = ap.parse_args()

    print("キャッシュを読み込み中…", file=sys.stderr)
    runs, roster = load(str(cache_dir()))
    lv = {r.key: r for r in th.scan()}
    print(f"  馬 {len(runs)} / 名簿 {len(roster)}", file=sys.stderr)

    def after(nm, d, k):
        ds = sorted(x for x in runs.get(nm, {}) if x > d)
        return [runs[nm][x] for x in ds[:k]]

    out = []
    for (d, pl, di), ros in roster.items():
        if pl != args.place or not d.startswith(args.year):
            continue
        r = lv.get((d, pl, di, len(ros)))
        if r is None:
            continue
        det, n = [], 0
        for nm, f in ros:
            if f < args.lose_from:
                continue
            nx = after(nm, d, args.look)
            if not nx:
                continue
            n += 1
            hit = next((x for x in nx if x.finish_pos <= args.hit), None)
            if hit:
                det.append((nm, f, hit))
        if n >= args.min_losers:
            out.append((len(det) / n, len(det), n, r, det))
    if not out:
        print(f"{args.year}年 {args.place} に該当レースがない。", file=sys.stderr)
        sys.exit(1)

    hits = sum(x[1] for x in out)
    tot = sum(x[2] for x in out)
    base = hits / tot
    print(f"\n=== {args.year}年 {args.place} {len(out)}レース ===")
    print(f"{args.lose_from}着以下だった馬が、次走〜{args.look}走先までに"
          f"{args.hit}着以内に来た率")
    print(f"  全体 {hits}/{tot} = {base:.1%}  ← これがベースライン\n")

    out.sort(key=lambda x: -wilson_lo(x[1], x[2]))
    print(f"■ 刺激になったレース 上位{args.top}（母数補正・Wilson下限順）")
    print(f"  {'日付':<11}{'R':>3}{'距離':>7}{'頭':>4}  {'敗戦馬の巻き返し':<13}"
          f"{'倍率':>6} {'濃さ':>7}{'時計':>7}")
    for rate, h, n, r, det in out[:args.top]:
        t = f"{r.thick:+.1f}" if r.thick is not None else "   - "
        v = f"{r.time_lv:+.2f}" if r.time_lv is not None else "   -  "
        print(f"  {r.date:<11}{r.race_no or 0:>3}{r.distance:>6}m{r.field_size:>4}  "
              f"{h}/{n}={rate:>5.0%}      {rate / base:>5.2f} {t:>7}{v:>7}")

    if args.detail:
        print(f"\n■ 上位{args.detail}レースの中身（誰がどこで巻き返したか）")
        for rate, h, n, r, det in out[:args.detail]:
            print(f"\n  ● {r.date} {r.place}{r.race_no}R ダ{r.distance}m "
                  f"{r.field_size}頭（濃さ{r.thick} / 時計{r.time_lv}）")
            for nm, f, x in sorted(det, key=lambda z: z[1]):
                print(f"      {f:>2}着 {nm:<14} → {x.date} {x.place}{x.distance}m "
                      f"{x.finish_pos}着  {(x.race_name or '').strip()[:16]}")

    if args.check:
        print("\n■ 検算 半分こテスト（敗戦馬を奇数/偶数に割る）")
        print("  奇数側の巻き返し率で並べたとき、偶数側（＝別の馬）も高いか。")
        print("  高ければ『レースの刺激』は実在する。そうでなければ選んだだけ。")
        pr = []
        for _, _, _, r, _ in out:
            ls = [(nm, f) for nm, f in roster[(r.date, r.place, r.distance)]
                  if f >= args.lose_from]

            def rate_of(g):
                c = t = 0
                for nm, f in g:
                    nx = after(nm, r.date, args.look)
                    if not nx:
                        continue
                    t += 1
                    c += any(x.finish_pos <= args.hit for x in nx)
                return c / t if t >= 2 else None
            a, b = rate_of(ls[0::2]), rate_of(ls[1::2])
            if a is not None and b is not None:
                pr.append((a, b))
        if len(pr) < 20:
            print(f"  {len(pr)}レースしか作れず、検算にならない。")
            return
        A = [p[0] for p in pr]
        B = [p[1] for p in pr]
        ma, mb = st.mean(A), st.mean(B)
        sa = math.sqrt(sum((x - ma) ** 2 for x in A))
        sb = math.sqrt(sum((y - mb) ** 2 for y in B))
        c = sum((x - ma) * (y - mb) for x, y in zip(A, B)) / (sa * sb) if sa and sb else 0
        k = max(1, len(pr) // 4)
        top = sorted(range(len(pr)), key=lambda i: -A[i])[:k]
        bot = sorted(range(len(pr)), key=lambda i: A[i])[:k]
        print(f"  {len(pr)}レース / 相関 {c:+.3f}（目安の誤差 ±{1/math.sqrt(len(pr)):.2f}）")
        print(f"  奇数側で上位1/4 → 偶数側の巻き返し率 {st.mean([B[i] for i in top]):.1%}")
        print(f"  奇数側で下位1/4 → 偶数側の巻き返し率 {st.mean([B[i] for i in bot]):.1%}")
        print(f"  （全体 {base:.1%}）")
        if abs(c) < 1 / math.sqrt(len(pr)):
            print("  ⚠️ 相関が誤差の範囲。**この母数では効いているとは言えない。**")


if __name__ == "__main__":
    main()
