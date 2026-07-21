"""激走マーク(実験的)のスモークテスト。

※ spark は未検証の実験的モジュール。ここでは「落ちない・型が正しい・ランクが
   高々3つ」といった構造だけを担保する(的中性能は担保しない)。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core.interval import RunRecord
from nankeiba.core import spark as sk, hindex


def rec(**kw):
    base = dict(date="2026-05-01", place="大井", distance=1600, field_size=12,
                finish_pos=6, baba="良", corner_pos=[5, 5, 5, 5], time_sec=103.0)
    base.update(kw)
    return RunRecord(**base)


class TestSpark(unittest.TestCase):
    def _entries(self):
        return [
            (1, [rec(finish_pos=8, time_sec=105.0), rec(finish_pos=1, time_sec=99.0)]),
            (2, [rec(finish_pos=3, time_sec=101.0)]),
            (3, [rec(finish_pos=10, time_sec=106.0)]),
            (4, [rec(finish_pos=2, time_sec=100.5)]),
        ]

    def test_returns_all(self):
        m = hindex.SpeedIndexModel()
        sp = sk.spark_ranking(self._entries(), m, "大井", 1600, "2026-07-21")
        self.assertEqual(set(sp), {1, 2, 3, 4})

    def test_at_most_3_ranks(self):
        m = hindex.SpeedIndexModel()
        sp = sk.spark_ranking(self._entries(), m, "大井", 1600, "2026-07-21")
        ranks = sorted(s.rank for s in sp.values() if s.rank)
        self.assertLessEqual(len(ranks), 3)
        self.assertTrue(all(1 <= r <= 3 for r in ranks))

    def test_mark_text(self):
        s = sk.Spark(umaban=5, score=1.0, rank=2)
        self.assertEqual(s.mark, "激2番")
        self.assertEqual(sk.Spark(umaban=6, score=0.0).mark, "")

    def test_empty(self):
        m = hindex.SpeedIndexModel()
        self.assertEqual(sk.spark_ranking([], m, "大井", 1600, "2026-07-21"), {})


if __name__ == "__main__":
    unittest.main()
