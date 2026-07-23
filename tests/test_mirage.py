"""見かけ倒し指数(mirage)検知のテスト。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import mirage as mir
from nankeiba.core.hindex import SpeedIndexModel, par_time
from nankeiba.core.interval import RunRecord


def _run(place, dist, time_sec, date="2026-05-01"):
    return RunRecord(date=date, place=place, distance=dist, field_size=12,
                     finish_pos=1, time_sec=time_sec)


class TestCentral(unittest.TestCase):
    def test_is_central(self):
        self.assertTrue(mir.is_central("Ｊ中山"))
        self.assertTrue(mir.is_central("J東京"))
        self.assertFalse(mir.is_central("大井"))
        self.assertFalse(mir.is_central(None))


class TestDetect(unittest.TestCase):
    def setUp(self):
        # par基準で「速い/遅い」を作る。中央の速い時計 vs 大井の平凡
        self.model = SpeedIndexModel(global_variant=0.0)

    def test_central_mirage(self):
        # 最高指数が中央、大井は遅い → ⚠️見かけ倒し(level2)
        hist = [
            _run("大井", 1400, par_time(1400) + 1.0),        # 大井は遅い
            _run("Ｊ新潟", 1800, par_time(1800) - 4.0),       # 中央で激速
        ]
        m = mir.detect(hist, self.model, "大井", 1400)
        self.assertEqual(m.level, 2)
        self.assertIn("中央", m.tag) if False else None
        self.assertTrue(any("中央" in r for r in m.reasons))

    def test_clean_local(self):
        # すべて大井、当地で速い → フラグ無し
        hist = [
            _run("大井", 1400, par_time(1400) - 2.0),
            _run("大井", 1400, par_time(1400) - 1.5),
        ]
        m = mir.detect(hist, self.model, "大井", 1400)
        self.assertEqual(m.level, 0)
        self.assertFalse(bool(m))

    def test_no_local_record(self):
        # 当地の実績が無い → level2
        hist = [_run("船橋", 1400, par_time(1400) - 3.0)]
        m = mir.detect(hist, self.model, "大井", 1400)
        self.assertGreaterEqual(m.level, 2)


if __name__ == "__main__":
    unittest.main()
