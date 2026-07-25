#!/usr/bin/env python3
"""血統×ラップ形適性の out-of-sample 検証。
学習(4-6月)で父を「緩得意(緩複勝−締複勝>=+th)/締向き(<=-th)」に分類し、
7月ホールドアウトで その群が予想通りの形で走ったか(緩得意群は緩レースで、締向き群は締レースで
複勝率を上げたか)をグループ集計で検証。個別父でなく群でノイズを潰す。
使い方: python3 scripts/blood_lap_oos.py
"""
import sys, datetime
from collections import defaultdict
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
import pace_day as PD
from blood_lap import race_shape

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"
TRACKS = ["浦和", "船橋", "大井", "川崎"]
TH = 0.08       # 緩得意/締向きの判定しきい(緩複勝−締複勝)
MIN_SIDE = 12   # 学習時 各形で最低この走数(小n父の誤分類を排除)


def scan(d0, d1):
    """期間の各出走を [(父, 形, good, 人気)] に。"""
    c = PoliteClient()
    out = []
    day = d0
    while day <= d1:
        ymd = day.strftime("%Y%m%d")
        for tr in TRACKS:
            try:
                idx = c.get(CARD.format(r=day_index_race_id(ymd, tr)), use_cache=True)
                races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[tr]))
            except Exception:
                races = {}
            for R, rid in sorted(races.items()):
                try:
                    _ch = c.get(CARD.format(r=rid), use_cache=True)
                    pc = P.parse_card_page(_ch, rid)
                    html = c.get(PERF.format(r=rid), use_cache=True)
                    rr = P.parse_result_page(html, rid)
                except Exception:
                    continue
                if not rr.rows or not rr.rows[0].finish_pos:
                    continue
                shape = race_shape(PD.parse_laps(html))
                if shape is None:
                    continue
                emap = {e.umaban: e for e in pc.entries if e.umaban}
                for row in rr.rows:
                    if not (row.umaban and row.finish_pos):
                        continue
                    e = emap.get(row.umaban)
                    if not e or not e.sire:
                        continue
                    g = 1 if row.finish_pos <= 3 else 0
                    out.append((e.sire.strip(), shape, g, row.popularity or 99))
        day += datetime.timedelta(days=1)
    return out


def learn(rows):
    """父->class('緩得意'/'締向き'/None)。"""
    sire = defaultdict(lambda: {"緩": [0, 0], "締": [0, 0]})
    for s, shape, g, pop in rows:
        sire[s][shape][0] += g; sire[s][shape][1] += 1
    cls = {}
    for s, d in sire.items():
        nq, nt = d["緩"][1], d["締"][1]
        if nq < MIN_SIDE or nt < MIN_SIDE:
            continue
        diff = d["緩"][0] / nq - d["締"][0] / nt
        if diff >= TH:
            cls[s] = "緩得意"
        elif diff <= -TH:
            cls[s] = "締向き"
    return cls


def rate(cell):
    return cell[0] / cell[1] if cell[1] else 0


def main():
    L = scan(datetime.date(2026, 4, 1), datetime.date(2026, 6, 30))
    cls = learn(L)
    warm = sorted([s for s, c in cls.items() if c == "緩得意"])
    tight = sorted([s for s, c in cls.items() if c == "締向き"])
    print(f"=== 学習(4-6月) 緩得意{len(warm)}血 / 締向き{len(tight)}血 (両形n>={MIN_SIDE},|差|>={TH:.0%}) ===")
    print(" 緩得意:", "・".join(warm))
    print(" 締向き:", "・".join(tight))

    T = scan(datetime.date(2026, 7, 1), datetime.date(2026, 7, 31))
    # 7月ホールドアウトで群別・形別 複勝率
    base = {"緩": [0, 0], "締": [0, 0]}
    G = {"緩得意": {"緩": [0, 0], "締": [0, 0]}, "締向き": {"緩": [0, 0], "締": [0, 0]}}
    Gu = {"緩得意": {"緩": [0, 0], "締": [0, 0]}, "締向き": {"緩": [0, 0], "締": [0, 0]}}  # 人気薄
    for s, shape, g, pop in T:
        base[shape][0] += g; base[shape][1] += 1
        c = cls.get(s)
        if c:
            G[c][shape][0] += g; G[c][shape][1] += 1
            if pop >= 6:
                Gu[c][shape][0] += g; Gu[c][shape][1] += 1
    print(f"\n=== 7月ホールドアウト検証 ===")
    print(f" 7月ベース複勝: 緩{rate(base['緩']):.1%}({base['緩'][1]}) 締{rate(base['締']):.1%}({base['締'][1]})")
    print(f"\n {'群':8s} {'緩レース':>16s} {'締レース':>16s} {'緩-締':>7s} 予想")
    for c, pred in [("緩得意", "緩>締"), ("締向き", "締>緩")]:
        q, t = G[c]["緩"], G[c]["締"]
        diff = rate(q) - rate(t)
        ok = "✓" if ((c == "緩得意" and diff > 0) or (c == "締向き" and diff < 0)) else "✗"
        print(f" {c:8s} {rate(q):5.1%}({q[0]:>2}/{q[1]:>3}) {rate(t):5.1%}({t[0]:>2}/{t[1]:>3}) {diff:+6.1%} {pred} {ok}")
    print(f"\n [人気薄≥6限定]")
    for c, pred in [("緩得意", "緩>締"), ("締向き", "締>緩")]:
        q, t = Gu[c]["緩"], Gu[c]["締"]
        diff = rate(q) - rate(t)
        ok = "✓" if ((c == "緩得意" and diff > 0) or (c == "締向き" and diff < 0)) else "✗"
        print(f" {c:8s} {rate(q):5.1%}({q[0]:>2}/{q[1]:>3}) {rate(t):5.1%}({t[0]:>2}/{t[1]:>3}) {diff:+6.1%} {pred} {ok}")


if __name__ == "__main__":
    main()
