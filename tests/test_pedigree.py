"""大系統(血統ビーム)のテスト。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import pedigree as ped


class TestClassify(unittest.TestCase):
    def test_known(self):
        self.assertEqual(ped.classify("ゴールドアリュール"), "sunday")
        self.assertEqual(ped.classify("サウスヴィグラス"), "mrprospector")
        self.assertEqual(ped.classify("フリオーソ"), "turnto")
        self.assertEqual(ped.classify("シニスターミニスター"), "nasrullah")
        self.assertEqual(ped.classify("クロフネ"), "northern")

    def test_fullwidth_alnum(self):
        self.assertEqual(ped.classify("Ｔｉｚｎｏｗ"), "matchem")

    def test_unknown(self):
        self.assertIsNone(ped.classify("存在しない種牡馬XYZ"))
        self.assertIsNone(ped.classify(None))


    def test_expanded_sires(self):
        # 2026-07 拡充分の主要種牡馬
        self.assertEqual(ped.classify("シャンハイボビー"), "northern")
        self.assertEqual(ped.classify("レッドファルクス"), "mrprospector")
        self.assertEqual(ped.classify("マクフィ"), "mrprospector")
        self.assertEqual(ped.classify("ロードカナロア"), "mrprospector")
        self.assertEqual(ped.classify("ワールドエース"), "sunday")
        self.assertEqual(ped.classify("クリエイター２"), "nasrullah")   # 全角数字
        self.assertEqual(ped.classify("Ｂｅｒｎａｒｄｉｎｉ"), "nasrullah")  # 全角英字

    def test_5keys(self):
        self.assertEqual(set(ped.KEY5),
                         {"northern", "sunday", "mrprospector", "turnto", "nasrullah"})


class TestBias(unittest.TestCase):
    def _tags(self):
        entries = [
            (1, "ディープインパクト", "サウスヴィグラス"),   # 父サンデー
            (2, "サウスヴィグラス", "クロフネ"),           # 父ミスプロ
            (3, "フリオーソ", "ダイワメジャー"),           # 母父サンデー
            (4, "存在しない", None),                       # 不明
        ]
        return ped.tag_entries(entries)

    def test_tag(self):
        t = self._tags()
        self.assertEqual(t[1].sire_sys, "sunday")
        self.assertTrue(t[1].is_sunday_line)
        self.assertTrue(t[3].is_sunday_line)     # 母父サンデー
        self.assertIsNone(t[4].sire_sys)

    def test_bias(self):
        b = ped.bias_of(self._tags())
        self.assertEqual(b.total, 4)
        self.assertEqual(b.sunday_line, 2)       # 1(父) と 3(母父)
        self.assertIn("sunday", b.counts)

    def test_track_read_dirt(self):
        # サンデー系少→通常ダート
        b = ped.PedBias(counts={"mrprospector": 8}, sunday_line=1, total=8)
        self.assertIn("パワー", b.track_read("ダ"))
        # サンデー系多→特殊ダート
        b2 = ped.PedBias(counts={"sunday": 6}, sunday_line=6, total=8)
        self.assertIn("特殊", b2.track_read("ダ"))


if __name__ == "__main__":
    unittest.main()
