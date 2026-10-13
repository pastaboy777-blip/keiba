#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""人気薄（7番人気以下）を、発走前に分かるものだけで拾えるかを比べる。

  python3 scripts/verify_ana.py

notes/live/*/ の past5.json と results.json が揃っている日を全部使う。
dayrank.txt があればその日の調教順位も混ぜる。

比べるもの（すべて発走前に分かる）
  先行力   近5走の1角位置を頭数で割った相対の中央値を、鞍の中で順位にしたもの
  終い     近5走の上り3Fを距離・馬場で補正した偏差の中央値を、鞍の中で順位に
  調教     その日の追い切りの鞍内順位
  枠       馬番を頭数で割った相対位置
  小型     鞍の中で前走馬体重が軽いほう1/3
  減量騎手  ▲☆◇△ のついた騎手

生の率は人気でほとんど説明がつくので、人気別3着内率からの上振れで見る。
"""
from __future__ import annotations
import collections, glob, json, os, re, statistics

MARKS = "▲☆◇△▽★"
HEAD = re.compile(r"^■ (\d+)R (\S+) ── (\d+)頭")
CROW = re.compile(r"^\s*(\d+) (.+?)\s+(\d\d/\d\d) (\S+) ([良稍重不]) ／ (\S+?)\s*\(負荷[\d.]+\) ／ "
                  r"([追流])組 (\d+)/(\d+)\s+／ その日 (\d+)/(\d+)")
MIN_POOL = 20

DAYS = sorted(os.path.basename(os.path.dirname(p))
              for p in glob.glob("/home/user/keiba/notes/live/*/past5.json")
              if os.path.exists(os.path.join(os.path.dirname(p), "results.json")))

# ── 上りの基準（距離×馬場ごとの中央値）を全近走から作る ──────────────
pool = collections.defaultdict(list)
P5 = {}
for d in DAYS:
    P5[d] = json.load(open("/home/user/keiba/notes/live/%s/past5.json" % d, encoding="utf-8"))
    for v in P5[d].values():
        for e in v["e"]:
            for x in (e.get("runs") or []):
                if x.get("ag"):
                    pool[(x["dist"], x["baba"])].append(x["ag"])
BASE_AG = {k: statistics.median(v) for k, v in pool.items() if len(v) >= 8}
GBASE = {}
for dd in {k[0] for k in pool}:
    vs = [x for k, v in pool.items() if k[0] == dd for x in v]
    if len(vs) >= 8:
        GBASE[dd] = statistics.median(vs)


def agdev(x):
    b = BASE_AG.get((x["dist"], x["baba"])) or GBASE.get(x["dist"])
    return (x["ag"] - b) if (b and x.get("ag")) else None


# ── 調教の鞍内順位 ────────────────────────────────────
CH = {}
for d in DAYS:
    p = "/home/user/keiba/notes/live/%s/dayrank.txt" % d
    if not os.path.exists(p):
        continue
    R = None
    for ln in open(p, encoding="utf-8"):
        s = ln.rstrip("\n")
        if re.match(r"^■ \d{8} ", s.strip()):
            continue
        h = HEAD.match(s.strip())
        if h:
            R = int(h.group(1))
            continue
        m = CROW.match(s)
        if m and R:
            dp, dn = int(m.group(10)), int(m.group(11))
            if dn >= MIN_POOL:
                CH[(d, R, int(m.group(1)))] = (dp - 1) / float(dn)

