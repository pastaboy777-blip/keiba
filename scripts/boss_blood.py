#!/usr/bin/env python3
"""【仮説検証】ボス理論 × 血統の相性。
ボス=「同じ相手に何度も勝つ馬」＝安定して力を出せる馬。血統には堅実型とムラ型があるので
 ・ボス×堅実血統 → 序列は本物で繰り返す
 ・ボス×ムラ血統 → 過去の勝ちはたまたま
という交互作用があるはず。父ごとに以下を出す：
 ①★ボス率(その血統がボスになりやすいか) ②父全体のlift ③★ボス時のlift
 ④「ボスであることの上乗せ分」= ③-② ←これが交互作用の本体

使い方: python3 scripts/boss_blood.py --from 2026-01-01 --warmup 2026-03-01 --to 2026-07-24
"""
import sys, argparse, datetime
from collections import defaultdict
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"
TRACKS = ["浦和", "船橋", "大井", "川崎"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--warmup", required=True)
    ap.add_argument("--to", dest="to", required=True)
    ap.add_argument("--usui", type=int, default=6)
    ap.add_argument("--min-boss", type=int, default=20, help="父ごとの★ボス最低サンプル")
    a = ap.parse_args()
    c = PoliteClient()
    d0 = datetime.date.fromisoformat(a.frm); d1 = datetime.date.fromisoformat(a.to)
    warm = datetime.date.fromisoformat(a.warmup)
    beat = defaultdict(int)
    base = [0, 0]
    S = defaultdict(lambda: {"all": [0, 0], "boss": [0, 0], "kobun": [0, 0]})

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
                    rr = P.parse_result_page(c.get(PERF.format(r=rid), use_cache=True), rid)
                except Exception:
                    continue
                rows = [(x.horse_name.strip(), x.finish_pos, x.popularity or 0, x.umaban)
                        for x in rr.rows if x.horse_name and x.finish_pos]
                if len(rows) < 6:
                    continue
                names = [n for n, f, p, u in rows]
                if day >= warm:
                    try:
                        pc = P.parse_card_page(c.get(CARD.format(r=rid), use_cache=True), rid)
                        emap = {e.umaban: e for e in pc.entries if e.umaban}
                    except Exception:
                        emap = {}
                    for name, fin, pop, um in rows:
                        if pop < a.usui:
                            continue
                        e = emap.get(um)
                        if not e or not e.sire:
                            continue
                        sire = e.sire.strip()
                        g = 1 if fin <= 3 else 0
                        base[0] += g; base[1] += 1
                        w = l = 0
                        for o in names:
                            if o == name:
                                continue
                            w += beat[(name, o)]; l += beat[(o, name)]
                        enc = w + l
                        d = S[sire]
                        d["all"][0] += g; d["all"][1] += 1
                        if enc >= 3 and w / enc >= 0.6:
                            d["boss"][0] += g; d["boss"][1] += 1
                        elif enc >= 3 and w / enc <= 0.3:
                            d["kobun"][0] += g; d["kobun"][1] += 1
                for i in range(len(rows)):
                    for j in range(i + 1, len(rows)):
                        n1, f1 = rows[i][0], rows[i][1]; n2, f2 = rows[j][0], rows[j][1]
                        if f1 < f2:
                            beat[(n1, n2)] += 1
                        elif f2 < f1:
                            beat[(n2, n1)] += 1
        day += datetime.timedelta(days=1)

    b = base[0] / base[1] if base[1] else 0
    def r(cc):
        return cc[0] / cc[1] if cc[1] else 0
    print(f"=== ボス理論 × 血統(父) {a.warmup}〜{a.to} 人気薄≥{a.usui} ===")
    print(f" 人気薄n={base[1]} ベース複勝{b:.1%}\n")
    rows_ = []
    for sire, d in S.items():
        if d["boss"][1] < a.min_boss:
            continue
        la = r(d["all"]) / b if b else 0
        lb = r(d["boss"]) / b if b else 0
        lk = (r(d["kobun"]) / b) if (b and d["kobun"][1] >= 10) else None
        rows_.append((lb - la, sire, d, la, lb, lk))
    rows_.sort(reverse=True)
    print(f" {'父':16s} {'全体lift':>9s} {'★ボス時lift':>12s} {'上乗せ':>7s} {'★ボス率':>7s} {'子分lift':>8s}")
    print(" --- ボスであることが効く血統(上乗せ大) ---")
    for diff, sire, d, la, lb, lk in rows_[:10]:
        bp = d["boss"][1] / d["all"][1]
        ks = f"{lk:5.2f}(n{d['kobun'][1]})" if lk is not None else "  -"
        print(f" {sire[:16]:16s} {la:9.2f}(n{d['all'][1]:>4}) {lb:6.2f}(n{d['boss'][1]:>3}) "
              f"{diff:+7.2f} {bp:7.0%} {ks}")
    print("\n --- ボスでも効かない血統(上乗せ小/マイナス) ---")
    for diff, sire, d, la, lb, lk in rows_[-8:]:
        bp = d["boss"][1] / d["all"][1]
        ks = f"{lk:5.2f}(n{d['kobun'][1]})" if lk is not None else "  -"
        print(f" {sire[:16]:16s} {la:9.2f}(n{d['all'][1]:>4}) {lb:6.2f}(n{d['boss'][1]:>3}) "
              f"{diff:+7.2f} {bp:7.0%} {ks}")
    # ★ボス率ランキング(どの血統がボスになりやすいか)
    print("\n --- ★ボス率が高い血統(=同じ相手に勝ち続ける安定型) ---")
    rr_ = [(d["boss"][1] / d["all"][1], s, d) for s, d in S.items() if d["all"][1] >= 60]
    rr_.sort(reverse=True)
    for bp, s, d in rr_[:8]:
        print(f" {s[:16]:16s} ★ボス率{bp:4.0%} (ボスn{d['boss'][1]}/全n{d['all'][1]}) "
              f"ボス時lift{(r(d['boss'])/b if b and d['boss'][1] else 0):4.2f}")
    print("\n --- ★ボス率が低い血統(=ムラ型/対戦歴が薄い) ---")
    for bp, s, d in rr_[-6:]:
        print(f" {s[:16]:16s} ★ボス率{bp:4.0%} (ボスn{d['boss'][1]}/全n{d['all'][1]})")


if __name__ == "__main__":
    main()
