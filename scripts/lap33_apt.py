"""33ラップ適性 予想モード: 出走各馬の33ラップ適性を出し、コースの質と合うか見る。

各馬の適性 = 過去走(出馬表の近走)のうち好走(3着内)時の33ラップ平均
            (好走が無ければ近走全体の平均)。+ =瞬発型 / − =持久型。
--course-val を渡すと、コースの平均33ラップとのマッチ度(小=合致)で並べ替える。

実行例:
    python3 scripts/lap33_apt.py --race-id 202602010611 --course-val 0.25   # 函館記念(函館芝2000)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from nankeiba.scraping import netkeiba as N
import nk_zubu
import lap33_match as LM


def main():
    ap = argparse.ArgumentParser(description="33ラップ適性 予想")
    ap.add_argument("--race-id", required=True)
    ap.add_argument("--course-val", type=float, default=None, help="コース平均33ラップ")
    ap.add_argument("--max-past", type=int, default=5)
    args = ap.parse_args()

    client = N.make_client(use_cache=True)
    rid = args.race_id
    past_html = client.get(nk_zubu.PAST_URL.format(race_id=rid))
    horses = nk_zubu.parse_past_table(past_html)            # umaban,horse,jockey,senkou
    past_map = LM.past_races_by_umaban(past_html)           # umaban -> [(past_rid,fin)]
    cache = {}

    def g33(prid):
        if prid not in cache:
            cache[prid] = LM.race33_of(client, prid)
        return cache[prid]

    rows = []
    for h in horses:
        um = h["umaban"]
        good, allp = [], []
        for prid, pfin in (past_map.get(um) or [])[:args.max_past]:
            v = g33(prid)
            if v is None:
                continue
            allp.append(v)
            if pfin and pfin <= 3:
                good.append(v)
        base = good or allp
        if not base:
            apt = None
        else:
            apt = sum(base) / len(base)
        rows.append({"um": um, "horse": h["horse"], "jockey": h["jockey"],
                     "apt": apt, "n_good": len(good), "n": len(allp)})

    cv = args.course_val
    print(f"\n=== {N.place_of(rid)} 33ラップ適性 / コース平均33ラップ "
          f"{'%+.2f' % cv if cv is not None else '(未指定)'} ===")
    if cv is not None:
        rows = sorted([r for r in rows if r["apt"] is not None],
                      key=lambda r: abs(r["apt"] - cv)) + [r for r in rows if r["apt"] is None]
    print(f"{'馬番':>4} {'馬名':<13}{'騎手':<5}{'適性':>7}{'型':>8}{'マッチ':>7}{'好走/近走':>9}")
    for r in rows:
        if r["apt"] is None:
            print(f"{r['um']:>4} {r['horse'][:12]:<13}{r['jockey'][:4]:<5}{'—':>7}")
            continue
        typ = "瞬発" if r["apt"] >= 1.0 else "持久" if r["apt"] <= -1.0 else "中間"
        match = f"{abs(r['apt']-cv):.1f}" if cv is not None else "—"
        fit = "◎" if cv is not None and abs(r["apt"]-cv) <= 1.0 else ""
        ng = f"{r['n_good']}/{r['n']}"
        print(f"{r['um']:>4} {r['horse'][:12]:<13}{r['jockey'][:4]:<5}"
              f"{r['apt']:>+7.1f}{typ:>8}{match:>7}{ng:>9} {fit}")
    print("\n※適性=過去好走時の33ラップ平均。コース値に近い馬ほど質が合う(◎=差1.0以内)。"
          "\n※33ラップ適性マッチの的中寄与は未バックテスト。理論ベースの参考。")


if __name__ == "__main__":
    main()
