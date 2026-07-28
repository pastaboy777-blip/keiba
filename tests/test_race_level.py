"""前走のレースレベル（メンバーの格）のテスト。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import race_level as rl
from nankeiba.core.interval import RunRecord

TABLE = {
    # 勝ち慣れた馬が集まった＝ハイレベル戦
    "2026-07-01|川崎|1400": {"強A": 0.5, "強B": 0.4, "強C": 0.35,
                             "強D": 0.32, "対象": 0.0},
    # 勝ち星の無い馬ばかり＝平凡
    "2026-07-02|川崎|1400": {"弱A": 0.0, "弱B": 0.05, "弱C": 0.0,
                             "弱D": 0.1, "対象": 0.9},
    # 他馬が足りない
    "2026-07-03|川崎|1400": {"甲": 0.4, "対象": 0.1},
}


class TestLevelOf(unittest.TestCase):
    def test_high_level_race(self):
        lv = rl.level_of("2026-07-01", "川崎", 1400, "対象", table=TABLE)
        self.assertAlmostEqual(lv.grade, 0.4, places=3)   # [0.32,0.35,0.4,0.5]の中央
        self.assertTrue(lv.is_high)
        self.assertEqual(lv.label(), "ハイレベル戦")
        self.assertEqual(lv.n_others, 4)

    def test_weak_race(self):
        lv = rl.level_of("2026-07-02", "川崎", 1400, "対象", table=TABLE)
        self.assertFalse(lv.is_high)
        self.assertEqual(lv.label(), "平凡")

    def test_target_horse_is_excluded(self):
        """対象馬自身を混ぜると格が歪む。ハイレベル戦に未勝利の対象馬がいる例。"""
        with_self = rl.level_of("2026-07-01", "川崎", 1400, None, table=TABLE)
        without = rl.level_of("2026-07-01", "川崎", 1400, "対象", table=TABLE)
        self.assertAlmostEqual(without.grade, 0.4, places=3)
        self.assertAlmostEqual(with_self.grade, 0.35, places=3)
        self.assertGreater(without.grade, with_self.grade)

    def test_needs_enough_others(self):
        self.assertIsNone(rl.level_of("2026-07-03", "川崎", 1400, "対象",
                                      table=TABLE))

    def test_unknown_race_is_none_not_low(self):
        """収録が無いレースは None。『低レベル』と読み替えてはいけない。"""
        self.assertIsNone(rl.level_of("2020-01-01", "門別", 1200, None,
                                      table=TABLE))
        self.assertIsNone(rl.level_of(None, "川崎", 1400, None, table=TABLE))


class TestPrevLevel(unittest.TestCase):
    def _rec(self, date):
        return RunRecord(date=date, place="川崎", distance=1400,
                         field_size=10, finish_pos=9)

    def test_uses_first_history_entry(self):
        h = [self._rec("2026-07-01"), self._rec("2026-07-02")]
        lv = rl.prev_level(h, "対象", table=TABLE)
        self.assertTrue(lv.is_high)          # 先頭＝直近＝ハイレベル戦のほう

    def test_empty_history(self):
        self.assertIsNone(rl.prev_level([], "対象", table=TABLE))


class TestShippedTable(unittest.TestCase):
    def test_table_is_loaded(self):
        self.assertGreater(len(rl.TABLE), 100, "data/race_grade.json が読めていない")

    def test_entries_look_like_rates(self):
        k = next(iter(rl.TABLE))
        self.assertIn("|", k)
        for v in rl.TABLE[k].values():
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 1.0)


if __name__ == "__main__":
    unittest.main()
