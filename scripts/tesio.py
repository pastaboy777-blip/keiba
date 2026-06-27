"""テシオ理論(自分流)で1頭の血統を分析する独立ツール。

netkeibaの5代血統表から各先祖の活性値を算出し、優先祖先・基礎体力を出す。
血統データ取得は netkeiba、計算は pedigree モジュール(活性値式は記事の実例で検証済)。

実行例:
    python3 scripts/tesio.py --horse-id 2002100816          # ディープインパクト
    python3 scripts/tesio.py --name キタサンブラック         # 馬名検索
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nankeiba.scraping import netkeiba as N
from nankeiba.scraping import pedigree as P


def search_horse_id(client, name):
    """馬名で netkeiba 馬IDを検索(先頭一致)。"""
    import urllib.parse
    url = "https://db.netkeiba.com/?pid=horse_list&word=" + urllib.parse.quote(name)
    html = client.get(url, use_cache=False)
    m = re.search(r"/horse/(\d{10})", html)
    return m.group(1) if m else None


def main() -> None:
    ap = argparse.ArgumentParser(description="テシオ理論(自分流) 血統分析")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--horse-id", help="netkeiba 馬ID(10桁)")
    g.add_argument("--name", help="馬名で検索")
    args = ap.parse_args()

    client = N.make_client(use_cache=True)
    hid = args.horse_id or search_horse_id(client, args.name)
    if not hid:
        raise SystemExit("馬が見つかりません。")

    html = client.get(P.PED_URL.format(horse_id=hid))
    anc = P.parse_pedigree(html)
    if not anc:
        raise SystemExit("血統表のパースに失敗。")
    subject_year = int(hid[:4])     # netkeiba 馬IDの先頭4桁=生年
    res = P.analyze(anc, subject_year)

    nm = anc.get("S", {}).get("name", "?")
    print(f"\n=== テシオ分析(自分流) 馬ID {hid} / 推定生年 {subject_year} ===")

    print("\n[主要先祖の活性値]")
    labels = [("S", "父"), ("SS", "父父"), ("SD", "父母"),
              ("D", "母"), ("DS", "母父"), ("DD", "母母"),
              ("DDS", "母母父"), ("DDD", "3代母"), ("DDDD", "4代母")]
    for path, lab in labels:
        a = anc.get(path)
        if not a:
            continue
        act = res["activity"].get(path)
        star = " ★MAX8" if act == 8 else ""
        print(f"  {lab:<5}{a['name'][:22]:<22} 生年{a['year'] or '?'}  活性値 {act if act is not None else '—'}{star}")

    ys = res["yusen_sosen"]
    print("\n[優先祖先(形=適性の芯)]")
    if ys:
        print(f"  → {ys['name']} （{ys['side']}・活性値{ys['activity']}・父との差{ys['diff']}）")
        if ys["activity"] == 8:
            print("    ★優先祖先が最大活性8 = 高評価パターン(祖先の特徴が強く遺伝)")
    else:
        print("  判定不可(活性値の欠落)")

    k = res["kiso_tairyoku"]
    print("\n[基礎体力(質料=タフさ)]")
    if k is not None:
        da = " + ".join(f"{lab}={res['activity'].get(p)}"
                        for p, lab in [("D", "母"), ("DD", "2代母"), ("DDD", "3代母"), ("DDDD", "4代母")])
        verdict = ("★タフ(使い詰めOK・連戦上積み)" if k >= 70 else
                   "休み明け向き(使い詰めで割引)" if k < 30 else "標準")
        print(f"  ({da}) ÷32×100 = {k}点  {verdict}")
    else:
        print("  算出不可(母系の生年欠落)")

    inb = res.get("inbreeding") or []
    print("\n[インブリード(クロス)/ 影響度=活性加重・順]")
    if not inb:
        print("  クロスなし(アウトブリード)")
    for c in inb[:6]:
        acts = "/".join(str(a) if a is not None else "—" for a in c["activities"])
        hot = " ★高活性クロス" if any(a == 8 for a in c["activities"] if a) and max(c["gens"]) <= 4 else ""
        print(f"  {c['name'][:22]:<22} {c['cross']}  影響度{c['strength']:.3f}"
              f"(世代のみ{c['strength_gen']:.3f})  活性[{acts}]{hot}")
    if inb:
        print("  ※影響度=世代の近さ×活性(高活性ほど子孫に強く伝わる)。クロス=悪ではない(良悪は別)。")


if __name__ == "__main__":
    main()
