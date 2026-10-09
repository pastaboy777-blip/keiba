#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""開催をまとめて見る。日ごとの results.json を何日ぶんでも渡す。

  python3 scripts/meet_bias.py "9/7〜9/11 川崎" \
      notes/live/2026-09-07/results.json notes/live/2026-09-08/results.json ...

生の3着内率は乗っている馬の人気でほとんど説明がついてしまうので、
買い側のファクターは人気別3着内率からの上振れでも出す。
"""
from __future__ import annotations
import json, os, statistics, sys

MARKS = "▲☆◇△▽★"

TITLE = sys.argv[1]
FILES = sys.argv[2:]

ALL = []
NR = 0
for path in FILES:
    day = os.path.basename(os.path.dirname(path))
    res = json.load(open(path, encoding="utf-8"))
    for Rs, r in res.items():
        es = [e for e in r["e"] if str(e.get("f", "")).isdigit()]
        if not es:
            continue
        NR += 1
        ags = sorted(e["ag"] for e in es if e.get("ag"))
        wts = sorted(e["wt"] for e in es if e.get("wt"))
        cut = wts[max(0, len(wts) // 3 - 1)] if wts else 0
        for e in es:
            pop = int(e["pop"]) if str(e.get("pop", "")).isdigit() else None
            dw = str(e.get("dw", ""))
            ALL.append(dict(
                day=day, R=int(Rs), dist=r["dist"], course=r.get("course", ""),
                baba=r.get("baba", ""), cls=r.get("cls", ""), n=r["n"],
                fin=int(e["f"]), u=e["u"], waku=e.get("waku"), nm=e["nm"], pop=pop,
                c4=e.get("c4"), ag=e.get("ag"), wt=e.get("wt"),
                dw=(int(dw) if dw.lstrip("+-").isdigit() else None),
                age=e.get("age"), jk=e.get("jk", ""),
                gen=bool(e.get("jk") and e["jk"][0] in MARKS),
                sml=bool(e.get("wt") and e["wt"] <= cut),
                agr=(ags.index(e["ag"]) + 1) if e.get("ag") in ags else None,
                wq=(wts.index(e["wt"]) / float(len(wts))) if e.get("wt") in wts else None,
                uq=((e["u"] - 1) / float(r["n"])) if r["n"] else None))

print("■ %s ── %d鞍 / %d頭" % (TITLE, NR, len(ALL)))

BASE = {}
for p in range(1, 20):
    g = [x for x in ALL if x["pop"] == p]
    if g:
        BASE[p] = 100.0 * sum(1 for x in g if x["fin"] <= 3) / len(g)


def rate(rows, lab, w=26):
    n = len(rows)
    if not n:
        print("   %-*s   0頭" % (w, lab))
        return
    t3 = sum(1 for x in rows if x["fin"] <= 3)
    win = sum(1 for x in rows if x["fin"] == 1)
    print("   %-*s %3d頭  3着内 %3d (%5.1f%%)  1着 %2d"
          % (w, lab, n, t3, 100.0 * t3 / n, win))


def updown(rows, lab, w=26):
    n = len(rows)
    if not n:
        print("   %-*s   0頭" % (w, lab))
        return
    act = 100.0 * sum(1 for x in rows if x["fin"] <= 3) / n
    hv = [x for x in rows if x["pop"] in BASE]
    exp = sum(BASE[x["pop"]] for x in hv) / len(hv) if hv else 0
    pops = [x["pop"] for x in rows if x["pop"]]
    print("   %-*s %3d頭  3着内 %5.1f%%  期待 %5.1f%%  上振れ %+5.1fpt  人気中央 %2d"
          % (w, lab, n, act, exp, act - exp,
             int(statistics.median(pops)) if pops else 0))


print("\n■ 日ごと")
for d in sorted({x["day"] for x in ALL}):
    g = [x for x in ALL if x["day"] == d]
    bb = sorted({x["baba"] for x in g})
    print("   %-11s %2d鞍 %3d頭  馬場 %-6s  7番人気以下の3着内 %2d/%d (%.1f%%)"
          % (d[5:], len({x["R"] for x in g}), len(g), "/".join(bb),
             sum(1 for x in g if x["pop"] and x["pop"] >= 7 and x["fin"] <= 3),
             sum(1 for x in g if x["pop"] and x["pop"] >= 7),
             100.0 * sum(1 for x in g if x["pop"] and x["pop"] >= 7 and x["fin"] <= 3)
             / max(1, sum(1 for x in g if x["pop"] and x["pop"] >= 7))))

print("\n■ 人気")
for lo, hi, lab in ((1, 1, "1番人気"), (2, 3, "2〜3番人気"), (4, 6, "4〜6番人気"),
                    (7, 9, "7〜9番人気"), (10, 99, "10番人気以下")):
    rate([x for x in ALL if x["pop"] and lo <= x["pop"] <= hi], lab)

print("\n■ 4角の位置")
for lo, hi, lab in ((1, 1, "1番手"), (2, 2, "2番手"), (3, 4, "3〜4番手"),
                    (5, 6, "5〜6番手"), (7, 8, "7〜8番手"), (9, 99, "9番手〜")):
    rate([x for x in ALL if x["c4"] and lo <= x["c4"] <= hi], "4角 " + lab)

print("\n■ 上り順位（鞍内）")
for lo, hi, lab in ((1, 1, "1位"), (2, 3, "2〜3位"), (4, 5, "4〜5位"),
                    (6, 8, "6〜8位"), (9, 99, "9位以下")):
    rate([x for x in ALL if x["agr"] and lo <= x["agr"] <= hi], "上り " + lab)

print("\n■ 上り × 4角")
for al, ah, alab in ((1, 3, "上り3位以内"), (4, 99, "上り4位以下")):
    for cl, ch, clab in ((1, 2, "4角1〜2"), (3, 4, "4角3〜4"), (5, 99, "4角5〜")):
        rate([x for x in ALL if x["agr"] and x["c4"] and al <= x["agr"] <= ah
              and cl <= x["c4"] <= ch], "%s × %s" % (alab, clab), 28)

print("\n■ 距離別の4角")
for dl, dh, dlab in ((900, 900, "900m"), (1400, 1500, "1400〜1500m"),
                     (1600, 1600, "1600m"), (1700, 2200, "2000m以上")):
    rows = [x for x in ALL if dl <= x["dist"] <= dh]
    if not rows:
        continue
    print("   %s（%d鞍 %d頭）" % (dlab, len({(x["day"], x["R"]) for x in rows}), len(rows)))
    for lo, hi, lab in ((1, 2, "  4角1〜2番手"), (3, 4, "  4角3〜4番手"),
                        (5, 99, "  4角5番手〜")):
        rate([x for x in rows if x["c4"] and lo <= x["c4"] <= hi], lab)

print("\n■ 枠順")
for lo, hi, lab in ((1, 2, "1〜2枠"), (3, 4, "3〜4枠"), (5, 6, "5〜6枠"), (7, 8, "7〜8枠")):
    rate([x for x in ALL if x["waku"] and lo <= x["waku"] <= hi], lab)
print("   ── 馬番を頭数で割った相対位置")
for lo, hi, lab in ((0, .34, "内寄り1/3"), (.34, .67, "中"), (.67, 1.01, "外寄り1/3")):
    rate([x for x in ALL if x["uq"] is not None and lo <= x["uq"] < hi], lab)
print("   ── 900m だけ（スタートが2角の引き込み線）")
for lo, hi, lab in ((0, .34, "内寄り1/3"), (.34, .67, "中"), (.67, 1.01, "外寄り1/3")):
    rate([x for x in ALL if x["dist"] == 900 and x["uq"] is not None
          and lo <= x["uq"] < hi], lab)

print("\n■ 馬体重（鞍内の軽い順）")
for lo, hi, lab in ((0, .34, "軽い1/3"), (.34, .67, "中"), (.67, 1.01, "重い1/3")):
    rate([x for x in ALL if x["wq"] is not None and lo <= x["wq"] < hi], lab)

print("\n■ 馬体重の増減")
for lo, hi, lab in ((-999, -8, "−8kg以上減"), (-7, -4, "−4〜−7kg"), (-3, -1, "−1〜−3kg"),
                    (0, 0, "増減なし"), (1, 3, "+1〜+3kg"), (4, 7, "+4〜+7kg"),
                    (8, 999, "+8kg以上増")):
    rate([x for x in ALL if x["dw"] is not None and lo <= x["dw"] <= hi], lab)
print("   ──")
rate([x for x in ALL if x["dw"] is not None and x["dw"] < 0], "減った馬")
rate([x for x in ALL if x["dw"] == 0], "変わらず")
rate([x for x in ALL if x["dw"] is not None and x["dw"] > 0], "増えた馬")

print("\n■ 減量騎手（%s）── 人気で揃えて見る" % MARKS[:4])
updown([x for x in ALL if x["gen"]], "減量騎手ぜんぶ")
updown([x for x in ALL if not x["gen"]], "減量なし")
for sml, lab in ((True, "小型"), (False, "小型でない")):
    for g2, lab2 in ((True, "減量騎手"), (False, "減量なし")):
        updown([x for x in ALL if x["sml"] == sml and x["gen"] == g2],
               "%s × %s" % (lab, lab2))

print("\n■ 人気薄（7番人気以下 %d頭）で何が効いたか"
      % sum(1 for x in ALL if x["pop"] and x["pop"] >= 7))
ana = [x for x in ALL if x["pop"] and x["pop"] >= 7]
for lo, hi, lab in ((1, 2, "4角1〜2番手"), (3, 4, "4角3〜4番手"), (5, 99, "4角5番手〜")):
    rate([x for x in ana if x["c4"] and lo <= x["c4"] <= hi], lab)
for lo, hi, lab in ((1, 3, "上り3位以内"), (4, 99, "上り4位以下")):
    rate([x for x in ana if x["agr"] and lo <= x["agr"] <= hi], lab)
rate([x for x in ana if x["gen"]], "減量騎手")
rate([x for x in ana if x["dw"] is not None and x["dw"] < 0], "馬体重が減った")
rate([x for x in ana if x["uq"] is not None and x["uq"] < .34], "内寄り1/3")

print("\n■ 人気薄で3着内に来た馬をぜんぶ")
print("   %-7s %3s %-10s %-16s %3s %5s %4s %9s %s"
      % ("日", "R", "距離", "馬", "人気", "上り", "4角", "馬体重", "騎手"))
for x in sorted([y for y in ana if y["fin"] <= 3],
                key=lambda z: (z["day"], z["R"], z["fin"])):
    print("   %-7s %2dR ダ%4d%-2s %-16s %3d %5.1f(%2s) %3s %4dk(%+d) %s  →%d着"
          % (x["day"][5:], x["R"], x["dist"], x["course"], x["nm"][:16], x["pop"],
             x["ag"] or 0, x["agr"] or "─", x["c4"] or "─", x["wt"] or 0, x["dw"] or 0,
             x["jk"], x["fin"]))
