"""今週の中央を間隔で仕分ける（scripts/jra_week.py）のテスト。"""

import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "jra_week", os.path.join(HERE, "..", "scripts", "jra_week.py"))
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)


def run(date, place="中山", pop=8, finish=2, field=16):
    return {"date": date, "place": place, "pop": pop,
            "finish": finish, "field": field}


class TestWeeks(unittest.TestCase):
    def test_weeks_between(self):
        self.assertAlmostEqual(W.weeks_between("2026-09-05", "20260919"), 2.0)
        self.assertAlmostEqual(W.weeks_between("2026-06-27", "20260919"), 12.0)

    def test_bad_input(self):
        self.assertIsNone(W.weeks_between("", "20260919"))
        self.assertIsNone(W.weeks_between("2026-09-05", "x"))


class TestClassify(unittest.TestCase):
    def test_gekiso_within_seven_weeks(self):
        """前走が人気薄で3着内、かつ詰めて使った＝反動が出る側。"""
        b, w, _ = W.classify([run("2026-09-05", pop=8, finish=2)], "20260919")
        self.assertEqual(b, "激走→7週以内")
        self.assertAlmostEqual(w, 2.0)

    def test_gekiso_after_seven_weeks(self):
        b, w, _ = W.classify([run("2026-06-27", pop=8, finish=2)], "20260919")
        self.assertEqual(b, "激走→7週超")

    def test_boundary_is_inclusive(self):
        """ちょうど7週は「以内」側。境界を動かすと数字が変わるので固定する。"""
        b, _, _ = W.classify([run("2026-08-01", pop=8, finish=2)], "20260919")
        self.assertEqual(b, "激走→7週以内")

    def test_popular_horse_is_not_gekiso(self):
        """⚠️ 1番人気の3着内は激走ではない。消耗が違う（mhousoku と同じ定義）。"""
        b, _, _ = W.classify([run("2026-09-05", pop=1, finish=1)], "20260919")
        self.assertEqual(b, "前走ふつう")

    def test_out_of_money_is_not_gekiso(self):
        """⚠️ 馬柱の着順は Ranking_N クラスにしか無く、**1〜3着にしか付かない**。
        4着以下は finish=None で来るので、激走にならないことを担保する。"""
        b, _, _ = W.classify([run("2026-09-05", pop=12, finish=None)], "20260919")
        self.assertEqual(b, "前走ふつう")

    def test_no_history(self):
        b, w, last = W.classify([], "20260919")
        self.assertEqual(b, "判定不能")
        self.assertIsNone(last)

    def test_uses_the_most_recent_run(self):
        """runs は新しい順。前走だけを見る。"""
        runs = [run("2026-09-05", pop=1, finish=1), run("2026-06-01", pop=9, finish=1)]
        b, _, last = W.classify(runs, "20260919")
        self.assertEqual(last["date"], "2026-09-05")
        self.assertEqual(b, "前走ふつう")


class TestConstantsAreShared(unittest.TestCase):
    def test_matches_mhousoku(self):
        """⚠️ 閾値を2か所に書かないこと。mhousoku と同じ値を使う。"""
        self.assertEqual(W.STIFF_WEEKS, W.M.STIFF_WEEKS)
        self.assertEqual(W.GEKISO_POP, W.M.GEKISO_POP)


class TestParseResult(unittest.TestCase):
    def test_parses_a_row(self):
        h = ('<tr class="HorseList">' + "".join(
            f"<td>{v}</td>" for v in
            ["1", "8", "9", "スマートブライド", "牝2", "55.0", "ルメール",
             "1:11.8", "", "3", "1.1", "37.8", "", "美浦 加藤征", "454(-2)"])
            + "</tr>")
        out = W.parse_result(h)
        self.assertEqual(out[9]["finish"], 1)
        self.assertEqual(out[9]["name"], "スマートブライド")
        self.assertEqual(out[9]["pop"], 3)


if __name__ == "__main__":
    unittest.main()
