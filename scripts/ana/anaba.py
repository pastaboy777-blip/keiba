#!/usr/bin/env python3
"""穴狙い専用 — **指数（マキシマム新聞ベース Engine B）とグリップ血統だけ**を使う。

ユーザー指定の運用（2026-07-27）:
  「マキシマム新聞を基に作った指数とグリップ血統のみで穴を狙う」
  → ⚠️見かけ倒し・🚀速度ショック・H2H序列・当日の厩舎/騎手は**一切使わない**。

穴の定義: **人気薄**（既定は7番人気以下）。§18 の実測どおり、上位人気帯では
どのファクターも lift ≒ 1.0 に潰れ、効果は人気薄にしか現れない。

2つのモード:
  --backtest  キャッシュ済みの過去レースで、指数×グリップの組み合わせを実測する
  （既定）    指定した日付・場の出馬表から、今日の穴候補を出す

    python3 scripts/ana/anaba.py --backtest --places 川崎 大井 船橋 浦和
    python3 scripts/ana/anaba.py --date 20260728 --place 川崎
"""
from __future__ import annotations

import argparse
import glob
import html as _h
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from nankeiba.core import grip, hindex                     # noqa: E402
from nankeiba.core import newspaper as nb                  # noqa: E402
from nankeiba.scraping import rakuten as rk                # noqa: E402

CACHE = "data/cache/rakuten"
ANA_POP = 7          # これ以下の人気（＝数字が大きい）を「穴」とみなす


# ---------------------------------------------------------------------------
# 指数とグリップ（この2つだけ）
# ---------------------------------------------------------------------------

def rate(entries: list[dict], place: str, distance: int, date: str,
         race_no: int) -> list[dict]:
    """出走各馬に 指数・指数順位・グリップ を付けて返す。他のファクターは使わない。"""
    runs = [x for e in entries for x in e["history"]]
    if not runs:
        return []
    model = hindex.SpeedIndexModel.fit(runs)
    pe = [nb.PaperEntry(umaban=e["umaban"], name=e["name"], history=e["history"],
                        sire=e.get("sire"), bms=e.get("bms")) for e in entries]
    card = nb.build_card(
        nb.RaceHeader(place=place, distance=distance or 0, date=date,
                      race_no=race_no, baba=None), pe, model)
    by = {e["umaban"]: e for e in entries}
    out = []
    for v in card.horses:
        idx = v.comp.total if (v.comp and v.comp.total is not None) else v.idx_best5
        if idx is None:
            continue
        e = by[v.entry.umaban]
        s, b = e.get("sire"), e.get("bms")
        out.append(dict(umaban=v.entry.umaban, name=v.entry.name, idx=idx,
                        sire=s, bms=b,
                        grip_sire=grip.is_grip(s), grip_bms=grip.is_grip(b),
                        grip=grip.is_grip(s) or grip.is_grip(b)))
    out.sort(key=lambda r: -r["idx"])
    for n, r in enumerate(out, 1):
        r["rank"] = n
    return out


# ---------------------------------------------------------------------------
# バックテスト
# ---------------------------------------------------------------------------

def _iter_cached(places: set[str]):
    """(place, distance, date, race_no, entries, result) を順に返す。"""
    for pf in sorted(glob.glob(os.path.join(
            CACHE, "race_performance_list_RACEID_*.html"))):
        rid = pf.rsplit("_", 1)[-1].removesuffix(".html")
        cf = os.path.join(CACHE, f"race_card_list_RACEID_{rid}.html")
        if not os.path.exists(cf):
            continue
        try:
            card = rk.parse_card(open(cf, encoding="utf-8").read())
            res = rk.parse_result(open(pf, encoding="utf-8").read())
        except Exception:                        # noqa: BLE001
            continue
        hd = card["header"]
        pl, dist = hd.get("place"), hd.get("distance")
        if not pl or not dist or not res or (places and pl not in places):
            continue
        yield (pl, dist, f"{rid[0:4]}-{rid[4:6]}-{rid[6:8]}",
               hd.get("race_no") or 0, card["entries"], res)


class Tally:
    def __init__(self):
        self.n = self.t3 = self.win = 0

    def add(self, finish: int) -> None:
        self.n += 1
        self.t3 += finish <= 3
        self.win += finish == 1

    def line(self, base: float) -> str:
        if not self.n:
            return f"{'—':>8}"
        p = self.t3 / self.n
        return (f"{self.n:>6}{self.t3:>6}{p:>8.1%}{(p / base if base else 0):>7.2f}"
                f"{self.win:>6}{self.win / self.n:>8.1%}")


