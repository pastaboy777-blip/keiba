"""楽天競馬パーサのテスト(ネットワーク不要・固定文字列)。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import rakuten as rk


class TestParseRun(unittest.TestCase):
    def test_basic(self):
        cell = ("9 良 9頭 過去映像 船橋 25.08.27 フリオーソレ ４上 1800左ダ 8人 "
                "藤田凌 56.0 1:57.2 (6.1) 40.4 526k 4番 6-6-8-9 サントノーレ")
        r = rk._parse_run(cell)
        self.assertIsNotNone(r)
        self.assertEqual(r.date, "2025-08-27")
        self.assertEqual(r.place, "船橋")
        self.assertEqual(r.distance, 1800)
        self.assertEqual(r.finish_pos, 9)
        self.assertEqual(r.field_size, 9)
        self.assertEqual(r.baba, "良")
        self.assertEqual(r.time_sec, 117.2)
        self.assertEqual(r.last3f_sec, 40.4)
        self.assertEqual(r.corner_pos, [6, 6, 8, 9])

    def test_three_corner(self):
        cell = ("4 良 8頭 過去映像 大井 25.07.03 ジュライ賞競 ３上 外1400右ダ 3人 "
                "矢野貴 56.0 1:26.7 (1.9) 39.4 525k 2番 1-1-2 サトノテンペ")
        r = rk._parse_run(cell)
        self.assertEqual(r.distance, 1400)
        self.assertEqual(r.time_sec, 86.7)
        self.assertEqual(r.corner_pos, [1, 1, 2])

    def test_turf_excluded(self):
        cell = ("1 良 12頭 過去映像 東京 25.06.01 ○○S ３上 芝1600左芝 5人 "
                "武豊 55.0 1:33.5 (0.2) 34.0 480k 3番 5-5 △△")
        self.assertIsNone(rk._parse_run(cell))

    def test_time_to_sec(self):
        self.assertEqual(rk._time_to_sec("1:45.8"), 105.8)
        self.assertEqual(rk._time_to_sec("59.3"), None)      # 分:秒.10 形式のみ

    def test_parse_card_minimal(self):
        html = """<title>大井競馬場 出馬表 | 2026/07/22 11R ：楽天競馬</title>
        <span class="distance"> ダ1,600m(内)</span>
        <table><tr>
          <td>1</td>
          <td><a href="/horse_detail/detail/HORSEID/999">テスト馬</a></td>
          <td>9 良 9頭 過去映像 船橋 25.08.27 レース ４上 1800左ダ 8人 騎手 56.0 1:57.2 (6.1) 40.4 526k 4番 6-6-8-9 相手</td>
        </tr></table>"""
        card = rk.parse_card(html)
        self.assertEqual(card["header"]["place"], "大井")
        self.assertEqual(card["header"]["race_no"], 11)
        self.assertEqual(card["header"]["distance"], 1600)
        self.assertEqual(len(card["entries"]), 1)
        e = card["entries"][0]
        self.assertEqual(e["umaban"], 1)
        self.assertEqual(e["name"], "テスト馬")
        self.assertEqual(len(e["history"]), 1)
        self.assertEqual(e["history"][0].corner_pos, [6, 6, 8, 9])


class TestFetchCardRefetch(unittest.TestCase):
    """発売前の空の出馬表がキャッシュに残っていたら取り直す。"""

    def test_refetches_when_no_entries(self):
        from nankeiba.scraping.rakuten import fetch_card

        real = ('<title>川崎競馬場 1R</title>'
                '<span class="distance">ダ1,400m</span>'
                '<table class="dataTable"><tr><td>1</td><td>1</td>'
                '<td><a href="/horse/1">ウマ</a></td></tr></table>')

        class Cli:
            def __init__(self):
                self.calls = []

            def get(self, path, *, use_cache=True):
                self.calls.append(use_cache)
                return "<html>空</html>" if use_cache else real

        c = Cli()
        card = fetch_card(c, "20260727000000000001")
        self.assertEqual(c.calls, [True, False])       # 2回目はキャッシュ無視
        self.assertEqual(card["header"]["distance"], 1400)

    def test_no_refetch_when_entries_exist(self):
        from nankeiba.scraping.rakuten import fetch_card, parse_card

        html = open("tests/data/rakuten_card.html", encoding="utf-8").read() \
            if os.path.exists("tests/data/rakuten_card.html") else None
        if html is None or not parse_card(html)["entries"]:
            self.skipTest("出馬表のフィクスチャが無い")

        class Cli:
            def __init__(self):
                self.calls = []

            def get(self, path, *, use_cache=True):
                self.calls.append(use_cache)
                return html

        c = Cli()
        fetch_card(c, "x")
        self.assertEqual(c.calls, [True])


if __name__ == "__main__":
    unittest.main()


class TestWeight(unittest.TestCase):
    def test_weight_captured(self):
        from nankeiba.scraping.rakuten import _parse_run
        cell = ("9 良 9頭 過去映像 船橋 25.08.27 フリオーソレ ４上 1800左ダ "
                "8人 藤田凌 56.0 1:57.2 (6.1) 40.4 526k 4番 6-6-8-9 サントノーレ")
        r = _parse_run(cell)
        self.assertIsNotNone(r)
        self.assertEqual(r.weight, 526)
        self.assertEqual(r.distance, 1800)


class TestParseBaba(unittest.TestCase):
    """当日馬場は天候アンカーで取る（馬体重・過去走馬場を誤爆しない）。"""

    def test_picks_today_baba(self):
        html = '<div>天候：晴　<span>ダ：稍重</span></div><td>馬体重 480(+2)</td>'
        self.assertEqual(rk.parse_baba(html), "稍重")

    def test_not_fooled_by_weight_or_history(self):
        # 「馬体重」の重や馬柱の過去走馬場('重')があっても、当日の良を返す
        html = ('<td>馬体重</td><td>川崎ダ1400 重 ①着</td>'
                '<div>天候：曇 ダ：良</div><td>体重 502kg</td>')
        self.assertEqual(rk.parse_baba(html), "良")

    def test_none_when_absent(self):
        self.assertIsNone(rk.parse_baba('<td>馬体重 480</td><td>重</td>'))


class TestCardEntryProfile(unittest.TestCase):
    """出馬表から 性齢・騎手・誕生日・オッズ を拾えるか。

    ⚠️ ここは長らく拾っていなかった。「ズブさ」を見るのに年齢が、
       「乗り替わり」を見るのに騎手が要る（2026-08-03 の船橋で必要になった）。
    ⚠️ オッズ・人気は**発売前は "-（-人気）"** なので None になる。
       前日夜に取ると必ず None。当日の発売後に取り直すこと。
    """

    ROW = """
    <table><tr>
      <td>1</td><td>1</td>
      <td>アメリカンペイトリオッ</td>
      <td><a href="/horse_detail/detail/HORSEID/2820260044">クシナダヒメ</a></td>
      <td>カナワン (エピファネイア)</td>
      <td>{odds}</td>
      <td>2024/4/23生</td><td>大久保秀一</td><td>富田恭司生産</td>
      <td>牝2</td><td>青鹿毛</td><td>54.0</td><td>野澤憲</td><td>（船 橋）</td>
      <td>佐々清</td>
    </tr></table>
    """

    def _one(self, odds="-（-人気）"):
        html = ("<title>船橋競馬場 出馬表 | 2026/08/03 1R</title>"
                + self.ROW.format(odds=odds))
        e = rk.parse_card(html)["entries"]
        self.assertEqual(len(e), 1)
        return e[0]

    def test_sex_age(self):
        e = self._one()
        self.assertEqual(e["sex_age"], "牝2")
        self.assertEqual(e["age"], 2)

    def test_jockey_and_kinryo(self):
        e = self._one()
        self.assertEqual(e["jockey"], "野澤憲")
        self.assertEqual(e["kinryo"], 54.0)

    def test_birth(self):
        self.assertEqual(self._one()["birth"], "2024-04-23")

    def test_odds_is_none_before_sale(self):
        """発売前は '-（-人気）'。0 や 1番人気に化けないこと。"""
        e = self._one()
        self.assertIsNone(e["odds"])
        self.assertIsNone(e["popularity"])

    def test_odds_after_sale(self):
        e = self._one(odds="5.9（2人気）")
        self.assertEqual(e["odds"], 5.9)
        self.assertEqual(e["popularity"], 2)

    def test_existing_fields_untouched(self):
        e = self._one()
        self.assertEqual(e["umaban"], 1)
        self.assertEqual(e["name"], "クシナダヒメ")
        self.assertEqual(e["horseid"], "2820260044")


class ParsePlacePayoutTest(unittest.TestCase):
    """複勝の払戻（馬番 → 円）。2026-08-16 大井7R の実データ。"""

    HTML = ("<p>４角 (3,7,10)-6 ■ 払戻金 単勝 8 4,760 円 9番人気 "
            "馬単 8-3 65,660 円 72番人気 "
            "複勝 8 3 11 1,170 円 240 円 270 円 9番人気 3番人気 4番人気 "
            "ワイド 3-8 8-11 3-11 3,640 円 4,780 円 780 円</p>")

    def test_three(self):
        self.assertEqual(rk.parse_place_payout(self.HTML),
                         {8: 1170, 3: 240, 11: 270})

    def test_two_horses(self):
        """7頭以下は複勝が2頭ぶんしか無い。金額と取り違えないこと。"""
        h = "複勝 5 2 310 円 150 円 3番人気 1番人気 ワイド 2-5 900 円"
        self.assertEqual(rk.parse_place_payout(h), {5: 310, 2: 150})

    def test_missing(self):
        self.assertEqual(rk.parse_place_payout("<p>払戻金 単勝 8 4,760 円</p>"), {})
