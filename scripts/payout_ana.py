#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""荒れレース(3連複高配当)の特徴分析.

キャッシュ済みの楽天結果ページ(data/cache)から各レースの3連複配当を抽出し、
サンプル(data/samples/nankan_*.jsonl)の脚質・距離・馬場と突き合わせて
「万馬券がどんな条件で出るか」を測る。鉄則13の裏取りツール。

使い方:
  python3 scripts/payout_ana.py                      # 全南関・閾値2万
  python3 scripts/payout_ana.py --place 川崎          # 川崎だけ
  python3 scripts/payout_ana.py --threshold 50000    # 5万円以上の激荒れ
"""
import argparse
import glob
import hashlib
import json
import re
import statistics
from collections import Counter
from pathlib import Path

RESULT_URL = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{race_id}"
_RE = re.compile(r'三連複\s*([\d\-]+)\s+([\d,]+)\s*円\s*(\d+)番人気')


def cache_path(url):
    return Path("data/cache") / f"{hashlib.sha256(url.encode()).hexdigest()[:24]}.html"


def senkou_style(s):
    if s is None:
        return "?"
    if s >= 0.35:
        return "逃先"
    if s >= 0.20:
        return "先行"
    if s >= 0.0:
        return "中団"
    return "後方"


def band(d):
    if d <= 1200:
        return "〜1200"
    if d <= 1400:
        return "1300-1400"
    if d <= 1600:
        return "1500-1600"
    return "1700+"


def load(places=None):
    files = sorted(glob.glob("data/samples/nankan_20*.jsonl"))
    out = []
    for f in files:
        for line in open(f, encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if places and r["place"] not in places:
                continue
            cp = cache_path(RESULT_URL.format(race_id=r["race_id"]))
            if not cp.exists():
                continue
            m = _RE.search(re.sub(r"<[^>]+>", " ", cp.read_text(encoding="utf-8", errors="ignore")))
            if not m:
                continue
            umap = {h["umaban"]: h for h in r["horses"]}
            styles = [senkou_style((umap.get(u, {}).get("features") or {}).get("senkou"))
                      for u in r.get("result_order", [])[:3]]
            out.append(dict(place=r["place"], dist=r["distance"], baba=r.get("baba"),
                            fs=r["field_size"], date=r["date"],
                            payout=int(m.group(2).replace(",", "")), styles=styles))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", default=None)
    ap.add_argument("--threshold", type=int, default=20000)
    args = ap.parse_args()
    TH = args.threshold
    places = {args.place} if args.place else None
    races = load(places)
    if not races:
        print("データなし")
        return

    def sashi(st):
        return any(s in ("中団", "後方") for s in st)

    def kouho(st):
        return "後方" in st

    n = len(races)
    are = [r for r in races if r["payout"] >= TH]
    ken = [r for r in races if r["payout"] < 5000]
    print(f"■ 対象 {n}R  荒れ(≥{TH:,}円) {len(are)}R ({len(are)/n*100:.1f}%)")
    print(f"  後方絡み率  荒れ {sum(map(lambda r:kouho(r['styles']),are))/len(are)*100:.1f}%"
          f"  vs 堅 {sum(map(lambda r:kouho(r['styles']),ken))/max(len(ken),1)*100:.1f}%")

    if not places:
        print("\n■ 場別 荒れ率")
        pl = {}
        for r in races:
            d = pl.setdefault(r["place"], [0, 0])
            d[0] += 1
            d[1] += r["payout"] >= TH
        for p, (a, b) in sorted(pl.items(), key=lambda x: -x[1][1] / x[1][0]):
            print(f"  {p:4} {b:3}/{a:4} = {b/a*100:4.1f}%")

    print("\n■ 距離帯 荒れ率")
    ca = Counter(band(r["dist"]) for r in races)
    cb = Counter(band(r["dist"]) for r in are)
    for b in ["〜1200", "1300-1400", "1500-1600", "1700+"]:
        if ca[b]:
            print(f"  {b:10} {cb[b]:3}/{ca[b]:4} = {cb[b]/ca[b]*100:4.1f}%")

    print("\n■ 馬場 荒れ率")
    ca = Counter(r["baba"] for r in races)
    cb = Counter(r["baba"] for r in are)
    for b in ["良", "稍", "重", "不"]:
        if ca.get(b):
            print(f"  {b} {cb.get(b,0):3}/{ca[b]:4} = {cb.get(b,0)/ca[b]*100:4.1f}%")

    top = sorted(are, key=lambda r: -r["payout"])[:6]
    print("\n■ 高額例:", "; ".join(
        f'{r["date"][5:]}/{r["place"]}/{r["dist"]}m/{r["baba"]}/{"".join(s[0] for s in r["styles"])}:{r["payout"]:,}'
        for r in top))


if __name__ == "__main__":
    main()
