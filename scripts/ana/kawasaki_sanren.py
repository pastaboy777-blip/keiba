#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""川崎競馬・今年(2026)の三連複2万円以上のレースを抽出し、
騎手・厩舎・脚質・距離・クラスを検証する（netkeiba NAR db・EUC-JP）。

race_id = 2026 + 45(川崎) + MMDD + RR
出力: scratchpad/kawasaki_sanren.json
"""
import subprocess, re, os, json, datetime

CACHE = os.environ.get("NKCACHE", "/tmp/claude-0/-home-user-keiba/5c9e9520-78d2-57a1-98df-28a0a517ec92/scratchpad/nkcache")
os.makedirs(CACHE, exist_ok=True)
THRESH = 20000

def fetch(rid):
    fp = os.path.join(CACHE, f"{rid}.html")
    if os.path.exists(fp) and os.path.getsize(fp) > 300:
        return open(fp, "rb").read().decode("euc-jp", errors="replace")
    p = subprocess.run(["curl", "-s", "-L", "--max-time", "15",
                        f"https://db.netkeiba.com/race/{rid}/"], capture_output=True)
    open(fp, "wb").write(p.stdout)
    return p.stdout.decode("euc-jp", errors="replace")

def cls_of(racename):
    m = re.search(r"([ABC][123](?:[ABC][123])?)", racename)
    if m: return m.group(1)
    if re.search(r"2歳", racename): return "2歳"
    if re.search(r"3歳", racename): return "3歳"
    if re.search(r"重賞|賞典|カップ|記念|ステークス", racename): return "重賞級"
    return "他"

def parse(html):
    tx = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    hd = re.search(r"(20\d\d)年(\d+)月(\d+)日.{0,50}?川崎", tx)
    if not hd: return None
    tt = re.sub(r"\s+", " ", html)
    # レース名・クラス・距離
    band = re.search(r"racedata[^>]*>(.*?)</dd", tt)
    bt = re.sub(r"<[^>]+>", " ", band.group(1)) if band else ""
    rn = re.search(r"R\s+([^ ].*?)\s+(?:ダ|芝)", bt)
    racename = rn.group(1).strip() if rn else ""
    dm = re.search(r"(ダ|芝)(?:右|左)?(\d{3,4})m", bt) or re.search(r"(\d{3,4})m", tx)
    dist = int(dm.group(dm.lastindex)) if dm else 0
    surf = "芝" if "芝" in bt[:20] else "ダ"
    # 三連複払戻
    pm = re.search(r"三連複\s*(\d+)\s*[-‐]\s*(\d+)\s*[-‐]\s*(\d+)\s*([\d,]+)", tx)
    if not pm: return None
    pay = int(pm.group(4).replace(",", ""))
    combo = {int(pm.group(1)), int(pm.group(2)), int(pm.group(3))}
    # ラップ→ペース
    lm = re.search(r"ラップ\s*</th>\s*<td[^>]*>([0-9 .\-]+)</td>", tt)
    pace = "?"
    if lm:
        seg = [float(x) for x in re.findall(r"[0-9]{1,2}\.[0-9]", lm.group(1))]
        if len(seg) >= 6:
            f3, l3 = sum(seg[:3]), sum(seg[-3:])
            pace = "前傾ハイ" if f3 < l3 - 0.6 else "後傾スロー" if f3 > l3 + 0.6 else "ミドル"
    # 着順行
    rows = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        if "/horse/" not in r: continue
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
        if len(cells) < 15: continue
        try:
            chaku = int(cells[0]); waku = int(cells[1]); ub = int(cells[2])
        except (ValueError, IndexError):
            continue
        kishu = cells[6] if len(cells) > 6 else "?"
        tsuka = next((c for c in cells if re.match(r"^\d+(-\d+){1,3}$", c)), "")
        ninki = None; odds = None
        for i, c in enumerate(cells):
            if re.match(r"^\d+\.\d$", c) and i+1 < len(cells) and re.match(r"^\d+$", cells[i+1]):
                odds = float(c); ninki = int(cells[i+1]); break
        tr = re.search(r"/trainer/[^\"]*\"[^>]*>([^<]+)<", r)
        chokyo = tr.group(1).strip() if tr else "?"
        rows.append(dict(chaku=chaku, waku=waku, ub=ub, name=cells[3], kishu=kishu,
                         chokyo=chokyo, tsuka=tsuka, ninki=ninki, odds=odds))
    if len(rows) < 3: return None
    n = len(rows)
    for row in rows:
        first = int(row["tsuka"].split("-")[0]) if row["tsuka"] else None
        row["kyaku"] = ("?" if first is None else "逃" if first == 1
                        else "先" if first <= max(2, round(n*0.25))
                        else "差" if first <= round(n*0.6) else "追")
    date = f"{hd.group(1)}-{int(hd.group(2)):02d}-{int(hd.group(3)):02d}"
    return dict(date=date, dist=dist, surf=surf, racename=racename, cls=cls_of(racename),
                pace=pace, n=n, pay=pay, combo=combo, rows=rows)

def main():
    start = datetime.date(2026, 1, 1); end = datetime.date(2026, 7, 24)
    hits = []; nrace = 0
    d = start
    while d <= end:
        md = f"{d.month:02d}{d.day:02d}"
        if parse(fetch(f"202645{md}01")):          # 開催日のみ本取得
            for RR in range(1, 13):
                pr = parse(fetch(f"202645{md}{RR:02d}"))
                if not pr: continue
                nrace += 1
                if pr["pay"] >= THRESH:
                    pr["combo"] = sorted(pr["combo"]); pr["rid"] = f"202645{md}{RR:02d}"
                    hits.append(pr)
        if d.day == 1: print(f"...{d} race={nrace} hits={len(hits)}", flush=True)
        d += datetime.timedelta(days=1)
    json.dump(dict(nrace=nrace, hits=hits),
              open(os.path.join(CACHE, "..", "kawasaki_sanren.json"), "w"), ensure_ascii=False)
    report(nrace, hits)

def report(nrace, hits):
    from collections import Counter
    print(f"\n=== 川崎2026 三連複{THRESH:,}円以上  {len(hits)}/{nrace}レース ({len(hits)/max(1,nrace)*100:.1f}%) ===")
    kishu = Counter(); chokyo = Counter(); kyaku = Counter(); dist = Counter(); cls = Counter()
    for h in hits:
        placed = [r for r in h["rows"] if r["chaku"] <= 3]
        for r in placed:
            kishu[r["kishu"]] += 1; chokyo[r["chokyo"]] += 1; kyaku[r["kyaku"]] += 1
        dist[h["dist"]] += 1; cls[h["cls"]] += 1
    print("\n[距離]", dict(dist.most_common()))
    print("[クラス]", dict(cls.most_common()))
    print("[3着内馬の脚質]", dict(kyaku.most_common()))
    print("[騎手 上位]", dict(kishu.most_common(10)))
    print("[厩舎 上位]", dict(chokyo.most_common(10)))

if __name__ == "__main__":
    main()
