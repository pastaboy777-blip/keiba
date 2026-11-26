#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逸脱を見つける ── その馬自身の標準形から、今回どこが変わったか。

なぜ「逸脱」なのか:
  馬固有の調教パターンは、ほぼ厩舎の方針で、その馬にとっては【定数】。
  定数は変化を予測できない。剥がすべき条件であって、シグナルではない。

  だが「いつもと違うことをした」なら、それは厩舎が意図を変えた印。
  変化なので、予測に使える余地がある。

  ★これは「穴馬を集めて共通点を探す」の代わりでもある。
    結果で切ってから中身を見ると、必ず何か見つかるが、それは結果の言い換え。
    先に逸脱を出しておいて、あとで答え合わせをする順番なら、予想になる。

見る軸（重みは置かない。数えるだけ）:
    本数    いつもより多い／少ない
    脚色    いつもより強く追った（馬なり→一杯 など）
    施設    過去に使っていない場所を使った
    曜日    いつもと違う曜日に追った
    併せ    単走ばかりだったのに併せた（逆も）
    負荷    ☆が付いた

★必ず割り引くもの ── 出走間隔:
  休み明けは本数が増えて当たり前（必要に迫られている）。
  勝負気配ではない。だから間隔で説明できる本数増は別に表示する。

★重みを置かない理由:
  8/18川崎で、手で決めた重みでカードを組んだら◎が12鞍0勝・回収0%、
  ▲が4勝・回収207%と順序が逆転した。重みはデータから決めるべきで、
  データが無いうちは【数える】に留める。

使い方:
    python3 scripts/ana/itsudatsu.py out/cyokyo_2026101101_0907.json
    python3 scripts/ana/itsudatsu.py out/*.json --min 2     # 逸脱2件以上だけ
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics as st
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cyokyo_jikei as C

MIN_PAST = 2          # 標準形を作るのに要る過去の走数
LONG_REST = 35        # これ以上空いたら「休み明け」。本数増は間隔で説明できる


def by_race(h, rid):
    """1頭の追い切りを走ごとにまとめ、日付順に並べる。"""
    g = {}
    for q in h["rows"]:
        g.setdefault(q.get("rid", rid), []).append(q)
    return [(k, sorted(g[k], key=lambda q: (q["mm"], q["dd"]))) for k in sorted(g, key=C.ymd)]


def prep(rows):
    """1走ぶんの仕上げを要約する。"""
    return dict(n=len(rows),
                ashi=max((r["av"] or 0) for r in rows),
                ashi_name=max(rows, key=lambda r: r["av"] or 0)["ashi"] or "—",
                place={r["course"] for r in rows},
                yobi=rows[-1]["yobi"],
                awase=any(r["awase"] for r in rows),
                load=any(r["load"].strip() for r in rows))


def gap(a, b):
    """2走の間隔（日）。レースIDから日付を作る。"""
    try:
        f = lambda r: date(int(r[:4]), int(r[12:14]), int(r[14:16]))
        return (f(b) - f(a)).days
    except Exception:
        return None


def deviations(h, rid):
    """今回（最後の走）が、それ以前の標準形からどう外れているか。"""
    g = by_race(h, rid)
    if len(g) < MIN_PAST + 1:
        return None
    past = [prep(r) for _, r in g[:-1]]
    now = prep(g[-1][1])
    d = gap(g[-2][0], g[-1][0])

    std = dict(n=st.median([p["n"] for p in past]),
               ashi=st.median([p["ashi"] for p in past]),
               ashi_name=Counter(p["ashi_name"] for p in past).most_common(1)[0][0],
               place=set().union(*[p["place"] for p in past]),
               yobi=Counter(p["yobi"] for p in past).most_common(1)[0][0],
               awase=sum(p["awase"] for p in past) / len(past))

    # ★中央値が 1.5 のような半端値のとき、0.5差を逸脱と呼ばない。
    #   丸めて表示すると「2→2本」が逸脱として出てしまう（実際に出た）。
    out = []
    if now["n"] - std["n"] >= 1:
        why = "（間隔で説明できる）" if (d and d >= LONG_REST) else "★間隔では説明できない"
        out.append(f"本数 {std['n']:g}→{now['n']}本 {why}")
    elif std["n"] - now["n"] >= 1:
        out.append(f"本数 {std['n']:g}→{now['n']}本（減らした）")
    if now["ashi"] - std["ashi"] >= 1:
        out.append(f"脚色 {std['ashi_name']}→{now['ashi_name']}（強めた）")
    elif std["ashi"] - now["ashi"] >= 1:
        out.append(f"脚色 {std['ashi_name']}→{now['ashi_name']}（緩めた）")
    new = now["place"] - std["place"]
    if new:
        out.append(f"施設 {'/'.join(sorted(new))} を初めて使った")
    if now["yobi"] and std["yobi"] and now["yobi"] != std["yobi"]:
        out.append(f"曜日 {std['yobi']}→{now['yobi']}")
    if now["awase"] and std["awase"] < 0.34:
        out.append("単走ばかりだったのに併せた")
    elif not now["awase"] and std["awase"] > 0.66:
        out.append("いつも併せるのに単走")
    if now["load"]:
        out.append("負荷印☆が付いた")
    return dict(dev=out, gap=d, std=std, now=now, rid=g[-1][0],
                last=C.race_meta(g[-1][0]), nrace=len(g))


def main():
    ap = argparse.ArgumentParser(description="その馬自身の標準形からの逸脱を出す")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--min", type=int, default=1, help="この件数以上の逸脱だけ")
    a = ap.parse_args()

    found = []
    for p in [x for g in a.paths for x in glob.glob(g)]:
        D = json.load(open(p))
        for rid, hs in D.items():
            for ub, h in hs.items():
                r = deviations(h, rid)
                if r and len(r["dev"]) >= a.min:
                    found.append((int(rid[10:12]), int(ub), h, r))
    found.sort(key=lambda x: (-len(x[3]["dev"]), x[0], x[1]))

    print("■ 標準形からの逸脱（重みは置かない。数えるだけ）\n")
    for rr, ub, h, r in found:
        m = r["last"]
        # 今走の調教がまだ公開されていないと、「直近」が過去走にずれる。
        print(f"{rr:>2}R {ub:>2}番 {h['name']:<15}逸脱{len(r['dev'])}件"
              f"   直近={m['mm']}/{m['dd']}{m['place']}{m['r']}R"
              + (f"   間隔{r['gap']}日" if r["gap"] else ""))
        print(f"        標準形  {r['std']['n']:g}本 / {r['std']['ashi_name']} / "
              f"{r['std']['yobi']}曜 / {'・'.join(sorted(r['std']['place']))}")
        for d in r["dev"]:
            print(f"        ・{d}")
        print()
    print(f"  {len(found)}頭。★印は出走間隔で説明できない本数増＝陣営が作りに行った可能性")
    print("  ※次は【オッズと突き合わせ】。逸脱していて人気していない馬だけが値段になる")
    print("  ※これは予想であって検証ではない。答え合わせは走ったあとで")


if __name__ == "__main__":
    main()
