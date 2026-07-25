"""netkeiba 5代血統パーサのテスト（rowspanからの代復元・side割り）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import netkeiba
from nankeiba.core import cross


# 3代の blood_table（本体8行）を rowspan で表現したフィクスチャ。
# 文書順（上→下・父方先）: A,C,G,H,D,I,J,B,E,K,L,F,M,N
#   gen1(rowspan4): A(父), B(母)
#   gen2(rowspan2): C(父父),D(父母),E(母父),F(母母)
#   gen3(rowspan1): G,H,I,J（父方4） / K,L,M,N（母方4）
# クロス検証: 父方gen3のG と 母方gen3のK を「ストームキャット」にして 3×3 を作る。
FIXTURE = """
<table class="blood_table">
 <tr>
   <td rowspan="4"><a href="/horse/1/">A</a><br>2015 鹿毛</td>
   <td rowspan="2"><a href="/horse/3/">C</a></td>
   <td rowspan="1"><a href="/horse/7/">ストームキャット</a></td>
 </tr>
 <tr><td rowspan="1">H</td></tr>
 <tr>
   <td rowspan="2"><a href="/horse/4/">D</a></td>
   <td rowspan="1">I</td>
 </tr>
 <tr><td rowspan="1">J</td></tr>
 <tr>
   <td rowspan="4"><a href="/horse/2/">B</a><br>2013 青毛</td>
   <td rowspan="2"><a href="/horse/5/">E</a></td>
   <td rowspan="1"><a href="/horse/7/">ストームキャット</a></td>
 </tr>
 <tr><td rowspan="1">L</td></tr>
 <tr>
   <td rowspan="2"><a href="/horse/6/">F</a></td>
   <td rowspan="1">M</td>
 </tr>
 <tr><td rowspan="1">N</td></tr>
</table>
"""


class TestNetkeibaPed(unittest.TestCase):
    def test_parse_ped_generations(self):
        ped = netkeiba.parse_ped(FIXTURE)
        self.assertEqual(ped[1], ["A", "B"])
        self.assertEqual(ped[2], ["C", "D", "E", "F"])
        self.assertEqual(ped[3], ["ストームキャット", "H", "I", "J",
                                  "ストームキャット", "L", "M", "N"])

    def test_cell_name_strips_year(self):
        self.assertEqual(netkeiba._cell_name('<a href="/x/">A</a><br>2015 鹿毛'), "A")
        self.assertEqual(netkeiba._cell_name("Halo"), "Halo")

    def test_occurrences_side_split(self):
        occ = netkeiba.occurrences(FIXTURE)
        # gen3 のストームキャットが父方・母方の両方に出る
        sc = [o for o in occ if o.name == "ストームキャット"]
        self.assertEqual(len(sc), 2)
        self.assertEqual({o.side for o in sc}, {"sire", "dam"})
        self.assertTrue(all(o.gen == 3 for o in sc))

    def test_cross_detected_from_fixture(self):
        occ = netkeiba.occurrences(FIXTURE)
        crosses = cross.detect_crosses(occ)
        names = [c.ancestor for c in crosses]
        self.assertIn("ストームキャット", names)
        sc = [c for c in crosses if c.ancestor == "ストームキャット"][0]
        self.assertEqual(sc.pattern, "3×3")
        self.assertIn(cross.DIRT_POWER, sc.tags)

    def test_cross_score_end_to_end(self):
        # 血統HTML → 道悪ダート短距離ならストームキャット濃縮が効く
        sc = cross.score(netkeiba.occurrences(FIXTURE),
                         surface="ダ", baba="重", distance=1200)
        self.assertGreater(sc.score, 0)
        self.assertIn("ストームキャット", sc.label())


if __name__ == "__main__":
    unittest.main()
