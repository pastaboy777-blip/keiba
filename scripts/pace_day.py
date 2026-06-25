"""ある日・ある場の結果からラップと通過順を読み、展開(トラックバイアス)を判定する。

楽天競馬の競走成績ページには『ハロンタイム』(各F のラップ)と『コーナー通過順位』が
載っている。これを使って各レースの:
  - 前半3F vs 上がり3F → ペース(前傾=ハイ→差し有利 / 後傾=スロー→前残り)
  - 勝ち馬の最終コーナー位置 → 勝ち脚質(逃げ/先行/中団/後方)
を出し、最後に当日全体の傾向(前残りか差し決まりか)をまとめる。

明日の展開読みの材料(同コース・同馬場の直近トレンド)に使う。結果確定直後は --no-cache。

実行例:
    python3 scripts/pace_day.py --date 2026-06-24 --place 浦和
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bs4 import BeautifulSoup

from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{race_id}"
RESULT = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{race_id}"


def parse_laps(html: str):
    """『ハロンタイム』行から各Fのラップ[秒]リストを取り出す。無ければ []。"""
    soup = BeautifulSoup(html, "html.parser")
    for tr in soup.find_all("tr"):
        th = tr.find("th")
        if th and "ハロンタイム" in th.get_text():
            td = tr.find("td")
            if td:
                return [float(x) for x in re.findall(r"\d+\.\d+", td.get_text())]
    return []


def winner_agari(html: str):
    """1着馬の推定上がり3F[秒](td.spurt)を返す。無ければ None。"""
    soup = BeautifulSoup(html, "html.parser")
    for tr in soup.find_all("tr"):
        od = tr.find("td", class_="order")
        if od and od.get_text(strip=True) == "1":
            sp = tr.find("td", class_="spurt")
            if sp:
                m = re.search(r"\d+\.\d+", sp.get_text())
                return float(m.group()) if m else None
    return None


def last_corner_order(html: str):
    """最終コーナーの通過順(馬番の並び・前→後)を返す。無ければ []。

    例 '(1,5),6-4,(3,8,9),7-2,10' → [1,5,6,4,3,8,9,7,2,10]。
    括弧(同位)も順序として展開する。
    """
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.find_all("tr"):
        th = tr.find("th")
        # 浦和は『１角〜４角』、笠松等は『最初の直線/第２コーナー…』表記。両対応。
        if th and re.search(r"角|コーナー|直線", th.get_text()):
            td = tr.find("td")
            if td and re.search(r"\d", td.get_text()):
                rows.append(td.get_text(strip=True))
    if not rows:
        return []
    return [int(x) for x in re.findall(r"\d+", rows[-1])]


def pace_label(first3: float, last3: float) -> str:
    """前半3F と 上がり3F の差でラップ形状を分類。

    ※地方ダートは上がりが構造的に落ちる(前半>上がりが常態)ため、ラップだけで
    『差し有利』とは結論しない。脚質分布(実際に何が勝ったか)を当日傾向の主判定に使う。
    """
    diff = last3 - first3   # 正=前半が速い(前傾) / 負=後傾
    if diff >= 4.0:
        return "超前傾(前半暴走)"
    if diff >= 1.5:
        return "前傾"
    if diff <= -0.5:
        return "後傾(緩み)"
    return "平均"


def style_of(umaban, order, field):
    """最終コーナーの並びでの位置から勝ち脚質を判定。"""
    if not order or umaban not in order:
        return "?"
    pos = order.index(umaban)
    n = len(order)
    r = pos / (n - 1) if n > 1 else 0.0
    if r <= 0.15:
        return "逃げ"
    if r <= 0.4:
        return "先行"
    if r <= 0.7:
        return "中団"
    return "後方"


def main() -> None:
    ap = argparse.ArgumentParser(description="1日分 ラップ・通過順から展開を読む")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--place", choices=list(ALL_CODES), required=True)
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    ymd = args.date.replace("-", "")
    client = PoliteClient(use_cache=not args.no_cache)
    idx = client.get(CARD.format(race_id=day_index_race_id(ymd, args.place)))
    races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[args.place]))
    if not races:
        raise SystemExit(f"{args.date} {args.place} のレースが見つかりません。")

    print(f"\n=== {args.date} {args.place} 展開読み(ラップ＋通過順) ===")
    print(f"{'R':>3} {'距離':>7} {'勝T':>8} {'上3F':>5} {'脚質':<5}{'前半3F':>6} {'ラップ展開':<18}勝ち馬")
    styles = {"逃げ": 0, "先行": 0, "中団": 0, "後方": 0, "?": 0}
    pace_counts = {"前傾": 0, "後傾": 0, "平均": 0}
    for rno in sorted(races):
        rid = races[rno]
        try:
            html = client.get(RESULT.format(race_id=rid))
            res = P.parse_result_page(html, rid)
        except Exception:  # noqa: BLE001
            continue
        if not res.rows:
            continue
        laps = parse_laps(html)
        order = last_corner_order(html)
        win = res.rows[0]
        agari = winner_agari(html)            # 1着馬の推定上がり3F(笠松等ラップ無でも取れる)
        if len(laps) >= 6:
            first3, last3 = sum(laps[:3]), sum(laps[-3:])
            lab = pace_label(first3, last3)
            f3 = f"{first3:.1f}"
        else:
            lab, f3 = "—(ラップ無)", "—"
        l3 = f"{agari:.1f}" if agari else "—"   # 上がりは勝ち馬の推定上がりを使う
        st = style_of(win.umaban, order, res.field_size)
        styles[st] = styles.get(st, 0) + 1
        if "前傾" in lab:
            pace_counts["前傾"] += 1
        elif "後傾" in lab:
            pace_counts["後傾"] += 1
        elif lab == "平均":
            pace_counts["平均"] += 1
        wn = next((r.horse_name for r in res.rows if r.umaban == win.umaban), "")
        wt = win.time or "—"
        print(f"{rno:>3} {('ダ'+str(res.distance)):>7} {wt:>8} {l3:>5} {st:<5}"
              f"{f3:>6} {lab:<18}①{win.umaban} {wn}")

    classified = styles['逃げ'] + styles['先行'] + styles['中団'] + styles['後方']
    n = sum(styles.values())
    print(f"\n--- 当日サマリー({n}R) ---")
    if classified == 0:
        print("勝ち脚質: 判定不可(通過順データが取得できず)")
        return
    fronts = styles['逃げ'] + styles['先行']
    print(f"勝ち脚質: 逃げ{styles['逃げ']}・先行{styles['先行']}・"
          f"中団{styles['中団']}・後方{styles['後方']}")
    print(f"ラップ形状: 前傾{pace_counts['前傾']}・平均{pace_counts['平均']}・"
          f"後傾{pace_counts['後傾']}")
    ratio = fronts / classified
    if ratio >= 0.6:
        verdict = "★前残り馬場(逃げ・先行が圧倒的)→ 明日も前で運べる馬を厚く"
    elif ratio <= 0.35:
        verdict = "★差し決まる馬場(中団・後方が好走)→ 明日は差し・展開崩れ狙い"
    else:
        verdict = "フラット(脚質偏りは小さい)→ 展開・枠で個別判断"
    print(f"前(逃げ+先行)勝率 {fronts}/{classified} = {ratio*100:.0f}%  {verdict}")


if __name__ == "__main__":
    main()
