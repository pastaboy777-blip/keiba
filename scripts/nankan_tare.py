#!/usr/bin/env python3
"""**前に行けて、垂れない馬を選ぶ。**南関の本質は「ズブい馬を走らせる競馬」。

    python3 scripts/nankan_tare.py --place 大井 --date 20260915
    python3 scripts/nankan_tare.py --place 大井 --date 20260915 --race 11

楽天だけで動く（Cookie 不要）。出馬表の馬柱から計算する。

── なぜ「垂れない」なのか ────────────────────────────

実測（大井6日＋川崎5日・96レース）:

    勝ち馬の4角位置   3番手以内 **82/96（85%）**   7番手以降 **7/96（7%）**

    ペース別に「1着がどこから来たか」（4角の相対位置）:
        速い1/3  20%  ／  中 19%  ／  遅い1/3 21%   ← **ペースで動かない**
        2着は    39%  ／     25%  ／        27%    ← 動くのは2着だけ

  → **ハイペースで前が垂れても、後ろは勝てずに2着を拾うだけ。**
     砂は弾性回復が 65%→45% に落ちるので、加速し直すのが構造的に高い。
     そこにズブい馬を集めれば、**差すという行為自体が成立しない。**

  → だから「前有利だから前を買う」ではなく、
     **「後ろは勝てない。前から、垂れない馬を選ぶ」**が正しい読み方。

── 何を測るか ───────────────────────────────────

**垂れ残差** ＝ 着順相対 − （その4角位置なら普通そうなる着順相対）

  ⚠️⚠️ **生の「着順 − 4角位置」を使ってはいけない。**4角1番手の馬は落ちる
     ことしかできず、最後方の馬は上がることしかできない。**位置と垂れは
     構造的に相関する。**実測した回帰曲線:

        4角 10%台 → 着順 32%      4角 60%台 → 着順 58%
        4角 20%台 → 着順 39%      4角 80%台 → 着順 67%
        4角 40%台 → 着順 48%      4角100%台 → 着順 83%

     この曲線からの**残差**だけを見る。＋＝期待より悪い＝垂れた。

── 繰り返すのか（2026-09-15 実測・5,546走）──────────────

    垂れ残差   連続2走         r = +0.264 (n=4,254)
               過去の平均→次走  r = **+0.333** (n=3,072)
    （比較）   4角位置          r = +0.473 (n=4,254)

  **このリポジトリで2番目に安定した量。**位置ほどではないが、十分に繰り返す。

── ⚠️ 正直な線引き ─────────────────────────────

・**「垂れない馬を買うと儲かる」は検証していない。**繰り返すことと、
  市場より正確に選べることは別の話。人気は既にこれを織り込んでいる
  可能性が高い（この開催で1〜3人気が10/12勝っている）。
・回帰曲線は**この期間の南関**から作った。場も距離も混ぜている。
・恒久ルール5：目の前の開催の出走馬を見るだけ。過去開催の一括検証はしない。
"""

from __future__ import annotations

import argparse
import json
import os
import statistics as stt
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import rakuten as rk                 # noqa: E402

#: 4角の相対位置（10%刻み）→ 普通そうなる着順の相対位置。
#: ⚠️ **構造的な回帰。**これを引かないと「前にいたから落ちた」を垂れと誤認する。
#: 実測：南関 5,546走（大井 2026-08-31〜09-15 ＋ 川崎 09-07〜09-11）。
EXPECTED = {1: 0.32, 2: 0.39, 3: 0.40, 4: 0.48, 5: 0.53,
            6: 0.58, 7: 0.62, 8: 0.67, 9: 0.74, 10: 0.83}
#: 標準偏差。垂れ残差を σ で割って読むため。実測 0.241。
SD = 0.241
#: 何走ぶん見るか。
DEFAULT_N = 5
#: 「前に行ける」とみなす4角の相対位置。
FRONT = 0.30


def expected(pos_rel: float) -> float | None:
    """その4角位置なら普通そうなる着順の相対位置。"""
    k = max(1, min(10, round(pos_rel * 10)))
    return EXPECTED.get(k)


