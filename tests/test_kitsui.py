"""きついラップを走った組・追跡のテスト。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import kitsui


def row(rid, name, laps, finish=1, pop=1, distance=1200, place="大井",
        date="2026-07-21", race_no=9):
    return dict(rid=rid, date=date, place=place, race_no=race_no,
                distance=distance, laps=laps, name=name, finish=finish,
                popularity=pop, time_sec=72.8, corner4=3)


class TestShape(unittest.TestCase):
    def test_reproduces_the_stated_examples(self):
        """提示された3レースの数字と一致すること（定義の逆算が正しいか）。"""
        for laps, sub, sp in (
                ([12.4, 11.5, 11.8, 12.5, 11.9, 12.7], 3, 1.2),
                ([12.7, 11.5, 11.9, 12.6, 11.8, 12.9], 3, 1.4),
                ([13.0, 11.5, 11.5, 11.8, 12.3, 11.8, 13.0], 4, 1.5)):
            s = kitsui.shape(laps)
            self.assertEqual(s.sub12, sub)
            self.assertAlmostEqual(s.spread, sp, places=2)
            self.assertTrue(s.kitsui)

    def test_partial_first_furlong_excluded(self):
        """⚠️ 1300m・1500m は先頭が 6.7 や 7.1 の部分ハロン。混ぜると最速差が
        常に5秒超になり、その距離が丸ごと候補から消える。"""
        laps = [7.1, 12.0, 11.8, 11.9, 11.7, 12.5]
        s = kitsui.shape(laps)
        self.assertLess(s.spread, 1.5)
        self.assertTrue(s.kitsui)

    def test_uneven_lap_is_not_kitsui(self):
        """緩むラップは落とす（最速差が大きい）。"""
        s = kitsui.shape([12.0, 11.5, 13.5, 13.2, 11.8, 12.6])
        self.assertGreater(s.spread, 1.5)
        self.assertFalse(s.kitsui)

    def test_too_few_fast_furlongs(self):
        s = kitsui.shape([12.4, 12.3, 11.9, 12.5, 12.2, 12.4])
        self.assertLess(s.sub12, 3)
        self.assertFalse(s.kitsui)

    def test_short_lap_list(self):
        s = kitsui.shape([12.0, 11.5])
        self.assertIsNone(s.spread)
        self.assertFalse(s.kitsui)

    def test_no_laps(self):
        self.assertFalse(kitsui.shape(None).kitsui)
        self.assertFalse(kitsui.shape([]).kitsui)

    def test_custom_thresholds(self):
        laps = [12.4, 12.3, 11.9, 12.5, 12.2, 12.4]
        self.assertTrue(kitsui.shape(laps, min_sub12=1).kitsui_custom)


class TestCollect(unittest.TestCase):
    def setUp(self):
        hard = [12.4, 11.5, 11.8, 12.5, 11.9, 12.7]
        soft = [12.0, 11.5, 13.5, 13.2, 11.8, 12.6]
        self.rows = (
            [row("A", f"h{i}", hard, finish=i + 1, pop=i + 1) for i in range(6)]
            + [row("B", f"s{i}", soft, finish=i + 1) for i in range(6)])

    def test_only_hard_races(self):
        got = kitsui.collect(self.rows)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].field_size, 6)

    def test_runners_sorted_by_finish(self):
        got = kitsui.collect(self.rows)[0]
        self.assertEqual([x["finish"] for x in got.runners], [1, 2, 3, 4, 5, 6])

    def test_keeps_losers_too(self):
        """⚠️ **全頭を残す。**好走した馬だけ追うと『前走で走った馬』を
        追うことになり、この考え方の意味が無くなる。"""
        got = kitsui.collect(self.rows)[0]
        self.assertIn("h5", [x["name"] for x in got.runners])

    def test_empty(self):
        self.assertEqual(kitsui.collect([]), [])


class TestChase(unittest.TestCase):
    def test_matches_entries(self):
        hard = [12.4, 11.5, 11.8, 12.5, 11.9, 12.7]
        races = kitsui.collect([row("A", f"h{i}", hard, finish=i + 1)
                                for i in range(6)])
        got = kitsui.chase(races, {5: ["h0", "よその馬"], 7: ["h3"]})
        self.assertEqual(len(got[5]), 1)
        self.assertEqual(got[5][0][0], "h0")
        self.assertEqual(len(got[7]), 1)

    def test_race_with_no_match_is_omitted(self):
        hard = [12.4, 11.5, 11.8, 12.5, 11.9, 12.7]
        races = kitsui.collect([row("A", f"h{i}", hard, finish=i + 1)
                                for i in range(6)])
        self.assertNotIn(9, kitsui.chase(races, {9: ["まったく別の馬"]}))

    def test_carries_source_result(self):
        """どのレースの何着だったかを持ち回ること（後で読めるように）。"""
        hard = [12.4, 11.5, 11.8, 12.5, 11.9, 12.7]
        races = kitsui.collect([row("A", f"h{i}", hard, finish=i + 1, pop=i + 2)
                                for i in range(6)])
        nm, kr, x = kitsui.chase(races, {1: ["h2"]})[1][0]
        self.assertEqual(x["finish"], 3)
        self.assertEqual(kr.race_no, 9)


if __name__ == "__main__":
    unittest.main()
