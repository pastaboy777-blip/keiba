#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""穴で来る騎手テーブル.

各馬の recent_runs（実人気・実着順つき過去走）を母集団に、
「人気薄に乗ったとき、どれだけ馬券圏に持ってくる騎手か」を測る。

想定人気(exp_pop)ではなく実人気(popularity)を使う点がキモ。
出力は 6人気以下・頭数8以上に絞った複勝率ランキングと、
全体ベースラインに対する lift（倍率）。

使い方:
  python3 scripts/jockey_ana.py                  # 南関4場・6人気以下
  python3 scripts/jockey_ana.py --place 大井      # 大井だけ
  python3 scripts/jockey_ana.py --pop-min 8       # 8人気以下の激穴限定
  python3 scripts/jockey_ana.py --min-n 30        # 標本30走以上の騎手のみ
  python3 scripts/jockey_ana.py --baba 重,不,稍   # 道悪だけ
"""
import argparse
import glob
import json
import re

NANKAN = {"船橋", "大井", "川崎", "浦和"}
# 見習い斤量マーク等の接頭辞を除去して騎手名を正規化
_MARK = re.compile(r"^[▲☆★◇◎△▽○◆□■※・\s]+")


def norm_jockey(name):
    if not name:
        return None
    return _MARK.sub("", name).strip()


def iter_runs(files):
    """dedup 済みの過去走を1件ずつ yield。"""
    seen = set()
    for f in files:
        try:
            fh = open(f, encoding="utf-8")
        except FileNotFoundError:
            continue
        for line in fh:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            for h in rec.get("horses", []):
                hid = h.get("horse_id")
                for rr in h.get("recent_runs", []):
                    key = (hid, rr.get("date"), rr.get("place"), rr.get("distance"))
                    if key in seen:
                        continue
                    seen.add(key)
                    yield rr


def dist_band(d):
    if d is None:
        return "?"
    if d <= 1200:
        return "〜1200"
    if d <= 1400:
        return "1300-1400"
    if d <= 1600:
        return "1500-1600"
    if d <= 1800:
        return "1700-1800"
    return "1900+"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", default=None,
                    help="カンマ区切りのjsonl。既定は南関サンプル+浦和")
    ap.add_argument("--place", default=None, help="場を1つに絞る（例: 大井）")
    ap.add_argument("--pop-min", type=int, default=6, help="この人気以下を穴とみなす")
    ap.add_argument("--field-min", type=int, default=8, help="この頭数以上のレースのみ")
    ap.add_argument("--min-n", type=int, default=20, help="ランキング表示の最低標本数")
    ap.add_argument("--baba", default=None, help="馬場フィルタ。例: 重,不,稍")
    ap.add_argument("--top", type=int, default=30, help="表示件数")
    args = ap.parse_args()

    if args.files:
        files = args.files.split(",")
    else:
        files = sorted(glob.glob("data/samples/nankan_2026-0*.jsonl"))
        files += ["data/samples/urawa_2025-06_2026-05.jsonl"]

    places = {args.place} if args.place else NANKAN
    baba_set = set(args.baba.split(",")) if args.baba else None

    # 集計
    jk = {}          # jockey -> dict
    base_n = base_t = base_w = 0  # 穴全体ベースライン

    for rr in iter_runs(files):
        if rr.get("place") not in places:
            continue
        fs = rr.get("field_size")
        if not fs or fs < args.field_min:
            continue
        pop = rr.get("popularity")
        if pop is None or pop < args.pop_min:
            continue
        if baba_set and rr.get("baba") not in baba_set:
            continue
        fp = rr.get("finish_pos")
        if fp is None:
            continue  # 取消・中止等
        j = norm_jockey(rr.get("jockey"))
        if not j:
            continue
        d = jk.setdefault(j, {"n": 0, "t3": 0, "w": 0, "band": {}})
        d["n"] += 1
        base_n += 1
        top3 = fp <= 3
        win = fp == 1
        if top3:
            d["t3"] += 1
            base_t += 1
        if win:
            d["w"] += 1
            base_w += 1
        b = d["band"].setdefault(dist_band(rr.get("distance")),
                                 {"n": 0, "t3": 0})
        b["n"] += 1
        if top3:
            b["t3"] += 1

    if base_n == 0:
        print("該当データなし")
        return
    base_rate = base_t / base_n
    base_win = base_w / base_n

    scope = args.place if args.place else "南関4場"
    babas = args.baba if args.baba else "全馬場"
    print(f"■ 穴で来る騎手  [{scope} / {args.pop_min}人気以下 / {args.field_min}頭立て以上 / {babas}]")
    print(f"  母集団 {base_n:,}走  複勝率ベースライン {base_rate*100:.1f}%  勝率 {base_win*100:.1f}%")
    print(f"  (標本{args.min_n}走以上の騎手のみ / 複勝率順)")
    print()
    hdr = f"{'騎手':<8}{'標本':>5}{'複勝率':>8}{'勝率':>7}{'lift':>7}   得意距離帯"
    print(hdr)
    print("-" * len(hdr) + "----------")

    rows = []
    for j, d in jk.items():
        if d["n"] < args.min_n:
            continue
        rate = d["t3"] / d["n"]
        win = d["w"] / d["n"]
        lift = rate / base_rate if base_rate else 0
        # 得意距離帯: 標本8走以上で複勝率が高い順に1つ
        best = None
        for band, bd in d["band"].items():
            if bd["n"] >= 8:
                br = bd["t3"] / bd["n"]
                if best is None or br > best[1]:
                    best = (band, br, bd["n"])
        rows.append((rate, win, lift, j, d, best))

    rows.sort(key=lambda x: (-x[0], -x[3].__len__()))
    for rate, win, lift, j, d, best in rows[:args.top]:
        flag = " 🔥" if lift >= 1.3 and d["n"] >= 30 else ""
        bstr = ""
        if best:
            bstr = f"{best[0]}({best[1]*100:.0f}%/{best[2]})"
        print(f"{j:<8}{d['n']:>5}{rate*100:>7.1f}%{win*100:>6.1f}%{lift:>6.2f}x   {bstr}{flag}")

    print()
    print("🔥 = lift1.3倍以上 & 標本30走以上（穴で明確に信頼できる騎手）")


if __name__ == "__main__":
    main()
