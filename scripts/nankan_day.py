#!/usr/bin/env python3
"""**開催1日ぶんの段取りを1本にまとめる。**発走前と、結果が出た後。

    # ① 発走前（前日〜当日朝）── 調教を確保して、記録シートを作る
    python3 scripts/nankan_day.py before --place 川崎 --date 20260907

    # ② 結果が出た後 ── 着順と突き合わせて記録する
    python3 scripts/nankan_day.py after  --place 川崎 --date 20260907

── ⚠️⚠️ なぜ「前」と「後」で分けるのか ────────────────────

**調教ページは消える。**競馬ブックの調教は会員ページで、Cookie が切れると
取れない。しかも開催が終わると提供が止まることがある。

  → **開催中に取らないと、あとから絶対に手に入らない。**
     `before` は Cookie が要る。**これだけは当日中に必ず回すこと。**
     `after` はキャッシュと楽天だけで動く（Cookie 不要）。

⚠️ **判断は発走前に確定させること。**結果を見てから逸脱の判定をいじったら、
   記録の価値はゼロになる。`before` が書いた jsonl を後から書き換えない。

── before が何をするか ───────────────────────────────

    ① その日の全12Rの調教をキャッシュに確保      **Cookie 必須・最優先**
    ② パドックの記録シートを作る（全頭・null 埋め）
    ③ 逸脱判定を jsonl に書き出す（**全頭**。逸脱馬だけではない）

  ⚠️ ③は「当たった馬だけ覚える」を防ぐために全頭を書く。
     `paddock.py` と同じ考え方。

── after が何をするか ────────────────────────────────

    ① 調教と着順を紐付けて `data/cyokyo/` に書く
    ② 逸脱していた馬がどうだったかを出す

  ⚠️ **恒久ルール5**：その日の開催を見るだけ。過去開催の一括検証はしない。
  ⚠️ **恒久ルール1**：結果を見るときはラップ（ペース）分析も必ず添えること。
     この道具はそこまではやらないので、`src/nankeiba/core/lap.py` を別に回す。

── ⚠️ 効くかどうかは、まだ何も分かっていない ─────────────────

このリポジトリで検証できているパドック・調教の材料は**馬体重の増減だけ**
（人気薄374頭：−8〜−3kg で11.8%、+9kg以上で3.6%、全体7.8%）。

他馬と比べる調教材料は大井 8/31〜9/4・692頭で**6つとも落ちた**（矢印／
時計ゼロ／脚色／*／☆の時計の速さ／併走で先着）。残っている仮説は
「**その馬自身の標準形からの逸脱**」だけで、これも n=68 で測れていない。

**積むための道具であって、当てるための道具ではない。**
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

HERE = os.path.dirname(os.path.abspath(__file__))
COOKIE = "data/.keibabook_cookie"
OUT_DIR = "data/cyokyo"


def run(args: list[str], why: str) -> int:
    print(f"\n{'─'*72}\n▶ {why}\n  $ {' '.join(args)}\n{'─'*72}", flush=True)
    return subprocess.call(args)


def fetch_cyokyo(place: str, date: str) -> int:
    """その日の全12Rの調教をキャッシュに確保する。**Cookie 必須。**"""
    from nankeiba.scraping import keibabook as kb
    if not os.path.exists(COOKIE):
        print(f"⚠️⚠️ {COOKIE} がありません。**調教は今日しか取れません。**\n"
              "   競馬ブックにログインして DevTools の Network タブから\n"
              "   Cookie ヘッダをコピーし、このファイルに1行で保存してください。",
              file=sys.stderr)
        return 0
    cli = kb.KeibabookClient.from_cookie_file(COOKIE)
    NG = "指定されたページは存在しません"
    try:
        h = cli.get(f"/chihou/nittei/{date}", use_cache=False)
    except Exception as e:                                  # noqa: BLE001
        print(f"⚠️ 日程が取れません（{e}）", file=sys.stderr)
        return 0
    by: dict[str, list[str]] = {}
    for i in sorted(set(re.findall(r"/chihou/syutuba/(\d+)", h))):
        by.setdefault(i[:8], []).append(i)
    for v in by.values():
        try:
            hdr = kb.parse_race_header(cli.get(f"/chihou/syutuba/{v[0]}")) or {}
        except Exception:                                   # noqa: BLE001
            continue
        if hdr.get("place") != place:
            continue
        n = 0
        for rno, rid in enumerate(v, 1):
            try:
                t = cli.get(f"/chihou/cyokyo/1/0/{rid}")
            except Exception:                               # noqa: BLE001
                continue
            ok = NG not in t and "cyokyodata" in t
            n += ok
            print(f"   {rno:>2}R {'○' if ok else '× まだ出ていない'}")
        return n
    print(f"⚠️ {date} に {place} の開催が見つかりません", file=sys.stderr)
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="開催1日ぶんの段取り")
    ap.add_argument("mode", choices=("before", "after"))
    ap.add_argument("--place", required=True)
    ap.add_argument("--date", required=True, help="YYYYMMDD")
    args = ap.parse_args()
    py = sys.executable
    tag = f"{args.date}_{args.place}"

    if args.mode == "before":
        print(f"■ {args.place} {args.date}　発走前の段取り")
        print("\n▶ ① 調教を確保する（**Cookie 必須・今日しか取れない**）")
        n = fetch_cyokyo(args.place, args.date)
        print(f"   → {n}/12R 確保")
        if n == 0:
            print("⚠️⚠️ 調教が1つも取れていません。**ここで止めないこと。**\n"
                  "   Cookie を入れ直して、もう一度 before を回してください。",
                  file=sys.stderr)
        run([py, os.path.join(HERE, "paddock.py"), "sheet",
             "--date", args.date, "--place", args.place],
            "② パドックの記録シートを作る（全頭・null埋め）")
        os.makedirs(OUT_DIR, exist_ok=True)
        run([py, os.path.join(HERE, "nankan_zure.py"),
             "--place", args.place, "--date", args.date,
             "--jsonl", os.path.join(OUT_DIR, f"zure_{tag}.jsonl")],
            "③ 逸脱判定を書き出す（**全頭**。逸脱馬だけではない）")
        print(f"\n■ 発走前の記録は {OUT_DIR}/zure_{tag}.jsonl と "
              f"data/paddock/{tag}.jsonl")
        print("⚠️ **結果を見てから書き換えないこと。**書き換えたら記録の価値はゼロ。")
    else:
        print(f"■ {args.place} {args.date}　結果が出た後")
        run([py, os.path.join(HERE, "nankan_cyokyo.py"),
             "--place", args.place, "--from", args.date, "--to", args.date,
             "--quiet"], "① 調教と着順を紐付ける")
        run([py, os.path.join(HERE, "paddock.py"), "score",
             "--place", args.place], "② パドックの記録と結果を突き合わせる")
        print("\n⚠️ **恒久ルール1**：結果を見たら、ラップ（ペース）分析も必ず添えること。")
        print("⚠️ **恒久ルール5**：その日の開催を見るだけ。過去開催の一括検証はしない。")


if __name__ == "__main__":
    main()
