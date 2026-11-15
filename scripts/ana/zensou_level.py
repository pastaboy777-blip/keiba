#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""出馬表の各馬について『前走がどれくらいレベルの高いレースだったか』を引く。

race_level.py は過去のレースを振り返って水準を出すツール。
それを予想に使うには、今日の出走馬の前走を照合して
「レベルの高いレースで負けてきた馬」を拾う必要がある。

  勝った馬は次も人気になる。負けた馬は人気を落とす。
  だから狙うのは【敗者の巻き返し率が高かったレースで4着以下だった馬】。

指標は race_level.py と同じ：
  次走勝率     … そのレースの出走馬が次走で勝った率
  敗者巻き返し率 … そのうち4着以下だった馬だけの次走勝率

使い方:
  python3 scripts/ana/zensou_level.py <楽天RACEID接頭辞16桁> [レース数]
  例) python3 scripts/ana/zensou_level.py 2026080219150601      # 船橋 8/2
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from race_level import add_elo, load_races, next_form

TMP = os.environ.get("ZLTMP", "/tmp/zensou")
PL = r"(浦和|川崎|大井|船橋|門別|金沢|名古屋|園田|高知|佐賀|水沢|盛岡|笠松)"


def fetch(pre, RR):
    os.makedirs(TMP, exist_ok=True)
    fp = f"{TMP}/{pre}{RR:02d}.html"
    if not (os.path.exists(fp) and os.path.getsize(fp) > 50000):
        subprocess.run(["curl", "-s", "-L", "--max-time", "25",
                        f"https://keiba.rakuten.co.jp/race_card/list/RACEID/{pre}{RR:02d}",
                        "-o", fp], check=False)
    return open(fp, encoding="utf-8", errors="replace").read()


def parse_card(html):
    """馬番・馬名・当日人気・前走(場/日付/着順)を取る。"""
    x = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    x = re.sub(r"<[^>]+>", "|", x); x = re.sub(r"[ 　]+", " ", x); x = re.sub(r"\|{3,}", "||", x)
    marks = [m.start() for m in re.finditer(r"\|◎\|", x)]
    dist = re.search(r"(\d{3,4})m成績", html)
    hs = []
    for k, pos in enumerate(marks):
        pre = x[max(0, pos-90):pos]; nums = re.findall(r"\|\s*(\d+)\s*\|", pre)
        ub = int(nums[-1]) if nums else k+1
        seg = re.sub(r"\s+", " ", x[pos:(marks[k+1] if k+1 < len(marks) else len(x))])
        nm = re.search(r"\|\|([ァ-ヴーヶ・]{2,16})\|\|", seg)
        if not nm:
            continue
        tn = re.search(r"（(\d{1,2})人気）", seg)
        run = re.search(PL + r" (\d\d)\.(\d\d)\.(\d\d)", seg)
        ch = re.search(r"\|(\d{1,2})\| \| \|(?:良|重|稍|不)\| \|\d{1,2}頭\|", seg)
        hs.append(dict(ub=ub, name=nm.group(1),
                       tn=(int(tn.group(1)) if tn else None),
                       zplace=(run.group(1) if run else None),
                       zdate=(f"20{run.group(2)}-{run.group(3)}-{run.group(4)}" if run else None),
                       zchaku=(int(ch.group(1)) if ch else None)))
    return (dist.group(1) if dist else "?"), hs


def main():
    pre = sys.argv[1]
    upto = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    print("■ 過去レースの水準を読み込み中…")
    races = load_races(); next_form(races); add_elo(races)
    idx = {(r["date"], r["place"]): [] for r in races}
    for r in races:
        idx.setdefault((r["date"], r["place"]), []).append(r)
    ln = sum(r["lo_n"] for r in races)
    base_l = sum(r["lo_win"] for r in races) / ln if ln else 0
    base_w = sum(r["nx_win"] for r in races) / sum(r["nx_n"] for r in races)
    print(f"  キャッシュ {len(races)}レース（{races[0]['date']}〜{races[-1]['date']}）")
    print(f"  基準：次走勝率 {base_w*100:.1f}% ／ 敗者の次走勝率 {base_l*100:.1f}%\n")

    for RR in range(1, upto+1):
        dist, hs = parse_card(fetch(pre, RR))
        rows = []
        for h in hs:
            cand = idx.get((h["zdate"], h["zplace"]), [])
            hit = next((r for r in cand if any(n == h["name"] for n, _, _ in r["rows"])), None)
            if not hit:
                rows.append((h, None, 0.0, "キャッシュに無い"))
                continue
            if not hit["lo_n"]:
                # レースはあるが、出走馬の『次走』がキャッシュに無い＝評価できない。
                # キャッシュの最終日に近いレースほどこうなる（追跡窓の打ち切り）。
                rows.append((h, None, 0.0, "次走データ未取得"))
                continue
            lift = (hit["lo_win"] / hit["lo_n"] / base_l) if base_l else 0
            rows.append((h, hit, lift, ""))
        rows.sort(key=lambda z: -z[2])
        print(f"── {RR}R ダ{dist}m {len(hs)}頭 ──")
        print(f"  {'番':>3} {'馬名':<15}{'今人気':>5}{'前走':>16}{'着':>4}  前走の水準")
        for h, r, lift, why in rows:
            zs = f"{h['zdate'] or '-'} {h['zplace'] or ''}"
            if not r:
                print(f"  {h['ub']:>3} {h['name']:<15}{h['tn'] or 0:>5}{zs:>16}{h['zchaku'] or 0:>4}  （{why}）")
                continue
            mark = "★" if (lift >= 2.0 and (h["zchaku"] or 0) >= 4) else " "
            print(f"  {h['ub']:>3} {h['name']:<15}{h['tn'] or 0:>5}{zs:>16}{h['zchaku'] or 0:>4} {mark}"
                  f" 敗者{r['lo_win']}/{r['lo_n']}={lift:.2f}倍  全体{r['nx_win']}/{r['nx_n']}"
                  f"  {r['place']}{r['rn']}R {r['name']}")
        print()
    print("★＝前走が『敗者の巻き返し率が基準の2倍以上』のレースで、そこで4着以下だった馬。")


if __name__ == "__main__":
    main()
