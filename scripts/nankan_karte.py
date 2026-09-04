#!/usr/bin/env python3
"""**出走馬の過去走を、古い順に1行ずつ並べる。**＝ カルテ。

    python3 scripts/nankan_karte.py --date 20260907 --place 川崎 --race 1
    python3 scripts/nankan_karte.py --date 20260907 --place 川崎        # 全12R

── なぜレースを並べるのか（2026-09-04）─────────────────────

「調教を時系列で」から出てきた道具。

⚠️⚠️ **当初「南関に調教データは無い」と書いたが、これは誤りだった。**
   競馬ブックwebには**地方の調教タブが実在する**（大井の調教で、コース・馬場・
   時計・脚色・短評まで載る）。未ログインで URL を叩いて「ページがありません」
   が返ったのを、ページ自体が無いと読み違えた。**ログイン壁だった。**
   → 調教は `data/.keibabook_cookie` を置けば `keibabook.py` 側から取れる。
     ただし**調教のパーサはまだ書いていない**（2026-09-04 時点）。

   このファイルは調教の代わりではなく、**調教と並べて見るもの**。
   調教は「今どう動けているか」、こちらは「レースで何が起きてきたか」。
   楽天だけで完結するので Cookie が無くても動く、という利点がある。

── 何を出すか ───────────────────────────────────

1行 ＝ 1走。**古い順**（楽天の馬柱は新しい順なので反転している）。

    日付 場 距離 馬場 │ 人気→着順 │ 4角位置 │ 上3F │ 馬体重(増減) │ 斤量 │
    間隔 │ 騎手（★＝前走から乗り替わり）

そのあと、時系列でしか見えないものをまとめる:

    人気と着順の差の傾き   市場の見立てに対して上向きか下向きか
    4角位置の傾き         前に行くようになっているか
    馬体重の推移          **唯一、このリポジトリで検証できている材料**
    騎手                 継続か乗り替わりか
    今回                 距離の延長/短縮・場の替わり・前走からの間隔

⚠️ 楽天の馬柱は `race_class` と `days_since_last` を持たない。**間隔は日付の
   差から自前で計算している**（取れない項目を 0 で埋めないこと）。

── ⚠️ 正直な線引き ─────────────────────────────

・**馬体重の増減だけが検証済み**（人気薄374頭：−8〜−3kg で11.8%、
  +9kg以上で3.6%、全体7.8%）。`nankan_keshi.py` の W_GAIN もここから。
・**傾きは弱い。**上がり残差の傾きが次走の水準を当てる力は partial r = +0.068
  しか無かった。**「傾いているから買う」根拠にはならない。**並べて見るための
  ものであって、単独の買い材料ではない。
・4角位置の自己相関は +0.507 で、このリポジトリで測ったどの量よりも安定して
  いる。**脚質は繰り返す。**位置の傾きはそのぶん信用してよい。

⚠️ 恒久ルール5：これは**目の前の開催の出走馬**の過去走を並べているだけで、
   過去開催の一括検証ではない。回収率の集計はしない。
"""

from __future__ import annotations

import argparse
import os
import statistics as stt
import sys
import unicodedata
from datetime import date as _date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import rakuten as rk                 # noqa: E402

#: 既定で何走ぶん並べるか。馬柱がこれより短ければあるだけ出す。
DEFAULT_N = 5
#: 馬体重がこれを超えて増えていたら印を付ける[kg]。`nankan_keshi.W_GAIN` と同じ。
W_GAIN = 2


def width(s: str) -> int:
    """全角を2で数えた表示幅。⚠️ `len()` で揃えると日本語がずれる。"""
    return sum(2 if unicodedata.east_asian_width(c) in "WFA" else 1 for c in s)


def pad(s: str, n: int) -> str:
    """表示幅 `n` になるよう右に空白を足す（超えていればそのまま）。"""
    return s + " " * max(n - width(s), 0)


