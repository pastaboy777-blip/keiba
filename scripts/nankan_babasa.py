# -*- coding: utf-8 -*-
"""南関：日ごとの馬場差を実測し、走破タイムを『完タイム差』に直す。

考え方はトラックマンの時計比較表と同じ:

    完タイム差 ＝ タイム差 ＋ 馬場差（距離で按分） ＋ 補正値

  タイム差 … 勝ちタイム − その条件(場・距離・クラス)の標準
  馬場差   … その日の速さのズレ。距離に比例して効かせる。
             1日の中でも砂は動くので 前半(1〜6R)/後半(7〜12R) に分けて持つ（ドリフト）。
             ただし生のドリフトはほぼノイズ。同じ日を奇数R/偶数R で割った偽ドリフトが
             ほぼ同じ大きさで出る（船橋 本物SD0.60 vs 偽SD0.48／川崎 0.48 vs 0.42、
             scripts/nankan_drift_test.py）。本物の成分は船橋0.36秒・川崎0.23秒ぶんしかない。
             そこで信号対雑音比から DRIFT_SHRINK 倍に縮めて使う。生値は使わないこと。
  補正値   … 展開など個別事情。ここでは扱わない（0とする）

なぜ必要か（2026-08-01 の失敗）:
  馬場を「良・稍・重・不」の発表で扱っていた。川崎7か月で測ると勝ち馬の上がりは
  良39.34／稍39.46／重39.78／不39.14 と 0.64秒しか動かず、しかも不良がいちばん速かった。
  発表の馬場は、その日の速さを表していない。
  日ごとに実測した1つの数字でなければ、時計は日をまたいで比較できない。

  馬場差が分かると副産物がある。「後方から上がり最速で負けた馬」を評価するとき、
  その上がりが本当に速かったのか、その日が全体的に速かっただけなのかを分離できる。

    python3 scripts/nankan_babasa.py --place 船橋 --from 2026-05-01 --to 2026-07-04
    python3 scripts/nankan_babasa.py --place 船橋 --from 2026-05-01 --to 2026-07-04 --races 2026-06-05
"""
from __future__ import annotations

import argparse
import re
import statistics as st
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping.race_id import NANKAN_CODES
from nankeiba.scraping import parser as P

from nankan_zubu_backtest import CARD, PERF, race_days

REF = 1400            # 馬場差を表示する基準距離
DRIFT_BASE = -0.258   # 後半−前半の全日平均（1400m換算）。南関4場68日で z=-3.9。
                      # 級を見ないparだと -1.059 出るが、par に級を入れると 76% 消える。
                      # 残ったこの分だけが構造的で、日ごとの推定より桁違いに安定している。
DRIFT_SHRINK = 0.3    # 日ごとのズレのうち効かせる割合。信号²/(信号²+雑音²) から


def sec(t):
    m = re.match(r"(\d+):(\d+)\.(\d)", t or "")
    return int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 10 if m else None


def grade(cls):
    """クラス表記を粗い級に落とす。標準タイムをこの単位で作るので、取りこぼすと時計が歪む。

    南関の表記ゆれ:
      Ｃ３五 / Ｂ２ / Ａ１        → C3 / B2 / A1
      ２歳二 / ３歳(七)          → 2歳 / 3歳
      帝王賞（Ｊｐｎ１）選定馬重賞 → 重賞     ← A級より上。分けないと標準が狂う
      短夜賞（準重賞） ３上 オープン → 準重
      ゆりかもめオープン競走 オープン特別 → OP特
      さきたま杯 ３上 オープン    → 重賞（Ｊｐｎ表記を先に見る）
    """
    if not cls:
        return "?"
    c = cls.translate(str.maketrans("ＡＢＣ０１２３４５６７８９", "ABC0123456789"))
    # 格の高い順に判定する。オープンの語は重賞名にも含まれるので順番を崩さないこと。
    if "Ｊｐｎ" in cls or "Jpn" in cls or re.search(r"[（(]G[ⅠⅡⅢ123]", cls):
        return "重賞"
    if "準重賞" in c:
        return "準重"
    if "重賞" in c:
        return "重賞"
    if "オープン特別" in c:
        return "OP特"
    if "オープン" in c:
        return "OP"
    if "歳" in c and not re.search(r"[ABC]", c):
        m = re.search(r"(\d)歳", c)
        return m.group(1) + "歳" if m else "?"
    m = re.search(r"([ABC])\s*(\d)?", c)
    return m.group(1) + (m.group(2) or "") if m else "?"


