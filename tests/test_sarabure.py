"""サラブレ穴ぐさ／好走リスト パーサのテスト（ネット非依存）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import sarabure as sb


ANAGUSA_HTML = """
<div class="anagusa-list">
  <section class="anagusa-horse b">
    <div class="place">新潟 2R メイクデビュー新潟</div>
    <div class="name"><span>12&nbsp;ミカミッチー</span><p class="re-tag-ana">穴ぐさ</p></div>
    <div class="anagusa-box"><div class="filter-anagusa"></div>
      <p>ドレフォン牝馬はJRAのダート1200ｍの新馬戦で[2.3.2.14](複勝率33.3％)。母母父がフレンチデピュティで、デピュティミニスターの5×4というクロスも持っている。</p>
    </div>
  </section>
  <section class="anagusa-horse a">
    <div class="place">新潟 6R 豊栄特別</div>
    <div class="name"><span>3&nbsp;ラビットアイ</span><p class="re-tag-ana">穴ぐさ</p></div>
    <div class="anagusa-box"><p>道悪馬場でスムーズに動ければ。</p></div>
  </section>
</div>
"""

KOSOU_HTML = """
<main>
  <div class="re-txt-area">
    <p>26年7月25日<br>
    新潟 12R 3歳以上1勝クラス･牝<br>
    芝1400m<br>
    ジョワイユノエル<br>
    11人気 2着 (単オッズ41.8倍)<br>
    小崎騎手<br><br>
    キタサンブラック産駒はJRAの芝1400ｍで3～7枠だと[16.8.11.73](複勝率32.4％)。C
    </p>
  </div>
  <div class="re-txt-area">
    <p>26年7月25日<br>
    新潟 2R メイクデビュー新潟<br>
    ダ1200m<br>
    ミカミッチー<br>
    9人気 1着 (単オッズ30.4倍)<br>
    横山典騎手<br><br>
    デピュティミニスターの5×4というクロスも持っている。B
    </p>
  </div>
</main>
"""


class TestAnagusaParse(unittest.TestCase):
    def test_parse(self):
        al = sb.parse_anagusa_list(ANAGUSA_HTML)
        self.assertEqual(len(al), 2)
        a = al[0]
        self.assertEqual((a.place, a.race_no, a.race_name), ("新潟", 2, "メイクデビュー新潟"))
        self.assertEqual((a.umaban, a.name, a.grade), (12, "ミカミッチー", "b"))
        self.assertEqual(a.stats, ["[2.3.2.14](複勝率33.3％)"])
        self.assertEqual(a.crosses, [("デピュティミニスター", "5×4")])
        self.assertEqual(al[1].grade, "a")

    def test_cross_handles_long_vowel(self):
        # 長音符ー を含む祖先名が化けない（ストームキャット）
        html = ANAGUSA_HTML.replace("デピュティミニスターの5×4",
                                    "ストームキャットの5×4")
        a = sb.parse_anagusa_list(html)[0]
        self.assertEqual(a.crosses, [("ストームキャット", "5×4")])


class TestKosouParse(unittest.TestCase):
    def test_parse(self):
        kl = sb.parse_kosou_list(KOSOU_HTML)
        self.assertEqual(len(kl), 2)
        k = kl[0]
        self.assertEqual(k.name, "ジョワイユノエル")
        self.assertEqual((k.place, k.race_no), ("新潟", 12))
        self.assertEqual(k.distance, "芝1400m")
        self.assertEqual((k.ninki, k.finish, k.odds), (11, 2, 41.8))
        self.assertEqual(k.jockey, "小崎騎手")
        self.assertEqual(k.grade, "C")
        self.assertEqual(k.stats, ["[16.8.11.73](複勝率32.4％)"])
        # グレード文字はコメント末尾から除去済み
        self.assertFalse(k.comment.endswith("C"))

    def test_second_entry_cross(self):
        k = sb.parse_kosou_list(KOSOU_HTML)[1]
        self.assertEqual((k.name, k.ninki, k.finish, k.grade), ("ミカミッチー", 9, 1, "B"))
        self.assertEqual(k.crosses, [("デピュティミニスター", "5×4")])


if __name__ == "__main__":
    unittest.main()
