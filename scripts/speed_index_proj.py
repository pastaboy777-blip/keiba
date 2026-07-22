#!/usr/bin/env python3
"""持ちタイム指数（事前投影版・Engine B）＝各馬の過去走を馬場差B正規化してスピード指数化。

speed_index.py(§14/§17-1)は「終わったレースの走破タイム→指数」だが、本モジュールは
レース"前"に各馬の過去走から指数を投影して軸を出す。核心は §17-1 の仕様どおり：
  指数 = -k(=10) * (走破タイム − (二次パー(距離) + 当日馬場差B))
過去走ごとに、その"開催日×場"の馬場差B[date,place]を speed_index.py と同じ方法
(その日の全馬の median(タイム−PAR)) で算出して引く。Bは場ごとの基準差も吸収するので
大井PARのまま他場の過去走も相対化できる(検証で確定・§6/§14)。

各馬の指数は既定で「正規化済み指数の自己ベスト(max)」を採用(=持ちタイム)。
--agg avg3 で上位3走平均も選べる。

使い方:
  python3 scripts/speed_index_proj.py --date 2026-07-22 --place 大井 --race 11
  python3 scripts/speed_index_proj.py --date 2026-07-22 --place 大井          # 全R top5
  python3 scripts/speed_index_proj.py --date 2026-07-22 --place 大井 --verify  # 実着と答え合わせ
"""
import sys, re, argparse, statistics
sys.path.insert(0, "src")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from bs4 import BeautifulSoup

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"
K = 10.0


def PAR(d):
    return 2.02e-6 * d * d + 0.0667 * d - 6.96


def _tosec(t):
    m = re.match(r'(?:(\d+):)?(\d+)\.(\d+)', str(t or ''))
    if not m:
        return None
    return (int(m.group(1)) if m.group(1) else 0) * 60 + int(m.group(2)) + int(m.group(3)) / 10


def _day_diffs(c, ymd, place):
    """その開催日×場の全馬 (タイム−PAR(距離)) を返す。馬場差B算出用。"""
    if place not in ALL_CODES:
        return []
    try:
        idx = c.get(CARD.format(r=day_index_race_id(ymd, place)), use_cache=True)
        races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[place]))
    except Exception:
        return []
    diffs = []
    for _, rid in races.items():
        try:
            dist = getattr(P.parse_card_page(c.get(CARD.format(r=rid), use_cache=True), rid), "distance", None)
            html = c.get(PERF.format(r=rid), use_cache=True)
        except Exception:
            continue
        if not dist:
            continue
        s = BeautifulSoup(html, "html.parser")
        for tr in s.find_all("tr"):
            cs = [re.sub(r"\s+", " ", td.get_text(" ", strip=True)) for td in tr.find_all("td")]
            if len(cs) >= 11 and cs[0].isdigit() and 1 <= int(cs[0]) <= 18:
                t = _tosec(cs[7])
                if t:
                    diffs.append(t - PAR(dist))
    return diffs


class BabaBook:
    """(date, place) -> 馬場差B のlazyキャッシュ。"""
    def __init__(self, c):
        self.c = c
        self.cache = {}

    def get(self, date, place):
        if not date or not place:
            return None
        key = (date, place)
        if key not in self.cache:
            ymd = date.replace("-", "")
            diffs = _day_diffs(self.c, ymd, place)
            self.cache[key] = statistics.median(diffs) if diffs else None
        return self.cache[key]


def proj_index(e, book, agg="best", raw=False, target_dist=None, dist_tol=400):
    """1頭の投影指数。過去走ごとに B正規化した指数を集計。取れた指数リストも返す。
    raw=True なら馬場差B正規化を省く(高速・外れ値に弱い)。
    target_dist指定時は|過去距離−目標|<=dist_tol の走のみ採用(距離違いの外れ値を排除)。
    条件を満たす走が2未満なら全走にフォールバック。"""
    runs = list((e.recent_runs or [])[:5])
    if target_dist:
        near = [pr for pr in runs if getattr(pr, "distance", None) and abs(pr.distance - target_dist) <= dist_tol]
        if len(near) >= 2:
            runs = near
    vals = []
    for pr in runs:
        d = getattr(pr, "distance", None)
        t = _tosec(getattr(pr, "time", None))
        if not (d and t):
            continue
        b = None if raw else book.get(getattr(pr, "date", None), getattr(pr, "place", None))
        base = PAR(d) + (b if b is not None else 0.0)   # Bが取れない過去走は生パー(近似)
        vals.append(-K * (t - base))
    if not vals:
        return None, []
    if agg == "avg3":
        top = sorted(vals, reverse=True)[:3]
        return sum(top) / len(top), vals
    return max(vals), vals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--race", type=int, default=None)
    ap.add_argument("--agg", choices=["best", "avg3"], default="best")
    ap.add_argument("--raw", action="store_true", help="馬場差B正規化を省く(高速)")
    ap.add_argument("--verify", action="store_true", help="実着と答え合わせ(指数①位の成績)")
    a = ap.parse_args()
    c = PoliteClient()
    book = BabaBook(c)
    ymd = a.date.replace("-", "")
    idx = c.get(CARD.format(r=day_index_race_id(ymd, a.place)), use_cache=True)
    races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[a.place]))
    Rs = [a.race] if a.race else sorted(races)
    win1 = comp = arre = 0
    arres = []
    for R in Rs:
        rid = races[R]
        pc = P.parse_card_page(c.get(CARD.format(r=rid), use_cache=True), rid)
        dist = getattr(pc, "distance", None)
        fin = {}
        if a.verify:
            try:
                rr = P.parse_result_page(c.get(PERF.format(r=rid), use_cache=True), rid)
                fin = {row.umaban: row.finish_pos for row in rr.rows if row.finish_pos}
            except Exception:
                fin = {}
        proj = []
        for e in pc.entries:
            if not e.umaban:
                continue
            si, _ = proj_index(e, book, a.agg, raw=a.raw, target_dist=dist)
            if si is not None:
                proj.append((si, e.umaban, (e.horse_name or "")[:8]))
        proj.sort(reverse=True)
        top5 = proj[:5]
        _norm = "生指数(B無)" if a.raw else "馬場差B正規化"
        print(f"\n {R:>2}R ダ{dist} 持ちタイム指数top5({a.agg}・{_norm}・距離±400)")
        for rank, (si, um, nm) in enumerate(top5, 1):
            f = fin.get(um)
            ftag = f" {f}着" if f else ""
            print(f"   {rank}位 {um:>2}番 {nm:8s} 指数{si:+6.1f}{ftag}")
        if a.verify and fin:
            top5_um = [um for _, um, _ in top5]
            act1 = [um for um, ff in fin.items() if ff == 1]
            t1f = fin.get(top5[0][1], 99)
            if t1f == 1:
                win1 += 1
            if t1f <= 3:
                comp += 1
            if not any(x in top5_um for x in act1):
                arre += 1
                arres.append(f"{R}R")
    if a.verify and not a.race:
        n = len(Rs)
        print(f"\n=== 指数①位 成績({a.agg}) ===")
        print(f" ①位が1着 : {win1}/{n} (勝率{win1/n:.0%})")
        print(f" ①位が3着内: {comp}/{n} (複勝率{comp/n:.0%})")
        print(f" 荒れ(実1着が指数top5圏外): {arre}/{n} {arres}")


if __name__ == "__main__":
    main()
