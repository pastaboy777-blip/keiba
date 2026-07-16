"""ツイート生成 (core/tweet.py) の単体テスト。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.core import tweet as tw
from nankeiba.core.features import RaceContext, ScoreWeights
from nankeiba.core.interval import RunRecord


def _rr(date, place="船橋", dist=1000, fs=12, fp=3, baba="良",
        corner=(3, 3), agari=4):
    return RunRecord(date=date, place=place, distance=dist, field_size=fs,
                     finish_pos=fp, baba=baba, corner_pos=list(corner),
                     agari_rank=agari)


def _entry(um, name, pop, odds, records, jockey="X"):
    return tw.HorseEntry(um=um, name=name, win_odds=odds, popularity=pop,
                         records=records, jockey=jockey)


class IntervalPhraseTest(unittest.TestCase):
    def test_buckets(self):
        self.assertIsNone(tw.interval_phrase(None))
        self.assertEqual(tw.interval_phrase(6), "連闘")
        self.assertEqual(tw.interval_phrase(13), "中1週")
        self.assertEqual(tw.interval_phrase(19), "中2週")
        self.assertEqual(tw.interval_phrase(80), "休み明け")


class WeightedLenTest(unittest.TestCase):
    def test_cjk_counts_double(self):
        self.assertEqual(tw.tweet_weighted_len("abc"), 3)
        self.assertEqual(tw.tweet_weighted_len("あ"), 2)
        self.assertEqual(tw.tweet_weighted_len("aあ"), 3)


class SelectHonmeiTest(unittest.TestCase):
    """モデル上位×人気薄の馬を逆張り本命に選ぶことを確認する。"""

    def _field(self):
        ctx = RaceContext(date="2026-06-02", place="船橋", distance=1000,
                          field_size=3, baba="良")
        # 強い履歴だが人気薄の馬(um=3, pop=8) を仕込む
        strong = [_rr("2026-05-27", fp=1, corner=(1, 1), agari=1),
                  _rr("2026-05-20", fp=1, corner=(1, 1), agari=1),
                  _rr("2026-05-13", fp=2, corner=(2, 2), agari=2)]
        weak = [_rr("2026-04-01", fp=8, corner=(9, 9), agari=9),
                _rr("2026-02-01", fp=9, corner=(10, 10), agari=10)]
        entries = [
            _entry(1, "ニンキウマ", pop=1, odds=2.0, records=weak),
            _entry(2, "チュウカン", pop=2, odds=4.0, records=weak),
            _entry(3, "ダークホース", pop=8, odds=40.0, records=strong),
        ]
        return entries, ctx

    def test_dark_horse_chosen(self):
        entries, ctx = self._field()
        honmei, partners, _ = tw.select_honmei(entries, ctx, ScoreWeights())
        self.assertEqual(honmei.um, 3)  # モデル上位×人気薄を本命に
        self.assertNotIn(3, [p.um for p in partners])  # 本命は相手から除外

    def test_fallback_to_model_top_when_no_dark_horse(self):
        # 全馬が人気上位(pop<4)なら人気薄は居ないのでモデル1位を本命に
        entries, ctx = self._field()
        entries[2].popularity = 3  # ダークホースも人気側に
        honmei, _, _ = tw.select_honmei(entries, ctx, ScoreWeights())
        self.assertEqual(honmei.um, 3)  # モデル1位(強い履歴)がそのまま本命


class GenerateTest(unittest.TestCase):
    def _plan(self, link=None, roi=None):
        ctx = RaceContext(date="2026-06-02", place="船橋", distance=1000,
                          field_size=3, baba="良")
        strong = [_rr("2026-05-27", fp=1, corner=(1, 1), agari=1),
                  _rr("2026-05-20", fp=1, corner=(1, 1), agari=1)]
        weak = [_rr("2026-04-01", fp=8, corner=(9, 9), agari=9)]
        entries = [
            _entry(1, "ニンキウマ", pop=1, odds=2.0, records=weak),
            _entry(2, "チュウカン", pop=2, odds=4.0, records=weak),
            _entry(3, "ダークホース", pop=8, odds=40.0, records=strong),
        ]
        return tw.generate(entries, ctx, race_label="11R", link=link, roi_pct=roi)

    def test_reasons_and_drafts(self):
        plan = self._plan()
        self.assertLessEqual(len(plan.reasons), 3)
        self.assertTrue(plan.reasons)
        styles = {d.style for d in plan.drafts}
        self.assertIn("gyakubari", styles)
        self.assertIn("iwakan", styles)

    def test_link_never_in_body_only_in_reply(self):
        link = "https://twitcasting.tv/test"
        plan = self._plan(link=link)
        for d in plan.drafts:
            self.assertNotIn(link, d.body, f"本文にリンクが混入: {d.style}")
            self.assertNotIn("http", d.body)
            self.assertTrue(any(link in r for r in d.replies),
                            f"リンクがリプに無い: {d.style}")

    def test_roi_adds_number_draft(self):
        plan = self._plan(roi=128)
        self.assertIn("suuji", {d.style for d in plan.drafts})
        suuji = next(d for d in plan.drafts if d.style == "suuji")
        self.assertIn("128", suuji.body)

    def test_no_roi_no_number_draft(self):
        plan = self._plan()
        self.assertNotIn("suuji", {d.style for d in plan.drafts})

    def test_drafts_within_x_limit(self):
        plan = self._plan(roi=128)
        for d in plan.drafts:
            self.assertFalse(d.over_limit, f"{d.style} が280超: {d.weighted_len}")


class ResultsTest(unittest.TestCase):
    def _items(self):
        return [
            tw.ResultItem(day="水", place="浦和", race="5R", pick="シヴァシン",
                          kind="単勝", odds=50, result="1着"),
            tw.ResultItem(day="木", place="浦和", race="8R", pick="3連単",
                          kind="3連単", odds=173, result="大本線",
                          reasons=["上位人気が間隔詰めすぎ", "穴馬が叩き3走目",
                                   "前残りの展開"]),
            tw.ResultItem(day="木", place="浦和", race="9R", pick="マッドスピード",
                          kind="複勝", payout=960, result="3着"),
        ]

    def test_bullet_no_kind_duplication(self):
        # pick が券種名を含む場合、券種を二重に出さない
        item = tw.ResultItem(place="浦和", race="8R", pick="3連単",
                             kind="3連単", odds=173, result="大本線")
        self.assertEqual(item.bullet().count("3連単"), 1)

    def test_bullet_shows_odds_and_result(self):
        item = tw.ResultItem(day="水", place="浦和", race="5R", pick="シヴァシン",
                             kind="単勝", odds=50, result="1着")
        b = item.bullet()
        self.assertIn("単勝50倍", b)
        self.assertIn("シヴァシン", b)
        self.assertIn("1着", b)

    def test_drafts_generated_and_fit_limit(self):
        drafts = tw.generate_results(self._items(), link="https://twitcasting.tv/x")
        styles = {d.style for d in drafts}
        self.assertEqual(styles, {"matome", "highlight", "kensho"})
        for d in drafts:
            self.assertFalse(d.over_limit, f"{d.style} が280超: {d.weighted_len}")

    def test_highlight_picks_biggest(self):
        drafts = tw.generate_results(self._items())
        hl = next(d for d in drafts if d.style == "highlight")
        self.assertIn("173倍", hl.body)  # 最大インパクト(単勝50倍より3連単173倍)

    def test_link_only_in_replies(self):
        link = "https://twitcasting.tv/x"
        drafts = tw.generate_results(self._items(), link=link)
        for d in drafts:
            self.assertNotIn(link, d.body)
            self.assertTrue(any(link in r for r in d.replies))

    def test_matome_trims_and_notes_extra(self):
        # 大量の実績を渡すと280に収めるため一部を落として件数を注記する
        many = self._items() * 5  # 15件
        drafts = tw.generate_results(many)
        matome = next(d for d in drafts if d.style == "matome")
        self.assertFalse(matome.over_limit)
        self.assertIn("ほか", matome.body)

    def test_kensho_only_when_reasons(self):
        no_reason = [tw.ResultItem(place="浦和", race="5R", pick="シヴァシン",
                                   kind="単勝", odds=50, result="1着")]
        styles = {d.style for d in tw.generate_results(no_reason)}
        self.assertNotIn("kensho", styles)

    def test_empty_items(self):
        self.assertEqual(tw.generate_results([]), [])


if __name__ == "__main__":
    unittest.main()
