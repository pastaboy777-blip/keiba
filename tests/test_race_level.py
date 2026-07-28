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


class TestRivalsInNewspaper(unittest.TestCase):
    """『前走で先着した相手の、その後』が新聞に事実として出ること。"""

    def _index(self):
        from nankeiba.core import rivals as rv

        idx = rv.Index.__new__(rv.Index)      # キャッシュ読込を飛ばす
        idx.roster = {("2026-06-03", "船橋", 1500):
                      [("本命馬", 1), ("負かした馬", 2), ("凡走馬", 7)]}
        idx.runs = {
            "負かした馬": {"2026-07-01": ("2026-07-01", "船橋", 1600, 3,
                                          "小石川賞競走 Ｂ１")},
            "凡走馬": {"2026-07-01": ("2026-07-01", "船橋", 1600, 9, "Ｃ２三")},
        }
        return idx

    def test_beaten_lists_only_horses_behind_me(self):
        idx = self._index()
        h = [RunRecord(date="2026-06-03", place="船橋", distance=1500,
                       field_size=8, finish_pos=1, race_name="手賀沼特別")]
        b = idx.beaten(h, "本命馬")
        self.assertEqual(sorted(r.name for r in b.rivals),
                         ["凡走馬", "負かした馬"])

    def test_stakes_placing_is_starred_and_ranked_first(self):
        idx = self._index()
        h = [RunRecord(date="2026-06-03", place="船橋", distance=1500,
                       field_size=8, finish_pos=1, race_name="手賀沼特別")]
        b = idx.beaten(h, "本命馬")
        top = b.highlights()[0]
        self.assertEqual(top.name, "負かした馬")
        self.assertIn("★", top.line())
        self.assertIn("小石川賞競走", top.line())

    def test_class_names_are_not_treated_as_stakes(self):
        from nankeiba.core import rivals as rv
        self.assertFalse(rv.is_stakes("３歳二"))
        self.assertFalse(rv.is_stakes("Ｃ２三四"))
        self.assertTrue(rv.is_stakes("手賀沼特別"))
        self.assertTrue(rv.is_stakes("小石川賞競走 Ｂ１"))

    def test_appears_in_text_render(self):
        from nankeiba.core import newspaper as nb
        from nankeiba.core.hindex import SpeedIndexModel

        h = [RunRecord(date="2026-06-03", place="船橋", distance=1500,
                       field_size=8, finish_pos=1, race_name="手賀沼特別",
                       time_sec=95.0, corner_pos=[3, 3, 3, 3])]
        e = nb.PaperEntry(umaban=3, name="本命馬", history=h)
        model = SpeedIndexModel.fit(h)
        card = nb.build_card(
            nb.RaceHeader(place="川崎", distance=1600, date="2026-07-29",
                          race_no=11, baba=None), [e], model, self._index())
        t = nb.render_text(card)
        self.assertIn("前走で先着した相手の、その後", t)
        self.assertIn("小石川賞競走", t)


if __name__ == "__main__":
    unittest.main()
