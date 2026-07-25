#!/usr/bin/env python3
"""「折り合い→直線脚」仮説の検証(本人着眼)。直線で脚を使えるかは4Cまでの折り合い次第で、
その手がかりは通過順(スタート〜4C)に残る。過去走のコーナー通過順から
 ・溜め型: 序盤後方 かつ 4C時点でもまだ後方〜中団(道中で無理に上げず脚を溜めた=折り合い)
 ・直線脚: 4C→着順で押し上げた(直線で差した)
を検出し、その履歴を持つ人気薄が好走率を上げるか(=直線一気の折り合い型が穴か)を実測。
netkeiba不要(rakutenキャッシュ)。
使い方: python3 scripts/folding_val.py --from 2026-04-01 --to 2026-07-24
"""
import sys, argparse, datetime
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"


def run_flags(pr):
    """1走を (溜め型か, 直線差しか, 直線押上量) に。コーナー<2 or 情報欠落は None。"""
    co = [x for x in (pr.corner or []) if isinstance(x, (int, float))]
    fs = pr.field_size or 12
    f = pr.finish_pos
    if len(co) < 2 or not f or not fs:
        return None
    early, c4 = co[0], co[-1]           # 序盤位置 / 最終コーナー(直線入口)位置
    tame = (early >= fs * 0.5) and (c4 >= fs * 0.4)   # 序盤後方かつ4Cでもまだ溜め(道中我慢=折り合い)
    straight_gain = c4 - f              # 直線で押し上げた数(+ = 差した)
    sashi = straight_gain >= 3
    return tame, sashi, straight_gain


def profile(e, n=5):
    """直近n走から (溜め×直線差し回数, 直線差し回数, 平均直線押上量, 有効走数)。"""
    tame_sashi = sashi = valid = 0
    gains = []
    for pr in (e.recent_runs or [])[:n]:
        r = run_flags(pr)
        if r is None:
            continue
        valid += 1
        t, s, g = r
        gains.append(g)
        if s:
            sashi += 1
        if t and s:
            tame_sashi += 1
    avg_gain = sum(gains) / len(gains) if gains else 0
    return tame_sashi, sashi, avg_gain, valid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", dest="to", required=True)
    ap.add_argument("--usui", type=int, default=6)
    ap.add_argument("--tracks", default="浦和,船橋,大井,川崎")
    a = ap.parse_args()
    c = PoliteClient()
    tracks = a.tracks.split(",")
    d0 = datetime.date.fromisoformat(a.frm); d1 = datetime.date.fromisoformat(a.to)
    base = [0, 0]
    B = {k: [0, 0] for k in [
        "溜め×直線差し1+", "溜め×直線差し2+", "直線差し1+(溜め問わず)",
        "平均押上>=2", "折り合い型無し(該当0)"]}
    day = d0
    while day <= d1:
        ymd = day.strftime("%Y%m%d")
        for tr in tracks:
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
                emap = {e.umaban: e for e in pc.entries if e.umaban}
                for row in rr.rows:
                    if not (row.umaban and row.finish_pos and row.popularity):
                        continue
                    if row.popularity < a.usui:
                        continue
                    e = emap.get(row.umaban)
                    if not e:
                        continue
                    ts, s, ag, valid = profile(e)
                    if valid < 2:
                        continue
                    g = 1 if row.finish_pos <= 3 else 0
                    base[0] += g; base[1] += 1
                    if ts >= 1:
                        B["溜め×直線差し1+"][0] += g; B["溜め×直線差し1+"][1] += 1
                    if ts >= 2:
                        B["溜め×直線差し2+"][0] += g; B["溜め×直線差し2+"][1] += 1
                    if s >= 1:
                        B["直線差し1+(溜め問わず)"][0] += g; B["直線差し1+(溜め問わず)"][1] += 1
                    if ag >= 2:
                        B["平均押上>=2"][0] += g; B["平均押上>=2"][1] += 1
                    if ts == 0:
                        B["折り合い型無し(該当0)"][0] += g; B["折り合い型無し(該当0)"][1] += 1
        day += datetime.timedelta(days=1)
    b = base[0] / base[1] if base[1] else 0
    print(f"=== 折り合い→直線脚 検証 {a.frm}〜{a.to} ({a.tracks}) 人気薄≥{a.usui} 複勝率 ===")
    print(f" [ベース] {b:.1%}({base[0]}/{base[1]}) / 有効走2+のみ")
    for k, cc in B.items():
        if not cc[1]:
            print(f" {k:22s} n0"); continue
        r = cc[0] / cc[1]
        print(f" {k:22s} {r:5.1%}({cc[0]:>3}/{cc[1]:>4}) lift{(r/b if b else 0):4.2f}")


if __name__ == "__main__":
    main()
