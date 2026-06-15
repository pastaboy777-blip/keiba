"""川崎 2026-06-15 6R/7R/8R を既存パイプラインで予想する。

データソース: 楽天競馬の出馬表ページ(前5走の馬柱つき)。
  - data/cache/rakuten/ に保存済みHTMLがあればそれを使う(再現用・オフライン可)。
  - 無ければ keiba.rakuten.co.jp から取得する(要ネットワーク)。

評価ロジックは src/nankeiba/core をそのまま流用:
  脚質(先行力)・末脚・出走間隔/タフネス・叩き良化・馬場/距離/競馬場適性
  → 合算スコア → Plackett-Luce で3着内確率/三連複確率 → 印・買い目。

正直な前提:
  - 騎手/厩舎の勝率テーブルが無いため関連特徴量はニュートラル。
  - 上がり3F「順位」は楽天ページに無いので末脚特徴はニュートラル(タイムは保持)。
  - 三連複/三連単オッズは静的取得できないため、EV判定の代わりに
    「モデル評価 vs 人気(単勝オッズ)」の乖離で妙味(市場の歪み)を示す。
  - 重みは未学習。既定重みと「南関=短間隔重視」の方針重みの2通りで確認する。

実行: python3 scripts/predict_kawasaki_0615.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nankeiba.ingest import rakuten
from nankeiba.core.interval import RunRecord
from nankeiba.core.features import RaceContext, ScoreWeights, horse_score, horse_features
from nankeiba.core import probability as pb

CACHE = ROOT / "data" / "cache" / "rakuten"
BASE_ID = "202606152135030100"   # 川崎 2026-06-15(一覧の基準RACEID)
RACES = [6, 7, 8]
MARKS = ["◎", "○", "▲", "△", "△", "☆"]


def load_page(race_no: int) -> str:
    """保存済みHTML優先、無ければ楽天から取得する。"""
    cached = CACHE / f"kawasaki_2026-06-15_{race_no}R.html"
    if cached.exists():
        return cached.read_text(encoding="utf-8", errors="replace")
    import urllib.request
    rid = rakuten.race_id(BASE_ID, race_no)
    req = urllib.request.Request(
        rakuten.race_card_url(rid),
        headers={"User-Agent": "Mozilla/5.0 (nankeiba research)"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read()
    CACHE.mkdir(parents=True, exist_ok=True)
    text = raw.decode("utf-8", errors="replace")
    cached.write_text(text, encoding="utf-8")
    return text


def to_records(runs: list[dict], jockey: str | None) -> list[RunRecord]:
    recs = []
    for r in runs:
        if not (r.get("date") and r.get("field_size") and r.get("finish_pos")):
            continue
        recs.append(RunRecord(
            date=r["date"], place=r["place"] or "?", distance=r["distance"] or 0,
            field_size=r["field_size"], finish_pos=r["finish_pos"], jockey=jockey,
            baba=r.get("baba"), corner_pos=r.get("corner_pos") or [],
            agari_rank=None,  # 楽天は上がり順位を持たない(タイムのみ)
        ))
    return recs


def rank(card: dict, weights: ScoreWeights):
    ctx_base = dict(date=card["date"], place=card["place"], distance=card["distance"],
                    field_size=len(card["horses"]), baba=card["baba"])
    scores, recs_by = {}, {}
    for h in card["horses"]:
        recs = to_records(h["runs"], h["jockey"])
        recs_by[h["umaban"]] = recs
        if not recs:
            scores[h["umaban"]] = -9.9
            continue
        ctx = RaceContext(jockey=h["jockey"], trainer=h["trainer"], **ctx_base)
        scores[h["umaban"]] = horse_score(recs, ctx, weights=weights)
    strengths = pb.strengths_from_scores(scores, temperature=1.0)
    order = sorted(scores, key=lambda u: scores[u], reverse=True)
    return order, strengths, scores


def show(card: dict):
    horses = {h["umaban"]: h for h in card["horses"]}
    print("\n" + "=" * 72)
    print(f"川崎 {card['race_no']}R  {card['race_name']}")
    print(f"  {card['surface']}{card['distance']}m {card['baba']}(天候{card['weather']}) "
          f"発走{card['post_time']}  {len(card['horses'])}頭")

    # 南関=短間隔重視の方針重み(predict_example と同じ思想)
    w = ScoreWeights(interval_fit=1.4, toughness=0.6, tatakii=1.2, senkou=0.7)
    order, strengths, scores = rank(card, w)
    top3p = {u: pb.top3_probability(strengths, u) for u in order}

    print("\n  印 馬 馬名             単勝   人気  3着内率  脚質")
    pop_order = sorted(horses, key=lambda u: (horses[u]["popularity"] or 99))
    for i, u in enumerate(order):
        h = horses[u]
        mark = MARKS[i] if i < len(MARKS) else " "
        feats = None
        recs = to_records(h["runs"], h["jockey"])
        if recs:
            from nankeiba.core import features as ft
            sen = ft.senkou_power(recs)
            kyaku = "逃先" if sen > 0.12 else ("差追" if sen < -0.12 else "自在")
        else:
            kyaku = "—"
        odds = f"{h['odds']:>5.1f}" if h["odds"] else "  —  "
        pop = f"{h['popularity']:>2d}" if h["popularity"] else " ?"
        print(f"  {mark} {u:2d} {h['name']:<14s} {odds} {pop}人  "
              f"{top3p[u]*100:5.1f}%   {kyaku}")

    # 市場との乖離(妙味): モデル上位なのに人気薄/モデル下位なのに人気
    print("\n  ◆ 市場との乖離(妙味の芽):")
    pop_rank = {u: r for r, u in enumerate(pop_order, 1)}
    for u in order[:6]:
        mr = order.index(u) + 1
        pr = pop_rank[u]
        if pr - mr >= 3:  # 人気より大きく上に評価
            print(f"    ▲妙味 {u:2d}{horses[u]['name']}: モデル{mr}位 ⇄ {pr}番人気(過小評価)")
    for u in pop_order[:4]:
        mr = order.index(u) + 1
        pr = pop_rank[u]
        if mr - pr >= 3:  # 人気だがモデルは低評価
            print(f"    ×危険 {u:2d}{horses[u]['name']}: {pr}番人気 ⇄ モデル{mr}位(過大評価)")

    # 買い目フォーメーション(◎○▲ 軸、相手は上位)
    axis = order[:3]
    partners = order[:6]
    print("\n  ◆ 推奨買い目(モデル確率ベース):")
    print(f"    三連複フォーメーション: "
          f"軸 {'-'.join(map(str, axis))} 流し → 相手 {','.join(map(str, partners))}")
    trio = pb.trio_probabilities(strengths)
    best = sorted(trio.items(), key=lambda kv: kv[1], reverse=True)[:8]
    print("    三連複 確率上位8点:")
    for combo, p in best:
        print(f"      {combo[0]:>2d}-{combo[1]:>2d}-{combo[2]:>2d}   {p*100:5.2f}%")
    tri = pb.trifecta_probabilities(strengths)
    best_t = sorted(tri.items(), key=lambda kv: kv[1], reverse=True)[:5]
    print("    三連単 確率上位5点:")
    for combo, p in best_t:
        print(f"      {combo[0]:>2d}→{combo[1]:>2d}→{combo[2]:>2d}  {p*100:5.2f}%")


def main() -> None:
    print("川崎競馬 2026-06-15  6R / 7R / 8R 予想(楽天競馬データ + nankeiba パイプライン)")
    for rno in RACES:
        page = load_page(rno)
        card = rakuten.parse_race_card(page)
        show(card)
    print("\n※オッズは取得時点。最終オッズ・馬場・パドックで微調整のこと。")
    print("※三連複/三連単の実オッズは静的取得不可のため期待値判定は別途要確認。")


if __name__ == "__main__":
    main()
