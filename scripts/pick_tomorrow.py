#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""検証で残ったものだけを重ねて、翌日の候補を出す。

  python3 scripts/pick_tomorrow.py notes/live/2026-10-15/past5.json 2026-10-15

使うもの（人気薄での上振れ・10日500頭規模で測ったもの）
  ◎ コーナー押上の鞍内上位1/3 × 直線は上げない   66頭 15.2%  +7.8pt
  ○ 先行力の鞍内上位25%                      70頭 14.3%  +5.3pt
  × 近5走で3角→4角を上げた走が0走            168頭  4.2%  -3.0pt
  × 間隔75日以上                            16頭 1着ゼロ
  参考 上り40台 × 渋った馬場 × 小回り の好走2走以上  23頭 52.2% +15.7pt（人気になりやすい）
"""
from __future__ import annotations
import datetime, json, statistics, sys

LAP = {"札幌": 1640, "函館": 1626, "福島": 1600, "新潟": 1623, "東京": 1899, "中山": 1667,
       "中京": 1530, "京都": 1783, "阪神": 1689, "小倉": 1615,
       "浦和": 1200, "船橋": 1400, "大井": 1600, "川崎": 1200,
       "門別": 1600, "盛岡": 1400, "水沢": 1200, "金沢": 1200, "笠松": 1100,
       "名古屋": 1180, "園田": 1051, "姫路": 1200, "高知": 1100, "佐賀": 1100, "帯広": 200}

P5 = json.load(open(sys.argv[1], encoding="utf-8"))
TODAY = datetime.date.fromisoformat(sys.argv[2])


def cgain(x):
    c = (x.get("cor") or "").split("-")
    if len(c) < 2 or not x.get("fs"):
        return None
    try:
        return (int(c[-2]) - int(c[-1])) / float(x["fs"])
    except ValueError:
        return None


def sgain(x):
    if not (x.get("fs") and x.get("fin") and x.get("c4")):
        return None
    return (x["c4"] - x["fin"]) / float(x["fs"])


def lead(x):
    c = (x.get("cor") or "").split("-")
    if not c or not x.get("fs"):
        return None
    try:
        return int(c[0]) / float(x["fs"])
    except ValueError:
        return None


print("■ %s ── 残ったファクターだけで拾う" % TODAY)
for Rs in sorted(P5, key=lambda x: int(x)):
    v = P5[Rs]
    rows = []
    for c in v["e"]:
        runs = c.get("runs") or []
        if not runs:
            continue
        cg = [z for z in (cgain(x) for x in runs) if z is not None]
        sg = [z for z in (sgain(x) for x in runs) if z is not None]
        ld = [z for z in (lead(x) for x in runs) if z is not None]
        d0 = datetime.datetime.strptime("20" + runs[0]["date"], "%Y/%m/%d").date()
        tough = sum(1 for x in runs
                    if x.get("ag") and x["ag"] >= 40.0
                    and x.get("baba") in ("稍", "重", "不")
                    and x["place"] in LAP and LAP[x["place"]] <= 1300
                    and x.get("fs") and x["fin"] / float(x["fs"]) <= 0.40)
        rows.append(dict(u=c["u"], nm=c["nm"], n=len(runs),
                         cg=(statistics.mean(cg) if cg else None),
                         cgn=sum(1 for z in cg if z > 0),
                         st=(statistics.mean(sg) if sg else None),
                         sen=(statistics.median(ld) if ld else None),
                         gap=(TODAY - d0).days, tough=tough))
    for key, tag in (("cg", "cgr"), ("st", "str"), ("sen", "senr")):
        have = [x for x in rows if x[key] is not None]
        have.sort(key=lambda z: (-z[key]) if key != "sen" else z[key])
        for i, x in enumerate(have):
            x[tag] = i / float(len(have)) if len(have) > 1 else 0.5
    print("\n■ %sR ダ%s ── %d頭" % (Rs, v.get("dist") or "?", len(v["e"])))
    for x in sorted(rows, key=lambda z: z["u"]):
        mark = []
        if (x.get("cgr") is not None and x["cgr"] < .34
                and x.get("str") is not None and x["str"] >= .34):
            mark.append("◎角")
        if x.get("senr") is not None and x["senr"] < .25:
            mark.append("○先行")
        if x["tough"] >= 2:
            mark.append("△タフ")
        if x["cgn"] == 0:
            mark.append("×角0")
        if x["gap"] >= 75:
            mark.append("×間隔%d" % x["gap"])
        if not mark:
            continue
        print("   %2d %-16s 近%d走  角で押上%s  直線%s  先行%s  間隔%3d日  %s"
              % (x["u"], x["nm"][:16], x["n"],
                 ("%3.0f%%" % (100 * x["cgr"])) if x.get("cgr") is not None else " ─ ",
                 ("%3.0f%%" % (100 * x["str"])) if x.get("str") is not None else " ─ ",
                 ("%3.0f%%" % (100 * x["senr"])) if x.get("senr") is not None else " ─ ",
                 x["gap"], " ".join(mark)))
