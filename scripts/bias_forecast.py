#!/usr/bin/env python3
"""事前バイアス予測 ── 前日までの結果から「当日どの型の穴が来るか」を仮説化する。

穴馬検出の最大課題＝バイアスが"事後追従"だった点を潰す。前開催/前日までの
上位馬の 枠ゾーン・体型(馬体重)・脚質・馬場/勝ち時計 を集計し、当日の狙い型を提示。

使い方:
  python3 scripts/bias_forecast.py --date 2026-07-17 --place 浦和 [--lookback 3]

出力: 枠(内/中/外) / 体型(小型/大型) / 脚質(前/差し) / 馬場(速い重/遅い重…) の傾向と、
      「初日R1から狙える穴型」の仮説。※直近日を重く重み付け。日替わり反転リスクも明示。
"""
import sys, argparse, datetime
from collections import defaultdict
sys.path.insert(0, "src")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"
SMALL, BIG = 458, 478


def style_of(corner, fs):
    co = [x for x in (corner or []) if isinstance(x, (int, float))]
    if not co:
        return None
    early = co[0]
    if early <= 2:
        return "逃"
    if early <= max(3, round(fs * 0.35)):
        return "先"
    if early > fs * 0.55:
        return "差"
    return "中"


def zone_of(umaban, n):
    return "内" if umaban < n * 0.34 else ("外" if umaban > n * 0.67 else "中")


def collect_day(c, date_yyyymmdd, place):
    """1日分の上位3着の 枠/体型/脚質 と 馬場/勝ち時計 を集計。"""
    try:
        idx = c.get(CARD.format(r=day_index_race_id(date_yyyymmdd, place)), use_cache=True)
        races = dict(P.parse_race_links(idx, date_yyyymmdd=date_yyyymmdd, jyo_code=ALL_CODES[place]))
    except Exception:
        return None
    agg = dict(zone=defaultdict(int), size=defaultdict(int), style=defaultdict(int),
               baba=defaultdict(int), win_small=0, win_big=0, n=0, times={})
    for R in sorted(races):
        try:
            rr = P.parse_result_page(c.get(PERF.format(r=races[R]), use_cache=True), races[R])
            if not rr.rows or not rr.rows[0].finish_pos:
                continue
            pc = P.parse_card_page(c.get(CARD.format(r=races[R]), use_cache=True), races[R])
        except Exception:
            continue
        wt = {e.umaban: e.horse_weight for e in pc.entries}
        sty = {e.umaban: style_of(e.recent_runs[0].corner if e.recent_runs else None,
                                   (e.recent_runs[0].field_size if e.recent_runs else 12) or 12)
               for e in pc.entries}
        n = max((row.umaban for row in rr.rows), default=12)
        agg["n"] += 1
        agg["baba"][rr.baba] += 1
        agg["times"].setdefault((rr.surface, rr.distance), []).append(rr.rows[0].time)
        for i, row in enumerate(rr.rows[:3]):
            agg["zone"][zone_of(row.umaban, n)] += 1
            w = wt.get(row.umaban)
            if w and w <= SMALL:
                agg["size"]["小"] += 1
                if i == 0:
                    agg["win_small"] += 1
            elif w and w >= BIG:
                agg["size"]["大"] += 1
                if i == 0:
                    agg["win_big"] += 1
            else:
                agg["size"]["中"] += 1
            s = sty.get(row.umaban)
            if s:
                agg["style"]["前" if s in ("逃", "先") else ("差" if s == "差" else "中")] += 1
    return agg


def prior_days(date_dash, place, lookback):
    d0 = datetime.date.fromisoformat(date_dash)
    return [(d0 - datetime.timedelta(days=k)).strftime("%Y%m%d") for k in range(1, lookback + 1)]


def dominant(counter, keys):
    tot = sum(counter.get(k, 0) for k in keys) or 1
    top = max(keys, key=lambda k: counter.get(k, 0))
    return top, counter.get(top, 0) / tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="対象日 YYYY-MM-DD")
    ap.add_argument("--place", required=True)
    ap.add_argument("--lookback", type=int, default=3)
    a = ap.parse_args()
    c = PoliteClient()
    days = prior_days(a.date, a.place, a.lookback)
    print(f"=== 事前バイアス予測: {a.date} {a.place} (直近{a.lookback}日を参照) ===")
    merged = dict(zone=defaultdict(float), size=defaultdict(float), style=defaultdict(float),
                  baba=defaultdict(float), win_small=0, win_big=0, n=0)
    per_day = []
    for i, dy in enumerate(days):
        w = 1.0 / (i + 1)  # 直近ほど重い
        agg = collect_day(c, dy, a.place)
        if not agg or agg["n"] == 0:
            continue
        per_day.append((dy, agg))
        for k in ("zone", "size", "style", "baba"):
            for kk, vv in agg[k].items():
                merged[k][kk] += vv * w
        merged["win_small"] += agg["win_small"] * w
        merged["win_big"] += agg["win_big"] * w
        merged["n"] += agg["n"] * w
    if not per_day:
        print("参照できる前日データがありません。"); return
    for dy, agg in per_day:
        z = "/".join(f"{k}{agg['zone'][k]}" for k in ("内", "中", "外"))
        print(f"  {dy}: {agg['n']}R 馬場{dict(agg['baba'])} 枠[{z}] 小{agg['size']['小']}大{agg['size']['大']} 勝小{agg['win_small']}大{agg['win_big']}")
    zt, zc = dominant(merged["zone"], ["内", "中", "外"])
    st, sc = dominant(merged["size"], ["小", "大", "中"])
    yt, yc = dominant(merged["style"], ["前", "差", "中"])
    print("\n--- 予測（加重） ---")
    print(f"  枠   : {zt}有利 (確度{zc:.0%})" + ("  ※日替わり反転が多い開催は初日R1-3で要再判定" if zc < 0.45 else ""))
    print(f"  体型 : {st}型有利 (確度{sc:.0%})")
    print(f"  脚質 : {yt}有利 (確度{yc:.0%})")
    lastbaba = max(per_day[0][1]["baba"], key=per_day[0][1]["baba"].get)
    print(f"  馬場 : 前日ベース={lastbaba}（当日変化があれば勝ち時計で速い/遅いを再判定＝§5f）")
    print("\n--- 初日から狙う穴型（仮説）---")
    tag = []
    if st == "小":
        tag.append("軽量小型(≤458)")
    if st == "大":
        tag.append("大型パワー(≥478)")
    tag.append(f"{zt}枠")
    tag.append("差し" if yt == "差" else ("前・先行" if yt == "前" else "自在"))
    print("  狙い＝" + " × ".join(tag) + " の人気薄。R1から適用し、朝の結果で微修正。")


if __name__ == "__main__":
    main()
