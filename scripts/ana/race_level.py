#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""南関のレースを「レベルの高かった順」に並べる。

レベルの測り方は3通りあるが、いちばん循環しないのは【次走成績】。

  ① 次走成績（本命）
     そのレースに出ていた馬が、次のレースでどれだけ勝ったか・馬券に絡んだか。
     速い時計が出たかではなく「そこに居た馬が、その後どこでも通用したか」を見る。
     馬場も展開もクラスも関係なく、メンバーの質だけが残る。

  ② 出走馬の平均Elo（h2h_elo.json）
     レース前時点の力関係の総和。ただしEloは過去の結果から作るので、
     「強い馬が集まった」ことは分かるが「その後伸びた」ことは分からない。

  ③ 勝ちタイム偏差
     同じ場・距離の標準勝ち時計との差。馬場差を拾ってしまうので参考程度。

①は「そのレースの後」を使うので、当日の予想には使えない。
過去のレースを振り返って「あれはレベルが高かった」と判定する用途のツール。
出てきた高レベル戦の【4着以下だった馬】が次に人気を落として出てきたら、それが狙い目になる。

使い方:
  python3 scripts/ana/race_level.py                    # 全体の上位
  python3 scripts/ana/race_level.py --place 川崎        # 川崎だけ
  python3 scripts/ana/race_level.py --from 2026-06-01 --min-horses 8
  python3 scripts/ana/race_level.py --horse ジョイフルロック   # その馬が出たレースの水準
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import math
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import h2h

ELO = Path(__file__).resolve().parent / "h2h_elo.json"


def load_races():
    """キャッシュ済みの南関レースを時系列で読む。"""
    out = []
    for fn in sorted(glob.glob(os.path.join(h2h.CACHE, "2026*.html"))):
        if os.path.getsize(fn) < 20000:
            continue
        p = h2h._parse(fn)
        if not p:
            continue
        d, place, rows = p
        t = open(fn, "rb").read().decode("euc-jp", errors="replace")
        x = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))
        m = re.search(r"(ダ|芝)\s*(?:左|右|直)?\s*(\d{3,4})m", x)
        rid = os.path.basename(fn)[:-5]        # 2026 + 場2桁 + MMDD + RR
        nm = re.search(r"\| ?([^|]{2,24}?)\｜?\s*\d{4}年", x) or re.search(r"([^ ]{2,20})｜2026年", x)
        out.append(dict(rid=rid, date=d, place=place,
                        rn=(int(rid[-2:]) if rid[-2:].isdigit() else None),
                        surf=(m.group(1) if m else None), dist=(int(m.group(2)) if m else None),
                        name=(nm.group(1).strip() if nm else ""),
                        rows=rows))
    out.sort(key=lambda z: (z["date"], z["place"], z["rn"] or 0))
    return out


def next_form(races):
    """各馬の出走順を作り、レースごとに『出走馬の次走成績』を集計する。"""
    seq = defaultdict(list)                       # 馬名 -> [(date, race_index)]
    for i, r in enumerate(races):
        for name, chaku, ninki in r["rows"]:
            seq[name].append((r["date"], i))
    for name in seq:
        seq[name].sort()

    for i, r in enumerate(races):
        nx_win = nx_plc = nx_n = 0
        lo_win = lo_plc = lo_n = 0          # 4着以下だった馬（＝敗者）だけの次走
        detail = []
        for name, chaku, ninki in r["rows"]:
            s = seq[name]
            pos = next((k for k, (d, j) in enumerate(s) if j == i), None)
            if pos is None or pos + 1 >= len(s):
                continue
            j = s[pos + 1][1]
            nr = races[j]
            fin = next((c for n2, c, _ in nr["rows"] if n2 == name), None)
            if fin is None:
                continue
            nx_n += 1
            if fin == 1:
                nx_win += 1
            if fin <= 3:
                nx_plc += 1
            if chaku >= 4:                  # このレースで負けた馬
                lo_n += 1
                if fin == 1:
                    lo_win += 1
                if fin <= 3:
                    lo_plc += 1
            detail.append((name, chaku, fin, nr["date"], nr["place"], ninki))
        r["nx_n"], r["nx_win"], r["nx_plc"], r["nx_detail"] = nx_n, nx_win, nx_plc, detail
        r["lo_n"], r["lo_win"], r["lo_plc"] = lo_n, lo_win, lo_plc


def add_elo(races):
    elo = json.load(open(ELO)) if ELO.exists() else {}
    for r in races:
        e = [elo[n] for n, _, _ in r["rows"] if n in elo]
        r["elo_mean"] = st.mean(e) if e else None
        r["elo_top3"] = st.mean(sorted(e, reverse=True)[:3]) if len(e) >= 3 else None


def wilson_lo(k, n, z=1.28):
    """勝率の下側信頼限界（90%）。母数が小さいレースが上位を占めるのを防ぐ。"""
    if not n:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - r) / d


