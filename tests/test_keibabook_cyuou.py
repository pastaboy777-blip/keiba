"""中央(JRA)パーサ: レースヘッダ・血統・通過順のテスト（HTML固定・ネット不要）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import keibabook as kb


class TestRaceHeader(unittest.TestCase):
    def test_distance_surface(self):
        html = ('<title>出馬表 | 2026年7月25日中京11R | 競馬ブック</title>'
                '<a>ダ・1200m</a><h2>３歳以上１勝クラス</h2>')
        h = kb.parse_race_header_cyuou(html)
        self.assertEqual(h["surface"], "ダ")
        self.assertEqual(h["distance"], 1200)
        self.assertIn("クラス", h["race_name"])

    def test_turf_fullwidth(self):
        html = '<title>新潟11R</title><span>芝1600m(外)</span>'
        h = kb.parse_race_header_cyuou(html)
        self.assertEqual(h["surface"], "芝")
        self.assertEqual(h["distance"], 1600)


class TestPedigree(unittest.TestCase):
    def test_sire_bms(self):
        html = ('<table><tr><th>父</th><td>'
                '<a href="/db/uma/0682673/sanku">マクフィ</a></td></tr>'
                '<tr><th>母</th><td><a href="/db/uma/1/">フェブノヘア</a></td></tr></table>'
                '<div>母父 ヨハネスブルグ</div>')
        sire, bms = kb.parse_pedigree_cyuou(html)
        self.assertEqual(sire, "マクフィ")
        self.assertEqual(bms, "ヨハネスブルグ")


class TestHistoryCorner(unittest.TestCase):
    def test_corner_pos(self):
        # parse_history が通過順セル(c[15]) を corner_pos に取り込む
        cells = ["2025/06/14", "中京", "良", "1勝", "レース", "12", "8", "3",
                 "5", "", "55", "武豊", "ダ1200", "1.11.6", "0.3", "4 5", "M 36.0"]
        row = "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"
        html = f'<table><tr><th>距離</th><th>タイム</th><th>通過</th></tr>{row}</table>'
        runs = kb.parse_history(html, drop_turf=False)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].corner_pos, [4, 5])
        self.assertEqual(runs[0].surface, "ダ")


if __name__ == "__main__":
    unittest.main()
