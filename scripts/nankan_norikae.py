#!/usr/bin/env python3
"""**乗り替わりか、そのままか。**開催ごとに記録する。

ユーザーの「穴馬の過去5走の騎手にヒントがある」から出てきた道具。
穴馬22頭の馬柱を並べたら「同じ騎手が長く乗っていた馬」が目立った ── そこから
**継続と乗り替わり**を測ったら、継続の長さより **乗り替わったかどうか** が効いた。

    python3 scripts/nankan_norikae.py --place 大井 --from 2026-08-12 --to 2026-08-16

⚠️ 恒久ルール5により、**目の前の開催しか見ない**。開催ごとに回して積むこと。

── 実測（大井 2026-08-12〜08-16・前走の騎手が読めた548頭）──────────

                       n    3着内    複勝回収  上位1件抜き  上位3件抜き
    全体              548   24.8%    65.9%     58.0%      53.4%
    **乗り替わり**     211   26.1%  **93.1%**   72.5%      62.2%
      そのまま         337   24.0%    48.9%     45.6%      40.4%

    1〜3人気 乗替       43   67.4%   105.3%    101.2%      94.2%
    1〜3人気 そのまま    94   60.6%    83.5%     81.2%      77.5%
    4〜6人気 乗替       54   27.8%    61.7%     54.7%      45.7%
    4〜6人気 そのまま    83   16.9%    39.3%     35.5%      28.9%
    7人気以下 乗替     114    9.6%   103.3%     65.2%      45.7%
    7人気以下 そのまま  160    6.2%    33.6%     26.4%      15.2%

  **全ての人気帯で、乗り替わりのほうが3着内率も回収率も上。**
  しかも上位3件の配当を抜いても崩れない。この開催で見つけたものの中で、
  **1頭で作った数字ではない唯一の買い側**。

  ⚠️ ただし1開催（548頭）だけ。**未検証**。恒久ルール5に従い過去には遡らない。
     次の開催で同じことが出るかを見て積むこと。

  ⚠️ 交絡の候補（潰していない）:
     ・南関は弱い馬ほど厩舎の主戦が乗り続ける。**「そのまま」＝弱い馬**かもしれない
     ・乗り替わりは「勝負気配」のサインで、それが実力に効いているのかもしれない
     ・市場は主戦継続を好むので、乗り替わりが割り引かれているのかもしれない
     どれであっても**買い側で全体を上回った**ことは変わらないが、理由は未確定。

  ⚠️ 「継続3走以上 → 乗り替わり」は**効かない**。人気薄では n=29 で 3着内2頭、
     複勝回収 50.0%（上位1件抜き 22.9%）。継続の長さは材料にならない。

── 次の開催で確かめた（川崎 2026-08-18・107頭）────────────────

⚠️⚠️ **再現しなかった。逆に出た。**

                       n    3着内    複勝回収  上位1件抜き  上位3件抜き
    全体              107   29.0%    63.8%     57.7%      48.9%
    乗り替わり          46   26.1%    48.7%     42.7%      32.1%
    そのまま            61   31.1%  **75.2%**   64.7%      49.1%

    7人気以下 乗替      24    4.2%    13.3%      0.0%       0.0%
    7人気以下 そのまま   19   10.5%    54.2%     22.2%       0.0%

  **大井で全人気帯に出ていた差が、川崎では全部ひっくり返った。**
  n=107 と小さい（大井は548）が、方向が完全に逆なので「小さいから」では
  片付かない。**場が違う／日が違う／たまたま、のどれかを分けられていない。**
  → **買い材料として使わないこと。**開催ごとに積み続けて判断する。

⚠️⚠️ **バグ（2026-08-18 発見・修正済み）**
   人気帯の集計で `(pop or 99) >= 7` と書いていたため、**人気が未掲載の馬が
   全部「7番人気以下」に入っていた**。川崎 8/18 は 11R・12R の人気欄が丸ごと
   「-」で、107頭中17頭（うち3着内6頭）が混入していた。
   大井 8/12〜16 は欠損0頭だったので、そちらの数字は汚染されていない。
   **欠損は 99 で埋めず、集計から外す。**
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date as _date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import rakuten as rk                 # noqa: E402

UNPOP = 7
_MARK = re.compile(r"^[☆★▲△◇◆◎]+|[（(].*$")


def norm(j: str | None) -> str | None:
    """`'☆中山遥 (浦和)'` → `'中山遥'`。減量印と所属を落とす。

    ⚠️ **落とさないと乗り替わり判定が全部おかしくなる。**出馬表・馬柱・結果で
       表記が違い、同じ騎手が別人に見える。
    """
    if not j:
        return None
    return _MARK.sub("", j).strip() or None


def collect(cli, place: str, lo: str, hi: str) -> list:
    rows = []
    d = _date.fromisoformat(lo)
    while d <= _date.fromisoformat(hi):
        ymd = d.isoformat().replace("-", "")
        d += timedelta(days=1)
        try:
            base = cli.find_race_id(ymd, place, 1)[:-2]
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
                h = hist.get(r["name"], [])
                prev = norm(h[0].jockey) if h else None
                now = norm(r.get("jockey"))
                if not prev or not now:
                    continue
                rows.append(dict(
                    date=ymd, race=rno, name=r["name"], finish=r["finish"],
                    pop=r.get("popularity"), pay=pay.get(r["umaban"], 0),
                    prev=prev, now=now, sw=(now != prev)))
    return rows


def report(rows: list) -> None:
    def rep(lab, sel):
        n = len(sel)
        if n < 4:
            print(f"  {lab:<26} n={n}（少なすぎる）")
            return
        hit = sum(1 for x in sel if x["finish"] <= 3)
        tot = sum(x["pay"] for x in sel)
        s = sorted((x["pay"] for x in sel), reverse=True)
        print(f"  {lab:<26} n={n:>4}  3着内 {hit:>3} ({hit/n*100:>5.1f}%)"
              f"  複勝回収 {tot/(100*n)*100:>6.1f}%"
              f"  上位1件抜き {(tot-s[0])/(100*(n-1))*100:>6.1f}%"
              f"  上位3件抜き {(tot-sum(s[:3]))/(100*(n-3))*100:>6.1f}%")

    nop = sum(1 for x in rows if x["pop"] is None)
    print(f"■ 前走の騎手が読めた {len(rows)}頭"
          + (f"（うち**人気が未掲載 {nop}頭**。人気帯の集計からは外す）" if nop else ""))
    print()
    rep("全体", rows)
    print("── 乗り替わりか、そのままか ────────────────")
    rep("★ 乗り替わり", [x for x in rows if x["sw"]])
    rep("   そのまま", [x for x in rows if not x["sw"]])
    print()
    # ⚠️ **人気が None の馬を「99番人気」として人気薄に入れてはいけない。**
    #    川崎 2026-08-18 は 11R・12R の人気欄が丸ごと「-」で、107頭中17頭
    #    （うち3着内6頭）が人気薄に混ざり、集計が壊れた。**欠損は欠損として外す。**
    pop = [x for x in rows if x["pop"] is not None]
    for lo, hi, lab in ((1, 3, "1〜3番人気"), (4, 6, "4〜6番人気"),
                        (UNPOP, 99, f"{UNPOP}番人気以下")):
        s = [x for x in pop if lo <= x["pop"] <= hi]
        rep(f"{lab}・乗り替わり", [x for x in s if x["sw"]])
        rep(f"{lab}・そのまま", [x for x in s if not x["sw"]])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", default="大井")
    ap.add_argument("--from", dest="lo", required=True)
    ap.add_argument("--to", dest="hi", required=True)
    ap.add_argument("--list", action="store_true",
                    help="乗り替わりで3着内に来た人気薄を並べる")
    args = ap.parse_args()
    rows = collect(rk.KeibaRakuten(), args.place, args.lo, args.hi)
    print(f"\n=== {args.place} {args.lo}〜{args.hi} ===\n")
    report(rows)
    if args.list:
        print(f"\n■ 乗り替わり × {UNPOP}番人気以下 で3着内")
        for x in sorted((y for y in rows if y["sw"] and y["finish"] <= 3
                         and y["pop"] is not None and y["pop"] >= UNPOP),
                        key=lambda y: -y["pay"]):
            print(f"   {x['date']} {x['race']:>2}R {x['name']:<12} "
                  f"{x['prev']}→{x['now']}  {x['finish']}着 {x['pop']}人気"
                  + (f"  複勝{x['pay']}円" if x["pay"] else ""))


if __name__ == "__main__":
    main()
