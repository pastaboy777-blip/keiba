"""`keibabook.parse_cyokyo` のテスト。

⚠️ 実ページの構造をそのまま縮めた HTML を使う。**整形して読みやすくしない**こと
   （実物は改行が無く、`<tr class="oikiri">` の判定が空白に依存しないことを
   ここで担保している）。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import keibabook as kb


def _row(cls, mark, date, course, baba, t9, t10, asiiro, note):
    """調教1行。**16セル**（mark/norite/日付/コース/馬場/時計7/回り/脚色/短評/動画）。"""
    return (f'<tr class="{cls}"><td class="mark">{mark}</td>'
            f'<td class="norite"></td><td class="tukihi">{date}</td>'
            f'<td class="corse">{course}</td><td class="baba">{baba}</td>'
            f'<td></td><td></td><td></td><td></td><td>{t9}</td><td>{t10}</td>'
            f'<td></td><td class="mawariiti"></td>'
            f'<td class="asiiro">{asiiro}</td>'
            f'<td class="tanpyo">{note}</td><td class="movie"></td></tr>')


HTML = (
    '<table class="default cyokyo" id="cyokyo0947209"><tbody>'
    '<tr><td class="waku"><p class="waku1">1</p></td>'
    '<td class="umaban">1</td>'
    '<td class="kbamei"><a href="/db/uma/0947209" umacd="0947209">'
    'キャリアラダー</a></td>'
    '<td class="tanpyo">攻め常に動く</td>'
    '<td class="yajirusi"><span>&rarr;</span></td></tr>'
    '<tr><td class="cyokyo" colspan="5"><table class="cyokyodata"><tbody>'
    + _row("time", "", "8/11(火)", "大井外", "良", "52.2", "37.7", "強め", "上がり重点")
    + _row("time", "", "*8/23(日)", "大井外", "不", "57.7", "42.1", "馬なり", "余裕ある動き")
    + _row("oikiri", "☆", "8/31(月)", "大井外", "良", "", "36.4", "強め", "攻め常に動く")
    + '</tbody></table></td></tr></tbody></table>'
    '<table class="default cyokyo" id="cyokyo0949817"><tbody>'
    '<tr><td class="waku"><p class="waku2">2</p></td>'
    '<td class="umaban">2</td>'
    '<td class="kbamei"><a href="/db/uma/0949817" umacd="0949817">'
    'ミエノワイルド</a></td>'
    '<td class="tanpyo">徐々に良化見せる</td>'
    '<td class="yajirusi"><span>&nearr;</span></td></tr>'
    '<tr><td class="cyokyo" colspan="5"><table class="cyokyodata"><tbody>'
    + _row("oikiri", "☆", "8/30(日)", "小林坂", "重", "50.6", "37.4", "馬なり", "良化")
    + '<tr class="awase"><td></td><td class="left" colspan="14">'
      'サイカンサンユウ（3歳）馬なりの内同入</td></tr>'
    + '</tbody></table></td></tr></tbody></table>'
)


class ParseCyokyoTest(unittest.TestCase):
    def setUp(self):
        self.rows = kb.parse_cyokyo(HTML)

    def test_horses(self):
        self.assertEqual([r["name"] for r in self.rows],
                         ["キャリアラダー", "ミエノワイルド"])
        self.assertEqual([r["umaban"] for r in self.rows], [1, 2])
        self.assertEqual([r["waku"] for r in self.rows], [1, 2])
        self.assertEqual(self.rows[0]["horseid"], "0947209")

    def test_tanpyo_and_arrow(self):
        self.assertEqual(self.rows[0]["tanpyo"], "攻め常に動く")
        self.assertEqual(self.rows[0]["arrow"], "→")
        self.assertEqual(self.rows[1]["arrow"], "↗")

    def test_works_order_is_oldest_first(self):
        w = self.rows[0]["works"]
        self.assertEqual([(x["month"], x["day"]) for x in w],
                         [(8, 11), (8, 23), (8, 31)])

    def test_oikiri_flag(self):
        """☆の行だけ `oikiri` が立つ。**最後の1本が追い切り。**"""
        self.assertEqual([x["oikiri"] for x in self.rows[0]["works"]],
                         [False, False, True])

    def test_gap_star(self):
        """`*` は調教が11日以上空いた印。**日付の一部として読み飛ばさない。**"""
        self.assertEqual([x["gap"] for x in self.rows[0]["works"]],
                         [False, True, False])

    def test_times(self):
        w = self.rows[0]["works"][0]
        self.assertEqual(w["times"]["半哩(3F)"], 52.2)
        self.assertEqual(w["times"]["3F(2F)"], 37.7)
        self.assertIsNone(w["times"]["1哩"])

    def test_times_raw_kept(self):
        """⚠️ 坂路の本数欄に `'2回'` のような非数値が入るので生も残す。"""
        w = self.rows[0]["works"][-1]
        self.assertIsNone(w["times"]["半哩(3F)"])
        self.assertIsNone(w["times_raw"]["半哩(3F)"])
        self.assertEqual(w["times_raw"]["3F(2F)"], "36.4")

    def test_course_and_asiiro(self):
        w = self.rows[1]["works"][0]
        self.assertEqual(w["course"], "小林坂")
        self.assertEqual(w["asiiro"], "馬なり")
        self.assertEqual(w["baba"], "重")

    def test_awase(self):
        self.assertEqual(self.rows[1]["awase"],
                         ["サイカンサンユウ（3歳）馬なりの内同入"])
        self.assertEqual(self.rows[0]["awase"], [])

    def test_awase_is_not_a_work(self):
        """⚠️ 併走行を調教1本として数えてはいけない。"""
        self.assertEqual(len(self.rows[1]["works"]), 1)

    def test_empty_page(self):
        """未提供の日は例外にせず空リスト。開催前は普通に起きる。"""
        self.assertEqual(kb.parse_cyokyo("<p>指定されたページは存在しません。</p>"), [])


if __name__ == "__main__":
    unittest.main()
