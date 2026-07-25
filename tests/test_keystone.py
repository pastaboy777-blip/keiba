"""キーストーン血 集計ロジック（scripts/ana/keystone.py）のテスト。"""
import importlib.util
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
_spec = importlib.util.spec_from_file_location(
    "keystone", os.path.join(ROOT, "scripts", "ana", "keystone.py"))
ks = importlib.util.module_from_spec(_spec)
sys.modules["keystone"] = ks          # dataclass の __module__ 解決に必要
_spec.loader.exec_module(ks)


def _o(name, finish, pop=8, dist=1600, place="大井"):
    return ks.Outcome(name=name, place=place, dist=dist, baba="良",
                      finish=finish, pop=pop, field=14)


class TestKeystone(unittest.TestCase):
    def test_lift_detects_good_ancestor(self):
        # 祖Xを持つ馬は全複勝、持たない馬は全着外 → Xのliftが高い
        anc = {"A": ["x", "z"], "B": ["x", "y"], "C": ["z"], "D": ["y"]}
        rows = [
            _o("A", 1), _o("A", 2), _o("A", 3),   # X持ち→複勝
            _o("B", 1), _o("B", 3), _o("B", 2),   # X持ち→複勝
            _o("C", 10), _o("C", 12), _o("C", 9),  # X無し→着外
            _o("D", 8), _o("D", 11), _o("D", 14),  # X無し→着外
        ]
        base, npool, keys = ks.ancestor_lift(rows, anc, min_n=3, min_lift=1.15,
                                             min_horses=2)
        self.assertEqual(npool, 12)
        self.assertAlmostEqual(base, 0.5)
        names = [k.ancestor for k in keys]
        self.assertIn("x", names)
        xk = [k for k in keys if k.ancestor == "x"][0]
        self.assertEqual((xk.n, xk.fuku, xk.horses), (6, 6, 2))  # 2頭(A,B)
        self.assertAlmostEqual(xk.lift, 2.0)  # 100% / 50%

    def test_min_horses_filters_single_horse_artifact(self):
        # 1頭Aが5回走って全複勝 → 全祖 n=5 だが horses=1 で足切り
        anc = {"A": ["solo1", "solo2"], "B": ["shared"], "C": ["shared"]}
        rows = ([ks.Outcome("A", "大井", 1600, "良", 1, 8, 14)] * 5
                + [ks.Outcome("B", "大井", 1600, "良", 1, 8, 14)] * 3
                + [ks.Outcome("C", "大井", 1600, "良", 2, 8, 14)] * 3)
        _, _, keys = ks.ancestor_lift(rows, anc, min_n=3, min_lift=1.0, min_horses=2)
        names = [k.ancestor for k in keys]
        self.assertNotIn("solo1", names)   # 1頭のみ→除外
        self.assertIn("shared", names)     # B,C の2頭→残る

    def test_min_n_filters(self):
        anc = {"A": ["rare"]}
        rows = [_o("A", 1), _o("A", 2)]  # rareはn=2のみ
        _, _, keys = ks.ancestor_lift(rows, anc, min_n=15, min_lift=1.0)
        self.assertFalse(keys)

    def test_cond_filter_popularity(self):
        anc = {"A": ["x"], "B": ["x"]}
        rows = [_o("A", 1, pop=2), _o("A", 3, pop=2),      # 人気→除外
                _o("B", 1, pop=9), _o("B", 2, pop=9), _o("B", 3, pop=9)]
        base, npool, keys = ks.ancestor_lift(
            rows, anc, cond=lambda o: o.pop and o.pop >= 7, min_n=3, min_lift=1.0)
        self.assertEqual(npool, 3)  # Bの3走のみ

    def test_empty(self):
        base, npool, keys = ks.ancestor_lift([], {}, min_n=1)
        self.assertEqual((base, npool, keys), (0.0, 0, []))

    def test_dist_band(self):
        self.assertEqual(ks._dist_band(1200), "〜1200")
        self.assertEqual(ks._dist_band(1700), "1600-1800")
        self.assertEqual(ks._dist_band(2000), "1900〜")


if __name__ == "__main__":
    unittest.main()