# A級以上は1場あたり年に数本しかなく、級ごとにparを作れない。
# 距離だけのpar（2歳〜C3込みの中央値）に落とすと大幅に速く出てしまうので、
# par を引くときだけ「A+」にまとめる。表示は元の級のまま残す。
TOP = {"A", "A1", "A2", "OP", "OP特", "準重", "重賞"}


def par_key(dist, g):
    return (dist, "A+" if g in TOP else g)


def main():
    ap = argparse.ArgumentParser(description="南関の日ごと馬場差と完タイム差")
    ap.add_argument("--place", default="船橋", choices=list(NANKAN_CODES))
    ap.add_argument("--from", dest="d_from", required=True)
    ap.add_argument("--to", dest="d_to", required=True)
    ap.add_argument("--races", help="この日の各レースの完タイム差を明細で出す")
    args = ap.parse_args()

    client = PoliteClient(use_cache=True)
    days = race_days(client, args.place,
                     date.fromisoformat(args.d_from), date.fromisoformat(args.d_to))

    rec = []
    for d, rs in days:
        for rno, rid in sorted(rs.items()):
            try:
                html = client.get(PERF.format(r=rid))
                res = P.parse_result_page(html, rid)
                cls = P.parse_race_class(client.get(CARD.format(r=rid)))
            except Exception:
                continue
            w = next((r for r in res.rows if r.finish_pos == 1), None)
            t = sec(w.time) if w else None
            if t is None or not res.distance:
                continue
            rec.append(dict(d=d, rno=rno, dist=res.distance, g=grade(cls),
                            baba=res.baba, t=t, name=w.horse_name, pop=w.popularity))
        print(f"\r  収集 {d}", end="", flush=True)
    print("\r" + " " * 30 + "\r", end="")
    if not rec:
        raise SystemExit("データなし")

    # 標準タイム：場・距離・級ごとの中央値。同じ条件が3本未満なら距離だけで代用する。
    by_cond = defaultdict(list)
    by_dist = defaultdict(list)
    for r in rec:
        by_cond[par_key(r["dist"], r["g"])].append(r["t"])
        by_dist[r["dist"]].append(r["t"])
    std = {k: st.median(v) for k, v in by_cond.items() if len(v) >= 3}
    std_d = {k: st.median(v) for k, v in by_dist.items()}

    for r in rec:
        base = std.get(par_key(r["dist"], r["g"]), std_d.get(r["dist"]))
        r["diff"] = round(r["t"] - base, 2) if base else None

    # 馬場差：その日のタイム差を1000mあたりに直した中央値。距離をまたいでも足並みが揃う。
    # さらに前半/後半に割る。砂は散水と踏み固めで1日の中でも動くので、
    # 1日1つの数字にすると後半のレースに前半の馬場を当ててしまう。
    byday, byhalf = defaultdict(list), defaultdict(list)
    for r in rec:
        if r["diff"] is not None:
            v = r["diff"] / (r["dist"] / 1000)
            byday[r["d"]].append(v)
            byhalf[(r["d"], r["rno"] <= 6)].append(v)
    variant = {d: st.median(v) for d, v in byday.items()}
    raw_half = {k: st.median(v) for k, v in byhalf.items() if len(v) >= 4}
    # 全日共通の傾き（前半は遅く・後半は速く）を必ず入れたうえで、
    # その日固有のズレだけを DRIFT_SHRINK 倍して足す。日ごとの生値は当てにならない。
    # DRIFT_BASE は「後半−前半」なので負＝後半が速い。前半には遅い側(+)、後半には速い側(-)を当てる。
    base = -DRIFT_BASE / 2 * 1000 / REF       # 1000mあたりに直した半分。前半は+base、後半は-base
    half = {k: variant[k[0]] + (base if k[1] else -base)
               + (v - variant[k[0]]) * DRIFT_SHRINK
            for k, v in raw_half.items()}
    for d in variant:                          # 前後半が取れない日も傾きだけは当てる
        for first in (True, False):
            half.setdefault((d, first), variant[d] + (base if first else -base))

    for r in rec:
        if r["diff"] is not None:
            v = half.get((r["d"], r["rno"] <= 6), variant[r["d"]])
            r["v"] = v
            r["kan"] = round(r["diff"] - v * (r["dist"] / 1000), 2)

    if args.races:
        target = date.fromisoformat(args.races)
        v = variant.get(target)
        if v is None:
            raise SystemExit(f"{args.races} は対象外")
        f_, b_ = half.get((target, True)), half.get((target, False))
        ext = ("" if f_ is None or b_ is None else
               f"　前半 {f_ * REF / 1000:+.2f} → 後半 {b_ * REF / 1000:+.2f}"
               f"（ドリフト {(b_ - f_) * REF / 1000:+.2f}）")
        print(f"\n■ {args.place} {target}　馬場差 {v * REF / 1000:+.1f}秒{ext}"
              f"（{REF}m換算／マイナスは速い馬場）\n")
        print(f"{'R':>3}{'距離':>6}{'級':>5}{'馬場':>4}{'勝ち馬':<16}"
              f"{'走破':>8}{'タイム差':>9}{'完タイム差':>11}")
        for r in sorted([x for x in rec if x["d"] == target], key=lambda x: x["rno"]):
            if r["diff"] is None:
                continue
            print(f"{r['rno']:>3}{r['dist']:>6}{r['g']:>5}{r['baba'] or '?':>4}"
                  f"{r['name']:<16}{r['t']:>8.1f}{r['diff']:>+9.2f}{r['kan']:>+11.2f}")
        return

    print(f"\n■ {args.place} {args.d_from}〜{args.d_to}　日ごとの馬場差"
          f"（{REF}m換算・マイナスが速い馬場）\n")
    print(f"{'日付':<12}{'発表馬場':<10}{'R':>3}{'1日':>7}{'前半':>7}{'後半':>7}"
          f"{'生ドリフト':>11}{'採用':>7}")
    for d in sorted(variant):
        day = [r for r in rec if r["d"] == d and r["diff"] is not None]
        bb = "/".join(sorted({r["baba"] or "?" for r in day}))
        f_ = half.get((d, True))
        b_ = half.get((d, False))
        g = lambda v: f"{v * REF / 1000:+.2f}" if v is not None else "  -  "
        rf, rb = raw_half.get((d, True)), raw_half.get((d, False))
        raw = (f"{(rb - rf) * REF / 1000:+.2f}" if rf is not None and rb is not None else "  -  ")
        dr = (f"{(b_ - f_) * REF / 1000:+.2f}" if f_ is not None and b_ is not None else "  -  ")
        print(f"{str(d):<12}{bb:<10}{len(day):>3}{g(variant[d]):>7}{g(f_):>7}{g(b_):>7}"
              f"{raw:>11}{dr:>7}")
    vs = [v * REF / 1000 for v in variant.values()]
    drs = [(raw_half[(d, False)] - raw_half[(d, True)]) * REF / 1000 for d in variant
           if (d, True) in raw_half and (d, False) in raw_half]
    print(f"\n  馬場差の幅 {min(vs):+.2f}〜{max(vs):+.2f}秒（{max(vs)-min(vs):.2f}秒）")
    if drs:
        print(f"  生ドリフト（後半−前半）の幅 {min(drs):+.2f}〜{max(drs):+.2f}秒"
              f"／平均 {st.mean(drs):+.2f}秒。プラスは後半にかけて重くなった日。")
        print(f"  ただし日ごとの生値は偽ドリフト（偶数R−奇数R）と同程度のブレなので、"
              f"効かせるのは {DRIFT_SHRINK:g} 倍だけ。")
        print(f"  加えて全日共通の傾き {DRIFT_BASE:+.2f}秒（後半が速い）を必ず入れる。"
              f"南関68日で z=-3.9。")
    print("  ※標準タイムは同じ期間から作っているので、日数が少ないと自分自身に引きずられる。")


if __name__ == "__main__":
    main()
