#!/usr/bin/env python3
"""コーナー通過順(keibabook・内→外並び)から"レーン(内/外)"を機械抽出し、
当日の「内有利/外有利」トラックバイアスを4角の内側順位で集計する。

発見(2026-07-20大井)：keibabookのコーナー通過順は () が併走(横並び)で、
グループ内は内→外の順(最内の馬が先頭に書かれる)。よって各馬の4角レーン
(最内=0,2列目=1,…)が読める。7/20大井は馬券圏36頭中 最内20/2列目13/外3＝
内2列で約92%＝終日"内・ロスなし"の圧倒的バイアス。狙い＝内で脚を溜める人気薄。

使い方:
  export KEIBABOOK_COOKIE="..."          # 成績ページ取得に必要
  python3 scripts/corner_bias.py --date 2026-07-20 --place 大井           # 当日集計
  python3 scripts/corner_bias.py --date 2026-07-20 --place 大井 --race 5  # 1R詳細

出力: 各Rの4角レーン×着順、当日の 内2列/外 の馬券圏比率(=バイアス強度)。
"""
import sys, os, re, argparse, urllib.request
from bs4 import BeautifulSoup

sys.path.insert(0, "scripts")
sys.path.insert(0, "src")
import keibabook_chokyo as K
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"
CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"


def _kb(path):
    ck = os.environ.get("KEIBABOOK_COOKIE", "")
    req = urllib.request.Request("https://p.keibabook.co.jp" + path,
                                 headers={"User-Agent": UA, "Cookie": ck})
    return urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")


def parse_lanes(seg):
    """1コーナー分の通過順(内→外)→ {馬番:(前後位置1〜, 内側順0=最内, 併走幅)}。"""
    out = {}
    pos = 0
    for grp, single in re.findall(r"\(([\d,]+)\)|(\d+)", seg):
        members = [int(x) for x in grp.split(",")] if grp else [int(single)]
        pos += 1
        for ir, u in enumerate(members):   # ir=0 が最内
            out[u] = (pos, ir, len(members))
    return out


def corner_lanes(rid, which="４角"):
    """keibabook成績ページから指定コーナーのレーン辞書。4角優先、無ければ3角。"""
    txt = BeautifulSoup(_kb(f"/chihou/seiseki/{rid}"), "html.parser").get_text(" ", strip=True)
    m4 = re.search(r"４角\s*([0-9,()\-= ]+?)\s*(?:ペース|■|払戻|＝|$)", txt)
    m3 = re.search(r"３角\s*([0-9,()\-= ]+?)\s*４角", txt)
    if which == "４角" and m4:
        return parse_lanes(m4.group(1))
    if m3:
        return parse_lanes(m3.group(1))
    return parse_lanes(m4.group(1)) if m4 else {}


def lane_label(p):
    if not p:
        return "?"
    return "最内" if p[1] == 0 else ("2列目" if p[1] == 1 else f"{p[1]+1}列目(外)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--race", type=int, default=None)
    a = ap.parse_args()
    ymd = a.date.replace("-", "")
    kb = {r["race_no"]: r["id"] for r in K.race_ids_for_date(ymd) if r["place"] == a.place}
    c = PoliteClient()
    idx = c.get(CARD.format(r=day_index_race_id(ymd, a.place)), use_cache=True)
    rjp = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[a.place]))
    races = [a.race] if a.race else sorted(rjp)
    inner2 = outer = 0
    print(f"=== {a.date} {a.place} 4角レーン×着順（内→外はkeibabook通過順） ===")
    for R in races:
        if R not in kb or R not in rjp:
            continue
        try:
            lanes = corner_lanes(kb[R])
            rr = P.parse_result_page(c.get(PERF.format(r=rjp[R]), use_cache=True), rjp[R])
        except Exception:
            continue
        t3 = [row.umaban for row in rr.rows[:3] if row.finish_pos]
        if not t3:
            continue
        cells = []
        for u in t3:
            p = lanes.get(u)
            cells.append(f"{u}({'前' + str(p[0]) if p else '?'}/{lane_label(p)})")
            if p:
                if p[1] <= 1:
                    inner2 += 1
                else:
                    outer += 1
        print(f"  {R:>2}R 着{t3} → 4角 {'  '.join(cells)}")
    tot = inner2 + outer
    if tot:
        print(f"\n--- 当日バイアス: 馬券圏の内2列(最内+2列目)={inner2}/{tot}={inner2/tot:.0%}"
              f" / 外(3列目〜)={outer}/{tot}={outer/tot:.0%} ---")
        print("  ≥75%内2列 → 強い内有利＝内枠×立ち回り(内で脚を溜める)人気薄を加点。外差し・外先行は割引。")


if __name__ == "__main__":
    main()
