"""渋った馬場(稍重・重)のときの狙いを、同じ物差しで出す。先の情報は使わない(時系列で貯める)。

    python3 scripts/jra_wet_pick.py --check            # 過去の稍重・重の鞍で確かめる
    python3 scripts/jra_wet_pick.py --shutuba data/jra/shutuba_20261115.jsonl --races 京都11,京都12,...

点数 = 力 + 馬場の得手(その馬場 − 良) + その場の馬場での決着の傾き × その馬の位置取り
  力       … 同じ芝ダの近5走の着順率(1=1着, 0=最下位)
  馬場の得手 … 稍重/重不良での着順率の平均 − 良での平均。走った数で縮める n/(n+3)
  決着の傾き … 同じ場・芝ダ(3年)で、その馬場の3着内が4角前1/3にいた率・組の外にいた率 − 良のとき
  位置取り   … 近5走の4角の相対位置(0=先頭)、近8走で4角の組の外にいた率
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOING = {"良": "良", "稍": "稍", "重": "重", "不": "重"}


def groups(s):
    return [[int(x) for x in re.findall(r"\d+", t)] for t in re.findall(r"\([^)]*\)|\d+", (s or "").replace("*", ""))]


class Book:
    def __init__(self):
        self.h = collections.defaultdict(list)     # (horse, 芝ダ) → [(going, pct, pos4, outer?)]
        self.c = collections.defaultdict(lambda: [0, 0, 0, 0])   # (場, 芝ダ, going) → [3着内, 前1/3, 組あり, 外]

    def add(self, d):
        g = GOING.get(d.get("baba"))
        if not g or d.get("surface") not in ("芝", "ダ"):
            return
        n = d["field_size"]
        gs = groups((d.get("corners") or {}).get("4"))
        for r in d["result"]:
            if not r.get("finish_pos") or not r.get("corner_pos") or n < 5:
                continue
            pos = (r["corner_pos"][-1] - 1) / (n - 1)
            out = None
            for gg in gs:
                if r["umaban"] in gg and len(gg) >= 2:
                    out = gg[-1] == r["umaban"]
            self.h[(r["horse_id"], d["surface"])].append((g, 1 - (r["finish_pos"] - 1) / (n - 1), pos, out))
            if r["finish_pos"] <= 3:
                c = self.c[(d["place"], d["surface"], g)]
                c[0] += 1
                c[1] += pos <= 1 / 3
                if out is not None:
                    c[2] += 1
                    c[3] += out

    def tilt(self, place, surface, g):
        def rate(gg):
            c = self.c[(place, surface, gg)]
            if c[0] < 60:   # 少ないときは全場の同じ芝ダ
                c = [sum(v[i] for k, v in self.c.items() if k[1] == surface and k[2] == gg) for i in range(4)]
            return c[1] / max(1, c[0]), c[3] / max(1, c[2])
        f, o = rate(g)
        f0, o0 = rate("良")
        return f - f0, o - o0

    def feats(self, hid, surface, g):
        H = self.h.get((hid, surface), [])
        if not H:
            return None
        abil = st.mean(x[1] for x in H[-5:])
        dry = [x[1] for x in H if x[0] == "良"]
        wet = [x[1] for x in H if x[0] == g]
        pref = ((st.mean(wet) - (st.mean(dry) if dry else abil)) * len(wet) / (len(wet) + 3)) if wet else 0.0
        pos = st.mean(x[2] for x in H[-5:])
        outs = [x[3] for x in H[-8:] if x[3] is not None]
        orate = sum(outs) / len(outs) if outs else 0.5
        return {"abil": abil, "pref": pref, "pos": pos, "out": orate, "nwet": len(wet)}


def score(f, tilt, wp=1.0, wt=3.0):
    df, do = tilt
    return f["abil"] + wp * f["pref"] + wt * (df * (0.5 - f["pos"]) * 2 + do * (f["out"] - 0.5) * 2)


def check(rows):
    bk = Book()
    res = collections.defaultdict(lambda: [0, 0, 0])
    for d in rows:
        g = GOING.get(d.get("baba"))
        if g in ("稍", "重") and d["date"] >= "2025-01-01" and d.get("surface") in ("芝", "ダ"):
            t = bk.tilt(d["place"], d["surface"], g)
            cand = []
            for r in d["result"]:
                f = bk.feats(r["horse_id"], d["surface"], g)
                if f:
                    cand.append((r, f))
            if len(cand) >= 0.7 * d["field_size"] and len(cand) >= 6:
                for nm, key in (("力だけ", lambda x: x[1]["abil"]), ("力＋馬場の得手", lambda x: x[1]["abil"] + x[1]["pref"]),
                                ("全部(位置×馬場の傾きも)", lambda x: score(x[1], t))):
                    top = max(cand, key=key)
                    res[(g, nm)][0] += 1
                    res[(g, nm)][1] += top[0]["finish_pos"] <= 3
                    res[(g, nm)][2] += top[0]["finish_pos"] == 1
        bk.add(d)
    for g in ("稍", "重"):
        for nm in ("力だけ", "力＋馬場の得手", "全部(位置×馬場の傾きも)"):
            n, t3, w = res[(g, nm)]
            if n:
                print(f"  {'稍重' if g == '稍' else '重・不良'} {nm:16s} {n}鞍  1位の馬が3着内 {t3/n:.1%}  勝ち {w/n:.1%}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--shutuba")
    ap.add_argument("--races", default="")
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(ROOT / "data/jra/races.jsonl")]
    rows.sort(key=lambda d: (d["date"], d["race_id"]))
    if a.check:
        check(rows)
    if a.shutuba:
        bk = Book()
        for d in rows:
            bk.add(d)
        want = set(a.races.split(",")) if a.races else None
        for l in open(a.shutuba, encoding="utf-8"):
            d = json.loads(l)
            key = f"{d['place']}{int(d['race_id'][-2:])}"
            if want and key not in want or d.get("surface") not in ("芝", "ダ"):
                continue
            print(f"===== {key}R {d['name']} {d['surface']}{d['distance']}")
            for g in ("稍", "重"):
                t = bk.tilt(d["place"], d["surface"], g)
                sc = []
                for e in d["result"]:
                    f = bk.feats(e["horse_id"], d["surface"], g)
                    if f:
                        sc.append((score(f, t), e["umaban"], e["horse_name"], f))
                sc.sort(reverse=True)
                print(f"  {'稍重' if g == '稍' else '重'}: 傾き 前{t[0]:+.2f} 外{t[1]:+.2f} | "
                      + "  ".join(f"{u}{nm[:5]}({s:.2f} 力{f['abil']:.2f} 得手{f['pref']:+.2f}/{f['nwet']}走)" for s, u, nm, f in sc[:6]))


if __name__ == "__main__":
    main()
