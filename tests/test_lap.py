"""ラップ／ペース分析のテスト。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import lap
from nankeiba.scraping.rakuten import _res_time_to_sec, parse_result, parse_lap


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

    def test_real_furlongs_high(self):
        # 2R実測: テン35.5 vs 上がり38.7 → 前傾3.2 → ハイ
        r = self._res([(1, 7, 74.2, None)])
        laps = {"furlongs": [12.6, 11.3, 11.6, 12.6, 12.5, 13.6],
                "agari4f": 50.3, "agari3f": 38.7, "corners": None}
        a = lap.analyze(r, 1200, laps)
        self.assertEqual(a.source, "実測ラップ")
        self.assertEqual(a.pace, "H")
        self.assertAlmostEqual(a.ten3f, 35.5)
        self.assertAlmostEqual(a.last3f, 38.7)


class TestParseLap(unittest.TestCase):
    def test_extract(self):
        html = ("<div>ハロンタイム 12.9-12.3-13.4-12.5-12.6-13.2-13.1-13.4 "
                "上がり 4F 52.3 - 3F 39.7 ■ コーナー通過順位 １角 (3,7),(2,4,11) </div>")
        d = parse_lap(html)
        self.assertEqual(len(d["furlongs"]), 8)
        self.assertAlmostEqual(d["furlongs"][0], 12.9)
        self.assertAlmostEqual(d["agari3f"], 39.7)
        self.assertAlmostEqual(d["agari4f"], 52.3)
        self.assertIn("3,7", d["corners"])

    def test_none(self):
        self.assertIsNone(parse_lap("<div>ラップ情報なし</div>"))


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
