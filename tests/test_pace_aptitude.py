"""ペース適性 S/H/F/U のテスト。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core.interval import RunRecord
from nankeiba.core import pace_aptitude as pa


def rec(first3f, last3f, finish, field=12, **kw):
    return RunRecord(date="2026-05-01", place="大井", distance=1600, field_size=field,
                     finish_pos=finish, baba="良", corner_pos=kw.get("corner", [4, 4, 4, 4]),
                     time_sec=kw.get("time", 101.0), first3f_sec=first3f, last3f_sec=last3f)


class TestRacePace(unittest.TestCase):
    def test_high(self):
        self.assertEqual(pa.race_pace(rec(36.0, 40.0, 3)), "H")   # 前半速い

    def test_slow(self):
        self.assertEqual(pa.race_pace(rec(40.0, 37.0, 3)), "S")   # 前半遅い

    def test_middle(self):
        self.assertEqual(pa.race_pace(rec(38.5, 38.5, 3)), "M")

    def test_none(self):
        self.assertIsNone(pa.race_pace(rec(None, None, 3)))


class TestAptitude(unittest.TestCase):
    def test_high_type(self):
        # ハイで好走(上位)、スローで凡走 → H
        runs = [rec(36.0, 40.0, 1), rec(36.2, 40.1, 2), rec(40.0, 37.0, 10),
                rec(35.8, 40.0, 1)]
        self.assertEqual(pa.pace_aptitude(runs), "H")

    def test_slow_type(self):
        runs = [rec(40.0, 37.0, 1), rec(40.2, 37.1, 2), rec(36.0, 40.0, 11),
                rec(40.1, 37.0, 1)]
        self.assertEqual(pa.pace_aptitude(runs), "S")

    def test_flex_type(self):
        runs = [rec(40.0, 37.0, 1), rec(36.0, 40.0, 2), rec(40.1, 37.0, 2),
                rec(35.9, 40.0, 1)]
        self.assertEqual(pa.pace_aptitude(runs), "F")

    def test_unknown_few(self):
        self.assertEqual(pa.pace_aptitude([rec(None, None, 3)]), "U")

    def test_nige_geki(self):
        runs = [rec(36.0, 40.0, 1, corner=[1, 1, 1, 1]) for _ in range(4)]
        self.assertTrue(pa.pace_aptitude_mark(runs).endswith("激"))


if __name__ == "__main__":
    unittest.main()