def main():
    ap = argparse.ArgumentParser(description="南関レースのレベル判定")
    ap.add_argument("--place", help="場を絞る（大井/川崎/船橋/浦和）")
    ap.add_argument("--from", dest="dfrom", help="この日以降 YYYY-MM-DD")
    ap.add_argument("--to", dest="dto", help="この日まで YYYY-MM-DD")
    ap.add_argument("--min-horses", type=int, default=7, help="次走が追えた頭数の下限")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--horse", help="この馬が出走したレースの水準を出す")
    ap.add_argument("--sort", choices=("win", "plc", "elo", "raw", "loser"), default="win",
                    help="win=次走勝率 / plc=次走3着内率 / loser=【4着以下だった馬】の次走勝率 "
                         "/ elo=平均Elo / raw=補正なしの生の率")
    ap.add_argument("--min-losers", type=int, default=4, help="loser時：次走を追えた敗者の下限")
    args = ap.parse_args()

    races = load_races()
    next_form(races)
    add_elo(races)
    print(f"■ キャッシュ {len(races)}レース（{races[0]['date']}〜{races[-1]['date']}）")

    if args.horse:
        hit = [r for r in races if any(n == args.horse for n, _, _ in r["rows"])]
        if not hit:
            raise SystemExit(f"{args.horse} の出走レースがキャッシュにない")
        print(f"\n■ {args.horse} が出たレースの水準")
        for r in hit:
            ch = next(c for n, c, _ in r["rows"] if n == args.horse)
            rate = f"{r['nx_win']}/{r['nx_n']}={r['nx_win']/r['nx_n']*100:.0f}%" if r["nx_n"] else "—"
            print(f"  {r['date']} {r['place']}{r['rn'] or '?':>2}R {r['surf'] or ''}{r['dist'] or ''}m "
                  f"{len(r['rows']):>2}頭 │ 自分{ch}着 │ 次走勝率 {rate} "
                  f"3着内 {r['nx_plc']}/{r['nx_n']} │ 平均Elo {r['elo_mean'] or 0:.0f}")
        return

    R = [r for r in races if r["nx_n"] >= args.min_horses]
    if args.place:
        R = [r for r in R if r["place"] == args.place]
    if args.dfrom:
        R = [r for r in R if r["date"] >= args.dfrom]
    if args.dto:
        R = [r for r in R if r["date"] <= args.dto]
    if not R:
        raise SystemExit("条件に合うレースがない")

    if args.sort == "loser":
        R = [r for r in R if r["lo_n"] >= args.min_losers]
    key = {"win": lambda r: (wilson_lo(r["nx_win"], r["nx_n"]),),
           "loser": lambda r: (wilson_lo(r["lo_win"], r["lo_n"]),),
           "plc": lambda r: (wilson_lo(r["nx_plc"], r["nx_n"]),),
           "raw": lambda r: (r["nx_win"] / r["nx_n"], r["nx_n"]),
           "elo": lambda r: (r["elo_mean"] or 0,)}[args.sort]
    R.sort(key=key, reverse=True)

    base_w = sum(r["nx_win"] for r in R) / sum(r["nx_n"] for r in R)
    base_p = sum(r["nx_plc"] for r in R) / sum(r["nx_n"] for r in R)
    ln = sum(r["lo_n"] for r in R)
    base_l = sum(r["lo_win"] for r in R) / ln if ln else 0
    base_lp = sum(r["lo_plc"] for r in R) / ln if ln else 0
    print(f"  対象{len(R)}レース／全体の次走勝率 {base_w*100:.1f}%・次走3着内率 {base_p*100:.1f}%")
    print(f"  うち4着以下だった馬（敗者{ln}頭）の次走勝率 {base_l*100:.1f}%・3着内率 {base_lp*100:.1f}%\n")
    print(f"  {'日付':<11}{'場':<4}{'R':>3} {'条件':<9}{'頭':>3} {'敗者の次走勝率':<15}{'倍率':>5} "
          f"{'敗者3着内':<13}{'全体次走勝率':<13}  レース名")
    for r in R[:args.top]:
        lw = f"{r['lo_win']}/{r['lo_n']}={r['lo_win']/r['lo_n']*100:.0f}%" if r["lo_n"] else "—"
        lp = f"{r['lo_plc']}/{r['lo_n']}={r['lo_plc']/r['lo_n']*100:.0f}%" if r["lo_n"] else "—"
        w = f"{r['nx_win']}/{r['nx_n']}={r['nx_win']/r['nx_n']*100:.0f}%"
        lift = (r["lo_win"] / r["lo_n"] / base_l) if (r["lo_n"] and base_l) else 0
        cond = f"{r['surf'] or ''}{r['dist'] or ''}m"
        print(f"  {r['date']:<11}{r['place']:<4}{r['rn'] or 0:>3} {cond:<9}{len(r['rows']):>3} "
              f"{lw:<15}{lift:>5.2f} {lp:<13}{w:<13}  {r['name']}")

    print("\n  ── 使い方 ──")
    print("  上位のレースで4着以下だった馬が、次に人気を落として出てきたら狙い目。")
    print("  --horse で個別の馬が『どのレベルのレースを走ってきたか』を確認できる。")


if __name__ == "__main__":
    main()
