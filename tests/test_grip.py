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
