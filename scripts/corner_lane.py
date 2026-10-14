#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""コーナー通過順から各馬の「通し位置（最内〜最外）」と前後の動きを取る。

楽天のコーナー通過順位は、括弧が併走で、括弧の中は内→外の並び。
先頭に書かれた馬が最内。これを使えば、どこを回ったかが読める。

  python3 scripts/corner_lane.py notes/live/2026-10-14/results.json out.json

出すもの（1頭ずつ）
  lanes   各コーナーの (前後の位置, 内から何列目)
  lane    全コーナーをならした列（0が最内）と、そのラベル
  move    最初の角 → 4角 の順位変化（プラスが押し上げ）
  agdiff  自身の上がり − そのレースの上がり3F（マイナスが速い）
"""
from __future__ import annotations
import json, re, sys, time

sys.path.insert(0, "/home/user/keiba/src")
from nankeiba.scraping.client import PoliteClient  # noqa: E402

SRC = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else "corner_lane.json"
c = PoliteClient(use_cache=True)


def get(u, n=4):
    for i in range(n):
        try:
            return c.get(u)
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def flat(t):
    t = re.sub(r"<[^>]+>", "|", t)
    t = re.sub(r"\|+", "|", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\|\s*", "|", t)
    t = re.sub(r"\s*\|", "|", t)
    return re.sub(r"\|+", "|", t)


def parse_lanes(seg):
    """1コーナーぶん → {馬番: (前後の位置1〜, 内から何列目0〜, 併走の幅)}"""
    out, pos = {}, 0
    seg = seg.replace("*", "").replace("=", ",").replace("-", ",")
    for grp, single in re.findall(r"\(([\d, ]+)\)|(\d+)", seg):
        members = ([int(x) for x in grp.split(",") if x.strip()]
                   if grp else [int(single)])
        pos += 1
        for ir, u in enumerate(members):        # ir=0 が最内
            out[u] = (pos, ir, len(members))
    return out


def label(v):
    if v is None:
        return "─"
    if v < 0.25:
        return "最内"
    if v < 0.75:
        return "内"
    if v < 1.25:
        return "中"
    if v < 2.0:
        return "外"
    return "最外"


res = json.load(open(SRC, encoding="utf-8"))
out = {}
for Rs in sorted(res, key=lambda x: int(x)):
    r = res[Rs]
    raw = get("https://keiba.rakuten.co.jp/race_performance/list/RACEID/%s" % r["rid"])
    if not raw:
        continue
    t = flat(raw)
    i = t.find("コーナー通過順位")
    if i < 0:
        continue
    seg = t[i:t.find("払戻金", i)]
    # 4角より多く回る鞍では同じ角が2度出る。最後のひと回りを使う。
    cs = re.findall(r"([１２３４])角\|([^|]+)\|", seg)
    keep = {}
    for lab, s in cs:
        keep[lab] = s
    order = [x for x in ("１", "２", "３", "４") if x in keep]
    ords = [(x, parse_lanes(keep[x])) for x in order]
    if not ords:
        continue
    es = [e for e in r["e"] if str(e.get("f", "")).isdigit()]
    ag3 = r.get("ag3")
    rows = []
    for e in es:
        u = e["u"]
        lanes = {lab: o.get(u) for lab, o in ords}
        seen = [v for v in lanes.values() if v]
        mean_lane = (sum(v[1] for v in seen) / len(seen)) if seen else None
        first = ords[0][1].get(u)
        last = ords[-1][1].get(u)
        rows.append(dict(
            u=u, nm=e["nm"], fin=int(e["f"]),
            pop=int(e["pop"]) if str(e.get("pop", "")).isdigit() else None,
            waku=e.get("waku"), wt=e.get("wt"), dw=e.get("dw"), ag=e.get("ag"),
            lanes={k: (list(v) if v else None) for k, v in lanes.items()},
            lane=mean_lane, lane_label=label(mean_lane),
            first=(first[0] if first else None), last=(last[0] if last else None),
            move=((first[0] - last[0]) if (first and last) else None),
            agdiff=(round(e["ag"] - ag3, 1) if (e.get("ag") and ag3) else None)))
    out[Rs] = dict(dist=r["dist"], n=r["n"], lap=r.get("lap"), ag3=ag3,
                   corners=[k for k, _ in ords], e=rows)
    print("%2sR ダ%4d %2d頭  角 %s" % (Rs, r["dist"], r["n"],
                                    "・".join(k + "角" for k, _ in ords)))
    time.sleep(0.4)
json.dump(out, open(OUT, "w"), ensure_ascii=False)
print("→ %s %d鞍" % (OUT, len(out)))
