#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""調教の鞍内順位が本当に効いているかを、複数日まとめて検証する。

  python3 scripts/verify_chokyo.py notes/live/2026-09-28 notes/live/2026-09-29 ...

各フォルダに dayrank.txt（調教の順位）と results.json（結果）が要る。
生の3着内率は人気でほとんど説明できてしまうので、
人気別の3着内率から期待値を出して、実績との差（上振れpt）で見る。
"""
from __future__ import annotations
import argparse, collections, json, os, re, sys

# dayrank.txt の1行
HEAD = re.compile(r"^■ (\d+)R (\S+) ── (\d+)頭")
ROW = re.compile(
    r"^\s*(\d+) (.+?)\s+(\d\d/\d\d) (\S+) ([良稍重不]) ／ (\S+?)\s*\(負荷([\d.]+)\) ／ "
    r"([追流])組 (\d+)/(\d+)\s+／ その日 (\d+)/(\d+)\s+／ 同脚色 (\d+)/(\d+)\s+／ (\d+)本")
MIN_POOL = 20   # その日の母数がこれ未満なら順位を使わない（--min-pool で変えられる）


def load_day(d: str):
    """1日ぶんの (調教, 結果) を1頭ずつに畳む。"""
    dr, rs = os.path.join(d, "dayrank.txt"), os.path.join(d, "results.json")
    if not (os.path.exists(dr) and os.path.exists(rs)):
        return []
    ch, R = {}, None
    for ln in open(dr, encoding="utf-8"):
        s = ln.rstrip("\n")
        if re.match(r"^■ \d{8} ", s.strip()):
            continue
        h = HEAD.match(s.strip())
        if h:
            R = int(h.group(1)); continue
        m = ROW.match(s)
        if m and R:
            ch[(R, int(m.group(1)))] = dict(
                day=m.group(3), course=m.group(4), baba=m.group(5), kyaku=m.group(6),
                load=float(m.group(7)), bucket=m.group(8),
                bp=int(m.group(9)), bn=int(m.group(10)),
                dp=int(m.group(11)), dn=int(m.group(12)), nrun=int(m.group(15)))
    out = []
    res = json.load(open(rs, encoding="utf-8"))
    for Rs, r in res.items():
        es = r.get("e") or []
        ags = sorted([e["ag"] for e in es if e.get("ag")])
        for e in es:
            f = str(e.get("f", ""))
            if not f.isdigit():
                continue                      # 取消・除外
            pop = e.get("pop")
            x = dict(date=os.path.basename(d.rstrip("/")), R=int(Rs), u=e["u"], nm=e["nm"],
                     dist=r.get("dist"), baba=r.get("baba"), fs=r.get("n"),
                     fin=int(f), ag=e.get("ag"), c4=e.get("c4"),
                     pop=int(pop) if str(pop).isdigit() else None)
            x["agr"] = (ags.index(e["ag"]) + 1) if e.get("ag") in ags else None
            c = ch.get((int(Rs), e["u"]))
            if c and c["dn"] >= MIN_POOL:
                x["chq"] = (c["dp"] - 1) / float(c["dn"])   # 0が最上位
                x["chp"], x["chn"] = c["dp"], c["dn"]
                x["kyaku"], x["bucket"] = c["kyaku"], c["bucket"]
            out.append(x)
    return out


def pop_base(rows):
    """人気ごとの3着内率。これが『人気で説明できる分』。"""
    g = collections.defaultdict(list)
    for x in rows:
        if x["pop"]:
            g[min(x["pop"], 13)].append(x)
    return {k: sum(1 for y in v if y["fin"] <= 3) / float(len(v)) for k, v in g.items() if v}


def show(rows, lab, base, w=30):
    n = len(rows)
    if not n:
        print("   %-*s     0頭" % (w, lab)); return
    t3 = sum(1 for x in rows if x["fin"] <= 3)
    exp = sum(base.get(min(x["pop"], 13), 0.0) for x in rows if x["pop"])
    npop = sum(1 for x in rows if x["pop"])
    act = 100.0 * t3 / n
    if npop >= 5:
        e = 100.0 * exp / npop
        print("   %-*s %4d頭  3着内 %3d (%5.1f%%)  人気からの期待 %5.1f%%  上振れ %+5.1fpt"
              % (w, lab, n, t3, act, e, act - e))
    else:
        print("   %-*s %4d頭  3着内 %3d (%5.1f%%)" % (w, lab, n, t3, act))


def main():
    global MIN_POOL
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--min-pool", type=int, default=MIN_POOL,
                    help="その日の母数がこれ未満なら順位を使わない（既定 %d）" % MIN_POOL)
    a = ap.parse_args()
    MIN_POOL = a.min_pool
    print("■ 母数のしきい値 %d本" % MIN_POOL)
    ALL = []
    for d in a.dirs:
        rows = load_day(d)
        got = sum(1 for x in rows if "chq" in x)
        print("  %-26s 出走 %3d頭 ／ 調教の順位が使えた %3d頭" % (d, len(rows), got))
        ALL += rows
    if not ALL:
        print("データなし"); sys.exit(1)
    base = pop_base(ALL)
    print("\n■ 全体 %d頭（%d日）" % (len(ALL), len(a.dirs)))
    print("  人気別の3着内率（これが地の期待値）")
    print("   " + "  ".join("%d番人気 %.0f%%" % (k, 100 * v)
                            for k, v in sorted(base.items()) if k <= 10))

    cc = [x for x in ALL if "chq" in x]
    print("\n■ 調教の鞍内順位（母数%d本以上の日だけ・%d頭）" % (MIN_POOL, len(cc)))
    for lo, hi, lab in ((0, .25, "上位25%"), (.25, .5, "25〜50%"),
                        (.5, .75, "50〜75%"), (.75, 1.01, "下位25%")):
        show([x for x in cc if lo <= x["chq"] < hi], "調教 " + lab, base)

    print("\n■ 人気薄（7番人気以下）だけで見る")
    hc = [x for x in cc if x["pop"] and x["pop"] >= 7]
    for lo, hi, lab in ((0, .25, "上位25%"), (.25, .5, "25〜50%"),
                        (.5, .75, "50〜75%"), (.75, 1.01, "下位25%")):
        show([x for x in hc if lo <= x["chq"] < hi], "人気薄 × 調教 " + lab, base)

    print("\n■ 日ごと（符号が安定しているか）")
    for d in sorted({x["date"] for x in cc}):
        up = [x for x in cc if x["date"] == d and x["chq"] < .25]
        dn = [x for x in cc if x["date"] == d and x["chq"] >= .75]
        show(up, "%s 調教 上位25%%" % d, base, 34)
        show(dn, "%s 調教 下位25%%" % d, base, 34)

    print("\n■ 脚色（負荷）だけで見る ── 効かないことの確認")
    for b, lab in (("流", "流組（馬なり系）"), ("追", "追組（強め以上）")):
        show([x for x in cc if x.get("bucket") == b], lab, base)

    print("\n■ 上り順位 × 調教順位（当日の上りは結果なので、効くかの確認用）")
    for al, ah, alab in ((1, 3, "上り3位以内"), (4, 99, "上り4位以下")):
        for lo, hi, clab in ((0, .25, "調教上位25%"), (.25, .75, "調教 中"),
                             (.75, 1.01, "調教下位25%")):
            show([x for x in cc if x["agr"] and al <= x["agr"] <= ah
                  and lo <= x["chq"] < hi], "%s × %s" % (alab, clab), base, 34)


if __name__ == "__main__":
    main()
