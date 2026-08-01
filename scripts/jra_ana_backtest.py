#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jra_ana の門の閾値と重みを、過去の開催日の結果で測る。

なぜ要るか：
  jra_ana のスコアは
      該当条件指数 + w_upset×(人気薄好走回数) + w_pop×min(近3走平均人気, 14)
  だが、w_upset=0.5 / w_pop=0.06 は手置きの値で回収率で最適化していない。
  門（条件4位以内・実力3位以内でない・近3走平均6番人気以下）も同じ。
  直すには「その設定で過去にどうだったか」を機械的に出す必要がある。

リークについて：
  出走表は shutuba_past.html を使う。これはそのレース時点の過去5走しか載らないので、
  当該レースの結果は構造的に入り込まない。較正(fit)もその日の出走馬の過去走だけで行う。
  ただし較正は「その日の全レース分をまとめて」行うので、同日の他レースの情報は共有される。
  当日の朝に同じことができる（結果は使わない）ので、実運用と同じ条件。

使い方:
  python3 scripts/jra_ana_backtest.py 20260725 20260726
  python3 scripts/jra_ana_backtest.py 20260718 20260719 20260725 20260726 --grid
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jra_ana import candidates, collect_day, fit
from win5_board import get

RESULT = "https://race.netkeiba.com/race/result.html?race_id={rid}"


def results(rid):
    """{馬番: (着順, 人気, 単勝オッズ)} と 複勝払戻 {馬番: 円}"""
    h = get(RESULT.format(rid=rid))
    s = BeautifulSoup(h, "html.parser")
    out = {}
    for tr in s.select("tr.HorseList"):
        td = [x.get_text(" ", strip=True) for x in tr.select("td")]
        if len(td) < 11 or not td[0].isdigit() or not td[2].isdigit():
            continue
        try:
            out[int(td[2])] = (int(td[0]), int(td[9]) if td[9].isdigit() else None,
                               float(td[10]) if re.match(r"[\d.]+$", td[10]) else None)
        except ValueError:
            continue
    fuku = {}
    for tb in s.select("table.Payout_Detail_Table"):
        for tr in tb.select("tr"):
            th = tr.select_one("th")
            if not th or "複勝" not in th.get_text(strip=True):
                continue
            ns = [x.get_text(strip=True) for x in tr.select("td.Result div span") if x.get_text(strip=True).isdigit()]
            ps = [x.replace(",", "").replace("円", "")
                  for x in tr.select_one("td.Payout").get_text("\n", strip=True).split("\n") if x.strip()]
            for n, p in zip(ns, ps):
                if p.isdigit():
                    fuku[int(n)] = int(p)
    return out, fuku


def evaluate(days, cond_rank, skip_rank, min_pop, w_upset, w_pop, top=None, verbose=False):
    """候補を作って結果と突き合わせる。top を指定するとスコア上位topのみ買う。"""
    n = win = plc = 0
    tan_ret = fuku_ret = 0
    hits = []
    for ymd, D, par, R in days:
        rows = candidates(D, par, cond_rank, skip_rank, min_pop, w_upset, w_pop)
        if top:
            rows = rows[:top]
        for o in rows:
            res, fuku = R.get(o["rid"], ({}, {}))
            r = res.get(o["umaban"])
            if not r:
                continue
            fin, pop, odds = r
            n += 1
            if fin == 1:
                win += 1
                tan_ret += (odds or 0) * 100
                hits.append((ymd, o, fin, pop, odds))
            if fin <= 3:
                plc += 1
                fuku_ret += fuku.get(o["umaban"], 0)
                if fin != 1 and verbose:
                    hits.append((ymd, o, fin, pop, odds))
    if not n:
        return None
    return dict(n=n, win=win, plc=plc,
                win_r=win / n, plc_r=plc / n,
                tan=tan_ret / (n * 100), fuku=fuku_ret / (n * 100), hits=hits)


def load(days):
    out = []
    for ymd in days:
        print(f"■ {ymd}")
        D = collect_day(ymd)
        par = fit(D)
        R = {rid: results(rid) for rid in D}
        out.append((ymd, D, par, R))
    return out


