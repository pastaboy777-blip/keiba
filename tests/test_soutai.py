"""相対の3層（レース内・位置・展開）のテスト。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import soutai as S


def h(name, agari, c4, fld=10, finish=5, pop=5):
    return dict(name=name, agari=agari, corner4=c4, field_size=fld,
                finish=finish, popularity=pop)


class TestPosBand(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(S.pos_band(2, 10), "前")
        self.assertEqual(S.pos_band(5, 10), "中")
        self.assertEqual(S.pos_band(9, 10), "後")

    def test_missing(self):
        self.assertIsNone(S.pos_band(None, 10))
        self.assertIsNone(S.pos_band(3, None))


class TestExpected(unittest.TestCase):
    def test_front_is_faster_only_when_flow_is_easy(self):
        """⚠️ 「後方は上がりが速くて当たり前」は**前が止まったときだけ**。
        前が楽な流れでは後方はむしろ遅い（+0.31）。展開で層別しないと
        この構造が消える（プールすると前25%が-0.18になり逆の結論が出る）。"""
        self.assertLess(S.EXPECTED[("前", "楽")], 0)
        self.assertGreater(S.EXPECTED[("前", "止")], 0)
        self.assertGreater(S.EXPECTED[("後", "楽")], 0)
        self.assertLess(S.EXPECTED[("後", "止")], 0)

    def test_position_effect_reverses_with_flow(self):
        self.assertGreater(S.EXPECTED[("後", "楽")], S.EXPECTED[("前", "楽")])
        self.assertLess(S.EXPECTED[("後", "止")], S.EXPECTED[("前", "止")])


class TestAnalyse(unittest.TestCase):
    def setUp(self):
        # 7/22 大井（提示された実データ・9頭）
        self.r = [h("トーキングザゴッド", 37.3, 3, 9, 1, 1),
                  h("ライドハイ", 38.4, 1, 9, 2, 2),
                  h("マッシブショット", 38.3, 2, 9, 3, 7),
                  h("スタールビーピアス", 38.2, 4, 9, 4, 3),
                  h("ジューンアカデミー", 37.9, 9, 9, 5, 8),
                  h("トコシエノヒトミ", 38.1, 6, 9, 6, 4),
                  h("オロールシェール", 39.2, 4, 9, 7, 6),
                  h("ナポレオンバディ", 38.7, 8, 9, 8, 9),
                  h("トゥモローズウェイ", 40.6, 6, 9, 9, 5)]

    def test_mean_agari(self):
        rr, _ = S.analyse(self.r)
        self.assertAlmostEqual(rr.mean_agari, 38.52, places=2)

    def test_diff_matches_hand_calculation(self):
        _, hs = S.analyse(self.r)
        d = {x.name: x.diff for x in hs}
        self.assertAlmostEqual(d["トーキングザゴッド"], -1.22, places=2)
        self.assertAlmostEqual(d["ジューンアカデミー"], -0.62, places=2)
        self.assertAlmostEqual(d["ライドハイ"], -0.12, places=2)

    def test_flow_detected_from_front_runners(self):
        """⚠️ ③はラップやペース記号ではなく、**実際に前にいた馬の上がり**で測る。
        前が止まったかどうかは前にいた馬の結果にしか現れない。"""
        rr, _ = S.analyse(self.r)
        self.assertEqual(rr.flow, "楽")

    def test_residual_reranks(self):
        """同じ -0.62 でも、後方から出したほうが濃い。"""
        _, hs = S.analyse(self.r)
        d = {x.name: x.residual for x in hs}
        self.assertAlmostEqual(d["ジューンアカデミー"], -0.93, places=2)
        self.assertGreater(d["ライドハイ"], d["ジューンアカデミー"])

    def test_sorted_by_residual(self):
        _, hs = S.analyse(self.r)
        self.assertEqual(hs[0].name, "トーキングザゴッド")
        self.assertEqual(hs[1].name, "ジューンアカデミー")

    def test_too_few_runners(self):
        rr, hs = S.analyse([h("a", 38.0, 1, 3)])
        self.assertEqual(hs, [])


class TestTarget(unittest.TestCase):
    def test_the_shape(self):
        """前が楽な流れで、後方から濃い脚を使ったのに着外だった馬。"""
        r = [h("逃げ", 38.4, 1, 9, 2), h("差し", 37.9, 9, 9, 5, 8),
             h("a", 38.3, 2, 9, 3), h("b", 38.2, 4, 9, 4),
             h("c", 39.2, 5, 9, 7), h("d", 38.7, 8, 9, 8)]
        rr, hs = S.analyse(r)
        got = [x.name for x in hs if S.target(rr, x)[0]]
        self.assertIn("差し", got)

    def test_front_stopped_is_not_a_target(self):
        """⚠️ 前が止まった流れで後方から速い上がり、は狙いではない。
        位置が向いただけで期待値どおり。"""
        rr = S.RaceRelative(mean_agari=39.0, front_diff=+0.5, n=10)
        x = S.HorseRelative(name="x", agari=38.5, diff=-0.5, band="後",
                            expected=-0.23, residual=-0.27, finish=6)
        self.assertFalse(S.target(rr, x)[0])

    def test_front_runner_is_not_a_target(self):
        rr = S.RaceRelative(mean_agari=39.0, front_diff=-0.3, n=10)
        x = S.HorseRelative(name="x", agari=38.0, diff=-1.0, band="前",
                            expected=-0.59, residual=-0.41, finish=6)
        self.assertFalse(S.target(rr, x)[0])

    def test_placed_horse_is_not_a_target(self):
        """着順に出てしまった馬は人気になるので狙いではない。"""
        rr = S.RaceRelative(mean_agari=39.0, front_diff=-0.3, n=10)
        x = S.HorseRelative(name="x", agari=38.0, diff=-1.0, band="後",
                            expected=+0.31, residual=-1.31, finish=2)
        self.assertFalse(S.target(rr, x)[0])


if __name__ == "__main__":
    unittest.main()
