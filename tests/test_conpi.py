"""コンピ風ランク指数のテスト。"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from nankeiba.core import conpi


class TestToConpi(unittest.TestCase):
    def test_range_and_unique(self):
        idx = {1: 50, 2: 30, 3: 20, 4: 10, 5: 5}
        c = conpi.to_conpi(idx)
        self.assertEqual(c[1], max(c.values()))          # 指数1位がコンピ最高
        self.assertTrue(all(40 <= v <= 90 for v in c.values()))
        self.assertEqual(len(set(c.values())), len(c))   # 重複なし

    def test_dominant_high_top(self):
        # 断トツ(差大)は1位値が高い
        c1 = conpi.to_conpi({1: 60, 2: 20, 3: 15})       # 差40
        c2 = conpi.to_conpi({1: 22, 2: 20, 3: 18})       # 差2(混戦)
        self.assertGreater(max(c1.values()), max(c2.values()))

    def test_features(self):
        c = conpi.to_conpi({1: 60, 2: 20, 3: 15})
        f = conpi.features(c)
        self.assertEqual(f.top, max(c.values()))
        self.assertEqual(f.n, 3)
        self.assertTrue(f.is_solid)


if __name__ == "__main__":
    unittest.main()
