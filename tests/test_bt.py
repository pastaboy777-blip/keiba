"""BT値（南関版）のテスト。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import bt


def row(**kw):
    """採点用の1行。既定は「浦和1400m・Ｃ２・古馬・良・4着/12頭」。"""
    base = dict(rid="R1", date="2026-08-10", place="浦和", race_no=5,
                distance=1400, field_size=12, baba="良", race_class="Ｃ２三",
                condition="サラブレッド系 一般", win_time=91.0, laps=[],
                ten3f=None, last3f_race=39.4, finish=4, popularity=3,
                time_sec=91.0, agari=39.4, kinryo=56.0, age=5, corner4=3,
                apprentice=False, name="テストウマ")
    base.update(kw)
    return base


class TestClass(unittest.TestCase):
    def test_grade(self):
        self.assertEqual(bt.grade("Ｃ１三"), "Ｃ１")
        self.assertEqual(bt.grade("３歳２"), "３歳")
        self.assertEqual(bt.grade("オープン"), "オープン")
        self.assertIsNone(bt.grade(None))

    def test_grade_merged_takes_upper(self):
        """併合クラスは上の級で代表する（下に合わせると水準を過小評価する）。"""
        self.assertEqual(bt.grade("Ｂ１二Ｂ２一"), "Ｂ１")

    def test_par_key_bundles_a(self):
        """Ａ級以上は 'A+' に束ねる（1マスの母数を確保するため）。"""
        for c in ("オープン", "Ａ１", "Ａ２", "重賞"):
            self.assertEqual(bt.par_key(c), "A+")
        self.assertEqual(bt.par_key("Ｂ３"), "B")
        self.assertEqual(bt.par_key("Ｃ３一二"), "C3")
        self.assertEqual(bt.par_key(None), "other")

    def test_age_group(self):
        self.assertEqual(bt.age_group(2), "2")
        self.assertEqual(bt.age_group(3), "3")
        self.assertEqual(bt.age_group(7), "old")
        self.assertEqual(bt.age_group(None), "old")


class TestSampling(unittest.TestCase):
    def test_good_sample(self):
        self.assertTrue(bt.is_sample(row(finish=3, field_size=12)))

    def test_winner_excluded(self):
        """1着は除く。桁違いの馬が下級条件に来ると基準が不当に速くなる。"""
        self.assertFalse(bt.is_sample(row(finish=1)))

    def test_lower_half_excluded(self):
        self.assertFalse(bt.is_sample(row(finish=8, field_size=12)))

    def test_non_good_going_excluded(self):
        self.assertFalse(bt.is_sample(row(finish=3, baba="重")))

    def test_apprentice_excluded(self):
        self.assertFalse(bt.is_sample(row(finish=3, apprentice=True)))

    def test_handicap_excluded(self):
        self.assertFalse(bt.is_sample(row(finish=3, condition="ハンデ")))

    def test_deep_closer_excluded(self):
        """4角で後方だった馬はロスが乗るので基準作りに使わない。"""
        self.assertFalse(bt.is_sample(row(finish=3, field_size=12, corner4=11)))

    def test_small_field_keeps_top2(self):
        """頭数が少なくても2着までは残す（round(4*0.33)=1 で全滅しないこと）。"""
        self.assertTrue(bt.is_sample(row(finish=2, field_size=4, corner4=2)))


class TestBaseTime(unittest.TestCase):
    def setUp(self):
        rows = []
        for i in range(12):
            rows.append(row(rid=f"c2{i}", finish=2, field_size=12, corner4=2,
                            time_sec=91.0, race_class="Ｃ２", age=5))
            rows.append(row(rid=f"a{i}", finish=2, field_size=12, corner4=2,
                            time_sec=87.6, race_class="オープン", age=5))
        self.B = bt.BaseTime.build(rows)

    def test_build_separates_classes(self):
        self.assertAlmostEqual(self.B.win[("浦和", 1400, "C2", "old")], 91.0)
        self.assertAlmostEqual(self.B.win[("浦和", 1400, "A+", "old")], 87.6)

    def test_min_samples(self):
        """母数が足りないマスは作らない。"""
        B = bt.BaseTime.build([row(finish=2, corner4=2)], min_samples=8)
        self.assertEqual(B.win, {})

    def test_lookup_exact(self):
        w, _, lv = self.B.lookup("浦和", 1400, "オープン", 5)
        self.assertAlmostEqual(w, 87.6)
        self.assertTrue(lv.startswith("1"))

    def test_lookup_falls_back_and_reports_level(self):
        """当たらなければ段を下げる。**どの段で当たったかを必ず返す。**"""
        w, _, lv = self.B.lookup("浦和", 1400, "Ｃ３", 5)
        self.assertIsNotNone(w)
        self.assertFalse(lv.startswith("1"))

    def test_lookup_missing(self):
        _, _, lv = self.B.lookup("大井", 9999, "Ｃ２", 5)
        self.assertTrue(lv.startswith("5"))

    def test_unified_ignores_class(self):
        """⚠️ 採点はクラスによらず同じ基準を引く。ここが崩れると全クラスが
        55に寄って、指数が階級を区別しなくなる。"""
        a = self.B.unified("浦和", 1400)
        self.assertAlmostEqual(a[0], 91.0)
        for cls in ("オープン", "Ｃ２", "３歳", None):
            w, _, _ = self.B.unified("浦和", 1400)
            self.assertAlmostEqual(w, 91.0, msg=f"{cls} で基準が変わった")

    def test_roundtrip(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "b.json")
            self.B.dump(p)
            C = bt.BaseTime.load(p)
        self.assertEqual(C.win, self.B.win)
        self.assertEqual(C.n, self.B.n)


class TestWeight(unittest.TestCase):
    def test_dist_mult_is_flat(self):
        """⚠️ 仕様は「短距離ほど斤量が効く」とするが実測では出なかった
        （〜1100m +0.0083 / 1200〜1400m +0.0246 / 1800m〜 +0.0391 と
        単調でない）。根拠が無いので一律1.0。"""
        for d in (800, 1200, 1600, 2000, 2600):
            self.assertAlmostEqual(bt.dist_mult(d), 1.0)

    def test_effect_scales_with_distance(self):
        """⚠️ 斤量の効果は**距離に比例する**（固定秒ではない）。
        1000mあたりの秒数×距離。最初の実装は構造から間違っていた。"""
        a = bt.weight_sec(57.0, 5, 1000) - bt.weight_sec(56.0, 5, 1000)
        b = bt.weight_sec(57.0, 5, 2000) - bt.weight_sec(56.0, 5, 2000)
        self.assertAlmostEqual(b, a * 2, places=6)

    def test_points_per_kg_is_constant(self):
        """距離に比例させた結果、BT点での効き目は距離によらず一定になる。"""
        def pt(d):
            return (bt.weight_sec(57.0, 5, d) - bt.weight_sec(56.0, 5, d)) / bt.dist_coef(d)
        self.assertAlmostEqual(pt(1200), pt(2000), places=6)

    def test_magnitude_is_measured_not_folklore(self):
        """⚠️ 巷の「1kg＝0.1〜0.2秒」を持ち込まないこと。実測は1桁小さい。"""
        self.assertAlmostEqual(bt.SEC_PER_KG_1000M, 0.0227, places=4)
        one_kg_at_1600 = bt.weight_sec(57.0, 5, 1600) - bt.weight_sec(56.0, 5, 1600)
        self.assertLess(one_kg_at_1600, 0.05)

    def test_heavier_is_positive(self):
        """重い斤量はプラス。走破タイムから引くと標準斤量の時計に近づく。"""
        self.assertGreater(bt.weight_sec(58.0, 5, 1400), 0)
        self.assertLess(bt.weight_sec(54.0, 5, 1400), 0)
        self.assertAlmostEqual(bt.weight_sec(56.0, 5, 1400), 0.0)

    def test_standard_is_male_allowance(self):
        """牡馬定量が基準。牝馬の2kg減が補正に乗ること。"""
        self.assertAlmostEqual(bt.STD_KINRYO["old"], 56.0)
        self.assertLess(bt.weight_sec(54.0, 5, 1400), 0)

    def test_fast_track_amplifies(self):
        """高速馬場では体重差が推進力差に直結する（二次補正）。"""
        n = abs(bt.weight_sec(58.0, 5, 1400, ratio=1.00))
        f = abs(bt.weight_sec(58.0, 5, 1400, ratio=0.95))
        self.assertGreater(f, n)

    def test_jockey_rank_is_flat(self):
        """⚠️ 仕様は「上位騎手は斤量差を技術でカバーするので係数が小さい」と
        するが、南関の実測は単調にならず、むしろ逆向きだった
        （ランク1 +0.0365 / 2 +0.0452 / 3 -0.0026 / 5 +0.0424）。
        根拠が無い係数は入れない。引数だけ残す。"""
        vals = {bt.weight_sec(58.0, 5, 1400, jockey_rank=k) for k in (1, 2, 3, 4, 5)}
        self.assertEqual(len(vals), 1)


class TestAge(unittest.TestCase):
    def test_old_is_zero(self):
        self.assertEqual(bt.age_sec(6, "2026-08-10", 1400), 0.0)

    def test_young_gets_credit(self):
        self.assertGreater(bt.age_sec(2, "2026-08-10", 1400), 0)

    def test_scales_with_distance(self):
        a = bt.age_sec(2, "2026-08-10", 1000)
        b = bt.age_sec(2, "2026-08-10", 2000)
        self.assertAlmostEqual(b, a * 2, places=6)

    def test_three_year_old_early_season_is_slower(self):
        """3歳の1〜3月は実質2歳の延長。ここだけは月別にはっきり出た。"""
        jan = bt.age_sec(3, "2026-01-10", 1400)
        jun = bt.age_sec(3, "2026-06-10", 1400)
        self.assertGreater(jan, jun)

    def test_measured_not_spec_values(self):
        """⚠️ 仕様の推測値（2歳で2.5s/1000m）ではなく実測値（0.64）であること。"""
        self.assertAlmostEqual(bt.age_sec(2, "2026-09-01", 1000), 0.64, places=2)


class TestScore(unittest.TestCase):
    def setUp(self):
        rows = [row(rid=f"c{i}", finish=2, field_size=12, corner4=2,
                    time_sec=91.0, race_class="Ｃ２", age=5) for i in range(12)]
        self.B = bt.BaseTime.build(rows)
        self.flat = bt.TrackRatio(1.0, 1.0, 12)

    def test_standard_run_is_center(self):
        """基準どおりに走った古馬は中心値になる。"""
        s = bt.score(row(time_sec=91.0, agari=39.4, kinryo=56.0, age=5),
                     self.B, self.flat)
        self.assertAlmostEqual(s.bt, bt.CENTER, places=1)

    def test_faster_is_higher(self):
        a = bt.score(row(time_sec=90.0), self.B, self.flat)
        b = bt.score(row(time_sec=92.0), self.B, self.flat)
        self.assertGreater(a.bt, b.bt)

    def test_dist_coef_floor(self):
        """短距離は距離係数に下限。ノイズをそのまま増幅しないため。"""
        self.assertAlmostEqual(bt.dist_coef(800), bt.DIST_COEF_FLOOR)
        self.assertAlmostEqual(bt.dist_coef(2000), 2.0)

    def test_same_gap_same_points(self):
        """距離が違っても同じ秒差＝同じポイント差にはならない（係数で割るため）。
        1400mで1秒は 10/1.4 ポイント。"""
        a = bt.score(row(time_sec=90.0), self.B, self.flat)
        b = bt.score(row(time_sec=91.0), self.B, self.flat)
        self.assertAlmostEqual(a.bt - b.bt, 10.0 / 1.4, places=1)

    def test_no_base_returns_none(self):
        self.assertIsNone(bt.score(row(place="大井", distance=9999),
                                   self.B, self.flat))

    def test_missing_time_returns_none(self):
        self.assertIsNone(bt.score(row(time_sec=None), self.B, self.flat))

    def test_baba_adjust_applied(self):
        good = bt.score(row(baba="良"), self.B, self.flat)
        wet = bt.score(row(baba="不良"), self.B, self.flat)
        self.assertAlmostEqual(wet.bt - good.bt, bt.BABA_ADJ["不"], places=1)
        self.assertEqual(wet.parts["馬場"], bt.BABA_ADJ["不"])

    def test_baba_can_be_disabled(self):
        a = bt.score(row(baba="不良"), self.B, self.flat, baba=False)
        b = bt.score(row(baba="良"), self.B, self.flat, baba=False)
        self.assertAlmostEqual(a.bt, b.bt, places=1)

    def test_track_ratio_applied(self):
        """高速馬場（比<1）で出した時計は割り引かれる。"""
        fast = bt.TrackRatio(0.97, 0.97, 12)
        a = bt.score(row(time_sec=90.0), self.B, self.flat)
        b = bt.score(row(time_sec=90.0), self.B, fast)
        self.assertLess(b.bt, a.bt)


class TestBaba(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(bt.norm_baba("稍重"), "稍")
        self.assertEqual(bt.norm_baba("不良"), "不")
        self.assertEqual(bt.norm_baba("良"), "良")
        self.assertIsNone(bt.norm_baba(None))

    def test_wet_gets_credit(self):
        """当日馬場比だけでは道悪を吸収しきれず、系統的に低く出る。その分を戻す。"""
        self.assertEqual(bt.BABA_ADJ["良"], 0.0)
        self.assertLess(bt.BABA_ADJ["稍"], bt.BABA_ADJ["重"])
        self.assertLess(bt.BABA_ADJ["重"], bt.BABA_ADJ["不"])

    def test_sign_is_opposite_to_spec(self):
        """⚠️ 仕様は「ダートは重・不良でBT値が高く出る」と書くが南関の実測は逆。
        補正は**足す**方向で正しい。"""
        self.assertGreater(bt.BABA_ADJ["不"], 0)


class TestPace(unittest.TestCase):
    def test_dev_is_ratio_difference(self):
        """⚠️ 前半の基準からのズレだけでは、全体が速いだけでもハイに見える。
        前半の比と上がりの比の**差**を取ること。"""
        # 全体が一様に3%速い＝ペースは中立
        d = bt.pace_dev({"win_time": 97.0, "last3f_race": 38.8}, 100.0, 40.0)
        self.assertAlmostEqual(d, 0.0, places=2)

    def test_high_pace_is_negative(self):
        """前半に寄った流れ（上がりが遅い）はマイナス。"""
        d = bt.pace_dev({"win_time": 100.0, "last3f_race": 41.0}, 100.0, 40.0)
        self.assertLess(d, 0)

    def test_slow_pace_is_positive(self):
        d = bt.pace_dev({"win_time": 100.0, "last3f_race": 39.0}, 100.0, 40.0)
        self.assertGreater(d, 0)

    def test_blend_off_by_default(self):
        """⚠️ 実測でペースの偏りを −1.09 → −1.37 に**悪化**させたので既定オフ。"""
        self.assertFalse(bt.PACE_BLEND_ON)


class TestTrackRatio(unittest.TestCase):
    def test_needs_enough_races(self):
        r = bt.day_ratio([], bt.BaseTime(), min_races=3)
        self.assertEqual((r.early, r.late), (1.0, 1.0))

    def test_label(self):
        self.assertEqual(bt.TrackRatio(0.95, 0.95).label, "高速馬場")
        self.assertEqual(bt.TrackRatio(1.05, 1.05).label, "時計のかかる馬場")
        self.assertEqual(bt.TrackRatio(1.0, 1.0).label, "標準")


class TestTen3f(unittest.TestCase):
    def test_only_multiples_of_200(self):
        self.assertTrue(bt.ten3f_ok(1200))
        self.assertFalse(bt.ten3f_ok(1500))
        self.assertFalse(bt.ten3f_ok(None))


if __name__ == "__main__":
    unittest.main()
