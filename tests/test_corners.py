"""`rakuten.parse_corners` / `corner4` のテスト。

⚠️ **`parse_result` は通過順を持っていない。**結果の行にあるのは着順・タイム・
   推定上がり・人気だけで、コーナー通過順は本文の別ブロックにある。これを
   拾い忘れて、川崎の不良・重 146レースが全部「決着傾向は測れない」になった。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import rakuten as rk

# 実ページの該当ブロックをそのまま縮めたもの（タグ入り・全角見出し）。
HTML = (
    "<p>■ <b>コーナー通過順位</b><br>"
    "向正面 10,5,12,3,1,4,2,8,9,7,11,6<br>"
    "３角 5,(10,12),(3,4),1,(2,9),11,(6,8),7<br>"
    "４角 10,5,1,3,12,2,4,(6,9),8,11,7</p>"
    "<p>■ 払戻金 単勝 5 130円</p>"
)


class ParseCornersTest(unittest.TestCase):
    def setUp(self):
        self.c = rk.parse_corners(HTML)

    def test_labels(self):
        self.assertEqual(sorted(self.c), ["3角", "4角", "向正面"])

    def test_simple_order(self):
        """括弧の無い列はそのまま1位から。"""
        self.assertEqual(self.c["向正面"][10], 1)
        self.assertEqual(self.c["向正面"][5], 2)
        self.assertEqual(self.c["向正面"][6], 12)

    def test_bracket_is_same_rank(self):
        """⚠️ 括弧は横並び＝**同順**。着順ではない（並びは内→外）。"""
        self.assertEqual(self.c["4角"][6], 8)
        self.assertEqual(self.c["4角"][9], 8)

    def test_rank_skips_by_group_size(self):
        """⚠️ 同順のあとは**その頭数ぶん飛ばす**。8が9位になってはいけない。"""
        self.assertEqual(self.c["4角"][8], 10)
        self.assertEqual(self.c["4角"][11], 11)
        self.assertEqual(self.c["4角"][7], 12)

    def test_nested_brackets_in_third(self):
        self.assertEqual(self.c["3角"][5], 1)
        self.assertEqual(self.c["3角"][10], 2)
        self.assertEqual(self.c["3角"][12], 2)
        self.assertEqual(self.c["3角"][3], 4)
        self.assertEqual(self.c["3角"][4], 4)
        self.assertEqual(self.c["3角"][1], 6)

    def test_every_horse_appears_once(self):
        self.assertEqual(len(self.c["4角"]), 12)

    def test_corner4_prefers_last_corner(self):
        self.assertEqual(rk.corner4(HTML), self.c["4角"])

    def test_corner4_falls_back_to_third(self):
        """4角が無ければ3角。⚠️ **無いものを0で埋めない。**"""
        h = ("■ コーナー通過順位 ３角 2,1,3 ■ 払戻金")
        self.assertEqual(rk.corner4(h), {2: 1, 1: 2, 3: 3})

    def test_no_corners_returns_empty(self):
        """川崎900mのようにコーナーが無いレースがある。空を返すこと。"""
        self.assertEqual(rk.parse_corners("<p>■ 払戻金 単勝 5 130円</p>"), {})
        self.assertEqual(rk.corner4("<p>なにもない</p>"), {})


if __name__ == "__main__":
    unittest.main()
