import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from nankeiba.core import ped_stats as pst

class TestPedStats(unittest.TestCase):
    def test_band(self):
        self.assertEqual(pst.dist_band(1200), "短(〜1400)")
        self.assertEqual(pst.dist_band(1600), "中(1500-1700)")
        self.assertEqual(pst.dist_band(2000), "長(1800〜)")
    def test_fit_good(self):
        # ナスルーラ系 中距離 = 0.344 >> baseline → ○
        self.assertEqual(pst.fit("nasrullah", 1600), "○")
    def test_fit_bad(self):
        # ノーザンダンサー系 中距離 = 0.172 << baseline → ▽
        self.assertEqual(pst.fit("northern", 1600), "▽")
    def test_fit_neutral_or_empty(self):
        self.assertEqual(pst.fit(None, 1600), "")
        # 母数外/基準内は空
        self.assertIn(pst.fit("sunday", 1600), ("", "○", "▽"))
    def test_rate(self):
        self.assertAlmostEqual(pst.rate("mrprospector", 1200), 0.212, places=3)

if __name__ == "__main__":
    unittest.main()
