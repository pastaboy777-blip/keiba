#!/usr/bin/env python3
"""**期待より道中で位置を上げてくる馬**を拾う。

ユーザー提示（2026-08-16）の「ウィリーしながら脚を溜める＝力まずに追走できて
いれば位置を下げない」を、測れる形にしたもの。

── 位置変動をそのまま使ってはいけない理由 ────────────────────

⚠️⚠️ **① コーナー数で出方が変わる。**通過順の点数は距離で違う。

        2点（1200m外など） 変動ゼロが **52.5%**
        3点（1400m外など） 変動ゼロが **36.7%**
        4点（1600m内など） 変動ゼロが **27.1%**

    「この馬は下げない」の多くは、**コーナーが2つしかない距離を走っただけ**。
    実例：コスモトロイメルの「鷹見陸で全部±0」は、4走中3走が1200m だった。

⚠️⚠️ **② 開始位置で出方が変わる。**前にいれば下がり、後ろなら上がる（構造）。

        4点 前25% **+0.087** ／ 中 +0.053 ／ 後40% **-0.087**

    だから **(コーナー数 × 開始位置帯) ごとの期待値を引く**。それが `rmove`。

── 補正後に何が残るか（南関 87,302走の実測）──────────────────

    連続2走の自己相関   4角の位置（脚質）   r = **+0.507**
                        補正後の位置変動     r = **+0.214**
                        （同じ距離・同じコーナー数に限ると +0.236）

    → **馬の性質として存在はする。ただし脚質の半分以下の安定性。**

    上がり残差との相関   r = **+0.422**（4割は同じことを言っている）

⚠️ **同じレース内の 3着内率（上げた20% 49.2% → 下げた20% 3.5%）を成績と
   呼ばないこと。**最終コーナーで位置を上げることは着順そのものに近い。
   使えるのは「**過去走の平均**が次走を当てるか」だけ。

    python3 scripts/nankan_move.py --place 大井 --from 2026-08-12 --to 2026-08-16

⚠️ 恒久ルール5により、**目の前の開催しか見ない**。

── 実測（大井 2026-08-12〜08-16・578頭／過去2走以上取れた438頭）──────

  **3着内率は綺麗に単調。信号は本物。**

      ★上げてくる(上位20%) n=87  3着内 32.2%  複勝回収  54.5%
        やや上げ           n=84  3着内 33.3%  複勝回収 119.5% ← 1頭で作った(抜くと67.8%)
        ふつう             n=91  3着内 20.9%  複勝回収  60.9%
        やや下げ           n=86  3着内 19.8%  複勝回収  59.9%
      **下げる(下位20%)**   n=90  3着内 **7.8%**  複勝回収 **24.4%**
        （全体 n=578 3着内 26.0% 複勝回収 68.1%）

  ⚠️ **買い側は使えない。**上げてくる側は3着内率こそ上がるが、複勝回収は
     全体（68.1%）を**下回る**。＝オッズに織り込まれている。

  ⚠️⚠️ **人気薄では逆効果。**
        平均 ≤ -0.05 × 7番人気以下  n=53  3着内 **1頭(1.9%)**  複勝回収 **7.0%**
        （対照）7番人気以下・全体     n=280 3着内 7.9%          複勝回収 62.8%
     人気薄で位置を上げてくる馬は**ただの追い込み馬**で、南関では届かない。

  ⚠️⚠️⚠️ **この条件は、元になった2頭を拾えない。**
        コスモトロイメル  8/16時点の過去3走平均 **-0.044**（線は -0.05）
        ジューンアカデミー 同                    **+0.031**
     1〜2件の事例から条件を作ると、その事例すら拾えないものが出来る。

  → **使えるのは消し側だけ。**「下げる」下位20%（3着内 7.8%）は切ってよい。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import statistics as stt
import sys
from collections import defaultdict
from datetime import date as _date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import rakuten as rk                 # noqa: E402

CACHE = "data/cache/rakuten"
#: 過去何走を見るか。
LOOKBACK = 3
UNPOP = 7
_CORNER = re.compile(r"([１-４])角([^１-４■]*)")


def _order(body: str) -> dict:
    """1コーナーぶんの通過順文字列から `{馬番: 順位}`。括弧内は同順。"""
    pos: dict = {}
    rank = 1
    for a, b in re.findall(r"\(([^)]*)\)|(\d+)", body):
        nums = [int(x) for x in re.findall(r"\d+", a or b)]
        for u in nums:
            pos[u] = rank
        rank += len(nums)
    return pos


def _band(f: float) -> str:
    return "前25%" if f < 0.25 else ("中" if f < 0.60 else "後40%")


def scan_cache() -> dict:
    """キャッシュ全体から `(日付, 馬名) -> 補正後の位置変動`。

    ⚠️ **キーに場や距離を入れない。**1頭は1日1走なので (日付, 馬名) で一意。
       場・距離で突合すると表記ゆれで落ちる。
    """
    raw_rows = []
    for pf in sorted(glob.glob(os.path.join(
            CACHE, "race_performance_list_RACEID_*.html"))):
        try:
            html = open(pf, encoding="utf-8").read()
            res = rk.parse_result(html)
        except Exception:                                   # noqa: BLE001
            continue
        if len(res) < 6:
            continue
        lp = rk.parse_lap(html) or {}
        cs = _CORNER.findall(lp.get("corners") or "")
        if len(cs) < 2:
            continue
        orders = [_order(b) for _, b in cs]
        fs = len(res)
        rid = pf.rsplit("_", 1)[-1].removesuffix(".html")
        d = f"{rid[0:4]}-{rid[4:6]}-{rid[6:8]}"
        for r in res:
            seq = [p for p in (o.get(r["umaban"]) for o in orders) if p]
            if len(seq) < 2:
                continue
            raw_rows.append((d, r["name"], len(seq),
                             seq[0] / fs, (seq[-1] - seq[0]) / fs))
    grp: dict = defaultdict(list)
    for _, _, n, first, mv in raw_rows:
        grp[(n, _band(first))].append(mv)
    exp = {k: stt.mean(v) for k, v in grp.items() if len(v) >= 200}
    out = {}
    for d, nm, n, first, mv in raw_rows:
        e = exp.get((n, _band(first)))
        if e is not None:
            out[(d, nm)] = round(mv - e, 3)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", default="大井")
    ap.add_argument("--from", dest="lo", required=True)
    ap.add_argument("--to", dest="hi", required=True)
    ap.add_argument("--cut", type=float, default=-0.05,
                    help="これ以下を「位置を上げてくる馬」とみなす")
    args = ap.parse_args()

    rmove = scan_cache()
    print(f"■ 補正後の位置変動を持つ走 {len(rmove):,}件\n")

    cli = rk.KeibaRakuten()
    rows = []
    d = _date.fromisoformat(args.lo)
    while d <= _date.fromisoformat(args.hi):
        ymd = d.isoformat().replace("-", "")
        d += timedelta(days=1)
        try:
            base = cli.find_race_id(ymd, args.place, 1)[:-2]
        except Exception:                                   # noqa: BLE001
            continue
        for rno in range(1, 13):
            rid = f"{base}{rno:02d}"
            try:
                raw = cli.get(f"/race_performance/list/RACEID/{rid}")
                res = rk.parse_result(raw)
                card = rk.parse_card(cli.get(f"/race_card/list/RACEID/{rid}"))
            except Exception:                               # noqa: BLE001
                continue
            if not res or not card["entries"]:
                continue
            pay = rk.parse_place_payout(raw)
            hist = {e["name"]: (e.get("history") or []) for e in card["entries"]}
            for r in res:
                v = [rmove[(h.date, r["name"])]
                     for h in hist.get(r["name"], [])[:LOOKBACK]
                     if (h.date, r["name"]) in rmove]
                rows.append(dict(
                    date=ymd, race=rno, name=r["name"], finish=r["finish"],
                    pop=r.get("popularity"), pay=pay.get(r["umaban"], 0),
                    m=(round(stt.mean(v), 3) if v else None), nv=len(v)))

    def rep(lab, sel):
        n = len(sel)
        if not n:
            print(f"  {lab:<32} n=0")
            return
        hit = sum(1 for x in sel if x["finish"] <= 3)
        tot = sum(x["pay"] for x in sel)
        top = max((x["pay"] for x in sel), default=0)
        print(f"  {lab:<32} n={n:>4}  3着内 {hit:>3} ({hit/n*100:>5.1f}%)"
              f"  複勝回収 {tot/(100*n)*100:>6.1f}%"
              f"  最高配当を抜くと {(tot-top)/(100*max(n-1,1))*100:>6.1f}%")

    ok = [x for x in rows if x["m"] is not None and x["nv"] >= 2]
    print(f"■ {args.place} {args.lo}〜{args.hi}　出走 {len(rows)}頭"
          f"／過去2走以上の位置変動が取れた {len(ok)}頭\n")
    rep("全体", rows)
    print()
    q = sorted(x["m"] for x in ok)
    cuts = [q[int(len(q) * f)] for f in (0.2, 0.4, 0.6, 0.8)]
    lab = ["★上げてくる(上位20%)", "やや上げ", "ふつう", "やや下げ", "下げる(下位20%)"]
    for i, lb in enumerate(lab):
        lo_ = cuts[i - 1] if i else -9
        hi_ = cuts[i] if i < 4 else 9
        rep(lb, [x for x in ok if lo_ <= x["m"] < hi_ or (i == 4 and x["m"] >= hi_)])
    print()
    hot = [x for x in ok if x["m"] <= args.cut]
    rep(f"★ 平均 ≤ {args.cut}", hot)
    rep(f"★ 平均 ≤ {args.cut} × {UNPOP}番人気以下",
        [x for x in hot if (x["pop"] or 99) >= UNPOP])
    rep(f"（対照）{UNPOP}番人気以下・全体",
        [x for x in rows if (x["pop"] or 99) >= UNPOP])
    print(f"\n■ 拾われた馬（平均 ≤ {args.cut}・人気薄）")
    for x in sorted((y for y in hot if (y["pop"] or 99) >= UNPOP),
                    key=lambda y: y["m"])[:20]:
        print(f"   {x['date']} {x['race']:>2}R {x['name']:<12} 平均{x['m']:+.3f}"
              f"（{x['nv']}走）→ {x['finish']:>2}着 {x['pop']}人気"
              + (f"  複勝{x['pay']}円" if x["pay"] else ""))


if __name__ == "__main__":
    main()
