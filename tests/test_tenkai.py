"""展開指数のテスト。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import tenkai


def race(rid, place, distance, n, order):
    """order = 4角順位のリスト。着順は order と同じ並びなら位置が完全に効く。"""
    return [dict(rid=rid, place=place, distance=distance, corner4=c, finish=f)
            for c, f in order]


class TestBand(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(tenkai.band(1200), "短")
        self.assertEqual(tenkai.band(1400), "中")
        self.assertEqual(tenkai.band(2000), "長")
        self.assertEqual(tenkai.band(None), "中")


class TestPositionWeight(unittest.TestCase):
    def test_position_decides_gives_high_dep(self):
        """4角の並び順どおりに入線するコースは依存度が1に近い。"""
        rows = []
        for i in range(120):
            rows += race(f"r{i}", "浦和", 1400, 8,
                         [(c, c) for c in range(1, 9)])
        P = tenkai.PositionWeight.build(rows, min_runs=100)
        self.assertGreater(P.of("浦和", 1400), 0.9)

    def test_position_irrelevant_gives_low_dep(self):
        """4角と着順が逆でも、無関係なら依存度は0に潰れる（負にしない）。"""
        rows = []
        for i in range(120):
            rows += race(f"r{i}", "大井", 1400, 8,
                         [(c, 9 - c) for c in range(1, 9)])
        P = tenkai.PositionWeight.build(rows, min_runs=100)
        self.assertEqual(P.of("大井", 1400), 0.0)

    def test_small_fields_skipped(self):
        rows = race("r1", "浦和", 1400, 4, [(1, 1), (2, 2), (3, 3), (4, 4)])
        P = tenkai.PositionWeight.build(rows, min_field=6, min_runs=1)
        self.assertEqual(P.dep, {})

    def test_fallback_to_same_place(self):
        rows = []
        for i in range(120):
            rows += race(f"r{i}", "浦和", 1400, 8, [(c, c) for c in range(1, 9)])
        P = tenkai.PositionWeight.build(rows, min_runs=100)
        # 未測定の距離帯でも同じ場の平均で返す
        self.assertGreater(P.of("浦和", 2000), 0.0)

    def test_roundtrip(self):
        import tempfile
        rows = []
        for i in range(120):
            rows += race(f"r{i}", "浦和", 1400, 8, [(c, c) for c in range(1, 9)])
        P = tenkai.PositionWeight.build(rows, min_runs=100)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "p.json")
            P.dump(p)
            Q = tenkai.PositionWeight.load(p)
        self.assertEqual(Q.dep, P.dep)


class TestSenkou(unittest.TestCase):
    def test_front_runner_is_high(self):
        runs = [dict(corner_pos=[1, 1], field_size=10)] * 4
        self.assertGreater(tenkai.senkou(runs), 0.85)

    def test_closer_is_low(self):
        runs = [dict(corner_pos=[9], field_size=10)] * 4
        self.assertLess(tenkai.senkou(runs), 0.2)

    def test_normalised_by_field_size(self):
        """頭数で割ること。8頭立ての4番手と16頭立ての8番手は同じ。"""
        a = tenkai.senkou([dict(corner_pos=[4], field_size=8)] * 3)
        b = tenkai.senkou([dict(corner_pos=[8], field_size=16)] * 3)
        self.assertAlmostEqual(a, b)

    def test_uses_recent_only(self):
        """⚠️ 直近に絞ること。脚質は変わる。"""
        runs = ([dict(corner_pos=[1], field_size=10)] * 6
                + [dict(corner_pos=[10], field_size=10)] * 20)
        self.assertGreater(tenkai.senkou(runs, limit=6), 0.85)

    def test_no_data(self):
        self.assertIsNone(tenkai.senkou([]))
        self.assertIsNone(tenkai.senkou([dict(corner_pos=None, field_size=10)]))


class TestFit(unittest.TestCase):
    def setUp(self):
        self.P = tenkai.PositionWeight(dep={("浦和", "中"): 0.80,
                                            ("大井", "中"): 0.50})

    def test_front_runner_at_position_course(self):
        self.assertGreater(tenkai.fit("浦和", 1400, 0.9, self.P), 0.5)

    def test_closer_at_position_course_is_negative(self):
        self.assertLess(tenkai.fit("浦和", 1400, 0.1, self.P), -0.5)

    def test_damped_where_position_matters_less(self):
        """位置が効かない場では、先行力が高くても適合度は小さくなる。"""
        a = tenkai.fit("浦和", 1400, 0.9, self.P)
        b = tenkai.fit("大井", 1400, 0.9, self.P)
        self.assertGreater(a, b)

    def test_neutral_horse_is_zero(self):
        self.assertAlmostEqual(tenkai.fit("浦和", 1400, 0.5, self.P), 0.0)

    def test_none_senkou(self):
        self.assertIsNone(tenkai.fit("浦和", 1400, None, self.P))


class TestLabel(unittest.TestCase):
    def test_zero_has_two_meanings(self):
        """⚠️ 0付近は「コースが位置を要求しない」と「馬が中庸」で意味が違う。"""
        self.assertIn("中庸", tenkai.label(0.0, dep=0.80))
        self.assertIn("効きにくい", tenkai.label(0.0, dep=0.30))

    def test_extremes(self):
        self.assertIn("向く", tenkai.label(0.5))
        self.assertIn("向かない", tenkai.label(-0.5))
        self.assertEqual(tenkai.label(None), "―")


if __name__ == "__main__":
    unittest.main()
