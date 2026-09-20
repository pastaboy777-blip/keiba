"""中島理論の磁場（scripts/nankan_jiba.py）のテスト。"""

import datetime as dt
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "nankan_jiba", os.path.join(HERE, "..", "scripts", "nankan_jiba.py"))
J = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(J)


class Run:
    """RunRecord の最小の代用。"""

    def __init__(self, date, place, finish_pos=1):
        self.date, self.place, self.finish_pos = date, place, finish_pos


class TestLon(unittest.TestCase):
    def test_jra_prefix_is_stripped(self):
        """⚠️ 楽天は中央を「Ｊ阪神」と全角Ｊ付きで書く。剥がさないと表に
        当たらず、**西日本の中央帰りが丸ごと該当なしに落ちる**。"""
        self.assertEqual(J.lon("Ｊ阪神"), J.lon("阪神"))
        self.assertEqual(J.lon("Ｊ中京"), J.lon("中京"))
        self.assertIsNotNone(J.lon("Ｊ京都"))

    def test_unknown_place(self):
        self.assertIsNone(J.lon("ばんえい帯広ナイター"))
        self.assertIsNone(J.lon(None))


class TestSameField(unittest.TestCase):
    def test_nankan_is_one_field(self):
        """**南関4場は中島氏の定義で丸ごと一つの磁場。**内部移動は無意味。"""
        for p in ("川崎", "船橋", "浦和"):
            self.assertTrue(J.same_field("大井", p), p)
        spread = max(J.LON[p] for p in ("大井", "川崎", "船橋", "浦和")) \
            - min(J.LON[p] for p in ("大井", "川崎", "船橋", "浦和"))
        self.assertLess(spread, 0.4)

    def test_west_is_another_field(self):
        for p in ("栗東", "京都", "阪神", "園田", "高知", "佐賀", "中京", "名古屋"):
            self.assertFalse(J.same_field("大井", p), p)

    def test_mombetsu_sits_just_outside(self):
        """⚠️ 門別は南関への移籍元として最も多いのに、**境界から0.26度の外**。
        座標の取り方で判定が裏返る急所。"""
        d = J.gap("門別", "大井")
        self.assertFalse(J.same_field("門別", "大井"))
        self.assertLess(d - J.SAME_FIELD_DEG, J.NEAR_EDGE)

    def test_unknown_returns_none(self):
        self.assertIsNone(J.same_field("大井", "ドバイ"))


class TestBand(unittest.TestCase):
    def test_three_bands(self):
        self.assertEqual(J.band(0.0), "元の磁場が続く")
        self.assertEqual(J.band(7.0), "元の磁場が続く")
        self.assertEqual(J.band(7.1), "順応の途中")
        self.assertEqual(J.band(26.0), "順応の途中")
        self.assertEqual(J.band(26.1), "順応済み")


class TestFieldState(unittest.TestCase):
    TODAY = dt.date(2026, 9, 18)

    def test_detects_crossing(self):
        runs = [Run("2026-06-04", "門別"), Run("2026-09-01", "大井")]
        st = J.field_state(runs, "大井", self.TODAY)
        self.assertEqual(st["crossed"]["from"], "門別")
        self.assertEqual(st["crossed"]["to_date"], "2026-09-01")
        self.assertAlmostEqual(st["weeks"], 17 / 7.0, places=2)
        self.assertEqual(J.band(st["weeks"]), "元の磁場が続く")

    def test_transfer_debut(self):
        """近5走すべて別磁場＝当磁場では今回が初戦。滞在0週。"""
        runs = [Run("2026-03-22", "Ｊ阪神"), Run("2026-08-08", "Ｊ中京")]
        st = J.field_state(runs, "大井", self.TODAY)
        self.assertTrue(st["first"])
        self.assertEqual(st["weeks"], 0.0)
        self.assertIsNone(st["crossed"]["to_date"])

    def test_never_crossed_is_a_lower_bound(self):
        """⚠️ 馬柱は近5走しか無い。移動が範囲外なら weeks は**下限**でしかない。"""
        runs = [Run("2026-05-02", "大井"), Run("2026-09-10", "川崎")]
        st = J.field_state(runs, "大井", self.TODAY)
        self.assertIsNone(st["crossed"])
        self.assertTrue(st["lower"])
        self.assertFalse(st["foreign"])

    def test_long_gap_is_flagged_unknown(self):
        """⚠️ 7週超の空白は「どこで暮らしたか分からない」。放牧先は馬柱に無い。
        これが磁場論の最大の穴で、埋められないことを出力に残す。"""
        runs = [Run("2026-01-30", "大井"), Run("2026-08-14", "大井")]
        st = J.field_state(runs, "大井", self.TODAY)
        self.assertTrue(st["unknown"])
        self.assertGreater(st["unknown"][0]["weeks"], J.OLD_FIELD_WEEKS)

    def test_no_known_place(self):
        st = J.field_state([Run("2026-09-01", "ドバイ")], "大井", self.TODAY)
        self.assertIsNone(st["weeks"])


if __name__ == "__main__":
    unittest.main()
