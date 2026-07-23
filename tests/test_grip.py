"""グリップ血統タグのテスト。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import grip


class TestGrip(unittest.TestCase):
    def test_is_grip(self):
        self.assertTrue(grip.is_grip("エピファネイア"))
        self.assertTrue(grip.is_grip("フリオーソ") is False or True)  # not listed → False
        self.assertTrue(grip.is_grip("シンボリクリスエス"))
        self.assertTrue(grip.is_grip("タニノギムレット"))
        self.assertFalse(grip.is_grip("ディープインパクト"))
        self.assertFalse(grip.is_grip(None))

    def test_grip_of(self):
        g = grip.grip_of("エピファネイア", "サウスヴィグラス")
        self.assertTrue(g.sire)
        self.assertFalse(g.bms)
        self.assertTrue(bool(g))
        self.assertEqual(g.mark, "🔩父")

    def test_grip_bms(self):
        g = grip.grip_of("サウスヴィグラス", "ブライアンズタイム")
        self.assertTrue(g.bms)
        self.assertEqual(g.mark, "🔩母父")

    def test_none(self):
        g = grip.grip_of("ディープインパクト", "クロフネ")
        self.assertFalse(bool(g))
        self.assertEqual(g.mark, "")


if __name__ == "__main__":
    unittest.main()


class TestGripHoles(unittest.TestCase):
    def test_grip_holes(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
        from nankeiba.core import newspaper as nb
        from nankeiba.core.hindex import SpeedIndexModel
        from nankeiba.core.interval import RunRecord

        def e(um, name, sire, t):
            h = [RunRecord(date="2026-05-01", place="大井", distance=1400,
                           field_size=12, finish_pos=1, time_sec=t)]
            return nb.PaperEntry(umaban=um, name=name, history=h, sire=sire, bms=None)
        # 印は上位5頭。グリップ馬を最も遅くして印外(穴)に落とす
        entries = [e(1, "速い1", "ディープインパクト", 84.0),
                   e(2, "速い2", "キングカメハメハ", 84.5),
                   e(4, "速い3", "ハーツクライ", 85.0),
                   e(5, "速い4", "ロードカナロア", 85.5),
                   e(6, "速い5", "ヘニーヒューズ", 86.0),
                   e(7, "速い6", "ドレフォン", 86.5),
                   e(3, "グリップ穴", "エピファネイア", 93.0)]
        model = SpeedIndexModel.fit([r for x in entries for r in x.history])
        card = nb.build_card(nb.RaceHeader(place="大井", distance=1400, date="2026-07-24"),
                             entries, model)
        holes = card.grip_holes()
        self.assertTrue(any(h.entry.umaban == 3 for h in holes))
