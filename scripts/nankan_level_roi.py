# -*- coding: utf-8 -*-
"""『高レベル戦の敗戦馬を次走で買ったら増えるか』を実測する。

ここまで（2026-08-01）で分かっているのは「そういうレースがある」までで、
買って増えるかは測っていなかった。トラックマン表のメンバー軸はこの一点に懸かっている。

測り方で気をつける点が2つある。どちらも外すと数字が勝手に良くなる。

  ① 自分自身を除く（leave-one-out）
     レースRのレベルは「Rの敗戦馬たちのその後」で作る。そのRの敗戦馬hを次走で買うなら、
     h自身の次走成績はレベルの材料から抜かねばならない。抜かないと
     「次走で勝った馬がいたレースは高レベル」→「その馬を買う」で、勝ちを二度数える。

  ② 買う時点で見えている情報だけを使う（因果版）
     ①を直しても、他馬の後続がhの次走より後に走ったものなら、買う時点では見えていない。
     実際に賭けられるかを測るなら、hの次走より前に済んだ後続だけでレベルを作る必要がある。

  全情報版と因果版を両方出す。全情報版だけが良くて因果版が消えるなら、
  それは「後から見れば分かる」だけで、売り物にはならない。

  比較の基準は同じ母集団の平均（＝敗戦馬を無差別に次走で買ったときの回収率）に置く。
  控除率のぶん元から75%前後に沈むので、「100%を超えたか」ではなく
  「無差別買いより上か」で見る。

    python3 scripts/nankan_level_roi.py --from 2026-02-01 --to 2026-06-15
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from nankeiba.scraping.client import PoliteClient

from nankan_racelevel import VENUES, collect
from nankan_zubu_backtest import PERF, payouts


def buckets(vals, n=5):
    """値を n 分位の境目に落とす。"""
    s = sorted(vals)
    return [s[int(len(s) * (i + 1) / n)] for i in range(n - 1)] if len(s) >= n else []


def which(v, cuts):
    for i, c in enumerate(cuts):
        if v <= c:
            return i
    return len(cuts)


def report(title, bets, cuts, labels):
    """束ごとに 的中率・単複回収率 を出す。"""
    def line(name, g):
        w = sum(1 for b in g if b["tan"])
        p = sum(1 for b in g if b["fuku"])
        # 回収率の誤差。払戻は歪んでいるので、点数が同じでも単勝のほうが桁違いに揺れる。
        # これを出さないと「複勝88%」を勝ったつもりで読んでしまう。
        se = lambda k: st.pstdev([b[k] for b in g]) / len(g) ** 0.5
        print(f"{name:<14}{len(g):>6}{w / len(g) * 100:>6.1f}%{p / len(g) * 100:>7.1f}%"
              f"{sum(b['tan'] for b in g) / len(g):>8.1f}%±{se('tan'):<5.0f}"
              f"{sum(b['fuku'] for b in g) / len(g):>7.1f}%±{se('fuku'):<4.0f}")

    print(f"\n■ {title}")
    print(f"{'区分':<14}{'点数':>6}{'勝率':>7}{'複勝率':>8}{'単回収':>9}{'':<6}{'複回収':>7}")
    grp = defaultdict(list)
    for b in bets:
        grp[which(b["z"], cuts)].append(b)
    for i in sorted(grp):
        line(labels[i], grp[i])
    line("── 無差別 ──", bets)


def main():
    ap = argparse.ArgumentParser(description="高レベル戦の敗戦馬を次走で買う回収率")
    ap.add_argument("--from", dest="d_from", required=True, help="評価するレースの開始日")
    ap.add_argument("--to", dest="d_to", required=True, help="評価するレースの終了日")
    ap.add_argument("--losers", type=int, default=4, help="この着順以下を『敗戦馬』とする")
    ap.add_argument("--min-cover", type=int, default=5,
                    help="自分を除いてこの頭数ぶん後続が取れないレースは判定しない")
    ap.add_argument("--shrink", type=float, default=8.0)
    ap.add_argument("--tail", type=int, default=60, help="次走を探す期間を何日ぶん余分に取るか")
    args = ap.parse_args()

    client = PoliteClient(use_cache=True)
    d0, d1 = date.fromisoformat(args.d_from), date.fromisoformat(args.d_to)
    races, timeline = collect(client, VENUES, d0, d1 + timedelta(days=args.tail))

    # 各馬の「そのレース以降の着順スコア」を引きやすい形に持ち替える
    later_of = {h: v for h, v in timeline.items()}

    # 全体平均（縮め先）。敗戦馬の後続スコアだけで作る。
    tot, cnt = 0.0, 0
    for rid, r in races.items():
        if not (d0 <= r["date"] <= d1):
            continue
        for row in r["rows"]:
            if row.finish_pos < args.losers:
                continue
            lt = [x for x in later_of.get(row.horse_id, []) if x[0] > r["date"]]
            if lt:
                tot += st.mean(x[2] for x in lt)
                cnt += 1
    if not cnt:
        raise SystemExit("後続が取れない。期間を早めに取ること。")
    g = tot / cnt
    print(f"\n収集 {len(races)}レース／敗戦馬の後続平均 {g:.3f}（縮め先）")

    # ---- 候補（レース, 敗戦馬）を作る
    cand = []
    for rid, r in races.items():
        if not (d0 <= r["date"] <= d1):
            continue
        beaten = [row for row in r["rows"] if row.finish_pos >= args.losers]
        if len(beaten) < args.min_cover + 1:
            continue
        for h in beaten:
            nxt = next((x for x in later_of.get(h.horse_id, []) if x[0] > r["date"]), None)
            if nxt is None or nxt[1] not in races:
                continue
            full, caus = [], []
            for o in beaten:
                if o.horse_id == h.horse_id:
                    continue                      # ①自分自身は材料から抜く
                lt = [x for x in later_of.get(o.horse_id, []) if x[0] > r["date"]]
                if lt:
                    full.append(st.mean(x[2] for x in lt))
                pre = [x for x in lt if x[0] < nxt[0]]   # ②買う時点で済んでいるものだけ
                if pre:
                    caus.append(st.mean(x[2] for x in pre))
            if len(full) < args.min_cover:
                continue
            cand.append(dict(rid=rid, r=r, h=h, nxt=nxt,
                             full=(sum(full) + args.shrink * g) / (len(full) + args.shrink),
                             caus=((sum(caus) + args.shrink * g) / (len(caus) + args.shrink)
                                   if len(caus) >= args.min_cover else None)))
    print(f"候補 {len(cand)}点（因果版で判定できるのは "
          f"{sum(1 for c in cand if c['caus'] is not None)}点）")

    # ---- 次走の払戻を引く
    bets = []
    for i, c in enumerate(cand, 1):
        nr = races[c["nxt"][1]]
        row = next((x for x in nr["rows"] if x.horse_id == c["h"].horse_id), None)
        if row is None or row.umaban is None:
            continue
        try:
            tan, fuku = payouts(client.get(PERF.format(r=c["nxt"][1])))
        except Exception:
            continue
        if not fuku:
            continue                              # 払戻が出ていない＝未確定
        bets.append(dict(full=c["full"], caus=c["caus"],
                         pop=row.popularity, fin=row.finish_pos,
                         tan=float(tan.get(row.umaban, 0)),
                         fuku=float(fuku.get(row.umaban, 0))))
        if i % 200 == 0:
            print(f"\r  払戻 {i}/{len(cand)}", end="", flush=True)
    print("\r" + " " * 24 + "\r", end="")

    if not bets:
        raise SystemExit("賭けが1点も立たない。")

    for key, name in (("full", "全情報版（後から見た高レベル戦）"),
                      ("caus", "因果版（買う時点で見えている情報だけ）")):
        sub = [b for b in bets if b[key] is not None]
        if len(sub) < 50:
            print(f"\n■ {name}：標本 {len(sub)}点で足りない")
            continue
        vals = [b[key] for b in sub]
        mu, sd = st.mean(vals), st.pstdev(vals)
        for b in sub:
            b["z"] = (b[key] - mu) / sd if sd else 0.0
        cuts = buckets([b["z"] for b in sub], 5)
        report(name, sub, cuts, ["最低レベル", "低め", "並", "高め", "最高レベル"])

    print("\n  単回収・複回収は100円あたりの払戻。控除率のぶん、無差別に買えば75%前後に沈む。")
    print("  見るべきは『最高レベル』の行が『無差別』の行を上回っているか、そして")
    print("  最低→最高で単調に増えているか。因果版で消えるなら売り物にはならない。")


if __name__ == "__main__":
    main()
