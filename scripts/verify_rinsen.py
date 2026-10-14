#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""臨戦過程（騎手と距離の繰り返しが崩れるか）が効くかを、手元の全日で数える。

  python3 scripts/verify_rinsen.py

notes/live/*/ に rinsen.json と results.json が両方ある日を使う。
生の3着内率は人気でほとんど説明がつくので、人気別3着内率からの上振れで見る。
"""
from __future__ import annotations
import datetime, glob, json, os, statistics

ROWS = []
for p in sorted(glob.glob("/home/user/keiba/notes/live/*/rinsen.json")):
    d = os.path.basename(os.path.dirname(p))
    rp = os.path.join(os.path.dirname(p), "results.json")
    if not os.path.exists(rp):
        continue
    today = datetime.date.fromisoformat(d)
    rin = json.load(open(p, encoding="utf-8"))
    res = json.load(open(rp, encoding="utf-8"))
    for Rs, v in rin.items():
        r = res.get(Rs)
        if not r:
            continue
        fin = {e["u"]: e for e in r["e"] if str(e.get("f", "")).isdigit()}
        dist = v["dist"]
        for row in v["rows"]:
            # 出馬表の件数が近5走の件数と合わない鞍では馬番が付いていない
            if "u" not in row:
                continue
            e = fin.get(row["u"])
            rs = row["runs"]
            if not e or len(rs) < 3:
                continue
            # 近走の先頭から数えた、同じ騎手／同じ距離の連続数
            jkrun = 0
            for x in rs:
                if x["jk"] == rs[0]["jk"]:
                    jkrun += 1
                else:
                    break
            dsrun = 0
            for x in rs:
                if x["dist"] == rs[0]["dist"]:
                    dsrun += 1
                else:
                    break
            chg_j = rs[0]["jk"] != row["jk"]
            chg_d = rs[0]["dist"] != dist
            gap = (today - datetime.date.fromisoformat(rs[0]["date"])).days
            ROWS.append(dict(
                day=d, R=int(Rs), u=row["u"], nm=row["nm"], dist=dist,
                fin=int(e["f"]),
                pop=int(e["pop"]) if str(e.get("pop", "")).isdigit() else None,
                c4=e.get("c4"), jkrun=jkrun, dsrun=dsrun, rep=max(jkrun, dsrun),
                chg_j=chg_j, chg_d=chg_d, gap=gap,
                ddir=(dist - rs[0]["dist"]),
                away=sum(1 for x in rs[:3] if x["place"] != rs[0]["place"]),
                fresh=(max(jkrun, dsrun) >= 3 and (chg_j or chg_d))))

BASE = {}
for p in range(1, 20):
    g = [x for x in ROWS if x["pop"] == p]
    if g:
        BASE[p] = 100.0 * sum(1 for x in g if x["fin"] <= 3) / len(g)

ANA = [x for x in ROWS if x["pop"] and x["pop"] >= 7]
print("■ %d日 %d頭（近5走が3走以上ある馬）／ 7番人気以下 %d頭"
      % (len({x["day"] for x in ROWS}), len(ROWS), len(ANA)))
print("   " + " ".join(sorted({x["day"][5:] for x in ROWS})))


def ud(rows, lab, w=30):
    n = len(rows)
    if not n:
        print("   %-*s   0頭" % (w, lab))
        return
    t = sum(1 for x in rows if x["fin"] <= 3)
    win = sum(1 for x in rows if x["fin"] == 1)
    act = 100.0 * t / n
    hv = [x for x in rows if x["pop"] in BASE]
    exp = sum(BASE[x["pop"]] for x in hv) / len(hv) if hv else 0
    print("   %-*s %4d頭 3着内%3d (%5.1f%%) 1着%2d 期待%5.1f%% 上振れ%+5.1fpt"
          % (w, lab, n, t, act, win, exp, act - exp))


for tag, rows in (("全体", ROWS), ("人気薄（7番人気以下）", ANA)):
    print("\n■ %s ── 繰り返しが崩れるか" % tag)
    ud([x for x in rows if x["fresh"]], "3走以上の繰り返し × 今日替わる")
    ud([x for x in rows if x["rep"] >= 3 and not (x["chg_j"] or x["chg_d"])],
       "3走以上の繰り返し × 今日も同じ")
    ud([x for x in rows if x["rep"] < 3], "そもそも繰り返していない")

print("\n■ 人気薄 ── 何が替わると効くか")
ud([x for x in ANA if x["chg_j"] and x["chg_d"]], "騎手も距離も替わる")
ud([x for x in ANA if x["chg_j"] and not x["chg_d"]], "騎手だけ替わる")
ud([x for x in ANA if x["chg_d"] and not x["chg_j"]], "距離だけ替わる")
ud([x for x in ANA if not x["chg_j"] and not x["chg_d"]], "どちらも同じ")

print("\n■ 人気薄 ── 繰り返しの長さ（替わる馬だけ）")
ch = [x for x in ANA if x["chg_j"] or x["chg_d"]]
for lo, hi, lab in ((0, 1, "繰り返し1走"), (2, 2, "2走"), (3, 3, "3走"), (4, 9, "4走以上")):
    ud([x for x in ch if lo <= x["rep"] <= hi], lab)

print("\n■ 人気薄 ── 距離を詰めるか延ばすか（距離替わりだけ）")
for lo, hi, lab in ((-9999, -101, "200m以上 詰める"), (-100, -1, "100m 詰める"),
                    (1, 100, "100m 延ばす"), (101, 9999, "200m以上 延ばす")):
    ud([x for x in ANA if x["chg_d"] and lo <= x["ddir"] <= hi], lab)

print("\n■ 人気薄 ── 間隔（繰り返しが崩れる馬だけ）")
fr = [x for x in ANA if x["fresh"]]
for lo, hi, lab in ((0, 20, "中2週以内（〜20日）"), (21, 40, "21〜40日"),
                    (41, 99, "41〜99日"), (100, 9999, "100日以上")):
    ud([x for x in fr if lo <= x["gap"] <= hi], lab)

print("\n■ 人気薄 ── 繰り返しが崩れる × 直近3走に他場を挟む")
ud([x for x in fr if x["away"] >= 1], "他場あり")
ud([x for x in fr if x["away"] == 0], "他場なし")

print("\n■ 人気薄で3着内に来た馬のうち、繰り返しが崩れていた馬")
for x in sorted([y for y in ANA if y["fin"] <= 3 and y["fresh"]],
                key=lambda z: (z["day"], z["R"])):
    print("   %s %2dR %2d %-16s %2d人気 %d着  繰り返し%d走 %s%s 間隔%3d日 距離%+d"
          % (x["day"][5:], x["R"], x["u"], x["nm"][:16], x["pop"], x["fin"], x["rep"],
             "騎手替" if x["chg_j"] else "", "距離替" if x["chg_d"] else "",
             x["gap"], x["ddir"]))
