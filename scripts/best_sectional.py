"""区間自己ベスト(breakthrough)検証: 前走で上がり3Fの自己ベストを更新した馬は今走で走るか。

仮説: 負けたレースでも『上がり3F(後3F)が自己ベスト』を出した馬＝能力が一段上がった予兆。
市場は着順しか見ないので、次走で過小評価＝妙味。
各馬の過去走の上がりは出馬表(shutuba_past)にインライン → 軽量に取得できる。

検証: 対象レースの各馬について
  - 前走(最新)の上がり3F が それ以前の自己ベストを更新したか
  - 今走の3着内 / 複勝ROI を 更新組 vs 非更新組 で比較
中央(netkeiba)向け。

実行例:
    python3 scripts/best_sectional.py --date 2026-06-21 --place 函館
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from bs4 import BeautifulSoup

from nankeiba.scraping import netkeiba as N
import nk_zubu


def agari_by_umaban(html):
    """shutuba_past → {馬番: [上がり3F, ...]}(新しい順)。Data06の(xx.x)が上がり。"""
    soup = BeautifulSoup(html, "html.parser")
    t = soup.find("table", class_=re.compile("Shutuba_Past5"))
    if not t:
        return {}
    tb = t.find("tbody") or t
    out, um, cur = {}, 0, None
    for td in tb.find_all("td"):
        classes = td.get("class") or []
        if any(re.fullmatch(r"Waku[1-8]", c) for c in classes):
            um += 1
            cur = []
            out[um] = cur
        elif cur is not None and "Past" in classes:
            d06 = td.find("div", class_="Data06")
            if d06:
                m = re.search(r"\((\d{2}\.\d)\)", d06.get_text())
                if m:
                    cur.append(float(m.group(1)))
    return out


def main():
    ap = argparse.ArgumentParser(description="区間自己ベスト(上がり)検証")
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", default=None)
    ap.add_argument("--races", default=None)
    ap.add_argument("--min-past", type=int, default=3, help="判定に必要な過去走数")
    args = ap.parse_args()

    client = N.make_client(use_cache=True)
    rids = N.race_ids_for_date(client, args.date.replace("-", ""))
    if args.place:
        rids = [r for r in rids if N.place_of(r) == args.place]
    if args.races:
        tr = {int(x) for x in args.races.split(",")}
        rids = [r for r in rids if int(r[10:12]) in tr]

    acc = {"自己ベスト更新": [0, 0, 0, 0], "非更新": [0, 0, 0, 0]}  # 投資,払戻,的中,頭数
    for rid in rids:
        try:
            res = N.parse_result(client.get(N.RESULT_URL.format(race_id=rid)))
            pay = N.parse_payoffs(client.get(N.RESULT_URL.format(race_id=rid)))
        except Exception:  # noqa: BLE001
            continue
        if not res:
            continue
        place_o = pay.get("place", {})
        ag = agari_by_umaban(client.get(nk_zubu.PAST_URL.format(race_id=rid)))
        for r in res:
            a = ag.get(r["umaban"]) or []
            if len(a) < args.min_past:
                continue
            # 前走(a[0])がそれ以前の最速(min)を更新=自己ベスト(小さい=速い)
            updated = a[0] <= min(a[1:]) - 0.0   # 厳密更新は < に、同値含むなら <=
            key = "自己ベスト更新" if a[0] < min(a[1:]) else "非更新"
            b = acc[key]
            b[0] += 100
            b[3] += 1
            if r["finish_pos"] <= 3:
                b[2] += 1
                b[1] += place_o.get(r["umaban"], 0)

    print(f"\n=== 区間自己ベスト(前走の上がり3F)検証 {args.date} {args.place or '全場'} ===")
    print(f"{'区分':<14}{'頭数':>5}{'3着内':>6}{'3着内率':>8}{'複勝ROI':>9}")
    for name, (inv, ret, hit, n) in acc.items():
        if not n:
            continue
        print(f"{name:<14}{n:>5}{hit:>6}{100*hit/n:>7.1f}%{(100*ret/inv if inv else 0):>8.1f}%")
    print("\n※『更新』が『非更新』より3着内率/ROIで上回れば、区間自己ベストは先行指標として有効。")


if __name__ == "__main__":
    main()
