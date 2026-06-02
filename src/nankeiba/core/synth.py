"""南関競馬の合成データ生成。パイプライン検証用。

「ズブい馬を走らせる」構造を真の生成モデルとして埋め込む:
  - 出走間隔(短間隔有利・休み明け割引)が真に結果へ効く
  - 叩き良化(2〜3走目ピーク)が効く
  - 騎手力・厩舎力・競馬場/距離適性が効く
そして「世間(オッズ)」はこれらを十分に織り込まず、直近着順と騎手人気だけで
値付けする(=市場の盲点)。結果として、間隔・叩き・条件替わりを評価するモデルは
過小評価された買い目を拾え、回収率で勝てる——という仕組みを再現する。

注意: これは合成データであり「コードとロジックが正しく機能すること」の検証用。
実際の的中・回収はリアルデータでの検証が必須(README 参照)。

依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from math import exp, log

from . import interval as iv
from .features import ConnStats
from .backtest import Race, Entry

PLACES = ["大井", "川崎", "船橋", "浦和"]
DISTANCES = [1200, 1400, 1500, 1600, 1800]


# --- 真の効果(モデルが推定しようとしている対象)---

def _true_interval_effect(days: int | None) -> float:
    table = {
        "rento": 0.20, "naka1": 0.10, "normal": 0.0,
        "aki": -0.10, "kyumei": -0.25, "long_kyuyo": -0.35, "unknown": 0.0,
    }
    return table[iv.interval_bucket(days)]


def _true_tatakii_effect(n: int) -> float:
    table = {1: -0.20, 2: 0.15, 3: 0.18, 4: 0.05, 5: 0.0}
    return table.get(n, -0.05)


class _Horse:
    def __init__(self, hid: int, rng: random.Random):
        self.id = hid
        self.ability = rng.gauss(0.0, 0.6)
        # 競馬場・距離の個別適性
        self.place_apt = {p: rng.gauss(0.0, 0.15) for p in PLACES}
        self.dist_pref = rng.choice(DISTANCES)
        self.last_date: date | None = None
        # 休み明けからの叩き数(レース毎に更新)
        self.tatakii = 1
        # 公開用の見かけの直近着順強さ(世間が見る指標)の素
        self.recent_form = 0.0


def _trio_odds_from_strengths(strengths: dict[int, float], takeout: float) -> dict:
    from . import probability as pb
    probs = pb.trio_probabilities(strengths)
    out = {}
    for combo, p in probs.items():
        if p <= 0:
            continue
        fair = 1.0 / p
        out[combo] = round(fair * (1.0 - takeout), 1)
    return out


def _trifecta_odds_from_strengths(strengths: dict[int, float], takeout: float) -> dict:
    from . import probability as pb
    probs = pb.trifecta_probabilities(strengths)
    out = {}
    for combo, p in probs.items():
        if p <= 0:
            continue
        fair = 1.0 / p
        out[combo] = round(fair * (1.0 - takeout), 1)
    return out


def generate_season(
    *,
    n_horses: int = 60,
    n_jockeys: int = 12,
    n_trainers: int = 10,
    n_races: int = 500,
    field_size: int = 10,
    takeout: float = 0.25,
    seed: int = 42,
) -> tuple[list[Race], ConnStats, ConnStats]:
    """1シーズン分のレース列と、騎手・厩舎の成績テーブルを返す。"""
    rng = random.Random(seed)

    horses = [_Horse(i, rng) for i in range(n_horses)]
    jockey_names = [f"J{i:02d}" for i in range(n_jockeys)]
    trainer_names = [f"T{i:02d}" for i in range(n_trainers)]
    # 騎手力・厩舎力(真値)。勝率テーブルにも反映。
    jockey_skill = {j: rng.uniform(-0.3, 0.4) for j in jockey_names}
    trainer_skill = {t: rng.uniform(-0.2, 0.3) for t in trainer_names}
    # 世間に見える勝率(skill と相関するが、人気は別途バイアス)
    jockey_rates = {j: max(0.02, 0.10 + jockey_skill[j] * 0.3) for j in jockey_names}
    trainer_rates = {t: max(0.02, 0.10 + trainer_skill[t] * 0.3) for t in trainer_names}

    cur = date(2024, 1, 1)
    races: list[Race] = []

    for r in range(n_races):
        cur = cur + timedelta(days=rng.randint(1, 3))
        field = rng.sample(horses, field_size)
        place = rng.choice(PLACES)
        distance = rng.choice(DISTANCES)
        rid = f"{cur:%Y%m%d}{r:03d}"

        entries: list[Entry] = []
        true_strength: dict[int, float] = {}
        public_strength: dict[int, float] = {}

        for h in field:
            jk = rng.choice(jockey_names)
            tr = rng.choice(trainer_names)
            entries.append(Entry(horse_id=h.id, jockey=jk, trainer=tr))

            days = (cur - h.last_date).days if h.last_date else None
            # 叩き数の更新
            if days is None or days >= 61:
                h.tatakii = 1
            else:
                h.tatakii += 1

            dist_apt = -0.15 * abs(distance - h.dist_pref) / 200.0

            # --- 真の強さ(結果を決める)---
            ts = (
                h.ability
                + _true_interval_effect(days)
                + _true_tatakii_effect(h.tatakii)
                + jockey_skill[jk]
                + trainer_skill[tr]
                + h.place_apt[place]
                + dist_apt
            )
            true_strength[h.id] = ts

            # --- 世間の見かけ強さ(オッズの素): 間隔・叩き・条件替わりを無視 ---
            # 直近着順と騎手人気だけ。市場の盲点を作る。
            ps = h.recent_form + 0.5 * jockey_skill[jk] + rng.gauss(0.0, 0.2)
            public_strength[h.id] = ps

        # --- 着順をサンプリング(Gumbel = Plackett-Luce サンプリング)---
        def gumbel():
            u = rng.random()
            return -log(-log(max(1e-12, u)))

        ranked = sorted(field, key=lambda h: true_strength[h.id] + 0.8 * gumbel(), reverse=True)
        result_order = [h.id for h in ranked]

        # --- オッズ生成(世間の確率 + 控除)---
        ps_exp = {hid: exp(s) for hid, s in public_strength.items()}
        trio_odds = _trio_odds_from_strengths(ps_exp, takeout)
        trifecta_odds = _trifecta_odds_from_strengths(ps_exp, takeout)

        races.append(Race(
            race_id=rid, date=f"{cur:%Y-%m-%d}", place=place, distance=distance,
            field_size=field_size, entries=entries, result_order=result_order,
            trio_odds=trio_odds, trifecta_odds=trifecta_odds,
        ))

        # --- 馬の状態更新(次走のために)---
        pos_of = {hid: i + 1 for i, hid in enumerate(result_order)}
        for h in field:
            h.last_date = cur
            fp = pos_of[h.id]
            strength = (field_size - fp) / (field_size - 1)
            # 直近着順強さ(世間が見る form)を指数移動平均で更新
            h.recent_form = 0.6 * h.recent_form + 0.8 * (strength - 0.5)

    jockeys = ConnStats(rates=jockey_rates, default=0.08)
    trainers = ConnStats(rates=trainer_rates, default=0.08)
    return races, jockeys, trainers
