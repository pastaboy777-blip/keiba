"""当日の馬場差（トラックバイアス）のテスト。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import track_bias, shock
from nankeiba.core.interval import RunRecord

TABLE = {"川崎|1400": 13.44, "川崎|1600": 13.33}


def _res(rno, dist, win_time):
    return dict(race_no=rno, place="川崎", distance=dist, win_time=win_time)


class TestMeasure(unittest.TestCase):
    def test_fast_track(self):
        # 1400m を 92.1秒 = 13.16 s/F、par13.44 → -0.28
        b = track_bias.measure([_res(1, 1400, 92.1), _res(2, 1400, 92.1)], table=TABLE)
        self.assertEqual(b.n_races, 2)
        self.assertAlmostEqual(b.offset, -0.28, places=2)
        self.assertTrue(b.is_fast)
        self.assertEqual(b.label, "高速馬場")
        self.assertIn("高速馬場", b.summary())

    def test_slow_track(self):
        # 1400m を 96.0秒 = 13.71 s/F → +0.27
        b = track_bias.measure([_res(1, 1400, 96.0)], table=TABLE)
        self.assertGreater(b.offset, track_bias.SLOW)
        self.assertEqual(b.label, "時計のかかる馬場")
        self.assertFalse(b.is_fast)

    def test_standard(self):
        b = track_bias.measure([_res(1, 1400, 94.08)], table=TABLE)  # ちょうどpar
        self.assertEqual(b.label, "標準")

    def test_skips_unknown_and_empty(self):
        # par を引けない場/距離は除外。全部除外なら offset=0
        b = track_bias.measure([_res(1, 9999, 200.0), dict(race_no=2)], table=TABLE)
        self.assertEqual((b.offset, b.n_races), (0.0, 0))
        self.assertEqual(track_bias.measure([], table=TABLE).n_races, 0)

    def test_adjusted_par_shifts_table(self):
        b = track_bias.measure([_res(1, 1400, 92.1)], table=TABLE)
        adj = b.adjusted_par(TABLE)
        self.assertAlmostEqual(adj["川崎|1400"], 13.44 + b.offset, places=3)


class TestShockWithBias(unittest.TestCase):
    def test_fast_track_makes_shock_stronger(self):
        """高速馬場では同じ馬でもショックが大きくなり、消しに変わりうる。"""
        prev = RunRecord(date="2026-07-01", place="川崎", distance=1400,
                         field_size=12, finish_pos=5, time_sec=13.80 * 7)
        base = shock.detect([prev], "川崎", 1400, table=TABLE)
        b = track_bias.measure([_res(1, 1400, 92.1)], table=TABLE)   # -0.28
        adj = shock.detect([prev], "川崎", 1400, table=b.adjusted_par(TABLE))
        self.assertLess(adj.value, base.value)          # より強いショック
        self.assertAlmostEqual(adj.value, base.value + b.offset, places=2)

    def test_detect_with_bias_helper(self):
        prev = RunRecord(date="2026-07-01", place="川崎", distance=1400,
                         field_size=12, finish_pos=5, time_sec=13.80 * 7)
        b = track_bias.measure([_res(1, 1400, 92.1)], table=TABLE)
        # 既定テーブルを使うヘルパは川崎1400が実データにあるので None にならない
        t = track_bias.detect_with_bias([prev], "川崎", 1400, b)
        self.assertIsNotNone(t)


class TestMirageDiscount(unittest.TestCase):
    def test_discount_weakens_on_fast_track(self):
        fast = track_bias.TrackBias(offset=-0.29, n_races=2)
        mild = track_bias.TrackBias(offset=-0.12, n_races=2)
        flat = track_bias.TrackBias(offset=0.0, n_races=2)
        slow = track_bias.TrackBias(offset=0.20, n_races=2)
        self.assertLess(track_bias.mirage_discount(fast), 0.5)
        self.assertLess(track_bias.mirage_discount(mild), 1.0)
        self.assertEqual(track_bias.mirage_discount(flat), 1.0)
        self.assertGreater(track_bias.mirage_discount(slow), 1.0)


class TestWinParDefault(unittest.TestCase):
    """当日の馬場差は**勝ち馬par**を基準にする（全馬parと取り違えない）。"""

    def test_default_table_is_win_par(self):
        # 2026-07-27 川崎1R: 1400m を 92.1秒 = 13.157 s/F
        b = track_bias.measure([_res(1, 1400, 92.1)])
        win_par = track_bias.PAR_WIN.get("川崎|1400")
        self.assertIsNotNone(win_par, "data/par_win.json が読めていない")
        self.assertAlmostEqual(b.offset, round(13.157 - win_par, 3), places=2)
        # 全馬par(shock用)を使うと約0.19秒ぶん下駄を履く → 別物であることを確認
        self.assertLess(win_par, shock.PAR_PACE["川崎|1400"])

    def test_win_par_covers_900m(self):
        """900mなど短距離が抜けていると、その日のレースが実測から丸ごと落ちる。"""
        for k in ("川崎|900", "浦和|800", "園田|820"):
            self.assertIn(k, track_bias.PAR_WIN)
            self.assertIn(k, shock.PAR_PACE)

    def test_par_tables_load_outside_repo_root(self):
        """カレントディレクトリに依存せず data/ を引けること。"""
        from nankeiba.core.datapath import data_path
        self.assertTrue(data_path("par_win.json").exists())
        self.assertTrue(data_path("par_pace.json").exists())


if __name__ == "__main__":
    unittest.main()
