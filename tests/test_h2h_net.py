"""H2Hネットワーク（結果ページ主・馬柱補助）のテスト。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import h2h_net


K1 = ("2026-04-22", "園田", 820, 12)
K2 = ("2026-07-23", "園田", 820, 12)


def _net():
    n = h2h_net.H2HNet()
    # 4/22: A が B に先着
    n.add("ミスターエヌ", K1, 1, from_result=True)
    n.add("ベラジオアブロード", K1, 2, from_result=True)
    n.add("スマートフレイヤ", K1, 3, from_result=True)
    return n


class TestNet(unittest.TestCase):
    def test_record_direction(self):
        n = _net()
        self.assertEqual(n.record("ミスターエヌ", "ベラジオアブロード"), (1, 0))
        self.assertEqual(n.record("ベラジオアブロード", "ミスターエヌ"), (0, 1))

    def test_before_blocks_leak(self):
        n = _net()
        # 4/22 より前の情報だけ見るなら対戦は無い
        self.assertEqual(n.record("ミスターエヌ", "ベラジオアブロード",
                                  before="2026-04-01"), (0, 0))
        self.assertEqual(n.record("ミスターエヌ", "ベラジオアブロード",
                                  before="2026-07-23"), (1, 0))

    def test_add_is_idempotent_and_counts_source(self):
        n = _net()
        before = n.n_result
        n.add("ミスターエヌ", K1, 9, from_result=True)   # 既存キーは無視
        self.assertEqual(n.n_result, before)
        self.assertEqual(n.finish_of["ミスターエヌ"][K1], 1)
        n.add("ミスターエヌ", K2, 1, from_result=False)
        self.assertEqual(n.n_history, 1)

    def test_common_races(self):
        n = _net()
        self.assertEqual(n.common_races("ミスターエヌ", "ベラジオアブロード"), [K1])
        self.assertEqual(n.common_races("ミスターエヌ", "存在しない馬"), [])

    def test_same_finish_is_not_counted(self):
        n = h2h_net.H2HNet()
        n.add("A", K1, 3, from_result=True)
        n.add("B", K1, 3, from_result=True)
        self.assertEqual(n.record("A", "B"), (0, 0))


class TestAlerts(unittest.TestCase):
    def _entries(self):
        return [
            dict(name="ミスターエヌ", umaban=12, ninki=9),
            dict(name="ベラジオアブロード", umaban=10, ninki=1),
            dict(name="スマートフレイヤ", umaban=3, ninki=2),
        ]

    def test_fires_on_longshot_beating_favorite(self):
        # ミスターエヌ(9人気,1着)は 1人気・2人気の両方に先着しているので2件鳴る
        a = h2h_net.alerts(_net(), self._entries(), before="2026-07-23")
        self.assertEqual(len(a), 2)
        # 人気差の大きい順＝1人気を疑うアラートが先頭
        self.assertEqual((a[0].ana, a[0].fav), ("ミスターエヌ", "ベラジオアブロード"))
        self.assertEqual((a[0].gap, a[0].win, a[0].loss), (8, 1, 0))
        self.assertIn("先着", a[0].note)
        self.assertEqual(a[1].fav, "スマートフレイヤ")
        self.assertEqual(a[1].gap, 7)

    def test_min_gap(self):
        # 人気差8なので min_gap=9 では鳴らない
        self.assertEqual(h2h_net.alerts(_net(), self._entries(), min_gap=9), [])

    def test_does_not_fire_when_favorite_won(self):
        # 逆向き（人気馬が先着していた）ケースは鳴らさない＝非対称
        n = h2h_net.H2HNet()
        n.add("ベラジオアブロード", K1, 1, from_result=True)
        n.add("ミスターエヌ", K1, 2, from_result=True)
        self.assertEqual(h2h_net.alerts(n, self._entries()), [])


if __name__ == "__main__":
    unittest.main()
