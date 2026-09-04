#!/usr/bin/env python3
"""**出走馬の「近N走ぶんの調教」を集める。**＝ 調教の時系列。

    python3 scripts/nankan_cyokyo_hist.py --place 大井 --from 20260831 --to 20260904

出力 `data/cyokyo/hist_{場}_{from}_{to}.jsonl`（1行＝1頭）。

── なぜ重いのか ────────────────────────────────

**競馬ブックには「馬ごとの調教履歴」が無い。**`/db/uma/{id}/crireki`（調教履歴）
は地方馬では中身が空で、`/db/uma/{id}/cyukan`（中間の時計）は**今回ぶんだけ**。

  → 過去走の調教は、**その馬が走ったレースの調教ページ**を引くしかない。
  → どのレースかは馬柱から分からない（楽天の RunRecord に R が無い）ので、
     **その開催日の全12Rを引いて、出走馬を総なめで索引する**。

  実測（大井 2026-08-31〜09-04・695頭・過去5走2,987走）:
      必要な (日付,場) は **404種類** → ×12R ＝ 4,848ページ ≈ 121分
      うち南関4場は **212種類**      → ×12R ＝ 2,544ページ ≈ 64分

⚠️ **南関4場だけを引く。**JRA・門別・名古屋などは `/chihou/` に無いので、
   引いても取れない（404の半分はそれ）。取れないものは `works: null` で残す。

⚠️ **一度引いたページはキャッシュに残る**（`data/cache/keibabook/`）ので、
   途中で止めても次回は続きから。**索引は開催日単位なので無駄が出にくい**
   （1日12ページで、その日の全馬ぶんが手に入る）。

⚠️⚠️ **Cookie が生きている間に走らせること。**切れると途中で全部空になる。
   `--dry-run` で件数だけ先に見られる。

── ⚠️ 正直な線引き ─────────────────────────────

・**調教が効くかどうかは、このリポジトリで一度も検証していない。**
・矢印・短評は競馬ブックの判断であって実測値ではない。人の意見が入る分、
  市場に織り込まれている可能性が高い。
・坂路では時計欄の意味がずれる（`keibabook.CYOKYO_COLS` の括弧内）。
  **`course` を見ずに横並びで比べないこと。**
・恒久ルール5：目の前の開催の出走馬を並べるだけ。過去開催の一括検証はしない。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date as _date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import keibabook as kb                # noqa: E402
from nankeiba.scraping import rakuten as rk                  # noqa: E402

OUT_DIR = "data/cyokyo"
COOKIE = "data/.keibabook_cookie"
#: `/chihou/` から引ける場。**ここに無い場は諦める**（JRA・門別・名古屋ほか）。
NANKAN = ("大井", "川崎", "船橋", "浦和")
DEFAULT_N = 5


def norm(s: str | None) -> str:
    """馬名の突き合わせ用。⚠️ 全角スペース・中黒のゆれで落ちる。"""
    return re.sub(r"[\s　・]", "", s or "")


def ymd_of(s: str) -> str:
    """`'2026-08-20'` → `'20260820'`。既に8桁ならそのまま。"""
    return (s or "").replace("-", "").replace("/", "")[:8]


def days(lo: str, hi: str):
    d = _date(int(lo[:4]), int(lo[4:6]), int(lo[6:8]))
    e = _date(int(hi[:4]), int(hi[4:6]), int(hi[6:8]))
    while d <= e:
        yield d.strftime("%Y%m%d")
        d += timedelta(days=1)


def kb_races(cli, ymd: str, place: str) -> list[str]:
    """その日その場の race_id を1R→12R順で。無ければ空。"""
    try:
        h = cli.get(f"/chihou/nittei/{ymd}")
    except Exception:                                       # noqa: BLE001
        return []
    by: dict[str, list[str]] = defaultdict(list)
    for i in sorted(set(re.findall(r"/chihou/syutuba/(\d+)", h))):
        by[i[:8]].append(i)
    for v in by.values():
        try:
            hdr = kb.parse_race_header(cli.get(f"/chihou/syutuba/{v[0]}")) or {}
        except Exception:                                   # noqa: BLE001
            continue
        if hdr.get("place") == place:
            return v
    return []


def index_meeting(cli, ymd: str, place: str) -> dict[str, dict]:
    """その開催日の**全12R**を引いて `正規化馬名 -> 調教` を作る。

    ⚠️ 1頭のために12ページ引くのではなく、**引いた12ページからその日の全馬を
       索引する**。これをやらないと同じページを何度も引く。
    """
    out: dict[str, dict] = {}
    for rno, rid in enumerate(kb_races(cli, ymd, place), 1):
        try:
            rows = kb.parse_cyokyo(cli.get(f"/chihou/cyokyo/1/0/{rid}"))
        except Exception:                                   # noqa: BLE001
            continue
        for h in rows:
            h["src_race"] = rno
            out[norm(h["name"])] = h
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="出走馬の近N走ぶんの調教を集める")
    ap.add_argument("--place", default="大井")
    ap.add_argument("--from", dest="lo", required=True, help="YYYYMMDD")
    ap.add_argument("--to", dest="hi", required=True, help="YYYYMMDD")
    ap.add_argument("-n", type=int, default=DEFAULT_N, help=f"近N走（既定 {DEFAULT_N}）")
    ap.add_argument("--dry-run", action="store_true", help="件数だけ数えて終わる")
    args = ap.parse_args()

    rcli = rk.KeibaRakuten()

    # ── ① 対象開催の出走馬と、その近N走を集める（楽天・Cookie不要）
    horses: list[dict] = []
    need: set[tuple[str, str]] = set()
    for ymd in days(args.lo, args.hi):
        for rno in range(1, 13):
            try:
                rid = rcli.find_race_id(ymd, args.place, rno)
                card = rk.parse_card(rcli.get(f"/race_card/list/RACEID/{rid}"))
            except Exception:                               # noqa: BLE001
                continue
            for e in card.get("entries") or []:
                past = []
                for h in (e.get("history") or [])[:args.n]:
                    d, p = ymd_of(h.date), h.place
                    past.append({"date": d, "place": p, "distance": h.distance,
                                 "finish": h.finish_pos, "pop": h.popularity,
                                 "jockey": h.jockey, "weight": h.weight,
                                 "baba": h.baba, "works": None,
                                 "reachable": bool(d and p in NANKAN)})
                    if d and p in NANKAN:
                        need.add((d, p))
                horses.append({"date": ymd, "place": args.place, "race": rno,
                               "umaban": e.get("umaban"), "name": e.get("name"),
                               "pop": e.get("popularity"), "odds": e.get("odds"),
                               "past": past})
    print(f"■ 対象 {len(horses)}頭（延べ）／引く開催日 {len(need)}種類"
          f" ≈ {len(need)*12}ページ ≈ {round(len(need)*12*1.5/60)}分",
          file=sys.stderr)
    if args.dry_run:
        return
    if not os.path.exists(COOKIE):
        print(f"⚠️ {COOKIE} がありません。キャッシュ済みぶんしか取れません。",
              file=sys.stderr)
    cli = (kb.KeibabookClient.from_cookie_file(COOKIE)
           if os.path.exists(COOKIE) else kb.KeibabookClient(""))

    # ── ② 開催日ごとに索引を作る（ここが重い。キャッシュで再開できる）
    idx: dict[tuple[str, str], dict] = {}
    for k, (d, p) in enumerate(sorted(need), 1):
        idx[(d, p)] = index_meeting(cli, d, p)
        print(f"  [{k}/{len(need)}] {d} {p} → {len(idx[(d,p)])}頭", file=sys.stderr)

    # ── ③ 紐付ける
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"hist_{args.place}_{args.lo}_{args.hi}.jsonl")
    hit = tot = 0
    with open(path, "w", encoding="utf-8") as f:
        for h in horses:
            for r in h["past"]:
                tot += 1
                got = idx.get((r["date"], r["place"]), {}).get(norm(h["name"]))
                if got:
                    r["works"] = got.get("works")
                    r["tanpyo"] = got.get("tanpyo")
                    r["arrow"] = got.get("arrow")
                    r["awase"] = got.get("awase")
                    hit += 1
            f.write(json.dumps(h, ensure_ascii=False) + "\n")
    print(f"\n■ {path}\n  {len(horses)}頭／過去走 {tot}走のうち"
          f" **調教が付いた {hit}走**（{hit/max(tot,1)*100:.1f}%）", file=sys.stderr)
    print("⚠️ 付かなかったぶんはJRA・門別・名古屋など /chihou/ に無い場か、"
          "提供外の日。**works: null のまま残してある。**", file=sys.stderr)


if __name__ == "__main__":
    main()
