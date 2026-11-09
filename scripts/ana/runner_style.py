#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""走行位置の癖（レイラー／ミッド／ワイド）を南関で作る。

ドッグレースの分類をそのまま持ち込む:
    レイラー   … 内ラチ沿いを走る
    ミッド     … 中程
    ワイド     … 外を回る
ドッグレースではこれと枠の噛み合わせが予想の核心になる。

南関でどう取るか:
  通過順の括弧は併走を表し、【括弧の中は内側の馬から順に書かれる】。
  この規約から、括弧に入った馬の内外が復元できる（南関全体の54%が判定可能）。
      3角と4角の両方を使う。

      括弧内の位置 k / (併走頭数-1)   →  0=内 / 1=外
      括弧に入らない単独の馬は判定不能なので捨てる

★交絡を必ず落とすこと:
  そのまま平均すると「ワイドランナー」の正体が【外枠を引くことが多かった】に
  なりかねない。枠から期待される内外を引いて、残差だけを癖とする。
      癖 = 実際の内外 − 枠から期待される内外

測ること:
  ① 癖は本当に安定した性質か
     各馬の履歴を前半・後半に割って、両者が相関するかを見る。
     相関しなければ、それは癖ではなくその日の偶然。
  ② ドッグレースと同じ噛み合わせが効くか
     ワイドランナーが内枠 → 外へ張られる／レイラーが外枠 → 内へ入れない
     という損得が、南関にもあるか。

使い方:
  python3 scripts/ana/runner_style.py
  python3 scripts/ana/runner_style.py --horse ジューンアカデミー
"""
from __future__ import annotations

import argparse
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bt

MIN_RUNS = 4          # 癖を判定するのに要る走数


def lateral(cs):
    """コーナー通過順の文字列 → {馬番: 内外(0=内 1=外)}。括弧に入った馬だけ。"""
    out = {}
    for tok in re.findall(r"\([^)]*\)|\d+", cs or ""):
        if not tok.startswith("("):
            continue
        vs = [int(v) for v in re.findall(r"\d+", tok)]
        if len(vs) < 2:
            continue
        for k, u in enumerate(vs):
            out.setdefault(u, []).append(k / (len(vs) - 1))
    return {u: st.mean(v) for u, v in out.items()}


def collect(R):
    """(馬名, 実際の内外, 枠の相対位置) を集める。3角と4角の両方から。"""
    rows = []
    for r in R:
        if r["n"] < 6:
            continue
        lat = defaultdict(list)
        for cs in (r.get("c3"), r.get("c4")):
            for u, v in lateral(cs).items():
                lat[u].append(v)
        for x in r["rows"]:
            if not x["ub"] or x["ub"] not in lat:
                continue
            rows.append(dict(name=x["name"], date=r["date"],
                             lat=st.mean(lat[x["ub"]]),
                             gate=(x["ub"] - 1) / (r["n"] - 1),
                             chaku=x["chaku"], n=r["n"], ninki=x["ninki"],
                             odds=x["odds"], dist=r["dist"]))
    return rows


def slope(X, Y):
    mx, my = st.mean(X), st.mean(Y)
    sxx = sum((x - mx) ** 2 for x in X)
    return (sum((x - mx) * (y - my) for x, y in zip(X, Y)) / sxx, mx, my) if sxx else (0, mx, my)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horse")
    a = ap.parse_args()
    R = bt.load("2026-01-01", "2026-12-31")
    rows = collect(R)
    print(f"■ 南関 {len(R):,}レース／内外が判定できた {len(rows):,}走\n")

    b, mx, my = slope([q["gate"] for q in rows], [q["lat"] for q in rows])
    print(f"■ 枠 → 実際の内外 の傾き {b:+.3f}")
    print("   1.0なら枠どおり／0なら枠と無関係。この分を引いてから癖にする")
    for q in rows:
        q["kuse"] = q["lat"] - (b * (q["gate"] - mx) + my)     # ＋なら枠のわりに外

    by = defaultdict(list)
    for q in rows:
        by[q["name"]].append(q)
    kuse = {k: st.mean(q["kuse"] for q in v) for k, v in by.items() if len(v) >= MIN_RUNS}
    v = sorted(kuse.values())
    print(f"\n■ 癖を出せた馬 {len(kuse):,}頭（{MIN_RUNS}走以上）")
    print(f"   中央 {st.median(v):+.3f}   5%tile {v[len(v)//20]:+.3f}   95%tile {v[-len(v)//20]:+.3f}")

    if a.horse:
        w = by.get(a.horse, [])
        print(f"\n■ {a.horse}  {len(w)}走")
        for q in sorted(w, key=lambda z: z["date"]):
            print(f"   {q['date']} {q['dist']}m {q['n']}頭 {q['chaku']}着  "
                  f"枠{q['gate']:.2f}  内外{q['lat']:.2f}  癖{q['kuse']:+.2f}")
        if a.horse in kuse:
            k = kuse[a.horse]
            print(f"   → 癖 {k:+.3f}  "
                  f"（{'ワイド' if k > 0.08 else ('レイラー' if k < -0.08 else 'ミッド')}）")
        return

    # ---- ① 癖は安定した性質か。履歴を前半・後半に割って相関を見る ----
    A, B = [], []
    for nm, w in by.items():
        if len(w) < MIN_RUNS * 2:
            continue
        w = sorted(w, key=lambda z: z["date"])
        h = len(w) // 2
        A.append(st.mean(q["kuse"] for q in w[:h]))
        B.append(st.mean(q["kuse"] for q in w[h:]))
    if len(A) > 50:
        s, _, _ = slope(A, B)
        ma, mb = st.mean(A), st.mean(B)
        sa = st.pstdev(A); sb = st.pstdev(B)
        cor = sum((x - ma) * (y - mb) for x, y in zip(A, B)) / len(A) / (sa * sb)
        print(f"\n■ ① 癖は安定しているか（{len(A)}頭を前半・後半に割った）")
        print(f"   相関 {cor:+.3f}   傾き {s:+.3f}")
        print("   相関が0に近ければ『癖』ではなくその日の偶然。ドッグレースなら高く出るはず")

    # ---- ② 枠との噛み合わせが効くか ----
    print("\n■ ② 枠と癖の噛み合わせ（3着内率）")
    print(f"   {'':<16}{'内枠(0-0.33)':>16}{'中枠(0.33-0.66)':>17}{'外枠(0.66-1)':>15}")
    tab = defaultdict(list)
    for q in rows:
        k = kuse.get(q["name"])
        if k is None:
            continue
        ks = "ワイド" if k > 0.08 else ("レイラー" if k < -0.08 else "ミッド")
        gs = "内" if q["gate"] < 1 / 3 else ("中" if q["gate"] < 2 / 3 else "外")
        tab[(ks, gs)].append(q["chaku"] <= 3)
    for ks in ("レイラー", "ミッド", "ワイド"):
        line = f"   {ks:<16}"
        for gs in ("内", "中", "外"):
            w = tab[(ks, gs)]
            line += f"{sum(w)/len(w)*100:>9.1f}% n{len(w):<6}" if len(w) >= 50 else f"{'—':>16}"
        print(line)
    print("   ※ ドッグレースなら『ワイド×内枠』『レイラー×外枠』が落ちるはず")


if __name__ == "__main__":
    main()
