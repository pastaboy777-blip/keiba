#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上がりの「濃さ」を3つの相対で測る。

★ユーザーの言語化をそのまま実装したもの。

  上がりの絶対値には意味がない。
  「レース平均との差」を「どの位置から」「前が有利か不利かの中で」出したか。
  この3つが揃って初めて、その脚が濃いか薄いかが決まる。

  ① レース内相対 … 順位ではなく、そのレースの平均上がりとの秒差
  ② 位置相対   … 後方の馬は道中で脚を使っていないので、上がりが速く出て当たり前
  ③ 展開相対   … 前が楽に残った流れか、前が止まった流れか

②に数字を入れる:
  taikan_lap.py の較正で「最終コーナーで1順位後ろ＝前半が0.13〜0.16秒楽」と出ている。
  楽をした分はそのまま上がりに乗る。だから位置から期待される平均差を引けば、
  【位置では説明できない分＝本当の脚】が残る。
      濃さ = 上がりの平均差 − 位置から期待される平均差
  期待値はデータから推定する（相対4角位置に回帰）。

③の測り方:
  そのレースの前々にいた馬（4角上位3頭）の平均差。
      マイナス … 前の馬が落ちていない ＝ 前が楽に残った流れ
      プラス  … 前の馬が落ちた       ＝ 前が止まった流れ

狙う形:
  前が楽に残った流れで、後方から、位置で説明できない脚を使ったのに着外だった馬。
  次に前が止まる流れ・内枠・斤量減が来れば、同じ脚のまま順位だけが上がる。

使い方:
  python3 scripts/ana/agari_sotai.py --calib          # 位置と上がりの関係を出す
  python3 scripts/ana/agari_sotai.py --verify         # 狙う形の次走成績を対照つきで
  python3 scripts/ana/agari_sotai.py --race 2026-07-22 大井 10
