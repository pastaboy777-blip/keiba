#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""南関版・血統バカ一代：条件ごとの「4代血統内キーストーン血」を抽出。

サラブレ「血統バカ一代」の手法＝重賞ごとに"効く特定の血"を決め、4代血統表内に
その血を持つか(●)で足切り。ここでは南関の各条件(場×距離帯)で、過去好走馬の
4代血統に頻出し複勝率を押し上げる祖(キーストーン血)をデータで自動抽出する。

- ped: db.netkeiba.com/horse/ped/{id}（EUC-JP）。4代血統表の祖名を集合化。
- lift: ある祖を4代内に持つ馬の複勝率 / 全体複勝率。>1.15 かつ n十分 = キーストーン血。

python3 scripts/ana/keystone.py run 44      # 44=大井 のキーストーン血抽出
"""
import subprocess, re, os, glob, json, sys
from collections import Counter, defaultdict

CACHE = os.environ.get("NKCACHE",
    "/tmp/claude-0/-home-user-keiba/5c9e9520-78d2-57a1-98df-28a0a517ec92/scratchpad/nkcache")
PED = os.path.join(CACHE, "ped")
os.makedirs(PED, exist_ok=True)

def fetch_ped(hid):
    fp = os.path.join(PED, f"{hid}.html")
    if not (os.path.exists(fp) and os.path.getsize(fp) > 500):
        p = subprocess.run(["curl","-s","-L","--max-time","15",
                            f"https://db.netkeiba.com/horse/ped/{hid}/"], capture_output=True)
        open(fp, "wb").write(p.stdout)
    return open(fp, "rb").read().decode("euc-jp", errors="replace")

def ancestors(hid):
    """4代血統表内の祖名の集合（父方・母方すべて）。"""
    h = fetch_ped(hid)
    m = re.search(r"blood_table(.*?)</table>", h, re.S)
    seg = m.group(1) if m else h
    names = re.findall(r'/horse/\w+/"[^>]*>\s*([^<>]+?)\s*<', seg)
    out = set()
    for n in names:
        n = n.strip()
        if not n or n.isdigit(): continue
        n = re.sub(r"[A-Za-z].*$", "", n).strip() or n   # 英名は落として和名優先
        if len(n) >= 2: out.add(n)
    return out

def parse_result(fn):
    t = open(fn, "rb").read().decode("euc-jp", errors="replace")
    hd = re.search(r"(20\d\d)年(\d+)月(\d+)日.{0,50}?(大井|川崎|船橋|浦和)", re.sub(r"<[^>]+>", " ", t))
    if not hd: return None
    dm = re.search(r"(ダ|芝)(?:右|左)?(\d{3,4})m", re.sub(r"<[^>]+>", " ", t))
    dist = int(dm.group(2)) if dm else 0
    rows = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S):
        if "/horse/" not in r: continue
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
        if len(cells) < 15: continue
        try: chaku = int(cells[0])
        except: continue
        hid = re.search(r"/horse/(\w+)/", r)
        if hid: rows.append((hid.group(1), chaku, dist))
    return rows

def run(code, cap=900):
    # 対象場の全出走(horse_id, chaku, dist) を収集
    runs = []
    for fn in glob.glob(os.path.join(CACHE, f"2026{code}*.html")):
        if os.path.getsize(fn) < 5000: continue
        rr = parse_result(fn)
        if rr: runs.extend(rr)
    # ユニーク馬をcapまで（好走馬を優先的に含める）
    seen = {}
    for hid, chaku, dist in runs:
        seen.setdefault(hid, (chaku, dist))
    hids = list(seen.keys())[:cap]
    print(f"対象馬 {len(hids)} / 全出走レコード {len(runs)}", flush=True)
    # ped取得
    anc = {}
    for i, hid in enumerate(hids):
        anc[hid] = ancestors(hid)
        if i % 100 == 0: print(f"  ped {i}/{len(hids)}", flush=True)
    # 距離帯付きで全出走レコードを評価（capに含まれる馬のみ）
    band = lambda d: "短(≤1400)" if d and d <= 1400 else "中(1500-1700)" if d and d <= 1700 else "長(1800+)"
    recs = [(hid, chaku, band(dist)) for hid, chaku, dist in runs if hid in anc]
    N = len(recs); base = sum(1 for _, c, _ in recs if c <= 3) / N
    print(f"\n=== {code} キーストーン血（全体・複勝ベース{base*100:.1f}% n={N}）===")
    cnt = Counter(); hit = Counter()
    for hid, chaku, _ in recs:
        for a in anc[hid]:
            cnt[a] += 1
            if chaku <= 3: hit[a] += 1
    res = []
    for a, n in cnt.items():
        if n >= 60:
            p = hit[a] / n
            res.append((p/base, a, n, p))
    res.sort(reverse=True)
    print(f"{'lift':>5}{'複勝':>7}{'n':>6}  祖(4代内に持つ)")
    for lift, a, n, p in res[:20]:
        print(f"{lift:>5.2f}{p*100:>6.1f}%{n:>6}  {a}")
    json.dump({a: [round(l,2), n, round(p,3)] for l, a, n, p in res},
              open(os.path.join(CACHE, "..", f"keystone_{code}.json"), "w"), ensure_ascii=False)

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "run":
        run(sys.argv[2])
    else:
        print("usage: keystone.py run <trackcode 44=大井/45=川崎/43=船橋/42=浦和>")
