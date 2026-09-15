#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""これから走る1鞍を読む。数えるだけ。重みは置かない。

数えるのは3つ＋2つ。全部その日の出馬表と各馬の履歴だけで足りる。

  ① 出走間隔          そのレースの中で、誰が浮いているか
  ② 前走距離との差     延長か短縮か
  ③ 直近の上がり順位   ★ただし【同じ距離帯】に限る
  ④ 道悪（重＋不良）の成績
  ⑤ 馬体重と増減      ★発走直前まで出ない。--force で取り直す
  ⑥ レース平均からの馬体重差 ★「大きい馬」ではなく「この鞍で大きい馬」

★⑥を絶対値でなく相対で出す理由（2026-09-15 大井・終日不良）:
    勝ち馬の馬体重は、そのレースの平均より 1600m以上で +18.3kg、
    1200m以下で +0.9kg だった。距離が延びるほど大型が効いている。
    480kgが大きいかどうかは、相手を見ないと決まらない。

★③に距離帯の縛りを付けた理由（2026-09-15 大井6R）:
    ポリループは直近2走とも上がり1位だった。ただし2走とも1400m。
    今日は1600mへの延長で、上がり8位まで落ちて5着。1.9倍。
    距離帯をまたいだ上がり順位は、そのままでは持ち越せない。

★①を「機械的に」拾う理由（同日 11R）:
    その日の勝ち馬12頭のうち6頭が中3週以上あいていた（328日・313日・98日…）。
    11Rの勝ち馬スマイルマンボは313日ぶりで、この表でも間隔1位に立っていた。
    それを「極端すぎる」という主観で買い目から外して、外した。
    → 間隔が上位2番目までの馬には★が付く。**★は消さない**、が使い方。

★履歴が引けない馬を切らないこと（2026-09-15 6R / 2026-09-14 11R）:
    クイーンアン（中央から転入・履歴が別体系）3.5倍 → 1着。消した。
    ナインエスクァイア（履歴が引けず）3.7倍 → 1着。相手から外した。
    **2日連続で、同じ理由で、同じ結果。**「データが無い」を「弱い」として扱っていた。
    転入初戦は“この条件での比較対象がいない”だけで、能力とは別の話。
    → 履歴が引けない馬・行が壊れた馬には「?」が付く。**? も ★ と同じく残す。**

★⑤（同日 6R）:
    勝ったクイーンアンは +29kg（462→491）。中央の芝18頭立て14着からの転入。
    馬体重は出馬表では空欄で、発走直前に入る。1回取って終わりにすると見落とす。

使い方:
    python3 scripts/ana/card.py --date 20260915 --place 大井 --race 11
    python3 scripts/ana/card.py --date 20260915 --place 大井 --race 11 --force
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kb


def zone(d: int) -> str:
    """距離帯。上がり順位はこの中でしか比べない。"""
    return "短" if d <= 1200 else ("マ" if d <= 1700 else "長")


def agari_rank(h, base, want: str):
    """その馬の直近の『上がり順位』を、同じ距離帯の走から拾う。

    上がり順位は【そのレースの全出走馬の上がり】が要る。馬ページには自分の分しか
    無いので、その走の成績ページを引き直す。取れなければ None を返す。
    """
    for r in reversed(h):
        if kb.to_date(r["date"]) >= base:
            continue
        d = kb.dist_of(r["dist"])
        if not d or zone(d) != want or "大井" not in (r["place"] or ""):
            continue
        pre = kb.prefix(r["date"].replace("/", ""), "大井")
        if not pre:
            continue
        for rr in range(1, 13):
            rid = kb.rid_of(pre, rr, r["date"].replace("/", ""))
            _, rows = kb.seiseki(rid)
            me = next((x for x in rows if x["name"] == r["_name"]), None)
            if not me or not me["agari"]:
                continue
            ag = sorted(x["agari"] for x in rows if x["agari"])
            return dict(date=r["date"][5:], n=len(rows), chaku=me["chaku"],
                        rank=ag.index(me["agari"]) + 1, nag=len(ag), ag=me["agari"],
                        dist=d)
        return None
    return None


