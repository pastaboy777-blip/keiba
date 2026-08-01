"""中央(JRA)穴馬抽出 jra_ana のテスト。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import jra_ana as ja           # noqa: E402
from nankeiba.core.interval import RunRecord      # noqa: E402
from nankeiba.scraping import keibabook as kb     # noqa: E402


def run(date, place, surf, dist, *, finish=5, margin=0.5, time=None,
        baba="良", klass="３歳以上１勝クラス", pace="M", pop=None):
    return RunRecord(date=date, place=place, distance=dist, field_size=12,
                     finish_pos=finish, surface=surf, baba=baba, popularity=pop,
                     time_sec=time, margin_sec=margin, pace_mark=pace,
                     race_class=klass, race_name=klass)


class TestWinTimeRestore(unittest.TestCase):
    """自分の着順を使わず、レースの勝ちタイムを復元できるか。"""

    def test_loser_subtracts_margin(self):
        r = run("2026-05-16", "新潟", "芝", 1800, finish=4, margin=1.0, time=109.1)
        self.assertAlmostEqual(r.win_time_sec(), 108.1, places=6)

    def test_winner_uses_own_time(self):
        r = run("2026-05-16", "新潟", "芝", 1800, finish=1, margin=0.0, time=108.1)
        self.assertAlmostEqual(r.win_time_sec(), 108.1)

    def test_missing_margin_is_none(self):
        r = run("2026-05-16", "新潟", "芝", 1800, finish=4, margin=None, time=109.1)
        self.assertIsNone(r.win_time_sec())

    def test_10th_in_a_fast_race_beats_winner_of_a_slow_one(self):
        """着順は見ない。10着でもレース自体が速ければ速いと判定する。"""
        fast10 = run("2026-05-16", "新潟", "芝", 1800, finish=10, margin=2.0, time=107.0)
        slow1 = run("2026-05-16", "新潟", "芝", 1800, finish=1, margin=0.0, time=110.0)
        self.assertLess(fast10.win_time_sec(), slow1.win_time_sec())


class TestClassOrd(unittest.TestCase):
    def test_ladder(self):
        self.assertEqual(ja.class_ord("３歳未勝利"), 0)
        self.assertEqual(ja.class_ord("３歳以上１勝クラス"), 1)
        self.assertEqual(ja.class_ord("３歳以上３勝クラス"), 3)
        self.assertEqual(ja.class_ord("柳都ステークス(3歳以上3勝クラス)"), 3)
        self.assertEqual(ja.class_ord("ＯＰ"), 4)

    def test_grade_beats_win_count(self):
        """'Ｇ１' を '1勝' と読み違えないこと。"""
        self.assertEqual(ja.class_ord("Ｇ１"), 7)
        self.assertEqual(ja.class_ord("G3"), 5)

    def test_unknown_is_none(self):
        self.assertIsNone(ja.class_ord(""))
        self.assertIsNone(ja.class_ord(None))


class TestTimeModel(unittest.TestCase):
    """既知の真値を仕込んで、係数と『何秒速いか』が復元できるかを見る。"""

    TRUE = {"芝": 55.0, "ダ": 58.0}       # 1kmあたり秒
    BABA = {("芝", "稍"): 0.8, ("芝", "重"): 2.2,
            ("ダ", "稍"): -0.2, ("ダ", "重"): -1.2}

    def _truth(self, surf, dist, baba):
        return self.TRUE[surf] * (dist / 1000.0) + self.BABA.get((surf, baba), 0.0)

    def _runs(self):
        runs = []
        i = 0
        for surf in ("芝", "ダ"):
            for dist in (1200, 1400, 1600, 1800, 2000):
                for baba in ("良", "稍", "重"):
                    for place in ("新潟", "中京", "札幌"):
                        i += 1
                        t = self._truth(surf, dist, baba)
                        runs.append(run(f"2026-01-{i % 28 + 1:02d}", place, surf, dist,
                                        finish=1, margin=0.0, time=t, baba=baba))
        return runs

    def test_baba_coefficients_have_the_right_sign(self):
        m = ja.TimeModel.fit(self._runs())
        self.assertIsNotNone(m)
        b = m.baba_report()
        self.assertGreater(b["芝稍"], 0, "芝は渋るほど遅いはず")
        self.assertGreater(b["芝重"], b["芝稍"])
        self.assertLess(b["ダ稍"], 0, "ダートは湿るほど速いはず")
        self.assertLess(b["ダ重"], b["ダ稍"])
        self.assertTrue(m.baba_sane())

    def test_standard_race_is_near_zero(self):
        m = ja.TimeModel.fit(self._runs())
        std = run("2026-03-01", "中京", "ダ", 1400, finish=1, margin=0.0,
                  time=self._truth("ダ", 1400, "良"))
        self.assertLess(abs(m.fast(std)), 0.30)

    def test_faster_race_scores_positive(self):
        m = ja.TimeModel.fit(self._runs())
        quick = run("2026-03-01", "中京", "ダ", 1400, finish=1, margin=0.0,
                    time=self._truth("ダ", 1400, "良") - 2.0)
        self.assertAlmostEqual(m.fast(quick), 2.0, delta=0.35)

    def test_same_race_gives_every_runner_the_same_index(self):
        """同じレースを使った2頭は、着順が違っても条件指数が同じになる。"""
        m = ja.TimeModel.fit(self._runs())
        t = self._truth("ダ", 1400, "良") - 1.5
        second = run("2026-03-01", "中京", "ダ", 1400, finish=2, margin=0.2, time=t + 0.2)
        eighth = run("2026-03-01", "中京", "ダ", 1400, finish=8, margin=1.7, time=t + 1.7)
        self.assertAlmostEqual(m.fast(second), m.fast(eighth), places=6)

    def test_one_race_counts_once_even_if_many_horses_used_it(self):
        """同じレースを複数頭が使っても、回帰の行は1本。"""
        base = self._runs()
        dup = [run("2026-03-01", "中京", "ダ", 1400, finish=f, margin=0.1 * f,
                   time=self._truth("ダ", 1400, "良") + 0.1 * f) for f in range(2, 12)]
        self.assertEqual(ja.TimeModel.fit(base + dup).n,
                         ja.TimeModel.fit(base).n + 1)

    def test_too_few_rows_returns_none(self):
        self.assertIsNone(ja.TimeModel.fit(self._runs()[:5]))


class TestFutureRaceLeak(unittest.TestCase):
    """⚠️ 馬柱に「まだ走っていない当日のレース」の行が混ざる回帰のテスト。"""

    def _mixed(self):
        past = run("2026-05-01", "中京", "ダ", 1400, time=85.0)
        today = run("2026-08-01", "中京", "ダ", 1400, time=82.7)
        return [today, past]

    def test_today_row_is_dropped(self):
        kept = ja.before_date(self._mixed(), "2026-08-01")
        self.assertEqual([r.date for r in kept], ["2026-05-01"])

    def test_no_date_keeps_everything(self):
        self.assertEqual(len(ja.before_date(self._mixed(), None)), 2)

    def test_debut_horse_gets_no_index(self):
        """キャリア0の新馬に指数が付いてしまう事故を防ぐ。"""
        m = TestTimeModel()
        model = ja.TimeModel.fit(m._runs())
        ents = [{"umaban": i, "name": f"新馬{i}", "popularity": i,
                 "runs": [run("2026-08-01", "中京", "芝", 1400, time=82.7)]}
                for i in (1, 2, 3)]
        cands, _ = ja.evaluate(ents, "芝", model=model, before="2026-08-01")
        self.assertTrue(all(c.cond_idx is None for c in cands))
        self.assertEqual([c.umaban for c in cands if c.passed], [])

    def test_shared_today_row_would_tie_every_runner(self):
        """フィルタしないと全馬が同じ1行を共有して条件指数が同値になる。"""
        m = TestTimeModel()
        model = ja.TimeModel.fit(m._runs())
        ents = [{"umaban": i, "name": f"新馬{i}", "popularity": i,
                 "runs": [run("2026-08-01", "中京", "芝", 1400, time=82.7)]}
                for i in (1, 2, 3)]
        # before を渡し忘れた場合（min_cond_runs=1 にすると素通りしてしまう）
        leaked, _ = ja.evaluate(ents, "芝", model=model, min_cond_runs=1)
        vals = {c.cond_idx for c in leaked}
        self.assertEqual(len(vals), 1, "全馬が同じ1行を共有して同値になる")
        self.assertIsNotNone(vals.pop())
        # 既定(min_cond_runs=2)なら1走しかない馬は弾かれるので二重に守られる
        guarded, _ = ja.evaluate(ents, "芝", model=model)
        self.assertTrue(all(c.cond_idx is None for c in guarded))

    def test_fit_ignores_future_rows(self):
        m = TestTimeModel()
        base = m._runs()
        fake = [run("2026-08-01", "中京", "ダ", 1400, time=70.0)]
        self.assertEqual(ja.TimeModel.fit(base + fake, before="2026-08-01").n,
                         ja.TimeModel.fit(base).n)


class TestGates(unittest.TestCase):
    """3つの門とスコア。"""

    def _entries(self):
        m = TestTimeModel()
        base = m._runs()
        ents = []
        # 1番: 今日の条件だけ速い / ふだんは平凡 / 人気なし  → 通る（＝穴）
        # 2番: 何でも速い / 1番人気                          → ①③で落ちる
        # 3番: 遅い / 人気なし                                → ①で落ちる
        # 4〜6番: 何でも一番速い人気馬（実力上位を埋める当て馬）→ ③で落ちる
        spec = [(1, -2.0, 0.0, 12, [8, 9, 10]),
                (2, -2.0, -2.0, 1, [1, 1, 2]),
                (3, +1.0, +1.0, 11, [7, 8, 9]),
                (4, -2.5, -2.5, 2, [2, 1, 3]),
                (5, -2.5, -2.5, 3, [3, 2, 1]),
                (6, -2.5, -2.5, 4, [1, 3, 2])]
        for um, cond_gain, other_gain, pop, hist in spec:
            # 条件指数は「今日と同じ馬場種の上位2走の平均」なのでダートを2走持たせる
            runs = [run(f"2026-03-0{j}", "中京", "ダ", 1400, finish=3, margin=0.3,
                        time=m._truth("ダ", 1400, "良") + cond_gain + 0.3, pop=hist[0])
                    for j in (1, 2)]
            for j, p in enumerate(hist[1:], 1):
                runs.append(run(f"2026-02-0{j}", "中京", "芝", 1600, finish=3, margin=0.3,
                                time=m._truth("芝", 1600, "良") + other_gain + 0.3, pop=p))
            ents.append({"umaban": um, "name": f"馬{um}", "runs": runs,
                         "popularity": pop})
        return base, ents

    def test_only_the_mispriced_horse_passes(self):
        base, ents = self._entries()
        model = ja.TimeModel.fit(base + [r for e in ents for r in e["runs"]])
        cands, _ = ja.evaluate(ents, "ダ", model=model)
        passed = [c.umaban for c in cands if c.passed]
        self.assertEqual(passed, [1])

    def test_power_median_differs_from_max(self):
        """実力=全走ベストだと条件指数と同じ値になり、門②が働かなくなる。"""
        base, ents = self._entries()
        model = ja.TimeModel.fit(base + [r for e in ents for r in e["runs"]])
        by_med = {c.umaban: c.power_idx
                  for c in ja.evaluate(ents, "ダ", model=model, power="median")[0]}
        by_max = {c.umaban: c.power_idx
                  for c in ja.evaluate(ents, "ダ", model=model, power="max")[0]}
        self.assertLess(by_med[1], by_max[1])

    def test_score_formula(self):
        c = ja.Cand(umaban=7, name="x", cond_idx=2.04, market=6.0, ana_wins=2)
        self.assertAlmostEqual(2.04 + 0.5 * 2 + 0.06 * 6.0, 3.40, places=2)
        self.assertAlmostEqual(
            c.cond_idx + ja.W_ANA * c.ana_wins + ja.W_POP * c.market, 3.40, places=2)

    def test_market_prefers_today_then_odds_then_recent(self):
        runs = [run("2026-03-01", "中京", "ダ", 1400, pop=9),
                run("2026-02-01", "中京", "ダ", 1400, pop=9)]
        ents = [{"umaban": 1, "popularity": 3, "odds": 99.0, "runs": runs},
                {"umaban": 2, "odds": 4.5, "runs": runs},
                {"umaban": 3, "odds": 12.0, "runs": runs},
                {"umaban": 4, "runs": runs},
                {"umaban": 5, "runs": []}]
        m = ja.market_of(ents)
        self.assertEqual(m[1], (3.0, "当日人気"))
        self.assertEqual(m[2], (1.0, "オッズ順"))      # 4.5 が最低オッズ
        self.assertEqual(m[3], (2.0, "オッズ順"))
        self.assertEqual(m[4], (9.0, "近2走人気"))
        self.assertEqual(m[5], (None, "-"))

    def test_odds_rank_ignores_horses_without_odds(self):
        """オッズの無い馬（取消など）は順位に混ぜない。"""
        ents = [{"umaban": 1, "odds": None, "runs": []},
                {"umaban": 2, "odds": 3.0, "runs": []},
                {"umaban": 3, "odds": 8.0, "runs": []}]
        m = ja.market_of(ents)
        self.assertEqual(m[2][0], 1.0)
        self.assertEqual(m[3][0], 2.0)
        self.assertIsNone(m[1][0])

    def test_ana_wins_counts_longshot_placings_only(self):
        runs = [run("2026-03-01", "中京", "ダ", 1400, finish=2, pop=8),   # ○
                run("2026-02-01", "中京", "ダ", 1400, finish=1, pop=1),   # 人気なので×
                run("2026-01-01", "中京", "ダ", 1400, finish=9, pop=12)]  # 着外なので×
        self.assertEqual(ja._ana_wins(runs), 1)


class TestSensitivity(unittest.TestCase):
    def test_stable_pick_is_reported_as_unanimous(self):
        base, ents = TestGates()._entries()
        model = ja.TimeModel.fit(base + [r for e in ents for r in e["runs"]])
        tally, n = ja.sensitivity(ents, "ダ", model=model)
        self.assertEqual(n, 9)
        self.assertEqual(tally, {1: 9})


NAV_HTML = """
<ul class="race clearfix">
<li class="active otherrace_new" id="01" value="2歳未勝利 <br>芝・1000m">
  <a href="202602070301">1R</a></li>
