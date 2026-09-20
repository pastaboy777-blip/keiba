"""中7週以上あけた馬を拾う（scripts/jra_pick.py）のテスト。"""

import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "jra_pick", os.path.join(HERE, "..", "scripts", "jra_pick.py"))
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)


class TestNaka(unittest.TestCase):
    def test_naka_is_one_less_than_weeks(self):
        """⚠️⚠️ **中N週は N+1週。**中7週＝8週。ここを間違えると境界が1週ズレる。
        実測では 7週以上 +2.6pt(0.71SE) / **8週以上 +4.0pt(1.06SE)**。"""
        self.assertEqual(P.naka(8.0), "中7週")
        self.assertEqual(P.naka(3.0), "中2週")
        self.assertEqual(P.naka(2.0), "中1週")

    def test_renta(self):
        self.assertEqual(P.naka(1.0), "連闘")
        self.assertEqual(P.naka(0.9), "連闘")

    def test_none(self):
        self.assertEqual(P.naka(None), "—")

    def test_threshold_matches_the_label(self):
        """既定の閾値が「中7週以上」と一致していること。"""
        self.assertEqual(P.MIN_WEEKS, P.NAKA_WEEKS + 1)
        self.assertEqual(P.naka(P.MIN_WEEKS), f"中{P.NAKA_WEEKS}週")


class TestSharedConstants(unittest.TestCase):
    def test_area_and_belong_come_from_jra_week(self):
        """⚠️ 地区の表を2か所に書かない。"""
        self.assertEqual(P.W.BELONG["美浦"], "関東")
        self.assertEqual(P.W.BELONG["栗東"], "関西")
        self.assertEqual(P.W.AREA["阪神"], "関西")
        self.assertEqual(P.W.AREA["中山"], "関東")
        # 札幌・函館はどちらのトレセンからも遠いので遠征扱いにしない
        self.assertEqual(P.W.AREA["札幌"], "北")
        self.assertEqual(P.W.AREA["函館"], "北")


if __name__ == "__main__":
    unittest.main()
