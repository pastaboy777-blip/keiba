"""核心ロジックの単体テスト(標準ライブラリ unittest のみ)。

実行: python3 -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.core import interval as iv
from nankeiba.core import probability as pb
from nankeiba.core import betting as bt
from nankeiba.core import synth
from nankeiba.core.backtest import run_backtest
from nankeiba.core.features import (
    RaceContext, ConnStats, ScoreWeights, FEATURE_NAMES,
    horse_score, horse_features, starts_since_layoff,
)
from nankeiba.core import learn as L
from math import isfinite


class TestInterval(unittest.TestCase):
    def test_buckets(self):
        self.assertEqual(iv.interval_bucket(7), "rento")
        self.assertEqual(iv.interval_bucket(15), "naka1")
        self.assertEqual(iv.interval_bucket(30), "normal")
        self.assertEqual(iv.interval_bucket(200), "long_kyuyo")
        self.assertEqual(iv.interval_bucket(None), "unknown")

    def test_prior_short_better(self):
        # 南関は短間隔ほど有利
        self.assertGreater(iv.global_interval_prior(7), iv.global_interval_prior(90))

    def test_profile_fills_intervals(self):
        runs = [
            iv.RunRecord("2024-03-01", "大井", 1400, 12, 1),
            iv.RunRecord("2024-02-20", "大井", 1400, 12, 3),
            iv.RunRecord("2024-02-10", "川崎", 1400, 12, 5),
        ]
        prof = iv.build_profile(runs)
        self.assertEqual(prof.n_runs, 3)
        self.assertGreater(prof.ability, 0.0)


class TestTatakii(unittest.TestCase):
    def test_layoff_is_first(self):
        runs = [iv.RunRecord("2024-01-01", "大井", 1400, 12, 5)]
        # 休み明け(間隔なし)→ 叩き1走目
        self.assertEqual(starts_since_layoff(runs, None), 1)

    def test_counts_after_layoff(self):
        runs = [
            iv.RunRecord("2024-03-01", "大井", 1400, 12, 2),  # 直近(間隔12日)
            iv.RunRecord("2024-02-18", "大井", 1400, 12, 4),  # 休み明け(90日)
        ]
        runs[0].days_since_last = 12
        runs[1].days_since_last = 90
        # 今回も12日 → 休み明けから数えて3走目
        self.assertEqual(starts_since_layoff(runs, 12), 3)


class TestProbability(unittest.TestCase):
    def test_trifecta_sums_to_one(self):
        s = {1: 3.0, 2: 2.0, 3: 1.0, 4: 0.5}
        probs = pb.trifecta_probabilities(s)
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=6)

    def test_trio_sums_to_one(self):
        s = {1: 3.0, 2: 2.0, 3: 1.0, 4: 0.5}
        probs = pb.trio_probabilities(s)
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=6)

    def test_stronger_horse_more_likely(self):
        s = {1: 5.0, 2: 1.0, 3: 1.0, 4: 1.0}
        self.assertGreater(pb.top3_probability(s, 1), pb.top3_probability(s, 2))


class TestBetting(unittest.TestCase):
    def test_only_positive_ev_selected(self):
        probs = {(1, 2, 3): 0.10, (1, 2, 4): 0.05}
        odds = {(1, 2, 3): 15.0, (1, 2, 4): 5.0}  # EV: 1.5, 0.25
        bets = bt.select_ev_bets(probs, odds, ev_threshold=1.1)
        self.assertEqual(len(bets), 1)
        self.assertEqual(bets[0].combo, (1, 2, 3))

    def test_settle_hit(self):
        bets = bt.select_ev_bets({(1, 2, 3): 0.2}, {(1, 2, 3): 10.0}, ev_threshold=1.0)
        spent, ret = bt.settle(bets, (1, 2, 3))
        self.assertEqual(spent, 100.0)
        self.assertEqual(ret, 1000.0)


class TestBacktestSmoke(unittest.TestCase):
    def test_runs_and_produces_sane_output(self):
        # 合成データ上のエッジは小さく乱数に敏感(実データ検証が必須)。
        # ここではパイプラインが健全に動き、妥当な範囲の数値を返すことだけ確認する。
        races, jockeys, trainers = synth.generate_season(n_races=300, seed=1)
        res = run_backtest(races, jockeys=jockeys, trainers=trainers,
                           bet_type="trio", ev_threshold=1.3, min_history=4)
        self.assertEqual(res.n_races, 300)
        self.assertGreater(res.spent, 0)
        self.assertGreater(res.n_bet_races, 0)
        self.assertTrue(0.2 < res.roi < 5.0, f"ROI out of sane range: {res.roi}")


class TestFeatures(unittest.TestCase):
    def test_feature_keys_match_names(self):
        runs = [iv.RunRecord("2024-02-20", "大井", 1400, 12, 3)]
        ctx = RaceContext("2024-03-01", "大井", 1400, 12, jockey="J01")
        feats = horse_features(runs, ctx)
        self.assertEqual(set(feats), set(FEATURE_NAMES))

    def test_score_is_weighted_dot(self):
        runs = [iv.RunRecord("2024-02-20", "大井", 1400, 12, 3)]
        ctx = RaceContext("2024-03-01", "大井", 1400, 12, jockey="J01")
        feats = horse_features(runs, ctx)
        w = ScoreWeights()
        expected = sum(w.as_dict()[f] * feats[f] for f in FEATURE_NAMES)
        self.assertAlmostEqual(horse_score(runs, ctx, weights=w), expected, places=9)


class TestLearn(unittest.TestCase):
    def test_train_scorer_runs(self):
        races, jockeys, trainers = synth.generate_season(n_races=300, seed=3)
        scorer = L.train_scorer(races, jockeys=jockeys, trainers=trainers,
                                epochs=10, lr=0.2, min_history=4, seed=0)
        # 重みは有限で、全特徴量ぶんある
        self.assertEqual(set(scorer.weights), set(FEATURE_NAMES))
        self.assertTrue(all(isfinite(v) for v in scorer.weights.values()))
        # スコアラーは実数を返す
        ctx = RaceContext("2024-06-01", "大井", 1400, 10, jockey="J01")
        s = scorer([iv.RunRecord("2024-05-20", "大井", 1400, 10, 2)], ctx)
        self.assertTrue(isfinite(s))
        # importances は降順
        imps = [abs(v) for _, v in scorer.importances()]
        self.assertEqual(imps, sorted(imps, reverse=True))

    def test_backtest_accepts_score_fn(self):
        races, jockeys, trainers = synth.generate_season(n_races=300, seed=4)
        scorer = L.train_scorer(races, jockeys=jockeys, trainers=trainers,
                                epochs=10, min_history=4, seed=0)
        res = run_backtest(races, jockeys=jockeys, trainers=trainers,
                           score_fn=scorer, bet_type="trio", min_history=4)
        self.assertGreater(res.spent, 0)


if __name__ == "__main__":
    unittest.main()