"""
from __future__ import annotations

import argparse
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bt

FRONT_N = 3          # ③で「前」とみなす4角上位の頭数


def prep(r):
    """1レースを (馬, 上がり平均差, 4角順位, 相対位置) に開く。"""
    ag = [x["agari"] for x in r["rows"] if x["agari"]]
    if len(ag) < 5 or r["n"] < 5:
        return None, None
    m = st.mean(ag)
    out = []
    for x in r["rows"]:
        p = [int(v) for v in re.findall(r"\d+", x.get("pas") or "")]
        if not x["agari"] or not p:
            continue
        rk = p[-1]
        out.append(dict(h=x, sa=x["agari"] - m, rk=rk, rel=(rk - 1) / (r["n"] - 1)))
    return out, m


def calib(R, verbose=False):
    """相対4角位置 → 期待される上がり平均差。距離帯別に推定する。"""
    by = defaultdict(list)
    for r in R:
        v, _ = prep(r)
        if not v:
            continue
        d = "〜1000m" if r["dist"] <= 1000 else ("1200m" if r["dist"] <= 1200
             else ("1400-1500m" if r["dist"] <= 1500 else "1600m〜"))
        for z in v:
            by[d].append((z["rel"], z["sa"]))
    out = {}
    for d, v in by.items():
        mx = st.mean(a for a, _ in v); my = st.mean(b for _, b in v)
        sxx = sum((a - mx) ** 2 for a, _ in v)
        b = sum((a - mx) * (c - my) for a, c in v) / sxx
        out[d] = (b, my - b * mx)
        if verbose:
            print(f"  {d:<12} n{len(v):>6}  傾き {b:+.2f} 秒/相対位置1.0"
                  f"   （先頭 {b*0+out[d][1]:+.2f} → 最後方 {b+out[d][1]:+.2f}）")
    return out


def band(dist):
    return "〜1000m" if dist <= 1000 else ("1200m" if dist <= 1200
           else ("1400-1500m" if dist <= 1500 else "1600m〜"))


def koi(r, A):
    """そのレースの各馬の『濃さ』と、レース全体の『前の残り方』を返す。"""
    v, m = prep(r)
    if not v:
        return None, None, None
    b, c = A[band(r["dist"])]
    for z in v:
        z["exp"] = b * z["rel"] + c            # 位置から期待される平均差
        z["koi"] = z["sa"] - z["exp"]          # 位置では説明できない分＝濃さ
    front = [z for z in sorted(v, key=lambda q: q["rk"])[:FRONT_N]]
    tenkai = st.mean(z["sa"] for z in front)   # ＋なら前が止まった／−なら前が楽だった
    return v, m, tenkai


def history(R):
    h = defaultdict(list)
    for r in R:
        for x in r["rows"]:
            h[x["name"]].append((r["date"], r, x))
    for q in h.values():
        q.sort(key=lambda z: z[0])
    return h


def next_run(H, name, date):
    for d, r, x in H.get(name, []):
        if d > date:
            return r, x
    return None, None


def tally(v, label):
    if not v:
        return f"{label:<34} 該当なし"
    n = len(v)
    w = sum(1 for a, b, o in v if a); p = sum(1 for a, b, o in v if b)
    ret = sum((o * 100 if a and o else 0) for a, b, o in v)
    return (f"{label:<34}{n:>6}回 1着{w/n*100:>5.1f}% 3着内{p/n*100:>5.1f}% 単回収{ret/n:>6.1f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calib", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--race", nargs=3, metavar=("日付", "場", "R"))
    ap.add_argument("--koi", type=float, default=-0.20, help="濃さの閾値（これより小さければ濃い）")
    ap.add_argument("--rel", type=float, default=0.5, help="後方とみなす相対位置の下限")
    a = ap.parse_args()

    R = bt.load("2026-01-01", "2026-12-31")
    print(f"■ 南関 {len(R):,}レース")
    print("■ ② 位置から期待される上がりの平均差（データから推定）")
    A = calib(R, verbose=True)
    print("   ※ 後方ほどマイナス＝上がりが速く出て当たり前。この分を引かないと脚を読み違える\n")

    if a.race:
        r = next((x for x in R if x["date"] == a.race[0] and x["place"] == a.race[1]
                  and x["rn"] == int(a.race[2])), None)
        if not r:
            print("該当レースなし"); return
        v, m, tk = koi(r, A)
        print(f"■ {r['date']} {r['place']}{r['rn']}R {r['dist']}m {r['baba']} 【{r['klass']}】")
        print(f"  平均上がり {m:.2f}   ③前の残り方 {tk:+.2f}"
              f"（{'前が止まった' if tk > 0.1 else ('前が楽に残った' if tk < -0.1 else '中立')}）\n")
        print(f"  {'着':>3} {'馬':<16}{'4角':>4}{'上り':>6}{'①平均差':>9}{'②位置期待':>10}{'③濃さ':>8}")
        for z in sorted(v, key=lambda q: q["h"]["chaku"]):
            print(f"  {z['h']['chaku']:>3} {z['h']['name']:<16}{z['rk']:>4}{z['h']['agari']:>6.1f}"
                  f"{z['sa']:>+9.2f}{z['exp']:>+10.2f}{z['koi']:>+8.2f}")
        return

    if a.verify:
        H = history(R)
        hit, ctl = [], []
        band_h, band_c = defaultdict(list), defaultdict(list)
        for r in R:
            v, m, tk = koi(r, A)
            if v is None:
                continue
            for z in v:
                nr, nx = next_run(H, z["h"]["name"], r["date"])
                if not nr:
                    continue
                res = (nx["chaku"] == 1, nx["chaku"] <= 3, nx["odds"])
                nk = nx["ninki"] or 99
                bd = "1-2番人気" if nk <= 2 else ("3-5番人気" if nk <= 5 else "6番人気以下")
                ctl.append(res); band_c[bd].append(res)
                # 狙う形：前が楽に残った × 後方 × 濃い脚 × 着外
                if (tk < 0 and z["rel"] >= a.rel and z["koi"] <= a.koi
                        and z["h"]["chaku"] >= 4):
                    hit.append(res); band_h[bd].append(res)
        print("■ 狙う形の次走成績")
        print("   条件：前が楽に残った流れ × 4角後方 × 位置で説明できない脚 × 着外")
        print("  " + tally(hit, "この形だった馬"))
        print("  " + tally(ctl, "対照（全馬の次走）"))
        print("\n■ 次走の人気帯で揃えて比べる")
        print(f"  {'':<14}{'この形':>22}{'対照':>22}")
        for k in ("1-2番人気", "3-5番人気", "6番人気以下"):
            g, c = band_h[k], band_c[k]
            if len(g) < 20:
                continue
            f = lambda v: (sum(1 for x, y, o in v if y) / len(v) * 100,
                           sum((o * 100 if x and o else 0) for x, y, o in v) / len(v))
            gp, gr = f(g); cp, cr = f(c)
            print(f"  {k:<14}3着内{gp:>6.1f}% 回収{gr:>5.0f}% n{len(g):<5}"
                  f"3着内{cp:>6.1f}% 回収{cr:>5.0f}% n{len(c):<6}")


if __name__ == "__main__":
    main()
