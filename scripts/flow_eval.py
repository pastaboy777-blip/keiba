"""前走の『レースの流れ』を差し引いて、各馬を 次走狙い/危険 に評価する。

着順は流れ(展開)に左右される。流れを差し引いて本当の中身を見る:
  - 各過去走の失速幅(コーナー出口の急加速後にどれだけ垂れたか)でレースの流れ型を判定
      失速幅 大 = 前崩壊(差し有利) / 小 = 前残り(前有利) / 中間
  - その馬の脚質(過去走の通過順=前/後)と着順を突き合わせ:
      流れ恵まれ(着順が実力以上=次危険) / 流れ泣き(着順が実力以下=次狙い)
  - 直近数走を集計し、ネットで 狙い/危険/中立 を出す。

データ: 出馬表(shutuba_past)の各馬近走(通過順・着順・頭数)＋各過去レースのラップ。
中央(netkeiba)向け。重いので対象レースを絞って実行。

実行例:
    python3 scripts/flow_eval.py --race-id 202602010611
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
import lap33 as L33


def past_details(html):
    """shutuba_past → {馬番: [(race_id, 着順, 頭数, 最終コーナー位置)]}。"""
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
            a = td.find("a", href=re.compile(r"/race/\d"))
            if not a:
                continue
            rid = re.search(r"/race/(\d+)", a["href"]).group(1)
            num = td.find("span", class_="Num")
            fp = int(num.get_text(strip=True)) if num and num.get_text(strip=True).isdigit() else None
            d03 = td.find("div", class_="Data03")
            d06 = td.find("div", class_="Data06")
            field = None
            if d03:
                fm = re.search(r"(\d+)頭", d03.get_text())
                field = int(fm.group(1)) if fm else None
            last = None
            if d06:
                cm = re.match(r"\s*([\d-]+)", d06.get_text(" ", strip=True))
                if cm and "-" in cm.group(1):
                    last = int(cm.group(1).split("-")[-1])
            cur.append((rid, fp, field, last))
    return out


def flow_type(shissoku):
    """失速幅から流れ型。"""
    if shissoku is None:
        return None
    if shissoku >= 1.5:
        return "前崩壊"      # 差し有利
    if shissoku <= 0.6:
        return "前残り"      # 前有利
    return "中間"


def classify(flow, style, hit):
    """流れ型×脚質(前/後)×好走 → タグ。"""
    if flow is None or style is None:
        return None
    favored = "後" if flow == "前崩壊" else "前" if flow == "前残り" else None
    if favored is None:
        return None
    if style == favored and hit:
        return ("恵", "流れ恵まれ(着順は流れの利)")       # 次危険
    if style != favored and not hit:
        return ("泣", "流れ泣き(流れ逆風で凡走)")          # 次狙い
    if style != favored and hit:
        return ("強", "流れに逆らい好走=真に強い")
    return ("弱", "流れ向きでも凡走=不振")


def main():
    ap = argparse.ArgumentParser(description="前走の流れで次走 狙い/危険 評価")
    ap.add_argument("--race-id", required=True)
    ap.add_argument("--max-past", type=int, default=4)
    args = ap.parse_args()

    client = N.make_client(use_cache=True)
    rid = args.race_id
    ph = client.get(nk_zubu.PAST_URL.format(race_id=rid))
    horses = nk_zubu.parse_past_table(ph)            # umaban, horse, jockey
    det = past_details(ph)
    namemap = {h["umaban"]: h["horse"] for h in horses}

    ca_cache = {}

    def shissoku_of(prid):
        if prid not in ca_cache:
            h = L33.get_result_html(client, prid)
            laps = N.parse_laps(h) if h else []
            ca_cache[prid] = (round(laps[-2] - laps[-3], 2) if len(laps) >= 4 else None)
        return ca_cache[prid]

    print(f"\n=== {N.place_of(rid)} {int(rid[10:12])}R 流れ評価(前走の流れを差し引く) ===")
    results = []
    for um in sorted(det):
        tags = []
        for prid, fp, field, last in det[um][:args.max_past]:
            if fp is None or field is None or last is None:
                continue
            sh = shissoku_of(prid)
            flow = flow_type(sh)
            style = "前" if last / field <= 0.4 else "後" if last / field >= 0.6 else "中"
            c = classify(flow, style, fp <= 3)
            if c:
                tags.append(c[0])
        score = tags.count("泣") - tags.count("恵")
        stance = ("◎次狙い(流れ泣き)" if score >= 1 else
                  "▲次危険(流れ恵まれ)" if score <= -1 else "中立")
        results.append((um, namemap.get(um, "?"), tags, score, stance))

    for um, nm, tags, score, stance in sorted(results, key=lambda x: -x[3]):
        tg = "".join(tags) if tags else "—"
        print(f"  {um:>2} {nm[:12]:<13} 直近[{tg:<6}] {stance}")
    print("\n泣=流れ泣き(次狙い) 恵=流れ恵まれ(次危険) 強=流れ逆らい好走 弱=不振")
    print("※着順を流れで補正した評価。流れ泣きの人気薄＝妙味、流れ恵まれの人気馬＝危険。")


if __name__ == "__main__":
    main()
