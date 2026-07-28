# -*- coding: utf-8 -*-
"""399フィルター：その日の勝ち圏の上がりを「再現できる馬」を洗い出す。

考え方(notes/playbook.md 鉄則16 / handoff §38)：
  ① 馬場を揃える   → 他場の上がりは実測の場補正で川崎換算に直す（消さない）
  ② 距離を揃える   → 距離帯の補正で1400相当に正規化し、直近で繰り返せているかを見る
  ③ 位置取り込み   → 逃げて出した数字はカス。後方・中団から出した数字だけを本物とする
  ④ 展開の脈絡     → 湿った(前が止まる)展開で出した数字を上位に

§38-C の反省を反映：
  - 川崎実績ゼロの遠征馬を除外しない（場補正して同じ土俵で採点する）
  - 湿った日の想定では「③④を同時に満たす走りが1本もない馬」を上位に来させない

使い方:
    python3 scripts/ana399.py --date 2026-07-29 --place 川崎 --from 1 --to 12
    python3 scripts/ana399.py --date 2026-07-29 --place 川崎 --wet      # 雨で前が止まる想定
    python3 scripts/ana399.py --date 2026-07-29 --place 川崎 --thr 40.0 # 網を締める
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

CARD_URL = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{race_id}"
ADJ_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"

BANDS = [(0, 1000, "900"), (1001, 1400, "1400"), (1401, 1600, "1600"), (1601, 9999, "2000")]


def band(d):
    if not d:
        return None
    for lo, hi, name in BANDS:
        if lo <= d <= hi:
            return name
    return None


def load_adj():
    """場補正と距離帯補正。無ければ scripts/place_agari_adj.py で作り直す。"""
    pa = json.loads((ADJ_DIR / "place_agari_adj.json").read_text())
    ba = json.loads((ADJ_DIR / "band_agari_adj.json").read_text())
    return pa, ba


def norm_agari(agari, place, b, home, pa, ba):
    """上がりを『home場・1400m相当』に正規化する。"""
    if agari is None or b is None:
        return None
    v = agari
    if place != home:
        adj = pa.get(f"{place}|{b}")
        if adj is None:
            return None  # 補正値が無い場(サンプル不足)は判定不能
        v -= adj
    v -= ba.get(b, 0.0)
    return round(v, 2)


def pos_kind(corner, field_size):
    if not corner or not field_size:
        return None
    r = corner[0] / field_size
    return "後方" if r >= 0.60 else ("中団" if r >= 0.30 else "前")


def evaluate(entry, today_band, home, pa, ba, thr, wet_mode):
    hits = []
    kawasaki_runs = 0
    for i, p in enumerate(entry.recent_runs or []):
        if p.place == home:
            kawasaki_runs += 1
        b = band(p.distance)
        n = norm_agari(p.agari, p.place, b, home, pa, ba)
        if n is None or n > thr:
            continue
        hits.append(dict(
            i=i, date=p.date, place=p.place, dist=p.distance, band=b,
            agari=p.agari, norm=n, baba=p.baba, fin=p.finish_pos, pop=p.popularity,
            pos=pos_kind(p.corner, p.field_size),
            recent=i < 3,
            wet=p.baba in ("稍", "重", "不"),
            away=p.place != home,
        ))
    for h in hits:
        h["margin"] = round(thr - h["norm"], 2)  # 勝ち圏をどれだけ上回ったか
    n_hit = len(hits)
    real = [h for h in hits if h["wet"] and h["pos"] in ("後方", "中団")]  # ③④同時＝本物
    backs = [h for h in hits if h["pos"] in ("後方", "中団")]
    n_real = len(real)
    n_rec_real = sum(1 for h in real if h["recent"])
    best_real = max((h["margin"] for h in real), default=0.0)
    best_back = max((h["margin"] for h in backs), default=0.0)
    # 回数ではなく「どれだけ勝ち圏を上回ったか」を主軸に、再現回数を加点する
    score = best_real * 2.5 + min(n_real, 4) * 0.9 + min(n_rec_real, 3) * 0.8 + best_back * 0.5
    gate = (not wet_mode) or n_real >= 1
    if not gate:
        score *= 0.35
    return dict(hits=hits, n_hit=n_hit, n_real=n_real, n_rec_real=n_rec_real,
                n_back=len(backs), n_wet=sum(1 for h in hits if h["wet"]),
                best_real=best_real, best_back=best_back,
                score=score, gate=gate, away_only=kawasaki_runs == 0)


def main():
    ap = argparse.ArgumentParser(description="399フィルター")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--place", default="川崎", choices=list(NANKAN_CODES))
    ap.add_argument("--from", dest="r_from", type=int, default=1)
    ap.add_argument("--to", dest="r_to", type=int, default=12)
    ap.add_argument("--thr", type=float, default=40.5,
                    help="勝ち圏の上がり(1400m相当)。締めるなら小さく")
    ap.add_argument("--wet", action="store_true", help="雨で前が止まる想定。③④同時の実績を必須にする")
    ap.add_argument("--top", type=int, default=6, help="1レースあたりの表示頭数")
    args = ap.parse_args()

    pa, ba = load_adj()
    client = PoliteClient(use_cache=False)
    ymd = date.fromisoformat(args.date).strftime("%Y%m%d")
    index_rid = day_index_race_id(ymd, args.place)
    html = client.get(CARD_URL.format(race_id=index_rid))
    races = dict(P.parse_race_links(html, date_yyyymmdd=ymd,
                                    jyo_code=NANKAN_CODES[args.place]))
    if not races:
        raise SystemExit(f"{args.date} {args.place}: 開催が見つかりません")

    print(f"■ {args.date} {args.place}  勝ち圏(1400m相当) {args.thr}  "
          f"{'雨想定=ON' if args.wet else '雨想定=OFF'}")
    print(f"  場補正/距離帯補正で他場・他距離の上がりを {args.place}・1400m相当に正規化して採点\n")

    for r in range(args.r_from, args.r_to + 1):
        if r not in races:
            continue
        page = P.parse_card_page(client.get(CARD_URL.format(race_id=races[r])), races[r])
        ents = getattr(page, "entries", page)
        tb = band(page.distance)
        rows = []
        for e in ents:
            ev = evaluate(e, tb, args.place, pa, ba, args.thr, args.wet)
            rows.append((ev, e))
        rows.sort(key=lambda x: -x[0]["score"])
        qual = sum(1 for ev, _ in rows if ev["n_hit"] > 0)
        warn = "  ⚠該当が少ない＝遠征馬中心のレース。網を緩めて見直すこと" if qual <= max(2, len(rows) // 4) else ""
        print(f"=== {r}R ダ{page.distance} 帯{tb} {len(ents)}頭  該当{qual}頭{warn}")
        for ev, e in rows[:args.top]:
            if ev["n_hit"] == 0:
                continue
            tag = []
            if ev["away_only"]:
                tag.append("遠征")
            if not ev["gate"]:
                tag.append("湿×後方の実績なし")
            det = " / ".join(
                f"{h['date'][5:]}{h['place'] if h['away'] else ''}{h['baba']}"
                f"{h['agari']}→{h['norm']}(+{h['margin']}){h['pos'] or '?'}{h['fin']}着{h['pop']}人"
                for h in sorted(ev["hits"], key=lambda x: -x["margin"])[:3])
            op = f"{e.exp_pop}人" if e.exp_pop else "-"
            print(f"  {ev['score']:5.1f} {e.umaban:>2} {e.horse_name:<12} {op:>4} "
                  f"本物{ev['n_real']}(直近{ev['n_rec_real']}) 最良+{ev['best_real']:.2f} "
                  f"該当{ev['n_hit']} {'/'.join(tag)}")
            print(f"        {det}")
        print()


if __name__ == "__main__":
    main()
