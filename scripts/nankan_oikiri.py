#!/usr/bin/env python3
"""**追い切り（☆）どうしを、レースをまたいで比べる。**その馬個体の上下。

    python3 scripts/nankan_oikiri.py --place 大井 --date 20260904
    python3 scripts/nankan_oikiri.py --place 大井 --date 20260904 --race 11

`data/cache/keibabook/` にあるぶんだけで動く（**取りに行かない**ので、
`nankan_cyokyo_hist.py` の巡回と同時に回してよい）。

── なぜ ☆ どうしなのか（2026-09-04 に判明）─────────────────

**1レース分のページの中で引き算しても、上昇は測れない。**

`中間の時計` は「乗り込み」と「追い切り」が混ざった列で、**脚色では強度が
揃わない**。ラブリールチア（大井 9/4 11R）の3本はすべて「小林坂・良・馬なり」:

        8/23   2F 27.5   「変わりなく順調」
        8/30   2F 29.4   「上がりに重点置く」   ← 坂路2本目
      ☆ 8/30   2F 22.8   「好時計マーク」       ← 追い切り

  同じ「馬なり」で 22.8 と 29.4。前者は本気の1本、後者はただの周回。
  引き算して **「-4.7秒 速くなった」と誤報した**（`nankan_cyokyo_trend.py`）。

  **☆ は1レースに1本で、役割が固定されている**（その週の本気の1本）。
  だから ☆ どうしなら比較になる:

        前々走の☆  →  前走の☆  →  今回の☆

── ⚠️ それでも揃えないといけないもの ────────────────────

  コース   大井外 / 小林坂 / 船橋外 …   **坂路と平場は別物**
  馬場     良 / 稍 / 重 / 不
  欄       3F(2F) か 1F(1F) か。**同じ欄どうしでしか引かない**

  ⚠️ 脚色（馬なり／強め／一杯）は**揃えない**。☆は毎回その週の本気の1本
     なので役割が同じであり、脚色の違いは「今回どれだけ攻めたか」という
     情報そのもの。揃えると本数が消える。**代わりに必ず併記する。**

  ⚠️ 揃うのは一部だけ。**揃わない馬は判定不能と出す。0で埋めない。**

── ⚠️ 正直な線引き ─────────────────────────────

・**調教の時計が効くかどうかは、このリポジトリで一度も検証していない。**
・他馬・市場とは比べていない。1頭の中だけの比較。
・矢印と短評は競馬ブックの判断なので使わない（人気で揃えたら消えた。
  1〜3人気で ↗52% < →61%、692頭）。ここで見るのは**測った数字だけ**。
・恒久ルール5：目の前の開催を見るだけ。過去開催の一括検証はしない。
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import keibabook as kb                # noqa: E402
from nankeiba.scraping import rakuten as rk                  # noqa: E402

CACHE = "data/cache/keibabook"
#: `/chihou/` から引ける場。ここに無い場（JRA・門別ほか）は諦める。
NANKAN = ("大井", "川崎", "船橋", "浦和")
#: 速さを代表させる欄。**上から順に、埋まっている最初のものを使う。**
PREF = ("3F(2F)", "1F(1F)", "半哩(3F)", "5F(4F)")
DEFAULT_N = 5


def norm(s: str | None) -> str:
    return re.sub(r"[\s　・]", "", s or "")


def cached(path: str) -> str | None:
    """**キャッシュにある時だけ読む。**取りに行かない（巡回とぶつけない）。"""
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


def oikiri(h: dict | None) -> dict | None:
    """その馬のその開催の**追い切り（☆）1本**。無ければ None。"""
    if not h:
        return None
    for w in reversed(h.get("works") or []):
        if w.get("oikiri"):
            return w
    return None


def pick(w: dict) -> tuple[str, float] | None:
    for k in PREF:
        v = w["times"].get(k)
        if v is not None:
            return k, v
    return None


def compare(seq: list[tuple]) -> str:
    """`[(ラベル, ☆), …]` を古い順で受け、比較できる組だけで差を言う。

    ⚠️ **(コース, 馬場, 欄) が同じ最後の2本**でだけ引く。揃わなければ判定不能。
    """
    pts = []
    for lab, w in seq:
        p = pick(w)
        if p:
            pts.append((lab, w, p[0], p[1]))
    for i in range(len(pts) - 1, 0, -1):
        a, b = pts[i - 1], pts[i]
        if (a[1].get("course"), a[1].get("baba"), a[2]) == \
           (b[1].get("course"), b[1].get("baba"), b[2]):
            d = b[3] - a[3]
            word = "速く" if d < 0 else ("遅く" if d > 0 else "変わらず")
            return (f"{a[1]['course']}・{a[1]['baba']}・{a[2]}　"
                    f"{a[3]:.1f}（{a[1].get('asiiro') or '?'}）→ "
                    f"{b[3]:.1f}（{b[1].get('asiiro') or '?'}）"
                    f"　**{d:+.1f}秒 {word}**")
    return "判定不能（同条件の☆が2本そろわない）"


def main() -> None:
    ap = argparse.ArgumentParser(description="追い切りどうしをレースまたぎで比べる")
    ap.add_argument("--place", default="大井")
    ap.add_argument("--date", required=True, help="YYYYMMDD")
    ap.add_argument("--race", type=int)
    ap.add_argument("-n", type=int, default=DEFAULT_N, help=f"近N走（既定 {DEFAULT_N}）")
    ap.add_argument("--only", action="store_true", help="判定できた馬だけ")
    args = ap.parse_args()

    rc = rk.KeibaRakuten()
    idx: dict[tuple, dict] = {}
    ok = ng = 0
    for rno in ([args.race] if args.race else range(1, 13)):
        try:
            rid = rc.find_race_id(args.date, args.place, rno)
            card = rk.parse_card(rc.get(f"/race_card/list/RACEID/{rid}"))
        except Exception:                                   # noqa: BLE001
            continue
        cur = index(args.date, args.place)
        printed = False
        for e in card.get("entries") or []:
            nm = norm(e.get("name"))
            seq = []
            for h in reversed((e.get("history") or [])[:args.n]):   # 古い順
                d = (h.date or "").replace("-", "")
                if not d or h.place not in NANKAN:
                    continue
                if (d, h.place) not in idx:
                    idx[(d, h.place)] = index(d, h.place)
                w = oikiri(idx[(d, h.place)].get(nm))
                if w:
                    seq.append((f"{h.date} {h.place} {h.finish_pos or '-'}着", w))
            w = oikiri(cur.get(nm))
            if w:
                seq.append(("★今回", w))
            desc = compare(seq)
            judged = "判定不能" not in desc
            ok += judged
            ng += not judged
            if args.only and not judged:
                continue
            if not printed:
                printed = True
                print(f"\n{'='*98}\n {args.place} {args.date}  {rno}R\n{'='*98}")
            pop = f"{e['popularity']}人気" if e.get("popularity") else ""
            print(f"\n {e.get('umaban') or '':>2} {e.get('name',''):<14}{pop:>7}"
                  f"   {desc}")
            for lab, w in seq:
                p = pick(w)
                print(f"      {lab:<22}{(w.get('course') or ''):<7}"
                      f"{(w.get('baba') or ''):<3}{(w.get('asiiro') or ''):<5}"
                      f"{(f'{p[0]} {p[1]:.1f}' if p else ''):<16}"
                      f"{w.get('note') or ''}")
            if not seq:
                print("      （南関4場の過去走が無いか、そのページが未取得）")

    print(f"\n■ 判定できた {ok}頭 ／ 判定不能 {ng}頭"
          f"（{ok/max(ok+ng,1)*100:.0f}%）", file=sys.stderr)
    print("⚠️ 未取得の開催があると判定不能が増える。"
          "`nankan_cyokyo_hist.py` を回してキャッシュを埋めること。", file=sys.stderr)
    print("⚠️ 調教の時計が効くかどうかは未検証。", file=sys.stderr)


if __name__ == "__main__":
    main()
