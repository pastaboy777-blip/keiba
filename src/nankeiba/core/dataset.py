"""収集データ(JSONL)と Race オブジェクトの相互変換、関係者成績の推定。

収集の保存形式(1行=1レースの JSON):
    {
      "race_id": "202444010101",
      "date": "2024-01-01",
      "place": "大井",
      "distance": 1400,
      "field_size": 12,
      "result": [
        {"finish_pos":1,"umaban":5,"horse_id":"2019104123",
         "horse_name":"...","jockey":"...","trainer":"...","popularity":3},
        ...
      ],
      "trio_odds":     {"3-5-8": 42.1, ...},   # 三連複(昇順の馬番キー)
      "trifecta_odds": {"5-3-8": 210.4, ...}   # 三連単(着順の馬番キー)
    }

依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Sequence

from .backtest import Race, Entry
from .features import ConnStats


# ---------------------------------------------------------------------------
# 組み合わせキーの相互変換  "3-5-8" <-> (3,5,8)
# ---------------------------------------------------------------------------

def _combo_to_key(combo: tuple[int, ...]) -> str:
    return "-".join(str(x) for x in combo)


def _key_to_combo(key: str) -> tuple[int, ...]:
    return tuple(int(x) for x in key.split("-"))


# ---------------------------------------------------------------------------
# dict <-> Race
# ---------------------------------------------------------------------------

def race_from_dict(d: dict) -> Race:
    """収集 dict を Race に変換する。"""
    result = sorted(d["result"], key=lambda r: r["finish_pos"])
    entries = [
        Entry(
            horse_id=r["horse_id"],
            umaban=r.get("umaban"),
            jockey=r.get("jockey"),
            trainer=r.get("trainer"),
        )
        for r in result
    ]
    result_order = [r.get("umaban", r["horse_id"]) for r in result]
    trio_odds = {_key_to_combo(k): float(v) for k, v in d.get("trio_odds", {}).items()}
    trifecta_odds = {_key_to_combo(k): float(v) for k, v in d.get("trifecta_odds", {}).items()}
    return Race(
        race_id=d["race_id"], date=d["date"], place=d["place"],
        distance=int(d["distance"]), field_size=int(d.get("field_size", len(entries))),
        entries=entries, result_order=result_order,
        trio_odds=trio_odds, trifecta_odds=trifecta_odds,
    )


def race_to_dict(race: Race) -> dict:
    """Race を収集 dict 形式に変換する(主に保存・テスト用)。"""
    pos_of = {um: i + 1 for i, um in enumerate(race.result_order)}
    result = []
    for e in race.entries:
        result.append({
            "finish_pos": pos_of.get(e.num(), race.field_size),
            "umaban": e.umaban if e.umaban is not None else e.horse_id,
            "horse_id": e.horse_id,
            "jockey": e.jockey,
            "trainer": e.trainer,
        })
    result.sort(key=lambda r: r["finish_pos"])
    return {
        "race_id": race.race_id, "date": race.date, "place": race.place,
        "distance": race.distance, "field_size": race.field_size,
        "result": result,
        "trio_odds": {_combo_to_key(k): v for k, v in race.trio_odds.items()},
        "trifecta_odds": {_combo_to_key(k): v for k, v in race.trifecta_odds.items()},
    }


# ---------------------------------------------------------------------------
# JSONL の入出力
# ---------------------------------------------------------------------------

def load_races(path: str | Path) -> list[Race]:
    races: list[Race] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                races.append(race_from_dict(json.loads(line)))
    return races


def save_races(races: Iterable[Race], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for race in races:
            f.write(json.dumps(race_to_dict(race), ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# 騎手・厩舎の成績(勝率)推定  ※リーク防止のため学習区間のみから作ること
# ---------------------------------------------------------------------------

def derive_conn_stats(
    races: Sequence[Race],
    *,
    pseudo: float = 20.0,
    metric: str = "place",
    place_k: int = 3,
) -> tuple[ConnStats, ConnStats]:
    """レース群から騎手・厩舎の成績率を推定する(騎手=追える力/厩舎=仕上げ手腕の代理)。

    metric:
        "place" (既定) … 好走率(place_k 着以内に入る率)。三連系に直結し、
                          単勝より安定して「追える力/仕上げ手腕」を捉える。
        "win"           … 勝率(1着率)。
    少サンプルの偏りを抑えるため、全体平均へ pseudo 件ぶん縮約する
    (ベイズ的スムージング)。返り値の default は全体率。

    注意: 未来の情報を使わないため、学習区間のレースだけを渡すこと。
    """
    def _success(pos: int | None, field_size: int) -> int:
        if pos is None:
            return 0
        if metric == "win":
            return 1 if pos == 1 else 0
        return 1 if pos <= place_k else 0  # "place": 好走(place_k 着以内)

    def _stats(get_name) -> ConnStats:
        starts: dict[str, int] = {}
        hits: dict[str, int] = {}
        total_starts = 0
        total_hits = 0
        for race in races:
            pos_of = {um: i + 1 for i, um in enumerate(race.result_order)}
            for e in race.entries:
                name = get_name(e)
                if name is None:
                    continue
                s = _success(pos_of.get(e.num()), race.field_size)
                starts[name] = starts.get(name, 0) + 1
                hits[name] = hits.get(name, 0) + s
                total_starts += 1
                total_hits += s
        prior = total_hits / total_starts if total_starts else 0.08
        rates = {
            n: (hits[n] + pseudo * prior) / (starts[n] + pseudo)
            for n in starts
        }
        return ConnStats(rates=rates, default=prior)

    jockeys = _stats(lambda e: e.jockey)
    trainers = _stats(lambda e: e.trainer)
    return jockeys, trainers


def derive_conn_uplift(
    races: Sequence[Race], *, pseudo: float = 20.0
) -> tuple[ConnStats, ConnStats]:
    """騎手・厩舎の「上積み力」を推定する(追える力/仕上げ手腕のより直接的な指標)。

    好走率は「良い馬に乗る/預かる」だけでも上がってしまう。ここでは各出走について
    「その馬のそれまでの平均的な走り(過去走の finish_strength 平均)」を基準に、
    今回それをどれだけ上回ったか(uplift = 今回 − 過去平均)を関係者ごとに平均する。
    正なら「馬を自身の水準より走らせた」= 追える/仕上げが効いた、と読める。
    リーク防止のため基準は過去走のみ。時系列に履歴を積みながら計算する。

    返り値は `ConnStats`(default=0.0、rates[name]=上積み)。
    `horse_features` の jockey_power / trainer 特徴量(= get(name) − default)に
    そのまま上積み値として乗る。学習区間のレースだけを渡すこと。
    """
    history: dict[object, list[float]] = {}  # horse_id -> 過去 finish_strength 列

    j_tot, j_cnt = {}, {}
    t_tot, t_cnt = {}, {}
    for race in sorted(races, key=lambda r: r.date):
        pos_of = {um: i + 1 for i, um in enumerate(race.result_order)}
        for e in race.entries:
            pos = pos_of.get(e.num(), race.field_size)
            fs = (race.field_size - pos) / max(1, race.field_size - 1)
            past = history.get(e.horse_id, [])
            if past:  # 過去走がある馬だけ上積みを測れる
                base = sum(past) / len(past)
                uplift = fs - base
                if e.jockey is not None:
                    j_tot[e.jockey] = j_tot.get(e.jockey, 0.0) + uplift
                    j_cnt[e.jockey] = j_cnt.get(e.jockey, 0) + 1
                if e.trainer is not None:
                    t_tot[e.trainer] = t_tot.get(e.trainer, 0.0) + uplift
                    t_cnt[e.trainer] = t_cnt.get(e.trainer, 0) + 1
            history.setdefault(e.horse_id, []).append(fs)

    def _finalize(tot, cnt) -> ConnStats:
        # 0(=上積みなし)へ pseudo 件縮約
        rates = {
            n: (tot[n] / cnt[n]) * (cnt[n] / (cnt[n] + pseudo))
            for n in tot
        }
        return ConnStats(rates=rates, default=0.0)

    return _finalize(j_tot, j_cnt), _finalize(t_tot, t_cnt)
