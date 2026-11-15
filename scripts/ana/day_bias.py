#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""その日のラップと決まり方から馬場傾向を逆算する。

使い方:
  python3 scripts/ana/day_bias.py <楽天RACEID接頭辞14桁>
  例) 川崎 2026/7/27 → 20260727211506 01  （末尾2桁がRR）

出力:
  ①各レースのラップ形（前傾/後傾）と1着馬の位置取り
  ②その日の集計＝どの位置が勝っているか＝バイアス
  ③次のレースへの逆算メモ
"""
import re, subprocess, os, sys
from collections import defaultdict

TMP = os.environ.get("DAYBIAS_TMP", "/tmp/daybias")
os.makedirs(TMP, exist_ok=True)

def fetch(pre, RR):
    fp = f"{TMP}/{pre}{RR:02d}.html"
    if not (os.path.exists(fp) and os.path.getsize(fp) > 20000):
        subprocess.run(["curl", "-s", "-L", "--max-time", "20",
                        f"https://keiba.rakuten.co.jp/race_performance/list/RACEID/{pre}{RR:02d}",
                        "-o", fp], check=False)
    return open(fp, encoding="utf-8", errors="replace").read()

def parse(html):
    x = re.sub(r"<[^>]+>", " ", html); x = re.sub(r"\s+", " ", x)
    d = re.search(r"ダ\s*([\d,]+)m", x)
    dist = int(d.group(1).replace(",", "")) if d else None
    lap = re.search(r"ハロンタイム\s*([0-9.\-]+)", x)
    laps = [float(v) for v in lap.group(1).split("-")] if lap else []
    ag = re.search(r"上がり\s*4F\s*([0-9.]+)\s*[-‐]\s*3F\s*([0-9.]+)", x)
    corner = re.search(r"(?:４角|4角)\s*([^■]{0,120})", x)
    # 着順（馬番のみ）
    y = re.sub(r"<[^>]+>", "|", html); y = re.sub(r"[ 　]+", " ", y); y = re.sub(r"\|{3,}", "||", y)
    i = y.find("着順"); j = y.find("■|払戻金")
    if j < 0: j = y.find("払戻金", i+100)
    order = []
    if i >= 0 and j > i:
        seg = re.sub(r"\s+", " ", y[i:j])
        for m in re.finditer(r"\|(\d{1,2})\|\s*\|(\d{1,2})\|\s*\|(\d{1,2})\|", seg):
            order.append((int(m.group(1)), int(m.group(3))))   # (着順, 馬番)
    pay = {}
    tail = re.sub(r"\s+", " ", y[j:j+1200]) if j > 0 else ""
    for lab in ["単勝", "三連単"]:
        mm = re.search(re.escape(lab)+r"\|\s*\|([\d\-\s|]+?)\|\s*\|([\d,]+) 円", tail)
        if mm: pay[lab] = mm.group(2)
    return dict(dist=dist, laps=laps, agari=(float(ag.group(2)) if ag else None),
                corner4=(corner.group(1).strip() if corner else ""), order=order, pay=pay)

def lap_shape(laps):
    """前半3F・後半3Fと形。
    ⚠1F目が10秒未満＝半端ハロン（900m/1500m等）。これを含めると必ず後傾に見えるので除外する。"""
    ls = laps[1:] if (laps and laps[0] < 10.0) else laps
    if len(ls) < 5: return None
    f3 = sum(ls[:3]); l3 = sum(ls[-3:])
    diff = f3 - l3
    if diff <= -1.0: return ("後傾（前が楽）", f3, l3, diff)
    if diff >= 1.0:  return ("前傾（前が苦しい）", f3, l3, diff)
    return ("平坦", f3, l3, diff)

def pos_of(corner4, umaban, n):
    """4角の通過順文字列から、その馬の位置(1始まり)を推定。"""
    if not corner4: return None
    s = re.sub(r"[（）\(\)]", ",", corner4)
    nums = [int(v) for v in re.findall(r"\d+", s)]
    seen = []
    for v in nums:
        if v not in seen: seen.append(v)
    if umaban not in seen: return None
    return seen.index(umaban) + 1

def run(pre, upto=12):
    print(f"■ 逆算エンジン  RACEID接頭辞 {pre}\n")
    rows = []
    for RR in range(1, upto+1):
        p = parse(fetch(pre, RR))
        if not p["order"]: continue
        sh = lap_shape(p["laps"])
        win = min(p["order"])[1] if p["order"] else None
        n = len(p["order"])
        wp = pos_of(p["corner4"], win, n)
        rows.append((RR, p, sh, win, wp, n))
        lp = "-".join(f"{v:.1f}" for v in p["laps"]) if p["laps"] else "ラップなし"
        print(f"{RR:>2}R {p['dist']}m {n}頭  {lp}")
        if sh:
            print(f"     前3F {sh[1]:.1f} / 後3F {sh[2]:.1f} → {sh[0]}（差{sh[3]:+.1f}）"
                  f"  上がり3F {p['agari']}")
        print(f"     1着 {win}番 … 4角 {wp if wp else '?'}番手/{n}頭"
              f"   三連単 {p['pay'].get('三連単','-')}")
    # 集計
    print("\n── その日のバイアス集計 ──")
    cnt = defaultdict(int); tot = 0
    for RR, p, sh, win, wp, n in rows:
        if not wp: continue
        tot += 1
        r = wp / n
        k = "逃げ・先行(上位25%)" if r <= 0.25 else "好位(〜50%)" if r <= 0.5 else "中団(〜75%)" if r <= 0.75 else "後方"
        cnt[k] += 1
    for k in ["逃げ・先行(上位25%)", "好位(〜50%)", "中団(〜75%)", "後方"]:
        if tot: print(f"  1着の4角位置 {k:<20} {cnt.get(k,0):>2}/{tot}  ({cnt.get(k,0)/tot*100:.0f}%)")
    sh_cnt = defaultdict(int)
    for RR, p, sh, win, wp, n in rows:
        if sh: sh_cnt[sh[0]] += 1
    print("  ラップ形の分布: " + " / ".join(f"{k}{v}" for k, v in sh_cnt.items()))
    ag = [p["agari"] for RR, p, sh, win, wp, n in rows if p["agari"]]
    if ag:
        print(f"  上がり3F 最速{min(ag)} / 中央{sorted(ag)[len(ag)//2]} / 最遅{max(ag)}")
        print(f"  → 上がりの天井はおよそ {min(ag)} 秒。これより速い脚は今日は出ていない。")
    return rows

if __name__ == "__main__":
    pre = sys.argv[1] if len(sys.argv) > 1 else "20260727211506"
    run(pre, int(sys.argv[2]) if len(sys.argv) > 2 else 12)
