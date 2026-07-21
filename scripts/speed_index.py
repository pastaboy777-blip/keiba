#!/usr/bin/env python3
"""大井スピード指数（自前）＝走破タイムを距離正規化＋当日馬場差で補正した相対指数。

マキシマム競馬新聞の指数(スピード指数)を7/21紙面から逆算(scripts解析)して構造を復元：
  指数 ≈ − k(距離) × (走破タイム秒 − 基準タイム) + 馬場差
  k(点/秒): 距離が延びるほど小さい(距離正規化)。基準タイム=指数0の標準時計。
紙面は馬場差が隠れ変数で完全再現不可なので、本モジュールは
  馬場差 = その日の各距離の代表勝ちタイム − 基準タイム
を自前で観測して補正する(=透明・毎回自前で出せる=predict_nankanの補完)。

使い方:
  python3 scripts/speed_index.py --date 2026-07-20 --place 大井          # 当日全馬の指数
  python3 scripts/speed_index.py --date 2026-07-20 --place 大井 --race 1
出力: 各馬の走破タイム→スピード指数(0=標準・+ほど優秀)。当日馬場差も表示。
"""
import sys, re, argparse, statistics
sys.path.insert(0, "src")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from bs4 import BeautifulSoup

PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"
CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"

# (A)で紙面から逆算した大井の基準タイム(指数0の標準時計・秒)と距離係数(点/秒)
BASE = {1200: 76.0, 1400: 90.2, 1500: 97.0, 1600: 104.2, 1650: 107.5, 1700: 111.0, 2000: 132.0}
KDIST = {1200: 10.0, 1400: 9.0, 1500: 8.5, 1600: 8.0, 1650: 7.8, 1700: 7.6, 2000: 7.0}


def _tosec(t):
    m = re.match(r'(?:(\d+):)?(\d+)\.(\d+)', str(t or ''))
    if not m:
        return None
    return (int(m.group(1)) if m.group(1) else 0) * 60 + int(m.group(2)) + int(m.group(3)) / 10


def _nearest(dist, table):
    return table.get(dist) or table[min(table, key=lambda d: abs(d - dist))]


def race_time_dist(c, rid):
    """1レースの (距離, 勝ちタイム秒, [(馬番,タイム秒,着)]) を返す。距離はカードから。"""
    dist = getattr(P.parse_card_page(c.get(CARD.format(r=rid), use_cache=True), rid), "distance", None)
    html = c.get(PERF.format(r=rid), use_cache=True)
    s = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in s.find_all("tr"):
        cs = [re.sub(r"\s+", " ", td.get_text(" ", strip=True)) for td in tr.find_all("td")]
        if len(cs) >= 11 and cs[0].isdigit() and 1 <= int(cs[0]) <= 18:
            t = _tosec(cs[7])
            if t:
                rows.append((int(cs[1]), t, int(cs[0])))
    win = min((t for _, t, _ in rows), default=None)
    return dist, win, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--race", type=int, default=None)
    a = ap.parse_args()
    c = PoliteClient()
    ymd = a.date.replace("-", "")
    idx = c.get(CARD.format(r=day_index_race_id(ymd, a.place)), use_cache=True)
    races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[a.place]))
    # 当日馬場差＝距離別「勝ちタイム − 基準」の中央値（全レースから）
    diffs = {}
    winlog = {}
    for R, rid in races.items():
        dist, win, rows = race_time_dist(c, rid)
        if dist and win:
            base = _nearest(dist, BASE)
            diffs.setdefault(dist, []).append(win - base)
            winlog[R] = (dist, win, rows)
    baba = {d: statistics.median(v) for d, v in diffs.items()}
    # 全距離の平均馬場差（データ無い距離の代替）
    gmean = statistics.median([x for v in diffs.values() for x in v]) if diffs else 0.0
    print(f"=== {a.date} {a.place} スピード指数（当日馬場差込み）===")
    print("  当日馬場差(距離別・勝ち時計−基準): " +
          " ".join(f"{d}:{baba[d]:+.1f}s" for d in sorted(baba)) + f" / 全体{gmean:+.1f}s")
    Rs = [a.race] if a.race else sorted(winlog)
    for R in Rs:
        if R not in winlog:
            continue
        dist, win, rows = winlog[R]
        base = _nearest(dist, BASE)
        k = _nearest(dist, KDIST)
        bd = baba.get(dist, gmean)
        print(f"\n {R:>2}R ダ{dist} 基準{base}s 係数{k}pt/s 馬場差{bd:+.1f}s")
        out = []
        for ub, t, fin in rows:
            si = -k * (t - base - bd)   # 馬場差で当日補正した相対スピード指数
            out.append((si, ub, t, fin))
        for si, ub, t, fin in sorted(out, reverse=True):
            print(f"   {fin:>2}着 {ub:>2}番 時{t:5.1f}s 指数{si:+5.1f}")


if __name__ == "__main__":
    main()
