#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""南関4場 穴サイン バックテスト（netkeiba NAR db・日付エンコードid）。

穴サインv2の核（展開×枠×脚質）が、4月以降の南関でどれだけ絡んだかを検証。
- race_id = 2026 + 場コード(42浦和/43船橋/44大井/45川崎) + MMDD + RR
- db.netkeiba.com/race/{id}/ はEUC-JP。ラップ・枠・通過(脚質)・単勝・人気・調教師が1ページ。
- 血統は含めない（馬ページ別取得が重いため）。展開×枠×脚質×厩舎で検証。

出力: scratchpad/anaback_nankan_result.json
"""
import subprocess, re, os, json, sys, datetime

CACHE = os.environ.get("NKCACHE", "/tmp/claude-0/-home-user-keiba/5c9e9520-78d2-57a1-98df-28a0a517ec92/scratchpad/nkcache")
os.makedirs(CACHE, exist_ok=True)
TRACKS = {"42": "浦和", "43": "船橋", "44": "大井", "45": "川崎"}

def fetch(rid):
    fp = os.path.join(CACHE, f"{rid}.html")
    if os.path.exists(fp) and os.path.getsize(fp) > 300:
        return open(fp, "rb").read().decode("euc-jp", errors="replace")
    p = subprocess.run(["curl", "-s", "-L", "--max-time", "15",
                        f"https://db.netkeiba.com/race/{rid}/"], capture_output=True)
    raw = p.stdout
    open(fp, "wb").write(raw)
    return raw.decode("euc-jp", errors="replace")

def parse(html):
    tt = re.sub(r"\s+", " ", html)
    hd = re.search(r"(20\d\d)年(\d+)月(\d+)日.{0,50}?(大井|川崎|船橋|浦和)", re.sub(r"<[^>]+>", " ", html))
    if not hd:
        return None
    # 距離
    dm = re.search(r"(ダ|芝)\s*(?:右|左)?\s*(\d{3,4})m", tt) or re.search(r"(\d{3,4})m", tt)
    dist = int(dm.group(dm.lastindex)) if dm else 0
    # ラップ → 前半3F/後半3F
    lm = re.search(r"ラップ\s*</th>\s*<td[^>]*>([0-9 .\-]+)</td>", tt)
    pace = "?"
    if lm:
        seg = [float(x) for x in re.findall(r"[0-9]{1,2}\.[0-9]", lm.group(1))]
        if len(seg) >= 6:
            f3, l3 = sum(seg[:3]), sum(seg[-3:])
            pace = "前傾ハイ" if f3 < l3 - 0.6 else "後傾スロー" if f3 > l3 + 0.6 else "ミドル"
    rows = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        if "/horse/" not in r:
            continue
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
        if len(cells) < 15:
            continue
        try:
            chaku = int(cells[0]); waku = int(cells[1]); ub = int(cells[2])
        except (ValueError, IndexError):
            continue
        tsuka = next((c for c in cells if re.match(r"^\d+(-\d+){1,3}$", c)), "")
        ninki = None
        # 人気: 単勝(float)の直後のint
        for i, c in enumerate(cells):
            if re.match(r"^\d+\.\d$", c) and i + 1 < len(cells) and re.match(r"^\d+$", cells[i+1]):
                ninki = int(cells[i+1]); odds = float(c); break
        else:
            odds = None
        tr = re.search(r"/trainer/[^\"]*\"[^>]*>([^<]+)<", r)
        chokyo = tr.group(1).strip() if tr else "?"
        rows.append(dict(chaku=chaku, waku=waku, ub=ub, tsuka=tsuka,
                         ninki=ninki, odds=odds, chokyo=chokyo))
    if not rows:
        return None
    n = len(rows)
    for row in rows:
        first = int(row["tsuka"].split("-")[0]) if row["tsuka"] else None
        row["kyaku"] = ("?" if first is None else "逃" if first == 1
                        else "先" if first <= max(2, round(n*0.25))
                        else "差" if first <= round(n*0.6) else "追")
    place = hd.group(4); date = f"{hd.group(1)}-{int(hd.group(2)):02d}-{int(hd.group(3)):02d}"
    return dict(date=date, place=place, dist=dist, pace=pace, n=n, rows=rows)

def daterange(a, b):
    d = a
    while d <= b:
        yield d
        d += datetime.timedelta(days=1)

def main():
    start = datetime.date(2026, 4, 1)
    end = datetime.date(2026, 7, 24)
    races = []
    for d in daterange(start, end):
        md = f"{d.month:02d}{d.day:02d}"
        for code in TRACKS:
            rid1 = f"2026{code}{md}01"
            h = fetch(rid1)
            if not parse(h):
                continue  # この場・この日はレース無し
            for RR in range(1, 13):
                rid = f"2026{code}{md}{RR:02d}"
                pr = parse(fetch(rid))
                if pr:
                    pr["rid"] = rid
                    races.append(pr)
        # 進捗
        if d.day == 1 or d == end:
            print(f"...{d} 済 races={len(races)}", flush=True)
    json.dump(races, open(os.path.join(CACHE, "..", "anaback_races.json"), "w"), ensure_ascii=False)
    analyze(races)

def analyze(races):
    from collections import defaultdict, Counter
    # 1) ペース別 穴発生率（核の再現性）
    pace_st = defaultdict(lambda: dict(races=0, runners=0, ana=0))
    # 2) シグナル（前傾ハイ×外枠[>=6]×差追）の複勝率・回収率
    sig = dict(n=0, top3=0, tan_ret=0, fuku_hit=0)
    base = dict(n=0, top3=0)
    for R in races:
        pace_st[R["pace"]]["races"] += 1
        for row in R["rows"]:
            pace_st[R["pace"]]["runners"] += 1
            if row["chaku"] <= 3 and (row["ninki"] or 99) >= 6:
                pace_st[R["pace"]]["ana"] += 1
            # シグナル判定
            hit = (R["pace"] == "前傾ハイ" and row["waku"] >= 6 and row["kyaku"] in ("差", "追")
                   and (row["ninki"] or 0) >= 6)
            if hit:
                sig["n"] += 1
                if row["chaku"] <= 3:
                    sig["top3"] += 1; sig["fuku_hit"] += 1
                if row["chaku"] == 1 and row["odds"]:
                    sig["tan_ret"] += row["odds"] * 100
    out = {"n_races": len(races), "pace": {}, "signal": sig}
    for p, s in pace_st.items():
        out["pace"][p] = dict(races=s["races"], ana_per_race=round(s["ana"]/max(1, s["races"]), 3),
                              ana=s["ana"], runners=s["runners"])
    print("\n=== 南関 穴サイン バックテスト 2026-04-01〜07-24 ===")
    print(f"総レース {len(races)}")
    print("\n[ペース別 穴発生率/レース]")
    for p in ["前傾ハイ", "ミドル", "後傾スロー", "?"]:
        if p in out["pace"]:
            s = out["pace"][p]
            print(f"  {p:<6} {s['races']:>4}R  穴/R {s['ana_per_race']:.2f}  (穴{s['ana']})")
    s = sig
    if s["n"]:
        print(f"\n[シグナル：前傾ハイ×外枠×差追×6人気↓]  該当 {s['n']}件")
        print(f"  複勝率 {s['fuku_hit']/s['n']*100:.1f}%  単勝回収率 {s['tan_ret']/(s['n']*100)*100:.0f}%")
    json.dump(out, open(os.path.join(CACHE, "..", "anaback_nankan_result.json"), "w"), ensure_ascii=False)
    print("\nsaved anaback_nankan_result.json")

if __name__ == "__main__":
    main()
