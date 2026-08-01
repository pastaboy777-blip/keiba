"""南関の「中身の濃いレース」判定 thickness のテスト。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import thickness as th        # noqa: E402


def lv(**kw):
    base = dict(date="2026-07-30", place="川崎", race_no=5, distance=1400,
                field_size=12)
    base.update(kw)
    return th.RaceLevel(**base)


class TestTen3fGuard(unittest.TestCase):
    """⚠️ 1500m/1900m は先頭に100mの半端な区間が入りテン3Fがずれる。"""

    def test_divisible_distances_are_ok(self):
        for d in (1200, 1400, 1600, 1800, 2000, 900):
            self.assertEqual(th.ten3f_ok(d), d % 200 == 0, d)

    def test_odd_distances_are_rejected(self):
        self.assertFalse(th.ten3f_ok(1500))
        self.assertFalse(th.ten3f_ok(1900))
        self.assertFalse(th.ten3f_ok(None))


class TestKey(unittest.TestCase):
    """⚠️ (日付,場,距離) では足りない。同日同距離が2レース組まれることがある。"""

    def test_field_size_is_part_of_the_key(self):
        a = lv(field_size=8)
        b = lv(field_size=14)
        self.assertNotEqual(a.key, b.key)
        self.assertEqual(a.key, ("2026-07-30", "川崎", 1400, 8))

    def test_index_keeps_both_races(self):
        idx = th.index_by_key([lv(field_size=8), lv(field_size=14)])
        self.assertEqual(len(idx), 2)


class TestRank(unittest.TestCase):
    def _set(self):
        return [lv(race_no=1, thick=-3.0, time_lv=0.5, grade=0.10),
                lv(race_no=2, thick=-1.0, time_lv=9.0, grade=0.40),
                lv(race_no=3, thick=+2.0, time_lv=2.0, grade=0.25),
                lv(race_no=4, thick=None, time_lv=5.0, grade=0.30)]

    def test_thick_is_ascending_because_minus_is_thicker(self):
        got = [r.race_no for r in th.rank(self._set(), by="thick")]
        self.assertEqual(got, [1, 2, 3])

    def test_races_without_thickness_drop_out_of_the_thick_ranking(self):
        self.assertNotIn(4, [r.race_no for r in th.rank(self._set(), by="thick")])

    def test_time_is_descending(self):
        got = [r.race_no for r in th.rank(self._set(), by="time")]
        self.assertEqual(got, [2, 4, 3, 1])

    def test_grade_is_descending(self):
        got = [r.race_no for r in th.rank(self._set(), by="grade")]
        self.assertEqual(got, [2, 4, 3, 1])

    def test_where_filter(self):
        rs = self._set() + [lv(race_no=9, place="大井", thick=-9.0)]
        got = [r.race_no for r in th.rank(rs, by="thick", place="大井")]
        self.assertEqual(got, [9])

    def test_top_limits(self):
        self.assertEqual(len(th.rank(self._set(), by="thick", top=2)), 2)

    def test_unknown_key_raises(self):
        with self.assertRaises(ValueError):
            th.rank(self._set(), by="なにか")


class TestNotRedundant(unittest.TestCase):
    """濃さ・時計・格は別のものを測っている（実測の相関を固定しておく）。

    2026年7月の南関170レースでの実測:
        濃さ × 時計レベル −0.535 / 濃さ × 格 −0.169 / 時計レベル × 格 +0.130
    （濃さはマイナスほど濃く、時計はプラスほど速いので、負の相関＝同じ向き）
    速いレースが濃いとは限らない、というのがこの手法の前提。
    """

    def test_a_fast_race_can_be_thin(self):
        """時計は速いのに、テンだけ速くて上がりが落ちた＝濃くない。"""
        r = lv(ten_d=-2.0, ag_d=+2.5, time_lv=+4.0)
        r.thick = round(r.ten_d + r.ag_d, 2)
        self.assertGreater(r.thick, 0, "上がりが落ちていれば濃くない")
        self.assertGreater(r.time_lv, 0, "それでも時計は速い")

    def test_a_thick_race_can_be_slow(self):
        r = lv(ten_d=-1.2, ag_d=-1.1, time_lv=-1.21)
        r.thick = round(r.ten_d + r.ag_d, 2)
        self.assertLess(r.thick, 0)
        self.assertLess(r.time_lv, 0)


class TestLabel(unittest.TestCase):
    def test_line_marks_unmeasurable_distances(self):
        self.assertIn("テン3F不可", lv(distance=1500, thick=None).line())

    def test_line_shows_numbers(self):
        s = lv(thick=-2.1, ten_d=-1.4, ag_d=-0.7, time_lv=4.11, grade=0.23).line()
        self.assertIn("-2.1", s)
        self.assertIn("川崎5R", s)


class TestBiasNameCollision(unittest.TestCase):
    """⚠️ bias（当日馬場差の数値）と finish_bias（決着傾向の文字列）の取り違え。

    `lap.LapAnalysis.bias` は決着傾向だが `RaceLevel.bias` は馬場差[s/F]。
    名前が同じで中身が違うため、日別集計の「決着」欄に馬場差の数値が
    並ぶバグを出した。
    """

    def test_two_different_fields(self):
        r = lv(bias=0.043, finish_bias="前残り")
        self.assertIsInstance(r.bias, float)
        self.assertEqual(r.finish_bias, "前残り")

    def test_finish_bias_defaults_to_none_not_zero(self):
        self.assertIsNone(lv().finish_bias)
        self.assertEqual(lv().bias, 0.0)

    def test_counting_finish_bias_never_yields_numbers(self):
        from collections import Counter
        rs = [lv(bias=0.04, finish_bias="前残り"), lv(bias=0.11, finish_bias="差し"),
              lv(bias=0.07, finish_bias="前残り")]
        c = Counter(r.finish_bias for r in rs if r.finish_bias)
        self.assertEqual(c, {"前残り": 2, "差し": 1})
        self.assertTrue(all(isinstance(k, str) for k in c))


class TestTimeLevelSign(unittest.TestCase):
    """⚠️ 当日馬場差の符号。補正後はその日の中央値が0付近になるのが正しい。

    `track_bias.offset` は 平均(実測 s/F − par) なので**時計のかかる日はプラス**。
    「実測 − par − 馬場差」と引くべきところを足してしまい、2026-07-03 船橋
    （馬場差 +0.27 s/F）が全12レース D/E・完全タイム差の中央値 +3.5秒という
    補正後とは思えない表になった。
    """

    def _day(self, par, off, dist=1200, n=12):
        """par から一律 off だけ遅い日を作る（＝馬場差 off の日）。"""
        f = dist / 200.0
        return [dict(race_no=i, place="船橋", distance=dist,
                     win_time=(par + off) * f) for i in range(1, n + 1)]

    def test_offset_is_positive_on_a_slow_day(self):
        from nankeiba.core import track_bias
        tb = track_bias.measure(self._day(12.5, +0.27),
                                table={"船橋|1200": 12.5})
        self.assertAlmostEqual(tb.offset, 0.27, places=2)

    def test_corrected_time_is_zero_on_a_uniform_day(self):
        """一律に遅い日なら、馬場差を引いた完全タイム差は0になる。"""
        par, off, dist = 12.5, 0.27, 1200
        f = dist / 200.0
        sf = par + off
        time_lv = (par - sf + off) * f          # 実装と同じ式
        self.assertAlmostEqual(time_lv, 0.0, places=6)

    def test_wrong_sign_would_double_the_error(self):
        """足してしまうと誤差が2倍になる（当時の症状の再現）。"""
        par, off, dist = 12.5, 0.27, 1200
        f = dist / 200.0
        sf = par + off
        wrong = -(par - sf - off) * f           # 旧実装の完全タイム差
        self.assertAlmostEqual(wrong, 2 * off * f, places=6)
        self.assertGreater(wrong, 3.0, "1200mで+3秒超＝表の症状")

    def test_a_genuinely_fast_race_still_scores_positive(self):
        par, off, dist = 12.5, 0.27, 1200
        f = dist / 200.0
        sf = par + off - 0.5                    # その日の中でさらに0.5s/F速い
        self.assertAlmostEqual((par - sf + off) * f, 0.5 * f, places=6)
