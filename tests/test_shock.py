"""体感速度ショック（除外フィルタ）のテスト。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import shock
from nankeiba.core.interval import RunRecord

TABLE = {"川崎|1400": 13.44, "川崎|1600": 13.33, "大井|1200": 12.75}


def _run(place, dist, time_sec):
    return RunRecord(date="2026-07-01", place=place, distance=dist, field_size=12,
                     finish_pos=5, time_sec=time_sec)


class TestPace(unittest.TestCase):
    def test_pace_per_furlong(self):
        # 1400m を 91.0秒 → 7F → 13.0 s/F
        self.assertAlmostEqual(shock.pace_per_furlong(91.0, 1400), 13.0)
        self.assertIsNone(shock.pace_per_furlong(None, 1400))
        self.assertIsNone(shock.pace_per_furlong(91.0, 0))

    def test_par_exact_and_nearest(self):
        self.assertEqual(shock.par_pace("川崎", 1400, TABLE), 13.44)
        # 1500m は未登録 → 同じ場の最近傍(1400/1600)で代用
        self.assertIn(shock.par_pace("川崎", 1500, TABLE), (13.44, 13.33))
        # 遠すぎる距離・未知の場は None
        self.assertIsNone(shock.par_pace("川崎", 2600, TABLE))
        self.assertIsNone(shock.par_pace("盛岡", 1400, TABLE))
        self.assertIsNone(shock.par_pace(None, 1400, TABLE))


class TestDetect(unittest.TestCase):
    def test_hard_shock_flagged(self):
        # 前走: 大井1800をゆったり(14.2 s/F) → 今走 川崎1400(par13.44) = -0.76
        prev = _run("大井", 1800, 14.2 * 9)
        t = shock.detect([prev], "川崎", 1400, table=TABLE)
        self.assertEqual(t.level, 2)
        self.assertTrue(bool(t))
        self.assertIn("速度ショック", t.tag)
        self.assertLess(t.value, shock.SHOCK_HARD)

    def test_easier_is_not_a_buy_signal(self):
        # 前走を速く走っていても level は 0（プラス側は買い材料にしない）
        prev = _run("大井", 1200, 12.0 * 6)
        t = shock.detect([prev], "川崎", 1400, table=TABLE)
        self.assertGreater(t.value, 0)
        self.assertEqual(t.level, 0)
        self.assertFalse(bool(t))
        self.assertEqual(t.tag, "")

    def test_soft_zone(self):
        # -0.2 〜 -0.6 の間は注意(level1)
        prev = _run("大井", 1200, 13.8 * 6)   # 13.8 → 13.44-13.8 = -0.36
        t = shock.detect([prev], "川崎", 1400, table=TABLE)
        self.assertEqual(t.level, 1)

    def test_none_when_data_missing(self):
        self.assertIsNone(shock.detect([], "川崎", 1400, table=TABLE))
        self.assertIsNone(shock.detect([_run("大井", 1200, None)], "川崎", 1400, table=TABLE))
        self.assertIsNone(shock.detect([_run("大井", 1200, 72.0)], "未知場", 1400, table=TABLE))


if __name__ == "__main__":
    unittest.main()
