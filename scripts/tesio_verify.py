"""テシオ値(基礎体力・優先祖先活性)が中央レースの3着内と関係するか検証する。

指定レースの結果(race.netkeiba)から各馬のhorse_idを取り、5代血統表→テシオ分析。
3着内馬と着外馬で 基礎体力 / 優先祖先活性 の平均を比較し、点双列相関も出す。
※テシオは本来"素質選定"理論。レース単位の予測力は限定的な点に留意(著者も未実証)。

実行例:
    python3 scripts/tesio_verify.py --date 2026-06-27 --races 11   # 全場の11R
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bs4 import BeautifulSoup

from nankeiba.scraping import netkeiba as N
from nankeiba.scraping import pedigree as P


def result_rows_with_id(html: str):
    """結果テーブルから (finish_pos, umaban, horse_id, popularity) を返す。"""
    soup = BeautifulSoup(html, "html.parser")
    t = soup.find("table", class_=re.compile("RaceTable01"))
    if not t:
        return []
    rows = t.find_all("tr")
    head = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]

    def col(name):
        return next((i for i, h in enumerate(head) if h.startswith(name)), None)
    ci = {k: col(k) for k in ("着順", "馬番", "人気")}
    out = []
    for tr in rows[1:]:
        tds = tr.find_all(["td", "th"])
        if ci["着順"] is None or len(tds) <= ci["着順"]:
            continue
        fp = tds[ci["着順"]].get_text(strip=True)
        if not fp.isdigit():
            continue
        a = tr.find("a", href=re.compile(r"/horse/[0-9a-z]+"))
        hid = re.search(r"/horse/([0-9a-z]+)", a["href"]).group(1) if a else None
        um = tds[ci["馬番"]].get_text(strip=True) if ci["馬番"] is not None else ""
        pop = tds[ci["人気"]].get_text(strip=True) if ci["人気"] is not None else ""
        out.append((int(fp), int(um) if um.isdigit() else None,
                    hid, int(pop) if pop.isdigit() else None))
    return out


def pbcorr(xs, ys):
    n = len(xs)
    if n < 8:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = (sum((x - mx) ** 2 for x in xs) / n) ** 0.5
    sy = (sum((y - my) ** 2 for y in ys) / n) ** 0.5
    if sx == 0 or sy == 0:
        return None
    return sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / (n * sx * sy)


def main() -> None:
    ap = argparse.ArgumentParser(description="テシオ値 vs 中央3着内 検証")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--races", default="11", help="対象R(カンマ区切り。既定11)")
    ap.add_argument("--place", default=None, help="場で絞る")
    args = ap.parse_args()

    client = N.make_client(use_cache=True)
    target_r = {int(x) for x in args.races.split(",")}
    rids = [r for r in N.race_ids_for_date(client, args.date.replace("-", ""))
            if int(r[10:12]) in target_r and (not args.place or N.place_of(r) == args.place)]

    rows = []   # (place, R, finish, um, pop, kiso, yusen_act, hit3)
    for rid in rids:
        try:
            res = result_rows_with_id(client.get(N.RESULT_LIVE_URL.format(race_id=rid)))
        except Exception:  # noqa: BLE001
            continue
        for fp, um, hid, pop in res:
            if not hid or not re.match(r"^\d{4}", hid):
                continue
            try:
                anc = P.parse_pedigree(client.get(P.PED_URL.format(horse_id=hid)))
                r = P.analyze(anc, int(hid[:4]))
            except Exception:  # noqa: BLE001
                continue
            ya = (r["yusen_sosen"] or {}).get("activity")
            rows.append((N.place_of(rid), int(rid[10:12]), fp, um, pop,
                         r["kiso_tairyoku"], ya, 1 if fp <= 3 else 0))

    print(f"\n=== {args.date} R{args.races} テシオ検証 ({len(rows)}頭) ===")
    print(f"{'場':>4}{'R':>3}{'着':>3}{'馬番':>4}{'人気':>4}{'基礎体力':>8}{'優先祖先活性':>12}")
    for pl, rno, fp, um, pop, k, ya, hit in sorted(rows, key=lambda x: (x[1], x[2])):
        mark = "★" if hit else " "
        print(f"{pl:>4}{rno:>3}{fp:>3}{(um or '?'):>4}{(pop or '?'):>4}"
              f"{(k if k is not None else '—'):>8}{(ya if ya is not None else '—'):>12}{mark}")

    # 3着内 vs 着外 の平均比較 + 相関
    def stat(key_idx, label):
        vals = [(r[key_idx], r[7]) for r in rows if r[key_idx] is not None]
        if len(vals) < 8:
            print(f"\n{label}: データ不足")
            return
        in3 = [v for v, h in vals if h]
        out3 = [v for v, h in vals if not h]
        r = pbcorr([v for v, _ in vals], [h for _, h in vals])
        m_in = sum(in3) / len(in3) if in3 else 0
        m_out = sum(out3) / len(out3) if out3 else 0
        print(f"\n{label}: 3着内平均 {m_in:.1f}(n={len(in3)}) / 着外平均 {m_out:.1f}(n={len(out3)})"
              f" / 相関r={r:+.3f}" if r is not None else "")

    stat(5, "基礎体力")
    stat(6, "優先祖先活性")
    print("\n※テシオは素質選定理論。レース単位は小標本かつ限定的。傾向の参考まで。")


if __name__ == "__main__":
    main()
