#!/usr/bin/env python3
"""**その馬個体が、自分の時計に対して上がっているか。**

    python3 scripts/nankan_cyokyo_trend.py --place 大井 --date 20260904
    python3 scripts/nankan_cyokyo_trend.py --place 大井 --date 20260904 --race 11

`data/cyokyo/{日付}_{場}.jsonl`（`nankan_cyokyo.py` が作る）を読む。

── なぜ他馬と比べないのか ─────────────────────────────

矢印・短評で他馬と比べるやり方は**この開催で潰した**（大井 8/31〜9/4・692頭）。
人気で揃えたら全部消えた ── 矢印は人気の言い換えだった:

        1〜3人気  ↗ 52%(n=23)  →  61%(n=156)   ← ↗のほうが悪い
        7人気以下 ↗ 13%(n=23)  →   5%(n=311)   ← 3着内3頭。noise

  矢印も短評も**競馬ブックの判断**なので、市場が先に読んでいる。
  実測値でないものは織り込まれる。

  → 見るべきは**その馬自身の時計が、前より速くなっているか**。
     これは人の判断が入らない**測ったもの**で、比較の相手が市場ではない。

── ⚠️⚠️ 時計を並べる前に、揃えないといけないもの ───────────────

**そのまま引き算してはいけない。**同じ数字でも中身が違う:

    コース   大井外 / 小林外 / 小林坂 / 船橋外 …  **坂路と平場は別物**
    馬場     良 / 稍 / 重 / 不                  重い馬場は当然遅い
    脚色     馬なり / 強め / 一杯 / 追って       **馬なりの37.5 と
                                               一杯の37.5 は別物**
    本数     坂路の「2回」は時計欄に入る（`times_raw` に生で残してある）

  → このファイルは **(コース, 馬場, 脚色) が同じ組でだけ差を取る**。
    揃わないものは `判定不能` と出す。**0 で埋めない。**

  ⚠️ 揃えると本数が激減する。「比較可能な馬が少ない」ことこそが実態で、
     無理に揃えずに引き算した数字より、**判定不能のほうが正しい。**
     実測：大井 2026-09-04 の122頭で **判定できたのは12頭（10%）**。

── ⚠️⚠️ このファイルの限界（2026-09-04 に判明）─────────────────

**1レース分のページの中で引き算しても、上昇は測れない。**

`中間の時計` は「乗り込み」と「追い切り」が混ざった列で、**脚色では強度が
揃わない**。ラブリールチア（大井 9/4 11R）の3本はすべて「小林坂・良・馬なり」:

        8/23   2F 27.5   「変わりなく順調」
        8/30   2F 29.4   「上がりに重点置く」   ← 坂路2本目
      ☆ 8/30   2F 22.8   「好時計マーク」       ← 追い切り

  同じ「馬なり」で 22.8 と 29.4。前者は本気の1本、後者はただの周回。
  これを引き算して **「-4.7秒 速くなった」と誤報した。**

  **正しい測り方は、追い切り（☆）どうしをレースをまたいで比べること。**
  ☆は1レースに1本で役割が固定（その週の本気の1本）なので比較になる。

        前々走の☆ → 前走の☆ → 今回の☆

  → それには `nankan_cyokyo_hist.py` が集める**近N走ぶんのページ**が要る。
     このファイルは1ページ内の並びしか見ておらず、**暫定**。
     ☆どうしの比較に組み直すこと。

⚠️ 日付の無い行（`■` `◇`）は**印の意味が分かっていない**。「前走時の追い切り」
   だと思って同開催の前走と照合したら不一致だった（n=1）。計算に入れない。

── ⚠️ 正直な線引き ─────────────────────────────

・**調教の時計が効くかどうかは、このリポジトリで一度も検証していない。**
  これは材料を作る道具であって、「速くなったから買い」ではない。
・比較の単位は1頭の中だけ。他馬・市場とは比べていない。
・恒久ルール5：目の前の開催を見るだけ。過去開催の一括検証はしない。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import keibabook as kb                # noqa: E402

IN_DIR = "data/cyokyo"
#: 速さを代表させる欄。**上から順に、埋まっている最初のものを使う。**
#: ⚠️ 坂路は 3F(2F)/1F(1F) が本体、平場は 半哩(3F)/3F(2F) が本体。
PREF = ("3F(2F)", "1F(1F)", "半哩(3F)", "5F(4F)", "6F(坂路)")


def pick(w: dict) -> tuple[str, float] | None:
    """その1本を代表する (欄名, 秒)。無ければ None。"""
    for k in PREF:
        v = w["times"].get(k)
        if v is not None:
            return k, v
    return None


def key(w: dict) -> tuple:
    """比較してよい条件の組。**ここが違うものを引き算しない。**"""
    return (w.get("course"), w.get("baba"), w.get("asiiro"))


def trend(works: list[dict]) -> tuple[str, list[dict]]:
    """(コース,馬場,脚色) が同じ最大の組で差を取る。

    返り値 `(説明, 使った本)`。組が2本未満なら `判定不能`。

    ⚠️⚠️ **日付のある行しか使わない。**日付欄が `■` `◇` になっている行が
       あり、**この印の意味が分かっていない**。「前走時の追い切り」だと思って
       同開催の前走と照合したら**不一致**だった（n=1）。意味の分からない行を
       表の並び順で「古い」と決めつけて引き算すると、上下が逆に出かねない。
       **表示はするが、計算には入れない。**判定できる馬は減るが、そのほうが
       正しい（意味の分からない行を混ぜた数字より、判定不能のほうがまし）。
    """
    groups: dict[tuple, list[dict]] = {}
    for w in works:
        if w.get("month") is None:            # 日付が無い行（■ / ◇）は使わない
            continue
        p = pick(w)
        if p:
            groups.setdefault(key(w), []).append({**w, "col": p[0], "sec": p[1]})
    # ⚠️⚠️ **同じ日に複数本ある。**坂路は1日2本引くことがあり（時計欄の「2回」）、
    #    1本目と2本目を並べると「上昇」に見える。実際 ラブリールチアで
    #    8/30の 29.4(2本目) → 22.8(追い切り) を拾って **-4.7秒速く** と誤報した。
    #    **1日1本に潰す**（その日の最後＝速いほうの本命を採る）。
    for k, v in list(groups.items()):
        byday: dict[tuple, dict] = {}
        for w in v:
            byday[(w["month"], w["day"])] = w   # 表の並びで後のものが残る
        groups[k] = list(byday.values())
    # 別々の日が2つ以上そろって初めて「前より速いか」が言える
    usable = {k: v for k, v in groups.items() if len(v) >= 2}
    if not usable:
        return "判定不能（同条件が2本そろわない）", []
    best = max(usable.values(), key=len)
    d = best[-1]["sec"] - best[0]["sec"]
    where = f"{best[0]['course']}・{best[0]['baba']}・{best[0]['asiiro']}"
    word = "速く" if d < 0 else ("遅く" if d > 0 else "変わらず")
    return (f"{where} の {best[0]['col']} で {best[0]['sec']:.1f} → "
            f"{best[-1]['sec']:.1f}（{d:+.1f}秒 {word}）"), best


def main() -> None:
    ap = argparse.ArgumentParser(description="その馬個体の調教時計の上下")
    ap.add_argument("--place", default="大井")
    ap.add_argument("--date", required=True, help="YYYYMMDD")
    ap.add_argument("--race", type=int)
    ap.add_argument("--only", action="store_true",
                    help="判定できた馬だけ出す")
    args = ap.parse_args()

    path = os.path.join(IN_DIR, f"{args.date}_{args.place}.jsonl")
    if not os.path.exists(path):
        print(f"{path} がありません。先に nankan_cyokyo.py を回してください。",
              file=sys.stderr)
        sys.exit(1)
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    if args.race:
        rows = [r for r in rows if r["race"] == args.race]

    ok = ng = 0
    cur = None
    for r in sorted(rows, key=lambda x: (x["race"], x.get("umaban") or 0)):
        desc, used = trend(r.get("works") or [])
        if used:
            ok += 1
        else:
            ng += 1
            if args.only:
                continue
        if r["race"] != cur:
            cur = r["race"]
            print(f"\n{'='*94}\n {args.place} {args.date}  {cur}R\n{'='*94}")
        side = r.get("race_side") or {}
        pop = f"{side['pop']}人気" if side.get("pop") else ""
        fin = f"→{side['finish']}着" if side.get("finish") else ""
        print(f"\n {r.get('umaban') or '':>2} {r['name']:<14}{pop:>7}{fin:>6}"
              f"   {desc}")
        for w in r.get("works") or []:
            p = pick(w)
            body = (f"【{w['no_time_note']}】" if w["no_time_note"]
                    else (f"{p[0]} {p[1]:.1f}" if p else ""))
            # ⚠️ 日付欄に既に `*` が入っているので、印はここで足さない（`**` になる）
            star = "☆" if w["oikiri"] else "  "
            use = "◀" if any(w is u or (w.get("date_raw") == u.get("date_raw")
                                        and key(w) == key(u)) for u in used) else " "
            print(f"    {star}{(w['date_raw'] or ''):<10}"
                  f"{(w['course'] or ''):<7}{(w['baba'] or ''):<3}"
                  f"{(w['asiiro'] or ''):<5}{body:<18}{use} {w['note'] or ''}")

    print(f"\n■ 判定できた {ok}頭 ／ 判定不能 {ng}頭"
          f"（{ok/max(ok+ng,1)*100:.0f}%）", file=sys.stderr)
    print("⚠️ 同条件（コース・馬場・脚色）が2本そろわない馬は判定不能。"
          "**揃えずに引き算した数字より、判定不能のほうが正しい。**", file=sys.stderr)
    print("⚠️ 調教の時計が効くかどうかは未検証。", file=sys.stderr)


if __name__ == "__main__":
    main()
