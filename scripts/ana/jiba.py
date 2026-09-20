#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""【磁場】中島理論の「場所と時間」を、観測できる形だけで測る。

中島氏の主張（原典 pp.58-68 ／ ユーザー提供の解説記事より）:
    ・二つの場所の**経度差が2度以内なら同じ磁場**として扱う
    ・移動後**約7週間**は、元の土地の磁場の影響が続く
    ・7週を過ぎると元の磁場が切れ、新しい土地への順応にさらに**約6か月**

★この道具は仮説の真偽を判定しない。**仮説が要求する量を計算するだけ。**
    視交差上核が体内時計であることは確立した科学だが、
    「土地の磁場を感知して競走能力を調整する」「2度」「7週」は中島氏独自の数字で、
    地磁気学にも生理学にも裏づけはない。だから**当てにいかず、まず測る。**

★基準の取り方（2026-09-20 に一度間違えたので明記する）
    所属トレセンを固定の基準にしてはいけない。13.9週空いた馬は、その間トレセンに
    いない。中島氏が見ているのは登録上の所属ではなく **その時どこで暮らしていたか**。
    → **前走の開催地**を基準にする。これは確定情報で、必ず取れる。

判定の形:
    間隔 < 7週  … 体はまだ**前走地の磁場**を持っている。
                  前走地と今回地の経度差だけで判定できる。**ここは確定。**
    間隔 ≥ 7週  … 前走の磁場は切れている。どこで過ごしたかは馬柱に無い。
                  → **断定しない。** 放牧地を仮に置いたときの**幅**を出す。

★なぜ幅で出すか（ピーアイフォルテの件）
    福島との経度差は 門別1.65 / 静内1.95 / 新冠2.00 / 浦河2.35 で、
    **日高地方そのものが2度線をまたいでいる。**
    牧場が東西に30kmずれるだけで結論が反転する。
    放牧先を動かせば、どんな結果でも後から説明できてしまう。
    **だから「分からない」を分からないまま出す。それがこの道具の仕事。**

使い方:
    python3 scripts/ana/jiba.py --rids 202604050611 --base 2026-09-20
    python3 scripts/ana/jiba.py --pre 2026040506 --races 9-12 --base 2026-09-20
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kb

SAME = 2.0      # 中島の線引き：経度差が何度以内なら同じ磁場か
WEEKS = 7       # 元の磁場が切れるまでの週数
ADAPT = 26      # 新しい土地へ順応するまで（週）＝およそ6か月

# 東経。競馬場・トレセン・主な馬産地。
LON = {
    # JRA
    "札幌": 141.35, "函館": 140.77, "福島": 140.44, "新潟": 139.05, "東京": 139.48,
    "中山": 140.02, "中京": 137.01, "京都": 135.77, "阪神": 135.36, "小倉": 130.86,
    # トレセン
    "美浦": 140.30, "栗東": 136.00,
    # 地方（南関ほか）
    "大井": 139.76, "船橋": 140.00, "川崎": 139.68, "浦和": 139.66, "門別": 142.07,
    "盛岡": 141.13, "水沢": 141.14, "金沢": 136.63, "笠松": 136.77, "名古屋": 136.92,
    "園田": 135.36, "姫路": 134.68, "高知": 133.57, "佐賀": 130.30, "帯広": 143.20,
}

# 休み明けの行き先候補（日高〜胆振）。★2度線をまたいでいるので必ず幅で出す。
BOKUJO = {
    "白老": 141.36, "千歳": 141.65, "安平(早来)": 141.83, "日高町(門別)": 142.07,
    "平取": 142.10, "新ひだか(静内)": 142.37, "新冠": 142.42, "浦河": 142.77,
    "えりも": 143.15,
}


def lon_of(place: str):
    """『3中山7』『1阪神6』のような表記からも場名を拾う。"""
    if not place:
        return None, None
    for k, v in LON.items():
        if k in place:
            return k, v
    return None, None


def judge(a: float, b: float) -> str:
    return "同磁場" if abs(a - b) <= SAME else "別磁場"


