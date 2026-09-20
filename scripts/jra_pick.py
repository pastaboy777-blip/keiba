#!/usr/bin/env python3
"""**これから走るJRAの1日から「中7週以上あけた馬」を拾う。**

    python3 scripts/jra_pick.py --date 20260921
    python3 scripts/jra_pick.py --date 20260921 --race 10
    python3 scripts/jra_pick.py --date 20260921 --away      # 逆の地区だけ

netkeiba の公開ページだけで動く（Cookie 不要）。**発走前に使う道具。**
結果の答え合わせは `scripts/jra_week.py` の担当。

── 何を拾うか ─────────────────────────────────

ユーザー指定（2026-09-20）。`jra_week.py` で今週の中央618頭を測った結果、
**爆走（5人気以下で3着内）に効いたのは次の2つだけ**だった:

    **中7週以上あけた**       15.6% (22/141)   全体 12.7%   +4.0pt / 1.06SE
    **所属と逆の地区で走る**    16.7% (8/48)                 +4.5pt / 0.80SE
    **両方**              **21.7% (5/23)**              ベースの1.7倍

    （参考・効かなかったもの）
    前走で負けている          12.9% (37/286)   −1.9pt
    前走と違う競馬場          12.8% (36/282)   −2.8pt
    その競馬場での好走歴       人気帯で割ると4帯すべてマイナス

⚠️⚠️ **「中7週」は「7週」ではない。**中N週は**N+1週**。中7週＝8週。
   7週以上で測ると +2.6pt / 0.71SE、8週以上だと +4.0pt / 1.06SE で、
   **境界は1週後ろ**だった。ユーザーの言い方のほうが正しかった（2026-09-20）。

⚠️⚠️ **n=23 で5頭。**ベースライン12.7%なら期待2.9頭なので、**まだ誤差の中**。
   この道具は「当たる馬を出す」ものではなく、**同じ条件の馬を毎週同じ基準で
   拾って記録に残す**ためのもの。`jra_week.py --pool` で積む。

⚠️ **前走で負けている・前走と違う競馬場は条件に入れない。**今週の実測では
   どちらもマイナスで、中7週×逆地区に「前走負け」を足すと
   21.7%→12.5%(2/16) に落ちた。中島理論の「チャレンジャーの立場」という
   読み自体は生きているが、**それを作るのは負けたことではなく間隔と遠征**。

── 地区 ──────────────────────────────────────

    関東  中山・東京・福島・新潟      ← 美浦所属のホーム
    関西  京都・阪神・中京・小倉      ← 栗東所属のホーム
    北    札幌・函館               ← どちらからも遠いので遠征扱いにしない
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jra_week as W                                      # noqa: E402

#: 中N週。**N+1週が実際の間隔。**中7週＝8週。
NAKA_WEEKS = 7
MIN_WEEKS = NAKA_WEEKS + 1


def naka(weeks: float | None) -> str:
    """実際の週数 → 「中N週」表記。"""
    if weeks is None:
        return "—"
    n = int(round(weeks)) - 1
    return "連闘" if n <= 0 else f"中{n}週"


def scan(date: str, only_race: int | None = None) -> list[dict]:
    """その日の全レースから1頭ずつ拾う。"""
    out: list[dict] = []
    for rid in W.race_ids(date):
        place = W.JYO.get(rid[4:6], rid[4:6])
        rno = int(rid[10:12])
        if only_race and rno != only_race:
            continue
        h = W.get(f"https://race.netkeiba.com/race/shutuba_past.html?race_id={rid}",
                  f"past_{rid}")
        nm = re.search(r"RaceName[^>]*>\s*([^<]{2,30})", h)
        d1 = re.search(r"RaceData01.*?>(.*?)</div>", h, re.S)
        seen: set[str] = set()
        for row in re.findall(r'<tr[^>]*class="[^"]*HorseList.*?</tr>', h, re.S):
            hn = re.search(r'/horse/\d+/?"[^>]*>\s*([^<]{2,24}?)\s*<', row, re.S)
            if not hn or hn.group(1) in seen:
                continue
            seen.add(hn.group(1))
            info = re.search(r'class="Horse_Info".*?</td>', row, re.S)
            it = W._txt(info.group(0)) if info else ""
            bel = re.search(r"(美浦|栗東)・(\S+)", it)
            # ⚠️ 馬番は Waku セルの**次**の td。除外・取消だと形が崩れるので
            #    取れなければ None のまま出す（落とさない）。
            um = re.search(r'<td[^>]*class="Waku[^"]*"[^>]*>.*?</td>\s*'
                           r'<td[^>]*>\s*(\d+)\s*</td>', row, re.S)
            jk = re.search(r'class="Jockey"[^>]*>(.*?)</td>', row, re.S)
            jt = W._txt(jk.group(1)) if jk else ""
            runs = []
            for cls, cell in re.findall(
                    r'<td[^>]*class="(Past[^"]*)"[^>]*>(.*?)</td>', row, re.S):
                d = re.search(r"<span>([\d.]+)&nbsp;(\S+?)</span>", cell)
                if not d:
                    continue
                t = W._txt(cell)
                pop = re.search(r"(\d+)頭\s*(\d+)番\s*(\d+)人", t)
                rk = re.search(r"Ranking_(\d+)", cls)
                runs.append({"date": d.group(1).replace(".", "-"),
                             "place": d.group(2),
                             "pop": int(pop.group(3)) if pop else None,
                             "finish": int(rk.group(1)) if rk else None})
            last = runs[0] if runs else None
            wk = W.weeks_between(last["date"], date) if last else None
            belong = bel.group(1) if bel else None
            out.append({
                "place": place, "rno": rno, "um": int(um.group(1)) if um else None,
                "name": hn.group(1), "belong": belong, "jockey": jt,
                "weeks": wk, "last": last, "runs": runs,
                "race": W._txt(nm.group(1)) if nm else "",
                "cond": (W._txt(d1.group(1))[:34] if d1 else ""),
                "away": (belong in W.BELONG and W.AREA.get(place) is not None
                         and W.BELONG[belong] != W.AREA[place]),
                "wdiff": (lambda m: int(m.group(2)) if m else None)(
                    re.search(r"(\d{3})kg\s*\(([-+]?\d+)\)", it)),
            })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="中7週以上あけた馬を拾う")
    ap.add_argument("--date", required=True, help="YYYYMMDD（これから走る日）")
    ap.add_argument("--race", type=int)
    ap.add_argument("--away", action="store_true", help="所属と逆の地区だけ")
    ap.add_argument("--weeks", type=int, default=NAKA_WEEKS,
                    help=f"中N週以上（既定 {NAKA_WEEKS}）")
    args = ap.parse_args()

    rows = scan(args.date, args.race)
    if not rows:
        print("取れませんでした（開催が無いか、まだ出馬表が出ていない）", file=sys.stderr)
        return
    lo = args.weeks + 1
    hit = [r for r in rows if r["weeks"] is not None and r["weeks"] >= lo]
    if args.away:
        hit = [r for r in hit if r["away"]]

    places = sorted({r["place"] for r in rows})
    print(f"\n{'='*94}\n {args.date}　{'・'.join(places)}　"
          f"{len({(r['place'], r['rno']) for r in rows})}レース／{len(rows)}頭"
          f"\n 中{args.weeks}週以上（＝{lo}週以上）あけた馬 **{len(hit)}頭**"
          f"　うち所属と逆の地区 **{sum(1 for r in hit if r['away'])}頭**\n{'='*94}")

    cur = None
    for r in sorted(hit, key=lambda x: (x["place"], x["rno"],
                                        -(x["weeks"] or 0))):
        key = (r["place"], r["rno"])
        if key != cur:
            cur = key
            print(f"\n── {r['place']}{r['rno']:>2}R {r['race']}　{r['cond']}")
        L = r["last"]
        tag = "**逆の地区**" if r["away"] else ""
        # ⚠️ **年を落とさない。**中52週の馬の前走を今月と誤読する。
        ymd = L["date"][5:] if L["date"][:4] == args.date[:4] else L["date"]
        past = (f"前走 {ymd} {L['place']}"
                f"{(str(L['pop'])+'人気') if L['pop'] else ''}"
                f"{(str(L['finish'])+'着') if L['finish'] else '着外'}")
        print(f"   {(r['um'] if r['um'] else '—'):>3} {r['name']:<15}"
              f"{(r['belong'] or '?'):<3}{naka(r['weeks']):<7}"
              f"({r['weeks']:>4.1f}週)  {past:<28}{tag}")

    print(f"\n{'─'*94}")
    print("⚠️ **当たる馬を出す道具ではない。**今週の実測で 中7週以上×逆の地区 は\n"
          "   爆走率 21.7%（全体12.7%）だったが **n=23で5頭**、期待2.9頭なので"
          "まだ誤差の中。\n"
          "   毎週同じ基準で拾って `jra_week.py --pool` に積むための道具。",
          file=sys.stderr)


if __name__ == "__main__":
    main()
