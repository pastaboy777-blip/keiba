"""川崎 2026-06-15 後半(9R〜12R)の「ズブ穴」を抽出する。

ズブ穴 = ズブい(タフで間隔を詰めて使われ、短間隔でも崩れない)のに
人気が無い妙味馬。南関の「ズブい馬を走らせるゲーム」で市場が軽視しがちな
   ・連闘/中1週など短間隔での好走実績(タフネス)
   ・叩き2〜3走目の上昇
   ・前で運べる脚質(小回り重ダート)
を満たし、かつ人気薄(=配当妙味)の馬を拾う。

実行: python3 scripts/zubuana_kawasaki_0615.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nankeiba.ingest import rakuten
from nankeiba.core import interval as iv
from nankeiba.core import features as ft
from nankeiba.core import probability as pb
from nankeiba.core.features import RaceContext, ScoreWeights, horse_score

CACHE = ROOT / "data" / "cache" / "rakuten"
BASE_ID = "202606152135030100"
RACES = [9, 10, 11, 12]

# ズブ穴の重み(短間隔・タフネス・叩き・先行力を強める)
W = ScoreWeights(interval_fit=1.6, toughness=0.9, tatakii=1.3, senkou=0.8)


def load_page(race_no: int) -> str:
    cached = CACHE / f"kawasaki_2026-06-15_{race_no}R.html"
    if cached.exists():
        return cached.read_text(encoding="utf-8", errors="replace")
    import urllib.request
    rid = rakuten.race_id(BASE_ID, race_no)
    req = urllib.request.Request(rakuten.race_card_url(rid),
                                 headers={"User-Agent": "Mozilla/5.0 (nankeiba)"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(text, encoding="utf-8")
    return text


def _days(a: str, b: str) -> int:
    ya, ma, da = map(int, a.split("-"))
    yb, mb, db = map(int, b.split("-"))
    return (date(ya, ma, da) - date(yb, mb, db)).days


def to_records(runs, jockey):
    recs = []
    for r in runs:
        if not (r.get("date") and r.get("field_size") and r.get("finish_pos")):
            continue
        recs.append(iv.RunRecord(
            date=r["date"], place=r["place"] or "?", distance=r["distance"] or 0,
            field_size=r["field_size"], finish_pos=r["finish_pos"], jockey=jockey,
            baba=r.get("baba"), corner_pos=r.get("corner_pos") or [], agari_rank=None))
    return recs


def analyze(card: dict):
    horses = card["horses"]
    n = len(horses)
    ctx_base = dict(date=card["date"], place=card["place"],
                    distance=card["distance"], field_size=n, baba=card["baba"])
    rows, scores = [], {}
    for h in horses:
        recs = to_records(h["runs"], h["jockey"])
        if not recs:
            scores[h["umaban"]] = -9.9
            continue
        prof = iv.build_profile(recs)
        recs_sorted = list(recs)
        iv._fill_intervals(recs_sorted)
        up = _days(card["date"], recs_sorted[0].date)
        ifit = iv.interval_fit(prof, up)
        ntat = ft.starts_since_layoff(recs_sorted, up)
        sen = ft.senkou_power(recs)
        ctx = RaceContext(jockey=h["jockey"], trainer=h["trainer"], **ctx_base)
        scores[h["umaban"]] = horse_score(recs, ctx, weights=W)
        rows.append(dict(um=h["umaban"], name=h["name"], odds=h["odds"],
                         pop=h["popularity"], up=up, tough=prof.toughness,
                         ifit=ifit, ntat=ntat, sen=sen, starts90=prof.starts_last_90d))
    strengths = pb.strengths_from_scores(scores, temperature=1.0)
    order = sorted(scores, key=lambda u: scores[u], reverse=True)
    model_rank = {u: i + 1 for i, u in enumerate(order)}
    for r in rows:
        r["top3"] = pb.top3_probability(strengths, r["um"])
        r["mrank"] = model_rank[r["um"]]
    return rows, order


def zubu_score(r) -> float:
    """ズブ穴度: タフ・短間隔向き・叩き上昇・前付け を満たし、人気薄ほど高い。"""
    s = 0.0
    s += 1.6 * max(0.0, r["tough"] - 0.5)        # ズブさ/タフネス
    s += 1.4 * max(0.0, r["ifit"])               # 今回間隔へのフィット(短間隔有利)
    s += 0.5 if r["up"] is not None and r["up"] <= 20 else 0.0  # 実際に短間隔
    s += 0.4 if r["ntat"] in (2, 3) else 0.0     # 叩き2〜3走目
    s += 0.5 * max(0.0, r["sen"])                # 前で運べる
    # 人気薄ボーナス(穴であるほど妙味)
    pop = r["pop"] or 18
    s *= 1.0 + 0.12 * max(0, pop - 4)
    return s


def main() -> None:
    print("川崎 2026-06-15 後半(9〜12R)ズブ穴抽出")
    print("基準: タフネス・短間隔フィット・叩き2〜3走目・先行力 × 人気薄\n")
    for rno in RACES:
        card = rakuten.parse_race_card(load_page(rno))
        rows, order = analyze(card)
        print("=" * 70)
        print(f"川崎 {card['race_no']}R {card['race_name']}  "
              f"{card['surface']}{card['distance']}m {card['baba']} 発走{card['post_time']}")
        # ズブ穴候補: 人気薄(5番人気以下 もしくは 単勝12倍以上)
        cand = [r for r in rows
                if (r["pop"] and r["pop"] >= 5) or (r["odds"] and r["odds"] >= 12.0)]
        cand.sort(key=zubu_score, reverse=True)
        print(" ズブ穴 馬 馬名            単勝  人気 間隔 タフ 叩き 先行 3着内 妙味")
        for r in cand[:4]:
            tag = "◎穴" if zubu_score(r) >= 1.2 else ("○穴" if zubu_score(r) >= 0.8 else "△穴")
            odds = f"{r['odds']:>5.1f}" if r["odds"] else "  -  "
            pop = f"{r['pop']:>2d}" if r["pop"] else " ?"
            kyaku = "前" if r["sen"] > 0.1 else ("差" if r["sen"] < -0.1 else "自")
            print(f"  {tag} {r['um']:2d} {r['name']:<13s}{odds} {pop}人 "
                  f"{(str(r['up'])+'日'):>4s} {r['tough']:.2f} {r['ntat']}走 "
                  f" {kyaku}  {r['top3']*100:4.1f}% {zubu_score(r):.2f}")
        # 一番手のズブ穴を本線にした買い目
        if cand:
            ana = cand[0]
            partners = [u for u in order[:6] if u != ana["um"]][:5]
            print(f"  → ズブ穴本線: {ana['um']}{ana['name']}(単{ana['odds']}/{ana['pop']}人) "
                  f"絡めた三連複: 軸{ana['um']} - 相手[{','.join(map(str, partners))}]")
        print()
    print("※短間隔=前走から日数が少ない/タフ=直近よく使われ短間隔で崩れない指数(0.5基準)。")
    print("※人気薄(5人気〜/12倍〜)に絞って妙味順。最終オッズと馬体重・パドックで取捨を。")


if __name__ == "__main__":
    main()