def main():
    ap = argparse.ArgumentParser(description="jra_ana のバックテスト")
    ap.add_argument("days", nargs="+", help="開催日 YYYYMMDD を複数")
    ap.add_argument("--grid", action="store_true", help="門と重みを総当たりで比較")
    ap.add_argument("--top", type=int, default=0, help="スコア上位N頭だけ買う（0=全候補）")
    ap.add_argument("--dump", help="全候補を1行1頭でCSVに書き出す（分析用）")
    args = ap.parse_args()

    days = load(args.days)

    if args.dump:
        import csv
        with open(args.dump, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "rid", "place", "rn", "surf", "dist", "field", "umaban", "name",
                        "cond", "cond_rank", "top2", "worst", "pop3", "upset", "score",
                        "fin", "pop", "odds", "fuku"])
            for ymd, D, par, R in days:
                for o in candidates(D, par, 6, 1, 0.0, 0.5, 0.06):   # 門を全開にして母集団ごと出す
                    res, fuku = R.get(o["rid"], ({}, {}))
                    r = res.get(o["umaban"])
                    if not r:
                        continue
                    x = o["x"]
                    w.writerow([ymd, o["rid"], o["pl"], o["rn"], o["surf"], o["dist"], o["nh"],
                                o["umaban"], x["h"]["name"],
                                round(x["cond"], 2), o["rank"], round(x["top2"], 2), round(x["worst"], 2),
                                round(x["pop"], 2) if x["pop"] else "", len(x["upset"]),
                                round(o["score"], 3), r[0], r[1], r[2], fuku.get(o["umaban"], 0)])
        print(f"→ {args.dump} に書き出し")

    base = evaluate(days, 4, 3, 6.0, 0.5, 0.06, args.top or None, verbose=True)
    if not base:
        raise SystemExit("候補が1頭も出なかった")

    print(f"\n■ 現行設定（条件4位以内／実力3位以内でない／近3走平均6人気以下／w=0.5,0.06）")
    print(f"  候補{base['n']}頭  1着{base['win']}({base['win_r']*100:.1f}%)  "
          f"3着内{base['plc']}({base['plc_r']*100:.1f}%)")
    print(f"  単勝回収 {base['tan']*100:.0f}%   複勝回収 {base['fuku']*100:.0f}%")
    if base["hits"]:
        print("\n  ── 馬券に絡んだ候補 ──")
        for ymd, o, fin, pop, odds in sorted(base["hits"], key=lambda z: -z[1]["score"]):
            print(f"    {ymd} {o['pl']}{o['rn']:>2}R {o['umaban']:>2}番 "
                  f"{o['x']['h']['name']}  {fin}着 {pop}人気 単{odds}倍 スコア{o['score']:.2f}")

    if not args.grid:
        return
    print("\n■ 門の総当たり（候補20頭未満は参考値）")
    print(f"  {'条件位':>4}{'実力除外':>7}{'最低人気':>7}{'候補':>6}{'1着率':>8}{'3着内率':>9}{'単回収':>8}{'複回収':>8}")
    for cr in (3, 4, 5, 6):
        for sr in (2, 3, 4):
            for mp in (5.0, 6.0, 7.0, 8.0):
                e = evaluate(days, cr, sr, mp, 0.5, 0.06)
                if not e:
                    continue
                flag = "" if e["n"] >= 20 else " *"
                print(f"  {cr:>4}{sr:>7}{mp:>7.0f}{e['n']:>6}{e['win_r']*100:>7.1f}%"
                      f"{e['plc_r']*100:>8.1f}%{e['tan']*100:>7.0f}%{e['fuku']*100:>7.0f}%{flag}")

    print("\n■ 重みの総当たり（門は現行のまま。スコア上位5頭だけ買った場合）")
    print(f"  {'w_upset':>8}{'w_pop':>7}{'候補':>6}{'1着率':>8}{'3着内率':>9}{'単回収':>8}{'複回収':>8}")
    for wu in (0.0, 0.25, 0.5, 0.75, 1.0):
        for wp in (0.0, 0.03, 0.06, 0.12):
            e = evaluate(days, 4, 3, 6.0, wu, wp, top=5)
            if not e:
                continue
            print(f"  {wu:>8.2f}{wp:>7.2f}{e['n']:>6}{e['win_r']*100:>7.1f}%"
                  f"{e['plc_r']*100:>8.1f}%{e['tan']*100:>7.0f}%{e['fuku']*100:>7.0f}%")


if __name__ == "__main__":
    main()