ALL = []
for d in DAYS:
    res = json.load(open("/home/user/keiba/notes/live/%s/results.json" % d, encoding="utf-8"))
    p5 = P5[d]
    for Rs, r in res.items():
        ent = {e["u"]: e for e in (p5.get(Rs, {}).get("e") or [])}
        es = [e for e in r["e"] if str(e.get("f", "")).isdigit()]
        if not es:
            continue
        # 前走馬体重で小型を決める（当日の馬体重は発走前に分からない）
        pw = {}
        for u, c in ent.items():
            rr = [x for x in (c.get("runs") or []) if x.get("wt")]
            if rr:
                pw[u] = rr[0]["wt"]
        cut = sorted(pw.values())[max(0, len(pw) // 3 - 1)] if len(pw) >= 5 else None
        rows = []
        for e in es:
            c = ent.get(e["u"], {})
            runs = c.get("runs") or []
            fc = [int(x["cor"].split("-")[0]) / float(x["fs"])
                  for x in runs if x.get("cor") and x.get("fs")]
            dv = [z for z in (agdev(x) for x in runs) if z is not None]
            rows.append(dict(
                day=d, R=int(Rs), dist=r["dist"], n=r["n"], u=e["u"], nm=e["nm"],
                fin=int(e["f"]),
                pop=int(e["pop"]) if str(e.get("pop", "")).isdigit() else None,
                c4=e.get("c4"), jk=e.get("jk", ""),
                gen=bool(e.get("jk") and e["jk"][0] in MARKS),
                sml=bool(cut and pw.get(e["u"]) and pw[e["u"]] <= cut),
                uq=((e["u"] - 1) / float(r["n"])) if r["n"] else None,
                ch=CH.get((d, int(Rs), e["u"])),
                sen=(statistics.median(fc) if fc else None),
                agd=(statistics.median(dv) if dv else None)))
        for key, tag in (("sen", "senr"), ("agd", "agdr")):
            have = [x for x in rows if x[key] is not None]
            have.sort(key=lambda z: z[key])
            for i, x in enumerate(have):
                x[tag] = i / float(len(have)) if len(have) > 1 else 0.5
        ALL += rows

BASE = {}
for p in range(1, 20):
    g = [x for x in ALL if x["pop"] == p]
    if g:
        BASE[p] = 100.0 * sum(1 for x in g if x["fin"] <= 3) / len(g)

ANA = [x for x in ALL if x["pop"] and x["pop"] >= 7]
print("■ %d日 %d頭 ／ 7番人気以下 %d頭 ／ 3着内 %d (%.1f%%)"
      % (len(DAYS), len(ALL), len(ANA), sum(1 for x in ANA if x["fin"] <= 3),
         100.0 * sum(1 for x in ANA if x["fin"] <= 3) / len(ANA)))
print("   " + " ".join(d[5:] for d in DAYS))


def ud(rows, lab, w=26):
    n = len(rows)
    if not n:
        print("   %-*s   0頭" % (w, lab))
        return
    t = sum(1 for x in rows if x["fin"] <= 3)
    act = 100.0 * t / n
    hv = [x for x in rows if x["pop"] in BASE]
    exp = sum(BASE[x["pop"]] for x in hv) / len(hv) if hv else 0
    pops = [x["pop"] for x in rows if x["pop"]]
    print("   %-*s %3d頭 3着内%2d (%5.1f%%) 期待%5.1f%% 上振れ%+5.1fpt 人気中央%2d"
          % (w, lab, n, t, act, exp, act - exp,
             int(statistics.median(pops)) if pops else 0))


for key, lab in (("senr", "先行力"), ("agdr", "終い"), ("ch", "調教")):
    g = [x for x in ANA if x.get(key) is not None]
    print("\n■ %s ランク（鞍の中で。0が最上位）── %d頭" % (lab, len(g)))
    for lo, hi, l2 in ((0, .25, "上位25%"), (.25, .5, "25〜50%"),
                       (.5, .75, "50〜75%"), (.75, 1.01, "下位25%")):
        ud([x for x in g if lo <= x[key] < hi], "%s %s" % (lab, l2))

print("\n■ 枠（馬番を頭数で割った相対位置）")
for lo, hi, lab in ((0, .34, "内寄り1/3"), (.34, .67, "中"), (.67, 1.01, "外寄り1/3")):
    ud([x for x in ANA if x["uq"] is not None and lo <= x["uq"] < hi], lab)

print("\n■ 小型（前走馬体重が鞍内で軽いほう1/3）と減量騎手")
ud([x for x in ANA if x["sml"]], "小型")
ud([x for x in ANA if not x["sml"]], "小型でない")
ud([x for x in ANA if x["gen"]], "減量騎手")
ud([x for x in ANA if x["sml"] and x["gen"]], "小型 × 減量騎手")

print("\n■ 先行力上位25%を、ほかと掛ける")
sen = [x for x in ANA if x.get("senr") is not None and x["senr"] < .25]
ud(sen, "先行力 上位25%")
ud([x for x in sen if x.get("ch") is not None and x["ch"] < .5], "　× 調教が鞍内の上半分")
ud([x for x in sen if x.get("ch") is not None and x["ch"] >= .5], "　× 調教が下半分")
ud([x for x in sen if x["uq"] is not None and x["uq"] < .34], "　× 内寄り1/3")
ud([x for x in sen if x["uq"] is not None and x["uq"] >= .67], "　× 外寄り1/3")
ud([x for x in sen if x.get("agdr") is not None and x["agdr"] < .34], "　× 終いも上位1/3")

print("\n■ 人気帯で分ける（先行力 上位25%）")
for lo, hi, lab in ((7, 9, "7〜9番人気"), (10, 99, "10番人気以下")):
    ud([x for x in sen if lo <= x["pop"] <= hi], lab)

print("\n■ 日ごと（先行力 上位25%）")
for d in DAYS:
    g = [x for x in sen if x["day"] == d]
    if g:
        t = sum(1 for x in g if x["fin"] <= 3)
        print("   %s  %2d頭  3着内 %d (%3.0f%%)" % (d[5:], len(g), t, 100.0 * t / len(g)))

print("\n■ 参考：人気馬側（1〜6番人気）でも先行力は効くか")
fav = [x for x in ALL if x["pop"] and x["pop"] <= 6 and x.get("senr") is not None]
for lo, hi, lab in ((0, .25, "先行力 上位25%"), (.25, .75, "中"), (.75, 1.01, "下位25%")):
    ud([x for x in fav if lo <= x["senr"] < hi], lab)
