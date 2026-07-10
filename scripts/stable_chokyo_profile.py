#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""厩舎の「勝負仕上げの型」プロファイル（調教×結果の結合データから）。

入力: data/samples/chokyo_joined_{tag}.jsonl（chokyo_join_result.py の出力）
考え方: 厩舎ごとに「最終脚色/追い本数」別の好走率(3着内)を出し、
  その厩舎の"勝負シグナル"（好走率がベースを大きく上回るパターン）を検出。
使い方: python3 scripts/stable_chokyo_profile.py --tag urawa
"""
from __future__ import annotations
import argparse, glob, json, os, statistics
from collections import defaultdict, Counter


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--out-dir", default="data/samples")
    ap.add_argument("--min-n", type=int, default=8, help="厩舎×脚色の最小標本")
    ap.add_argument("--min-stable", type=int, default=25, help="厩舎の最小総走破数")
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(os.path.join(args.out_dir, f"chokyo_joined_{args.tag}.jsonl"), encoding="utf-8")]
    rows = [r for r in rows if r.get("好走") is not None]  # 着順取得できた行
    base = sum(1 for r in rows if r["好走"]) / len(rows)
    print(f"■ {args.tag} 厩舎プロファイル（n={len(rows)}走・全体好走率(3着内)={base*100:.1f}%）\n")

    # 厩舎×最終脚色 の好走率
    cell = defaultdict(lambda: [0, 0])  # (厩舎,脚色)->[好走, 総]
    stable_n = Counter()
    for r in rows:
        st = r.get("厩舎"); k = r.get("最終脚色") or "追切無"
        if not st:
            continue
        stable_n[st] += 1
        cell[(st, k)][1] += 1
        if r["好走"]:
            cell[(st, k)][0] += 1

    # 勝負シグナル: 標本十分＆好走率がベースの1.4倍以上
    print("【厩舎の『勝負仕上げシグナル』（好走率がベース比1.4x以上・n>=%d）】" % args.min_n)
    sig = []
    for (st, k), (w, n) in cell.items():
        if n >= args.min_n and stable_n[st] >= args.min_stable:
            rate = w / n
            if rate >= base * 1.4:
                sig.append((rate / base, st, k, w, n, rate))
    for lift, st, k, w, n, rate in sorted(sig, reverse=True)[:20]:
        print(f"  {st:<8} 最終[{k}] → 好走率{rate*100:.0f}% ({w}/{n})  lift {lift:.2f}x")
    if not sig:
        print("  （標本不足。データが増えると出ます）")

    # 追い本数の効き（全体）
    print("\n【追い本数 × 好走率（全体傾向）】")
    hon = defaultdict(lambda: [0, 0])
    for r in rows:
        hon[r["追い本数"]][1] += 1
        if r["好走"]:
            hon[r["追い本数"]][0] += 1
    for h in sorted(hon):
        w, n = hon[h]
        print(f"  {h}本: 好走率{w/n*100:.0f}% ({w}/{n})")

    # 最終脚色の効き（全体）
    print("\n【最終脚色 × 好走率（全体傾向）】")
    ky = defaultdict(lambda: [0, 0])
    for r in rows:
        ky[r.get("最終脚色") or "追切無"][1] += 1
        if r["好走"]:
            ky[r.get("最終脚色") or "追切無"][0] += 1
    for k, (w, n) in sorted(ky.items(), key=lambda x: -x[1][0] / max(1, x[1][1])):
        print(f"  {k:<5}: 好走率{w/n*100:.0f}% ({w}/{n})")

    # 人気薄×好走(調教で拾える穴) の抽出例
    print("\n【人気薄(6人気↓)で好走した馬の調教（穴の型サンプル）】")
    ana = [r for r in rows if r.get("人気") and r["人気"] >= 6 and r["好走"]]
    for r in sorted(ana, key=lambda x: -x["人気"])[:12]:
        print(f"  {r['date']} {r['race_no']}R {r['人気']}人 {r['馬名']}({r.get('厩舎')}) "
              f"最終[{r['最終脚色']}] 追{r['追い本数']}本 終い3F{r.get('終い3F')} 総評「{r['総評']}」")


if __name__ == "__main__":
    main()
