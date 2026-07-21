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

# 検証で確定した構造(並行解析・3回+実測で完全に割れた 2026-07-20):
#   指数 = -10 * (タイム - 実測基準タイム)   ※係数10は距離不問
#   標準基準 = 二次パー(距離d[m]の関数)     ※距離正規化は係数でなく基準側(長距離外挿の破綻防止)
#   実測基準 = 二次パー + 当日馬場差         ※馬場差は当日実測・符号一貫・一箇所で1回だけ反映
#     (固定馬場差はMAE9.7で外れる/当日実測でMAE2.5。符号一貫が生命線)
K = 10.0  # 距離不問

def PAR(d):
    """二次パー(標準基準タイム・秒)。d=距離[m]。"""
    return 2.02e-6 * d * d + 0.0667 * d - 6.96


def _tosec(t):
    m = re.match(r'(?:(\d+):)?(\d+)\.(\d+)', str(t or ''))
    if not m:
        return None
    return (int(m.group(1)) if m.group(1) else 0) * 60 + int(m.group(2)) + int(m.group(3)) / 10


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
    # 当日馬場差＝「実測タイム − 二次パー」の中央値。符号一貫で"一箇所で1回だけ"算出。
    # 全馬(当日全レースの全着) から取る＝母数を増やして誤差を潰す(検証で確定)。
    diffs = []          # 全馬ぶんの (実測タイム − PAR(dist))
    winlog = {}
    for R, rid in races.items():
        dist, win, rows = race_time_dist(c, rid)
        if dist and rows:
            for _, t, _ in rows:
                diffs.append(t - PAR(dist))
            winlog[R] = (dist, win, rows)
    baba = statistics.median(diffs) if diffs else 0.0   # 当日馬場差(秒・全馬中央値・1回算出)
    print(f"=== {a.date} {a.place} スピード指数（k=10固定・二次パー・当日馬場差{baba:+.2f}s）===")
    Rs = [a.race] if a.race else sorted(winlog)
    for R in Rs:
        if R not in winlog:
            continue
        dist, win, rows = winlog[R]
        base = PAR(dist) + baba            # 実測基準タイム = 二次パー + 当日馬場差
        print(f"\n {R:>2}R ダ{dist} 二次パー{PAR(dist):.1f}s 実測基準{base:.1f}s")
        out = [(-K * (t - base), ub, t, fin) for ub, t, fin in rows]  # 指数=-10*(タイム-実測基準)
        for si, ub, t, fin in sorted(out, reverse=True):
            print(f"   {fin:>2}着 {ub:>2}番 時{t:5.1f}s 指数{si:+5.1f}")


if __name__ == "__main__":
    main()
