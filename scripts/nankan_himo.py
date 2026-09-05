#!/usr/bin/env python3
"""**馬1頭ごとに、近5走の調教内容をそのまま並べる。**ヒモ付けの本体。

    python3 scripts/nankan_himo.py --place 大井 --date 20260904
    python3 scripts/nankan_himo.py --place 大井 --date 20260904 --race 11
    python3 scripts/nankan_himo.py --place 大井 --date 20260904 --jsonl out.jsonl

判定も分析もしない。**過去5走それぞれの調教を、その馬の下に並べるだけ。**

── 読むもの ────────────────────────────────────

    出走馬と過去5走     楽天（Cookie不要）
    各過去走の調教      競馬ブック。**`data/cache/keibabook/` にあるぶんだけ**

⚠️ **取りに行かない。**キャッシュだけを見るので、`nankan_cyokyo_hist.py` の
   巡回と同時に回してよい。巡回が進むほど埋まる。

⚠️ 未取得の過去走は `〈未取得〉` と出す。**空欄と区別する。**
   JRA・門別・名古屋などは `/chihou/` に無いので永久に埋まらない → `〈対象外〉`。

── 1行の見方 ───────────────────────────────────

    ☆   その週の追い切り（1レースに1本）
    *   調教が11日以上空いた
    【】 時計を課していない週（「中間軽め」など）

    時計は表の見出しそのまま。⚠️ **坂路と平場で欄の意味がずれる**
    （`keibabook.CYOKYO_COLS` の括弧内が坂路のときの意味）。
    コースを見ずに横並びで比べないこと。

⚠️ 調教が効くかどうかは、このリポジトリで一度も検証していない。
   矢印と短評は競馬ブックの判断であって実測値ではない。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import keibabook as kb                # noqa: E402
from nankeiba.scraping import rakuten as rk                  # noqa: E402

CACHE = "data/cache/keibabook"
#: `/chihou/` から引ける場。ここに無い場は永久に埋まらない。
NANKAN = ("大井", "川崎", "船橋", "浦和")
DEFAULT_N = 5


def norm(s: str | None) -> str:
    return re.sub(r"[\s　・]", "", s or "")


def cached(path: str) -> str | None:
    """**キャッシュにある時だけ読む。**取りに行かない。"""
    p = os.path.join(CACHE, re.sub(r"[^0-9A-Za-z]+", "_", path).strip("_") + ".html")
    return open(p, encoding="utf-8").read() if os.path.exists(p) else None


def index(ymd: str, place: str) -> dict:
    """その開催日の全12Rから `正規化馬名 -> 調教` を作る（キャッシュのみ）。"""
    h = cached(f"/chihou/nittei/{ymd}")
    if not h:
        return {}
    by: dict[str, list[str]] = {}
    for i in sorted(set(re.findall(r"/chihou/syutuba/(\d+)", h))):
        by.setdefault(i[:8], []).append(i)
    for v in by.values():
        s = cached(f"/chihou/syutuba/{v[0]}")
        if not s or (kb.parse_race_header(s) or {}).get("place") != place:
            continue
        out = {}
        for rid in v:
            t = cached(f"/chihou/cyokyo/1/0/{rid}")
            if t:
                for x in kb.parse_cyokyo(t):
                    out[norm(x["name"])] = x
        return out
    return {}


def times(w: dict) -> str:
    """埋まっている時計欄だけを `欄=秒` で。**空欄は出さない。**"""
    if w.get("no_time_note"):
        return f"【{w['no_time_note']}】"
    return " ".join(f"{k.split('(')[0]}{v}"
                    for k, v in w["times_raw"].items() if v)


def main() -> None:
    ap = argparse.ArgumentParser(description="馬ごとに近N走の調教を並べる")
    ap.add_argument("--place", default="大井")
    ap.add_argument("--date", required=True, help="YYYYMMDD")
    ap.add_argument("--race", type=int, help="指定しなければ全12R")
    ap.add_argument("-n", type=int, default=DEFAULT_N, help=f"近N走（既定 {DEFAULT_N}）")
    ap.add_argument("--jsonl", help="この名前で JSONL にも書く")
    args = ap.parse_args()

    rc = rk.KeibaRakuten()
    idx: dict[tuple, dict] = {}
    out = open(args.jsonl, "w", encoding="utf-8") if args.jsonl else None
    filled = total = 0

    def today_weight(rno: int) -> dict:
        """当日の馬体重（結果ページから）。**発走前は空**。

        ⚠️ 出馬表には馬体重が無い。当日ぶんは結果が出るまで取れないので、
           取れなければ黙って空にする（0で埋めない）。
        """
        try:
            rid = rc.find_race_id(args.date, args.place, rno)
            res = rk.parse_result(rc.get(f"/race_performance/list/RACEID/{rid}"))
            return {norm(r.get("name")): (r.get("weight"), r.get("weight_diff"))
                    for r in res}
        except Exception:                                   # noqa: BLE001
            return {}

    for rno in ([args.race] if args.race else range(1, 13)):
        try:
            rid = rc.find_race_id(args.date, args.place, rno)
            card = rk.parse_card(rc.get(f"/race_card/list/RACEID/{rid}"))
        except Exception:                                   # noqa: BLE001
            continue
        ents = card.get("entries") or []
        if not ents:
            continue
        hdr = card.get("header") or {}
        print(f"\n{'='*100}\n {args.place} {args.date}  {rno}R  "
              f"{hdr.get('race_class') or ''} {hdr.get('distance') or ''}m\n{'='*100}")
        cur = index(args.date, args.place)
        tw = today_weight(rno)
        for e in ents:
            nm = norm(e.get("name"))
            pop = f"{e['popularity']}人気" if e.get("popularity") else ""
            # 馬体重の推移（古い順）。**このリポジトリで唯一の検証済み材料**
            ws = [(h.date, h.weight) for h in
                  reversed((e.get("history") or [])[:args.n]) if h.weight]
            w_now = tw.get(nm, (None, None))
            line = "→".join(str(w) for _, w in ws)
            if w_now[0]:
                line += f"→**{w_now[0]}**"
            print(f"\n■ {e.get('umaban') or '':>2} {e.get('name','')}　{pop}"
                  + (f"　馬体 {line}" if line else "　馬体〈不明〉"))
            rec = {"date": args.date, "place": args.place, "race": rno,
                   "umaban": e.get("umaban"), "name": e.get("name"),
                   "pop": e.get("popularity"), "past": []}
            # 今回ぶん
            for lab, got, meta in ([("★今回", cur.get(nm), None)] +
                                   [(None, None, h) for h in
                                    reversed((e.get("history") or [])[:args.n])]):
                if meta is not None:
                    d = (meta.date or "").replace("-", "")
                    # ⚠️ 馬体重の増減は**前走との差**。楽天の馬柱は増減を持たない
                    #    ので、並べた列から自分で引く。取れなければ書かない。
                    wt = ""
                    if meta.weight:
                        wt = f" 馬体{meta.weight}"
                        pw = [w for dd, w in ws if dd < (meta.date or "")]
                        if pw:
                            dw = meta.weight - pw[-1]
                            wt += f"({dw:+d})" if dw else "( 0)"
                    lab = (f"{meta.date} {meta.place} {meta.distance}m "
                           f"{meta.baba or ''} {meta.popularity or '-'}人気"
                           f"→{meta.finish_pos or '-'}着{wt}")
                    if meta.place not in NANKAN:
                        print(f"  {lab}   〈対象外・{meta.place}〉")
                        rec["past"].append({"label": lab, "state": "対象外"})
                        total += 1
                        continue
                    if (d, meta.place) not in idx:
                        idx[(d, meta.place)] = index(d, meta.place)
                    got = idx[(d, meta.place)].get(nm)
                    total += 1
                    if not got:
                        print(f"  {lab}   〈未取得〉")
                        rec["past"].append({"label": lab, "state": "未取得"})
                        continue
                    filled += 1
                elif not got:
                    print("  ★今回   〈未取得〉")
                    continue
                print(f"  {lab}   〔{got.get('tanpyo') or ''}〕"
                      f"{got.get('arrow') or ''}")
                for w in got.get("works") or []:
                    star = "☆" if w["oikiri"] else "  "
                    print(f"      {star}{(w['date_raw'] or ''):<10}"
                          f"{(w.get('course') or ''):<7}{(w.get('baba') or ''):<3}"
                          f"{times(w):<34}{(w.get('asiiro') or ''):<5}"
                          f"{w.get('note') or ''}")
                for a in got.get("awase") or []:
                    print(f"        併走 {a}")
                rec["past"].append({"label": lab, "state": "取得",
                                    "tanpyo": got.get("tanpyo"),
                                    "arrow": got.get("arrow"),
                                    "works": got.get("works"),
                                    "awase": got.get("awase")})
            if out:
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if out:
        out.close()
        print(f"\n{args.jsonl} に書きました。", file=sys.stderr)
    print(f"\n■ 過去走 {total}走のうち **調教が付いた {filled}走**"
          f"（{filled/max(total,1)*100:.0f}%）", file=sys.stderr)
    print("⚠️ 〈未取得〉は nankan_cyokyo_hist.py の巡回が進めば埋まる。"
          "〈対象外〉はJRA・門別など /chihou/ に無い場なので埋まらない。",
          file=sys.stderr)


if __name__ == "__main__":
    main()
