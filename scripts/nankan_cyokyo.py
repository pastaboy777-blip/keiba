#!/usr/bin/env python3
"""**出走馬に、調教内容を紐付ける。**競馬ブック（調教）× 楽天（人気・着順）。

    python3 scripts/nankan_cyokyo.py --place 大井 --from 20260831 --to 20260904
    python3 scripts/nankan_cyokyo.py --place 大井 --from 20260904 --to 20260904 --race 1

出力は画面と `data/cyokyo/{日付}_{場}.jsonl`（1行＝1頭）。

── なぜ2つのサイトを混ぜるのか ───────────────────────────

    調教      競馬ブック  **会員ページ**。`data/.keibabook_cookie` が要る
    人気・着順 楽天        無料。Cookie 不要

⚠️ **調教は一度取ったらキャッシュに残る**（`data/cache/keibabook/`、gitignore済）。
   Cookie は期限切れするので、**開催が終わる前に取っておく**こと。
   取り終えたら Cookie は無効化してよい（ログアウト→再ログインで死ぬ）。

── 何が紐付くか ────────────────────────────────

競馬ブックの調教ページから取れるもの:

    tanpyo   追い切り短評   「攻め常に動く」など、競馬ブックの一言
    arrow    矢印           ↗ → ↘。**競馬ブックが付けた状態の向き**
    works    調教1本ずつ    日付・コース・馬場・時計・回り位置・脚色・短評
    awase    併走馬         「〇〇（3歳）馬なりの内同入」
    gap      *印            **調教が11日以上空いた**（表の凡例より）
    oikiri   ☆             その週の追い切り（最終追い）

⚠️⚠️ **坂路では時計欄の意味がずれる。**見出しは 6F(坂路) / 5F(4F) / 半哩(3F) /
   3F(2F) / 1F(1F) で、括弧内が坂路のときの意味。**`course` を見ずに時計を
   横並びで比べないこと**（「小林坂」と「小林外」は別物）。
   本数欄に `'2回'` のような非数値も入るので、`times_raw` も残してある。

── ⚠️ 正直な線引き ─────────────────────────────

・**調教が効くかどうかは、このリポジトリで一度も検証していない。**
  これは材料を並べる道具であって、「この時計なら買い」ではない。
・矢印と短評は**競馬ブックの判断**であって実測値ではない。人の意見が
  入っている分、市場に既に織り込まれている可能性が高い。
・恒久ルール5：**目の前の開催**を並べるだけ。過去開催の一括検証はしない。
  着順を一緒に出すのは「その日のレースをその日の材料で説明する」ため。
  **回収率や勝率の集計はここではやらない。**
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date as _date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import keibabook as kb                # noqa: E402
from nankeiba.scraping import rakuten as rk                  # noqa: E402

OUT_DIR = "data/cyokyo"
COOKIE = "data/.keibabook_cookie"
#: 1頭あたり何本まで並べるか。ページに載っているのは会員種別で変わる。
DEFAULT_N = 5


def norm(s: str | None) -> str:
    """馬名を突き合わせ用に正規化。⚠️ 全角スペース・中黒のゆれで落ちる。"""
    return re.sub(r"[\s　・]", "", s or "")


def kb_races(cli, ymd: str, place: str) -> list[str]:
    """その日その場の race_id を1R→12Rの順で返す。無ければ空。"""
    h = cli.get(f"/chihou/nittei/{ymd}")
    ids = sorted(set(re.findall(r"/chihou/syutuba/(\d+)", h)))
    by: dict[str, list[str]] = {}
    for i in ids:
        by.setdefault(i[:8], []).append(i)
    for v in by.values():
        hdr = kb.parse_race_header(cli.get(f"/chihou/syutuba/{v[0]}")) or {}
        if hdr.get("place") == place:
            return v
    return []


def rakuten_side(rcli, ymd: str, place: str, rno: int) -> dict:
    """楽天から `正規化馬名 -> {人気, 着順, オッズ}`。取れなければ空。"""
    try:
        rid = rcli.find_race_id(ymd, place, rno)
    except Exception:                                       # noqa: BLE001
        return {}
    out: dict[str, dict] = {}
    try:
        card = rk.parse_card(rcli.get(f"/race_card/list/RACEID/{rid}"))
        for e in card.get("entries") or []:
            out[norm(e.get("name"))] = {"pop": e.get("popularity"),
                                        "odds": e.get("odds"), "finish": None}
    except Exception:                                       # noqa: BLE001
        pass
    try:
        for r in rk.parse_result(rcli.get(f"/race_performance/list/RACEID/{rid}")):
            d = out.setdefault(norm(r.get("name")), {"pop": None, "odds": None})
            d["finish"] = r.get("finish")
            d["pop"] = d.get("pop") or r.get("popularity")
    except Exception:                                       # noqa: BLE001
        pass
    return out


def fmt_times(w: dict) -> str:
    """時計7欄を固定幅で。**空欄は空欄のまま**（0で埋めない）。"""
    return "".join(f"{(w['times_raw'].get(k) or ''):>7}" for k in kb.CYOKYO_COLS)


def show(rows: list[dict], n: int) -> None:
    for h in rows:
        side = h.get("race_side") or {}
        pop = f"{side['pop']}人気" if side.get("pop") else ""
        fin = f"→{side['finish']}着" if side.get("finish") else ""
        arrow = h.get("arrow") or ""
        print(f"\n  {h.get('umaban') or '':>2} {h['name']:<14}{pop:>7}{fin:>6}"
              f"   {arrow}  「{h.get('tanpyo') or ''}」")
        for w in h["works"][-n:]:
            star = "☆" if w["oikiri"] else (" *" if w["gap"] else "  ")
            print(f"   {star}{(w['date_raw'] or ''):<10}{(w['course'] or ''):<7}"
                  f"{(w['baba'] or ''):<3}{fmt_times(w)}  "
                  f"{(w['asiiro'] or ''):<5}{w['note'] or ''}")
        for a in h["awase"]:
            print(f"      併走 {a}")


def main() -> None:
    ap = argparse.ArgumentParser(description="出走馬に調教内容を紐付ける")
    ap.add_argument("--place", default="大井")
    ap.add_argument("--from", dest="lo", required=True, help="YYYYMMDD")
    ap.add_argument("--to", dest="hi", required=True, help="YYYYMMDD")
    ap.add_argument("--race", type=int, help="指定しなければ全12R")
    ap.add_argument("-n", type=int, default=DEFAULT_N,
                    help=f"1頭あたり何本並べるか（既定 {DEFAULT_N}）")
    ap.add_argument("--quiet", action="store_true", help="画面出力を省いて書くだけ")
    args = ap.parse_args()

    if not os.path.exists(COOKIE):
        print(f"⚠️ {COOKIE} がありません。調教は会員ページなので Cookie が要ります。",
              file=sys.stderr)
        print("   （既にキャッシュ済みなら、この先も動きます）", file=sys.stderr)
    cli = (kb.KeibabookClient.from_cookie_file(COOKIE)
           if os.path.exists(COOKIE) else kb.KeibabookClient(""))
    rcli = rk.KeibaRakuten()
    os.makedirs(OUT_DIR, exist_ok=True)

    d, hi = _date(*map(int, (args.lo[:4], args.lo[4:6], args.lo[6:8]))), \
        _date(*map(int, (args.hi[:4], args.hi[4:6], args.hi[6:8])))
    total = 0
    while d <= hi:
        ymd = d.strftime("%Y%m%d")
        d += timedelta(days=1)
        try:
            ids = kb_races(cli, ymd, args.place)
        except Exception as e:                              # noqa: BLE001
            print(f"{ymd} 日程が取れません（{e}）", file=sys.stderr)
            continue
        if not ids:
            continue
        path = os.path.join(OUT_DIR, f"{ymd}_{args.place}.jsonl")
        wrote = 0
        with open(path, "w", encoding="utf-8") as f:
            for rno, rid in enumerate(ids, 1):
                if args.race and rno != args.race:
                    continue
                try:
                    rows = kb.parse_cyokyo(cli.get(f"/chihou/cyokyo/1/0/{rid}"))
                except Exception:                           # noqa: BLE001
                    rows = []
                if not rows:
                    if not args.quiet:
                        print(f"\n=== {ymd} {args.place} {rno}R  調教なし")
                    continue
                side = rakuten_side(rcli, ymd, args.place, rno)
                for h in rows:
                    h["race_side"] = side.get(norm(h["name"]), {})
                    h.update(date=ymd, place=args.place, race=rno, race_id=rid)
                    f.write(json.dumps(h, ensure_ascii=False) + "\n")
                    wrote += 1
                if not args.quiet:
                    print(f"\n{'='*96}\n {ymd} {args.place} {rno}R"
                          f"     時計欄 → {'  '.join(kb.CYOKYO_COLS)}\n{'='*96}")
                    show(rows, args.n)
        total += wrote
        print(f"\n[{ymd}] {wrote}頭 → {path}", file=sys.stderr)
    print(f"\n合計 {total}頭ぶんを {OUT_DIR}/ に書きました。", file=sys.stderr)
    print("⚠️ 調教が効くかどうかは未検証。矢印と短評は競馬ブックの判断であって"
          "実測値ではない。", file=sys.stderr)


if __name__ == "__main__":
    main()
