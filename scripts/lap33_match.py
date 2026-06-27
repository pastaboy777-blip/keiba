"""33ラップ適性マッチ検証: 馬の過去好走時の33ラップ ≒ 今回レースの33ラップ なら好走するか。

仮説(33ラップ理論): 馬は瞬発型/持久型の適性を持ち、レースの質(33ラップ)が
自分の適性に合うと好走する。検証:
  - 各馬の適性 = 過去走(shutuba_pastの近走)のうち好走(3着内)時の33ラップ平均
    (各過去レースの全ラップを db/live 結果から取得して算出)
  - 今回レースの実33ラップ
  - マッチ度 = |適性 - 今回33ラップ| (小さい=適性が合致)
  - マッチ度と『今回3着内か』の関係を見る(小さいほど好走するはず)
※過去走ラップ取得が重い(馬×過去走)ため対象を絞って実行する。

実行例:
    python3 scripts/lap33_match.py --date 2026-06-27 --races 11,12 --place 函館
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
import lap33 as L33

PAST_URL = "https://race.netkeiba.com/race/shutuba_past.html?race_id={race_id}"


def race33_of(client, rid):
    h = L33.get_result_html(client, rid)
    return L33.lap33(N.parse_laps(h)) if h else None


def past_races_by_umaban(html):
    """shutuba_past から {馬番: [(過去race_id, 過去着順), ...]} を返す(馬番順)。"""
    soup = BeautifulSoup(html, "html.parser")
    t = soup.find("table", class_=re.compile("Shutuba_Past5"))
    if not t:
        return {}
    tb = t.find("tbody") or t
    out = {}
    um = 0
    cur = None
    for td in tb.find_all("td"):
        classes = td.get("class") or []
        if any(re.fullmatch(r"Waku[1-8]", c) for c in classes):
            um += 1
            cur = []
            out[um] = cur
        elif cur is not None and "Past" in classes:
            a = td.find("a", href=re.compile(r"/race/\d"))
            num = td.find("span", class_="Num")
            if a:
                rid = re.search(r"/race/(\d+)", a["href"]).group(1)
                fp = int(num.get_text(strip=True)) if num and num.get_text(strip=True).isdigit() else None
                cur.append((rid, fp))
    return out


def main():
    ap = argparse.ArgumentParser(description="33ラップ適性マッチ検証")
    ap.add_argument("--date", required=True)
    ap.add_argument("--races", default="11,12")
    ap.add_argument("--place", default=None)
    ap.add_argument("--max-past", type=int, default=4, help="1頭あたり遡る過去走数")
    args = ap.parse_args()

    client = N.make_client(use_cache=True)
    target = {int(x) for x in args.races.split(",")}
    rids = [r for r in N.race_ids_for_date(client, args.date.replace("-", ""))
            if int(r[10:12]) in target and (not args.place or N.place_of(r) == args.place)]

    cache33 = {}

    def get33(rid):
        if rid not in cache33:
            cache33[rid] = race33_of(client, rid)
        return cache33[rid]

    samples = []  # (place,R,umaban,finish,apt,race33,match)
    for rid in rids:
        race33 = get33(rid)
        if race33 is None:
            continue
        # 今回の結果(着順・馬番)
        from tesio_verify import result_rows_with_id  # 再利用
        res = {um: fp for fp, um, hid, pop in result_rows_with_id(
            client.get(N.RESULT_LIVE_URL.format(race_id=rid))) if um}
        past = past_races_by_umaban(client.get(PAST_URL.format(race_id=rid)))
        for um, fp in res.items():
            good = []   # 好走(3着内)時の過去33ラップ
            allp = []
            for prid, pfin in (past.get(um) or [])[:args.max_past]:
                v = get33(prid)
                if v is None:
                    continue
                allp.append(v)
                if pfin and pfin <= 3:
                    good.append(v)
            base = good or allp
            if not base:
                continue
            apt = sum(base) / len(base)
            samples.append((N.place_of(rid), int(rid[10:12]), um, fp, apt, race33,
                            abs(apt - race33)))

    print(f"\n=== 33ラップ適性マッチ検証 {args.date} R{args.races} ({len(samples)}頭) ===")
    print(f"{'場':>4}{'R':>3}{'馬番':>4}{'着':>3}{'適性':>7}{'今回33':>8}{'マッチ度':>8}")
    for s in sorted(samples, key=lambda x: (x[1], x[3])):
        mk = "★" if s[3] <= 3 else " "
        print(f"{s[0]:>4}{s[1]:>3}{s[2]:>4}{s[3]:>3}{s[4]:>+7.1f}{s[5]:>+8.1f}{s[6]:>8.1f}{mk}")

    in3 = [s[6] for s in samples if s[3] <= 3]
    out3 = [s[6] for s in samples if s[3] > 3]
    if in3 and out3:
        print(f"\nマッチ度(小=適性合致): 3着内平均 {sum(in3)/len(in3):.2f} / 着外平均 {sum(out3)/len(out3):.2f}")
        print("※3着内の方がマッチ度が小さい(適性が合致)なら、33ラップ適性が効いている証拠。")


if __name__ == "__main__":
    main()