<li class="otherrace_new" id="02" value="2歳新馬 <br>芝外・1800m">
  <a href="202602070302">2R</a></li>
<li class="otherrace_new" id="06" value="月岡温泉特別(3歳以上2勝クラス ) <br>ダ・1200m">
  <a href="202602070306">6R</a></li>
</ul>
"""


class TestMeetingNav(unittest.TestCase):
    """⚠️ 本文検索だと『どのレースでも1Rの距離』が返る回帰のテスト。"""

    def test_each_race_gets_its_own_distance(self):
        nav = kb.parse_meeting_races_cyuou(NAV_HTML)
        self.assertEqual(len(nav), 3)
        self.assertEqual(nav["202602070301"]["distance"], 1000)
        self.assertEqual(nav["202602070302"]["distance"], 1800)
        self.assertEqual(nav["202602070306"]["distance"], 1200)

    def test_surface_course_and_name(self):
        nav = kb.parse_meeting_races_cyuou(NAV_HTML)
        self.assertEqual(nav["202602070302"]["surface"], "芝")
        self.assertEqual(nav["202602070302"]["course"], "外")
        self.assertEqual(nav["202602070301"]["course"], None)
        self.assertEqual(nav["202602070306"]["surface"], "ダ")
        self.assertEqual(nav["202602070306"]["race_name"],
                         "月岡温泉特別(3歳以上2勝クラス )")

    def test_active_race_is_included(self):
        """開いているレースは class='active otherrace_new' になる。"""
        self.assertIn("202602070301", kb.parse_meeting_races_cyuou(NAV_HTML))

    def test_header_uses_race_id(self):
        hd = kb.parse_race_header_cyuou(NAV_HTML, "202602070306")
        self.assertEqual((hd["surface"], hd["distance"]), ("ダ", 1200))


SYUTUBA_HTML = """
<table class="syutuba">
<tr><th>枠番</th><th>馬番</th><th>My印</th><th>本紙</th><th>馬　名</th><th>性齢</th>
    <th>騎　手</th><th>重量</th><th>厩　舎</th><th>レイティング</th>
    <th>単勝</th><th>人気</th></tr>