def backtest(places: set[str], ana_pop: int) -> None:
    """人気薄に絞ったうえで、指数順位 × グリップ の組み合わせを実測する。"""
    cells: dict[str, Tally] = defaultdict(Tally)
    per_place: dict[tuple, Tally] = defaultdict(Tally)
    base = Tally()
    n_race = 0

    for pl, dist, date, rno, ents, res in _iter_cached(places):
        rated = rate(ents, pl, dist, date, rno)
        if not rated:
            continue
        n_race += 1
        fin = {r["umaban"]: r["finish"] for r in res}
        pop = {r["umaban"]: r.get("popularity") for r in res}
        for r in rated:
            f, p = fin.get(r["umaban"]), pop.get(r["umaban"])
            if f is None or p is None or p < ana_pop:
                continue                      # 穴（人気薄）だけを見る
            base.add(f)
            rk_band = ("指数1位" if r["rank"] == 1 else
                       "指数2-3位" if r["rank"] <= 3 else
                       "指数4-6位" if r["rank"] <= 6 else "指数7位以下")
            g = ("グリップ父" if r["grip_sire"] else
                 "グリップ母父" if r["grip_bms"] else "グリップ無")
            cells[f"{rk_band} × {g}"].add(f)
            cells[rk_band].add(f)
            cells[g].add(f)
            if r["rank"] <= 3 and r["grip"]:
                cells["★指数上位3 × グリップ"].add(f)
                per_place[(pl, "★")].add(f)
            per_place[(pl, "全")].add(f)

    b = base.t3 / base.n if base.n else 0
    print(f"■ 穴（{ana_pop}番人気以下）のみで実測　"
          f"{n_race}レース / 該当 {base.n}頭　複勝率 {b:.1%} ＝ lift 1.00")
    print(f"\n{'':30}{'頭':>6}{'複勝':>6}{'率':>8}{'lift':>7}{'1着':>6}{'勝率':>8}")
    for k in ("指数1位", "指数2-3位", "指数4-6位", "指数7位以下",
              "グリップ父", "グリップ母父", "グリップ無",
              "★指数上位3 × グリップ"):
        if k in cells:
            print(f"  {k:28}{cells[k].line(b)}")
    print()
    for k in sorted(x for x in cells if " × " in x and not x.startswith("★")):
        if cells[k].n >= 30:
            print(f"  {k:28}{cells[k].line(b)}")
    print(f"\n■ 場別の ★指数上位3×グリップ")
    for pl in sorted({p for p, _ in per_place}):
        a, t = per_place[(pl, "★")], per_place[(pl, "全")]
        if not t.n:
            continue
        pb = t.t3 / t.n
        print(f"  {pl:6}全{t.n:>5}頭 複勝{pb:>6.1%}  ／  ★{a.line(pb)}")


# ---------------------------------------------------------------------------
# 当日の穴候補
# ---------------------------------------------------------------------------

def _odds(cli, rid: str) -> dict[int, float]:
    try:
        h = cli.get(f"/odds/tanfuku/RACEID/{rid}", use_cache=False)
    except Exception:                            # noqa: BLE001
        return {}
    txt = re.sub(r"<[^>]+>", "|", _h.unescape(h))
    out: dict[int, float] = {}
    for m in re.finditer(r"\|(\d{1,2})\|[^|]{0,40}?\|([ァ-ヶーА-я\w]{3,14})\|"
                         r"[^|]{0,60}?\|(\d+\.\d)\|", txt):
        out.setdefault(int(m.group(1)), float(m.group(3)))
    return out


def today(date: str, place: str, races: list[int]) -> None:
    cli = rk.KeibaRakuten()
    base = cli.find_race_id(date, place, 1)[:-2]
    d = f"{date[0:4]}-{date[4:6]}-{date[6:8]}"
    print(f"■ {place} {d} — 指数×グリップのみ／穴狙い")
    for rno in races:
        rid = f"{base}{rno:02d}"
        try:
            card = rk.fetch_card(cli, rid)
        except Exception:                        # noqa: BLE001
            continue
        hd, ents = card["header"], card["entries"]
        if not ents:
            continue
        rated = rate(ents, place, hd.get("distance"), d, rno)
        if not rated:
            continue
        od = _odds(cli, rid)
        rank_by_odds = {u: n for n, (u, _) in enumerate(
            sorted(od.items(), key=lambda x: x[1]), 1)}
        print(f"\n{'='*72}\n■ {rno}R ダ{hd.get('distance')}m {len(ents)}頭 "
              f"{hd.get('post_time') or ''}")
        print(f"{'':2}{'指数':>7}{'位':>3} {'馬':13}{'父/母父':30}{'人気':>5}{'単勝':>7}")
        for r in rated:
            g = ("🔩父" if r["grip_sire"] else "🔩母" if r["grip_bms"] else "  ")
            p = rank_by_odds.get(r["umaban"])
            star = "★" if (r["rank"] <= 3 and r["grip"]
                           and (p is None or p >= ANA_POP)) else " "
            print(f"{star}{r['idx']:>7.1f}{r['rank']:>3} {r['umaban']:>2}番"
                  f"{r['name'][:10]:12}"
                  f"{((r['sire'] or '?')[:11] + '/' + (r['bms'] or '?')[:11]):28}"
                  f"{g:4}{(p or '-'):>5}{(od.get(r['umaban']) or '-'):>7}")
        hits = [r for r in rated if r["rank"] <= 3 and r["grip"]]
        if hits:
            print("  ★穴候補: " + " / ".join(
                f"{r['umaban']}番{r['name']}(指数{r['rank']}位)" for r in hits))
        else:
            print("  ★該当なし（指数上位3にグリップ血統がいない）")


