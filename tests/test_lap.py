"""ラップ／ペース分析のテスト。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import lap
from nankeiba.scraping.rakuten import _res_time_to_sec, parse_result


class TestTimeParse(unittest.TestCase):
    def test_mmss(self):
        self.assertAlmostEqual(_res_time_to_sec("1:43.4"), 103.4)
        self.assertAlmostEqual(_res_time_to_sec("43.4"), 43.4)
        self.assertIsNone(_res_time_to_sec(""))
        self.assertIsNone(_res_time_to_sec("―"))


class TestAnalyze(unittest.TestCase):
    def _res(self, times_agari):
        # [(finish, umaban, time, agari)]
        return [{"finish": f, "umaban": u, "name": f"H{u}",
                 "popularity": f, "time_sec": t, "agari": a}
                for f, u, t, a in times_agari]

    def test_high_pace(self):
        # 前半が速く上がりが掛かる → ハイペース＝差し有利
        r = self._res([(1, 3, 103.4, 40.5)])
        a = lap.analyze(r, 1600)
        self.assertEqual(a.pace, "H")
        self.assertIn("差し", a.bias)

    def test_slow_pace(self):
        # 前半が遅く上がりが速い → スロー＝前残り
        r = self._res([(1, 3, 103.4, 37.0)])
        a = lap.analyze(r, 1600)
        self.assertEqual(a.pace, "S")
        self.assertIn("前残り", a.bias)

    def test_agari_ranking(self):
        r = self._res([(1, 3, 103.4, 39.7), (2, 11, 103.4, 39.6), (3, 2, 103.5, 39.5)])
        a = lap.analyze(r, 1600)
        # 上がり最速は3着の馬番2
        self.assertEqual(a.agari_top[0][0], 2)

    def test_empty(self):
        a = lap.analyze([], 1600)
        self.assertEqual(a.pace, "?")


class TestResultFields(unittest.TestCase):
    def test_parse_has_time_agari(self):
        html = ('<table class="dataTable"><tr><th>着順</th></tr>'
                '<tr><td>1</td><th>3</th><td>3</td><td>ウマ</td><td>牝4</td>'
                '<td>53.0</td><td>452</td><td>騎手</td><td>1:43.4</td><td></td>'
                '<td>39.7</td><td>調教師</td><td>3</td></tr></table>')
        out = parse_result(html)
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out[0]["time_sec"], 103.4)
        self.assertAlmostEqual(out[0]["agari"], 39.7)


if __name__ == "__main__":
    unittest.main()