def runs_of(entry: dict, n: int) -> list[dict]:
    """馬柱から (日付, 位置, 着順, 垂れ残差) を**古い順**で。

    ⚠️ 通過順か着順か頭数が欠けている走は**落とす**。0で埋めない。
    """
    out = []
    for h in reversed((entry.get("history") or [])[:n]):
        if not (h.corner_pos and h.field_size and h.finish_pos):
            continue
        if h.field_size < 6:            # 少頭数は位置の意味が変わる
            continue
        p = h.corner_pos[-1] / h.field_size
        f = h.finish_pos / h.field_size
        e = expected(p)
        if e is None:
            continue
        out.append({"date": h.date, "place": h.place, "dist": h.distance,
                    "baba": h.baba, "pos": p, "fin": f, "tare": f - e,
                    "field": h.field_size, "corner": h.corner_pos[-1],
                    "finish": h.finish_pos})
    return out


def profile(rs: list[dict]) -> dict:
    """その馬の「位置」と「垂れ」。**3走以上ないと出さない。**"""
    if len(rs) < 3:
        return {"n": len(rs), "pos": None, "tare": None}
    return {"n": len(rs),
            "pos": stt.mean([r["pos"] for r in rs]),
            "tare": stt.mean([r["tare"] for r in rs]),
            "recent_pos": rs[-1]["pos"]}


def main() -> None:
    ap = argparse.ArgumentParser(description="前に行けて垂れない馬")
    ap.add_argument("--place", required=True)
    ap.add_argument("--date", required=True, help="YYYYMMDD")
    ap.add_argument("--race", type=int)
    ap.add_argument("-n", type=int, default=DEFAULT_N)
    ap.add_argument("--jsonl")
    args = ap.parse_args()

    cli = rk.KeibaRakuten()
    out = open(args.jsonl, "w", encoding="utf-8") if args.jsonl else None
    for rno in ([args.race] if args.race else range(1, 13)):
        try:
            rid = cli.find_race_id(args.date, args.place, rno)
            card = rk.parse_card(cli.get(f"/race_card/list/RACEID/{rid}"))
        except Exception:                                   # noqa: BLE001
            continue
        ents = card.get("entries") or []
        if not ents:
            continue
        hdr = card.get("header") or {}
        print(f"\n{'='*96}\n {args.place} {args.date} {rno}R  "
              f"{hdr.get('race_class') or ''} {hdr.get('distance')}m "
              f"{hdr.get('post_time') or ''}\n{'='*96}")
        print(f"  {'馬':<19}{'人気':>5}  {'位置':>6}{'垂れ':>8}  "
              f"評価        過去の走り（○＝垂れず ×＝垂れた）")
        rows = []
        for e in ents:
            rs = runs_of(e, args.n)
            pr = profile(rs)
            rows.append((pr.get("pos") if pr["pos"] is not None else 9, e, rs, pr))
        for _, e, rs, pr in sorted(rows, key=lambda x: x[0]):
            if pr["pos"] is None:
                print(f"  {e.get('umaban'):>2} {e.get('name',''):<16}"
                      f"{(str(e.get('popularity'))+'人') if e.get('popularity') else ' −':>5}"
                      f"   判定不能（{pr['n']}走）")
                continue
            z = pr["tare"] / SD
            # ★ 前に行けて、垂れない
            mark = ("★★" if (pr["pos"] <= FRONT and z <= -0.4) else
                    ("★ " if (pr["pos"] <= FRONT and z <= 0.2) else
                     ("消" if z >= 0.6 else "  ")))
            hist = " ".join(("○" if r["tare"] <= -0.1 else
                             ("×" if r["tare"] >= 0.1 else "・")) for r in rs)
            print(f"  {e.get('umaban'):>2} {e.get('name',''):<16}"
                  f"{(str(e.get('popularity'))+'人') if e.get('popularity') else ' −':>5}"
                  f"  {pr['pos']*100:>5.0f}%{z:>+8.2f}σ  {mark:<10}{hist}")
            if out:
                out.write(json.dumps({"date": args.date, "place": args.place,
                                      "race": rno, "umaban": e.get("umaban"),
                                      "name": e.get("name"),
                                      "pop": e.get("popularity"),
                                      "pos": pr["pos"], "tare_z": z,
                                      "mark": mark.strip(), "n": pr["n"]},
                                     ensure_ascii=False) + "\n")
    if out:
        out.close()
    print("\n  ★★ 前に行けて（4角30%以内）、垂れない（−0.4σ以下）")
    print("  ★  前に行けて、垂れが平均並み以下")
    print("  消  垂れが +0.6σ 以上")
    print("\n⚠️ 垂れ残差の自己相関は +0.333。**繰り返すことと、市場より正確に"
          "選べることは別**。この道具が儲かるかは検証していない。", file=sys.stderr)


if __name__ == "__main__":
    main()
