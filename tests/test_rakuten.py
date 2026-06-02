"""楽天競馬スクレイパのオフライン検証(ネット不要・bs4 があれば実行)。

HTML/オッズの「純粋ロジック」部分(RACEID抽出・オッズ正規化・結果パース)を
合成フィクスチャで検証する。ライブ取得は環境のネットワーク次第のため対象外。

実行: python3 -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    import bs4  # noqa: F401
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

from nankeiba.scraping import rakuten as R


class TestRaceIdExtract(unittest.TestCase):
    def test_extract_raceids_dedup_and_order(self):
        html = """
        <a href="/race_card/list/RACEID/20240101200101">1R</a>
        <a href="/race_performance/list/RACEID/20240101200102">2R</a>
        <a href="/race_card/list/RACEID/20240101200101">dup</a>
        <a href="/">noid</a>
        """
        self.assertEqual(
            R.extract_raceids(html),
            ["20240101200101", "20240101200102"],
        )


class TestOddsParse(unittest.TestCase):
    def test_trio_sorts_combo(self):
        html = """
        <table>
          <tr><td>3-1-2</td><td>42.5</td></tr>
          <tr><td>5-4-6</td><td>8.1</td></tr>
        </table>
        """
        odds = R.parse_odds_html(html, bet_type="trio")
        self.assertEqual(odds[(1, 2, 3)], 42.5)   # 昇順に正規化
        self.assertEqual(odds[(4, 5, 6)], 8.1)

    def test_trifecta_keeps_order(self):
        html = "<table><tr><td>5-3-8</td><td>123.4</td></tr></table>"
        odds = R.parse_odds_html(html, bet_type="trifecta")
        self.assertIn((5, 3, 8), odds)            # 着順保持
        self.assertNotIn((3, 5, 8), odds)
        self.assertEqual(odds[(5, 3, 8)], 123.4)

    def test_fullwidth_hyphen_and_skip_bad(self):
        html = """
        <table>
          <tr><td>1－2－3</td><td>10.0</td></tr>
          <tr><td>no combo here</td><td>9.9</td></tr>
          <tr><td>7-8-9</td><td>0</td></tr>
        </table>
        """
        odds = R.parse_odds_html(html, bet_type="trio")
        self.assertEqual(odds[(1, 2, 3)], 10.0)   # 全角ハイフン許容
        self.assertNotIn((7, 8, 9), odds)         # オッズ<=0 は除外


@unittest.skipUnless(HAS_BS4, "beautifulsoup4 未導入")
class TestResultParse(unittest.TestCase):
    HTML = """
    <html><body>
      <div class="raceData">2024年1月8日 大井 ダ1400m</div>
      <table>
        <tr><th>着</th><th>馬番</th><th>馬名</th><th>騎手</th></tr>
        <tr><td>2</td><td>7</td>
            <td><a href="/horse/H222/">ウマB</a></td>
            <td><a href="/jockey/J9/">騎手B</a></td></tr>
        <tr><td>1</td><td>3</td>
            <td><a href="/horse/H111/">ウマA</a></td>
            <td><a href="/jockey/J1/">騎手A</a></td></tr>
        <tr><td>除外</td><td>5</td><td>ウマC</td><td>騎手C</td></tr>
      </table>
    </body></html>
    """

    def test_parse_result(self):
        race = R.parse_result_page(self.HTML, "20240108200111")
        self.assertEqual(race.race_id, "20240108200111")
        self.assertEqual(race.date, "2024-01-08")
        self.assertEqual(race.place, "大井")
        self.assertEqual(race.distance, 1400)
        self.assertEqual(race.field_size, 2)            # 「除外」行は除外
        self.assertEqual([r.finish_pos for r in race.rows], [1, 2])  # 着順ソート
        winner = race.rows[0]
        self.assertEqual(winner.umaban, 3)
        self.assertEqual(winner.horse_id, "H111")
        self.assertEqual(winner.horse_name, "ウマA")
        self.assertEqual(winner.jockey, "騎手A")


class TestConfig(unittest.TestCase):
    def test_nankan_codes_and_urls(self):
        self.assertEqual(set(R.NANKAN_CODES), {"浦和", "船橋", "大井", "川崎"})
        self.assertIn("RACEID/RID", R.result_url("RID"))
        self.assertIn("sanrenpuku", R.odds_url("RID", "trio"))
        self.assertIn("sanrentan", R.odds_url("RID", "trifecta"))


if __name__ == "__main__":
    unittest.main()
