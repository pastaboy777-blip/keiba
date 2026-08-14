"""Mの法則ベースの鮮度／硬直指標のテスト。

⚠️ 本家（今井雅宏氏）の理論そのものではなく、公開情報からの独自解釈の実装。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import mhousoku as M


def run(date="2026-07-14", place="大井", distance=1200, jockey="Ａ",
        finish_pos=8, popularity=8, corner_pos=(5,), field_size=10, gate=5):
    return dict(date=date, place=place, distance=distance, jockey=jockey,
                finish_pos=finish_pos, popularity=popularity,
                corner_pos=(list(corner_pos) if corner_pos else None),
                field_size=field_size, gate=gate)


class TestGekiso(unittest.TestCase):
    def test_longshot_in_the_money_is_gekiso(self):
        self.assertTrue(M.is_gekiso(run(finish_pos=3, popularity=9)))

    def test_favourite_winning_is_not_gekiso(self):
        """⚠️ 1着＝激走ではない。1番人気の1着は消耗が違う。"""
        self.assertFalse(M.is_gekiso(run(finish_pos=1, popularity=1)))

    def test_longshot_losing_is_not(self):
        self.assertFalse(M.is_gekiso(run(finish_pos=9, popularity=12)))

    def test_missing_data(self):
        self.assertFalse(M.is_gekiso(run(popularity=None)))


class TestShocks(unittest.TestCase):
    def test_no_history(self):
        self.assertEqual(M.shocks("大井", 1200, "Ａ", 3, 10, None,
                                  "2026-08-14", []), (0.0, []))

    def test_distance_change(self):
        s, t = M.shocks("大井", 1600, "Ａ", 5, 10, None, "2026-08-14",
                        [run(distance=1200, corner_pos=(5,))])
        self.assertTrue(any("延長" in x for x in t))

    def test_big_distance_change_scores_more(self):
        a, _ = M.shocks("大井", 1300, "Ａ", 5, 10, None, "2026-08-14",
                        [run(distance=1200, corner_pos=(5,))])
        b, _ = M.shocks("大井", 1700, "Ａ", 5, 10, None, "2026-08-14",
                        [run(distance=1200, corner_pos=(5,))])
        self.assertGreater(b, a)

    def test_extreme_position_last_time(self):
        """位置取りショックは前走が極端だったことを代理にしている（近似）。"""
        s, t = M.shocks("大井", 1200, "Ａ", 5, 10, None, "2026-08-14",
                        [run(corner_pos=(1,), field_size=10)])
        self.assertTrue(any("位置取り" in x for x in t))

    def test_middle_position_is_no_shock(self):
        s, t = M.shocks("大井", 1200, "Ａ", 5, 10, None, "2026-08-14",
                        [run(corner_pos=(5,), field_size=10)])
        self.assertFalse(any("位置取り" in x for x in t))

    def test_inner_draw_shock_needs_outer_before(self):
        outer = run(gate=12, field_size=14, corner_pos=(5,))
        s, t = M.shocks("大井", 1200, "Ａ", 2, 12, None, "2026-08-14", [outer])
        self.assertTrue(any("内枠" in x for x in t))

    def test_inner_to_inner_is_not_a_shock(self):
        inner = run(gate=1, field_size=14, corner_pos=(5,))
        s, t = M.shocks("大井", 1200, "Ａ", 2, 12, None, "2026-08-14", [inner])
        self.assertFalse(any("内枠" in x for x in t))

    def test_layoff(self):
        s, t = M.shocks("大井", 1200, "Ａ", 5, 10, None, "2026-08-14",
                        [run(date="2026-01-10", corner_pos=(5,))])
        self.assertTrue(any("休み明け" in x for x in t))

    def test_shocks_add_not_multiply(self):
        """「有効なショックが多いほど激走の可能性が上がる」＝足し算。
        1つ欠けたら0、という掛け算にしない。"""
        one = M.shocks("大井", 1600, "Ａ", 5, 10, None, "2026-08-14",
                       [run(distance=1200, corner_pos=(5,))])[0]
        two = M.shocks("大井", 1600, "Ｂ", 5, 10, None, "2026-08-14",
                       [run(distance=1200, corner_pos=(5,))])[0]
        self.assertGreater(two, one)


class TestStiffness(unittest.TestCase):
    def test_needs_two_runs(self):
        self.assertEqual(M.stiffness([run()]), (0.0, []))

    def test_no_gekiso_no_stiffness(self):
        """前走が平凡なら硬直は出ない。"""
        s, r = M.stiffness([run(finish_pos=8, popularity=3)] * 3)
        self.assertEqual(s, 0.0)

    def test_gekiso_creates_stiffness(self):
        """⚠️ **激走そのものが次走の減点材料**。買う材料しか持たない指数は
        ここで必ず外す。"""
        runs = [run(finish_pos=2, popularity=9)] + [run()] * 2
        s, r = M.stiffness(runs)
        self.assertGreater(s, 0)
        self.assertTrue(any("激走" in x for x in r))

    def test_gekiso_after_layoff_is_worse(self):
        plain = M.stiffness([run(finish_pos=2, popularity=9,
                                 date="2026-07-14")]
                            + [run(date="2026-07-01")] * 2)[0]
        after = M.stiffness([run(finish_pos=2, popularity=9,
                                 date="2026-07-14")]
                            + [run(date="2026-01-01")] * 2)[0]
        self.assertGreater(after, plain)

    def test_gekiso_at_odd_distance_is_worse(self):
        same = M.stiffness([run(finish_pos=2, popularity=9, distance=1200)]
                           + [run(distance=1200)] * 3)[0]
        odd = M.stiffness([run(finish_pos=2, popularity=9, distance=1800)]
                          + [run(distance=1200)] * 3)[0]
        self.assertGreater(odd, same)


class TestState(unittest.TestCase):
    def test_empty(self):
        st = M.state("大井", 1200, "Ａ", 3, 10, None, "2026-08-14", [])
        self.assertEqual(st.score, 0.0)

    def test_score_is_fresh_minus_stiff(self):
        st = M.MState(fresh=4.0, stiff=1.5)
        self.assertAlmostEqual(st.score, 2.5)

    def test_stiff_label_wins(self):
        """硬直が出ている馬は、鮮度が高くても消し表示にする。"""
        st = M.MState(fresh=5.0, stiff=3.0)
        self.assertIn("硬直", st.label())

    def test_fresh_label(self):
        self.assertIn("鮮度", M.MState(fresh=4.0).label())

    def test_dull_label(self):
        self.assertIn("変わり映え", M.MState(fresh=0.5).label())


class TestLeg(unittest.TestCase):
    def test_normalised(self):
        self.assertAlmostEqual(M.leg(run(corner_pos=(5,), field_size=10)), 0.5)

    def test_missing(self):
        self.assertIsNone(M.leg(run(corner_pos=None)))


if __name__ == "__main__":
    unittest.main()
