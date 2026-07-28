"""指数の補正項（斤量・位置取りロス・出遅れ）のテスト。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import adjust
from nankeiba.core.interval import RunRecord


def _run(**kw):
    base = dict(date="2026-07-01", place="川崎", distance=1400,
                field_size=12, finish_pos=5)
    base.update(kw)
    return RunRecord(**base)


class TestKinryo(unittest.TestCase):
    def test_base_weight_is_zero(self):
        self.assertEqual(adjust.kinryo_sec(55.0, 1400, sec_per_kg_per_f=0.003), 0.0)

    def test_heavier_is_positive(self):
        """重い斤量は損 → 正の秒数（指数に足し戻す）。"""
        v = adjust.kinryo_sec(57.0, 1400, sec_per_kg_per_f=0.003)
        self.assertAlmostEqual(v, 0.003 * 2 * 7, places=3)
        self.assertGreater(v, 0)

    def test_lighter_is_negative(self):
        self.assertLess(adjust.kinryo_sec(53.0, 1400, sec_per_kg_per_f=0.003), 0)

    def test_missing_inputs(self):
        self.assertEqual(adjust.kinryo_sec(None, 1400), 0.0)
        self.assertEqual(adjust.kinryo_sec(56.0, None), 0.0)

    def test_default_coefficient_is_measured(self):
        """既定係数は実測値。0なら『効果なしと測れた』ことを意味する。"""
        self.assertIsInstance(adjust.SEC_PER_KG_PER_F, float)


class TestPositionLoss(unittest.TestCase):
    def test_front_runner_loses_nothing(self):
        pl = adjust.position_loss(_run(corner_pos=[1, 1, 1, 1]))
        self.assertEqual(pl.sec, 0.0)
        self.assertFalse(pl)

    def test_backmarker_loses_more_than_midfield(self):
        back = adjust.position_loss(_run(corner_pos=[12, 12, 12, 12]))
        mid = adjust.position_loss(_run(corner_pos=[6, 6, 6, 6]))
        self.assertGreater(back.sec, mid.sec)
        self.assertGreater(mid.sec, 0)

    def test_more_corners_more_loss(self):
        four = adjust.position_loss(_run(corner_pos=[10, 10, 10, 10]))
        two = adjust.position_loss(_run(corner_pos=[10, 10]))
        self.assertGreater(four.sec, two.sec)
        self.assertEqual((four.corners, two.corners), (4, 2))

    def test_needs_corner_and_field(self):
        self.assertIsNone(adjust.position_loss(_run(corner_pos=[])))
        self.assertIsNone(adjust.position_loss(_run(corner_pos=[3], field_size=1)))


class TestLateStart(unittest.TestCase):
    def _hist(self, first_corners):
        return [_run(corner_pos=[c, c, c], date=f"2026-0{i+1}-01")
                for i, c in enumerate(first_corners)]

    def test_flags_unusually_slow_break(self):
        h = self._hist([2, 2, 3])          # 普段は前
        now = _run(corner_pos=[12, 10, 8])  # 今回だけ最後方
        self.assertGreater(adjust.late_start(now, h), 0)

    def test_normal_break_is_zero(self):
        h = self._hist([2, 2, 3])
        self.assertEqual(adjust.late_start(_run(corner_pos=[2, 2, 2]), h), 0.0)

    def test_needs_enough_history(self):
        h = self._hist([2, 2])
        self.assertEqual(adjust.late_start(_run(corner_pos=[12, 12, 12]), h), 0.0)


class TestAdjustment(unittest.TestCase):
    def test_total_is_kinryo_only(self):
        """位置取りの足し戻しは実測で棄却したので total には入らない。"""
        a = adjust.Adjustment(kinryo_sec=0.10, position_sec=0.20, late=0.0)
        self.assertAlmostEqual(a.total_sec, 0.10, places=3)
        self.assertAlmostEqual(a.points, 1.0, places=1)

    def test_note_mentions_only_active_parts(self):
        a = adjust.Adjustment(kinryo_sec=0.0, position_sec=0.30, late=0.4)
        n = a.note()
        self.assertIn("位置取り", n)
        self.assertIn("出遅れ", n)
        self.assertNotIn("斤量", n)

    def test_adjust_end_to_end(self):
        a = adjust.adjust(_run(corner_pos=[10, 9, 8, 7], kinryo=56.0),
                          sec_per_kg_per_f=0.003)
        self.assertGreater(a.position_sec, 0)      # 指標としては出す
        self.assertGreater(a.total_sec, 0)         # ただし total は斤量ぶんのみ
        self.assertAlmostEqual(a.total_sec, a.kinryo_sec, places=3)


class TestRevenge(unittest.TestCase):
    """前走大敗×前々のポジション = 巻き返し候補（実測 lift 1.39）。"""

    def test_bad_finish_but_forward_is_flagged(self):
        self.assertTrue(adjust.revenge(
            _run(finish_pos=9, corner_pos=[2, 2, 2, 3], field_size=12)))

    def test_boundary_is_around_fourth_in_a_twelve_horse_field(self):
        """実測の境界は1.5秒。12頭立てなら4番手(1.21秒)まで、5番手(1.61秒)は外。"""
        self.assertTrue(adjust.revenge(
            _run(finish_pos=10, corner_pos=[4, 4, 4, 4], field_size=12)))
        self.assertFalse(adjust.revenge(
            _run(finish_pos=10, corner_pos=[5, 5, 5, 5], field_size=12)))

    def test_bad_finish_from_the_back_is_not(self):
        self.assertFalse(adjust.revenge(
            _run(finish_pos=9, corner_pos=[12, 12, 11, 11], field_size=12)))

    def test_good_finish_is_not_a_revenge_case(self):
        self.assertFalse(adjust.revenge(
            _run(finish_pos=2, corner_pos=[2, 2, 2, 2], field_size=12)))

    def test_needs_corner_data(self):
        self.assertFalse(adjust.revenge(_run(finish_pos=9, corner_pos=[])))


class TestPositionNotAddedBack(unittest.TestCase):
    """IDM式の『損を足し戻す』は実測で棄却したので total に含めない。"""

    def test_total_excludes_position(self):
        a = adjust.Adjustment(kinryo_sec=0.10, position_sec=1.50, late=0.0)
        self.assertAlmostEqual(a.total_sec, 0.10, places=3)
        self.assertAlmostEqual(a.points, 1.0, places=1)


class TestNewspaperIntegration(unittest.TestCase):
    """巻き返し候補が新聞カードに出ること。"""

    def _card(self):
        from nankeiba.core import newspaper as nb
        from nankeiba.core.hindex import SpeedIndexModel

        def runs(um, corners, fin):
            return [RunRecord(date="2026-07-20", place="川崎", distance=1400,
                              field_size=12, finish_pos=fin, corner_pos=corners,
                              time_sec=92.0 + um, kinryo=55.0),
                    RunRecord(date="2026-07-01", place="川崎", distance=1400,
                              field_size=12, finish_pos=4, corner_pos=[4, 4, 4, 4],
                              time_sec=93.0, kinryo=55.0)]

        entries = [
            nb.PaperEntry(umaban=1, name="マキカエシ", history=runs(1, [2, 2, 2, 3], 9)),
            nb.PaperEntry(umaban=2, name="ソトマワリ", history=runs(2, [11, 11, 11, 11], 9)),
            nb.PaperEntry(umaban=3, name="ゼンソウチャクジュン", history=runs(3, [2, 2, 2, 2], 2)),
        ]
        model = SpeedIndexModel.fit([r for e in entries for r in e.history])
        return nb, nb.build_card(
            nb.RaceHeader(place="川崎", distance=1400, date="2026-07-29",
                          race_no=1, baba=None), entries, model)

    def test_only_the_forward_loser_is_flagged(self):
        _, card = self._card()
        self.assertEqual([v.entry.umaban for v in card.revengers()], [1])

    def test_appears_in_text_render(self):
        nb, card = self._card()
        t = nb.render_text(card)
        self.assertIn("巻き返し候補", t)
        self.assertIn("マキカエシ", t)
        self.assertNotIn("ソトマワリ", t.split("【10走以内")[0].split("巻き返し候補")[1])


if __name__ == "__main__":
    unittest.main()
