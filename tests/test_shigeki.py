"""点火指数（穴馬が走るタイミング）のテスト。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import shigeki


def run(date="2026-07-14", place="浦和", distance=1400, jockey="Ａ",
        finish_pos=5, corner_pos=(5,), field_size=10, last3f_sec=40.0):
    return dict(date=date, place=place, distance=distance, jockey=jockey,
                finish_pos=finish_pos, corner_pos=list(corner_pos),
                field_size=field_size, last3f_sec=last3f_sec)


class TestChanges(unittest.TestCase):
    def test_no_previous_run(self):
        s, t = shigeki.changes("浦和", 1400, "Ａ", "2026-08-10", None)
        self.assertEqual((s, t), (0.0, []))

    def test_same_everything_is_zero(self):
        prev = run(date="2026-07-14")
        s, t = shigeki.changes("浦和", 1400, "Ａ", "2026-08-10", prev)
        self.assertEqual(t, [])
        self.assertEqual(s, 0.0)

    def test_place_change(self):
        s, t = shigeki.changes("浦和", 1400, "Ａ", "2026-08-10",
                               run(place="川崎"))
        self.assertGreaterEqual(s, shigeki.W_PLACE)
        self.assertTrue(any("川崎" in x for x in t))

    def test_novelty_scores_more_than_routine(self):
        """⚠️ ただ替わっただけの変化はオッズに織り込まれている。
        効くとすれば**その馬がまだ試していない**変化のはず。"""
        prev = run(place="川崎")
        hist_new = [prev, run(place="川崎"), run(place="船橋")]
        hist_old = [prev, run(place="浦和"), run(place="浦和")]
        a, ta = shigeki.changes("浦和", 1400, "Ａ", "2026-08-10", prev,
                                history=hist_new)
        b, _ = shigeki.changes("浦和", 1400, "Ａ", "2026-08-10", prev,
                               history=hist_old)
        self.assertGreater(a, b)
        self.assertTrue(any("初浦和" in x for x in ta))

    def test_first_jockey_combo(self):
        prev = run(jockey="Ａ")
        s, t = shigeki.changes("浦和", 1400, "Ｚ", "2026-08-10", prev,
                               history=[prev, run(jockey="Ａ")])
        self.assertTrue(any("初コンビ" in x for x in t))

    def test_first_distance_band(self):
        prev = run(distance=1200)
        s, t = shigeki.changes("浦和", 2000, "Ａ", "2026-08-10", prev,
                               history=[prev, run(distance=1200)])
        self.assertTrue(any("初長距離" in x for x in t))

    def test_band(self):
        self.assertEqual(shigeki.band(1200), "短")
        self.assertEqual(shigeki.band(1500), "中")
        self.assertEqual(shigeki.band(1800), "長")

    def test_jockey_change(self):
        s, t = shigeki.changes("浦和", 1400, "Ｂ", "2026-08-10", run(jockey="Ａ"))
        self.assertTrue(any("乗替" in x for x in t))

    def test_big_distance_change_scores_more(self):
        a, _ = shigeki.changes("浦和", 1300, "Ａ", "2026-08-10", run(distance=1400))
        b, _ = shigeki.changes("浦和", 1800, "Ａ", "2026-08-10", run(distance=1400))
        self.assertGreater(b, a)

    def test_long_rest(self):
        s, t = shigeki.changes("浦和", 1400, "Ａ", "2026-08-10",
                               run(date="2026-01-10"))
        self.assertTrue(any("ぶり" in x for x in t))

    def test_tight_interval(self):
        s, t = shigeki.changes("浦和", 1400, "Ａ", "2026-08-10",
                               run(date="2026-08-02"))
        self.assertTrue(any("中" in x for x in t))

    def test_bad_date_is_safe(self):
        s, t = shigeki.changes("浦和", 1400, "Ａ", "こわれた", run())
        self.assertIsInstance(s, float)


class TestPreheat(unittest.TestCase):
    def test_needs_two_runs(self):
        self.assertEqual(shigeki.preheat([run()]), (0.0, []))
        self.assertEqual(shigeki.preheat([]), (0.0, []))

    def test_faster_agari_than_own_baseline(self):
        """⚠️ 他馬ではなく**自分の過去**と比べる。"""
        runs = [run(last3f_sec=38.0)] + [run(last3f_sec=41.0)] * 3
        s, w = shigeki.preheat(runs)
        self.assertTrue(any("上がり" in x for x in w))

    def test_position_improved(self):
        runs = [run(corner_pos=(2,), field_size=10)] + [
            run(corner_pos=(8,), field_size=10)] * 3
        s, w = shigeki.preheat(runs)
        self.assertTrue(any("位置" in x for x in w))

    def test_finish_improvement_is_not_credited(self):
        """⚠️ **着順が上がったことを加点しない。**着順はオッズに反映されるので、
        そこを買うと人気馬を買うことになる。8/14 大井で「点火」と出した人気薄
        15頭が1頭も来ず、来た穴は「材料なし」判定だったのがこの形。"""
        runs = [run(finish_pos=2)] + [run(finish_pos=9)] * 3
        s, w = shigeki.preheat(runs)
        self.assertFalse(any("着順が上がった" in x for x in w))

    def test_hidden_improvement_is_the_target(self):
        """内容は良化したのに着順は着外、が狙い（まだ人気にならない）。"""
        runs = ([run(last3f_sec=38.0, finish_pos=8)]
                + [run(last3f_sec=41.0, finish_pos=8)] * 3)
        s, w = shigeki.preheat(runs)
        self.assertTrue(any("着順に出ていない" in x for x in w))

    def test_visible_improvement_scores_less(self):
        """同じ内容良化でも、着順に出てしまった馬は加点しない。"""
        hidden = shigeki.preheat([run(last3f_sec=38.0, finish_pos=8)]
                                 + [run(last3f_sec=41.0, finish_pos=8)] * 3)[0]
        shown = shigeki.preheat([run(last3f_sec=38.0, finish_pos=1)]
                                + [run(last3f_sec=41.0, finish_pos=8)] * 3)[0]
        self.assertGreater(hidden, shown)

    def test_chained_change_counts(self):
        """前走**も**変化だったなら予熱が済んでいる。"""
        runs = [run(place="浦和"), run(place="川崎"), run(place="川崎")]
        s, w = shigeki.preheat(runs)
        self.assertTrue(any("予熱済み" in x for x in w))

    def test_flat_horse_scores_zero(self):
        runs = [run()] * 4
        s, w = shigeki.preheat(runs)
        self.assertEqual(s, 0.0)


class TestIgnition(unittest.TestCase):
    def test_no_history(self):
        ig = shigeki.ignition("浦和", 1400, "Ａ", "2026-08-10", [])
        self.assertEqual(ig.score, 0.0)

    def test_change_plus_preheat_is_ignition(self):
        runs = [run(place="川崎", last3f_sec=38.0, corner_pos=(2,), finish_pos=2),
                run(place="船橋", last3f_sec=41.0, corner_pos=(8,), finish_pos=9),
                run(place="船橋", last3f_sec=41.0, corner_pos=(8,), finish_pos=9)]
        ig = shigeki.ignition("浦和", 1400, "Ｂ", "2026-08-10", runs)
        self.assertGreater(ig.change, 1.5)
        self.assertGreater(ig.preheat, 3.0)
        self.assertIn("点火", ig.label())

    def test_change_without_signs(self):
        runs = [run(place="川崎")] * 3
        ig = shigeki.ignition("浦和", 1400, "Ａ", "2026-08-10", runs)
        self.assertIn("変化のみ", ig.label())

    def test_warm_without_trigger_is_not_no_material(self):
        """⚠️ 変化が無くても前走で動いていれば「予熱済み・引き金なし」。
        材料なしと混ぜない。実際ここを混ぜて表示バグを出した。
        ⚠️ かつて「前走で発射済み」と呼んでいたが、着順加点を外した今は
        予熱が高い＝着順に出ていない良化なので、その名前は逆だった。"""
        runs = [run(last3f_sec=38.0, corner_pos=(2,), finish_pos=8, place="浦和"),
                run(last3f_sec=41.0, corner_pos=(8,), finish_pos=8, place="川崎"),
                run(last3f_sec=41.0, corner_pos=(8,), finish_pos=8, place="川崎")]
        ig = shigeki.ignition("浦和", 1400, "Ａ", "2026-08-10", runs)
        self.assertLess(ig.change, 1.5)
        self.assertGreaterEqual(ig.preheat, 3.0)
        self.assertIn("予熱済み", ig.label())
        self.assertNotIn("材料なし", ig.label())

    def test_nothing(self):
        ig = shigeki.ignition("浦和", 1400, "Ａ", "2026-08-10", [run()] * 3)
        self.assertEqual(ig.label(), "材料なし")


if __name__ == "__main__":
    unittest.main()
