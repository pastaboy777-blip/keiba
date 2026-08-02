#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""南関ズブ穴ファクター診断（kk_factor を場に依存しない形へ広げたもの）.

kk_factor.py は川崎に固定で、勝ち圏の上がりも川崎の値を直書きしていた。
船橋・浦和・大井で回すには場ごとに基準を作り直す必要があるので、
標本（data/samples/nankan_20*.jsonl）から場×距離帯の3着内中央値を毎回引き直す。

付けるファクター:
  血統      … その場での父別複勝率lift（1.3倍以上で加点）
  馬体重    … 480kg以上
  遅い上り  … その場・同距離帯（±200m）で、勝ち圏より遅い上がりのまま3着内に来た実績。
              速い上がりを使えた馬ではなく、時計がかかった中で残した馬を拾う。
              重み2（本命の芯）
  乗り替わり… 前走と騎手が替わった馬。乗り替わり自体は良し悪しではないが、
              市場は前走の着順を見て値段を付けるので、手が変わった分は値段に入りにくい
  休み明けでない… 前走が他場で、間隔が21日以内。
              2026-08-02 の船橋（29日空きの開催初日）で、他場帰り41頭が単223%・複137%、
              船橋帰り69頭が単31.7%・複91.9%。ただし1日ぶんの観測で未検証

  ★重みは仮置きである。回収率で測っていない。並べ替えの目安として使うこと。

    python3 scripts/nankan_factor.py --date 2026-08-03 --place 船橋
    python3 scripts/nankan_factor.py --date 2026-08-03 --place 船橋 --from 7 --to 12
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics as st
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{race_id}"
NANKAN = set(NANKAN_CODES)


