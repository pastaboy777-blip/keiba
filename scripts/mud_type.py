#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""砂を掻き込むタイプかどうかを、近5走の馬場別の着順から測る。

  bias ＝ （重・不良での相対着順の平均） − （良・稍での相対着順の平均）
          相対着順 ＝ 着順 ÷ 頭数。マイナスほど、時計のかかる馬場で走る馬。

  python3 scripts/mud_type.py              # 結果のある日を全部で検証
  python3 scripts/mud_type.py 2026-10-14 9 # その鞍の1頭ずつ

掻き込む馬が来るのは「時計のかかった日」のはずなので、
その日のレース上がりが場の平均より遅かったかどうかでも割る。
"""
from __future__ import annotations
import glob, json, os, statistics, sys

HEAVY = ("重", "不")
GOOD = ("良", "稍")


def bias(runs):
    hv = [x for x in runs if x.get("baba") in HEAVY and x.get("fs")]
    gd = [x for x in runs if x.get("baba") in GOOD and x.get("fs")]
    if not hv or not gd:
        return None, len(hv), len(gd)
    h = statistics.mean(x["fin"] / float(x["fs"]) for x in hv)
    g = statistics.mean(x["fin"] / float(x["fs"]) for x in gd)
    return h - g, len(hv), len(gd)


DAYS = sorted(os.path.basename(os.path.dirname(p))
              for p in glob.glob("/home/user/keiba/notes/live/*/past5.json")
              if os.path.exists(os.path.join(os.path.dirname(p), "results.json")))

# 場ごとの「距離別レース上がり」の中央値を作り、その日が速かったか遅かったかを出す
norm = {}
for d in DAYS:
    res = json.load(open("/home/user/keiba/notes/live/%s/results.json" % d, encoding="utf-8"))
    for r in res.values():
        if r.get("ag3"):
            norm.setdefault(r["dist"], []).append(r["ag3"])
NORM = {k: statistics.median(v) for k, v in norm.items() if len(v) >= 3}

ROWS = []
for d in DAYS:
    p5 = json.load(open("/home/user/keiba/notes/live/%s/past5.json" % d, encoding="utf-8"))
    res = json.load(open("/home/user/keiba/notes/live/%s/results.json" % d, encoding="utf-8"))
    for Rs, v in p5.items():
        r = res.get(Rs)
        if not r:
            continue
        slow = (r["ag3"] - NORM[r["dist"]]) if (r.get("ag3") and r["dist"] in NORM) else None
        fin = {e["u"]: e for e in r["e"] if str(e.get("f", "")).isdigit()}
        rows = []
        for c in v["e"]:
            e = fin.get(c["u"])
            if not e:
                continue
            b, nh, ng = bias(c.get("runs") or [])
            rows.append(dict(day=d, R=int(Rs), u=c["u"], nm=c["nm"], fin=int(e["f"]),
                             pop=int(e["pop"]) if str(e.get("pop", "")).isdigit() else None,
                             baba=r.get("baba"), slow=slow, bias=b, nh=nh, ng=ng,
                             wt=e.get("wt"), c4=e.get("c4")))
        have = [x for x in rows if x["bias"] is not None]
        have.sort(key=lambda z: z["bias"])
        for i, x in enumerate(have):
            x["br"] = i / float(len(have)) if len(have) > 1 else 0.5
        ROWS += rows

if len(sys.argv) > 2:
    d, Rn = sys.argv[1], int(sys.argv[2])
    g = [x for x in ROWS if x["day"] == d and x["R"] == Rn]
    print("■ %s %dR ── 掻き込み度（マイナスほど時計のかかる馬場向き）" % (d, Rn))
    print("   %3s %-16s %3s %7s %4s %5s %s" % ("馬番", "馬", "人気", "bias", "重走", "良走", "着"))
    for x in sorted(g, key=lambda z: (z["bias"] is None, z["bias"])):
        print("   %3d %-16s %3s %7s %3d走 %3d走 %2d着"
              % (x["u"], x["nm"][:16], x["pop"],
                 ("%+.2f" % x["bias"]) if x["bias"] is not None else "─",
                 x["nh"], x["ng"], x["fin"]))
    sys.exit()

BASE = {}
for p in range(1, 20):
    g = [x for x in ROWS if x["pop"] == p]
    if g:
        BASE[p] = 100.0 * sum(1 for x in g if x["fin"] <= 3) / len(g)


def ud(rows, lab, w=30):
    n = len(rows)
    if not n:
        print("   %-*s   0頭" % (w, lab))
        return
    t = sum(1 for x in rows if x["fin"] <= 3)
    act = 100.0 * t / n
    hv = [x for x in rows if x["pop"] in BASE]
    exp = sum(BASE[x["pop"]] for x in hv) / len(hv) if hv else 0
    print("   %-*s %4d頭 3着内%3d (%5.1f%%) 1着%2d 期待%5.1f%% 上振れ%+5.1fpt"
          % (w, lab, n, t, act, sum(1 for x in rows if x["fin"] == 1), exp, act - exp))


OK = [x for x in ROWS if x["bias"] is not None]
ANA = [x for x in OK if x["pop"] and x["pop"] >= 7]
print("■ %d日 %d頭（重・良の両方を走っている馬 %d頭）／ 7番人気以下 %d頭"
      % (len(DAYS), len(ROWS), len(OK), len(ANA)))
for tag, rows in (("全体", OK), ("人気薄（7番人気以下）", ANA)):
    print("\n■ %s ── 掻き込み度の鞍内順位（0が最も重向き）" % tag)
    for lo, hi, lab in ((0, .25, "上位25%（重向き）"), (.25, .5, "25〜50%"),
                        (.5, .75, "50〜75%"), (.75, 1.01, "下位25%（良向き）")):
        ud([x for x in rows if x.get("br") is not None and lo <= x["br"] < hi], lab)

print("\n■ その日のレース上がりが場の平均より遅かったか（＝時計がかかったか）")
for lo, hi, lab in ((0.3, 99, "平均より0.3秒以上 遅い"), (-0.3, 0.3, "ふつう"),
                    (-99, -0.3, "0.3秒以上 速い")):
    g = [x for x in OK if x["slow"] is not None and lo <= x["slow"] < hi]
    print("   %s（%d頭）" % (lab, len(g)))
    ud([x for x in g if x.get("br") is not None and x["br"] < .25], "  重向き 上位25%", 26)
    ud([x for x in g if x.get("br") is not None and x["br"] >= .75], "  良向き 下位25%", 26)
