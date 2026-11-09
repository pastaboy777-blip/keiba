"""中央競馬(JRA)対応 と 展開予想(core/tenkai.py)の単体テスト。

実行: python3 -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.core import interval as iv
from nankeiba.core import course as cs
from nankeiba.core import tenkai as tk
from nankeiba.core import dataset as ds
from nankeiba.core.backtest import Race, Entry, race_contexts, record_result
from nankeiba.core.features import RaceContext, horse_features, surface_fit
from nankeiba.scraping import race_id as rid
from nankeiba.scraping.odds import odds_api_url
from nankeiba.scraping.urls import result_url


def _runs(early_positions, *, fs=16, place="東京", surface="芝"):
    """通過順だけ指定した過去走(新しい順)。"""
    return [
        iv.RunRecord(f"2026-{10 - i:02d}-01", place, 1600, fs, 5,
                     surface=surface, corner_pos=[p, p])
        for i, p in enumerate(early_positions)
    ]


class TestCourse(unittest.TestCase):
    def test_org(self):
        self.assertTrue(cs.is_jra("東京"))
        self.assertFalse(cs.is_jra("大井"))
        self.assertEqual(len(cs.JRA_PLACES), 10)

    def test_front_bias_by_straight(self):
        # 直線が短いほど前有利
        self.assertGreater(cs.front_bias("中山", "芝"), cs.front_bias("東京", "芝"))
        self.assertGreater(cs.front_bias("浦和"), cs.front_bias("大井"))
        # 新潟は外回り(659m)と内回り(359m)で大きく違う
        self.assertLess(cs.front_bias("新潟", "芝"), cs.front_bias("新潟", "芝", inner=True))
        self.assertEqual(cs.front_bias("不明場"), 0.0)


class TestStyle(unittest.TestCase):
    def test_style_classification(self):
        self.assertEqual(tk.style_profile(_runs([1, 1, 1])).style, "逃げ")
        self.assertEqual(tk.style_profile(_runs([4, 4, 5])).style, "先行")
        self.assertEqual(tk.style_profile(_runs([16, 15, 16])).style, "追込")
        self.assertEqual(tk.style_profile([]).style, "不明")

    def test_nige_rate(self):
        self.assertAlmostEqual(tk.style_profile(_runs([1, 1])).nige_rate, 1.0)
        self.assertAlmostEqual(tk.style_profile(_runs([3, 3])).nige_rate, 0.0)


class TestPaceForecast(unittest.TestCase):
    def test_many_leaders_means_faster_pace(self):
        base = {i: _runs([10 + i, 10 + i]) for i in range(1, 7)}
        lone = dict(base, L1=_runs([1, 1, 1]))
        crowded = dict(base, L1=_runs([1, 1, 1]), L2=_runs([1, 1, 2]), L3=_runs([1, 2, 1]))
        f1 = tk.forecast(lone, place="東京", distance=1600, surface="芝")
        f3 = tk.forecast(crowded, place="東京", distance=1600, surface="芝")
        self.assertGreater(f3.pace_index, f1.pace_index)
        self.assertEqual(f1.lone_leader, "L1")
        self.assertIsNone(f3.lone_leader)
        self.assertEqual(f1.order[0], "L1")

    def test_lone_leader_gets_advantage(self):
        field = {i: _runs([8 + i, 8 + i]) for i in range(1, 7)}
        field["L"] = _runs([1, 1, 1])
        fc = tk.forecast(field, place="中山", distance=2000, surface="芝")
        self.assertEqual(fc.lone_leader, "L")
        self.assertEqual(max(fc.advantage, key=fc.advantage.get), "L")

    def test_high_pace_long_straight_favors_closers(self):
        field = {f"F{i}": _runs([1, 1, 2]) for i in range(4)}  # 逃げ馬だらけ
        field["C"] = _runs([16, 16, 15])                        # 追込
        fc = tk.forecast(field, place="東京", distance=1400, surface="芝")
        self.assertEqual(fc.pace, "ハイ")
        self.assertGreater(fc.advantage["C"], 0)
        self.assertLess(fc.advantage["F0"], 0)

    def test_no_data_is_neutral(self):
        field = {1: [], 2: [], 3: []}
        fc = tk.forecast(field, place="東京", distance=1600, surface="芝")
        self.assertTrue(all(v == 0.0 for v in fc.advantage.values()))


class TestJraFeatures(unittest.TestCase):
    def test_surface_fit(self):
        runs = [
            iv.RunRecord("2026-10-01", "東京", 1600, 16, 1, surface="ダ"),
            iv.RunRecord("2026-09-01", "中山", 1600, 16, 14, surface="芝"),
        ]
        dirt = RaceContext("2026-11-01", "東京", 1600, 16, surface="ダ")
        turf = RaceContext("2026-11-01", "東京", 1600, 16, surface="芝")
        self.assertGreater(surface_fit(runs, dirt, 0.5), 0)
        self.assertLess(surface_fit(runs, turf, 0.5), 0)

    def test_jra_interval_prior_applied(self):
        # 連闘(7日): 南関はプラス、中央はマイナス評価
        runs = [iv.RunRecord("2026-10-25", "東京", 1600, 16, 5)]
        nar = horse_features(runs, RaceContext("2026-11-01", "大井", 1600, 16))
        jra = horse_features(runs, RaceContext("2026-11-01", "東京", 1600, 16))
        self.assertGreater(nar["interval_fit"], 0)
        self.assertLess(jra["interval_fit"], 0)

    def test_tenkai_feature_passthrough(self):
        ctx = RaceContext("2026-11-01", "東京", 1600, 16, tenkai_adv=0.12)
        self.assertAlmostEqual(horse_features([], ctx)["tenkai"], 0.12)


class TestPipelineWiring(unittest.TestCase):
    def _race(self, day, order):
        entries = [Entry(horse_id=f"H{u}", umaban=u, corner_pos=[u, u], agari_rank=9 - u)
                   for u in range(1, 9)]
        return Race(f"r{day}", f"2026-10-{day:02d}", "東京", 1600, 8, entries, order,
                    {}, {}, surface="芝", baba="良")

    def test_history_carries_corner_and_tenkai(self):
        history: dict = {}
        record_result(self._race(1, list(range(1, 9))), history)
        rec = history["H1"][0]
        self.assertEqual(rec.corner_pos, [1, 1])
        self.assertEqual(rec.surface, "芝")
        ctxs = race_contexts(self._race(20, list(range(1, 9))), history)
        advs = {e.umaban: c.tenkai_adv for e, _, c in ctxs}
        self.assertNotEqual(advs[1], advs[8])  # 逃げ馬と追込馬で展開利が違う

    def test_dataset_roundtrip_keeps_tenkai_fields(self):
        race = self._race(1, list(range(1, 9)))
        back = ds.race_from_dict(ds.race_to_dict(race))
        self.assertEqual(back.surface, "芝")
        self.assertEqual(back.entries[0].corner_pos, race.entries[0].corner_pos)


class TestJraScraping(unittest.TestCase):
    def test_race_id(self):
        r = rid.build_race_id(2024, "東京", 5, 8, 11)
        self.assertEqual(r, "202405050811")
        self.assertTrue(rid.is_jra(r))
        self.assertFalse(rid.is_nankan(r))
        self.assertEqual(rid.place_of(r), "東京")
        self.assertEqual(rid.place_of("202444010111"), "大井")

    def test_urls(self):
        self.assertIn("race.netkeiba.com", result_url("202405050811"))
        self.assertIn("nar.netkeiba.com", result_url("202444010111"))
        self.assertIn("race.netkeiba.com", odds_api_url("202405050811", "trio"))
        self.assertIn("nar.netkeiba.com", odds_api_url("202444010111", "trio"))

    def test_parser_helpers(self):
        from nankeiba.scraping import parser as P
        self.assertEqual(P.parse_corner("3-3-2-1"), [3, 3, 2, 1])
        self.assertEqual(P._extract_distance_surface("15:40発走 / 芝1600m (左 A)"), (1600, "芝"))
        self.assertEqual(P._extract_distance_surface("ダ1400m (右)"), (1400, "ダ"))
        self.assertEqual(P._extract_baba("天候:晴 / 馬場:稍"), "稍")


if __name__ == "__main__":
    unittest.main()
