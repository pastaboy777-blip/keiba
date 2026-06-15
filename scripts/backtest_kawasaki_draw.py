"""川崎特有の『内枠の穴』バイアスを検証する。

(a) 安定性: 川崎の人気薄(6人気↓)の3着内率を、馬番(内1-4/中5-8/外9+)別に
    期間前半/後半で比較し、内枠有利・外枠割引が時期をまたいで再現するか確認する。
(b) ON/OFF: ズブ穴ピックに『川崎×内枠=加点 / 外枠=減点』を入れた場合と入れない
    場合で、上位ピックの3着内的中率を比較する(川崎レースのみ)。

ピックのスコアは backtest_wet.py の再現ロジックを流用(time_fit 除外は両条件共通)。

実行: python3 scripts/backtest_kawasaki_draw.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import backtest_wet as bw   # load_races / base_score / records_of などを再利用

POP_MIN = bw.POP_MIN
TOPN = bw.TOPN


def draw_bonus(h, place, w):
    """川崎限定: 内枠(1-4)+w / 外枠(9+)-w / 中枠 0。他場は 0。"""
    if place != "川崎" or w == 0:
        return 0.0
    um = h.get("umaban")
    if not um:
        return 0.0
    if um <= 4:
        return w
    if um >= 9:
        return -w
    return 0.0


def picks_for(race, draw_w=0.0):
    ag = {}
    for h in race["horses"]:
        vals = [r["agari"] for r in h.get("recent_runs", []) if r.get("agari")]
        ag[h["umaban"]] = (sum(vals) / len(vals)) if vals else None
    have = sorted([(u, a) for u, a in ag.items() if a is not None], key=lambda x: -x[1])
    n = len(have)
    slow_pts = {}
    for i, (u, _a) in enumerate(have):
        pct = i / (n - 1) if n > 1 else 0.0
        slow_pts[u] = 2.0 if pct <= 0.3 else (1.0 if pct <= 0.5 else 0.0)
    scored = []
    for h in race["horses"]:
        if h.get("exp_pop") is None or h["exp_pop"] < POP_MIN:
            continue
        sc = bw.base_score(h, race, slow_pts) + draw_bonus(h, race["place"], draw_w)
        if sc > 0:
            scored.append((h, sc))
    scored.sort(key=lambda x: -x[1])
    return scored


def stability(races):
    kw = sorted([r for r in races if r["place"] == "川崎"], key=lambda r: r["date"])
    mid = kw[len(kw) // 2]["date"]
    print(f"=== (a) 内枠バイアスの安定性 (川崎{len(kw)}R, 境={mid}) ===")
    for half, sub in [("前半", [r for r in kw if r["date"] < mid]),
                      ("後半", [r for r in kw if r["date"] >= mid])]:
        ana = [h for r in sub for h in r["horses"]
               if h.get("exp_pop") and h["exp_pop"] >= POP_MIN and h.get("finish_pos")]
        base_n = len(ana)
        base_t = sum(1 for h in ana if h["finish_pos"] <= 3)
        base = 100 * base_t / base_n if base_n else 0
        def seg(lo, hi):
            s = [h for h in ana if h.get("umaban") and lo <= h["umaban"] <= hi]
            t = sum(1 for h in s if h["finish_pos"] <= 3)
            return len(s), (100 * t / len(s) if s else 0)
        ni, pi = seg(1, 4)
        no, po = seg(9, 99)
        print(f"  {half}: ベース{base:.1f}%(n={base_n}) | "
              f"内1-4 {pi:.1f}%(n={ni},{pi/base:.2f}x) | "
              f"外9+ {po:.1f}%(n={no},{po/base:.2f}x)")


def onoff(races):
    kw = [r for r in races if r["place"] == "川崎"]
    print(f"\n=== (b) ON/OFF バックテスト (川崎{len(kw)}R, 上位{TOPN}ピック) ===")
    for w in (0.0, 0.4, 0.6, 0.8):
        n_pick = n_board = n_head = n_hb = 0
        for r in kw:
            top3 = {h["umaban"] for h in r["horses"]
                    if h.get("finish_pos") and h["finish_pos"] <= 3}
            if not top3:
                continue
            picks = picks_for(r, draw_w=w)[:TOPN]
            if not picks:
                continue
            n_head += 1
            for i, (h, _sc) in enumerate(picks):
                n_pick += 1
                if h["umaban"] in top3:
                    n_board += 1
                    if i == 0:
                        n_hb += 1
        tag = "OFF" if w == 0 else f"内枠±{w}"
        print(f"  [{tag}] ピック{n_pick}頭 3着内{n_board} ({100*n_board/n_pick:.1f}%) / "
              f"本線3着内 {n_hb}/{n_head} ({100*n_hb/n_head:.0f}%)")


def main() -> None:
    races = bw.load_races()
    stability(races)
    onoff(races)


if __name__ == "__main__":
    main()
