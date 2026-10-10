#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中央の当日結果から傾向を出す。

  python3 scripts/jra_bias.py notes/live/2026-10-10/jra_results.json "10/10(土)"

障害は上りの意味が違うので外す。
生の率は人気でほとんど説明がつくので、買い側は人気別3着内率からの上振れも出す。
"""
from __future__ import annotations
import json, statistics, sys

F, TITLE = sys.argv[1], sys.argv[2]
res = json.load(open(F, encoding="utf-8"))

ALL = []
for key, r in res.items():
    if r["surf"] == "障":
        continue
    es = [e for e in r["e"] if str(e.get("f", "")).isdigit()]
    if not es:
        continue
    ags = sorted(e["ag"] for e in es if e.get("ag"))
    wts = sorted(e["wt"] for e in es if e.get("wt"))
    # netkeiba は初出走の馬の増減を「(0)」と書く。新馬戦は増減を持たない扱いにする。
    debut = "新馬" in r["name"]
    for e in es:
        dw = "" if debut else str(e.get("dw", ""))
        ALL.append(dict(
            key=key, place=r["place"], R=r["r"], surf=r["surf"], dist=r["dist"],
            turn=r["turn"], baba=r["baba"], pace=r["pace"], name=r["name"], n=r["n"],
            lap=r["lap"], fin=int(e["f"]), u=e["u"], waku=e.get("waku"), nm=e["nm"],
            pop=e.get("pop"), odds=e.get("odds"), c4=e.get("c4"), ag=e.get("ag"),
            wt=e.get("wt"), jk=e.get("jk", ""), age=e.get("age"),
            dw=(int(dw) if dw.lstrip("+-").isdigit() else None),
            agr=(ags.index(e["ag"]) + 1) if e.get("ag") in ags else None,
            wq=(wts.index(e["wt"]) / float(len(wts))) if e.get("wt") in wts else None,
            uq=((e["u"] - 1) / float(r["n"])) if r["n"] else None))

NR = len({x["key"] for x in ALL})
print("■ %s 中央 ── %d鞍 / %d頭（障害は除く）" % (TITLE, NR, len(ALL)))

BASE = {}
for p in range(1, 20):
    g = [x for x in ALL if x["pop"] == p]
    if g:
        BASE[p] = 100.0 * sum(1 for x in g if x["fin"] <= 3) / len(g)


def rate(rows, lab, w=24):
    n = len(rows)
    if not n:
        print("   %-*s   0頭" % (w, lab))
        return
    t3 = sum(1 for x in rows if x["fin"] <= 3)
    win = sum(1 for x in rows if x["fin"] == 1)
    print("   %-*s %3d頭  3着内 %3d (%5.1f%%)  1着 %2d"
          % (w, lab, n, t3, 100.0 * t3 / n, win))


def updown(rows, lab, w=24):
    n = len(rows)
    if not n:
        print("   %-*s   0頭" % (w, lab))
        return
    act = 100.0 * sum(1 for x in rows if x["fin"] <= 3) / n
    hv = [x for x in rows if x["pop"] in BASE]
    exp = sum(BASE[x["pop"]] for x in hv) / len(hv) if hv else 0
    print("   %-*s %3d頭  3着内 %5.1f%%  期待 %5.1f%%  上振れ %+5.1fpt"
          % (w, lab, n, act, exp, act - exp))


print("\n■ 1鞍ずつ")
print("   %-9s %-7s %3s %-6s %-14s %-4s %5s %4s %s"
      % ("場・R", "条件", "頭", "馬場", "レース名", "ペース", "勝1人気", "勝4角", "勝上り"))
for k in sorted(res, key=lambda z: (res[z]["place"], res[z]["r"])):
    r = res[k]
    es = [e for e in r["e"] if str(e.get("f", "")).isdigit()]
    if not es:
        continue
    w = es[0]
    print("   %-3s%2dR  %s%-4d %3d %-6s %-14s %-4s %5s %4s %5s"
          % (r["place"], r["r"], r["surf"], r["dist"], r["n"], r["baba"],
             r["name"][:14], r["pace"], w.get("pop"), w.get("c4"), w.get("ag")))

print("\n■ 人気")
for lo, hi, lab in ((1, 1, "1番人気"), (2, 3, "2〜3番人気"), (4, 6, "4〜6番人気"),
                    (7, 9, "7〜9番人気"), (10, 99, "10番人気以下")):
    rate([x for x in ALL if x["pop"] and lo <= x["pop"] <= hi], lab)

print("\n■ 4角の位置")
for lo, hi, lab in ((1, 2, "1〜2番手"), (3, 4, "3〜4番手"), (5, 6, "5〜6番手"),
                    (7, 9, "7〜9番手"), (10, 99, "10番手〜")):
    rate([x for x in ALL if x["c4"] and lo <= x["c4"] <= hi], "4角 " + lab)

print("\n■ 上り順位（鞍内）")
for lo, hi, lab in ((1, 1, "1位"), (2, 3, "2〜3位"), (4, 5, "4〜5位"),
                    (6, 8, "6〜8位"), (9, 99, "9位以下")):
    rate([x for x in ALL if x["agr"] and lo <= x["agr"] <= hi], "上り " + lab)

print("\n■ 上り × 4角")
for al, ah, alab in ((1, 3, "上り3位以内"), (4, 99, "上り4位以下")):
    for cl, ch, clab in ((1, 4, "4角4番手以内"), (5, 9, "4角5〜9番手"), (10, 99, "4角10番手〜")):
        rate([x for x in ALL if x["agr"] and x["c4"] and al <= x["agr"] <= ah
              and cl <= x["c4"] <= ch], "%s × %s" % (alab, clab), 30)

print("\n■ 場 × 芝ダ")
for pl in sorted({x["place"] for x in ALL}):
    for sf in ("芝", "ダ"):
        rows = [x for x in ALL if x["place"] == pl and x["surf"] == sf]
        if not rows:
            continue
        print("   %s %s（%d鞍 %d頭）"
              % (pl, sf, len({x["key"] for x in rows}), len(rows)))
        for lo, hi, lab in ((1, 4, "  4角4番手以内"), (5, 99, "  4角5番手〜")):
            rate([x for x in rows if x["c4"] and lo <= x["c4"] <= hi], lab)
        for lo, hi, lab in ((1, 3, "  上り3位以内"), (4, 99, "  上り4位以下")):
            rate([x for x in rows if x["agr"] and lo <= x["agr"] <= hi], lab)

print("\n■ ペース別（netkeiba の H / M / S）")
for p in ("H", "M", "S"):
    rows = [x for x in ALL if x["pace"] == p]
    if not rows:
        continue
    print("   ペース%s（%d鞍）" % (p, len({x["key"] for x in rows})))
    for lo, hi, lab in ((1, 4, "  4角4番手以内"), (5, 99, "  4角5番手〜")):
        rate([x for x in rows if x["c4"] and lo <= x["c4"] <= hi], lab)

print("\n■ 枠順")
for sf in ("芝", "ダ"):
    rows = [x for x in ALL if x["surf"] == sf]
    print("   %s（%d鞍 %d頭）" % (sf, len({x["key"] for x in rows}), len(rows)))
    for lo, hi, lab in ((1, 2, "  1〜2枠"), (3, 4, "  3〜4枠"),
                        (5, 6, "  5〜6枠"), (7, 8, "  7〜8枠")):
        rate([x for x in rows if x["waku"] and lo <= x["waku"] <= hi], lab)

print("\n■ 距離帯")
for dl, dh, lab in ((1000, 1400, "〜1400m"), (1500, 1800, "1500〜1800m"),
                    (1900, 3600, "1900m以上")):
    for sf in ("芝", "ダ"):
        rows = [x for x in ALL if sf == x["surf"] and dl <= x["dist"] <= dh]
        if not rows:
            continue
        print("   %s %s（%d鞍）" % (sf, lab, len({x["key"] for x in rows})))
        for lo, hi, l2 in ((1, 4, "  4角4番手以内"), (5, 99, "  4角5番手〜")):
            rate([x for x in rows if x["c4"] and lo <= x["c4"] <= hi], l2)

print("\n■ 馬体重の増減")
for lo, hi, lab in ((-999, -8, "−8kg以上減"), (-7, -4, "−4〜−7kg"), (-3, -1, "−1〜−3kg"),
                    (0, 0, "増減なし"), (1, 3, "+1〜+3kg"), (4, 7, "+4〜+7kg"),
                    (8, 999, "+8kg以上増")):
    rate([x for x in ALL if x["dw"] is not None and lo <= x["dw"] <= hi], lab)

print("\n■ 馬体重（鞍内の軽い順）")
for lo, hi, lab in ((0, .34, "軽い1/3"), (.34, .67, "中"), (.67, 1.01, "重い1/3")):
    rate([x for x in ALL if x["wq"] is not None and lo <= x["wq"] < hi], lab)

ana = [x for x in ALL if x["pop"] and x["pop"] >= 7]
print("\n■ 人気薄（7番人気以下 %d頭）で何が効いたか" % len(ana))
for lo, hi, lab in ((1, 4, "4角4番手以内"), (5, 9, "4角5〜9番手"), (10, 99, "4角10番手〜")):
    rate([x for x in ana if x["c4"] and lo <= x["c4"] <= hi], lab)
for lo, hi, lab in ((1, 3, "上り3位以内"), (4, 99, "上り4位以下")):
    rate([x for x in ana if x["agr"] and lo <= x["agr"] <= hi], lab)
updown([x for x in ana if x["uq"] is not None and x["uq"] < .34], "内寄り1/3")
updown([x for x in ana if x["uq"] is not None and x["uq"] >= .67], "外寄り1/3")

print("\n■ 人気薄で3着内に来た馬")
print("   %-9s %-8s %-15s %3s %7s %5s %4s %s"
      % ("場・R", "条件", "馬", "人気", "単勝", "上り", "4角", "馬体重"))
for x in sorted([y for y in ana if y["fin"] <= 3],
                key=lambda z: (z["place"], z["R"], z["fin"])):
    print("   %-3s%2dR  %s%-5d %-15s %3d %6.1f倍 %5.1f(%2s) %3s %4dk(%+d)  →%d着"
          % (x["place"], x["R"], x["surf"], x["dist"], x["nm"][:15], x["pop"],
             x["odds"] or 0, x["ag"] or 0, x["agr"] or "─", x["c4"] or "─",
             x["wt"] or 0, x["dw"] or 0, x["fin"]))

print("\n■ 1〜3着ぜんぶ")
for k in sorted(res, key=lambda z: (res[z]["place"], res[z]["r"])):
    r = res[k]
    if r["surf"] == "障":
        continue
    rows = [x for x in ALL if x["key"] == k and x["fin"] <= 3]
    if not rows:
        continue
    print("   %-3s%2dR %s%-4d %-16s ペース%-2s %s"
          % (r["place"], r["r"], r["surf"], r["dist"], r["name"][:16], r["pace"], r["lap"]))
    for x in sorted(rows, key=lambda z: z["fin"]):
        print("     %d着 %2d %-15s %2d人気 %6.1f倍 上%.1f(%2s位) 4角%-3s %sk(%+d)"
              % (x["fin"], x["u"], x["nm"][:15], x["pop"], x["odds"] or 0,
                 x["ag"] or 0, x["agr"] or "─", x["c4"] or "─", x["wt"], x["dw"] or 0))