def leg(rid: str, base):
    m, runners = kb.syutuba(rid)
    here, hlon = lon_of(m["title"])
    if hlon is None:
        return m, None, []
    out = []
    for x in runners:
        h = [q for q in kb.uma(x["umacd"]) if kb.to_date(q["date"]) < base] if x["umacd"] else []
        last = h[-1] if h else None
        gap = (base - kb.to_date(last["date"])).days if last else None
        wk = gap / 7 if gap else None
        pl, plon = lon_of(last["place"]) if last else (None, None)
        out.append(dict(x=x, last=last, gap=gap, wk=wk, place=pl, plon=plon))
    return m, (here, hlon), out


def show(m, here, rec):
    place, hlon = here
    print("=" * 104)
    ttl = m["title"].split("|")[1].strip() if "|" in m["title"] else m["title"]
    print(f"■ {ttl}   {place}（東経{hlon:.2f}）  {m['surface']}{m['dist']}m  {len(rec)}頭")
    print(f"  ※中島の線引き：経度差 {SAME}度以内＝同磁場 ／ 移動後 {WEEKS}週は元の磁場が残る\n")

    fixed = [r for r in rec if r["wk"] is not None and r["wk"] < WEEKS and r["plon"]]
    open_ = [r for r in rec if not (r["wk"] is not None and r["wk"] < WEEKS and r["plon"])]

    print(f"  ── ① 前走から{WEEKS}週未満：体はまだ前走地の磁場。**ここは確定できる** "
          f"（{len(fixed)}頭）")
    print(f"  {'番':>3} {'馬名':<17}{'単勝':>7}{'前走地':>7}{'経度':>8}{'差':>7}  判定")
    for r in sorted(fixed, key=lambda z: z["x"]["ub"]):
        x, d = r["x"], abs(r["plon"] - hlon)
        print(f"  {x['ub']:>3} {x['name']:<17}{(x['odds'] or '-'):>7}{r['place']:>7}"
              f"{r['plon']:>8.2f}{d:>6.2f}度  {judge(r['plon'], hlon)}"
              f"   （中{r['wk']:.1f}週）")

    if open_:
        print(f"\n  ── ② 前走から{WEEKS}週以上、または前走地が取れない：**断定しない**"
              f" （{len(open_)}頭）")
        for r in sorted(open_, key=lambda z: z["x"]["ub"]):
            x = r["x"]
            wk = f"{r['wk']:.1f}週" if r["wk"] else "履歴なし"
            pl = r["place"] or "?"
            print(f"  {x['ub']:>3} {x['name']:<17}{(x['odds'] or '-'):>7}"
                  f"  前走 {pl}／{wk}  → 前走の磁場は切れている。放牧先は馬柱に無い")

        lo = min(abs(v - hlon) for v in BOKUJO.values())
        hi = max(abs(v - hlon) for v in BOKUJO.values())
        same = [k for k, v in BOKUJO.items() if abs(v - hlon) <= SAME]
        diff = [k for k, v in BOKUJO.items() if abs(v - hlon) > SAME]
        print(f"\n     休養先を日高〜胆振と置いたときの、この場との経度差：{lo:.2f}〜{hi:.2f}度")
        print(f"       同磁場になる … {'／'.join(same) if same else 'なし'}")
        print(f"       別磁場になる … {'／'.join(diff) if diff else 'なし'}")
        if same and diff:
            print(f"     ★**この場は2度線をまたぐ。牧場の位置しだいで結論が反転する。**")
            print(f"       放牧先を選べばどちらにも説明できてしまうので、**断定してはいけない。**")
    print()


def main():
    ap = argparse.ArgumentParser(description="磁場（経度差と7週）を観測できる形だけで測る")
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
        if not here or not rec:
            print(f"× 場所が判定できません（{rid}）")
            continue
        show(m, here, rec)

    print("※ この道具は磁場仮説の真偽を判定しません。仮説が要求する量を計算するだけです。")
    print("  『2度』『7週』は中島氏独自の数字で、地磁気学にも生理学にも裏づけはありません。")


if __name__ == "__main__":
    main()
