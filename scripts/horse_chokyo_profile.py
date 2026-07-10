#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""個体(umacd)プロファイル：馬自身の調教履歴から「自己前走比の上昇」を測る。

考え方（ユーザーの読み）：
  「この馬は前走から今回で脚色が上がった／終い3Fが詰まった＝上昇」を
  厩舎の型ではなく“その馬自身の下地”を物差しにして読む。
  → 個体の中央値(終い3F・総評符号)を基準に、今走が自己ベース比でどうか。

入力: data/samples/chokyo_joined_{tag}.jsonl（chokyo_join_result.py の出力）
出力: data/samples/chokyo_horse_{tag}.json（umacd→個体プロファイル＋各走の自己比フラグ）
検証: 「終い3Fが自己前走より詰まった」「総評符号↑」等が好走(3着内)に効くか。
使い方: python3 scripts/horse_chokyo_profile.py --tag urawa
"""
from __future__ import annotations
import argparse, json, os, statistics
from collections import defaultdict

# 脚色の負荷スケール（軽 → 強）。個体の「今回どれだけ追ったか」を数値化。
_KYAKU = {"馬なり": 0, "馬也": 0, "直強め": 1, "末強め": 2, "強め": 3, "一杯": 4}


def kyaku_load(k: str):
    return _KYAKU.get((k or "").strip())


def rate(w, n):
    return (w / n * 100) if n else 0.0


def bucket_report(title, rows, keyfn):
    """keyfn(今走row, 前走row)->ラベル別に好走率を出す。"""
    cell = defaultdict(lambda: [0, 0])
    for cur, prev in rows:
        lab = keyfn(cur, prev)
        if lab is None:
            continue
        cell[lab][1] += 1
        if cur["好走"]:
            cell[lab][0] += 1
    print(f"\n【{title}】")
    for lab, (w, n) in sorted(cell.items(), key=lambda x: -rate(*x[1])):
        print(f"  {lab:<16} 好走率{rate(w,n):4.0f}% ({w}/{n})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--out-dir", default="data/samples")
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(os.path.join(args.out_dir, f"chokyo_joined_{args.tag}.jsonl"), encoding="utf-8")]
    rows = [r for r in rows if r.get("好走") is not None and r.get("umacd")]
    base = rate(sum(1 for r in rows if r["好走"]), len(rows)) / 100

    by = defaultdict(list)
    for r in rows:
        by[r["umacd"]].append(r)
    for cd in by:
        by[cd].sort(key=lambda x: (x.get("date") or "", x.get("race_no") or 0))

    # 各馬の自己ベース（過去走の中央値）と、今走の自己比を注記
    pairs = []  # (今走, 前走) 連続ペア
    prof = {}   # umacd -> プロファイル
    for cd, hist in by.items():
        t3 = [h["終い3F"] for h in hist if h.get("終い3F")]
        sign = [h.get("総評符号", 0) for h in hist]
        prof[cd] = {
            "馬名": hist[-1]["馬名"], "走数": len(hist),
            "終い3F自己中央": round(statistics.median(t3), 1) if t3 else None,
            "終い3F自己速": min(t3) if t3 else None,
            "総評符号中央": statistics.median(sign) if sign else 0,
            "厩舎": hist[-1].get("厩舎"),
            "履歴": [{"date": h["date"], "race_no": h["race_no"], "脚色": h["最終脚色"],
                      "追": h["追い本数"], "終3F": h.get("終い3F"), "符号": h.get("総評符号"),
                      "着": h.get("着順"), "人気": h.get("人気")} for h in hist],
        }
        for i in range(1, len(hist)):
            pairs.append((hist[i], hist[i - 1]))

    n_multi = sum(1 for v in by.values() if len(v) >= 2)
    print(f"■ {args.tag} 個体(umacd)プロファイル  n走={len(rows)} / ユニーク馬={len(by)}")
    print(f"  連続2走以上={n_multi}頭 / 前走比が取れる今走={len(pairs)}走 / 全体好走率(3着内)={base*100:.1f}%")

    # 1) 終い3F：自己前走比で詰まった/伸びた
    def t3_delta(cur, prev):
        a, b = cur.get("終い3F"), prev.get("終い3F")
        if a is None or b is None:
            return None
        d = a - b
        if d <= -0.5:
            return "詰まった(-0.5↑速)"
        if d >= 0.5:
            return "遅くなった(+0.5↑)"
        return "ほぼ同じ(±0.5)"
    bucket_report("終い3F：自己前走比（詰まり＝時計が速くなった）", pairs, t3_delta)

    # 2) 脚色：自己前走比で負荷が上/下（追われ方の変化＝厩舎の勝負度）
    def ky_delta(cur, prev):
        a, b = kyaku_load(cur.get("最終脚色")), kyaku_load(prev.get("最終脚色"))
        if a is None or b is None:
            return None
        if a > b:
            return "強くなった(追った)"
        if a < b:
            return "楽になった(緩めた)"
        return "同じ"
    bucket_report("最終脚色：自己前走比（負荷アップ/ダウン）", pairs, ky_delta)

    # 3) 総評符号：自己前走比でポジ方向へ
    def sign_delta(cur, prev):
        d = (cur.get("総評符号", 0)) - (prev.get("総評符号", 0))
        if d > 0:
            return "好転(符号↑)"
        if d < 0:
            return "悪化(符号↓)"
        return "変わらず"
    bucket_report("総評符号：自己前走比", pairs, sign_delta)

    # 4) 追い本数：自己前走比
    def hon_delta(cur, prev):
        d = cur["追い本数"] - prev["追い本数"]
        if d > 0:
            return "増やした"
        if d < 0:
            return "減らした"
        return "同じ"
    bucket_report("追い本数：自己前走比", pairs, hon_delta)

    # 5) 複合サイン：終い詰まり かつ 符号好転（＝個体の上昇シグナル）
    def combo(cur, prev):
        t = t3_delta(cur, prev)
        s = sign_delta(cur, prev)
        if t is None:
            return None
        up_t = t.startswith("詰まった")
        up_s = s.startswith("好転")
        if up_t and up_s:
            return "◎ 詰まり＆好転"
        if up_t or up_s:
            return "○ どちらか上昇"
        return "無印"
    bucket_report("個体・上昇シグナル（終い詰まり＋総評好転）", pairs, combo)

    # 6) 人気薄×個体上昇（穴の実サンプル）
    print("\n【人気薄(6人気↓)×個体上昇シグナルで好走した実例】")
    ex = []
    for cur, prev in pairs:
        if cur.get("人気") and cur["人気"] >= 6 and cur["好走"] and combo(cur, prev) == "◎ 詰まり＆好転":
            ex.append((cur, prev))
    for cur, prev in sorted(ex, key=lambda x: -x[0]["人気"])[:12]:
        print(f"  {cur['date']} {cur['race_no']}R {cur['人気']}人 {cur['馬名']}({cur.get('厩舎')}) "
              f"終3F {prev.get('終い3F')}→{cur.get('終い3F')} 符号 {prev.get('総評符号')}→{cur.get('総評符号')} 着{cur.get('着順')}")
    if not ex:
        print("  （該当なし。データ増で出ます）")

    out = os.path.join(args.out_dir, f"chokyo_horse_{args.tag}.json")
    json.dump(prof, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"\n  → 個体プロファイル {len(prof)}頭 保存: {out}")


if __name__ == "__main__":
    main()