def to_date(s: str | None) -> _date | None:
    """`'2026-08-20'` も `'20260820'` も受ける。

    ⚠️ **楽天の馬柱は `YYYY-MM-DD`、レースIDの日付は `YYYYMMDD`。**
       決め打ちで slice すると日付が壊れる（`-0-4-` になる）。
    """
    if not s:
        return None
    t = s.replace("/", "-")
    try:
        if "-" in t:
            return _date.fromisoformat(t[:10])
        return _date(int(t[:4]), int(t[4:6]), int(t[6:8]))
    except ValueError:
        return None


def slope(v: list) -> float | None:
    """最小二乗の傾き（**古い順に並んだ列**を渡すこと）。3点未満は None。

    ⚠️ **2点の引き算で取らないこと。**水準の情報が消えて、たまたま直近が
       良かっただけの馬が「上昇中」に見える。
    """
    v = [float(x) for x in v if x is not None]
    if len(v) < 3:
        return None
    xs = list(range(len(v)))
    mx, my = stt.mean(xs), stt.mean(v)
    den = sum((a - mx) ** 2 for a in xs)
    return sum((a - mx) * (b - my) for a, b in zip(xs, v)) / den if den else None


def label(value: float, digits: int, good_is_down: bool,
          up: str, down: str, flat: str, thr: float) -> str:
    """傾きの言葉。⚠️ **表示に使う丸めた値で判定する。**生の値で判定すると
    `+0.30（横ばい）` と `+0.30（下向き）` が同じ表に並ぶ。"""
    r = round(value, digits)
    if r <= -thr:
        return down if good_is_down else up
    if r >= thr:
        return up if good_is_down else down
    return flat


def band(corner4: int | None, field: int | None) -> str:
    """4角位置を 前/中/後 に落とす。取れなければ空。"""
    if not corner4 or not field:
        return ""
    r = corner4 / field
    return "前" if r <= 0.34 else ("中" if r <= 0.67 else "後")


def run_line(h, prev) -> str:
    """過去走1走を1行にする。**取れない項目は空欄**（0で埋めない）。"""
    d = to_date(h.date)
    ds = f"{d.month:>2}/{d.day:<2}" if d else "  −  "
    dist = f"{h.distance}" if h.distance else "----"
    pop = f"{h.popularity}人" if h.popularity else "  −"
    fin = f"{h.finish_pos}着" if h.finish_pos else " −"
    c4 = h.corner_pos[-1] if h.corner_pos else None
    pos = f"{c4}/{h.field_size}{band(c4, h.field_size)}" if c4 else ""
    ag = f"{h.last3f_sec:.1f}" if h.last3f_sec else ""
    wt = ""
    if h.weight:
        wt = f"{h.weight}"
        if prev is not None and prev.weight:
            diff = h.weight - prev.weight
            wt += f"({diff:+d})" if diff else "( 0)"
    kin = f"{h.kinryo:g}" if h.kinryo else ""
    itv = ""
    pd = to_date(prev.date) if prev is not None else None
    if d and pd:
        itv = f"中{(d - pd).days}日"
    jk = h.jockey or ""
    mark = "★" if (prev is not None and prev.jockey and jk
                   and jk != prev.jockey) else " "
    return (f"    {ds} {pad(h.place or '', 6)}{dist:>4} {pad(h.baba or '', 2)}"
            f"{pop:>4}→{fin:>3}  {pad(pos, 8)}{ag:>5}  {pad(wt, 10)}"
            f"{kin:>4}  {pad(itv, 8)}{mark}{jk}")


