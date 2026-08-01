# -*- coding: utf-8 -*-
"""中央の時計指数とズブ穴フィルタを、過去の開催日で実測する。

前日と同じ手順（その日の全出走馬の馬柱だけを見て指数を作る）を過去日に対して回し、
確定した着順・払戻と突き合わせる。過去日の shutuba_past はその時点までの馬柱しか
返さないことを確認済みなので、先読みは入らない。

出すもの:
  A 時計指数の順位別 … 勝率・複勝率・単複回収率（人気別をベンチマークに並べる）
  B ズブ穴フィルタ  … 通過馬の単複回収率（重みを変える前の素の性能）
  C 仮説検証        … 該当条件指数を「渋った馬場で出した馬」と「良馬場で出した馬」に
                       分けて成績を比べる。渋った側だけ成績が落ちるなら馬場補正が甘い。

    python3 scripts/jra_backtest.py 20260725 20260726 20260718 20260719
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import statistics as st
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jra_ana import collect_day, fit
from win5_board import sec

CTX = ssl.create_default_context(cafile="/root/.ccr/ca-bundle.crt")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
CACHE = Path("data/cache_jra_result")
_last = [0.0]


def result(rid):
    """確定した着順＋単勝オッズ＋複勝払戻。未確定なら空リスト（保存しない）。"""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{rid}.json"
    if f.exists():
        return json.loads(f.read_text())
    req = urllib.request.Request(f"https://race.netkeiba.com/race/result.html?race_id={rid}",
                                 headers={"User-Agent": UA, "Accept-Language": "ja"})
    for attempt in range(5):
        wait = 1.5 - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            raw = urllib.request.urlopen(req, timeout=30, context=CTX).read()
            break
        except Exception as e:      # 長時間の収集では相手に切られる。落ちないことを優先。
            if attempt == 4:
                raise
            print(f"\n  retry {attempt+1}/4 ({e}) {rid}", flush=True)
            time.sleep(5 * (attempt + 1))
    s = BeautifulSoup(raw.decode("utf-8", "ignore"), "html.parser")
    fuku = {}
    for tr in s.select("table.Payout_Detail_Table tr.Fukusho"):
        td = tr.find_all("td")
        if len(td) >= 2:
            nums = td[0].get_text("|", strip=True).split("|")
            yen = [int(x.replace(",", "").replace("円", "")) for x in
                   td[1].get_text("|", strip=True).split("|")]
            fuku = {int(n): y for n, y in zip(nums, yen) if n.isdigit()}
    if not fuku:
        return []                                       # 払戻が出ていない＝未確定
    out = []
    for tr in s.select("tr.HorseList"):
        # 末尾にラップ分析やコーナー通過の行が同じクラスで混ざる。着順が数字の行だけ拾う。
        td = [x.get_text(" ", strip=True) for x in tr.find_all("td")]
        if len(td) < 12 or not td[0].isdigit() or not td[2].isdigit():
            continue
        um = int(td[2])
        out.append(dict(fin=int(td[0]), umaban=um, name=td[3],
                        pop=int(td[9]) if td[9].isdigit() else None,
                        odds=float(td[10]) if re.match(r"[\d.]+$", td[10]) else None,
                        fuku=fuku.get(um, 0)))
    if out:
        f.write_text(json.dumps(out, ensure_ascii=False))
    return out


def horses_of(r, par):
    """1レースぶんの指標。指数が3走ぶん取れない馬は測れないので落とす。"""
    m = re.search(r"(芝|ダ)(\d+)m", r["data1"])
    if not m:
        return None, None, None
    surf, dist = m.group(1), int(m.group(2))
    hs = []
    for h in r["horses"]:
        f = []
        for p in h["past"]:
            b, t = par(p.get("place"), p.get("surf"), p.get("dist"), p.get("baba", "良")), sec(p.get("time"))
            p["fig"] = round(b - t, 2) if (b is not None and t is not None) else None
            if p["fig"] is not None:
                f.append(p["fig"])
        if len(f) < 3:
            continue
        cond = [p for p in h["past"] if p.get("fig") is not None
                and p.get("surf") == surf and abs(p.get("dist", 0) - dist) <= 200]
        best = max(cond, key=lambda p: p["fig"]) if cond else None
        pops = [p["pop"] for p in h["past"][:3] if p.get("pop")]
        hs.append(dict(h=h, top2=st.mean(sorted(f, reverse=True)[:2]),
                       cond=best["fig"] if best else None,
                       cond_baba=best.get("baba") if best else None,
                       pop3=st.mean(pops) if pops else None,
                       upset=len([p for p in h["past"]
                                  if p.get("pop") and p.get("fin") and p["pop"] >= 6 and p["fin"] <= 3])))
    return hs, surf, dist


def main():
    ap = argparse.ArgumentParser(description="中央 時計指数／ズブ穴の実測")
    ap.add_argument("dates", nargs="+", help="開催日 YYYYMMDD を複数")
    ap.add_argument("--cond-rank", type=int, default=4)
    ap.add_argument("--skip-rank", type=int, default=3)
    ap.add_argument("--min-pop", type=float, default=6.0)
    args = ap.parse_args()

    rank = defaultdict(lambda: [0, 0, 0, 0.0, 0.0])     # 出走,1着,3着内,単払戻,複払戻
    hrank = defaultdict(lambda: [0, 0, 0, 0.0, 0.0])    # (ハンデ/定量, 指標, 順位) 別
    nr_by_hcp = defaultdict(int)
    pops = defaultdict(lambda: [0, 0, 0, 0.0, 0.0])
    ana = [0, 0, 0, 0.0, 0.0]
    ana_rows, baba_split = [], defaultdict(lambda: [0, 0, 0, 0.0])
    nrace = 0

    for ymd in args.dates:
        print(f"\n===== {ymd} =====")
        D = collect_day(ymd)
        if not D:
            print("  非開催日。スキップ。")
            continue
        par = fit(D)
        for rid, r in D.items():
            res = result(rid)
            if not res:
                continue
            fin = {x["umaban"]: x for x in res}
            hs, surf, dist = horses_of(r, par)
            if not hs:
                continue
            hs = [x for x in hs if x["h"]["umaban"] in fin]
            for x in hs:
                x["r"] = fin[x["h"]["umaban"]]
            if len(hs) < 6:
                continue
            nrace += 1
            # ハンデ戦は「過去の実績を斤量で相殺する」競走なので、斤量を見ない指数が
            # 効かないはず。定量戦と分けて測る。
            hcp = "ハンデ" if "ハンデ" in r["data2"] else "定量"
            nr_by_hcp[hcp] += 1

            def tally(d, x):
                d[0] += 1
                if x["r"]["fin"] == 1:
                    d[1] += 1
                    d[3] += (x["r"]["odds"] or 0) * 100
                if x["r"]["fin"] <= 3:
                    d[2] += 1
                    d[4] += x["r"]["fuku"]

            for key, lst in (("top2", sorted(hs, key=lambda x: -x["top2"])),
                             ("cond", sorted([x for x in hs if x["cond"] is not None],
                                             key=lambda x: -x["cond"]))):
                for i, x in enumerate(lst[:5], 1):
                    tally(rank[(key, i)], x)
                    tally(hrank[(hcp, key, i)], x)
            for x in hs:
                if x["r"]["pop"] and x["r"]["pop"] <= 5:
                    tally(pops[x["r"]["pop"]], x)

            # C: 該当条件指数を稼いだ走りの馬場で分ける（1位の馬だけ）
            cl = sorted([x for x in hs if x["cond"] is not None], key=lambda x: -x["cond"])
            if cl:
                x = cl[0]
                k = "良" if x["cond_baba"] == "良" else "渋"
                d = baba_split[k]
                d[0] += 1
                if x["r"]["fin"] == 1:
                    d[1] += 1
                    d[3] += (x["r"]["odds"] or 0) * 100
                if x["r"]["fin"] <= 3:
                    d[2] += 1

            # B: ズブ穴フィルタ
            honmei = {id(x) for x in sorted(hs, key=lambda x: -x["top2"])[:args.skip_rank]}
            cand = sorted([x for x in hs if x["cond"] is not None], key=lambda x: -x["cond"])
            for i, x in enumerate(cand, 1):
                if i > args.cond_rank or id(x) in honmei:
                    continue
                if not x["pop3"] or x["pop3"] < args.min_pop:
                    continue
                tally(ana, x)
                ana_rows.append((x["cond"] + x["upset"] * 0.5 + min(x["pop3"], 14) * 0.06,
                                 ymd, rid, x["h"]["name"], x["r"]["pop"], x["r"]["fin"],
                                 x["r"]["odds"], x["r"]["fuku"]))

    def show(lab, d):
        n, w, p3, tp, fp = d
        if not n:
            return
        print(f"  {lab:<10} {n:5}  {w/n*100:5.1f}%  {p3/n*100:5.1f}%   "
              f"{tp/(n*100)*100:6.1f}%  {fp/(n*100)*100:6.1f}%")

    print(f"\n{'='*70}\n■ 対象 {nrace}レース（指数が測れる6頭以上のレースのみ）\n")
    print(f"  {'':<10} {'出走':>5}  {'勝率':>6} {'複勝率':>6}   {'単回収':>6}  {'複回収':>6}")
    print("-- 上位2走平均")
    for i in range(1, 6):
        show(f"{i}位", rank[("top2", i)])
    print("-- 該当条件指数")
    for i in range(1, 6):
        show(f"{i}位", rank[("cond", i)])
    print("-- 人気（ベンチマーク）")
    for p in range(1, 6):
        show(f"{p}人気", pops[p])
    print("-- ズブ穴フィルタ通過馬")
    show("ズブ穴", ana)

    print("\n■ ハンデ戦 vs 定量戦（斤量を見ない指数が効くのはどちらか）")
    for hcp in ("定量", "ハンデ"):
        print(f"-- {hcp}  {nr_by_hcp[hcp]}レース")
        for key, lab in (("top2", "上位2走"), ("cond", "該当条件")):
            for i in (1, 2, 3):
                show(f"{lab}{i}位", hrank[(hcp, key, i)])

    print("\n■ 仮説C：該当条件指数を稼いだ走りの馬場別（条件1位の馬だけ）")
    print(f"  {'':<6} {'頭数':>5} {'勝率':>7} {'複勝率':>7} {'単回収':>8}")
    for k in ("良", "渋"):
        n, w, p3, tp = baba_split[k]
        if n:
            print(f"  {k:<6} {n:5} {w/n*100:6.1f}% {p3/n*100:6.1f}% {tp/(n*100)*100:7.1f}%")

    print("\n■ ズブ穴の的中")
    for sc, ymd, rid, nm, pop, f, od, fu in sorted(ana_rows, reverse=True):
        if f <= 3:
            print(f"  {ymd} {rid} {nm} {pop}人気 {f}着 単{int((od or 0)*100)} 複{fu}")


if __name__ == "__main__":
    main()
