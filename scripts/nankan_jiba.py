#!/usr/bin/env python3
"""**中島理論の「磁場」を、間違えられる形まで絞り込む道具。**

    # ① 磁場地図（大井から見てどこが同じ磁場か）
    python3 scripts/nankan_jiba.py --map --place 大井

    # ② その日の出走馬が、いま磁場のどこにいるか
    python3 scripts/nankan_jiba.py --place 大井 --date 20260918

楽天だけで動く（Cookie 不要）。出馬表の馬柱から計算する。

── 中島理論の主張（原典 pp.58-68）─────────────────────────

  ・馬は長く暮らした土地の磁場の支配を受ける（脳の視交差上核が感知する）
  ・**経度差2度以内なら同じ磁場**
  ・2度を越えて移動すると、**約7週間は元の土地の磁場の影響が続く**
  ・7週を過ぎて元の磁場が切れ、**新しい土地への順応におよそ6か月**

⚠️ 「視交差上核が体内時計」は現代科学でも知られているが、**それが土地ごとの
   磁場を感知して競走能力を調整する**という部分は中島氏独自の仮説。
   「経度2度以内＝同じ磁場」も地磁気学の定説ではない。**本当の地磁気は経度に
   沿って並ばない**（偏角・全磁力は緯度と局所地質で変わる）。
   ここで経度を使うのは、**中島氏の理論を彼自身のルールで動かすため**であって、
   地球物理として正しいからではない。

── ⚠️⚠️ この道具を作って分かった、いちばん大事なこと ─────────

**① 南関4場は、中島氏の定義では丸ごと一つの磁場。**

       浦和 139.65° ／ 川崎 139.71° ／ 大井 139.74° ／ 船橋 139.99°
       → 最大の開きでも **0.34度**。2度の 1/6 しかない。

   大井→川崎→船橋と回っても磁場は動かない。**南関の中だけを走る馬について、
   磁場論は何も言わない。**

**② 遠征では磁場は切り替わらない。**

   中島氏の時定数は **7週**。JRAの関西馬が東京へ行くのは**数日**。
   7週の足元にも及ばない。つまり中島氏の理屈では、遠征馬は**行った先が
   何度離れていようと、ずっと元の磁場のまま**走っている。
   「遠征＝別磁場だから走らない」は**中島理論の誤読**。

   → **磁場が実際に切り替わるのは次の3つだけ:**
        (a) **移籍・転厩**（門別→大井、西日本→南関、JRA→南関 …）
        (b) **7週を越える長期放牧**（放牧先が2度を越えていれば）
        (c) 海外遠征

**③ だから南関では、対象になる馬が極端に少ない。**

   実測（大井 2026-09-18・近5走がある105頭）:
       経度差2度超の走りを持つ馬        **9頭 / 105頭（8.6%）**
       うち「〜7週＝元の磁場が続く」帯    **1頭**

   恒久ルール5（目の前の開催だけ見る）の下では、**1日1頭では何年かけても
   判断材料が貯まらない。**間違っているから捨てるのではなく、
   **我々の運用ルールでは原理的に検証できない**という結論になる。

**④ 最大の穴：放牧先が馬柱に無い。**

   中島理論の磁場は「**どこで暮らしたか**」の話で、「どこで走ったか」ではない。
   休養を挟んだ馬がどこにいたかは馬柱から分からない。この道具は
   **7週を越える空白を「磁場不明期間」として明示する**だけで、埋められない。
   ここを埋めない限り、磁場論は本当には検証できない。

── 境界に立つ場所（座標の取り方で判定が変わる）────────────

    大井(139.743°) から:
        **門別 142.003° → 2.26°**  ← 2度の外。だが余裕は **0.26度**しかない
        札幌 141.328° → 1.58°      同じ磁場（内側）
        盛岡 141.135° → 1.39°      同じ磁場（内側）

  門別は南関への移籍元として最も多い。**その門別が境界ぎりぎりの外側**という
  のは、この理論を南関で使う上での急所。座標を競馬場ではなく町役場で取ると
  判定が裏返りうる。`NEAR_EDGE` で印を付けている。
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import rakuten as rk                 # noqa: E402

#: 経度[度]。競馬場は Wikipedia/Wikidata の施設座標、トレセンは所在地。
#: ⚠️ ±0.05度ていどの誤差はある。**2度の閾値に対しては十分だが、境界から
#:    0.3度以内の場所（門別）は座標の取り方で判定が裏返る。**
#: ⚠️ 名古屋は2022年4月に港区→弥富市へ移転した。**同じ「名古屋」でも
#:    2022年より前と後で場所が違う**（136.88° → 136.73°）。どちらも大井から
#:    2度超なので本ツールの判定は変わらないが、原理的には別の土地。
LON: dict[str, float] = {
    # 南関東（すべて 0.34度以内＝単一磁場）
    "大井": 139.743, "川崎": 139.710, "船橋": 139.989, "浦和": 139.653,
    # JRA
    "東京": 139.485, "中山": 140.002, "新潟": 139.072, "福島": 140.430,
    "中京": 136.981, "京都": 135.769, "阪神": 135.362, "小倉": 130.881,
    "札幌": 141.328, "函館": 140.784,
    # トレセン
    "美浦": 140.302, "栗東": 136.003,
    # 地方
    "門別": 142.003, "帯広": 143.213, "盛岡": 141.135, "水沢": 141.135,
    "金沢": 136.681, "笠松": 136.771, "名古屋": 136.730,
    "園田": 135.371, "姫路": 134.702, "高知": 133.602, "佐賀": 130.222,
}

#: 同じ磁場とみなす経度差[度]。中島氏の線引き。
SAME_FIELD_DEG = 2.0
#: 移動後、元の磁場の影響が続く週数。
OLD_FIELD_WEEKS = 7.0
#: 新しい土地へ順応するまでの週数（およそ6か月）。
ADAPT_WEEKS = 26.0
#: 境界からこの度数以内なら「座標次第で裏返る」と警告する。
NEAR_EDGE = 0.3


def lon(place: str | None) -> float | None:
    """場名→経度。

    ⚠️ **楽天は中央の場を「Ｊ阪神」と全角Ｊ付きで書く。**剥がさないと表に
       当たらず、**西日本の中央帰りが丸ごと「該当なし」に落ちる**
       （実測：大井9/18 で該当馬が 9頭→3頭 に見えていた）。
    """
    if not place:
        return None
    return LON.get(place.lstrip("ＪJ").strip())


def gap(a: str | None, b: str | None) -> float | None:
    """2つの場の経度差[度]。どちらかが表に無ければ None。"""
    la, lb = lon(a), lon(b)
    return None if la is None or lb is None else abs(la - lb)


def same_field(a: str | None, b: str | None) -> bool | None:
    """中島氏の定義で同じ磁場か。判定できなければ None。"""
    d = gap(a, b)
    return None if d is None else d <= SAME_FIELD_DEG


def band(weeks: float) -> str:
    """現在の磁場に入ってからの週数→中島氏の3帯。"""
    if weeks <= OLD_FIELD_WEEKS:
        return "元の磁場が続く"
    if weeks <= ADAPT_WEEKS:
        return "順応の途中"
    return "順応済み"


def _d(s: str) -> dt.date:
    y, m, d = s.split("-")
    return dt.date(int(y), int(m), int(d))


def field_state(runs: list, home: str, today: dt.date) -> dict:
    """馬柱から「いま磁場のどこにいるか」を組み立てる。

    `runs` は **古い順**の RunRecord 列。`home` は今走る場。

    返す物:
        crossed     直近の磁場移動（別磁場→home磁場）。無ければ None
        weeks       home の磁場に入ってからの週数。crossed が無ければ
                    **馬柱の最古走からの週数＝下限**（`lower` が True）
        lower       weeks が下限でしかないか
        unknown     7週を越える空白（放牧かもしれない＝磁場不明期間）の一覧
        foreign     別磁場での走りの一覧
    """
    out = {"crossed": None, "weeks": None, "lower": False, "first": False,
           "unknown": [], "foreign": [], "n": len(runs)}
    known = [r for r in runs if lon(r.place) is not None]
    if not known:
        return out

    out["foreign"] = [r for r in known if same_field(r.place, home) is False]

    # 新しい順に見て、home と別磁場の走りに当たったところが移動地点。
    prev = None                      # ひとつ新しい側の走（＝移動後の最初の走）
    for r in reversed(known):
        if same_field(r.place, home):
            prev = r
            continue
        out["crossed"] = {"from": r.place, "from_date": r.date,
                          "to_date": prev.date if prev else None,
                          "deg": gap(r.place, home)}
        break

    anchor = prev if out["crossed"] else known[0]
    if anchor is None:
        # ⚠️ 近5走**すべて**が別磁場＝この磁場では今回が初戦（移籍初戦）。
        #    中島理論では「まだ完全に元の磁場のまま」。滞在0週。
        out["weeks"] = 0.0
        out["first"] = True
        return out
    out["weeks"] = (today - _d(anchor.date)).days / 7.0
    out["lower"] = out["crossed"] is None

    # ⚠️ 7週を越える空白は「どこにいたか分からない」。中島理論では、放牧先が
    #    2度を越えていればそこで磁場が切り替わっている。**馬柱には書いていない。**
    seq = [r for r in known if _d(r.date) >= _d(anchor.date)]
    for a, b in zip(seq, seq[1:]):
        w = (_d(b.date) - _d(a.date)).days / 7.0
        if w > OLD_FIELD_WEEKS:
            out["unknown"].append({"from": a.date, "to": b.date, "weeks": w})
    if seq:
        w = (today - _d(seq[-1].date)).days / 7.0
        if w > OLD_FIELD_WEEKS:
            out["unknown"].append({"from": seq[-1].date, "to": "今回", "weeks": w})
    return out


def print_map(home: str) -> None:
    """その場から見た磁場地図。"""
    h = lon(home)
    if h is None:
        print(f"⚠️ {home} の経度が表にありません", file=sys.stderr)
        return
    print(f"\n{'='*72}\n 磁場地図　基準＝{home}（{h:.3f}°E）"
          f"　同じ磁場＝経度差 {SAME_FIELD_DEG:.0f}度以内\n{'='*72}")
    rows = sorted(((abs(v - h), k, v) for k, v in LON.items()))
    for d, k, v in rows:
        if k == home:
            continue
        mark = "同じ磁場" if d <= SAME_FIELD_DEG else "別の磁場"
        edge = ""
        if abs(d - SAME_FIELD_DEG) <= NEAR_EDGE:
            edge = "  ⚠️ **境界から0.3度以内。座標の取り方で裏返る**"
        print(f"  {k:<5}{v:>9.3f}°  差{d:>6.3f}°  {mark}{edge}")
    inside = [k for k, v in LON.items() if abs(v - h) <= SAME_FIELD_DEG and k != home]
    print(f"\n  → {home} と同じ磁場: {'、'.join(sorted(inside))}")
    print(f"\n  ⚠️ 中島氏の時定数は{OLD_FIELD_WEEKS:.0f}週。**遠征は数日なので磁場は"
          f"切り替わらない。**\n     切り替わるのは「移籍・転厩」「{OLD_FIELD_WEEKS:.0f}週超の"
          f"放牧」「海外遠征」の3つだけ。")


def main() -> None:
    ap = argparse.ArgumentParser(description="中島理論の磁場を当てる")
    ap.add_argument("--place", required=True)
    ap.add_argument("--date", help="YYYYMMDD")
    ap.add_argument("--race", type=int)
    ap.add_argument("--map", action="store_true", help="磁場地図だけ出す")
    ap.add_argument("-n", type=int, default=5, help="馬柱を何走見るか")
    args = ap.parse_args()

    if args.map or not args.date:
        print_map(args.place)
        return

    today = dt.date(int(args.date[:4]), int(args.date[4:6]), int(args.date[6:]))
    cli = rk.KeibaRakuten()
    n_horse = n_cross = n_unknown = 0
    hits: list = []

    for rno in ([args.race] if args.race else range(1, 13)):
        try:
            rid = cli.find_race_id(args.date, args.place, rno)
            card = rk.parse_card(cli.get(f"/race_card/list/RACEID/{rid}"))
        except Exception:                                   # noqa: BLE001
            continue
        for e in card.get("entries") or []:
            runs = list(reversed((e.get("history") or [])[:args.n]))
            if not runs:
                continue
            n_horse += 1
            st = field_state(runs, args.place, today)
            if st["unknown"]:
                n_unknown += 1
            if st["foreign"]:
                n_cross += 1
                hits.append((rno, e, st))

    print(f"\n{'='*84}\n {args.place} {args.date}　中島理論・磁場\n{'='*84}")
    print(f"  近{args.n}走がある馬 {n_horse}頭")
    print(f"  うち別磁場（{args.place}から経度差{SAME_FIELD_DEG:.0f}度超）の走りを持つ馬 "
          f"**{n_cross}頭**（{n_cross/max(1,n_horse)*100:.1f}%）")
    print(f"  うち{OLD_FIELD_WEEKS:.0f}週超の空白＝**磁場不明期間**を持つ馬 {n_unknown}頭")

    if not hits:
        print(f"\n  → 磁場が動いた馬はいません。"
              f"**{args.place}だけを走る馬について、磁場論は何も言いません。**")
    for rno, e, st in hits:
        print(f"\n  {rno:>2}R {e.get('umaban'):>2} {e.get('name','')}"
              f"{('　' + str(e.get('popularity')) + '人気') if e.get('popularity') else ''}")
        for r in st["foreign"]:
            d = gap(r.place, args.place)
            print(f"      別磁場での走り  {r.date} {r.place}"
                  f"（{args.place}と{d:.2f}度）{r.finish_pos}着")
        c = st["crossed"]
        if c:
            when = (f"{c['from_date']} と {c['to_date']} の間"
                    if c["to_date"] else "**今回が当磁場での初戦**")
            print(f"      磁場移動  {c['from']} → {args.place}"
                  f"（{c['deg']:.2f}度）　{when}")
        w = st["weeks"]
        if w is not None:
            b = "移籍初戦（完全に元の磁場）" if st["first"] else band(w)
            lo = "以上（馬柱が届く範囲での下限）" if st["lower"] else ""
            print(f"      現在の磁場での滞在  {w:.1f}週{lo}　→ **{b}**")
        for u in st["unknown"]:
            print(f"      ⚠️ 磁場不明  {u['from']} 〜 {u['to']}  {u['weeks']:.1f}週の空白"
                  f"（放牧先は馬柱に載っていない）")

    # ── 理論と市場が食い違う場所 ──────────────────────────
    #    ⚠️ ここが磁場論を使うなら**唯一おいしい**ところ。中島理論が「まだ走れない」
    #       と言う帯に、市場が人気を付けているなら、そこは賭けになる。
    #       **逆に言えば、市場と一致している帯を見ても妙味は無い。**
    if hits:
        print(f"\n{'─'*84}\n■ 中島理論の帯 × 市場の評価（食い違いを探す）")
        rows: dict[str, list] = {}
        for rno, e, st in hits:
            b = "移籍初戦（完全に元の磁場）" if st["first"] else band(st["weeks"])
            rows.setdefault(b, []).append((rno, e))
        for b in ("移籍初戦（完全に元の磁場）", "元の磁場が続く",
                  "順応の途中", "順応済み"):
            if b not in rows:
                continue
            who = "、".join(
                f"{r}R{e.get('umaban')}"
                + (f"({e.get('popularity')}人気)" if e.get("popularity") else "")
                for r, e in rows[b])
            pops = [e.get("popularity") for _, e in rows[b] if e.get("popularity")]
            avg = f"　平均{sum(pops)/len(pops):.1f}人気" if pops else ""
            print(f"  {b:<16} {len(rows[b])}頭{avg}　{who}")
        print("\n  中島理論では上の帯ほど走れない。**市場がそこに人気を付けていれば"
              "食い違い＝賭けどころ。**")

    print(f"\n{'─'*84}")
    print(f"⚠️ **{n_unknown}頭（{n_unknown/max(1,n_horse)*100:.0f}%）が磁場不明期間を"
          f"持つ。**放牧先は馬柱に載っていない。\n"
          f"   中島理論の磁場は「どこで暮らしたか」であって「どこで走ったか」では"
          f"ない。\n   ここを埋めない限り、磁場論は本当には検証できない。",
          file=sys.stderr)


if __name__ == "__main__":
    main()