def summarise(hs: list, hdr: dict, today: str) -> list[str]:
    """時系列でしか見えないものを数行にする。`hs` は**古い順**。"""
    out = []
    # 人気と着順の差。プラス＝人気より走れなかった。**下がるほど良い**
    gap = [h.finish_pos - h.popularity for h in hs
           if h.finish_pos and h.popularity]
    s = slope(gap)
    if s is not None:
        out.append(f"人気との差の傾き {s:+.2f}/走"
                   f"（{label(s, 2, True, '下向き', '上向き', '横ばい', 0.30)}）")
    # 4角位置。**自己相関 +0.507 でいちばん安定している量**
    rel = [h.corner_pos[-1] / h.field_size for h in hs
           if h.corner_pos and h.field_size]
    s = slope(rel)
    if s is not None:
        out.append(f"位置の傾き {s:+.3f}/走"
                   f"（{label(s, 3, True, '後ろへ', '前へ', '横ばい', 0.030)}）")
    # 馬体重。**唯一の検証済み材料**
    ws = [h.weight for h in hs if h.weight]
    if len(ws) >= 2:
        d = ws[-1] - ws[-2]
        out.append("馬体重 " + "→".join(str(x) for x in ws)
                   + (f"  ⚠️ 直近 +{d}kg" if d > W_GAIN else ""))
    # 騎手
    js = [h.jockey for h in hs if h.jockey]
    if js:
        out.append("騎手 " + "→".join(js)
                   + ("  ★乗り替わり" if len(set(js[-2:])) > 1 else "  （継続）"))
    # 今回の条件との差
    if hs:
        last, bits = hs[-1], []
        td, ld = to_date(today), to_date(last.date)
        if td and ld:
            bits.append(f"中{(td - ld).days}日")
        dist = hdr.get("distance")
        if dist and last.distance:
            d = dist - last.distance
            bits.append(f"{dist}m（{'延長 +' if d > 0 else ('短縮 ' if d < 0 else '同距離')}"
                        f"{d if d else ''}{'m' if d else ''}）")
        if last.place and hdr.get("place") and last.place != hdr["place"]:
            bits.append(f"{last.place}→{hdr['place']}")
        if bits:
            out.append("今回 " + "　".join(bits))
    return out


def show_race(cli, date: str, place: str, rno: int, n: int) -> None:
    try:
        rid = cli.find_race_id(date, place, rno)
        card = rk.parse_card(cli.get(f"/race_card/list/RACEID/{rid}"))
    except Exception as e:                                  # noqa: BLE001
        print(f"\n=== {rno}R  取得できませんでした（{e}）")
        return
    ents = card.get("entries") or []
    hdr = card.get("header") or {}
    if not ents:
        print(f"\n=== {rno}R  出馬表がまだ出ていません")
        return
    title = "  ".join(str(x) for x in
                      (hdr.get("race_class"), hdr.get("condition"),
                       f"{hdr.get('distance')}m", hdr.get("post_time")) if x)
    print(f"\n{'='*82}\n {place} {date}  {rno}R  {title}\n{'='*82}")
    print("    日付  場      距離 馬 人気→着順  4角位置  上3F  馬体重(増減)"
          "  斤量  間隔    騎手")
    for e in ents:
        hs = list(reversed((e.get("history") or [])[:n]))    # 古い順にする
        pop = f"{e['popularity']}人気" if e.get("popularity") else ""
        odds = f"{e['odds']}" if e.get("odds") else ""
        print(f"\n  {e.get('umaban',''):>2} {pad(e.get('name',''), 20)}"
              f"{pop:>7} {odds:>7}"
              + ("" if hs else "   ── 過去走なし（新馬・転入など）"))
        prev = None
        for h in hs:
            print(run_line(h, prev))
            prev = h
        for line in summarise(hs, hdr, date):
            print(f"      · {line}")


def main() -> None:
    ap = argparse.ArgumentParser(description="出走馬の過去走を古い順に並べる")
    ap.add_argument("--date", required=True, help="YYYYMMDD")
    ap.add_argument("--place", required=True)
    ap.add_argument("--race", type=int, help="指定しなければ全12R")
    ap.add_argument("-n", type=int, default=DEFAULT_N,
                    help=f"何走ぶん並べるか（既定 {DEFAULT_N}）")
    args = ap.parse_args()
    cli = rk.KeibaRakuten()
    for rno in ([args.race] if args.race else range(1, 13)):
        show_race(cli, args.date, args.place, rno, args.n)
    print("\n⚠️ 検証できているのは**馬体重の増減だけ**。傾きは並べて見るための"
          "もので、単独の買い材料ではない（上がり残差の傾きは partial r=+0.068）。")


if __name__ == "__main__":
    main()
