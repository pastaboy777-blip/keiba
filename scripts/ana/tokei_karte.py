#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""時計カルテ ── 1頭の時計を「その日その流れの中で」読む。

時計の絶対値は情報を持たない。読めるのは
    ・その日の勝ちタイムとの差
    ・その差がどういう流れの中で作られたか
の2つだけ。それを1頭ぶん並べる道具。

★作るにあたって潰した誤りを2つ、記録として残す（コスモトロイメルの実例）:

  ① 同じ日・同じ距離・同じ馬場でも【クラスが違えば比較にならない】
     8/16大井は 3R 1400m重 勝1:29.8 / 7R 1400m重 勝1:26.5 で3.3秒違ったが、
     3Rは2歳戦、7RはC1の古馬戦だった。差の大半はクラスであって流れではない。
     → 同条件の比較はクラスを揃えたときだけ意味を持つ。

  ② 前3Fの合計は【前が潰れるかどうか】を決めない
     07-23 12.8-11.6-12.1-12.4-12.5-12.3-13.4  前3F 36.5 → 前が残った（③-0.13）7着
     08-16 13.0-11.6-11.7-12.1-12.6-12.4-13.1  前3F 36.3 → 前が潰れた（③+0.75）1着
     前3Fはほぼ同じ。違いは【11秒台が1本か2本か】＝緩んだかどうかだった。
     → 「速い流れ」ではなく「緩まない流れ」を見る。

出す列:
    差      … その日の勝ちタイムとの差（時計の唯一の意味）
    前3F    … 参考。これ単独では潰れるかを決めない
    速本    … 基準ハロンより速いハロンの本数（緩まなさ）
    緩み    … ラップの最大-最小。小さいほど緩まない
    ③      … 4角上位3頭の上がり平均差。＋なら前が止まった／−なら前が楽だった
    ①      … 自分の上がりのレース平均との差

使い方:
    python3 scripts/ana/tokei_karte.py コスモトロイメル
    python3 scripts/ana/tokei_karte.py コスモトロイメル --day     # 同日の他レースも出す
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bt
import agari_sotai as AS

HANPA = 10.0          # これ未満のハロンは半端ハロンとして除く


def shape(r, M):
    """ラップの形。速いハロンの本数と緩み。"""
    L = [x for x in r["laps"] if x >= HANPA]
    if len(L) < 4:
        return None, None, None
    par = bt.par_of(M["all"], r["place"], r["dist"], r["klass"]) if r["klass"] else None
    avg = par / (r["dist"] / 200.0) if par else None
    fast = sum(1 for x in L if avg and x < avg)
    return (fast if avg else None), round(max(L) - min(L), 1), round(sum(r["laps"][:3]), 1)


def main():
    ap = argparse.ArgumentParser(description="1頭の時計をその日の流れの中で読む")
    ap.add_argument("horse")
    ap.add_argument("--day", action="store_true", help="同日・同場の他レースも並べる")
    a = ap.parse_args()

    M = json.load(open(bt.MODEL))
    R = bt.load("2026-01-01", "2026-12-31")
    A = AS.calib(R)
    mine = []
    for r in sorted(R, key=lambda z: z["date"]):
        if not any(x["name"] == a.horse for x in r["rows"]):
            continue
        v, m, tk = AS.koi(r, A)
        if v is None:
            continue
        z = next((q for q in v if q["h"]["name"] == a.horse), None)
        if z is None:
            continue
        mine.append((r, z, tk))
    if not mine:
        print("該当なし")
        return

    print(f"■ {a.horse}  {len(mine)}走\n")
    print(f"{'日付':<11}{'条件':<20}{'クラス':<5}{'頭':>3}{'着':>3}{'人':>3}"
          f"{'自分':>7}{'勝ち':>7}{'差':>6}{'前3F':>6}{'速本':>5}{'緩み':>5}"
          f"{'③流れ':>8}{'①上り差':>8}{'4角':>4}")
    for r, z, tk in mine:
        w = min(x["t"] for x in r["rows"] if x["t"])
        fast, sp, t3 = shape(r, M)
        print(f"{r['date']:<11}{r['place']}{r['dist']}m{r['baba']:<8}{(r['klass'] or '?'):<5}"
              f"{r['n']:>3}{z['h']['chaku']:>3}{z['h']['ninki'] or 0:>3}"
              f"{z['h']['t']:>7.1f}{w:>7.1f}{z['h']['t']-w:>+6.1f}"
              f"{(t3 if t3 else 0):>6.1f}{(fast if fast is not None else 0):>5}"
              f"{(sp if sp else 0):>5.1f}{tk:>+8.2f}{z['sa']:>+8.2f}{z['rk']:>4}")

    print("\n  差   … 勝ちタイムとの差。時計の唯一の意味")
    print("  速本 … 基準より速いハロンの本数。緩まなさ。前3Fの合計より効く")
    print("  ③   … ＋なら前が止まった／−なら前が楽に残った")

    # 良かった走と悪かった走で、流れがどう違ったか
    good = [(r, z, tk) for r, z, tk in mine if z["h"]["chaku"] <= 3]
    bad = [(r, z, tk) for r, z, tk in mine if z["h"]["chaku"] >= 6]
    if good and bad:
        f = lambda v, k: st.mean(k(r, z, tk) for r, z, tk in v)
        print(f"\n■ 掲示板({len(good)}走) と 6着以下({len(bad)}走) で何が違ったか")
        for nm, k in (("③ 前の残り方", lambda r, z, tk: tk),
                      ("① 自分の上がり差", lambda r, z, tk: z["sa"]),
                      ("速いハロンの本数", lambda r, z, tk: shape(r, M)[0] or 0),
                      ("ラップの緩み", lambda r, z, tk: shape(r, M)[1] or 0),
                      ("前3F", lambda r, z, tk: shape(r, M)[2] or 0),
                      ("4角の相対位置", lambda r, z, tk: z["rel"])):
            print(f"   {nm:<18} 好走 {f(good,k):>+7.2f}   凡走 {f(bad,k):>+7.2f}   差 {f(good,k)-f(bad,k):>+7.2f}")

    if a.day:
        print("\n■ 各走の同日・同場の他レース（クラスを揃えないと比較にならない）")
        for r, z, tk in mine:
            same = [q for q in R if q["date"] == r["date"] and q["place"] == r["place"]
                    and q["dist"] == r["dist"]]
            if len(same) < 2:
                continue
            print(f"  {r['date']} {r['place']}{r['dist']}m")
            for q in sorted(same, key=lambda y: y["rn"]):
                w = min(x["t"] for x in q["rows"] if x["t"])
                fast, sp, t3 = shape(q, M)
                mk = "★" if q["rn"] == r["rn"] else " "
                print(f"   {mk}{q['rn']:>3}R 【{(q['klass'] or '?'):<4}】{q['baba']:<4}"
                      f"勝{w:>7.1f}  前3F{(t3 or 0):>6.1f}  速{(fast or 0)}本  緩み{(sp or 0):.1f}")


if __name__ == "__main__":
    main()
