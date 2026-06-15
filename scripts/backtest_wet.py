"""重馬場の穴特徴量(厩舎の道悪穴率 + ダート巧者血統)の効果を、蓄積データで
リーク無しにバックテストする。

道悪(重/不)レースのみを対象に、ズブ穴ピックを「特徴量OFF / ON」の2通りで
作り、上位ピックの3着内的中率を比較する。道悪穴テーブルは**検証レースの開催日を
除外**して作成し(leave-one-day-out)、自己参照リークを防ぐ。

※ predict_nankan.zubu_ana_picks のスコアを JSONL から再現する(レース自身の勝ち
   時計が蓄積に無いため time_fit は両条件で共通に除外=ON/OFF差分には影響しない)。

実行: python3 scripts/backtest_wet.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nankeiba.core import interval as iv
from nankeiba.core import features as F

FILES = [f"data/samples/nankan_2026-{m}.jsonl" for m in ("02", "03", "04", "05", "06")]
POP_MIN = 6
TOPN = 5


def load_races():
    races = []
    for p in FILES:
        fp = ROOT / p
        if not fp.exists():
            continue
        for line in open(fp, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                races.append(json.loads(line))   # 収集中の部分行はスキップ
            except json.JSONDecodeError:
                continue
    return races


def records_of(h):
    recs = []
    for r in h.get("recent_runs", []):
        if not (r.get("field_size") and r.get("finish_pos")):
            continue
        recs.append(iv.RunRecord(
            date=r.get("date") or "2000-01-01", place=r.get("place") or "?",
            distance=r.get("distance") or 0, field_size=r["field_size"],
            finish_pos=r["finish_pos"], baba=r.get("baba"),
            corner_pos=r.get("corner") or []))
    return recs


def wet_stats(races, exclude_date):
    """道悪×人気薄の厩舎・種牡馬 3着内率(指定日を除外してリーク防止)。"""
    t_s, t_h, s_s, s_h = defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(int)
    tot_s = tot_h = 0
    for r in races:
        if (r.get("baba") or "")[:1] not in ("重", "不"):
            continue
        if r["date"] == exclude_date:
            continue
        for h in r["horses"]:
            fp, pop = h.get("finish_pos"), h.get("exp_pop")
            if fp is None or pop is None or pop < POP_MIN:
                continue
            hit = 1 if fp <= 3 else 0
            tot_s += 1
            tot_h += hit
            if h.get("trainer"):
                t_s[h["trainer"]] += 1
                t_h[h["trainer"]] += hit
            if h.get("sire"):
                s_s[h["sire"]] += 1
                s_h[h["sire"]] += hit
    if tot_s == 0:
        return None
    base = tot_h / tot_s
    tr = {t: (t_h[t] + 12 * base) / (t_s[t] + 12) for t in t_s}
    si = {s: (s_h[s] + 8 * base) / (s_s[s] + 8) for s in s_s}
    return {"base": base, "trainer": tr, "sire": si}


def base_score(h, race, slow_pts):
    """zubu_ana_picks のスコアを JSONL から再現(time_fit を除く共通部分)。"""
    sig = h.get("signals") or {}
    score = 0.0
    sp = slow_pts.get(h["umaban"], 0.0)
    score += sp
    d = sig.get("days_since_last")
    if d is not None and d <= 14:
        score += 1.0
    elif d is not None and 15 <= d <= 20:
        score += 1.5
    elif d is not None and d >= 35:
        score += 1.0
    if sig.get("jockey_changed"):
        score += 0.5            # 簡略化: 強化判定は騎手率テーブル非依存で一律
    if sig.get("place_changed"):
        score += 0.5
    if sig.get("distance_change") is not None and sig["distance_change"] < 0:
        score += 0.5
    recs = records_of(h)
    sen = F.senkou_power(recs)
    if sen >= 0.2:
        score += sen * 2.5
    elif sen <= -0.15:
        score += sen * 1.5
    def slow_for_dist(r):
        if not r.get("distance") or not r.get("agari"):
            return False
        norm = 37.5 + r["distance"] / 1000 * 2.0
        return r["agari"] >= norm + 1.2
    if any(slow_for_dist(r) for r in h.get("recent_runs", [])):
        score += 1.0
    jq = h.get("jockey_top3_rate") or 0.0
    if jq > 0:
        score += jq / 12.0
    return score


def wet_bonus(h, ws):
    b = 0.0
    base = ws["base"]
    tr = ws["trainer"].get(h.get("trainer"))
    if tr and tr / base > 1.05:
        b += min(1.2, (tr / base - 1.0) * 1.5)
    si = ws["sire"].get(h.get("sire"))
    if si and si / base > 1.05:
        b += min(1.2, (si / base - 1.0) * 1.5)
    return b


def picks_for(race, ws=None):
    # レース内 上がり中央値の遅さポイント
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
        sc = base_score(h, race, slow_pts)
        if ws:
            sc += wet_bonus(h, ws)
        if sc > 0:
            scored.append((h, sc))
    scored.sort(key=lambda x: -x[1])
    return scored


def evaluate(races, use_wet):
    n_pick = n_board = n_head = n_head_board = 0
    cache: dict[str, dict] = {}
    for r in races:
        if (r.get("baba") or "")[:1] not in ("重", "不"):
            continue
        top3 = {h["umaban"] for h in r["horses"] if h.get("finish_pos") and h["finish_pos"] <= 3}
        if not top3:
            continue
        ws = None
        if use_wet:
            ws = cache.get(r["date"]) or wet_stats(races, r["date"])
            cache[r["date"]] = ws
        picks = picks_for(r, ws if use_wet else None)[:TOPN]
        if not picks:
            continue
        n_head += 1
        for i, (h, _sc) in enumerate(picks):
            n_pick += 1
            if h["umaban"] in top3:
                n_board += 1
                if i == 0:
                    n_head_board += 1
    return n_pick, n_board, n_head, n_head_board


def main() -> None:
    races = load_races()
    wet = [r for r in races if (r.get("baba") or "")[:1] in ("重", "不")]
    print(f"全{len(races)}R 中 道悪(重/不) {len(wet)}R を対象にバックテスト "
          f"(pop>={POP_MIN}・上位{TOPN}ピック・leave-one-day-out)\n")
    for label, uw in [("OFF(特徴量なし)", False), ("ON(重馬場特徴量)", True)]:
        np_, nb, nh, nhb = evaluate(races, uw)
        print(f"[{label}] ピック{np_}頭中 3着内 {nb}頭 ({100*nb/np_:.1f}%) / "
              f"本線(穴度1位)3着内 {nhb}/{nh} ({100*nhb/nh:.0f}%)")


if __name__ == "__main__":
    main()
