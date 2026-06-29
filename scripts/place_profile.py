"""場(トラック)の素性プロファイルを過去開催から測る＝予想前の「prior(事前分布)」を作る。

朝イチ予想は当日4Rの実測(鉄則7)を待たないと流れが分からない。そこで過去の同場開催から
『この場は前残りか/持続戦か/穴はどの脚質か』をあらかじめ測り、朝の前提に使う。
南関(楽天・当日ラップ有)向け。

測る指標:
  - 勝ち脚質分布(逃/先/中/後)＝前残り度
  - 平均失速幅・平均ラスト失速(>=0.8で持続戦傾向)
  - 距離帯別の勝ち脚質＆後方が3着内に来たレース率
  - 6人気以下で3着内に来た馬の脚質分布(=穴の正体)

実行例:
    python3 scripts/place_profile.py --place 大井 --dates 20260608,20260609,20260610,20260611,20260612,20260629
"""

from __future__ import annotations

import argparse
import statistics as S
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping import parser as P
import pace_day as PD

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/"


def style(um, order, field):
    lp = (order.index(um) + 1) if um in order else None
    if not lp or not field or field < 2:
        return "?"
    r = (lp - 1) / (field - 1)
    return "逃" if r <= 0.15 else "先" if r <= 0.4 else "中" if r <= 0.7 else "後"


def dist_bin(d):
    d = d or 0
    return "〜1300" if d <= 1300 else "1400-1600" if d <= 1600 else "1700+"


def main():
    ap = argparse.ArgumentParser(description="場の素性プロファイル(prior)を過去開催から測る")
    ap.add_argument("--place", choices=list(ALL_CODES), required=True)
    ap.add_argument("--dates", required=True, help="YYYYMMDD をカンマ区切りで")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    c = PoliteClient(use_cache=not args.no_cache)
    days = [d.strip() for d in args.dates.split(",") if d.strip()]

    win = defaultdict(int)
    ana = defaultdict(int)             # 6人気以下3着内の脚質
    fades, shis = [], []
    distbin = defaultdict(lambda: defaultdict(int))
    backbydist = defaultdict(lambda: [0, 0])
    nR = 0
    for ymd in days:
        try:
            races = dict(P.parse_race_links(
                c.get(CARD + day_index_race_id(ymd, args.place)),
                date_yyyymmdd=ymd, jyo_code=ALL_CODES[args.place]))
        except Exception:  # noqa: BLE001
            continue
        for rid in races.values():
            try:
                html = c.get(PERF + rid)
                r = P.parse_result_page(html, rid)
                order = PD.last_corner_order(html)
            except Exception:  # noqa: BLE001
                continue
            if not r.rows:
                continue
            field = r.field_size
            nR += 1
            laps = PD.parse_laps(html)
            if len(laps) >= 4:
                shis.append(round(laps[-2] - laps[-3], 2))
                fades.append(round(laps[-1] - min(laps[-4:]), 2))
            db = dist_bin(r.distance)
            w = r.rows[0]
            ws = style(w.umaban, order, field)
            win[ws] += 1
            distbin[db][ws] += 1
            back_in = False
            for x in r.rows[:3]:
                st = style(x.umaban, order, field)
                if st == "後":
                    back_in = True
                if x.popularity and x.popularity >= 6:
                    ana[st] += 1
            backbydist[db][1] += 1
            backbydist[db][0] += 1 if back_in else 0

    if not nR:
        raise SystemExit("結果が取得できませんでした(日付/開催を確認)")

    tot = sum(win.values())
    front = win["逃"] + win["先"]
    print(f"\n=== {args.place} プロファイル({len(days)}日 {nR}R) ===")
    print(f"勝ち脚質: 逃{win['逃']} 先{win['先']} 中{win['中']} 後{win['後']} "
          f"→ 前(逃+先) {100*front/tot:.0f}%")
    if shis:
        sustain = S.mean(fades)
        print(f"平均失速幅 {S.mean(shis):+.2f} / 平均ラスト失速 {sustain:+.2f}"
              f" → {'持続戦傾向(瞬発が効きにくい)' if sustain >= 0.8 else '瞬発も可'}")
    print("距離帯別 勝ち脚質(前%):")
    for db, sc in distbin.items():
        t = sum(sc.values())
        print(f"  {db}: 逃{sc['逃']} 先{sc['先']} 中{sc['中']} 後{sc['後']}"
              f"  (前{100*(sc['逃']+sc['先'])/t:.0f}%)")
    print("距離帯別 後方が3着内に来たレース率:")
    for db, (h, t) in backbydist.items():
        print(f"  {db}: {h}/{t} = {100*h/t:.0f}%")
    ta = sum(ana.values())
    if ta:
        print(f"6人気以下で3着内の脚質(穴の正体): 逃{ana['逃']} 先{ana['先']} "
              f"中{ana['中']} 後{ana['後']} → 前(逃+先) {100*(ana['逃']+ana['先'])/ta:.0f}%")

    # prior サマリー(朝の前提)
    front_pct = 100 * front / tot
    prior = "front(前残り)" if front_pct >= 65 else "sashi(差し)" if front_pct <= 40 else "中立"
    print(f"\n★ prior(朝の前提): bias={prior} / "
          f"穴は{'逃げ・先行から(後方は基本消す)' if ta and (ana['逃']+ana['先'])/ta >= 0.6 else '脚質フラット'}")
    print("※買う前に当日4Rを pace_day で実測して上書き(鉄則7)。これはあくまで初期前提。")


if __name__ == "__main__":
    main()
