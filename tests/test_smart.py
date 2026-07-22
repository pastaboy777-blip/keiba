"""スマート出馬表(テンT/上がりT/ロ)のテスト。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core.interval import RunRecord
from nankeiba.core import smart as sma


def rec(dist, last3f, first3f=None, **kw):
    return RunRecord(date="2026-05-01", place="大井", distance=dist, field_size=12,
                     finish_pos=3, baba="良", corner_pos=[3, 3, 3, 3],
                     time_sec=kw.get("time", 101.0), last3f_sec=last3f, first3f_sec=first3f)


class TestRotation(unittest.TestCase):
    def test_all(self):
        self.assertEqual(sma.rotation(1400, 1600), "延")
        self.assertEqual(sma.rotation(1600, 1600), "同")
        self.assertEqual(sma.rotation(1800, 1600), "短")
        self.assertEqual(sma.rotation(None, 1600), "")


class TestTimes(unittest.TestCase):
    def test_agari_min(self):
        runs = [rec(1600, 39.0), rec(1600, 38.2), rec(1600, 39.5)]
        self.assertEqual(sma.agari_time(runs), 38.2)

    def test_ten_uses_first3f(self):
        runs = [rec(1600, 39.0, first3f=37.5), rec(1600, 39.0, first3f=36.9)]
        self.assertEqual(sma.ten_time(runs), 36.9)

    def test_none(self):
        self.assertIsNone(sma.agari_time([rec(1600, None)]))


class TestSmartTable(unittest.TestCase):
    def test_ranks_and_rot(self):
        entries = [
            (1, [rec(1600, 39.0, first3f=37.0)]),   # 上がり39.0
            (2, [rec(1400, 38.0, first3f=37.5)]),   # 上がり38.0(最速) 前走1400→今回1600=延
        ]
        tbl = sma.smart_table(entries, 1600)
        self.assertEqual(tbl[2].agari_rank, 1)      # 38.0が1位
        self.assertEqual(tbl[1].agari_rank, 2)
        self.assertEqual(tbl[2].rot, "延")

    def test_agari_top_order(self):
        entries = [(1, [rec(1600, 39.0)]), (2, [rec(1600, 37.5)]), (3, [rec(1600, 38.2)])]
        top = sma.agari_t_top(entries)
        self.assertEqual([um for um, _ in top], [2, 3, 1])


if __name__ == "__main__":
    unittest.main()
