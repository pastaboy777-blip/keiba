"""Mの法則ベースの鮮度／硬直指標のテスト。

⚠️ 本家（今井雅宏氏）の理論そのものではなく、公開情報からの独自解釈の実装。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import mhousoku as M


def run(date="2026-07-14", place="大井", distance=1200, jockey="Ａ",
        finish_pos=8, popularity=8, corner_pos=(5,), field_size=10, gate=5):
    return dict(date=date, place=place, distance=distance, jockey=jockey,
                finish_pos=finish_pos, popularity=popularity,
                corner_pos=(list(corner_pos) if corner_pos else None),
                field_size=field_size, gate=gate)


class TestGekiso(unittest.TestCase):
    def test_longshot_in_the_money_is_gekiso(self):
        self.assertTrue(M.is_gekiso(run(finish_pos=3, popularity=9)))

    def test_favourite_winning_is_not_gekiso(self):
        """⚠️ 1着＝激走ではない。1番人気の1着は消耗が違う。"""
        self.assertFalse(M.is_gekiso(run(finish_pos=1, popularity=1)))

    def test_longshot_losing_is_not(self):
        self.assertFalse(M.is_gekiso(run(finish_pos=9, popularity=12)))

    def test_missing_data(self):
        self.assertFalse(M.is_gekiso(run(popularity=None)))


class TestShocks(unittest.TestCase):
    def test_no_history(self):
        self.assertEqual(M.shocks("大井", 1200, "Ａ", 3, 10, None,
                                  "2026-08-14", []), (0.0, []))

    def test_distance_change(self):
        s, t = M.shocks("大井", 1600, "Ａ", 5, 10, None, "2026-08-14",
                        [run(distance=1200, corner_pos=(5,))])
        self.assertTrue(any("延長" in x for x in t))

    def test_big_distance_change_scores_more(self):
        a, _ = M.shocks("大井", 1300, "Ａ", 5, 10, None, "2026-08-14",
                        [run(distance=1200, corner_pos=(5,))])
        b, _ = M.shocks("大井", 1700, "Ａ", 5, 10, None, "2026-08-14",
                        [run(distance=1200, corner_pos=(5,))])
        self.assertGreater(b, a)

    def test_extreme_position_last_time(self):
        """位置取りショックは前走が極端だったことを代理にしている（近似）。"""
        s, t = M.shocks("大井", 1200, "Ａ", 5, 10, None, "2026-08-14",
                        [run(corner_pos=(1,), field_size=10)])
        self.assertTrue(any("位置取り" in x for x in t))

    def test_middle_position_is_no_shock(self):
        s, t = M.shocks("大井", 1200, "Ａ", 5, 10, None, "2026-08-14",
                        [run(corner_pos=(5,), field_size=10)])
        self.assertFalse(any("位置取り" in x for x in t))

    def test_inner_draw_shock_needs_outer_before(self):
        outer = run(gate=12, field_size=14, corner_pos=(5,))
        s, t = M.shocks("大井", 1200, "Ａ", 2, 12, None, "2026-08-14", [outer])
        self.assertTrue(any("内枠" in x for x in t))

    def test_inner_to_inner_is_not_a_shock(self):
        inner = run(gate=1, field_size=14, corner_pos=(5,))
        s, t = M.shocks("大井", 1200, "Ａ", 2, 12, None, "2026-08-14", [inner])
        self.assertFalse(any("内枠" in x for x in t))

    def test_layoff(self):
        s, t = M.shocks("大井", 1200, "Ａ", 5, 10, None, "2026-08-14",
                        [run(date="2026-01-10", corner_pos=(5,))])
        self.assertTrue(any("休み明け" in x for x in t))

    def test_shocks_add_not_multiply(self):
        """「有効なショックが多いほど激走の可能性が上がる」＝足し算。
        1つ欠けたら0、という掛け算にしない。"""
        one = M.shocks("大井", 1600, "Ａ", 5, 10, None, "2026-08-14",
                       [run(distance=1200, corner_pos=(5,))])[0]
        two = M.shocks("大井", 1600, "Ｂ", 5, 10, None, "2026-08-14",
                       [run(distance=1200, corner_pos=(5,))])[0]
        self.assertGreater(two, one)


class TestStiffness(unittest.TestCase):
    def test_needs_two_runs(self):
        self.assertEqual(M.stiffness([run()]), (0.0, []))

    def test_no_gekiso_no_stiffness(self):
        """前走が平凡なら硬直は出ない。"""
        s, r = M.stiffness([run(finish_pos=8, popularity=3)] * 3)
        self.assertEqual(s, 0.0)

    def test_gekiso_creates_stiffness(self):
        """⚠️ **激走そのものが次走の減点材料**。買う材料しか持たない指数は
        ここで必ず外す。"""
        runs = [run(finish_pos=2, popularity=9)] + [run()] * 2
        s, r = M.stiffness(runs)
        self.assertGreater(s, 0)
        self.assertTrue(any("激走" in x for x in r))

    def test_gekiso_after_layoff_is_worse(self):
        plain = M.stiffness([run(finish_pos=2, popularity=9,
                                 date="2026-07-14")]
                            + [run(date="2026-07-01")] * 2)[0]
        after = M.stiffness([run(finish_pos=2, popularity=9,
                                 date="2026-07-14")]
                            + [run(date="2026-01-01")] * 2)[0]
        self.assertGreater(after, plain)

    def test_gekiso_at_odd_distance_is_worse(self):
        same = M.stiffness([run(finish_pos=2, popularity=9, distance=1200)]
                           + [run(distance=1200)] * 3)[0]
        odd = M.stiffness([run(finish_pos=2, popularity=9, distance=1800)]
                          + [run(distance=1200)] * 3)[0]
        self.assertGreater(odd, same)


class TestState(unittest.TestCase):
    def test_empty(self):
        st = M.state("大井", 1200, "Ａ", 3, 10, None, "2026-08-14", [])
        self.assertEqual(st.score, 0.0)

    def test_score_is_fresh_minus_stiff(self):
        st = M.MState(fresh=4.0, stiff=1.5)
        self.assertAlmostEqual(st.score, 2.5)

    def test_stiff_label_wins(self):
        """硬直が出ている馬は、鮮度が高くても消し表示にする。"""
        st = M.MState(fresh=5.0, stiff=3.0)
        self.assertIn("硬直", st.label())

    def test_fresh_label(self):
        self.assertIn("鮮度", M.MState(fresh=4.0).label())

    def test_dull_label(self):
        self.assertIn("変わり映え", M.MState(fresh=0.5).label())


class TestLeg(unittest.TestCase):
    def test_normalised(self):
        self.assertAlmostEqual(M.leg(run(corner_pos=(5,), field_size=10)), 0.5)

    def test_missing(self):
        self.assertIsNone(M.leg(run(corner_pos=None)))


if __name__ == "__main__":
    unittest.main()


class TestM3(unittest.TestCase):
    def test_needs_enough_runs(self):
        """⚠️ 走数が足りない馬を型に押し込まない。"""
        t = M.m3([run()] * 2)
        self.assertEqual(t.label(), "―")
        self.assertIn("走数不足", t.note())

    def test_front_runner_is_S(self):
        runs = [run(corner_pos=(1, 1), field_size=12, finish_pos=4)] * 6
        t = M.m3(runs)
        self.assertGreater(t.s, t.l)

    def test_no_condition_variety_is_not_M(self):
        """⚠️ **「材料が無い」と「まとまり系」は別。**いつも同じ条件で走って
        いる馬は得意条件から逆算できない。正規化すると3つとも0.333になって
        まとまり系と見分けが付かなくなる（実際そのバグを出した）。"""
        runs = [run(corner_pos=(6,), field_size=12, finish_pos=f)
                for f in (1, 2, 1, 2, 1, 2)]
        t = M.m3(runs)
        self.assertEqual(t.evidence, 0)
        self.assertEqual(t.label(), "―")
        self.assertIn("判定できない", t.note())

    def test_C_and_L_are_separated_by_conditions(self):
        """⚠️ CとLはどちらも「安定」だが意味が逆。**得意条件で分ける。**
        C系＝多頭数・内枠（摩擦が大きいレース）、L系＝少頭数・外枠（楽なレース）。
        抽象的な「着順の分散」で測っていたときは両者が分離しなかった。"""
        def by_field(small_good):
            out = []
            for i in range(3):
                out.append(run(field_size=14, gate=2,
                               finish_pos=10 if small_good else 1))
                out.append(run(field_size=8, gate=7,
                               finish_pos=1 if small_good else 10))
            return out
        l_horse = M.m3(by_field(True))     # 少頭数・外枠で走る
        c_horse = M.m3(by_field(False))    # 多頭数・内枠で走る
        self.assertGreater(l_horse.evidence, 0)
        self.assertGreater(l_horse.l, c_horse.l)
        self.assertGreater(c_horse.c, l_horse.c)

    def test_single_condition_cannot_be_typed(self):
        """1条件しか走っていない馬を型に押し込まない。"""
        same = M.m3([run(corner_pos=(6,), field_size=12, finish_pos=11,
                         distance=1200, place="大井")] * 6)
        self.assertEqual(same.label(), "―")

    def test_label_format(self):
        self.assertEqual(M.M3(s=0.9, c=0.3, l=0.1, n=6, evidence=3).label(), "S(L)")
        self.assertEqual(M.M3(s=0.9, c=0.85, l=0.1, n=6, evidence=3).label(),
                         "SC(L)")
        self.assertEqual(M.M3(s=0.34, c=0.33, l=0.33, n=6, evidence=3).label(),
                         "M")


class TestFieldStress(unittest.TestCase):
    def setUp(self):
        self.horses = {
            "唯一の休み明け": [run(date="2026-01-01")],
            "普通A": [run(date="2026-08-01")],
            "普通B": [run(date="2026-08-01")],
            "普通C": [run(date="2026-08-01")],
        }

    def test_alone_is_ihen(self):
        fs = M.field_stress(self.horses, "2026-08-14", "大井", 1200)
        self.assertGreater(fs["唯一の休み明け"].ihen, 0)
        self.assertTrue(any("唯一" in t for t in fs["唯一の休み明け"].tags))

    def test_common_condition_is_not_ihen(self):
        """⚠️ 半分が該当する条件は異端ではない。**1〜2頭のときだけ**加点する。
        分けないとほぼ全頭に札が付いて選別にならない（点火指数で62%に
        札が付いた失敗と同じ）。"""
        horses = {f"h{i}": [run(date="2026-01-01")] for i in range(8)}
        fs = M.field_stress(horses, "2026-08-14", "大井", 1200)
        self.assertEqual(fs["h0"].ihen, 0.0)

    def test_pace_pressure_counted(self):
        horses = {f"h{i}": [run(corner_pos=(1,), field_size=10)]
                  for i in range(4)}
        fs = M.field_stress(horses, "2026-08-14", "大井", 1200)
        self.assertGreaterEqual(fs["h0"].pressure, 4)
        self.assertTrue(fs["h0"].front_runner)

    def test_no_history(self):
        fs = M.field_stress({"x": []}, "2026-08-14", "大井", 1200)
        self.assertEqual(fs["x"].ihen, 0.0)


def r2(d, dist, fin, cp, marg=0.5, fld=12):
    return dict(date=d, place="大井", distance=dist, jockey="A",
                finish_pos=fin, popularity=5, corner_pos=list(cp),
                field_size=fld, gate=5, margin_sec=marg)


class TestCorner3(unittest.TestCase):
    def test_four_corners(self):
        self.assertEqual(M.corner3(r2("2026-01-01", 1600, 3, [4, 4, 5, 3])), 5)

    def test_three_corners(self):
        self.assertEqual(M.corner3(r2("2026-01-01", 1200, 3, [4, 5, 3])), 5)

    def test_two_corners(self):
        self.assertEqual(M.corner3(r2("2026-01-01", 1200, 3, [4, 3])), 4)

    def test_none(self):
        self.assertIsNone(M.corner3(r2("2026-01-01", 1200, 3, [])))


class TestTanshukuShocker(unittest.TestCase):
    def runs(self):
        return [r2("2026-07-20", 1600, 4, [3, 3, 4, 5]),
                r2("2026-07-01", 1200, 2, [2, 2]),
                r2("2026-06-10", 1200, 1, [1, 1])]

    def test_limited(self):
        """1と2を同時に満たすとリミテッド。"""
        tag, got, miss = M.tanshuku_shocker(1200, "ダ", "2026-08-14", self.runs())
        self.assertIn("リミテッド", tag)
        self.assertEqual(miss, [])

    def test_needs_placing_at_distance(self):
        """② 今走の距離以下で連対経験。無ければ成立しない。"""
        rs = [r2("2026-07-20", 1600, 4, [3, 3, 4, 5]),
              r2("2026-07-01", 1200, 8, [2, 2]),
              r2("2026-06-10", 1200, 9, [1, 1])]
        tag, got, miss = M.tanshuku_shocker(1200, "ダ", "2026-08-14", rs)
        self.assertEqual(tag, "")
        self.assertTrue(any("連対" in x for x in miss))

    def test_needs_forward_position(self):
        """③ 前走3角5番手以内。距離が長い前走で前に行けるテンションが要る。

        ⚠️ 前々走を今走と同距離にしないこと。それだとバウンド短縮が成立して
        ショッカー2で通ってしまう（テストの作り方でハマった）。"""
        rs = [r2("2026-07-20", 1600, 4, [9, 9, 10, 9]),
              r2("2026-07-01", 1800, 2, [9, 9, 9, 9]),
              r2("2026-06-10", 1200, 2, [2, 2])]
        tag, got, miss = M.tanshuku_shocker(1200, "ダ", "2026-08-14", rs)
        self.assertEqual(tag, "")
        self.assertTrue(any("3角" in x for x in miss))

    def test_not_a_shortening(self):
        rs = [r2("2026-07-20", 1200, 4, [3, 3]), r2("2026-07-01", 1200, 2, [2, 2])]
        tag, _, _ = M.tanshuku_shocker(1200, "ダ", "2026-08-14", rs)
        self.assertEqual(tag, "")

    def test_L_type_is_penalised(self):
        """⚠️ L系は短縮に向かない（ペースが速くなると投げ出す）。"""
        self.assertLess(M.SHOCK_FIT["短縮"]["L"], 1.0)
        self.assertGreater(M.SHOCK_FIT["短縮"]["S"], 1.0)
        self.assertGreater(M.SHOCK_FIT["短縮"]["C"], 1.0)


class TestEnchouRider(unittest.TestCase):
    def test_bound_extension(self):
        """2000先行 → 1600差し → 今走2000 の形。"""
        rs = [r2("2026-07-20", 1600, 6, [9, 9, 8, 7]),
              r2("2026-07-01", 2000, 3, [2, 2, 2, 3]),
              r2("2026-06-10", 2000, 2, [1, 1, 1, 1])]
        ok, got, miss = M.enchou_rider(2000, "2026-08-14", rs)
        self.assertTrue(ok)

    def test_needs_back_position_last_time(self):
        rs = [r2("2026-07-20", 1600, 6, [1, 1, 1, 1]),
              r2("2026-07-01", 2000, 3, [2, 2, 2, 3])]
        ok, got, miss = M.enchou_rider(2000, "2026-08-14", rs)
        self.assertFalse(ok)

    def test_L_type_suits_extension(self):
        """⚠️ 延長は揉まれ弱いL系が得意、摩擦で走るC系は不得手。"""
        self.assertGreater(M.SHOCK_FIT["延長"]["L"], M.SHOCK_FIT["延長"]["C"])


class TestSameDistanceShock(unittest.TestCase):
    def test_after_failed_shortening(self):
        """一度短縮して失敗 → 次走の同距離で狙う。"""
        rs = [r2("2026-07-20", 1200, 8, [5, 5]), r2("2026-07-01", 1600, 3, [3, 3])]
        kind, note = M.same_distance_shock(1200, rs)
        self.assertEqual(kind, "短縮後の同距離")

    def test_after_failed_extension(self):
        rs = [r2("2026-07-20", 1600, 9, [5, 5]), r2("2026-07-01", 1200, 3, [3, 3])]
        kind, _ = M.same_distance_shock(1600, rs)
        self.assertEqual(kind, "延長後の同距離")

    def test_not_if_already_ran_well(self):
        """⚠️ 前走で好走していたらこの形ではない（既に決まった後）。"""
        rs = [r2("2026-07-20", 1200, 1, [5, 5]), r2("2026-07-01", 1600, 3, [3, 3])]
        self.assertEqual(M.same_distance_shock(1200, rs)[0], "")


class TestNigerarenakatta(unittest.TestCase):
    def base(self):
        return [r2("2026-07-20", 1200, 9, [6, 6]),
                r2("2026-07-01", 1200, 1, [1, 1]),
                r2("2026-06-10", 1200, 2, [1, 1])]

    def test_detects(self):
        ok, note = M.nigerarenakatta(self.base(), pressure=1)
        self.assertTrue(ok)

    def test_blocked_when_many_front_runners(self):
        """今回も同型が多ければ、また逃げられない可能性が高い。"""
        ok, _ = M.nigerarenakatta(self.base(), pressure=4)
        self.assertFalse(ok)

    def test_needs_history_of_leading(self):
        """⚠️ 逃げられない＝単に活力低下、の可能性がある。過去に何度も
        逃げている馬に限ることで最低限ふるいにかける。"""
        rs = [r2("2026-07-20", 1200, 9, [6, 6]),
              r2("2026-07-01", 1200, 5, [5, 5]),
              r2("2026-06-10", 1200, 6, [6, 6])]
        self.assertFalse(M.nigerarenakatta(rs, pressure=1)[0])

    def test_not_if_led_last_time(self):
        rs = [r2("2026-07-20", 1200, 3, [1, 1]),
              r2("2026-07-01", 1200, 1, [1, 1]),
              r2("2026-06-10", 1200, 2, [1, 1])]
        self.assertFalse(M.nigerarenakatta(rs, pressure=1)[0])


class TestStress(unittest.TestCase):
    def test_close_finish_creates_stress(self):
        s, t = M.stress([r2("2026-07-20", 1200, 2, [3, 3], marg=0.1)])
        self.assertGreater(s, 0)
        self.assertTrue(any("接戦" in x for x in t))

    def test_winner_gets_relief(self):
        """⚠️ 勝ち馬は勝ったことでストレスが軽減される。"""
        w = M.stress([r2("2026-07-20", 1200, 1, [3, 3], marg=0.1)])[0]
        l = M.stress([r2("2026-07-20", 1200, 2, [3, 3], marg=0.1)])[0]
        self.assertLess(w, l)

    def test_blowout_win_is_no_stress(self):
        """圧勝するとほとんどストレスを貯めない。"""
        s, t = M.stress([r2("2026-07-20", 1200, 1, [1, 1], marg=1.5)])
        self.assertEqual(s, 0.0)
        self.assertTrue(any("圧勝" in x for x in t))

    def test_closing_creates_stress(self):
        s, t = M.stress([r2("2026-07-20", 1200, 4, [10, 9], marg=1.0)])
        self.assertTrue(any("追い込み" in x for x in t))

    def test_same_distance_stress(self):
        rs = [r2("2026-07-20", 1200, 5, [5, 5]), r2("2026-07-01", 1200, 5, [5, 5]),
              r2("2026-06-10", 1200, 5, [5, 5])]
        s, t = M.stress(rs)
        self.assertTrue(any("同距離" in x for x in t))


class TestAtypicalUpgrade(unittest.TestCase):
    def test_blowout_then_upgrade(self):
        ok, note = M.atypical_upgrade([r2("2026-07-20", 1200, 1, [1, 1], marg=1.5)],
                                      None)
        self.assertTrue(ok)

    def test_narrow_win_is_not(self):
        ok, _ = M.atypical_upgrade([r2("2026-07-20", 1200, 1, [1, 1], marg=0.2)],
                                   None)
        self.assertFalse(ok)


class TestRhythm(unittest.TestCase):
    def test_tight(self):
        rs = [r2(d, 1200, 5, [5, 5]) for d in
              ("2026-08-01", "2026-07-18", "2026-07-04", "2026-06-20")]
        self.assertEqual(M.rhythm(rs, "2026-08-14")[0], "使い詰め")

    def test_breather_after_tight(self):
        rs = [r2(d, 1200, 5, [5, 5]) for d in
              ("2026-06-01", "2026-05-20", "2026-05-06", "2026-04-22")]
        self.assertEqual(M.rhythm(rs, "2026-08-14")[0], "一息入れた")

    def test_not_enough_runs(self):
        self.assertEqual(M.rhythm([r2("2026-08-01", 1200, 5, [5, 5])],
                                  "2026-08-14")[0], "―")


class TestFatigue(unittest.TestCase):
    def test_more_runs_more_fatigue(self):
        a = M.fatigue([r2("2026-08-01", 1200, 5, [5, 5])], "2026-08-14")
        b = M.fatigue([r2(d, 1200, 5, [5, 5]) for d in
                       ("2026-08-01", "2026-07-18", "2026-07-04")], "2026-08-14")
        self.assertGreater(b, a)

    def test_old_runs_weigh_less(self):
        near = M.fatigue([r2("2026-08-10", 1200, 5, [5, 5])], "2026-08-14")
        far = M.fatigue([r2("2026-06-01", 1200, 5, [5, 5])], "2026-08-14")
        self.assertGreater(near, far)
