#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Turn Time（Brohamer）の南関版 ── 勝負どころで動ける馬を測る。

★ユーザーの明示的な指示で回すもの。

原典の考え方:
  全体タイムでも上がりでもなく【3〜4コーナーの区間】だけを見る。
  ここは「曲がりながら加速する」唯一の区間で、直線の加速とは要求が違う。
  前半は枠と隊列で決まり、上がりは展開に左右される。
  turn time だけが、その馬の機動力を素で映す ── というのがBrohamerの主張。

南関でどう作るか:
  1頭ごとの区間タイムは公表されないので、秒では出せない。
  代わりに【通過順の動き】で測る。netkeibaは1頭ごとの通過順を持っている。

      相対位置 rel = (通過順位 - 1) / (頭数 - 1)      0=先頭 1=最後方
      turn move   = rel(最後から2番目のコーナー) - rel(4角)

  正なら「コーナーで押し上げた」。先頭の馬は上げようがないので0に張り付く。
  この偏りを避けるため、後方から出た馬だけに絞った集計も併せて出す。

  さらに、レース単位の4角通過順の括弧表記（併走・括弧内は内から）を使って
  【内で拾ったのか、外を回して上げたのか】を分ける。
  外を回して押し上げたほうが価値が高い、というのが原典の含意。

判定はリークを塞ぐ:
  対象レースの【前日以前】の走りだけから各馬の機動力を作り、
  そのレースの着順・単勝オッズと突き合わせる。

対照を必ず置く:
  1番人気（市場）と、馬番の若い馬（でたらめの水準）を同じレース集合で並べる。

使い方:
  python3 scripts/ana/turn_move.py --from 2026-07-01 --to 2026-08-02
