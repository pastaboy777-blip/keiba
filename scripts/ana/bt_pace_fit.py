#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ズブい馬まわりの2つの理論を南関で測る。

★ユーザーの明示的な指示で回すもの（CLAUDE.mdの検証ルールに従う）。

【③ Sartin / Brohamer：馬ごとに最適なペースがある】
  ズブい馬は自分で加速を作れないので、速い流れに引っ張られたほうが走る。
  逆に切れる馬は緩い流れで待たされたほうがいい。
  ＝ ペースの効き方は馬ごとに符号が違う。だから全体平均ではゼロに見える。
     （実際、南関19,174走の全体では ペース×位置 p=-0.035 とほぼゼロだった）

  測り方: 各馬の【過去走だけ】から
      BT値 ~ β × ペース偏差
  の傾き β を出す。β<0 なら「速い流れで走る馬」＝ズブい側。
  そのうえで【次の1走】で
      (BT − その馬の過去平均BT) ~ c × (β × 今回のペース偏差)
  を回す。c が 1 に近ければ β は本物、0 なら β はただのノイズ。
  ★c そのものが検定になっている。別途プラセボを用意しなくてよい。

【⑤ finishing speed %：自分の平常からの落ち幅で仕上がりを見る】
  FS% = 終い600mの平均速度 ÷ レース全体の平均速度
      = (600 × 走破タイム) ÷ (上がり3F × 距離) × 100
  1頭ごとの実測だけで出る。ただしレースのペースに丸ごと依存するので、
  そのレースの中央値を引いて相対化する（rFS）。
  さらに その馬の過去平均 rFS を引いて 落ち幅 dFS を作る。

  問うのは「dFSが沈んだ次走は巻き返すか」。
  ★dFSと【同じ走】のBT値を比べても意味がない（悪く走れば上がりも落ちる）。
    必ず【次走】を見る。

使い方:
  python3 scripts/ana/bt_pace_fit.py
  python3 scripts/ana/bt_pace_fit.py --min-prior 6
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bt


def build(dfrom="2026-01-01", dto="2026-12-31"):
    """全走を1行ずつに開く。1行 = (日付, 馬名, BT値, ペース偏差, rFS, 馬体重, 4角相対位置)"""
    M = json.load(open(bt.MODEL))
    R = bt.load(dfrom, dto)
    runs = defaultdict(list)
    for r in R:
        pc = bt._pace(r, M)
        if pc is None:
            continue
        pdev = (pc - 1.0) / bt.PACE_SIG                     # 正＝スロー、負＝ハイ（σ単位）
        fs = {}
        for h in r["rows"]:
            if h["t"] and h["agari"] and h["agari"] > 0:
                fs[h["name"]] = 600.0 * h["t"] / (h["agari"] * r["dist"]) * 100
        if len(fs) < 4:
            continue
        med = st.median(fs.values())                        # レース内で相対化＝流れの影響を抜く
        for h in r["rows"]:
            b = bt.bt_of(r, h, M)
            if not b or h["name"] not in fs:
                continue
            pos = (r.get("rk") or {}).get(h["ub"])
            rel = ((pos - 1) / (r["n"] - 1)) if pos and r["n"] > 1 else None
            runs[h["name"]].append(dict(
                date=r["date"], bt=b[0], pdev=pdev, rfs=fs[h["name"]] - med,
                weight=h["weight"], rel=rel, chaku=h["chaku"], dist=r["dist"]))
    for v in runs.values():
        v.sort(key=lambda z: z["date"])
    return runs


def slope(xs, ys):
    """単回帰の傾き。xの分散がなければ None。"""
    n = len(xs)
    if n < 3:
        return None
    mx, my = st.mean(xs), st.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx < 1e-9:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx


