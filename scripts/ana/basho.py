#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""【場所と間隔】前走の競馬場と、そこからの週数を数える。

★もとは中島理論の「磁場」として書いた道具。2026-09-20 に言い換えた。
    中島氏は「経度差2度以内なら同じ磁場」「移動後7週で元の磁場が切れる」と言う。
    ところが10場の経度を総当たりで出すと、2度でつながる集団は**3つしかない**:

        東 … 札幌 函館 福島 新潟 東京 中山（＋美浦）
        西 … 中京 京都 阪神（＋栗東）
        単独 … 小倉

    **これは「関東・関西・小倉」という既存の区分とほぼ同じ。**
    磁場という言葉を外しても情報は減らないので、**競馬場と地区で言い換える。**

★2026-09-20 中山＋阪神 24鞍 308頭で測った結果（その日だけ。遡っていない）

    経度差（＝地区が同じか）… **効かなかった。**
        中山10Rで、前走が同じ地区の7頭が揃って掲示板を外した。
        11Rは1着が別地区、2着が同地区で割れた。

    前走からの週数 … **こちらが濃い。**
        0-4週   102頭  3着内19  19%   1着6
        4.5-7週  25頭  3着内 5  20%   1着2
        7-9週    31頭  3着内 8  26%   1着2
        9-16週   53頭  3着内20  38%   1着8   ← 山
        16週超   36頭  3着内 2   6%   1着0   ← 谷。**1着ゼロ**
        合計    308頭  3着内66  21%

    ＝ 7週の境目より、**16週の崖**のほうがずっと大きい。
      中島氏の「順応に約6か月」でいえば、**6か月に近づくほど走らない**。

★だから既定の出力は「地区」ではなく「週数の帯」を主にする。
  地区は列として横に出すだけ。理由には使わない（4角relと同じ扱い）。

★これは1日・308頭。中山は不良/重、阪神は良だった。
  乾いた日にどうなるかは分からない。**ルールに昇格させるかはユーザーが決める。**

使い方:
    python3 scripts/ana/basho.py --rids 202604050611 --base 2026-09-20
    python3 scripts/ana/basho.py --pre 2026040506 --races 9-12 --base 2026-09-20
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kb

# 東経。地区の判定にだけ使う。
LON = {
    "札幌": 141.35, "函館": 140.77, "福島": 140.44, "新潟": 139.05, "東京": 139.48,
    "中山": 140.02, "中京": 137.01, "京都": 135.77, "阪神": 135.36, "小倉": 130.86,
    "美浦": 140.30, "栗東": 136.00,
    "大井": 139.76, "船橋": 140.00, "川崎": 139.68, "浦和": 139.66, "門別": 142.07,
    "盛岡": 141.13, "水沢": 141.14, "金沢": 136.63, "笠松": 136.77, "名古屋": 136.92,
    "園田": 135.36, "姫路": 134.68, "高知": 133.57, "佐賀": 130.30, "帯広": 143.20,
}
HIGASHI = {"札幌", "函館", "福島", "新潟", "東京", "中山", "美浦",
           "大井", "船橋", "川崎", "浦和", "門別", "盛岡", "水沢", "帯広"}
NISHI = {"中京", "京都", "阪神", "栗東", "金沢", "笠松", "名古屋", "園田", "姫路"}

# 2026-09-20 の308頭で測った3着内率。**その日だけの数字。参考として横に出す。**
RATE = {"0-4週": "19%", "4.5-7週": "20%", "7-9週": "26%",
        "9-16週": "38%", "16週超": "6%（1着0）"}


def area_of(place: str | None) -> str:
    if not place:
        return "?"
    if place in HIGASHI:
        return "東"
    if place in NISHI:
        return "西"
    if place == "小倉":
        return "小倉"
    return "?"


def place_of(s: str | None):
    """『3中山7』『2026年9月20日中山11R…』どちらからも場名を拾う。"""
    if not s:
        return None
    for k in LON:
        if k in s:
            return k
    return None


def band(w) -> str:
    if w is None:
        return "?"
    return ("0-4週" if w < 4.5 else "4.5-7週" if w < 7 else
            "7-9週" if w < 9 else "9-16週" if w < 16 else "16週超")