<tr><td>1</td><td>1</td><td>-</td><td>◎</td>
    <td><a href="/db/uma/0953955">ヴェニゼロス ★</a></td><td>牝3</td>
    <td>戸崎圭</td><td>55</td><td>美林</td><td>54.0</td><td>5.9</td><td>2</td></tr>
<tr><td>2</td><td>4</td><td>-</td><td></td>
    <td><a href="/db/uma/0946238">キリスパークル ★</a></td><td>牝3</td>
    <td>石橋脩</td><td>55</td><td>美勢司</td><td>52.6</td><td>65.3</td><td>15</td></tr>
</table>
"""


class TestParseEntries(unittest.TestCase):
    """⚠️ 予想家の印の列数は可変。見出しで引くこと(位置決め打ち禁止)。"""

    def test_reads_odds_and_popularity(self):
        ents = kb.parse_entries(SYUTUBA_HTML)
        self.assertEqual([e["umaban"] for e in ents], [1, 4])
        self.assertEqual(ents[0]["name"], "ヴェニゼロス")
        self.assertEqual(ents[0]["odds"], 5.9)
        self.assertEqual(ents[0]["popularity"], 2)
        self.assertEqual(ents[1]["odds"], 65.3)
        self.assertEqual(ents[1]["popularity"], 15)
        self.assertEqual(ents[0]["jockey"], "戸崎圭")
        self.assertEqual(ents[0]["kinryo"], 55.0)

    def test_survives_an_extra_pundit_column(self):
        shifted = (SYUTUBA_HTML
                   .replace("<th>My印</th>", "<th>My印</th><th>吉田幹</th>")
                   .replace("<td>-</td>", "<td>-</td><td>△</td>"))
        ents = kb.parse_entries(shifted)
        self.assertEqual([e["umaban"] for e in ents], [1, 4])
        self.assertEqual(ents[0]["odds"], 5.9)
        self.assertEqual(ents[0]["popularity"], 2)


if __name__ == "__main__":
    unittest.main()


class TestPeakEstimator(unittest.TestCase):
    """⚠️ max はノイズの最大値を拾う。上位k走の平均を使う。"""

    def test_top2_mean(self):
        self.assertAlmostEqual(ja.peak([3.0, 1.0, 2.0, 0.0]), 2.5)
        self.assertAlmostEqual(ja.peak([3.0, 1.0, 2.0, 0.0], k=3), 2.0)

    def test_one_run_is_itself(self):
        self.assertAlmostEqual(ja.peak([1.7]), 1.7)

    def test_max_is_dragged_by_a_single_outlier_but_top2_is_not(self):
        steady = [2.2, 2.2, 2.2, 2.2]
        fluke = [4.0, 0.0, 0.0, 0.0]
        self.assertGreater(max(fluke), max(steady))          # max だと一発が勝つ
        self.assertGreater(ja.peak(steady), ja.peak(fluke))  # 上位2走なら逆転する

    def test_needs_min_runs(self):
        m = TestTimeModel()
        model = ja.TimeModel.fit(m._runs())
        one = [{"umaban": 1, "name": "一走馬", "popularity": 9,
                "runs": [run("2026-03-01", "中京", "ダ", 1400, time=81.0)]}]
        self.assertIsNone(ja.evaluate(one, "ダ", model=model)[0][0].cond_idx)
        self.assertIsNotNone(
            ja.evaluate(one, "ダ", model=model, min_cond_runs=1)[0][0].cond_idx)

    def test_reports_how_many_runs_and_how_long_ago(self):
        m = TestTimeModel()
        model = ja.TimeModel.fit(m._runs())
        runs = [run("2026-06-01", "中京", "ダ", 1400, time=85.0),   # 1走前(遅い)
                run("2026-05-01", "中京", "芝", 1600, time=88.0),   # 芝なので条件外
                run("2026-04-01", "中京", "ダ", 1400, time=79.0),   # 3走前(速い)
                run("2026-03-01", "中京", "ダ", 1400, time=80.0)]
        c = ja.evaluate([{"umaban": 1, "name": "x", "popularity": 9, "runs": runs}],
                        "ダ", model=model)[0][0]
        self.assertEqual(c.cond_runs, 3)
        self.assertEqual(c.n_runs, 4)
        self.assertEqual(c.cond_ago, 3, "ピークは3走前＝市場はもう忘れている")


class TestAgeCond(unittest.TestCase):
    def test_split(self):
        self.assertEqual(ja.age_cond("２歳新馬"), "2")
        self.assertEqual(ja.age_cond("３歳未勝利"), "3")
        self.assertEqual(ja.age_cond("３歳１勝クラス"), "3")
        self.assertEqual(ja.age_cond("３歳上１勝クラス"), "old")
        self.assertEqual(ja.age_cond("３歳以上２勝クラス"), "old")
        self.assertEqual(ja.age_cond("桶狭間Ｓ"), "old")

    def test_two_year_olds_are_not_lumped_with_maidens(self):
        """クラス序列だけだと2歳新馬と3歳未勝利がどちらも0になってしまう。"""
        self.assertEqual(ja.class_ord("２歳新馬"), ja.class_ord("３歳未勝利"))
        self.assertNotEqual(ja.age_cond("２歳新馬"), ja.age_cond("３歳未勝利"))

    def test_is_a_regression_term(self):
        m = ja.TimeModel.fit(TestTimeModel()._runs())
        self.assertIn("2歳戦", m.names)
        self.assertIn("3歳限定", m.names)


class TestBasis(unittest.TestCase):
    """⚠️ レースの勝ち時計だけだと順位付けの力がほぼ無い（実測 +0.095）。

    自分の走破タイム（レースの速さ − 着差）を土台にすると +0.319 になった。
    着差は着順ではなく**時計の差**なので、オッズを見ない原則は保たれている。
    """

    def _model(self):
        return ja.TimeModel.fit(TestTimeModel()._runs())

    def test_race_basis_ignores_the_margin(self):
        m = self._model()
        t = TestTimeModel()._truth("ダ", 1400, "良")
        won = run("2026-03-01", "中京", "ダ", 1400, finish=1, margin=0.0, time=t)
        lost = run("2026-03-01", "中京", "ダ", 1400, finish=9, margin=3.0, time=t + 3.0)
        self.assertAlmostEqual(m.fast(won), m.fast(lost), places=6)

    def test_self_basis_separates_them(self):
        m = self._model()
        t = TestTimeModel()._truth("ダ", 1400, "良")
        won = run("2026-03-01", "中京", "ダ", 1400, finish=1, margin=0.0, time=t)
        lost = run("2026-03-01", "中京", "ダ", 1400, finish=9, margin=3.0, time=t + 3.0)
        self.assertAlmostEqual(m.fast_self(won) - m.fast_self(lost), 3.0, places=6)

    def test_a_beaten_horse_in_a_fast_race_still_scores_well(self):
        """5馬身離されても、レースが速ければ良い数字になる（着順では切らない）。"""
        m = self._model()
        t = TestTimeModel()._truth("ダ", 1400, "良")
        beaten_in_fast = run("2026-03-01", "中京", "ダ", 1400, finish=8,
                             margin=1.0, time=t - 3.0 + 1.0)
        won_slow = run("2026-03-01", "中京", "ダ", 1400, finish=1, margin=0.0, time=t)
        self.assertGreater(m.fast_self(beaten_in_fast), m.fast_self(won_slow))

    def test_margin_weight_interpolates(self):
        m = self._model()
        t = TestTimeModel()._truth("ダ", 1400, "良")
        r = run("2026-03-01", "中京", "ダ", 1400, finish=5, margin=2.0, time=t + 2.0)
        self.assertAlmostEqual(m.fast_self(r, 0.5) - m.fast_self(r, 1.0), 1.0, places=6)

    def test_missing_margin_falls_out(self):
        m = self._model()
        r = run("2026-03-01", "中京", "ダ", 1400, finish=5, margin=None, time=85.0)
        self.assertIsNone(m.fast_self(r))

    def test_evaluate_default_is_self(self):
        base, ents = TestGates()._entries()
        model = ja.TimeModel.fit(base + [r for e in ents for r in e["runs"]])
        a = {c.umaban: c.cond_idx for c in ja.evaluate(ents, "ダ", model=model)[0]}
        b = {c.umaban: c.cond_idx
             for c in ja.evaluate(ents, "ダ", model=model, basis="race")[0]}
        self.assertNotEqual(a, b)
        # 着差0.3秒ぶんだけ self のほうが低く出る
        self.assertAlmostEqual(b[1] - a[1], 0.3, places=6)


class TestVerifyNameJoin(unittest.TestCase):
    """⚠️ 出馬表の (外)(地) 接頭辞で名寄せが静かに落ちる回帰のテスト。"""

    def setUp(self):
        import importlib.util
        path = os.path.join(os.path.dirname(__file__), "..", "scripts", "jra_verify.py")
        spec = importlib.util.spec_from_file_location("jra_verify", path)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_strips_origin_prefix(self):
        n = self.mod.norm_name
        self.assertEqual(n("(外)パーシャングレー"), "パーシャングレー")
        self.assertEqual(n("（地）サトノドルチェ"), "サトノドルチェ")
        self.assertEqual(n("パーシャングレー"), "パーシャングレー")

    def test_leaves_normal_names_alone(self):
        n = self.mod.norm_name
        self.assertEqual(n("ハヤテノオジョー"), "ハヤテノオジョー")
        self.assertEqual(n(" タイキインドラ "), "タイキインドラ")

    def test_entry_and_result_forms_join(self):
        n = self.mod.norm_name
        self.assertEqual(n("(外)パーシャングレー"), n("パーシャングレー"))
