# -*- coding: utf-8 -*-
"""中央(JRA)ズブ穴：開催日の全レースから『市場と食い違っている馬』を抜く。

穴は弱い馬ではなく「今日の条件なら足りるのに、市場がそれを値段に入れていない馬」。
だから測る物差しを2本に分けて、その食い違いだけを見る。

  能力側 … 走破時計だけで作る（オッズを一切見ない）＝ win5_board.py の時計指数
  市場側 … 近3走の人気（前日はオッズが無いのでこれで代用）

  ┌ ① 該当条件（今日と同じ芝ダ・距離±200m）の時計指数が レース4位以内
  │     → 条件が合えば足りる下地がある
  ├ ② 上位2走平均で レース3位以内ではない
  │     → 実力上位3頭は人気を被る。ズブ穴の定義から外れる
  └ ③ 近3走の平均人気が 6番人気以下
        → 市場がこの馬を評価していない

  ①だけなら本命サイド、③だけならただの人気薄。①と③が同時に立つ馬だけが穴で、
  ②はそれを機械的に担保するための門。

  スコア = 該当条件指数 + 0.5×(6番人気以下で3着内に来た回数) + 0.06×min(近3走平均人気, 14)

  第2項が「一発ではなく再現性があるか」、第3項が「どれだけ無視されているか」。
  ★重み 0.5 / 0.06 は手置きで、回収率で最適化した値ではない。結果を記録して直すこと。

    python3 scripts/jra_ana.py 20260801
    python3 scripts/jra_ana.py 20260801 --top 20 --min-pop 5
"""
from __future__ import annotations

import argparse
import re
import statistics as st
import sys
from pathlib import Path

import numpy as np
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from win5_board import PAST, get, kl, parse_past, sec, wid

RACE_LIST = "https://race.netkeiba.com/top/race_list_sub.html?kaisai_date={d}"
JRA = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
       "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"}


def collect_day(ymd):
    """その日の全レースの出走馬＋過去5走。"""
    ids = []
    for m in re.finditer(r"race_id=(\d{12})", get(RACE_LIST.format(d=ymd))):
        if m.group(1) not in ids:
            ids.append(m.group(1))
    if not ids:
        return {}                      # 非開催日。呼び出し側でスキップする
    D = {}
    for i, rid in enumerate(ids, 1):
        s = BeautifulSoup(get(PAST.format(rid=rid)), "html.parser")
        horses = []
        for tr in s.select("tr.HorseList"):
            info, um = tr.select_one("td.Horse_Info"), tr.select_one("td.Waku")
            if not info or not um or not um.get_text(strip=True).isdigit():
                continue
            ln = info.get_text("\n", strip=True).split("\n")
            jk = tr.select_one("td.Jockey").get_text("\n", strip=True).split("\n")
            horses.append(dict(
                umaban=int(um.get_text(strip=True)),
                name=ln[1] if len(ln) > 1 else None,
                sexage=jk[0] if jk else None, jockey=jk[1] if len(jk) > 1 else None,
                kin=float(jk[2]) if len(jk) > 2 and re.match(r"[\d.]+$", jk[2]) else None,
                past=[p for p in (parse_past(td) for td in tr.select("td.Past")) if p]))
        D[rid] = dict(name=s.select_one(".RaceName").get_text(strip=True),
                      data1=s.select_one(".RaceData01").get_text(" ", strip=True),
                      data2=s.select_one(".RaceData02").get_text(" ", strip=True),
                      horses=horses)
        print(f"\r収集 {i}/{len(ids)}", end="", flush=True)
    print()
    return D


def fit(D):
    """復元した勝ちタイムを条件で分解し、『標準勝ち時計 − 走破時計』を返す関数を作る。"""
    races = {}
    for r in D.values():
        for h in r["horses"]:
            for p in h["past"]:
                t, mg = sec(p.get("time")), p.get("margin")
                if t is None or mg is None or p.get("surf") == "障":
                    continue
                races[(p["date"], p["place"], p.get("race"))] = dict(
                    place=p["place"], surf=p["surf"], dist=p["dist"], baba=p.get("baba", "良"),
                    k=kl(p.get("klass")), wt=t if p.get("fin") == 1 else t - mg)
    rs = list(races.values())
    grp = sorted({(x["surf"], x["dist"]) for x in rs})
    pl = sorted({x["place"] for x in rs})
    bb = [s + b for s in ("芝", "ダ") for b in ("良", "稍", "重", "不")]
    gi = {g: i for i, g in enumerate(grp)}
    pi = {p: i for i, p in enumerate(pl)}
    bi = {b: i for i, b in enumerate(bb)}
    NG, NP = len(grp), len(pl)
    X = np.zeros((len(rs), NG + NP + len(bb) + 1))
    y = np.array([x["wt"] for x in rs])
    for i, x in enumerate(rs):
        X[i, gi[(x["surf"], x["dist"])]] = 1
        X[i, NG + pi[x["place"]]] = 1
        X[i, NG + NP + bi.get(x["surf"] + x["baba"], 0)] = 1
        X[i, -1] = x["k"] - 3
    I = np.eye(X.shape[1]); I[:NG, :NG] = 0
    beta = np.linalg.solve(X.T @ X + I, X.T @ y)
    print(f"■ 較正 {len(rs)}レース／残差SD {np.std(y - X @ beta):.2f}秒／"
          f"クラス係数 {beta[-1]:+.2f}秒per段")
    for s in ("芝", "ダ"):
        print(f"  馬場補正({s})", {b: round(beta[NG + NP + bi[s + b]] - beta[NG + NP + bi[s + "良"]], 2)
                                  for b in ("良", "稍", "重", "不")})
    print("  ※芝は渋るほど遅く／ダは湿るほど速く出ていなければ指数を信用しないこと\n")

    def par(place, surf, dist, baba):
        if (surf, dist) not in gi or place not in pi or surf + baba not in bi:
            return None
        return beta[gi[(surf, dist)]] + beta[NG + pi[place]] + beta[NG + NP + bi[surf + baba]]
    return par