def bucket(rows, keyf, edges, names):
    out = defaultdict(list)
    for r in rows:
        k = keyf(r)
        if k is None:
            continue
        i = sum(1 for e in edges if k > e)
        out[names[i]].append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-prior", type=int, default=5, help="βや平常値を作るのに要る過去走数")
    a = ap.parse_args()
    runs = build()
    print(f"■ 南関 {sum(len(v) for v in runs.values()):,}走 / {len(runs):,}頭"
          f"（過去{a.min_prior}走以上ある馬だけを使う）\n")

    # ---------------- ③ ペース適性 ----------------
    print("=" * 78)
    print("③ 馬ごとに最適なペースがあるか（Sartin/Brohamer）")
    print("=" * 78)
    rows = []
    for nm, v in runs.items():
        for i in range(a.min_prior, len(v)):
            pri = v[:i]
            b = slope([p["pdev"] for p in pri], [p["bt"] for p in pri])
            if b is None:
                continue
            base = st.mean(p["bt"] for p in pri)
            rows.append(dict(name=nm, beta=b, x=b * v[i]["pdev"],
                             y=v[i]["bt"] - base, w=v[i]["weight"],
                             pdev=v[i]["pdev"]))
    if len(rows) < 200:
        print("  データ不足")
    else:
        c = slope([r["x"] for r in rows], [r["y"] for r in rows])
        bs = sorted(r["beta"] for r in rows)
        print(f"  βの分布 {len(rows):,}走  中央{st.median(bs):+.3f}  "
              f"5%tile{bs[len(bs)//20]:+.2f}  95%tile{bs[-len(bs)//20]:+.2f}")
        print(f"  β<0（速い流れで走る側）{sum(1 for x in bs if x < 0)/len(bs)*100:.0f}%")
        print()
        print(f"  ★次走での検証   c = {c:+.3f}")
        print("     c≒1 … βは本物（馬ごとに最適な流れがある）")
        print("     c≒0 … βはただのノイズ（過去のブレを拾っただけ）")
        # 馬体重別。ズブい＝大型、という読みが正しいか
        print("\n  馬体重別のβ中央値（負ほど『速い流れで走る』側）")
        bw = bucket(rows, lambda r: r["w"], [440, 470, 500], ["〜440k", "440-470k", "470-500k", "500k〜"])
        for k in ("〜440k", "440-470k", "470-500k", "500k〜"):
            v = bw.get(k, [])
            if len(v) >= 100:
                print(f"    {k:<10} n{len(v):>5}  β中央 {st.median(r['beta'] for r in v):+.3f}")

    # ---------------- ⑤ finishing speed % ----------------
    print()
    print("=" * 78)
    print("⑤ 上がりの落ち幅（finishing speed %）が沈んだ次走は巻き返すか")
    print("=" * 78)
    rows = []
    for nm, v in runs.items():
        for i in range(a.min_prior, len(v) - 1):
            pri = v[:i]
            base_f = st.mean(p["rfs"] for p in pri)
            base_b = st.mean(p["bt"] for p in pri)
            rows.append(dict(dfs=v[i]["rfs"] - base_f,          # 今走の落ち幅
                             now=v[i]["bt"] - base_b,           # 今走のBT（参考）
                             nxt=v[i + 1]["bt"] - base_b,       # ★次走のBT
                             nchaku=v[i + 1]["chaku"]))
    if len(rows) < 200:
        print("  データ不足")
        return
    print(f"  {len(rows):,}走ぶん\n")
    print(f"  {'落ち幅 dFS':<14}{'n':>6}{'今走BT差':>10}{'次走BT差':>10}{'次走3着内':>10}")
    bk = bucket(rows, lambda r: r["dfs"], [-2.0, -0.7, 0.7, 2.0],
                ["-2.0未満(大きく落ちた)", "-2.0〜-0.7", "-0.7〜+0.7(平常)",
                 "+0.7〜+2.0", "+2.0超(伸びた)"])
    for k in ("-2.0未満(大きく落ちた)", "-2.0〜-0.7", "-0.7〜+0.7(平常)", "+0.7〜+2.0", "+2.0超(伸びた)"):
        v = bk.get(k, [])
        if len(v) < 50:
            continue
        p3 = sum(1 for r in v if r["nchaku"] <= 3) / len(v) * 100
        print(f"  {k:<20}{len(v):>6}{st.mean(r['now'] for r in v):>+10.1f}"
              f"{st.mean(r['nxt'] for r in v):>+10.1f}{p3:>9.1f}%")
    c = slope([r["dfs"] for r in rows], [r["nxt"] for r in rows])
    print(f"\n  ★次走BT差 ~ dFS の傾き {c:+.3f}")
    print("     負なら「落ちた次走ほど巻き返す」／正なら「落ちた次走も落ちたまま」")


if __name__ == "__main__":
    main()
