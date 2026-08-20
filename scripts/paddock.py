#!/usr/bin/env python3
"""**パドックで見たものを記録して、あとで結果と突き合わせる。**

このリポジトリで「効く」と確認できたパドック情報は、いまのところ**馬体重の
増減だけ**（人気薄374頭で −8〜−3kg 11.8% ／ +9kg以上 3.6%、全体7.8%）。
それ以外は全部、力学からの推論で未検証。

目で見たものを同じ土俵に乗せるための道具。**当たった馬だけ覚えていると必ず
過大評価になる**ので、**全頭を記録させる**作りにしてある。

── 使い方 ───────────────────────────────────────

    # ① 開催前：白紙の記録シートを作る（出馬表から全頭ぶん）
    python3 scripts/paddock.py sheet --date 20260818 --place 川崎 --race 12

    # ② パドックで数字を埋める（data/paddock/YYYYMMDD_場.jsonl を直接編集）

    # ③ レース後：結果と突き合わせる
    python3 scripts/paddock.py score --place 川崎

── 採点項目 ─────────────────────────────────────

**総合1つではなく、分けて点ける。**あとで「どの項目が効いていたか」を
分離できるようにするため。1つにまとめると、効いた理由が永久に分からない。

    fold_h   畳みの高さ    膝がどこまで折れて上がるか
    fold_v   畳みの速さ    折れてから前に出るまでが速いか
    relax    脱力         立脚の終わりで力が抜けているか（カタパルトの撃鉄）
    distal   遠位の締まり  膝から下に余肉が無いか（**細さではなく締まり**）
    head     頭の安定     頭の高さが一定か（腕頭筋の作用線）
    total    総合         「カタパルトが見えたか」の一言判断

    すべて **0〜3**（0=悪い / 1=並 / 2=良い / 3=際立つ）。
    見られなかった項目は **null** のままにする（0を入れない）。

⚠️⚠️ **「見なかった馬」を書かないこと。**シートは全頭ぶん作られるので、
   点けられなかった馬は null のまま残す。**消さない。**消すと、その馬が
   「対象外」なのか「悪かった」のか区別できなくなる。

⚠️ 判断は**発走前に**確定させること。結果を見てから点数をいじったら、
   このファイルの価値はゼロになる。

── なぜこの項目を点けるのか（カタパルトの構造・2026-08-20 調査）──────

前肢を前に振り出しているのは筋力ではなく、**上腕二頭筋の内部腱＝カタパルト**。
ギャロップ中に 243 J を 0.11秒で放出する（非弾性の筋肉なら50kg相当）。

  実測された構造（Watson & Wilson, J Anat 2007）:
      MTU全長        約40cm、質量 576〜1068g
      **内部腱**       長さ 35〜44cm、質量 **122〜260g**（個体差 2.1倍）
      外側頭の筋線維   **0.5〜0.8cm**   内側頭 2.2〜4.0cm
      筋の等尺性力     10.6〜21.4 kN
      **腱の耐力**      **32〜54 kN**（筋の3倍）

  → 筋肉が出せない力に耐える設計＝**荷重源は筋肉ではない**。
     腱を引くのは**馬自身の体重と前進運動**で、筋肉は握って離すだけ。

  充填の条件：立脚期の **肩関節の屈曲 ＋ 肘関節の伸展**。
     腱は 肩甲骨の棘上結節 →（肩関節前面）→ 上腕前面 → 橈骨粗面 と走る。
     体が前進して肩が閉じ、同時に肘が伸びると、腱の両端が引き離される。
     **蹄を置いて、その上を体が通過する**ことが充填そのもの。

  容量：E = ½ · E_mod · ε² · V   （V＝腱の体積、ε＝歪み）
     → **同じ歪みならエネルギーは腱の体積に比例**。腱質量の個体差2.1倍が効く。
     → ⚠️⚠️ **εは2乗で効く。**伸びが2割減ればエネルギーは 0.64倍、
        3割減れば 0.49倍。**砂で蹄が沈むと、わずかな伸び不足が倍近い損失になる。**

  骨格で決まる部分（＝パドックで見える部分）:
      ① 上腕の長さ      腱の長さ＝容量。肩甲骨長の 75% に近いほど長い
      ② 肩甲骨の傾斜    引き幅（ε）。サラブレッドの理想は約45°。**2乗で効く**
      ③ 肩と上腕の角度  **90°未満（closed shoulder）は前方への動きが構造的に死ぬ**

  → ③が0なら①②が良くても撃てない。だから `total` だけでなく分解して点ける。

⚠️ ①②③の数値は文献値だが、「この馬体だと速い」を直接検証した研究は
   見ていない。つなげて競走能力を語るのは**このリポジトリの推論**。
   だからこそ、ここで記録して人気薄の帯で照合する。
"""

from __future__ import annotations

import argparse
import json
import os
import statistics as stt
import sys
from glob import glob

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import rakuten as rk                 # noqa: E402

DIR = "data/paddock"
#: 採点項目。**総合を1つ持つが、分解項目も必ず残す。**
ITEMS = ("total", "fold_h", "fold_v", "relax", "distal", "head")
UNPOP = 7


def path_for(date: str, place: str) -> str:
    return os.path.join(DIR, f"{date}_{place}.jsonl")


