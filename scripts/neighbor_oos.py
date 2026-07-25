#!/usr/bin/env python3
"""隣の馬効果(§25)の期間分割・再現性検証。
ルールベース(学習パラメータ無し)なので、4-6月と7月で同じセルが同じ方向に出るかを見る。
両期で再現すれば本物、片方だけなら偶然。
使い方: python3 scripts/neighbor_oos.py
"""
import sys, datetime
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from neighbor_val import style

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"
TRACKS = ["浦和", "船橋", "大井", "川崎"]
USUI = 6


def period(d0, d1):
    c = PoliteClient()
    base = [0, 0]; C = {}
    def add(k, g):
        cc = C.setdefault(k, [0, 0]); cc[0] += g; cc[1] += 1
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
                    pc = P.parse_card_page(c.get(CARD.format(r=rid), use_cache=True), rid)
                    rr = P.parse_result_page(c.get(PERF.format(r=rid), use_cache=True), rid)
                except Exception:
                    continue
                if not rr.rows or not rr.rows[0].finish_pos:
                    continue
                ent = {e.umaban: e for e in pc.entries if e.umaban}
                if len(ent) < 6:
                    continue
                st = {um: style(e) for um, e in ent.items()}
                n_nige = sum(1 for v in st.values() if v == "逃")
                for row in rr.rows:
                    if not (row.umaban and row.finish_pos and row.popularity):
                        continue
                    if row.popularity < USUI:
                        continue
                    me = st.get(row.umaban, "?")
                    if me == "?":
                        continue
                    g = 1 if row.finish_pos <= 3 else 0
                    base[0] += g; base[1] += 1
                    um = row.umaban
                    nb = [st.get(um - 1), st.get(um + 1)]
                    nb = [x for x in nb if x and x != "?"]
                    if me == "逃":
                        add("逃×隣に逃げ" if any(x == "逃" for x in nb) else "逃×隣に逃げ無", g)
                        add("逃×単騎(同型0)" if n_nige <= 1 else "逃×同型有(2頭+)", g)
                        if st.get(um - 1) == "逃":
                            add("逃×内隣が逃げ", g)
                    # 参考: 差し追いが逃げ隣
                    if me in ("差", "追"):
                        add("差追×隣に逃げ" if any(x == "逃" for x in nb) else "差追×隣に逃げ無", g)
        day += datetime.timedelta(days=1)
    return base, C


def show(label, base, C):
    b = base[0] / base[1] if base[1] else 0
    print(f"\n=== {label} 人気薄n={base[1]} ベース{b:.1%} ===")
    for k in ["逃×内隣が逃げ", "逃×隣に逃げ", "逃×隣に逃げ無", "逃×同型有(2頭+)", "逃×単騎(同型0)",
              "差追×隣に逃げ", "差追×隣に逃げ無"]:
        v = C.get(k)
        if not v or not v[1]:
            print(f" {k:18s} n0"); continue
        r = v[0] / v[1]
        print(f" {k:18s} {r:5.1%}({v[0]:>3}/{v[1]:>4}) lift{(r/b if b else 0):4.2f}")


def main():
    b1, c1 = period(datetime.date(2026, 4, 1), datetime.date(2026, 6, 30))
    show("学習期 4-6月", b1, c1)
    b2, c2 = period(datetime.date(2026, 7, 1), datetime.date(2026, 7, 31))
    show("検証期 7月", b2, c2)
    print("\n=== 再現性判定(両期で同方向か) ===")
    r1 = b1[0] / b1[1]; r2 = b2[0] / b2[1]
    for k in ["逃×内隣が逃げ", "逃×隣に逃げ", "逃×単騎(同型0)", "差追×隣に逃げ"]:
        v1, v2 = c1.get(k), c2.get(k)
        if not (v1 and v1[1] and v2 and v2[1]):
            print(f" {k}: データ不足"); continue
        l1 = (v1[0] / v1[1]) / r1; l2 = (v2[0] / v2[1]) / r2
        same = (l1 > 1 and l2 > 1) or (l1 < 1 and l2 < 1)
        print(f" {k:18s} 4-6月lift{l1:4.2f}(n{v1[1]})  7月lift{l2:4.2f}(n{v2[1]})  {'✓再現' if same else '✗不一致'}")


if __name__ == "__main__":
    main()
