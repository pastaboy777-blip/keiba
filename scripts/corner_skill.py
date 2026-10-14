#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""近5走の通過順から「コーナーで損をしない馬」を測る。

出馬表の近走には各馬の通過順がそのまま載っている（例 4-4-2-3）。
最後の2つが3角→4角。ここで順位を上げられる馬は、落ち込む区間で
外に出さずに動けている。

  python3 scripts/corner_skill.py            # 結果のある日を全部で検証
  python3 scripts/corner_skill.py 2026-10-14 # その日の1頭ずつ

出すもの（1頭ずつ・近5走から）
  cg     3角→4角で上げた合計（頭数で割った相対で見る）
  cgn    上げた走の数
  back   4角から着順を落とさなかった走の数（直線で止まらない）
"""
from __future__ import annotations
import glob, json, os, statistics, sys


def corner_gain(run):
    """1走ぶん。3角→4角の順位変化を頭数で割る。プラスが押し上げ。"""
    cor = (run.get("cor") or "").split("-")
    fs = run.get("fs")
    if len(cor) < 2 or not fs:
        return None
    try:
        a, b = int(cor[-2]), int(cor[-1])
    except ValueError:
        return None
    return (a - b) / float(fs)


def straight(run):
    """4角から着順をどれだけ落としたか（頭数で割る）。プラスが直線で伸びた。"""
    fs, fin, c4 = run.get("fs"), run.get("fin"), run.get("c4")
    if not (fs and fin and c4):
        return None
    return (c4 - fin) / float(fs)


def profile(runs):
    g = [corner_gain(x) for x in runs]
    g = [x for x in g if x is not None]
    s = [straight(x) for x in runs]
    s = [x for x in s if x is not None]
    if not g:
        return None
    return dict(cg=statistics.mean(g), cgn=sum(1 for x in g if x > 0),
                st=(statistics.mean(s) if s else None),
                stn=sum(1 for x in s if x >= 0), n=len(g))


DAYS = sorted(os.path.basename(os.path.dirname(p))
              for p in glob.glob("/home/user/keiba/notes/live/*/past5.json")
              if os.path.exists(os.path.join(os.path.dirname(p), "results.json")))

ROWS = []
for d in DAYS:
    p5 = json.load(open("/home/user/keiba/notes/live/%s/past5.json" % d, encoding="utf-8"))
    res = json.load(open("/home/user/keiba/notes/live/%s/results.json" % d, encoding="utf-8"))
    for Rs, v in p5.items():
        r = res.get(Rs)
        if not r:
            continue
        fin = {e["u"]: e for e in r["e"] if str(e.get("f", "")).isdigit()}
        rows = []
        for c in v["e"]:
            e = fin.get(c["u"])
            if not e:
                continue
            pr = profile(c.get("runs") or [])
            if not pr:
                continue
            rows.append(dict(day=d, R=int(Rs), u=c["u"], nm=c["nm"],
                             fin=int(e["f"]),
                             pop=int(e["pop"]) if str(e.get("pop", "")).isdigit() else None,
                             c4=e.get("c4"), **pr))
        # 鞍の中で順位にする
        for key, tag in (("cg", "cgr"), ("st", "str")):
            have = [x for x in rows if x.get(key) is not None]
            have.sort(key=lambda z: -z[key])
            for i, x in enumerate(have):
                x[tag] = i / float(len(have)) if len(have) > 1 else 0.5
        ROWS += rows

if len(sys.argv) > 1:
    d = sys.argv[1]
    g = [x for x in ROWS if x["day"] == d]
    print("■ %s ── 近5走のコーナーでの押し上げ（鞍内順位つき）" % d)
    print("   %2s %3s %-16s %3s %7s %4s %7s %4s %s"
          % ("R", "馬番", "馬", "人気", "角で押上", "回数", "直線", "回数", "着"))
    for x in sorted(g, key=lambda z: (z["R"], z.get("cgr", 1))):
        print("   %2dR %3d %-16s %3s %+7.3f %3d/%d %+7.3f %3d/%d %2d着"
              % (x["R"], x["u"], x["nm"][:16], x["pop"], x["cg"], x["cgn"], x["n"],
                 x["st"] or 0, x["stn"], x["n"], x["fin"]))
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


ANA = [x for x in ROWS if x["pop"] and x["pop"] >= 7]
print("■ %d日 %d頭 ／ 7番人気以下 %d頭" % (len(DAYS), len(ROWS), len(ANA)))
print("   " + " ".join(d[5:] for d in DAYS))
for tag, rows in (("全体", ROWS), ("人気薄（7番人気以下）", ANA)):
    print("\n■ %s ── 近5走でコーナーを押し上げる馬（鞍内順位）" % tag)
    for lo, hi, lab in ((0, .25, "上位25%"), (.25, .5, "25〜50%"),
                        (.5, .75, "50〜75%"), (.75, 1.01, "下位25%")):
        ud([x for x in rows if x.get("cgr") is not None and lo <= x["cgr"] < hi], lab)

print("\n■ 人気薄 ── 近5走で3角→4角を上げた走の数")
for lo, hi, lab in ((0, 0, "0走"), (1, 1, "1走"), (2, 2, "2走"), (3, 9, "3走以上")):
    ud([x for x in ANA if lo <= x["cgn"] <= hi], lab)

print("\n■ 人気薄 ── コーナーで上げる × 直線で止まらない")
for c0, c1, cl in ((0, .34, "角で押上 上位1/3"), (.34, 1.01, "それ以外")):
    for s0, s1, sl in ((0, .34, "直線 上位1/3"), (.34, 1.01, "それ以外")):
        ud([x for x in ANA if x.get("cgr") is not None and x.get("str") is not None
            and c0 <= x["cgr"] < c1 and s0 <= x["str"] < s1], "%s × %s" % (cl, sl))
