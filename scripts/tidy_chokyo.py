#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""調教データを分析レディに整える（フラット化＋派生項目＋個体index＋品質レポート）。

入力: data/samples/keibabook_chokyo_{tag}_*.jsonl（collect_keibabook_chokyo.py の出力）
出力:
  data/samples/chokyo_tidy_{tag}.jsonl   … 1行=1馬×1レース（派生項目つき・楽天結果と結合しやすい平坦形）
  data/samples/chokyo_byhorse_{tag}.json … umacd→その馬の調教履歴（個体プロファイル用）
使い方: python3 scripts/tidy_chokyo.py --tag urawa
"""
from __future__ import annotations
import argparse, glob, json, os, re, statistics
from collections import Counter, defaultdict

_POS = ("仕上が", "上昇", "絞れ", "良化", "気配良", "上々", "文句な", "抜群", "デキ良", "態勢")
_NEG = ("変わり身無", "太", "一息", "平凡", "物足", "余裕", "案外", "イマイチ", "ズブ", "重")


def _num(xs):
    return [float(x) for x in xs if re.fullmatch(r"\d{2,3}\.\d", x)]


def flatten_horse(rec: dict, h: dict) -> dict:
    oi = h.get("追切") or []
    last = oi[-1] if oi else {}
    ltimes = _num(last.get("時計", []))
    txt = (h.get("総評", "") + " " + " ".join(w.get("短評", "") for w in oi))
    pos = sum(1 for w in _POS if w in txt)
    neg = sum(1 for w in _NEG if w in txt)
    return {
        "date": rec.get("date"), "place": rec.get("place"), "race_no": rec.get("race_no"),
        "race_id": rec.get("race_id"), "umaban": h.get("馬番"), "umacd": h.get("umacd"),
        "馬名": h.get("馬名"), "総評": h.get("総評", ""),
        "追い本数": len(oi),
        "最終脚色": last.get("脚色", ""), "最終コース": last.get("コース", ""),
        "最終馬場": last.get("馬場", ""),
        "終い3F": (min([x for x in ltimes if 35 <= x <= 45]) or None) if any(35 <= x <= 45 for x in ltimes) else None,
        "終い1F": (min([x for x in ltimes if 11 <= x <= 16]) or None) if any(11 <= x <= 16 for x in ltimes) else None,
        "最終時計": last.get("時計", []),
        "脚色列": [w.get("脚色", "") for w in oi],
        "総評符号": pos - neg,
        "追切無": len(oi) == 0,
        "仕上がり": h.get("仕上がり"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="調教データ整備")
    ap.add_argument("--tag", required=True, help="収集時の--tag（例: urawa）")
    ap.add_argument("--out-dir", default="data/samples")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.out_dir, f"keibabook_chokyo_{args.tag}_*.jsonl")))
    if not files:
        raise SystemExit(f"入力なし: keibabook_chokyo_{args.tag}_*.jsonl")

    rows, seen = [], set()
    for f in files:
        for line in open(f, encoding="utf-8"):
            rec = json.loads(line)
            for h in rec.get("horses", []):
                key = (rec.get("race_id"), h.get("馬番"))
                if key in seen:
                    continue
                seen.add(key)
                rows.append(flatten_horse(rec, h))

    tidy_path = os.path.join(args.out_dir, f"chokyo_tidy_{args.tag}.jsonl")
    with open(tidy_path, "w", encoding="utf-8") as w:
        for r in rows:
            w.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 個体index: umacd→履歴（日付順）
    byhorse = defaultdict(list)
    for r in rows:
        if r.get("umacd"):
            byhorse[r["umacd"]].append(r)
    for cd in byhorse:
        byhorse[cd].sort(key=lambda x: x.get("date") or "")
    bh_path = os.path.join(args.out_dir, f"chokyo_byhorse_{args.tag}.json")
    json.dump(byhorse, open(bh_path, "w", encoding="utf-8"), ensure_ascii=False)

    # 品質レポート
    n = len(rows)
    with_oi = sum(1 for r in rows if not r["追切無"])
    with_cd = sum(1 for r in rows if r.get("umacd"))
    kyaku = Counter(r["最終脚色"] for r in rows if r["最終脚色"])
    honsu = Counter(r["追い本数"] for r in rows)
    multi = sum(1 for cd, v in byhorse.items() if len(v) >= 2)
    st = [r["終い3F"] for r in rows if r["終い3F"]]
    print(f"■ 整備完了 tag={args.tag}")
    print(f"  行(馬×レース) {n} / 調教有 {with_oi}({with_oi/n*100:.0f}%) / umacd有 {with_cd}({with_cd/n*100:.0f}%)")
    print(f"  ユニーク馬 {len(byhorse)} / うち2走以上(個体型が作れる) {multi}")
    print(f"  最終脚色: {dict(kyaku.most_common())}")
    print(f"  追い本数分布: {dict(sorted(honsu.items()))}")
    if st:
        print(f"  終い3F: 中央{statistics.median(st):.1f} 平均{statistics.mean(st):.1f} 速い{min(st):.1f} (n={len(st)})")
    print(f"  → {tidy_path}")
    print(f"  → {bh_path}")


if __name__ == "__main__":
    main()