def main():
    ap = argparse.ArgumentParser(description="これから走る1鞍を数える")
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", default="大井")
    ap.add_argument("--race", type=int, required=True)
    ap.add_argument("--force", action="store_true", help="出馬表を取り直す（馬体重が入る）")
    ap.add_argument("--no-agari", action="store_true", help="上がり順位を引かない（速い）")
    a = ap.parse_args()

    base = kb.to_date(f"{a.date[:4]}/{a.date[4:6]}/{a.date[6:]}")
    pre = kb.prefix(a.date, a.place)
    if not pre:
        print(f"× {a.date} に {a.place} が見つかりません")
        return
    rid = kb.rid_of(pre, a.race, a.date)
    m, runners = kb.syutuba(rid, force=a.force)
    if not runners:
        print(f"× 出馬表が取れません（{rid}）")
        return
    td, tz = m["dist"], zone(m["dist"])
    print(f"■ {a.place}{a.race}R  ダ{td}m {m['course'] or ''}  {len(runners)}頭"
          f"   発走{m['start'] or '?'}  馬場{m['baba'] or '?'}")
    if not any(x["w"] for x in runners):
        print("  ※馬体重がまだ出ていません。発走30分前に --force で取り直すこと")
    if not kb.has_cookie():
        print("  ※cookie未設定。通過順位・前半3Fは取れません（脚質は直接測れない）")

    rec = []
    for x in runners:
        h = kb.uma(x["umacd"]) if x["umacd"] else []
        for r in h:
            r["_name"] = x["name"]
        last = kb.last_run(h, base)
        pd = kb.dist_of(last["dist"]) if last else None
        n1, w1, t1 = kb.at(h, a.place, td, base)
        n2, w2, t2 = kb.wet(h, base)
        ar = None if a.no_agari else agari_rank(h, base, tz)
        rec.append(dict(x=x, gap=kb.interval(h, base), pd=pd, last=last,
                        cond=(n1, w1, t1), wet=(n2, w2, t2), ar=ar,
                        unknown=(not h) or bool(x.get("partial"))))

    # ★ 間隔が浮いている馬（機械的に。主観で外さない）
    g = sorted((r for r in rec if r["gap"]), key=lambda r: -r["gap"])
    star = {id(r) for r in g[:2]}
    gaps = [r["gap"] for r in rec if r["gap"]]
    if gaps:
        print(f"\n  ▸ 間隔: 中央値 {st.median(gaps):.0f}日 / 最長 {max(gaps)}日 / "
              f"中2週(≦17日)以内 {sum(1 for v in gaps if v <= 17)}頭")
    ext = sum(1 for r in rec if r["pd"] and r["pd"] < td)
    sho = sum(1 for r in rec if r["pd"] and r["pd"] > td)
    print(f"  ▸ 距離: 延長 {ext}頭 / 短縮 {sho}頭 / 同距離 {len(rec)-ext-sho}頭")

    # ⑥ レース平均からの馬体重差。「大きい馬」でなく「この鞍で大きい馬」を出す
    #    ★0kg や空欄を平均に混ぜない（混ぜると全馬の差が壊れる）
    ws = [int(r["x"]["w"]) for r in rec
          if (r["x"]["w"] or "").isdigit() and int(r["x"]["w"]) > 100]
    avg = st.mean(ws) if ws else None
    if avg:
        print(f"  ▸ 馬体重: レース平均 {avg:.0f}kg"
              f"（最重 {max(ws)} / 最軽 {min(ws)}）")

    print(f"\n  {'★':<2}{'番':>2} {'馬名':<15}{'人気':>3}{'単勝':>7}{'体重':>7}{'平均差':>7}"
          f"{'間隔':>6}{'距離':>6}  {a.place+str(td)+'m':<12}{'道悪':<12}"
          f"{'直近の上がり順位('+tz+')'}")
    for r in sorted(rec, key=lambda z: int(z["x"]["nin"]) if (z["x"]["nin"] or "").isdigit() else 99):
        x = r["x"]
        dd = f"{td - r['pd']:+d}" if r["pd"] else "—"
        ar = r["ar"]
        arl = (f"{ar['date']} {ar['dist']}m {ar['n']}頭 {ar['chaku']}着 "
               f"→ 上り{ar['rank']}/{ar['nag']}位") if ar else "—"
        rel = (f"{int(x['w'])-avg:+.0f}kg"
               if avg and (x["w"] or "").isdigit() and int(x["w"]) > 100 else "—")
        mk = "★" if id(r) in star else ""
        if r["unknown"]:
            mk += "?"
        print(f"  {mk:<2}{x['ub']:>2} {x['name']:<15}"
              f"{(x['nin'] or '-'):>3}{(x['odds'] or '-'):>7}"
              f"{(x['w'] or '-'):>5}{(x['dw'] or ''):>4}{rel:>7}"
              f"{(str(r['gap'])+'日' if r['gap'] else '—'):>6}{dd:>6}  "
              f"{'{}走{}勝{}好走'.format(*r['cond']):<12}"
              f"{'{}走{}勝{}好走'.format(*r['wet']):<12}{arl}")

    unk = [r["x"]["name"] for r in rec if r["unknown"]]
    print("\n  ★＝そのレースで間隔が長いほうから2頭。**買い目から機械的に外さない**")
    if unk:
        print(f"  ?＝履歴が引けない/行が壊れた馬（{len(unk)}頭: {'・'.join(unk)}）")
        print("     転入初戦などで比較対象がいないだけ。**弱いという意味ではない。切らない**")
    print("  ※重みは置いていません。数えただけです。")


if __name__ == "__main__":
    main()
