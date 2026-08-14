"""中央の成績ページ「レース単位の詳細」パーサのテスト（BT値の入力）。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import keibabook as kb

HTML = """
<div class="section">
 <table class="default seiseki-etc"><caption>コーナー通過順</caption><tbody>
  <tr><th>３　角</th><td>3(14.9)(8.2)-1</td></tr>
  <tr><th>４　角</th><td>9.3-2-5(14.7.15)4.8-1</td></tr>
 </tbody></table>
 <table class="default seiseki-etc"><caption>平均ハロンなど</caption><tbody>
  <tr><th>平均ハロン</th><td>12.58</td></tr>
  <tr><th>上り</th><td>52.8-39.9</td></tr>
  <tr><th>ペース</th><td>ハイ</td></tr>
  <tr><th>決め手</th><td>１着馬:Ｇ前出　２着馬:中位伸　</td></tr>
  <tr><th>発走状況他</th><td>(4)(5)出遅れ１馬身不利　(11)アオル２馬身不利
   (7)スタート直後躓く半馬身不利 (3)３角寄られる不利 (12)４角競走中止
   (9)出遅れ１秒以上大きな不利</td></tr>
 </tbody></table>
 <table class="default seiseki-tuka"><caption>通過タイム</caption><tbody>
  <tr><th>600m</th><th>800m</th></tr><tr><td>35.1</td><td>47.6</td></tr>
 </tbody></table>
 <table class="default seiseki-tuka"><caption>ラップタイム</caption><tbody>
  <tr><th>100m</th><th>300m</th><th>500m</th></tr>
  <tr><td>7.2</td><td>10.8</td><td>11.0</td></tr>
 </tbody></table>
</div>
"""


class TestCornerOrder(unittest.TestCase):
    def test_rank_and_ties(self):
        p = kb.parse_corner_order("9.3-2-5(14.7.15)4.8-1")
        self.assertEqual(p[9], 1)
        self.assertEqual(p[3], 2)
        self.assertEqual(p[5], 4)

    def test_bracket_is_same_rank(self):
        """括弧は横並び＝同順。次はその頭数ぶん飛ばす。"""
        p = kb.parse_corner_order("9.3-2-5(14.7.15)4.8")
        self.assertEqual(p[14], p[7])
        self.assertEqual(p[7], p[15])
        self.assertEqual(p[4], p[15] + 3)

    def test_empty(self):
        self.assertEqual(kb.parse_corner_order(None), {})
        self.assertEqual(kb.parse_corner_order(""), {})


class TestIncidents(unittest.TestCase):
    def setUp(self):
        self.inc = {x["umaban"]: x for x in kb.parse_incidents(
            "(4)(5)出遅れ１馬身不利　(11)アオル２馬身不利 "
            "(7)スタート直後躓く半馬身不利 (3)３角寄られる不利 "
            "(12)４角競走中止 (9)出遅れ１秒以上大きな不利")}

    def test_shared_entry_splits_per_horse(self):
        """(4)(5)…のように複数馬にかかる記述は馬ごとにばらす。"""
        self.assertEqual(self.inc[4]["lengths"], 1.0)
        self.assertEqual(self.inc[5]["lengths"], 1.0)

    def test_half_length(self):
        self.assertEqual(self.inc[7]["lengths"], 0.5)

    def test_fullwidth_digits(self):
        """⚠️ 文字クラスで漢数字の範囲を書くとひらがなを含む。実際
        『出遅れ１馬身』から『れ１馬身』を掴んで None になっていた。"""
        self.assertEqual(self.inc[11]["lengths"], 2.0)

    def test_phase_start_vs_mid(self):
        self.assertEqual(self.inc[4]["phase"], "start")
        self.assertEqual(self.inc[11]["phase"], "start")
        self.assertEqual(self.inc[3]["phase"], "mid")

    def test_retired(self):
        self.assertEqual(self.inc[12]["phase"], "stop")

    def test_severe_without_lengths(self):
        """馬身に換算されていない不利は severe で立てる（0扱いにしない）。"""
        self.assertTrue(self.inc[9]["severe"])
        self.assertIsNone(self.inc[9]["lengths"])

    def test_empty(self):
        self.assertEqual(kb.parse_incidents(None), [])
        self.assertEqual(kb.parse_incidents(""), [])


class TestResultDetail(unittest.TestCase):
    def setUp(self):
        self.d = kb.parse_result_detail_cyuou(HTML)

    def test_sectionals_pair_header_with_value(self):
        self.assertEqual(self.d["sectionals"], {600: 35.1, 800: 47.6})

    def test_laps_handle_odd_headers(self):
        """⚠️ 見出しはレースごとに違う（半端距離は 100/300/500…）。
        位置決め打ちにしないこと。"""
        self.assertEqual(self.d["laps"], {100: 7.2, 300: 10.8, 500: 11.0})

    def test_corner_positions_by_number(self):
        self.assertEqual(self.d["corner_pos"][4][9], 1)
        self.assertIn(3, self.d["corner_pos"])

    def test_misc(self):
        self.assertAlmostEqual(self.d["avg_furlong"], 12.58)
        self.assertAlmostEqual(self.d["agari4f"], 52.8)
        self.assertAlmostEqual(self.d["agari3f"], 39.9)
        self.assertEqual(self.d["pace"], "ハイ")

    def test_incidents_included(self):
        self.assertTrue(self.d["incidents"])

    def test_missing_tables_are_safe(self):
        d = kb.parse_result_detail_cyuou("<html></html>")
        self.assertEqual(d["sectionals"], {})
        self.assertEqual(d["incidents"], [])
        self.assertIsNone(d["avg_furlong"])


if __name__ == "__main__":
    unittest.main()
