#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""【前に向かって貯める】その日、馬券になった馬を1頭1行で書き出す。

★CLAUDE.md の最優先ルール（過去開催のバックテストはしない）を壊さない形にしてある。
    やらないこと … 過去に遡って回収率や的中率を測りに行く
    やること     … **その日終わった鞍だけ**を1行ずつ書き出して置いておく
  遡らない。前に向かって貯めるだけ。何日ぶんかを集計するかどうかはユーザーが決める。

出す列は、**新聞の一面に載っていないもの**を優先する:
    ・間隔（週）と帯       … 7週/16週の境目（中島理論の時定数）を見るため
    ・4角の位置 rel        … (4角順位-1)/(頭数-1)。0=先頭 1=最後方
    ・馬体重のレース平均差   … 絶対値では意味が変わる（CLAUDE.mdルール4）
    ・前走地との経度差      … 中島理論の磁場。2度以内が「同じ磁場」
    ・性齢・斤量

使い方:
    python3 scripts/ana/tameru.py --date 2026-09-20 --pre 2026040506:中山 2026040106:阪神
    python3 scripts/ana/tameru.py --date 2026-09-20 --pre 2026040506:中山 --out notes/live/x.tsv
"""
from __future__ import annotations

import argparse
import csv
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kb

LON = {"札幌": 141.35, "函館": 140.77, "福島": 140.44, "新潟": 139.05, "東京": 139.48,
       "中山": 140.02, "中京": 137.01, "京都": 135.77, "阪神": 135.36, "小倉": 130.86,
       "美浦": 140.30, "栗東": 136.00, "門別": 142.07, "盛岡": 141.13, "水沢": 141.14,
       "金沢": 136.63, "笠松": 136.77, "名古屋": 136.92, "園田": 135.36, "姫路": 134.68,
       "高知": 133.57, "佐賀": 130.30, "大井": 139.76, "船橋": 140.00, "川崎": 139.68,
       "浦和": 139.66, "帯広": 143.20}


def lon_of(p):
    if not p:
        return None, None
    for k, v in LON.items():
        if k in p:
            return k, v
    return None, None


def band(w):
    if w is None:
        return "?"
    return ("0-4週" if w < 4.5 else "4.5-7週" if w < 7 else
            "7-9週" if w < 9 else "9-16週" if w < 16 else "16週超")


def collect(pre, place, base, top=3):
    hl = LON.get(place)
    rows = []
    for r in range(1, 13):
        rid = f"{pre}{r:02d}"
        try:
            m, res = kb.seiseki(rid)
            _, run = kb.syutuba(rid)
        except Exception:
            continue
        done = [x for x in res if isinstance(x["chaku"], int)]
        if not done:
            continue
        n = len(done)
        ws = [int(x["w"]) for x in done if (x["w"] or "").isdigit()]
        avg = st.mean(ws) if ws else None
        code = {x["ub"]: x["umacd"] for x in run}
        for x in sorted(done, key=lambda z: z["chaku"])[:top]:
            ub = int(x["ub"])
            h = ([q for q in kb.uma(code[ub]) if kb.to_date(q["date"]) < base]
                 if code.get(ub) else [])
            wk = ((base - kb.to_date(h[-1]["date"])).days / 7) if h else None
            pl, pln = lon_of(h[-1]["place"]) if h else (None, None)
            # ★通過順には丸数字（①②…）が混ざる。必ず数字に直す（kb.kyakushitsu と同じ罠）
            pas = [kb._CIR.get(c, c) for c in (x.get("pas") or "").split()]
            c4 = int(pas[-1]) if pas and pas[-1].isdigit() else None
            rel = (c4 - 1) / (n - 1) if c4 and n > 1 else None
            dw = (int(x["w"]) - avg) if avg and (x["w"] or "").isdigit() else None
            rows.append({
                "場": place, "R": r, "馬場": m.get("baba") or "?",
                "コース": f"{m['surface']}{m['dist']}", "頭数": n,
                "着": x["chaku"], "番": ub, "馬名": x["name"],
                "人気": x["nin"], "オッズ": x["odds"], "性齢": x["sex"], "斤量": x["kin"],
                "体重": x["w"], "平均差": (round(dw, 1) if dw is not None else None),
                "週": (round(wk, 1) if wk else None), "帯": band(wk),
                "4角": c4, "rel": (round(rel, 2) if rel is not None else None),
                "前走地": pl, "経度差": (round(abs(pln - hl), 2) if pln and hl else None),
            })
    return rows


def show(rows):
    cols = ("場", "R", "着", "馬名", "人気", "オッズ", "性齢", "斤量",
            "体重", "平均差", "週", "帯", "4角", "rel", "前走地", "経度差")
    wid = {"場": 4, "R": 3, "着": 3, "馬名": 17, "人気": 4, "オッズ": 7, "性齢": 5,
           "斤量": 4, "体重": 5, "平均差": 6, "週": 6, "帯": 8, "4角": 4, "rel": 6,
           "前走地": 6, "経度差": 6}
    print("".join(f"{c:<{wid[c]}}" for c in cols))
    print("-" * sum(wid.values()))
    for z in rows:
        cells = []
        for c in cols:
            v = z[c]
            if v is None:
                s = "-"
            elif c == "平均差":
                s = f"{v:+.0f}"
            elif c == "オッズ":
                s = f"{v:.1f}"
            else:
                s = str(v)
            cells.append(f"{s:<{wid[c]}}")
        print("".join(cells))


def summary(rows):
    print("\n=== 帯ごと（3着内の内訳）===")
    for b in ("0-4週", "4.5-7週", "7-9週", "9-16週", "16週超", "?"):
        v = [z for z in rows if z["帯"] == b]
        if not v:
            continue
        w1 = [z for z in v if z["着"] == 1]
        print(f"  {b:<9} 3着内 {len(v):>3}頭   うち1着 {len(w1):>2}頭")
    rel = [z["rel"] for z in rows if z["rel"] is not None]
    if rel:
        print(f"\n=== 4角の位置 ===")
        print(f"  3着内の平均 rel {st.mean(rel):.2f}（0=先頭 1=最後方）")
        for lo, hi, nm in ((0, .25, "逃先"), (.25, .45, "好位"), (.45, .70, "中団"), (.70, 1.01, "後方")):
            c = [v for v in rel if lo <= v < hi]
            print(f"    {nm} {len(c):>3}頭 ({len(c)/len(rel):.0%})")
    dw = [z["平均差"] for z in rows if z["平均差"] is not None]
    if dw:
        print(f"\n=== 馬体重（レース平均との差）===")
        print(f"  3着内の平均 {st.mean(dw):+.1f}kg（偶然なら0）  n={len(dw)}")
    lg = [z["経度差"] for z in rows if z["経度差"] is not None]
    if lg:
        same = [v for v in lg if v <= 2]
        print(f"\n=== 前走地との経度差（中島の2度）===")
        print(f"  同磁場 {len(same)}/{len(lg)}頭 ({len(same)/len(lg):.0%})")
    mares = [z for z in rows if (z["性齢"] or "").startswith("牝")]
    print(f"\n=== 性別 ===")
    print(f"  3着内のうち牝馬 {len(mares)}/{len(rows)}頭 ({len(mares)/len(rows):.0%})")


def main():
    ap = argparse.ArgumentParser(description="その日 馬券になった馬を1行ずつ貯める")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--pre", nargs="+", required=True, help="開催コード:場名 （例 2026040506:中山）")
    ap.add_argument("--top", type=int, default=3, help="何着までを書き出すか")
    ap.add_argument("--out", help="TSVの書き出し先")
    a = ap.parse_args()

    base = kb.to_date(a.date.replace("-", "/"))
    rows = []
    for spec in a.pre:
        pre, _, place = spec.partition(":")
        rows += collect(pre, place, base, a.top)
    if not rows:
        print("× 結果が取れません")
        return
    print(f"■ {a.date}  {a.top}着以内 {len(rows)}頭\n")
    show(rows)
    summary(rows)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        with open(a.out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t")
            w.writeheader()
            w.writerows(rows)
        print(f"\n→ {a.out} に書き出しました（**遡らない。前に向かって貯めるだけ**）")


if __name__ == "__main__":
    main()