def main():
    ap = argparse.ArgumentParser(description="中央ズブ穴")
    ap.add_argument("ymd", help="開催日 YYYYMMDD")
    ap.add_argument("--top", type=int, default=16, help="表示する候補数")
    ap.add_argument("--cond-rank", type=int, default=4, help="① 該当条件指数がこの順位以内")
    ap.add_argument("--skip-rank", type=int, default=3, help="② 実力この順位までは人気を被るとみなす")
    ap.add_argument("--min-pop", type=float, default=6.0, help="③ 近3走の平均人気がこれ以下")
    args = ap.parse_args()

    D = collect_day(args.ymd)
    if not D:
        raise SystemExit(f"{args.ymd} は開催がない。日付を確認。")
    par = fit(D)

    rows = []
    for rid, r in D.items():
        m = re.search(r"(芝|ダ)(\d+)m", r["data1"])
        if not m:
            continue
        surf, dist = m.group(1), int(m.group(2))
        nh = int(re.search(r"(\d+)頭", r["data2"]).group(1)) if re.search(r"(\d+)頭", r["data2"]) else 0
        hs = []
        for h in r["horses"]:
            f = []
            for p in h["past"]:
                b, t = par(p.get("place"), p.get("surf"), p.get("dist"), p.get("baba", "良")), sec(p.get("time"))
                p["fig"] = round(b - t, 2) if (b is not None and t is not None) else None
                if p["fig"] is not None:
                    f.append(p["fig"])
            if len(f) < 3:                        # 3走ぶん指数が取れない馬は測れない
                continue
            cond = [p["fig"] for p in h["past"] if p.get("fig") is not None
                    and p.get("surf") == surf and abs(p.get("dist", 0) - dist) <= 200]
            pops = [p["pop"] for p in h["past"][:3] if p.get("pop")]
            upset = [p for p in h["past"]
                     if p.get("pop") and p.get("fin") and p["pop"] >= 6 and p["fin"] <= 3]
            hs.append(dict(h=h, top2=st.mean(sorted(f, reverse=True)[:2]),
                           cond=max(cond) if cond else None, worst=min(f),
                           pop=st.mean(pops) if pops else None, upset=upset))
        if len(hs) < 6:
            continue
        honmei = {id(x) for x in sorted(hs, key=lambda x: -x["top2"])[:args.skip_rank]}
        cand = sorted([x for x in hs if x["cond"] is not None], key=lambda x: -x["cond"])
        for rank, x in enumerate(cand, 1):
            if rank > args.cond_rank or id(x) in honmei:
                continue
            if not x["pop"] or x["pop"] < args.min_pop:
                continue
            rows.append(dict(pl=JRA.get(rid[4:6], rid[4:6]), rn=int(rid[-2:]), race=r["name"],
                             nh=nh, surf=surf, dist=dist, x=x, rank=rank,
                             score=x["cond"] + len(x["upset"]) * 0.5 + min(x["pop"], 14) * 0.06))

    rows.sort(key=lambda x: -x["score"])
    print(f"■ ズブ穴候補（①条件{args.cond_rank}位以内 ②実力{args.skip_rank}位以内でない "
          f"③近3走平均{args.min_pop:.0f}番人気以下）\n")
    for o in rows[:args.top]:
        x, h = o["x"], o["x"]["h"]
        print(f"{o['score']:5.2f} {o['pl']}{o['rn']:>2}R {wid(o['race'], 13)}{o['surf']}{o['dist']} "
              f"{o['nh']:>2}頭 │ {h['umaban']:>2} {wid(h['name'], 18)}{wid(h['sexage'], 6)}"
              f"{wid(h['jockey'], 7)}{h['kin'] or 0:>5} 該当{x['cond']:5.2f}(条件{o['rank']}位) "
              f"最低{x['worst']:5.2f} 近3走平均{x['pop']:4.1f}人 人気薄好走{len(x['upset'])}回")
        for p in x["upset"][:2]:
            print(f"        {p['date']} {p['place']}{wid(p.get('race'), 9)}{wid(p.get('klass'), 4)}"
                  f"{p.get('surf')}{p.get('dist')}{p.get('baba')} {p['fin']}着/{p.get('field')}頭 "
                  f"{p['pop']}人 差{p.get('margin')} 指数{p.get('fig')}")


if __name__ == "__main__":
    main()