def leg(rid: str, base):
    m, runners = kb.syutuba(rid)
    here = place_of(m["title"])
    out = []
    for x in runners:
        h = ([q for q in kb.uma(x["umacd"]) if kb.to_date(q["date"]) < base]
             if x["umacd"] else [])
        last = h[-1] if h else None
        wk = ((base - kb.to_date(last["date"])).days / 7) if last else None
        pl = place_of(last["place"]) if last else None
        if pl and here:
            rel = ("同じ競馬場" if pl == here else
                   "同じ地区" if area_of(pl) == area_of(here) else "遠征")
        else:
            rel = "?"
        out.append(dict(x=x, wk=wk, band=band(wk), place=pl, move=rel,
                        lon=(round(abs(LON[pl] - LON[here]), 2)
                             if pl and here else None)))
    return m, here, out


def show(m, here, rec):
    print("=" * 100)
    ttl = m["title"].split("|")[1].strip() if "|" in m["title"] else m["title"]
    print(f"■ {ttl}   {here}（{area_of(here)}）  {m['surface']}{m['dist']}m  {len(rec)}頭\n")
    order = ["9-16週", "7-9週", "4.5-7週", "0-4週", "16週超", "?"]
    print(f"  {'番':>3} {'馬名':<17}{'単勝':>7}{'間隔':>7} {'帯':<9}"
          f"{'9/20の3着内率':<14}{'前走地':>7} {'移動':<11}経度差")
    for r in sorted(rec, key=lambda z: (order.index(z["band"]), z["x"]["ub"])):
        x = r["x"]
        wk = f"{r['wk']:.1f}週" if r["wk"] else "—"
        print(f"  {x['ub']:>3} {x['name']:<17}{(x['odds'] or '-'):>7}{wk:>7} "
              f"{r['band']:<9}{RATE.get(r['band'], '—'):<14}"
              f"{(r['place'] or '—'):>7} {r['move']:<11}"
              + (f"{r['lon']:.2f}度" if r["lon"] is not None else "—"))
    # 帯ごとの頭数
    cnt = {}
    for r in rec:
        cnt[r["band"]] = cnt.get(r["band"], 0) + 1
    print("\n  ▸ この鞍の内訳 … " + " / ".join(
        f"{b} {cnt[b]}頭" for b in order if b in cnt))
    good = [r for r in rec if r["band"] in ("9-16週", "7-9週")]
    bad = [r for r in rec if r["band"] == "16週超"]
    if good:
        print(f"  ▸ 7〜16週（9/20に33%の帯）… "
              + " / ".join(f"{r['x']['ub']} {r['x']['name']}" for r in good))
    if bad:
        print(f"  ▸ 16週超（9/20に6%・1着ゼロの帯）… "
              + " / ".join(f"{r['x']['ub']} {r['x']['name']}" for r in bad))
    print()


def main():
    ap = argparse.ArgumentParser(description="前走の競馬場と、そこからの週数を数える")
    ap.add_argument("--rids", nargs="*", default=[])
    ap.add_argument("--pre", help="中央の開催コード10桁")
    ap.add_argument("--races", default="1-12")
    ap.add_argument("--base", required=True, help="基準日 YYYY-MM-DD")
    a = ap.parse_args()

    base = kb.to_date(a.base.replace("-", "/"))
    rids = list(a.rids)
    if a.pre and not rids:
        lo, _, hi = a.races.partition("-")
        rids = [f"{a.pre}{r:02d}" for r in range(int(lo), int(hi or lo) + 1)]

    for rid in rids:
        m, here, rec = leg(rid, base)
        if not rec:
            print(f"× 出馬表が取れません（{rid}）")
            continue
        show(m, here, rec)

    print("※『9/20の3着内率』は 2026-09-20 の中山＋阪神 308頭で測った、その日だけの数字です。")
    print("  遡って測ってはいません。ルールに昇格させるかはユーザーが決めます。")
    print("※ 地区（東/西/小倉）は事実として横に出すだけで、理由には使いません。")
    print("  9/20は経度差が効かず（中山10Rで同地区7頭が全滅）、効いたのは週数のほうでした。")


if __name__ == "__main__":
    main()
