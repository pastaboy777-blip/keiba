"""指数・展開予想・新聞レンダラのテスト。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core.interval import RunRecord
from nankeiba.core import hindex, pace, summary, newspaper as nb


def rec(**kw):
    base = dict(date="2026-06-01", place="大井", distance=1600, field_size=12,
                finish_pos=3, baba="良", corner_pos=[3, 3, 3, 3], time_sec=101.0)
    base.update(kw)
    return RunRecord(**base)


class TestPaceClassify(unittest.TestCase):
    def test_nige_in5(self):
        self.assertEqual(pace.classify_run(rec(finish_pos=1, corner_pos=[1, 1, 1, 1])), "in5_nige")

    def test_nige_out(self):
        self.assertEqual(pace.classify_run(rec(finish_pos=8, corner_pos=[1, 1, 1, 2])), "out_nige")

    def test_senko_in5(self):
        # 3角2番手・4角3番手、逃げでない → 先行
        self.assertEqual(pace.classify_run(rec(finish_pos=2, corner_pos=[3, 3, 2, 3])), "in5_senko")

    def test_sashi_in5(self):
        # 3角6番手→4角2番手(まくり)、5着以内
        self.assertEqual(pace.classify_run(rec(finish_pos=4, corner_pos=[8, 7, 6, 2])), "in5_sashi")

    def test_oikomi_in5(self):
        # 4角も後方だが5着以内
        self.assertEqual(pace.classify_run(rec(finish_pos=5, corner_pos=[10, 9, 8, 6])), "in5_oikomi")

    def test_out_backmarker_none(self):
        # 6着以降で後方 → 対象外
        self.assertIsNone(pace.classify_run(rec(finish_pos=9, corner_pos=[10, 9, 8, 7])))

    def test_out_senko(self):
        self.assertEqual(pace.classify_run(rec(finish_pos=7, corner_pos=[3, 3, 3, 3])), "out_senko")

    def test_no_corner_none(self):
        self.assertIsNone(pace.classify_run(rec(corner_pos=[])))


class TestPaceGrid(unittest.TestCase):
    def test_unique_and_order(self):
        # 同じ馬が3走ぶん同じマスに入っても1回だけ、馬番順
        h5 = [rec(finish_pos=1, corner_pos=[1, 1, 1, 1]) for _ in range(3)]
        h3 = [rec(finish_pos=1, corner_pos=[1, 1, 1, 1])]
        grid = pace.build_pace_grid([(5, h5), (3, h3)])
        self.assertEqual(grid.cell("in5_nige").umaban, [3, 5])

    def test_overflow(self):
        entries = [(i, [rec(finish_pos=1, corner_pos=[1, 1, 1, 1])]) for i in range(1, 13)]
        grid = pace.build_pace_grid(entries)
        self.assertTrue(grid.cell("in5_nige").overflow)
        self.assertEqual(grid.cell("in5_nige").umaban, [])

    def test_lookback_3(self):
        # 4走前は対象外
        runs = [rec(finish_pos=8, corner_pos=[5, 5, 5, 5]) for _ in range(3)]  # 6着以降・後方→None
        runs.append(rec(finish_pos=1, corner_pos=[1, 1, 1, 1]))               # 4走前・逃げ
        grid = pace.build_pace_grid([(7, runs)])
        self.assertEqual(grid.cell("in5_nige").umaban, [])

    def test_front_count(self):
        grid = pace.build_pace_grid([
            (1, [rec(finish_pos=1, corner_pos=[1, 1, 1, 1])]),        # in5_nige
            (2, [rec(finish_pos=2, corner_pos=[2, 2, 3, 3])]),        # in5_senko
            (3, [rec(finish_pos=5, corner_pos=[10, 9, 8, 6])]),      # oikomi
        ])
        self.assertEqual(grid.front_count(), 2)


class TestIndex(unittest.TestCase):
    def test_faster_is_higher(self):
        m = hindex.SpeedIndexModel()
        fast = m.index(rec(time_sec=99.0))
        slow = m.index(rec(time_sec=103.0))
        self.assertGreater(fast, slow)

    def test_slope_1600_about_4(self):
        # 距離係数: 1600m で 4.0 点/秒 (逆解析アンカー)
        m = hindex.SpeedIndexModel()
        a = m.index(rec(time_sec=100.0))
        b = m.index(rec(time_sec=101.0))
        self.assertAlmostEqual(a - b, 4.0, delta=0.5)

    def test_shorter_distance_steeper(self):
        m = hindex.SpeedIndexModel()
        self.assertGreater(m.coef(1200), m.coef(1600))

    def test_going_penalty(self):
        # 同タイムなら濡れた馬場ほど指数が低い(基準が速い)
        m = hindex.SpeedIndexModel()
        ryo = m.index(rec(baba="良", time_sec=101.0))
        omo = m.index(rec(baba="重", time_sec=101.0))
        self.assertGreater(ryo, omo)

    def test_no_time_none(self):
        self.assertIsNone(hindex.SpeedIndexModel().index(rec(time_sec=None)))

    def test_fit_learns_standard(self):
        runs = [rec(place="大井", distance=1600, baba="良", time_sec=100.0 + i * 0.1)
                for i in range(20)]
        m = hindex.SpeedIndexModel.fit(runs, min_samples=5)
        self.assertIn(1600, m.standard["大井"])


class TestSummary(unittest.TestCase):
    def test_top_index_sorted(self):
        m = hindex.SpeedIndexModel()
        e = [
            (1, [rec(time_sec=103.0)]),
            (2, [rec(time_sec=99.0)]),
        ]
        rows = summary.top_index_last10(e, m)
        self.assertEqual(rows[0].umaban, 2)      # 速い方が上位

    def test_same_track_filters(self):
        m = hindex.SpeedIndexModel()
        e = [(1, [rec(place="川崎", time_sec=99.0)]), (2, [rec(place="大井", time_sec=101.0)])]
        rows = summary.same_track_index_top(e, m, "大井")
        self.assertEqual([r.umaban for r in rows], [2])

    def test_first3f_distance_filter(self):
        e = [(1, [rec(distance=1600, time_sec=100.0, last3f_sec=39.0)]),
             (2, [rec(distance=1200, time_sec=74.0, last3f_sec=37.0)])]
        rows = summary.first3f_top(e, 1600, dist_tol=200)
        self.assertEqual([r.umaban for r in rows], [1])   # 1200 は±200外で除外


class TestGoingMode(unittest.TestCase):
    def test_pace_read_wet_shift(self):
        # 同じ前頭数でも重・不良は前残り寄りの表現に変わる
        grid = pace.build_pace_grid([
            (1, [rec(finish_pos=1, corner_pos=[1, 1, 1, 1])]),
            (2, [rec(finish_pos=2, corner_pos=[2, 2, 3, 3])]),
            (3, [rec(finish_pos=3, corner_pos=[2, 2, 2, 3])]),
        ])
        dry = grid.pace_read("良")
        wet = grid.pace_read("重")
        self.assertNotEqual(dry, wet)
        self.assertIn("前残り", wet)

    def test_going_aptitude_group(self):
        m = hindex.SpeedIndexModel()
        e = [
            (1, [rec(baba="重", time_sec=100.0, finish_pos=1),
                 rec(baba="良", time_sec=99.0, finish_pos=1)]),
            (2, [rec(baba="良", time_sec=99.0, finish_pos=1)]),
        ]
        apt = summary.going_aptitude(e, m, "重")   # 重系 = {稍,重,不}
        self.assertEqual(apt[1].n, 1)              # 馬1は重の1走のみ該当
        self.assertEqual(apt[2].n, 0)              # 馬2は良のみ→該当なし
        self.assertEqual(apt[1].in3_rate, 1.0)


class TestRender(unittest.TestCase):
    def _card(self):
        m = hindex.SpeedIndexModel()
        entries = [
            nb.PaperEntry(umaban=i, name=f"馬{i}",
                          history=[rec(finish_pos=(i % 5) + 1,
                                       corner_pos=[i % 6 + 1] * 4,
                                       time_sec=100.0 + i * 0.2)])
            for i in range(1, 9)
        ]
        header = nb.RaceHeader(place="大井", distance=1600, date="2026-07-21",
                               race_no=11, baba="良")
        return nb.build_card(header, entries, m)

    def test_text_render(self):
        txt = nb.render_text(self._card())
        self.assertIn("展開予想", txt)
        self.assertIn("10走以内 指数上位", txt)

    def test_html_render(self):
        h = nb.render_html(self._card())
        self.assertIn("<!doctype html>", h)
        self.assertIn("展開予想", h)
        self.assertIn("指数つき馬柱", h)

    def test_marks_assigned(self):
        card = self._card()
        marks = [v.mark for v in card.horses if v.mark]
        self.assertIn("◎", marks)


if __name__ == "__main__":
    unittest.main()
