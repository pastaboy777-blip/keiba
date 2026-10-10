#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中央（JRA）の当日結果を netkeiba からまとめて取る。

  python3 scripts/fetch_jra_results.py 20261010 out.json

着順・人気・単勝オッズ・上り3F・馬体重と増減・4角通過順・ラップ・ペースを拾う。
result.html は race_id だけだと400を返すので rf=race_list を付ける。
"""
from __future__ import annotations
import json, re, sys, time

sys.path.insert(0, "/home/user/keiba/src")
from bs4 import BeautifulSoup                      # noqa: E402
from nankeiba.scraping.client import PoliteClient  # noqa: E402

JRA = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
       "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"}
YMD, OUT = sys.argv[1], sys.argv[2]
c = PoliteClient(use_cache=False)


def get(u, n=5):
    """空の本文が返ることがあるので、中身が来るまで待って取り直す。"""
    for i in range(n):
        try:
            r = c.session.get(u, timeout=30)
            if r.status_code == 200 and len(r.text) > 2000:
                return r.text
        except Exception:
            pass
        time.sleep(2 * (i + 1))
    return None


def order4(s):
    """'(*11,6,10)(3,4)13(1,9)12,5,2,8,7' → {馬番: 通過順}"""
    pos, n = {}, 1
    s = s.replace("*", "").replace("=", ",").replace("-", ",")
    for g in re.findall(r"\(([\d, ]+)\)|(\d+)", s):
        if g[0]:
            us = [int(x) for x in g[0].split(",") if x.strip()]
            for u in us:
                pos[u] = n
            n += len(us)
        elif g[1]:
            pos[int(g[1])] = n
            n += 1
    return pos


def num(s):
    try:
        return float(s)
    except Exception:
        return None


idx = get("https://race.netkeiba.com/top/race_list_sub.html?kaisai_date=%s" % YMD)
rids = sorted({x for x in re.findall(r"race_id=(\d{12})", idx or "")})
out = {}
for rid in rids:
    h = get("https://race.netkeiba.com/race/result.html?race_id=%s&rf=race_list" % rid)
    if not h:
        print("%s 取得NG" % rid)
        continue
    s = BeautifulSoup(h, "html.parser")
    tb = s.select_one("#All_Result_Table") or s.select_one("table.RaceTable01")
    trs = tb.find_all("tr")[1:] if tb else []
    if not trs:
        print("%s 未確定" % rid)
        continue
    d1 = s.select_one(".RaceData01")
    d2 = s.select_one(".RaceData02")
    nm = s.select_one(".RaceName")
    t1 = d1.get_text(" ", strip=True) if d1 else ""
    t2 = d2.get_text(" ", strip=True) if d2 else ""
    dm = re.search(r"(芝|ダ|障)\s*(\d+)m\s*\(([^)]*)\)", t1)
    bm = re.search(r"馬場:(\S+)", t1)
    wm = re.search(r"天候:(\S+)", t1)
    nh = re.search(r"(\d+)頭", t2)
    # ラップ（2行目が区間ごと）
    lap, pace = "", ""
    ht = s.select_one("table.Race_HaronTime")
    if ht:
        rs = ht.find_all("tr")
        if len(rs) >= 3:
            lap = "-".join(td.get_text(strip=True) for td in rs[2].find_all("td"))
    pt = s.select_one(".RapPace_Title")
    if pt:
        pm = re.search(r"ペース:\s*(\S+)", pt.get_text(" ", strip=True))
        pace = pm.group(1) if pm else ""
    c4 = {}
    ct = s.select_one("table.Corner_Num")
    if ct:
        for tr in ct.find_all("tr"):
            th = tr.find("th")
            td = tr.find("td")
            if th and td and "4" in th.get_text(strip=True):
                c4 = order4(td.get_text(strip=True))
    es = []
    for tr in trs:
        v = [td.get_text(" ", strip=True) for td in tr.find_all(["th", "td"])]
        if len(v) < 15:
            continue
        wm2 = re.match(r"(\d+)\s*\(([+-]?\d+)\)", v[14])
        u = int(v[2]) if v[2].isdigit() else None
        es.append(dict(
            f=v[0], waku=int(v[1]) if v[1].isdigit() else None, u=u, nm=v[3],
            sx=v[4][:1], age=int(v[4][1:]) if v[4][1:].isdigit() else None,
            kin=num(v[5]), jk=v[6], tm=v[7], margin=v[8],
            pop=int(v[9]) if v[9].isdigit() else None, odds=num(v[10]),
            ag=num(v[11]), tr=v[13],
            wt=int(wm2.group(1)) if wm2 else None,
            dw=wm2.group(2) if wm2 else "",
            c4=c4.get(u)))
    R = int(rid[-2:])
    key = "%s-%d" % (JRA.get(rid[4:6], rid[4:6]), R)
    out[key] = dict(rid=rid, place=JRA.get(rid[4:6], rid[4:6]), r=R,
                    name=nm.get_text(strip=True) if nm else "",
                    surf=dm.group(1) if dm else "", dist=int(dm.group(2)) if dm else 0,
                    turn=dm.group(3) if dm else "",
                    baba=bm.group(1) if bm else "", weather=wm.group(1) if wm else "",
                    cls=t2, n=int(nh.group(1)) if nh else len(es),
                    lap=lap, pace=pace, e=es)
    w = es[0]
    print("%-3s%2dR %s%-4d %-3s %2d頭 %-14s ペース%-2s ／ 1着 %2s %-13s %2s人気 4角%-3s 上%s"
          % (out[key]["place"], R, out[key]["surf"], out[key]["dist"], out[key]["baba"],
             out[key]["n"], out[key]["name"][:14], pace, w["u"], w["nm"][:13],
             w["pop"], w["c4"], w["ag"]))
    time.sleep(0.6)
json.dump(out, open(OUT, "w"), ensure_ascii=False)
print("→ %s %d鞍" % (OUT, len(out)))
