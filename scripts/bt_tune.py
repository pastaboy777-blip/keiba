#!/usr/bin/env python3
"""BT値の補正パラメータを **条件をまたいだ一致度** で詰める。

    python3 scripts/bt_tune.py                 # 現状の性能を測る
    python3 scripts/bt_tune.py --grid          # ペース補正のパラメータを探索

⚠️⚠️ **split-half（同じ馬で値が安定するか）で決めてはいけない。**
   無補正の素の時計でも r=+0.848 出るので、補正の良し悪しを判別できない。
   実測:  素0.848 → 基準差0.862 → ＋斤量年齢0.871 → 全補正0.877
   §32 の「毎日当たる予測は当たっても何も言っていない」と同じ。

**補正の仕事は「条件をまたいで比べられること」**なので、同じ馬が違う条件で
走ったときに値がどれだけ一致するかで測る。

⚠️⚠️ **ただし一致度で「係数」を決めてはいけない。**相関は馬の間の広がりが
   増えるだけで上がる。実際、斤量係数を実測の4倍にすると残差が
   +0.75 BT点/kg も残る（明確な効かせすぎ）のに、場をまたいだ一致度は
   0.798 → 0.815 と**上がった**。牝馬が2kg軽いので、係数を大きくすると
   牡牝の差が広がり、馬の間のばらつきが増えるから。
   **係数は「補正後にその変数の効果が0になるか」（残差）で決めること。**
   一致度は補正を「入れるか入れないか」の判断にだけ使う。

⚠️ **回収率でチューニングしない**（恒久ルール5）。ここでやっているのは
   「同じ馬なら同じ値が出るべき」という測定器としての性質の確認であって、
   馬券の成績とは無関係。
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import statistics as st
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import bt                             # noqa: E402

RUNS = "data/bt/runs.jsonl"
BASE = "data/bt/base.json"


def corr(a, b) -> float:
    if len(a) < 3:
        return 0.0
    ma, mb = st.mean(a), st.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return num / den if den else 0.0


def load():
    rows = [json.loads(l) for l in open(RUNS, encoding="utf-8")]
    B = bt.BaseTime.load(BASE)
    day = collections.defaultdict(list)
    for r in rows:
        day[(r["date"], r["place"])].append(r)
    ratio = {k: bt.day_ratio(v, B) for k, v in day.items()}
    return rows, B, ratio


def scored(rows, B, ratio, **kw):
    out = []
    for r in rows:
        s = bt.score(r, B, ratio[(r["date"], r["place"])], **kw)
        if s:
            out.append((r, s.bt))
    return out


def cross(pairs, keyfn, minruns=3) -> tuple[float, int]:
    """同じ馬の、条件Aでの平均と条件Bでの平均を突き合わせる。"""
    g = collections.defaultdict(lambda: collections.defaultdict(list))
    for r, v in pairs:
        k = keyfn(r)
        if k is not None:
            g[r["name"]][k].append(v)
    A, Bb = [], []
    for d in g.values():
        ok = sorted(k for k, L in d.items() if len(L) >= minruns)
        if len(ok) < 2:
            continue
        A.append(st.mean(d[ok[0]]))
        Bb.append(st.mean(d[ok[1]]))
    return corr(A, Bb), len(A)


def bias(pairs, keyfn, ref, other, minruns=2) -> tuple[float, int]:
    """同じ馬の中での**系統的なズレ**。0なら偏りなし。

    ⚠️ **偏りを消す補正は相関では測れない。**各群に定数を足すだけの補正は
       相関をほとんど動かさない（馬場状態補正で 0.878→0.879 しか動かず、
       効果なしと誤判定しかけた）。実際は偏りが −2.36 → −0.00 に消えていた。
    """
    g = collections.defaultdict(lambda: collections.defaultdict(list))
    for r, v in pairs:
        k = keyfn(r)
        if k is not None:
            g[r["name"]][k].append(v)
    d = [st.mean(v[other]) - st.mean(v[ref]) for v in g.values()
         if len(v.get(other, [])) >= minruns and len(v.get(ref, [])) >= minruns]
    return (st.median(d) if d else float("nan")), len(d)


def pace_shape(r, B):
    """ペース形状。**マイナスがハイペース**。上がり水準で切らないこと。"""
    bw, bl, _ = B.unified(r["place"], r["distance"])
    if not bw:
        return None
    d = bt.pace_dev(r, bw, bl)
    if d is None:
        return None
    return "ハイ" if d < -0.03 else "スロー" if d > 0.0 else None


def pace_bucket(r, B):
    """そのレースが瞬発戦か消耗戦か。基準の上がりと比べる。"""
    bw, bl, _ = B.unified(r["place"], r["distance"])
    rl = r.get("last3f_race")
    if not bl or not rl:
        return None
    if rl < bl - 0.5:
        return "瞬発"
    if rl > bl + 0.5:
        return "消耗"
    return None


def report(rows, B, ratio, label, **kw):
    pairs = scored(rows, B, ratio, **kw)
    r1, n1 = cross(pairs, lambda r: r["place"])
    r2, n2 = cross(pairs, lambda r: "短" if r["distance"] <= 1300
                   else "長" if r["distance"] >= 1500 else None)
    r3, n3 = cross(pairs, lambda r: "良" if (r.get("baba") or "").startswith("良")
                   else "非良")
    r4, n4 = cross(pairs, lambda r: pace_bucket(r, B))
    # 3着内馬のBT値がペースでどれだけ偏るか（0に近いほどよい）
    g = collections.defaultdict(list)
    for r, v in pairs:
        if r.get("finish") and r["finish"] <= 3:
            k = pace_bucket(r, B)
            if k:
                g[k].append(v)
    b_wet, nw = bias(pairs, lambda r: bt.norm_baba(r.get("baba")), "良", "不")
    b_pace, np_ = bias(pairs, lambda r: pace_shape(r, B), "ハイ", "スロー", minruns=3)
    print(f"  {label:<20} 一致度 場{r1:+.3f} 距離{r2:+.3f} 馬場{r3:+.3f} ペース{r4:+.3f}"
          f"   偏り 不良{b_wet:+.2f}点(n={nw}) スロー{b_pace:+.2f}点(n={np_})")
    return r1, r2, r3, r4, b_pace


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", action="store_true")
    args = ap.parse_args()
    rows, B, ratio = load()
    print(f"{len(rows)}走 / 基準{len(B.win)}マス\n")
    print("◆ 条件をまたいだ一致度（同じ馬が違う条件で走ったとき値が合うか）")
    report(rows, B, ratio, "補正なし", pace=False, baba=False)
    report(rows, B, ratio, "＋馬場状態のみ", pace=False, baba=True)
    report(rows, B, ratio, "＋ペースのみ", pace=True, baba=False)
    report(rows, B, ratio, "全補正", pace=True, baba=True)

    if args.grid:
        print("\n◆ ペース補正の探索（目的＝ペースをまたいだ一致度）")
        best = None
        for k in (2.0, 3.0, 4.0, 6.0, 8.0):
            for mx in (0.25, 0.35, 0.45, 0.60):
                bt.BLEND_K, bt.BLEND_MAX = k, mx
                res = report(rows, B, ratio, f"K={k} MAX={mx}")
                if best is None or res[3] > best[0]:
                    best = (res[3], k, mx, res)
        print(f"\n  最良: K={best[1]} MAX={best[2]}  ペース一致度 {best[0]:+.3f}")


if __name__ == "__main__":
    main()
