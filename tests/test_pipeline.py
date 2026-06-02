"""核心ロジックの単体テスト(標準ライブラリ unittest のみ)。

実行: python3 -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.core import interval as iv
from nankeiba.core import probability as pb
from nankeiba.core import betting as bt
from nankeiba.core import synth
from nankeiba.core.backtest import run_backtest
from nankeiba.core.features import (
    RaceContext, ConnStats, ScoreWeights, FEATURE_NAMES,
    horse_score, horse_features, starts_since_layoff,
)
from nankeiba.core import learn as L
from math import isfinite

try:
    import bs4  # noqa: F401  スクレイピングのパーサテストに必要(任意依存)
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False


class TestInterval(unittest.TestCase):
    def test_buckets(self):
        self.assertEqual(iv.interval_bucket(7), "rento")
        self.assertEqual(iv.interval_bucket(15), "naka1")
        self.assertEqual(iv.interval_bucket(30), "normal")
        self.assertEqual(iv.interval_bucket(200), "long_kyuyo")
        self.assertEqual(iv.interval_bucket(None), "unknown")

    def test_prior_short_better(self):
        # 南関は短間隔ほど有利
        self.assertGreater(iv.global_interval_prior(7), iv.global_interval_prior(90))

    def test_profile_fills_intervals(self):
        runs = [
            iv.RunRecord("2024-03-01", "大井", 1400, 12, 1),
            iv.RunRecord("2024-02-20", "大井", 1400, 12, 3),
            iv.RunRecord("2024-02-10", "川崎", 1400, 12, 5),
        ]
        prof = iv.build_profile(runs)
        self.assertEqual(prof.n_runs, 3)
        self.assertGreater(prof.ability, 0.0)


class TestTatakii(unittest.TestCase):
    def test_layoff_is_first(self):
        runs = [iv.RunRecord("2024-01-01", "大井", 1400, 12, 5)]
        # 休み明け(間隔なし)→ 叩き1走目
        self.assertEqual(starts_since_layoff(runs, None), 1)

    def test_counts_after_layoff(self):
        runs = [
            iv.RunRecord("2024-03-01", "大井", 1400, 12, 2),  # 直近(間隔12日)
            iv.RunRecord("2024-02-18", "大井", 1400, 12, 4),  # 休み明け(90日)
        ]
        runs[0].days_since_last = 12
        runs[1].days_since_last = 90
        # 今回も12日 → 休み明けから数えて3走目
        self.assertEqual(starts_since_layoff(runs, 12), 3)


class TestProbability(unittest.TestCase):
    def test_trifecta_sums_to_one(self):
        s = {1: 3.0, 2: 2.0, 3: 1.0, 4: 0.5}
        probs = pb.trifecta_probabilities(s)
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=6)

    def test_trio_sums_to_one(self):
        s = {1: 3.0, 2: 2.0, 3: 1.0, 4: 0.5}
        probs = pb.trio_probabilities(s)
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=6)

    def test_stronger_horse_more_likely(self):
        s = {1: 5.0, 2: 1.0, 3: 1.0, 4: 1.0}
        self.assertGreater(pb.top3_probability(s, 1), pb.top3_probability(s, 2))


class TestBetting(unittest.TestCase):
    def test_only_positive_ev_selected(self):
        probs = {(1, 2, 3): 0.10, (1, 2, 4): 0.05}
        odds = {(1, 2, 3): 15.0, (1, 2, 4): 5.0}  # EV: 1.5, 0.25
        bets = bt.select_ev_bets(probs, odds, ev_threshold=1.1)
        self.assertEqual(len(bets), 1)
        self.assertEqual(bets[0].combo, (1, 2, 3))

    def test_settle_hit(self):
        bets = bt.select_ev_bets({(1, 2, 3): 0.2}, {(1, 2, 3): 10.0}, ev_threshold=1.0)
        spent, ret = bt.settle(bets, (1, 2, 3))
        self.assertEqual(spent, 100.0)
        self.assertEqual(ret, 1000.0)


class TestBacktestSmoke(unittest.TestCase):
    def test_runs_and_produces_sane_output(self):
        # 合成データ上のエッジは小さく乱数に敏感(実データ検証が必須)。
        # ここではパイプラインが健全に動き、妥当な範囲の数値を返すことだけ確認する。
        races, jockeys, trainers = synth.generate_season(n_races=300, seed=1)
        res = run_backtest(races, jockeys=jockeys, trainers=trainers,
                           bet_type="trio", ev_threshold=1.3, min_history=4)
        self.assertEqual(res.n_races, 300)
        self.assertGreater(res.spent, 0)
        self.assertGreater(res.n_bet_races, 0)
        self.assertTrue(0.2 < res.roi < 5.0, f"ROI out of sane range: {res.roi}")


class TestFeatures(unittest.TestCase):
    def test_feature_keys_match_names(self):
        runs = [iv.RunRecord("2024-02-20", "大井", 1400, 12, 3)]
        ctx = RaceContext("2024-03-01", "大井", 1400, 12, jockey="J01")
        feats = horse_features(runs, ctx)
        self.assertEqual(set(feats), set(FEATURE_NAMES))

    def test_senkou_and_agari(self):
        from nankeiba.core.features import senkou_power, agari_sharpness
        # 逃げ(通過1番手)・最速上がり の馬は先行力+・末脚+
        front = [iv.RunRecord("2026-05-01", "船橋", 1000, 12, 1,
                              corner_pos=[1, 1], agari_rank=1)]
        back = [iv.RunRecord("2026-05-01", "船橋", 1000, 12, 8,
                             corner_pos=[12, 12], agari_rank=12)]
        self.assertGreater(senkou_power(front), senkou_power(back))
        self.assertGreater(agari_sharpness(front), agari_sharpness(back))
        # データ無しは 0(ニュートラル)
        self.assertEqual(senkou_power([iv.RunRecord("2026-05-01", "船橋", 1000, 12, 3)]), 0.0)

    def test_baba_fit(self):
        from nankeiba.core.features import baba_fit
        runs = [iv.RunRecord("2026-05-01", "船橋", 1000, 12, 1, baba="良"),
                iv.RunRecord("2026-04-01", "船橋", 1000, 12, 10, baba="重")]
        ctx = RaceContext("2026-06-01", "船橋", 1000, 12, baba="良")
        # 良馬場で好走(baseline 0.5)→ 正
        self.assertGreater(baba_fit(runs, ctx, 0.5), 0.0)

    def test_score_is_weighted_dot(self):
        runs = [iv.RunRecord("2024-02-20", "大井", 1400, 12, 3)]
        ctx = RaceContext("2024-03-01", "大井", 1400, 12, jockey="J01")
        feats = horse_features(runs, ctx)
        w = ScoreWeights()
        expected = sum(w.as_dict()[f] * feats[f] for f in FEATURE_NAMES)
        self.assertAlmostEqual(horse_score(runs, ctx, weights=w), expected, places=9)


class TestDataset(unittest.TestCase):
    def test_roundtrip_and_backtest(self):
        import tempfile, os
        from nankeiba.core import dataset as ds
        races, jockeys, trainers = synth.generate_season(n_races=120, seed=2)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "r.jsonl")
            ds.save_races(races, path)
            loaded = ds.load_races(path)
        self.assertEqual(len(loaded), len(races))
        # 往復後も馬番キーのオッズ・着順が保たれ、バックテストが動く
        res = run_backtest(loaded, jockeys=jockeys, trainers=trainers,
                           bet_type="trio", min_history=4)
        self.assertEqual(res.n_races, len(races))
        self.assertGreaterEqual(res.spent, 0)

    def test_derive_conn_stats(self):
        from nankeiba.core import dataset as ds
        races, _, _ = synth.generate_season(n_races=200, seed=5)
        jockeys, trainers = ds.derive_conn_stats(races)
        self.assertTrue(0.0 < jockeys.default < 1.0)
        # 推定勝率は妥当な範囲
        for r in list(jockeys.rates.values())[:20]:
            self.assertTrue(0.0 <= r <= 1.0)


@unittest.skipUnless(_HAS_BS4, "beautifulsoup4 が必要")
class TestOddsParser(unittest.TestCase):
    """楽天競馬オッズページ(人気高配当順リスト)のパース。"""

    def _page(self, rows: str) -> str:
        return ("<html><body><div id='ninkiKohaitoJun'><table>"
                "<tr><th>順位</th><th>組番</th><th>オッズ</th></tr>"
                f"{rows}</table></div></body></html>")

    def test_trio_keys_sorted(self):
        from nankeiba.scraping import odds as O
        html = self._page(
            "<tr><td>1</td><td>8-3-5</td><td><span class='hot'>42.1</span></td></tr>"
            "<tr><td>2</td><td>1-2-4</td><td><span>10.0</span></td></tr>")
        d = O.parse_odds_html(html, bet_type="trio")
        self.assertIn((3, 5, 8), d)            # 三連複は昇順化
        self.assertAlmostEqual(d[(3, 5, 8)], 42.1)

    def test_trifecta_keeps_order(self):
        from nankeiba.scraping import odds as O
        html = self._page(
            "<tr><td>1</td><td>5→3→8</td><td><span>210.4</span></td></tr>")
        d = O.parse_odds_html(html, bet_type="trifecta")
        self.assertIn((5, 3, 8), d)            # 三連単は着順保持
        self.assertAlmostEqual(d[(5, 3, 8)], 210.4)

    def test_skips_unsold_and_invalid(self):
        from nankeiba.scraping import odds as O
        html = self._page(
            "<tr><td>1</td><td>2-4-6</td><td><span>-</span></td></tr>"   # 発売外
            "<tr><td>2</td><td>3-3-7</td><td><span>5.0</span></td></tr>"  # 同番(不正)
            "<tr><td>3</td><td>1-2-3</td><td><span>1,234.5</span></td></tr>")  # カンマ
        d = O.parse_odds_html(html, bet_type="trio")
        self.assertNotIn((2, 4, 6), d)
        self.assertEqual(len(d), 1)
        self.assertAlmostEqual(d[(1, 2, 3)], 1234.5)


@unittest.skipUnless(_HAS_BS4, "beautifulsoup4 が必要")
class TestResultParser(unittest.TestCase):
    """楽天競馬 競走成績ページのパース。"""

    def test_parse_result_rows(self):
        from nankeiba.scraping import parser as P
        html = (
            "<html><body><li class='distance'>ダ1,200m</li>"
            "<table><tr><th class='order'>着順</th><th class='horse'>馬名</th></tr>"
            "<tbody>"
            "<tr><td class='order'>2</td><th class='position'>3</th>"
            "<td class='number'>5</td>"
            "<td class='horse'><a href='/horse_detail/detail/HORSEID/2820260025'>ウマA</a></td>"
            "<td class='jockey'>西村栄<br>(船橋)</td><td class='tamer'>佐々功</td>"
            "<td class='time'>1:17.4</td><td class='rank'>5</td></tr>"
            "<tr><td class='order'>1</td><th class='position'>1</th>"
            "<td class='number'>2</td>"
            "<td class='horse'><a href='/horse_detail/detail/HORSEID/120250133'>ウマB</a></td>"
            "<td class='jockey'>澤田龍<br>(船橋)</td><td class='tamer'>長谷剛</td>"
            "<td class='time'>1:17.1</td><td class='rank'>2</td></tr>"
            "<tr><td class='order'>中止</td><th class='position'>2</th>"
            "<td class='number'>9</td>"
            "<td class='horse'><a href='/horse_detail/detail/HORSEID/999'>ウマC</a></td>"
            "<td class='jockey'>誰か</td><td class='tamer'>厩舎</td>"
            "<td class='time'></td><td class='rank'></td></tr>"
            "</tbody></table></body></html>")
        race = P.parse_result_page(html, "202606021914030201")
        self.assertEqual(race.place, "船橋")          # RACEID 由来(19=船橋)
        self.assertEqual(race.distance, 1200)
        self.assertEqual(race.surface, "ダ")
        self.assertEqual(race.field_size, 2)          # 中止馬は除外
        self.assertEqual([r.finish_pos for r in race.rows], [1, 2])  # 着順ソート
        winner = race.rows[0]
        self.assertEqual(winner.umaban, 2)
        self.assertEqual(winner.horse_id, "120250133")
        self.assertEqual(winner.jockey, "澤田龍")     # 所属(船橋)を除去
        self.assertEqual(winner.trainer, "長谷剛")
        self.assertEqual(winner.popularity, 2)

    def test_parse_race_links(self):
        from nankeiba.scraping import parser as P
        html = (
            "<a href='/race_card/list/RACEID/202606021900000000'>一覧</a>"   # 末尾00=除外
            "<a href='/race_card/list/RACEID/202606021914030201'>1R</a>"
            "<a href='/race_card/list/RACEID/202606021914030211'>11R</a>"
            "<a href='/race_card/list/RACEID/202606022014030201'>他場</a>")  # 場違い
        links = P.parse_race_links(html, date_yyyymmdd="20260602", jyo_code="19")
        self.assertEqual(links, [(1, "202606021914030201"),
                                 (11, "202606021914030211")])

    def test_parse_card_entry_with_past_run(self):
        from nankeiba.scraping import parser as P
        html = (
            "<html><body><li class='distance'>ダ2,200m</li>"
            "<table><tr>"
            "<th class='position'>1</th><td class='number'>5</td>"
            "<td class='name'>サトノ <a href='/horse_detail/detail/HORSEID/120230894'>"
            "ウマ名</a> 母名 (母父) 7.6 （3人気） 2022/4/24生 馬主</td>"
            "<td class='profile'>牡4 鹿毛 56.0 野畑凌 （川崎） 【 1.4% 】 【 10.5% 】 村田順</td>"
            "<td class='weightDistance'>478 +1</td>"
            "<td class='race place06'><div class='firstInfo'><span class='place'>6</span>"
            "<span class='stateInfo'>良</span><span class='numberInfo'>13頭</span></div>"
            "川崎 26.05.14<br><span class='raceName'>"
            "<a href='/race_performance/list/RACEID/202605142100000009'>レイノ賞</a></span><br>"
            "Ｃ１<br>1600左ダ<br>13人<br>増田充<br>56.0<br>1:46.1 (0.4)<br>"
            "40.1 477k 9番<br>13-13-11-7<br>相手馬</td>"
            "</tr></table></body></html>")
        card = P.parse_card_page(html, "202606021914030211")
        self.assertEqual(card.place, "船橋")           # RACEID 由来
        self.assertEqual(card.distance, 2200)
        self.assertEqual(len(card.entries), 1)
        e = card.entries[0]
        self.assertEqual(e.umaban, 5)
        self.assertEqual(e.horse_id, "120230894")
        self.assertEqual(e.horse_name, "ウマ名")
        self.assertEqual(e.jockey, "野畑凌")
        self.assertEqual(e.jockey_win_rate, 1.4)
        self.assertEqual(e.trainer, "村田順")
        self.assertEqual(e.horse_weight_diff, 1)
        self.assertEqual(len(e.recent_runs), 1)
        pr = e.recent_runs[0]
        self.assertEqual(pr.date, "2026-05-14")        # リンク RACEID 由来
        self.assertEqual(pr.place, "川崎")
        self.assertEqual(pr.distance, 1600)
        self.assertEqual(pr.finish_pos, 6)
        self.assertEqual(pr.jockey, "増田充")           # 前走騎手(乗り替わり判定用)
        self.assertEqual(pr.corner, [13, 13, 11, 7])


@unittest.skipUnless(_HAS_BS4, "beautifulsoup4 が必要")
class TestEnrich(unittest.TestCase):
    """出馬表 -> 『走らせる』観点の特徴量・信号の導出。"""

    def _card(self):
        from nankeiba.scraping.parser import ParsedCard, CardEntry, PastRun
        run1 = PastRun(date="2026-05-14", place="川崎", distance=1600, surface="ダ",
                       field_size=13, finish_pos=6, popularity=5, jockey="増田充",
                       weight_carried=56.0, time="1:46.1", agari=40.1,
                       horse_weight=477, gate=9, corner=[13, 13, 11, 7],
                       baba="良", race_name="レイノ賞")
        run2 = PastRun(date="2026-05-02", place="船橋", distance=1800, surface="ダ",
                       field_size=12, finish_pos=3, popularity=4, jockey="増田充",
                       weight_carried=56.0, time="1:55.0", agari=39.5,
                       horse_weight=476, gate=4, corner=[6, 5, 4, 3],
                       baba="良", race_name="特別")
        entry = CardEntry(
            umaban=5, waku=1, horse_id="120230894", horse_name="ウマ名",
            sire=None, dam=None, sex_age="牡4", weight_carried=56.0,
            jockey="野畑凌", jockey_affil="川崎", jockey_win_rate=1.4,
            jockey_top3_rate=10.5, trainer="村田順", horse_weight=478,
            horse_weight_diff=1, exp_odds=7.6, exp_pop=3,
            recent_runs=[run1, run2])
        return ParsedCard(race_id="202606021914030211", date="2026-06-02",
                          place="船橋", distance=2200, surface="ダ",
                          field_size=1, race_name="11R", entries=[entry])

    def test_running_signals(self):
        from nankeiba.scraping import enrich as E
        rec = E.build_enriched_race(self._card())
        h = rec["horses"][0]
        s = h["signals"]
        self.assertEqual(s["days_since_last"], 19)          # 6/2 - 5/14
        self.assertEqual(s["interval_bucket"], "naka1")     # 中1〜2週
        self.assertTrue(s["jockey_changed"])                # 増田充 -> 野畑凌
        self.assertEqual(s["prev_jockey"], "増田充")
        self.assertTrue(s["place_changed"])                 # 川崎 -> 船橋
        self.assertEqual(s["distance_change"], 600)         # 1600 -> 2200
        # 「走らせる」特徴量がひと通り出ている
        for k in ("interval_fit", "toughness", "tatakii", "jockey_change"):
            self.assertIn(k, h["features"])

    def test_finish_label_attached(self):
        from nankeiba.scraping import enrich as E
        from nankeiba.scraping.parser import ParsedRace, ParsedRow
        result = ParsedRace(
            race_id="202606021914030211", date="2026-06-02", place="船橋",
            distance=2200, surface="ダ", field_size=1,
            rows=[ParsedRow(finish_pos=2, umaban=5, waku=1, horse_id="120230894",
                            horse_name="ウマ名", jockey="野畑凌", trainer="村田順",
                            popularity=3, time="2:20.0")])
        rec = E.build_enriched_race(self._card(), result)
        self.assertEqual(rec["result_order"], [5])
        self.assertEqual(rec["horses"][0]["finish_pos"], 2)   # ラベル付与


class TestUmaban(unittest.TestCase):
    def test_umaban_distinct_from_horse_id(self):
        races, _, _ = synth.generate_season(n_races=5, seed=9)
        race = races[0]
        # 馬番は 1..field_size、horse_id はプール全体のIDで別物
        umabans = sorted(e.umaban for e in race.entries)
        self.assertEqual(umabans, list(range(1, race.field_size + 1)))
        # オッズのキーは馬番(<= field_size)で構成される
        any_combo = next(iter(race.trio_odds))
        self.assertTrue(all(1 <= x <= race.field_size for x in any_combo))


class TestLearn(unittest.TestCase):
    def test_train_scorer_runs(self):
        races, jockeys, trainers = synth.generate_season(n_races=300, seed=3)
        scorer = L.train_scorer(races, jockeys=jockeys, trainers=trainers,
                                epochs=10, lr=0.2, min_history=4, seed=0)
        # 重みは有限で、全特徴量ぶんある
        self.assertEqual(set(scorer.weights), set(FEATURE_NAMES))
        self.assertTrue(all(isfinite(v) for v in scorer.weights.values()))
        # スコアラーは実数を返す
        ctx = RaceContext("2024-06-01", "大井", 1400, 10, jockey="J01")
        s = scorer([iv.RunRecord("2024-05-20", "大井", 1400, 10, 2)], ctx)
        self.assertTrue(isfinite(s))
        # importances は降順
        imps = [abs(v) for _, v in scorer.importances()]
        self.assertEqual(imps, sorted(imps, reverse=True))

    def test_backtest_accepts_score_fn(self):
        races, jockeys, trainers = synth.generate_season(n_races=300, seed=4)
        scorer = L.train_scorer(races, jockeys=jockeys, trainers=trainers,
                                epochs=10, min_history=4, seed=0)
        res = run_backtest(races, jockeys=jockeys, trainers=trainers,
                           score_fn=scorer, bet_type="trio", min_history=4)
        self.assertGreater(res.spent, 0)


if __name__ == "__main__":
    unittest.main()