def verify(date: str, place: str) -> None:
    """終わった開催を、指数×グリップだけで予想し直して結果と突き合わせる。"""
    cli = rk.KeibaRakuten()
    base = cli.find_race_id(date, place, 1)[:-2]
    d = f"{date[0:4]}-{date[4:6]}-{date[6:8]}"
    print(f"■ {place} {d} — 指数×グリップのみ／穴狙いの答え合わせ")
    star = Tally(); allpop = Tally(); rank3 = Tally(); gripall = Tally()
    lines = []
    for rno in range(1, 13):
        rid = f"{base}{rno:02d}"
        try:
            card = rk.fetch_card(cli, rid)
            res = rk.parse_result(cli.get(
                f"/race_performance/list/RACEID/{rid}", use_cache=False))
        except Exception:                        # noqa: BLE001
            continue
        hd, ents = card["header"], card["entries"]
        if not ents or not res:
            continue
        rated = rate(ents, place, hd.get("distance"), d, rno)
        if not rated:
            continue
        fin = {r["umaban"]: r["finish"] for r in res}
        pop = {r["umaban"]: r.get("popularity") for r in res}
        picks = []
        for r in rated:
            f, p = fin.get(r["umaban"]), pop.get(r["umaban"])
            if f is None or p is None:
                continue
            ana = p >= ANA_POP
            if ana:
                allpop.add(f)
                if r["rank"] <= 3:
                    rank3.add(f)
                if r["grip"]:
                    gripall.add(f)
                if r["rank"] <= 3 and r["grip"]:
                    star.add(f)
                    picks.append((r, p, f))
        w = res[0]
        lines.append((rno, hd.get("distance"), w, picks, rated, pop, fin))

    for rno, dist, w, picks, rated, pop, fin in lines:
        top = rated[0]
        print(f"\n{rno}R ダ{dist}m  1着 {w['umaban']}番{w['name']}"
              f"({w.get('popularity')}人気)"
              f"   指数1位={top['umaban']}番{top['name']}"
              f"({pop.get(top['umaban'])}人気)→{fin.get(top['umaban'])}着")
        if picks:
            for r, p, f in picks:
                print(f"   ★穴 {r['umaban']}番{r['name']}"
                      f" 指数{r['rank']}位 {p}人気 → **{f}着**"
                      f"  {'🔩父' if r['grip_sire'] else '🔩母父'}")
        else:
            print("   ★該当なし")

    b = allpop.t3 / allpop.n if allpop.n else 0
    print(f"\n{'='*72}\n■ 穴（{ANA_POP}番人気以下）だけでの集計"
          f"　母数{allpop.n}頭　複勝率 {b:.1%} ＝ lift 1.00")
    print(f"{'':26}{'頭':>6}{'複勝':>6}{'率':>8}{'lift':>7}{'1着':>6}{'勝率':>8}")
    for k, t in (("指数上位3", rank3), ("グリップ", gripall),
                 ("★指数上位3×グリップ", star)):
        print(f"  {k:24}{t.line(b)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backtest", action="store_true")
    ap.add_argument("--places", nargs="+", default=["川崎", "大井", "船橋", "浦和"])
    ap.add_argument("--ana-pop", type=int, default=ANA_POP)
    ap.add_argument("--date")
    ap.add_argument("--verify", action="store_true",
                    help="--date の開催を、結果と突き合わせて検証する")
    ap.add_argument("--place", default="川崎")
    ap.add_argument("--races", nargs="+", type=int,
                    default=list(range(1, 13)))
    args = ap.parse_args()
    if args.backtest:
        backtest(set(args.places), args.ana_pop)
    elif args.date and args.verify:
        verify(args.date, args.place)
    elif args.date:
        today(args.date, args.place, args.races)
    else:
        ap.error("--backtest か --date のどちらかを指定してください")


if __name__ == "__main__":
    main()
