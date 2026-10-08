#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""その日の馬場感を数値にする。

見ているのは4つ。

  脚色の揃い   鞍の中で上り3Fがどれだけ散るか。四分位差（IQR）で見る。
               外れ値（大差で沈んだ馬）に引っ張られないようにSDは使わない。
               小さいほど「最後はみんな同じ脚色」。
  入れ替わり   4角の通過順と着順の順位相関（スピアマン）。
               1に近いほど4角の並びがそのまま決着＝抜けない馬場。
  追われる側   4角1〜2番手の3着内率。
  追う側       4角5番手以降で上り3位以内だった馬の3着内率。
               「追われる側 − 追う側」がプラスなら、追われる方が良い馬場。

荒れた鞍の中身も一緒に出す。

  連番度       1〜3着の馬番がどれだけ隣り合っているか（最大−最小 ÷ 頭数）。
               小さいほど固まっている。
  減量騎手     ▲☆◇ のついた騎手。

使い方:
  python3 scripts/baba_index.py                      全日
  python3 scripts/baba_index.py --day 2026-10-08     1日を鞍ごとに
"""
from __future__ import annotations
import argparse, glob, json, os, statistics

MARKS = "▲☆◇△▽★"
ROUGH_POP = 7          # これ以下の人気が3着内に来たら「荒れた」とみなす


def iqr(v):
    v = sorted(v)
    n = len(v)
    if n < 4:
        return None
    lo = statistics.median(v[: n // 2])
    hi = statistics.median(v[(n + 1) // 2 :])
    return hi - lo


def spearman(a, b):
    """同順位を平均順位でならしたスピアマン。"""
    def rank(xs):
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        r = [0.0] * len(xs)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
                j += 1
            m = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = m
            i = j + 1
        return r
    ra, rb = rank(a), rank(b)
    n = len(a)
    if n < 4:
        return None
    ma, mb = statistics.mean(ra), statistics.mean(rb)
    sa = sum((x - ma) ** 2 for x in ra) ** .5
    sb = sum((x - mb) ** 2 for x in rb) ** .5
    if sa == 0 or sb == 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(ra, rb)) / (sa * sb)


def load(path):
    res = json.load(open(path, encoding="utf-8"))
    out = []
    for Rs, r in res.items():
        es = [e for e in r["e"] if str(e.get("f", "")).isdigit()]
        if len(es) < 6:
            continue
        ag = [e["ag"] for e in es if e.get("ag")]
        srt = sorted(ag)
        for e in es:
            e["agr"] = srt.index(e["ag"]) + 1 if e.get("ag") in srt else None
            e["fin"] = int(e["f"])
            # 人気は古いJSONで文字列のことがある
            e["pop"] = int(e["pop"]) if str(e.get("pop", "")).isdigit() else None
            e["gen"] = bool(e.get("jk") and e["jk"][0] in MARKS)
        wt = sorted(e["wt"] for e in es if e.get("wt"))
        cut = wt[max(0, len(wt) // 3 - 1)] if wt else 0
        for e in es:
            e["sml"] = bool(e.get("wt") and e["wt"] <= cut)
        c4 = [(e["c4"], e["fin"]) for e in es if e.get("c4")]
        t3 = sorted([e for e in es if e["fin"] <= 3], key=lambda z: z["fin"])
        us = [e["u"] for e in t3]
        out.append(dict(
            R=int(Rs), dist=r["dist"], course=r.get("course", ""), n=r["n"],
            cls=r.get("cls", ""), es=es,
            iqr=iqr(ag),
            sp=spearman([x[0] for x in c4], [x[1] for x in c4]),
            keep=[e for e in es if e.get("c4") and e["c4"] <= 2],
            chase=[e for e in es if e.get("c4") and e["c4"] >= 5 and e["agr"] and e["agr"] <= 3],
            t3=t3,
            # 1〜3着の馬番がどれだけ固まっているか
            span=((max(us) - min(us)) / float(r["n"])) if len(us) == 3 else None,
            rough=max((e["pop"] for e in t3 if e.get("pop")), default=0)))
    return out


def rate(rows):
    if not rows:
        return None
    return 100.0 * sum(1 for e in rows if e["fin"] <= 3) / len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", help="この日を鞍ごとに出す")
    ap.add_argument("--dir", default="/home/user/keiba/notes/live")
    a = ap.parse_args()

    days = sorted(os.path.basename(os.path.dirname(p))
                  for p in glob.glob(os.path.join(a.dir, "*", "results.json")))
    D = {d: load(os.path.join(a.dir, d, "results.json")) for d in days}
    D = {d: v for d, v in D.items() if v}

    print("■ 日ごとの馬場感")
    print("   %-7s %3s  %5s %6s   %6s %6s %7s"
          % ("日", "鞍", "脚色", "入替り", "追われ", "追う", "差"))
    for d, rs in D.items():
        iq = [x["iqr"] for x in rs if x["iqr"] is not None]
        sp = [x["sp"] for x in rs if x["sp"] is not None]
        k = rate([e for x in rs for e in x["keep"]])
        c = rate([e for x in rs for e in x["chase"]])
        print("   %-7s %3d  %5.2f %+6.2f   %5.1f%% %5.1f%% %+6.1fpt"
              % (d[5:], len(rs), statistics.median(iq), statistics.median(sp),
                 k or 0, c or 0, (k or 0) - (c or 0)))
    print("   脚色＝鞍内の上り3Fの四分位差（小さいほど揃う） ／ 入替り＝4角順位と着順の相関")

    print("\n■ 荒れた鞍（%d番人気以下が3着内）の中身" % ROUGH_POP)
    print("   %-7s %3s %-9s %3s  %5s %5s %5s  %s"
          % ("日", "R", "距離", "頭数", "連番度", "脚色", "入替り", "1〜3着の馬番"))
    rough = []
    for d, rs in D.items():
        for x in rs:
            if x["rough"] >= ROUGH_POP:
                rough.append((d, x))
                print("   %-7s %2dR ダ%4d%-2s %3d  %5.2f %5.2f %+5.2f   %s"
                      % (d[5:], x["R"], x["dist"], x["course"], x["n"],
                         x["span"] if x["span"] is not None else 0,
                         x["iqr"] or 0, x["sp"] or 0,
                         "-".join(str(e["u"]) for e in x["t3"])))
    oth = [(d, x) for d, rs in D.items() for x in rs if x["rough"] < ROUGH_POP]
    # 馬番を無作為に3つ引いたときの連番度は (頭数-1)/(2×頭数)。これと比べる。
    for g, lab in ((rough, "荒れた鞍"), (oth, "それ以外")):
        sp = [x["span"] for _, x in g if x["span"] is not None]
        ex = [(x["n"] - 1) / (2.0 * x["n"]) for _, x in g if x["span"] is not None]
        iq = [x["iqr"] for _, x in g if x["iqr"] is not None]
        dv = [a - b for a, b in zip(sp, ex)]
        print("   %-8s %3d鞍  連番度 %.2f（無作為なら %.2f ／ 差 %+.2f）  脚色 %.2f"
              % (lab, len(g), statistics.median(sp) if sp else 0,
                 statistics.median(ex) if ex else 0,
                 statistics.median(dv) if dv else 0,
                 statistics.median(iq) if iq else 0))

    print("\n■ 減量騎手（%s）" % MARKS[:3])
    allh = [e for rs in D.values() for x in rs for e in x["es"]]
    gen = [e for e in allh if e["gen"]]
    print("   全体 %d頭中 %d頭 ／ 3着内率 %.1f%%（減量なし %.1f%%）"
          % (len(allh), len(gen), rate(gen) or 0,
             rate([e for e in allh if not e["gen"]]) or 0))
    for lo, hi, lab in ((1, 6, "1〜6番人気"), (7, 99, "7番人気以下")):
        g = [e for e in gen if e.get("pop") and lo <= e["pop"] <= hi]
        o = [e for e in allh if not e["gen"] and e.get("pop") and lo <= e["pop"] <= hi]
        print("   %-12s 減量 %3d頭 %5.1f%%  ／ 減量なし %3d頭 %5.1f%%"
              % (lab, len(g), rate(g) or 0, len(o), rate(o) or 0))
    # 生の率は乗っている馬の人気でほとんど説明できてしまうので、
    # 人気別の3着内率から期待値を出して、そこからの上振れで見る。
    bp = {}
    for p in range(1, 19):
        g = [e for e in allh if e["pop"] == p]
        if g:
            bp[p] = rate(g)

    def updown(rows, lab, w=22):
        n = len(rows)
        if not n:
            print("   %-*s   0頭" % (w, lab))
            return
        act = rate(rows)
        hv = [e for e in rows if e["pop"] in bp]
        exp = sum(bp[e["pop"]] for e in hv) / len(hv) if hv else 0
        print("   %-*s %3d頭  3着内 %5.1f%%  期待 %5.1f%%  上振れ %+5.1fpt"
              % (w, lab, n, act, exp, act - exp))

    print("   ── 人気で揃えて見る（人気別3着内率からの上振れ）")
    updown(gen, "減量騎手ぜんぶ")
    print("   ── 小型（鞍内で軽いほう1/3）と掛ける")
    for sml, lab in ((True, "小型"), (False, "小型でない")):
        for g2, lab2 in ((True, "減量騎手"), (False, "減量なし")):
            updown([e for e in allh if e["sml"] == sml and e["gen"] == g2],
                   "%s × %s" % (lab, lab2))
    print("   ── 荒れた鞍の1〜3着に減量騎手が入っていた割合")
    for g, lab in ((rough, "荒れた鞍"), (oth, "それ以外")):
        if not g:
            continue
        hit = sum(1 for _, x in g if any(e["gen"] for e in x["t3"]))
        print("   %-8s %3d鞍中 %3d鞍 (%.0f%%)" % (lab, len(g), hit, 100.0 * hit / len(g)))

    if a.day and a.day in D:
        print("\n■ %s ── 鞍ごと" % a.day)
        print("   %3s %-9s %3s  %5s %6s  %6s %6s  %s"
              % ("R", "距離", "頭数", "脚色", "入替り", "追われ", "追う", "1〜3着"))
        for x in sorted(D[a.day], key=lambda z: z["R"]):
            k, c = rate(x["keep"]), rate(x["chase"])
            print("   %2dR ダ%4d%-2s %3d  %5.2f %+6.2f  %5s %5s  %s"
                  % (x["R"], x["dist"], x["course"], x["n"], x["iqr"] or 0, x["sp"] or 0,
                     ("%.0f%%" % k) if k is not None else "─",
                     ("%.0f%%" % c) if c is not None else "─",
                     " ".join("%d%s%s" % (e["u"], "▲" if e["gen"] else "", "✓" if e["sml"] else "")
                              for e in x["t3"])))


if __name__ == "__main__":
    main()
