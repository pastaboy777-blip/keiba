"""その日のレースから『ズブ穴6頭BOXを張るべき荒れそうなレース』を自動判定する。

荒れ度スコア = 多頭数 + 道悪 + 下級条件 + 荒れ距離 の合算(出馬表+想定馬場から)。
スコアで BOXサイズ(本線3頭 / 4頭 / 6頭)を推奨する。
--validate を付けると実結果で『荒れたか(勝ち馬5番人気↓)』と突き合わせる。

⚠️ 検証注記: 笠松2026-06-25 で 6頭BOX推奨 0/3(逆相関)。重みは浦和3日の傾向で仮置きで
   笠松へ転移せず。実運用前に複数日・複数場で学習し直す必要あり(現状は雛形)。

実行例:
    python3 scripts/box_finder.py --date 2026-06-25 --place 笠松 --baba 重 --validate
"""
from __future__ import annotations
import argparse, sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
os.chdir(ROOT)
import predict_nankan as PN
from track_report import grade
from nankeiba.scraping.race_id import NANKAN_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

EXTRA_CODES = {"門別": "36", "笠松": "23", "園田": "27", "佐賀": "32", "名古屋": "26",
               "金沢": "24", "高知": "31", "姫路": "28", "水沢": "35", "盛岡": "34"}
CLS_PTS = {"C3": 2.0, "C2": 1.5, "3歳": 0.5, "他": 0.5, "?": 0.5,
           "C1": -1.0, "B": -1.0, "A": -1.5, "2歳": -2.0, "OP": -1.0}


def are_score(card, baba):
    s = 0.0; why = []
    fs = card.field_size or 0
    if fs >= 14: s += 2; why.append(f"多頭数{fs}")
    elif fs >= 12: s += 1; why.append(f"頭数{fs}")
    g = grade(getattr(card, "race_class", None))
    cp = CLS_PTS.get(g, 0.0); s += cp
    if cp > 0: why.append(f"下級{g}")
    elif cp < 0: why.append(f"上級{g}")
    if baba in ("重", "不"): s += 1.5; why.append(f"道悪{baba}")
    elif baba == "稍": s += 0.5; why.append("稍重")
    d = card.distance or 0
    if d == 1400: s += 1; why.append("1400m荒")
    elif d == 1500: s -= 1; why.append("1500m堅")
    return s, g, why


def rec_of(score):
    if score >= 3: return "★6頭BOX"
    if score >= 1.5: return "○4頭BOX"
    return "−本線3頭"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--baba", choices=["良", "稍", "重", "不"], default="重")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()
    code = NANKAN_CODES.get(args.place) or EXTRA_CODES.get(args.place)
    if not code:
        raise SystemExit(f"unknown place: {args.place}")
    ymd = args.date.replace("-", "")
    c = PoliteClient(use_cache=not args.no_cache)
    src = PN.RESULT_URL if args.validate else PN.CARD_URL
    races = dict(P.parse_race_links(c.get(src.format(race_id=ymd + code + "00000000")),
                                    date_yyyymmdd=ymd, jyo_code=code))
    print(f"=== {args.place} {args.date} baba={args.baba} BOX判定 ===")
    hits = miss = 0
    for rno in sorted(races):
        rid = races[rno]
        try:
            card = P.parse_card_page(c.get(PN.CARD_URL.format(race_id=rid)), rid)
        except Exception:
            continue
        score, g, why = are_score(card, args.baba)
        line = f"{rno:>2}R {card.surface}{card.distance}m [{g}] {(card.field_size or 0)}t score{score:+.1f} {rec_of(score)} ({'・'.join(why)})"
        if args.validate:
            try:
                res = P.parse_result_page(c.get(PN.RESULT_URL.format(race_id=rid)), rid)
                if res.rows:
                    wp = res.rows[0].popularity
                    arare = bool(wp and wp >= 5)
                    if score >= 3:
                        if arare: hits += 1
                        else: miss += 1
                    line += f" | 1st {wp}nin {'ARARE' if arare else 'kata'}"
            except Exception:
                pass
        print(line)
    if args.validate:
        print(f"\n6BOX rec races hit(winner>=5nin): {hits}/{hits+miss}")


if __name__ == "__main__":
    main()
