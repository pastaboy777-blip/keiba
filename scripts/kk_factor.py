#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""川崎ファクター診断（鉄則15の詰めツール）.

ズブ穴の最終比較用に、各馬へ「川崎好走血統lift・大型(480kg+)・川崎限定の上がり・
道悪ダイワメジャー」を付与する。v2エンジンは変更せず、別立てで一押し材料を出す。

血統liftはサンプル(data/samples/nankan_20*.jsonl)の川崎成績から毎回計算(陳腐化しない)。
上がりは川崎のレースのみで比較(浦和は軽いので混ぜない=鉄則15)。

使い方:
  python3 scripts/kk_factor.py --date 2026-07-08 --race 12 --baba 稍
  python3 scripts/kk_factor.py --date 2026-07-08 --from 10 --to 12 --baba 稍
"""
import argparse
import glob
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from nankeiba.scraping import enrich as E
from nankeiba.core import features as F

CARD_URL = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{race_id}"


def sire_lift_table(place="川崎", min_n=40):
    """サンプルから place の父別複勝率lift を計算。"""
    n = {}
    t3 = {}
    base_n = base_t3 = 0
    for f in sorted(glob.glob("data/samples/nankan_20*.jsonl")):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                import json
                r = json.loads(line)
            except Exception:
                continue
            if r.get("place") != place:
                continue
            for h in r.get("horses", []):
                fp = h.get("finish_pos")
                if fp is None:
                    continue
                s = h.get("sire") or ""
                hit = 1 if fp <= 3 else 0
                n[s] = n.get(s, 0) + 1
                t3[s] = t3.get(s, 0) + hit
                base_n += 1
                base_t3 += hit
    base = base_t3 / base_n if base_n else 0.27
    lift = {s: (t3[s] / n[s]) / base for s in n if n[s] >= min_n and base}
    return lift, n, base


def styl(s):
    if s is None:
        return "?"
    return "逃先" if s >= 0.35 else ("先行" if s >= 0.2 else ("中団" if s >= 0.0 else "後方"))


def agari_target(dist):
    """川崎の距離別"勝ち圏"上がりの上限(loose)。距離が延びるほど緩む。"""
    if dist <= 1000:
        return 38.7
    if dist <= 1300:
        return 39.3
    if dist <= 1400:
        return 40.0
    if dist <= 1600:
        return 40.5
    return 41.2


def reproduce_399(e, dist):
    """4フィルターで「今日の399を再現できる」候補か判定。
    ①川崎の上がり ②同距離帯(±200m)で勝ち圏の上がり ③後方/中団から出した(位置取り込み)。
    返り値: (該当走数, 例(日付,距離,上がり))。④展開(前傾か)は当日判断のため未自動化。"""
    cnt = 0
    ex = None
    for rr in (e.recent_runs or []):
        if getattr(rr, "place", None) != "川崎":
            continue
        a = getattr(rr, "agari", None)
        d = getattr(rr, "distance", None)
        c = getattr(rr, "corner", None)
        fs = getattr(rr, "field_size", None)
        if not (a and d and a > 0):
            continue
        if abs(d - dist) > 200:                 # ②距離を揃える
            continue
        if a > agari_target(dist):              # ②その距離の勝ち圏の上がり
            continue
        if c and fs:                            # ③位置取り込み: 早い角で中団/後方
            p0 = c[0] if isinstance(c, (list, tuple)) and c else None
            if p0 and p0 / fs < 0.4:
                continue
        cnt += 1
        if ex is None:
            ex = (str(getattr(rr, "date", ""))[5:], d, a)
    return cnt, ex


def kk_agari(e):
    ags = [getattr(rr, "agari", None) for rr in (e.recent_runs or [])
           if getattr(rr, "place", None) == "川崎" and getattr(rr, "agari", None)
           and getattr(rr, "agari") > 0]
    if not ags:
        return None, None
    return statistics.median(ags), min(ags)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--race", type=int)
    ap.add_argument("--from", dest="from_r", type=int, default=None)
    ap.add_argument("--to", dest="to_r", type=int, default=None)
    ap.add_argument("--baba", default="良", help="良/稍/重/不")
    ap.add_argument("--pop-min", type=int, default=6, help="穴の想定人気しきい")
    args = ap.parse_args()

    ymd = args.date.replace("-", "")
    wet = args.baba in ("稍", "重", "不")
    lift, sire_n, base = sire_lift_table()
    client = PoliteClient()
    idx = client.get(CARD_URL.format(race_id=day_index_race_id(ymd, "川崎")))
    races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd,
                                    jyo_code=NANKAN_CODES["川崎"]))
    if args.race:
        rlist = [args.race]
    else:
        lo = args.from_r or 1
        hi = args.to_r or 12
        rlist = [r for r in sorted(races) if lo <= r <= hi]

    print(f"■ 川崎 {args.date} ファクター診断（鉄則15）／馬場={args.baba}"
          f"{'（道悪→ダイワメジャー加点）' if wet else ''}")
    print(f"  好走血統(lift1.3+): "
          + " / ".join(f"{s}{lift[s]:.2f}" for s in sorted(lift, key=lambda x: -lift[x])[:8]))
    for R in rlist:
        card = P.parse_card_page(client.get(CARD_URL.format(race_id=races[R])), races[R])
        print(f"\n=== {R}R {card.surface}{card.distance} ({card.field_size}頭) {card.race_class or ''} ===")
        rows = []
        for e in card.entries:
            if e.umaban is None:
                continue
            s = e.sire or ""
            lf = lift.get(s)
            w = e.horse_weight
            med, best = kk_agari(e)
            sp = F.senkou_power(E.past_runs_to_records(e))
            pts = 0
            tags = []
            if lf and lf >= 1.3:
                pts += 1
                tags.append(f"血統{s[:8]}{lf:.2f}x")
            if w and w >= 480:
                pts += 1
                tags.append(f"大型{w}")
            if wet and "ダイワメジャー" in s:
                pts += 1
                tags.append("道悪ダイワメジャー")
            n9, ex9 = reproduce_399(e, card.distance)   # 4フィルターの①②③
            if n9:
                pts += 2                                # 399再現は重み高め(本命の芯)
                exs = f"例{ex9[0]}/{ex9[1]}m/{ex9[2]}" if ex9 else ""
                tags.append(f"🎯399再現{n9}回[{exs}]")
            if med:
                tags.append(f"川崎上り中{med:.1f}/最{best:.1f}")
            else:
                tags.append("川崎上り無")
            rows.append((pts, e, sp, tags))
        rows.sort(key=lambda x: (-x[0], -(x[1].exp_pop or 0)))
        for pts, e, sp, tags in rows:
            star = "★" * pts
            ana = "穴" if (e.exp_pop and e.exp_pop >= args.pop_min) else "  "
            print(f" {ana}{e.umaban:>2} {e.horse_name[:11]:<12}{(e.jockey or '')[:4]:<5}"
                  f"{styl(sp):<4} {e.exp_pop}人 {star:<3} {' / '.join(tags)}")
    print("\n※ ★=鉄則15ファクター（血統lift/大型480+/道悪ダイワメジャー）＋🎯399再現(★★重み)。")
    print("  🎯399再現＝①川崎の上がり②同距離帯で勝ち圏(距離別target)③後方/中団から出した、を満たす直近走の数。")
    print("  ④展開(前傾か)は当日4Rで判断。上がり勝負の馬場(稍重×前傾×差し)と確認できた日に発動。")


if __name__ == "__main__":
    main()
