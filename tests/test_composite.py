"""総合指数(展開・馬場合成)のテスト。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core.interval import RunRecord
from nankeiba.core import composite as cp, pace, summary as sm


def rec(**kw):
    base = dict(date="2026-06-01", place="大井", distance=1600, field_size=12,
                finish_pos=3, baba="良", corner_pos=[3, 3, 3, 3], time_sec=101.0)
    base.update(kw)
    return RunRecord(**base)


class TestStyle(unittest.TestCase):
    def test_nige(self):
        self.assertEqual(cp.dominant_style([rec(corner_pos=[1, 1, 1, 1])]), "逃げ")

    def test_senko(self):
        self.assertEqual(cp.dominant_style([rec(corner_pos=[3, 3, 3, 3], field_size=12)]), "先行")

    def test_sashi(self):
        self.assertEqual(cp.dominant_style([rec(corner_pos=[8, 8, 8, 6], field_size=12)]), "差し")

    def test_oikomi(self):
        self.assertEqual(cp.dominant_style([rec(corner_pos=[12, 12, 11, 10], field_size=12)]), "追込")

    def test_none(self):
        self.assertIsNone(cp.dominant_style([rec(corner_pos=[])]))


class TestPaceBonus(unittest.TestCase):
    def test_front_favored_helps_front(self):
        ctx = cp.PaceContext(front_bias=1, going="良")
        self.assertGreater(cp.pace_bonus("逃げ", ctx), 0)
        self.assertLess(cp.pace_bonus("差し", ctx), 0)

    def test_closer_favored_helps_closer(self):
        ctx = cp.PaceContext(front_bias=-1, going="良")
        self.assertGreater(cp.pace_bonus("差し", ctx), 0)
        self.assertLess(cp.pace_bonus("先行", ctx), 0)

    def test_neutral_zero(self):
        ctx = cp.PaceContext(front_bias=0, going="良")
        self.assertEqual(cp.pace_bonus("逃げ", ctx), 0.0)


class TestGoingBonus(unittest.TestCase):
    def test_good_wet_record_helps(self):
        apt = sm.GoingAptitude(umaban=1, n=4, best_index=0, avg_finish=2.0, in3_rate=0.75)
        self.assertGreater(cp.going_bonus(apt, "重"), 0)

    def test_poor_wet_record_penalized(self):
        apt = sm.GoingAptitude(umaban=1, n=4, best_index=-5, avg_finish=8.0, in3_rate=0.0)
        self.assertLess(cp.going_bonus(apt, "重"), 0)

    def test_dry_no_going_adjust(self):
        apt = sm.GoingAptitude(umaban=1, n=4, best_index=0, avg_finish=2.0, in3_rate=0.75)
        self.assertEqual(cp.going_bonus(apt, "良"), 0.0)


class TestComposite(unittest.TestCase):
    def test_pace_context_wet_shift(self):
        grid = pace.build_pace_grid([
            (i, [rec(finish_pos=1, corner_pos=[1, 1, 1, 1])]) for i in range(1, 6)
        ])  # 前多数=差し有利(-1)
        dry = cp.PaceContext.from_grid(grid, "良")
        wet = cp.PaceContext.from_grid(grid, "不")
        self.assertLess(dry.front_bias, wet.front_bias)   # 湿走で前有利側へ

    def test_total_sums(self):
        ctx = cp.PaceContext(front_bias=-1, going="良")
        runs = [rec(corner_pos=[7, 7, 6, 5], field_size=12)]   # 差し(c3=6/12=0.5)
        c = cp.composite_index(0.0, runs, ctx, None)
        self.assertEqual(c.style, "差し")
        self.assertGreater(c.total, 0)                    # 差し有利で加点

    def test_no_base_none(self):
        ctx = cp.PaceContext(front_bias=0, going="良")
        c = cp.composite_index(None, [rec()], ctx, None)
        self.assertIsNone(c.total)


if __name__ == "__main__":
    unittest.main()