"""
from __future__ import annotations

import argparse
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bt          # パーサだけ借りる（BT値は使わない）


def outer_map(c4, n):
    """レース単位の4角通過順から、各馬が『外を回していたか』を復元する。

    括弧は併走で、括弧内は内側の馬から順に書かれる規約を使う。
    括弧の2頭目以降＝外。単独表記は判定できないので None。
    """
    out = {}
    for tok in re.findall(r"\([^)]*\)|\d+", c4 or ""):
        vs = [int(v) for v in re.findall(r"\d+", tok)]
        if tok.startswith("("):
            for k, u in enumerate(vs):
                out[u] = (k > 0)          # True=外 / False=内
        else:
            out[vs[0]] = None
    return out


def moves(dfrom="2026-01-01", dto="2026-12-31"):
    """馬名 → [(日付, turn move, 外を回したか, 出た位置)] の履歴。"""
    R = bt.load(dfrom, dto)
    h = defaultdict(list)
    for r in R:
        om = outer_map(r.get("c4"), r["n"])
        for x in r["rows"]:
            p = [int(v) for v in re.findall(r"\d+", x.get("pas") or "")]
            if len(p) < 2 or r["n"] < 5:
                continue
            rel = lambda q: (q - 1) / (r["n"] - 1)
            mv = rel(p[-2]) - rel(p[-1])           # ＋なら4角までに押し上げた
            h[x["name"]].append((r["date"], mv, om.get(x["ub"]), rel(p[0])))
    for v in h.values():
        v.sort()
    return h, R


def tally(rows, label):
    n = len(rows)
    if not n:
        return f"{label:<20} 該当なし"
    w = sum(1 for a, b, o in rows if a)
    p = sum(1 for a, b, o in rows if b)
    ret = sum((o * 100 if a and o else 0) for a, b, o in rows)
    return (f"{label:<20}{n:>5}回  1着{w:>4} ({w/n*100:>5.1f}%)  "
            f"3着内{p:>4} ({p/n*100:>5.1f}%)  単回収 {ret/n:>6.1f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="dfrom", default="2026-07-01")
    ap.add_argument("--to", dest="dto", default="2026-08-02")
    ap.add_argument("--min-prior", type=int, default=3)
    a = ap.parse_args()

    H, ALL = moves()
    T = [r for r in ALL if a.dfrom <= r["date"] <= a.dto]
    print(f"■ 対象 {len(T)}レース（{a.dfrom}〜{a.dto}・南関4場）／履歴のある馬 {len(H):,}頭")

    mv_all = [m for v in H.values() for _, m, _, _ in v]
    print(f"  turn move の分布 {len(mv_all):,}走  中央{st.median(mv_all):+.3f}  "
          f"押し上げ{sum(1 for m in mv_all if m > 0.02)/len(mv_all)*100:.0f}%  "
          f"下げ{sum(1 for m in mv_all if m < -0.02)/len(mv_all)*100:.0f}%\n")

    top, topo, pop, rnd = [], [], [], []
    cross = defaultdict(list)
    allp = defaultdict(list)
    for r in T:
        cand = []
        for x in r["rows"]:
            v = [(m, o) for d, m, o, _ in H.get(x["name"], []) if d < r["date"]]
            if len(v) >= a.min_prior:
                mm = st.mean(m for m, _ in v)
                # 外を回して押し上げた分だけを取り出した版
                ow = st.mean(m for m, o in v if o) if any(o for _, o in v) else None
                cand.append((x, mm, ow))
        if len(cand) < 4:
            continue
        res = lambda x: (x["chaku"] == 1, x["chaku"] <= 3, x["odds"])
        order = sorted(cand, key=lambda z: -z[1])
        top.append(res(order[0][0]))
        ow = [c for c in cand if c[2] is not None]
        if ow:
            topo.append(res(max(ow, key=lambda z: z[2])[0]))
        f = next((x for x in r["rows"] if x["ninki"] == 1), None)
        if f:
            pop.append(res(f))
        rnd.append(res(sorted(cand, key=lambda z: z[0]["ub"] or 99)[0][0]))
        rk = {id(c[0]): i + 1 for i, c in enumerate(order)}
        for x, mm, _ in cand:
            nk = x["ninki"] or 99
            pb = "1-2番人気" if nk <= 2 else ("3-5番人気" if nk <= 5 else "6番人気以下")
            i = rk[id(x)]
            rb = "機動1-2位" if i <= 2 else ("機動3-5位" if i <= 5 else "機動6位以下")
            cross[(pb, rb)].append(res(x))
            allp[pb].append(res(x))

    print("■ 過去の機動力で1頭選んだとき")
    print("  " + tally(top, "turn move 1位"))
    print("  " + tally(topo, "外を回して上げた1位"))
    print("\n■ 対照")
    print("  " + tally(pop, "1番人気"))
    print("  " + tally(rnd, "馬番の若い馬"))

    print("\n■ 人気帯 × 機動力順位（3着内率／単回収率）")
    print(f"{'':<12}" + "".join(f"{c:>18}" for c in ("機動1-2位", "機動3-5位", "機動6位以下"))
          + f"{'帯全体':>18}")
    for pb in ("1-2番人気", "3-5番人気", "6番人気以下"):
        line = f"{pb:<12}"
        for rb in ("機動1-2位", "機動3-5位", "機動6位以下"):
            v = cross[(pb, rb)]
            if len(v) < 30:
                line += f"{'—':>18}"
                continue
            p = sum(1 for x, y, o in v if y) / len(v) * 100
            ret = sum((o * 100 if x and o else 0) for x, y, o in v) / len(v)
            line += f"{p:>6.1f}% {ret:>5.0f}% n{len(v):<4}"
        v = allp[pb]
        p = sum(1 for x, y, o in v if y) / len(v) * 100
        ret = sum((o * 100 if x and o else 0) for x, y, o in v) / len(v)
        line += f"{p:>6.1f}% {ret:>5.0f}% n{len(v):<4}"
        print(line)


if __name__ == "__main__":
    main()