def load_samples():
    for f in sorted(glob.glob(str(ROOT / "data/samples/nankan_20*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except Exception:
                    continue


def tables(place, min_n=40):
    """その場の『父別lift』と『距離帯ごとの勝ち圏上がり』をまとめて作る。"""
    n, t3 = defaultdict(int), defaultdict(int)
    base_n = base_t3 = 0
    agari = defaultdict(list)
    for r in load_samples():
        if r.get("place") != place:
            continue
        dist = r.get("distance")
        for h in r.get("horses") or []:
            fin = h.get("finish_pos")
            if not fin:
                continue
            base_n += 1
            top3 = fin <= 3
            base_t3 += top3
            s = h.get("sire")
            if s:
                n[s] += 1
                t3[s] += top3
            a = h.get("agari")
            if a and top3 and dist:
                agari[dist // 200 * 200].append(a)
    base = base_t3 / base_n if base_n else 0.27
    lift = {s: (t3[s] / n[s]) / base for s in n if n[s] >= min_n and base}
    par = {k: st.median(v) for k, v in agari.items() if len(v) >= 20}
    return lift, par, base, base_n


def par_from_results(client, place, d0, d1):
    """勝ち圏の上がりを結果ページから作る。

    標本ファイル（data/samples）には個別の上がりが入っていない（延べ11,227走で0件）ので、
    3着内に来た馬の上がりを結果ページから直接拾って距離帯ごとの中央値を取る。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from nankan_gyaku import result_rows
    from nankan_zubu_backtest import PERF, race_days

    agari = defaultdict(list)
    days = race_days(client, place, d0, d1)
    for i, (d, rs) in enumerate(days, 1):
        for rno, rid in sorted(rs.items()):
            try:
                html = client.get(PERF.format(race_id=rid) if "{race_id}" in PERF
                                  else PERF.format(r=rid))
                res = P.parse_result_page(html, rid)
                rows = result_rows(html)
            except Exception:
                continue
            if not res.distance:
                continue
            for r in rows:
                if r["agari"] and r["fin"] <= 3:
                    agari[res.distance // 200 * 200].append(r["agari"])
        print(f"\r  基準づくり {i}/{len(days)}日", end="", flush=True)
    print("\r" + " " * 30 + "\r", end="")
    return {k: st.median(v) for k, v in agari.items() if len(v) >= 20}


def jname(x):
    """減量記号（▲☆△★◇）を落とす。付けたまま比べると同じ騎手が乗替に見える。"""
    return (x or "").lstrip("▲☆△★◇◎○ ").strip()


def agari_par(par, dist):
    """その距離帯の勝ち圏上がり。無ければ近い帯で代用する。"""
    k = dist // 200 * 200
    if k in par:
        return par[k]
    if not par:
        return None
    return par[min(par, key=lambda x: abs(x - k))]


def slow_but_held(e, place, dist, par):
    """『遅い上がりのまま3着内に来た』実績を数える。速い脚の証明ではない。"""
    cut = agari_par(par, dist)
    if cut is None:
        return 0, None
    cnt, ex = 0, None
    for rr in e.recent_runs or []:
        if rr.place != place or not rr.agari or not rr.distance or not rr.finish_pos:
            continue
        if abs(rr.distance - dist) > 200 or rr.finish_pos > 3:
            continue
        if rr.agari <= cut:          # 速い上がりで来た馬はここでは数えない
            continue
        cnt += 1
        if ex is None:
            ex = (str(rr.date)[5:], rr.distance, rr.agari)
    return cnt, ex


def main():
    ap = argparse.ArgumentParser(description="南関ズブ穴ファクター診断")
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", default="船橋", choices=sorted(NANKAN))
    ap.add_argument("--from", dest="r_from", type=int, default=1)
    ap.add_argument("--to", dest="r_to", type=int, default=12)
    ap.add_argument("--par-from", default="2026-04-01",
                    help="勝ち圏の上がりを作る期間の開始（標本に上がりが無い場合に使う）")
    ap.add_argument("--fresh-days", type=int, default=21,
                    help="前走からこの日数以内かつ他場なら『休み明けでない』")
    args = ap.parse_args()

    d = date.fromisoformat(args.date)
    ymd = d.strftime("%Y%m%d")
    lift, par, base, n = tables(args.place)
    client = PoliteClient(use_cache=True)
    if not par:
        par = par_from_results(client, args.place,
                               date.fromisoformat(args.par_from), d)
    races = dict(P.parse_race_links(
        client.get(CARD.format(race_id=day_index_race_id(ymd, args.place))),
        date_yyyymmdd=ymd, jyo_code=NANKAN_CODES[args.place]))

    print(f"■ {args.place} {args.date} ファクター診断（標本 {n:,}走・複勝率 {base:.3f}）")
    if lift:
        top = sorted(lift, key=lambda x: -lift[x])[:8]
        print("  好走血統(lift1.3+): "
              + " / ".join(f"{s}{lift[s]:.2f}" for s in top if lift[s] >= 1.3))
    print("  勝ち圏上がり: "
          + " / ".join(f"{k}m台 {v:.1f}" for k, v in sorted(par.items())))

    for R in sorted(races):
        if not (args.r_from <= R <= args.r_to):
            continue
        card = P.parse_card_page(client.get(CARD.format(race_id=races[R])), races[R])
        print(f"\n=== {R}R {card.surface}{card.distance} "
              f"({card.field_size}頭) {card.race_class or ''} ===")
        rows = []
        for e in card.entries:
            if e.umaban is None:
                continue
            pts, tags = 0, []
            lf = lift.get(e.sire or "")
            if lf and lf >= 1.3:
                pts += 1
                tags.append(f"血統{(e.sire or '')[:8]}{lf:.2f}x")
            if e.horse_weight and e.horse_weight >= 480:
                pts += 1
                tags.append(f"{e.horse_weight}kg")
            cnt, ex = slow_but_held(e, args.place, card.distance, par)
            if cnt:
                pts += 2
                tags.append(f"🎯遅い上りで3着内{cnt}回"
                            + (f"[{ex[0]}/{ex[1]}m/{ex[2]}]" if ex else ""))
            runs = e.recent_runs or []
            prev = runs[0] if runs else None
            if (prev and prev.jockey and e.jockey
                    and jname(prev.jockey) != jname(e.jockey)):
                pts += 1
                tags.append(f"乗替 {prev.jockey}→{e.jockey}")
            gap = None
            if prev and prev.date:
                try:
                    gap = (d - date.fromisoformat(str(prev.date))).days
                except Exception:
                    gap = None
            if gap is not None and gap <= args.fresh_days and prev.place != args.place:
                pts += 2
                tags.append(f"休み明けでない({prev.place}{prev.distance}・{gap}日)")
            pop = f"{prev.popularity}人" if prev and prev.popularity else "-"
            rows.append((pts, e.umaban, e.horse_name, e.jockey or "", pop, tags))
        rows.sort(key=lambda x: (-x[0], x[1]))
        for pts, um, nm, jk, pop, tags in rows:
            star = "★" * min(pts, 5)
            print(f"  {um:>3} {nm:<15}{(jk or '')[:4]:<5}前走{pop:>4} {star:<6}"
                  + (" / ".join(tags) if tags else ""))

    print("\n  重みは仮置き（遅い上り2・休み明けでない2・血統1・馬体重1・乗替1）。回収率では測っていない。")


if __name__ == "__main__":
    main()
