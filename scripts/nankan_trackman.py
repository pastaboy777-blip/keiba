# -*- coding: utf-8 -*-
"""南関版トラックマン表：1開催を『完タイム差』と『レベル2軸』で並べる。

トラックマンの時計比較表と同じ形にする。ただし A〜E は目分量ではなく実測から付ける。

    完タイム差   ＝ タイム差 − 馬場差×(距離/1000)      … nankan_babasa と同じ式
                   馬場差は前半(1〜6R)/後半(7〜12R)で分けて持つ。1日1つにすると
                   午後に速くなった日の後半レースを軒並み過大評価する
                   （7/02は前半+0.17→後半−0.47で、後半4鞍が0.3〜0.5秒ぶん甘く出ていた）
                   ただし生のドリフトはほぼノイズなので DRIFT_SHRINK 倍に縮めて使う。
                   奇数R/偶数R で割った偽ドリフトがほぼ同じ大きさで出る
                   （scripts/nankan_drift_test.py）。
    タイムレベル ＝ 完タイム差の分位（速いほど A）
    メンバーレベル＝ 出走馬のその後の成績（nankan_racelevel と同じ、4着以下の敗者で測る）

  2軸に分けるのが肝で、この2つは別物である。速い時計が出ても相手が弱ければ次に繋がらないし、
  時計が平凡でもメンバーが強ければ、そこの敗戦馬は次で走る。
  2026-08-01 に中央493レースで時計指数だけの順位付けが控除率どおりだったのは、
  時計しか見ていなかったからでもある。

  ★メンバーレベルはレースより後の出走で測るので、開催直後はまだ薄い。
    後続が足りないレースは「-」と出る。時間が経つほど確度が上がる。

    python3 scripts/nankan_trackman.py --place 船橋 --days 2026-06-28 2026-06-29 2026-07-02 2026-07-03 2026-07-04
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
from nankeiba.scraping.race_id import NANKAN_CODES
from nankeiba.scraping import parser as P

from nankan_babasa import DRIFT_BASE, DRIFT_SHRINK, REF, grade, par_key, sec
from nankan_racelevel import VENUES, collect
from nankan_zubu_backtest import CARD, PERF, race_days


def band(v, cuts, labels="ABCDE"):
    """値を A〜E に落とす。cuts は小さい側から4つの境目。"""
    for i, c in enumerate(cuts):
        if v <= c:
            return labels[i]
    return labels[-1]


def wid(s, n):
    o, c = "", 0
    for ch in str(s or ""):
        k = 2 if ord(ch) > 0x2000 else 1
        if c + k > n:
            break
        o += ch
        c += k
    return o + " " * (n - c)


def main():
    ap = argparse.ArgumentParser(description="南関版トラックマン表")
    ap.add_argument("--place", default="船橋", choices=list(NANKAN_CODES))
    ap.add_argument("--days", nargs="+", required=True, help="表にする開催日")
    ap.add_argument("--std-from", default="2026-05-01", help="標準タイムを作る期間の開始")
    ap.add_argument("--level-from", default="2026-01-01", help="メンバーレベル収集の開始")
    ap.add_argument("--tsv", help="画像化などに使うTSVの書き出し先。桁揃えで馬名が切れないよう生値で出す")
    args = ap.parse_args()

    client = PoliteClient(use_cache=True)
    targets = [date.fromisoformat(x) for x in args.days]
    last = max(targets)

    # ---- 時計側：標準タイムと馬場差
    days = race_days(client, args.place, date.fromisoformat(args.std_from), last)
    rec = []
    for d, rs in days:
        for rno, rid in sorted(rs.items()):
            try:
                res = P.parse_result_page(client.get(PERF.format(r=rid)), rid)
                cls = P.parse_race_class(client.get(CARD.format(r=rid)))
            except Exception:
                continue
            top = sorted([r for r in res.rows if r.finish_pos], key=lambda r: r.finish_pos)[:2]
            t = sec(top[0].time) if top else None
            if t is None or not res.distance:
                continue
            rec.append(dict(d=d, rno=rno, rid=rid, dist=res.distance, g=grade(cls),
                            baba=res.baba, t=t, win=top[0].horse_name,
                            second=top[1].horse_name if len(top) > 1 else "",
                            pop=top[0].popularity))
        print(f"\r  時計 {d}", end="", flush=True)

    by_cond, by_dist = defaultdict(list), defaultdict(list)
    for r in rec:
        by_cond[par_key(r["dist"], r["g"])].append(r["t"])
        by_dist[r["dist"]].append(r["t"])
    std = {k: st.median(v) for k, v in by_cond.items() if len(v) >= 3}
    std_d = {k: st.median(v) for k, v in by_dist.items()}
    for r in rec:
        b = std.get(par_key(r["dist"], r["g"]), std_d.get(r["dist"]))
        r["diff"] = round(r["t"] - b, 2) if b else None
    byday, byhalf = defaultdict(list), defaultdict(list)
    for r in rec:
        if r["diff"] is not None:
            v = r["diff"] / (r["dist"] / 1000)
            byday[r["d"]].append(v)
            byhalf[(r["d"], r["rno"] <= 6)].append(v)
    variant = {d: st.median(v) for d, v in byday.items()}
    raw_half = {k: st.median(v) for k, v in byhalf.items() if len(v) >= 4}
    base = -DRIFT_BASE / 2 * 1000 / REF   # 前半に+base（遅い側）、後半に-base
    half = {k: variant[k[0]] + (base if k[1] else -base)
               + (v - variant[k[0]]) * DRIFT_SHRINK
            for k, v in raw_half.items()}
    for d in variant:
        for first in (True, False):
            half.setdefault((d, first), variant[d] + (base if first else -base))
    for r in rec:
        if r["diff"] is not None:
            r["v"] = half.get((r["d"], r["rno"] <= 6), variant[r["d"]])
            r["kan"] = round(r["diff"] - r["v"] * (r["dist"] / 1000), 2)
    kans = sorted(r["kan"] for r in rec if r.get("kan") is not None)
    q = [kans[int(len(kans) * p)] for p in (0.10, 0.30, 0.70, 0.90)]   # 速い順にA〜E

    # ---- メンバー側：出走馬のその後（4着以下の敗者で測る）
    print("\r" + " " * 24 + "\r", end="")
    races, timeline = collect(client, VENUES,
                              date.fromisoformat(args.level_from), last + timedelta(days=40))
    raw = {}
    for rid, r in races.items():
        tot, cov = 0.0, 0
        for row in r["rows"]:
            if row.finish_pos < 4:
                continue
            later = [x for x in timeline[row.horse_id] if x[0] > r["date"]]
            if not later:
                continue
            cov += 1
            tot += st.mean(x[2] for x in later)
        if cov >= 4:
            raw[rid] = (tot, cov)
    g0 = sum(v[0] for v in raw.values()) / sum(v[1] for v in raw.values())
    lv = {rid: (t + 8 * g0) / (c + 8) for rid, (t, c) in raw.items()}
    mu, sd = st.mean(lv.values()), st.pstdev(lv.values())

    if args.tsv:
        # 表示用の桁揃えは全角を2文字幅で切るため馬名が途切れる。加工用には生値を渡す。
        with open(args.tsv, "w") as f:
            for d in targets:
                v = variant.get(d)
                for r in sorted([x for x in rec if x["d"] == d and x.get("kan") is not None],
                                key=lambda x: x["rno"]):
                    z = (lv[r["rid"]] - mu) / sd if r["rid"] in lv and sd else None
                    fh, bh = half.get((d, True)), half.get((d, False))
                    dr = ((bh - fh) * REF / 1000) if fh is not None and bh is not None else 0.0
                    f.write("\t".join(str(x) for x in [
                        d, r["baba"] or "?", f"{v * REF / 1000:+.2f}",
                        f"{r['v'] * REF / 1000:+.2f}", f"{dr:+.2f}", r["rno"], r["dist"],
                        r["win"], r["second"], r["g"], f"{r['t']:.1f}",
                        f"{r['diff']:+.2f}", f"{r['kan']:+.2f}", band(r["kan"], q),
                        band(-z, (-1.5, -0.5, 0.5, 1.5)) if z is not None else "-"]) + "\n")
        print(f"TSV → {args.tsv}")

    for d in targets:
        day = sorted([r for r in rec if r["d"] == d and r.get("kan") is not None],
                     key=lambda r: r["rno"])
        if not day:
            print(f"\n{d}：データなし")
            continue
        bb = "/".join(sorted({r["baba"] or "?" for r in day}))
        fh, bh = half.get((d, True)), half.get((d, False))
        ext = ("" if fh is None or bh is None else
               f"　前半 {fh * REF / 1000:+.2f} → 後半 {bh * REF / 1000:+.2f}")
        print(f"\n■ {args.place} {d}（{bb}）　馬場差 "
              f"{variant[d] * REF / 1000:+.1f}秒{ext}（{REF}m換算・マイナスが速い）")
        print(f"{'R':>3}{'距離':>6} {'優勝馬':<16}{'2着':<16}{'条件':<5}"
              f"{'走破':>7}{'タイム差':>8}{'完タイム差':>10}  {'時計':<4}{'メンバー'}")
        for r in day:
            z = (lv[r["rid"]] - mu) / sd if r["rid"] in lv and sd else None
            tl = band(r["kan"], q)
            ml = band(-z, (-1.5, -0.5, 0.5, 1.5)) if z is not None else "-"
            print(f"{r['rno']:>3}{r['dist']:>6} {wid(r['win'],16)}{wid(r['second'],16)}"
                  f"{wid(r['g'],5)}{r['t']:>7.1f}{r['diff']:>+8.2f}{r['kan']:>+10.2f}  "
                  f"{tl:<4}{ml}")

    print(f"\n  時計レベル：完タイム差の分位（A=上位10% / E=下位10%）"
          f"　境目 {q[0]:+.2f} {q[1]:+.2f} {q[2]:+.2f} {q[3]:+.2f}")
    print("  メンバーレベル：4着以下の馬のその後の成績（A=偏差+1.5以上）。"
          "後続が4頭に満たないレースは「-」。")


if __name__ == "__main__":
    main()