def cmd_sheet(args) -> None:
    """出馬表から白紙のシートを作る（既にある行は上書きしない）。"""
    cli = rk.KeibaRakuten()
    os.makedirs(DIR, exist_ok=True)
    p = path_for(args.date, args.place)
    have = set()
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            have.add((r["race"], r["umaban"]))
    races = [args.race] if args.race else range(1, 13)
    added = 0
    with open(p, "a", encoding="utf-8") as f:
        for rno in races:
            try:
                rid = cli.find_race_id(args.date, args.place, rno)
                card = rk.parse_card(cli.get(f"/race_card/list/RACEID/{rid}"))
            except Exception:                               # noqa: BLE001
                continue
            for e in card["entries"]:
                if (rno, e["umaban"]) in have:
                    continue
                row = {"date": args.date, "place": args.place, "race": rno,
                       "umaban": e["umaban"], "name": e["name"],
                       "odds": e.get("odds"), "pop": e.get("popularity")}
                row.update({k: None for k in ITEMS})
                row["memo"] = ""
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                added += 1
    print(f"{p} に {added}行 追加しました（既存 {len(have)}行 はそのまま）")
    print(f"採点は {'/'.join(ITEMS)} を 0〜3 で。見られなかった項目は null のまま。")


def load(place: str) -> list:
    out = []
    for p in sorted(glob(os.path.join(DIR, f"*_{place}.jsonl"))):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def cmd_score(args) -> None:
    cli = rk.KeibaRakuten()
    rows = load(args.place)
    if not rows:
        print(f"{DIR} に {args.place} の記録がありません。まず sheet で作ってください。")
        return
    # 結果と払戻を引く
    cache: dict = {}
    for r in rows:
        key = (r["date"], r["race"])
        if key not in cache:
            try:
                rid = cli.find_race_id(r["date"], args.place, r["race"])
                raw = cli.get(f"/race_performance/list/RACEID/{rid}")
                res = rk.parse_result(raw)
                cache[key] = ({x["umaban"]: x for x in res},
                              rk.parse_place_payout(raw))
            except Exception:                               # noqa: BLE001
                cache[key] = ({}, {})
        fin, pay = cache[key]
        x = fin.get(r["umaban"])
        r["finish"] = x["finish"] if x else None
        r["rpop"] = (x.get("popularity") if x else None) or r.get("pop")
        r["pay"] = pay.get(r["umaban"], 0)

    done = [r for r in rows if r["finish"] is not None]
    scored = [r for r in done if r.get("total") is not None]
    print(f"\n=== {args.place}　記録 {len(rows)}頭／結果が出た {len(done)}頭"
          f"／総合を点けた {len(scored)}頭 ===\n")
    if len(scored) < 20:
        print("⚠️ まだ判断できる量ではありません。**最低でも数開催、200頭は要ります。**")
        print("   いまの内訳だけ出します。\n")

    def rep(lab, sel):
        n = len(sel)
        if n < 5:
            print(f"  {lab:<30} n={n}")
            return
        hit = sum(1 for x in sel if x["finish"] <= 3)
        tot = sum(x["pay"] for x in sel)
        s = sorted((x["pay"] for x in sel), reverse=True)
        ex = (tot - sum(s[:3])) / (100 * max(n - 3, 1)) * 100
        print(f"  {lab:<30} n={n:>4}  3着内 {hit:>3} ({hit/n*100:>5.1f}%)"
              f"  複勝回収 {tot/(100*n)*100:>6.1f}%  上位3件抜き {ex:>6.1f}%")

    rep("記録した全頭", done)
    print("\n── 総合点ごと ──────────────────────────")
    for v in (3, 2, 1, 0):
        rep(f"総合 {v}", [x for x in scored if x["total"] == v])
    print("\n── **人気薄（7番人気以下）だけ** ────────────────")
    u = [x for x in done if x.get("rpop") and x["rpop"] >= UNPOP]
    rep("人気薄・全体", u)
    for v in (3, 2):
        rep(f"人気薄 × 総合 {v}",
            [x for x in u if x.get("total") == v])
    print("\n── 分解項目ごと（総合より効くものがあるか）────────")
    for k in ITEMS[1:]:
        hi = [x for x in done if x.get(k) is not None and x[k] >= 2]
        lo = [x for x in done if x.get(k) is not None and x[k] <= 1]
        if len(hi) >= 5 and len(lo) >= 5:
            print(f"  【{k}】")
            rep("    2〜3点", hi)
            rep("    0〜1点", lo)
    print("\n⚠️ 100%を超える複勝回収を見たら、必ず『上位3件抜き』を見ること。")
    print("   このリポジトリで見た3桁は、ほぼ全部1〜3頭で作られていた。")


def main() -> None:
    ap = argparse.ArgumentParser(description="パドックの記録と照合")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sheet", help="白紙の記録シートを作る")
    s.add_argument("--date", required=True, help="YYYYMMDD")
    s.add_argument("--place", required=True)
    s.add_argument("--race", type=int, help="指定しなければ全12R")
    s.set_defaults(func=cmd_sheet)
    c = sub.add_parser("score", help="結果と突き合わせる")
    c.add_argument("--place", required=True)
    c.set_defaults(func=cmd_score)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
