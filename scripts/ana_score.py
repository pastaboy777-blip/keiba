#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""穴スコア：人気薄好走の型（厩舎×調教内容×追い間隔×遠征下地）を1本に合成。

設計（2026-07-11の実証に基づく透明な加点式）:
  買い材料
    ・厩舎の穴力（その厩舎の人気薄好走率 vs 基準）        … 最強の軸
    ・終い3Fが速い(≤37.5)                              … 微プラス
    ・総評ポジ(符号≥1)                                  … 微プラス
    ・船橋遠征馬で船橋下地(自己終い3F)が速い(≤38.0)       … プラス（船橋のみ効く）
  消し材料
    ・追切無(0本)                                       … 消し
    ・直前追い(最終追い≤3日前)                          … 強力な消し
    ・船橋遠征で下地が遅い(≥39.1)                        … マイナス

使い方: python3 scripts/ana_score.py            # 浦和人気薄でバックテスト
       関数 score_row() を予想スクリプトから import して各馬採点にも使える。
"""
from __future__ import annotations
import json, os, statistics
from collections import defaultdict

DATA = "data/samples"
POOL_TAGS = ["urawa", "funabashi", "oi", "kawasaki"]


def load_pool():
    rows = []
    for tag in POOL_TAGS:
        p = os.path.join(DATA, f"chokyo_joined_{tag}.jsonl")
        if os.path.exists(p):
            for l in open(p, encoding="utf-8"):
                rows.append(json.loads(l))
    return [r for r in rows if r.get("好走") is not None]


def stable_ana_rate(rows, min_n=12):
    """厩舎→人気薄(6人気↓)好走率。標本min_n未満はNone（=基準扱い）。"""
    st = defaultdict(lambda: [0, 0])
    for r in rows:
        if r.get("厩舎") and r.get("人気") and r["人気"] >= 6:
            st[r["厩舎"]][1] += 1
            if r["好走"]:
                st[r["厩舎"]][0] += 1
    return {s: (w / n) for s, (w, n) in st.items() if n >= min_n}


def funabashi_baseline():
    """umacd→船橋の自己終い3F中央（遠征下地）。"""
    p = os.path.join(DATA, "chokyo_byhorse_funabashi.json")
    if not os.path.exists(p):
        return {}
    bh = json.load(open(p, encoding="utf-8"))
    out = {}
    for cd, hist in bh.items():
        ts = [h["終い3F"] for h in hist if h.get("終い3F")]
        if ts:
            out[cd] = statistics.median(ts)
    return out


def score_row(r, stable_rate, funa_med, ana_base=0.11):
    """1頭の穴スコアと内訳を返す。row は joined+最終追い何日前 を含む dict。"""
    pts = 0.0
    br = []
    # ① 厩舎の穴力（基準比のリフトで段階加点）
    sr = stable_rate.get(r.get("厩舎"))
    if sr is not None:
        lift = sr / ana_base
        add = 3 if lift >= 2.2 else 2 if lift >= 1.6 else 1 if lift >= 1.2 else 0 if lift >= 0.8 else -1
        if add:
            pts += add; br.append(f"厩舎{r.get('厩舎')}({sr*100:.0f}%){add:+d}")
    # ② 追い間隔（直前追い＝強力な消し）
    g = r.get("最終追い何日前")
    if g is not None:
        if g <= 3:
            pts -= 3; br.append(f"直前追い{g}日-3")
        elif 4 <= g <= 7:
            pts += 1; br.append("一週前+1")
    # ③ 追切無＝消し
    if r.get("追切無"):
        pts -= 2; br.append("追切無-2")
    # ④ 終い3F 速い
    t3 = r.get("終い3F")
    if t3 is not None:
        if t3 <= 37.5:
            pts += 1; br.append("終い速+1")
        elif t3 >= 39.6:
            pts -= 0.5; br.append("終い遅-0.5")
    # ⑤ 総評ポジ/ネガ
    s = r.get("総評符号", 0)
    if s >= 1:
        pts += 1; br.append("総評ポジ+1")
    elif s <= -1:
        pts -= 0.5; br.append("総評ネガ-0.5")
    # ⑥ 船橋遠征の下地（船橋履歴がある馬のみ）
    m = funa_med.get(r.get("umacd"))
    if m is not None:
        if m <= 38.0:
            pts += 2; br.append(f"船橋下地速{m:.1f}+2")
        elif m >= 39.1:
            pts -= 1; br.append(f"船橋下地遅{m:.1f}-1")
    return round(pts, 1), br


def main():
    pool = load_pool()
    stable_rate = stable_ana_rate(pool)
    funa_med = funabashi_baseline()

    # バックテスト：浦和の人気薄で スコア帯 × 好走率
    tidy = {(r["race_id"], r["umaban"]): r.get("最終追い何日前")
            for r in (json.loads(l) for l in open(os.path.join(DATA, "chokyo_tidy_urawa.jsonl"), encoding="utf-8"))}
    ur = [json.loads(l) for l in open(os.path.join(DATA, "chokyo_joined_urawa.jsonl"), encoding="utf-8")]
    for r in ur:
        r["最終追い何日前"] = tidy.get((r["race_id"], r["umaban"]))
    pop = [r for r in ur if r.get("好走") is not None and r.get("人気") and r["人気"] >= 6]
    base = sum(1 for r in pop if r["好走"]) / len(pop)

    for r in pop:
        r["_score"], r["_br"] = score_row(r, stable_rate, funa_med, base)

    def rate(w, n):
        return w / n * 100 if n else 0

    print(f"■ 穴スコア バックテスト（浦和 人気薄 n={len(pop)} / 基準好走率{base*100:.1f}%）\n")
    bands = [("消し帯 ≤-2", lambda s: s <= -2), ("弱 -1.9〜0.9", lambda s: -2 < s < 1),
             ("中 1〜2.9", lambda s: 1 <= s < 3), ("強 3〜4.9", lambda s: 3 <= s < 5),
             ("特強 5+", lambda s: s >= 5)]
    for label, f in bands:
        sub = [r for r in pop if f(r["_score"])]
        w = sum(1 for r in sub if r["好走"])
        n = len(sub)
        lift = (rate(w, n) / (base * 100)) if n else 0
        print(f"  {label:<14} 好走率{rate(w,n):4.0f}% ({w:>3}/{n:<3})  lift{lift:.2f}")

    # 上位スコアの実例（穴的中）
    print("\n【高スコア(≥3)で好走した人気薄の実例】")
    hi = [r for r in pop if r["_score"] >= 3 and r["好走"]]
    for r in sorted(hi, key=lambda x: -x["_score"])[:10]:
        print(f"  {r['date'][4:6]}/{r['date'][6:]} {r['race_no']}R {r['人気']}人 {r['馬名']}({r.get('厩舎')}) "
              f"score{r['_score']} 着{r['着順']}  [{' '.join(r['_br'])}]")


if __name__ == "__main__":
    main()
