#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""1開催ぶんの調教を、出走馬の近N走までさかのぼって一括で集める。

なぜ要るか:
  ・1レースの調教ページには直近1〜3本しか載らない
    （川崎は【1頭1本が7割】。単体では変化の向きが原理的に測れない）
  ・今走の調教がまだ公開されていない開催でも、出馬表は先に出る
    → 出馬表から出走馬を取り、過去走の調教だけ先に集めておける

取ってくるもの:
    出馬表 /chihou/syutuba/{rid}        出走馬と umacd
    馬     /db/uma/{umacd}              過去走のレースID
    調教   /chihou/cyokyo/1/0/{rid}     各過去走の追い切り

すべて scripts/ana/arc/ にキャッシュするので、
途中で止めても再実行すれば続きから進みます（取得済みは再取得しない）。

使い方:
    python3 scripts/ana/cyokyo_shushu.py --pre 2026101101 --mmdd 0907 --back 5
    python3 scripts/ana/cyokyo_shushu.py --pre 2026101101 --mmdd 0907 --back 5 --races 1-6
    # 出来た JSON を読む
    python3 scripts/ana/cyokyo_shushu.py --report out/cyokyo_2026101101_0907.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cyokyo_jikei as C

OUT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "out")


def collect(pre, mmdd, back, races, dst):
    """★1鞍ごとにJSONへ書き出す。

    以前は最後にまとめて書いていたため、途中でプロセスが落ちたときに
    6鞍ぶんの取得が全部消えた。取れた端から保存する。
    """
    got = json.load(open(dst)) if os.path.exists(dst) else {}
    t0 = time.time()
    total = len(races)
    for i, r in enumerate(races, 1):
        rid = f"{pre}{r:02d}{mmdd}"
        try:
            D = C.with_history(rid, back)
        except Exception as e:                      # 1鞍の失敗で全部止めない
            print(f"  {r:>2}R  × {e}", flush=True)
            continue
        got[rid] = {str(ub): dict(name=h["name"], umacd=h["umacd"],
                                  soukan=h["soukan"], arrow=h["arrow"],
                                  mark=C.trend(h["rows"])[0], why=C.trend(h["rows"])[1],
                                  rows=h["rows"]) for ub, h in D.items()}
        json.dump(got, open(dst, "w"), ensure_ascii=False)   # 1鞍ごとに保存
        n = sum(len(h["rows"]) for h in D.values())
        el = time.time() - t0
        eta = el / i * (total - i)
        print(f"  {r:>2}R  {len(D):>2}頭 / 追い切り {n:>3}本   "
              f"[{i}/{total}]  経過{el/60:.1f}分  残り約{eta/60:.0f}分", flush=True)
    return got


def report(path):
    D = json.load(open(path))
    star = []
    for rid, hs in sorted(D.items()):
        r = int(rid[10:12])
        for ub, h in sorted(hs.items(), key=lambda x: int(x[0])):
            if h["mark"] in ("★", "○"):
                star.append((r, int(ub), h))
    print(f"■ {len(D)}鞍 / {sum(len(v) for v in D.values())}頭\n")
    print("■ 上げてきている馬（★＝同じ脚色のまま時計が縮んだ／○＝追って縮んだ）")
    for r, ub, h in star:
        print(f"  {r:>2}R {ub:>2}番 {h['name']:<14}{h['mark']}  {h['why']}")
    print(f"\n  ★ {sum(1 for x in star if x[2]['mark']=='★')}頭 "
          f"／ ○ {sum(1 for x in star if x[2]['mark']=='○')}頭")
    print("  ※ ○ は「強く追えば速くなる」ぶんを含む。★のほうが情報として強い")


def linked(path, only=None):
    """1頭ずつ、【走ごとに区切って】調教を紐づけて出す。

    走の切れ目が見えないと「前走の仕上げ」と「今回の仕上げ」を比べられない。
    ここが分かって初めて『上げてきているか』を目で読める。
    """
    D = json.load(open(path))
    for rid, hs in sorted(D.items(), key=lambda x: int(x[0][10:12])):
        print(f"\n{'='*76}\n■ {int(rid[10:12])}R\n{'='*76}")
        for ub, h in sorted(hs.items(), key=lambda x: int(x[0])):
            if only and only not in h["name"]:
                continue
            print(f"\n{int(ub):>2}番 {h['name']}"
                  + (f"   総評:{h['soukan']}" if h["soukan"] else "")
                  + (f" 矢印:{h['arrow']}" if h["arrow"] else ""))
            byrace = {}
            for q in h["rows"]:
                byrace.setdefault(q.get("rid", rid), []).append(q)
            ks = sorted(byrace, key=C.ymd)
            for k in ks:
                m = C.race_meta(k)
                tag = "今走" if k == rid else f"{len(ks)-1-ks.index(k)}走前"
                w, dw = (None, None) if k == rid else C.weight_of(k, h["name"])
                wt = f"  馬体重 {w}({dw})" if w else ""
                print(f"  ┌ {tag:<5} {m['y']%100}/{m['mm']:>2}/{m['dd']:<2} "
                      f"{m['place']}{m['r']}R {m['name'][:20]}{wt}")
                for q in byrace[k]:
                    t = "  ".join(f"{v:.1f}" for v in q["cum"]) or "—"
                    one = f"{q['f1']:.1f}" if q["f1"] else "—"
                    print(f"  │  {q['mark']}{q['load']} {q['mm']:>2}/{q['dd']:<2}"
                          f"({q['yobi'] or '?'}) {q['course'][:7]:<7}{q['baba'][:2]:<3}"
                          f"{t:<22}{one:>5}  {(q['ashi'] or '—'):<5}"
                          f"{(q['awase'] or ''):<4}{q['note']}")
            if not byrace:
                print("  （調教の記載なし）")
            print(f"  └ {len(h['rows'])}本   {h['mark'] or ' '} {h['why']}")


def main():
    ap = argparse.ArgumentParser(description="1開催ぶんの調教を近N走まで集める")
    ap.add_argument("--pre", help="レースIDの先頭10桁（開催コード）")
    ap.add_argument("--mmdd", help="開催日 MMDD")
    ap.add_argument("--back", type=int, default=5)
    ap.add_argument("--races", default="1-12", help="例 1-12 / 3-6")
    ap.add_argument("--report", help="集め終わったJSONを読んで要約する")
    ap.add_argument("--linked", help="JSONを読んで、1頭ずつ走ごとに紐づけて出す")
    ap.add_argument("--horse", help="--linked のとき1頭に絞る")
    a = ap.parse_args()

    if a.linked:
        return linked(a.linked, a.horse)
    if a.report:
        return report(a.report)
    if not (a.pre and a.mmdd):
        ap.error("--pre と --mmdd が要ります")

    lo, _, hi = a.races.partition("-")
    races = list(range(int(lo), int(hi or lo) + 1))
    os.makedirs(OUT, exist_ok=True)
    dst = os.path.join(OUT, f"cyokyo_{a.pre}_{a.mmdd}.json")
    print(f"■ {a.pre} {a.mmdd}  {len(races)}鞍 × 近{a.back}走 を集めます")
    print(f"   取得済みはキャッシュを使うので、止めて再実行すれば続きから進みます\n")
    collect(a.pre, a.mmdd, a.back, races, dst)
    print(f"\n→ {dst}")
    report(dst)


if __name__ == "__main__":
    main()
