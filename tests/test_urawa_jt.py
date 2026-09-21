"""騎手・調教師・前走で割る（scripts/urawa_jt.py）のテスト。"""

import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "urawa_jt", os.path.join(HERE, "..", "scripts", "urawa_jt.py"))
J = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(J)


class TestJockeyHome(unittest.TestCase):
    def test_splits_name_and_home_track(self):
        """⚠️ 楽天は「櫻井光 (川崎)」の形。**括弧の中が騎手の所属場**で、
        これが「地元か遠征か」の唯一の手がかり。実測では浦和・不良で
        大井の騎手 45.5% 対 地元浦和 23.4% と倍近い差が出る。"""
        self.assertEqual(J.jockey_home("櫻井光 (川崎)"), ("櫻井光", "川崎"))
        self.assertEqual(J.jockey_home("笹川翼 (大井)"), ("笹川翼", "大井"))

    def test_keeps_apprentice_mark(self):
        """⚠️ 見習い印（☆◇△）は落とさない。減量の有無そのものが材料に
        なりうるので、名前に付けたまま残す。"""
        self.assertEqual(J.jockey_home("☆中山遥 (浦和)"), ("☆中山遥", "浦和"))
        self.assertEqual(J.jockey_home("◇中島良 (船橋)"), ("◇中島良", "船橋"))

    def test_missing_bracket(self):
        self.assertEqual(J.jockey_home("名前だけ"), ("名前だけ", "不明"))
        self.assertEqual(J.jockey_home(""), ("", "不明"))
        self.assertEqual(J.jockey_home(None), ("", "不明"))

    def test_empty_bracket(self):
        self.assertEqual(J.jockey_home("誰か ()"), ("誰か", "不明"))


class TestRate(unittest.TestCase):
    def test_zero_denominator(self):
        """0頭のときに割り算で落ちないこと。"""
        self.assertEqual(J.rate([0, 0]), "—")

    def test_formats(self):
        self.assertIn("50.0%", J.rate([5, 10]))
        self.assertIn("5/10", J.rate([5, 10]).replace(" ", ""))


if __name__ == "__main__":
    unittest.main()
