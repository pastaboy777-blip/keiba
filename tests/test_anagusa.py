"""穴ぐさ流モジュール（anagusa / cross / attrsplit）のテスト。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import anagusa, cross, attrsplit
from nankeiba.core.interval import RunRecord


def _run(date, place, dist, fld, fin, baba="良", surf="ダ", days=None):
    return RunRecord(date=date, place=place, distance=dist, field_size=fld,
                     finish_pos=fin, baba=baba, surface=surf, days_since_last=days)


class TestAnagusa(unittest.TestCase):
    def test_distance_slice_surfaces_as_angle(self):
        # 1400では好走(1,2,3着)、1800では凡走(着外)。今日1400 → 1400角度が立つ。
        runs = [
            _run("2026-07-01", "大井", 1400, 12, 1),
            _run("2026-06-01", "大井", 1400, 12, 2),
            _run("2026-05-01", "大井", 1800, 12, 10),
            _run("2026-04-01", "大井", 1800, 12, 11),
            _run("2026-03-01", "大井", 1400, 12, 3),
        ]
        cond = anagusa.Condition(place="大井", distance=1400, surface="ダ", baba="良")
        res = anagusa.analyze(runs, cond)
        self.assertGreater(res.n_runs, 0)
        self.assertTrue(res.hits, "角度が1つ以上立つはず")
        best = res.best
        # 1400のスライスは複勝率100%
        dist_hits = [h for h in res.hits if h.axis == "距離"]
        self.assertTrue(dist_hits)
        self.assertEqual(dist_hits[0].value, "ダ1400")
        self.assertEqual(dist_hits[0].rate, 1.0)
        self.assertEqual(dist_hits[0].record_str(), "①②③着")

    def test_baba_group(self):
        self.assertEqual(anagusa._baba_group("稍重"), "道悪")
        self.assertEqual(anagusa._baba_group("良"), "良")
        self.assertEqual(anagusa._baba_group("不良"), "道悪")
        self.assertIsNone(anagusa._baba_group(None))

    def test_empty(self):
        res = anagusa.analyze([], anagusa.Condition(distance=1400))
        self.assertEqual(res.n_runs, 0)
        self.assertIsNone(res.best)

    def test_min_n_filters_small_slices(self):
        runs = [_run("2026-07-01", "大井", 1600, 12, 1)]  # 1走だけ
        cond = anagusa.Condition(distance=1600, surface="ダ")
        res = anagusa.analyze(runs, cond, min_n=2)
        self.assertFalse([h for h in res.hits if h.axis == "距離"])


class TestCross(unittest.TestCase):
    def test_tags_of(self):
        self.assertIn(cross.DIRT_POWER, cross.tags_of("ストームキャット"))
        self.assertIn(cross.SPEED, cross.tags_of("ダンチヒ"))
        self.assertIn(cross.STAMINA, cross.tags_of("ニジンスキー"))
        self.assertEqual(cross.tags_of("存在しない馬"), set())

    def test_detect_cross_both_sides(self):
        occ = [
            cross.Occurrence("ストームキャット", 5, "sire"),
            cross.Occurrence("ストームキャット", 4, "dam"),
            cross.Occurrence("ダンチヒ", 4, "sire"),  # 片側だけ→クロスでない
        ]
        cs = cross.detect_crosses(occ)
        names = [c.ancestor for c in cs]
        self.assertIn("ストームキャット", names)
        self.assertNotIn("ダンチヒ", names)
        sc_tag = [c for c in cs if c.ancestor == "ストームキャット"][0]
        self.assertEqual(sc_tag.pattern, "5×4")
        self.assertEqual(sc_tag.closeness, 4)

    def test_score_matches_dirt_condition(self):
        occ = [
            cross.Occurrence("ストームキャット", 5, "sire"),
            cross.Occurrence("ストームキャット", 4, "dam"),
        ]
        # 道悪ダート → DIRT_POWER 濃縮が一致してスコアが立つ
        sc = cross.score(occ, surface="ダ", baba="重", distance=1200)
        self.assertGreater(sc.score, 0)
        self.assertTrue(sc.matched)
        self.assertIn("ストームキャット", sc.label())

    def test_score_no_match_on_turf_good(self):
        occ = [
            cross.Occurrence("ストームキャット", 5, "sire"),
            cross.Occurrence("ストームキャット", 4, "dam"),
        ]
        sc = cross.score(occ, surface="芝", baba="良", distance=2000)
        self.assertEqual(sc.matched, [])

    def test_occurrences_from_5gen(self):
        ped = {1: ["父", "母"], 2: ["父父", "父母", "母父", "母母"]}
        occ = cross.occurrences_from_5gen(ped)
        sires = [o for o in occ if o.side == "sire"]
        dams = [o for o in occ if o.side == "dam"]
        self.assertEqual({o.name for o in sires}, {"父", "父父", "父母"})
        self.assertEqual({o.name for o in dams}, {"母", "母父", "母母"})


class TestAttrSplit(unittest.TestCase):
    def _outs(self):
        # モーリス産駒 芝1400 の6走: 1,1,2,3,着外,着外 → [2.1.1.2]
        data = [
            (1, dict(sire="モーリス", surface="芝", distance=1400, waku=5)),
            (1, dict(sire="モーリス", surface="芝", distance=1400, waku=7)),
            (2, dict(sire="モーリス", surface="芝", distance=1400, waku=4)),
            (3, dict(sire="モーリス", surface="芝", distance=1400, waku=8)),
            (9, dict(sire="モーリス", surface="芝", distance=1400, waku=1)),
            (12, dict(sire="モーリス", surface="芝", distance=1400, waku=2)),
            (1, dict(sire="ディープ", surface="芝", distance=1400, waku=3)),
        ]
        return [attrsplit.Outcome(fin, a) for fin, a in data]

    def test_cross_stat(self):
        r = attrsplit.cross_stat(self._outs(),
                                 {"sire": "モーリス", "surface": "芝", "distance": 1400})
        self.assertEqual(r.bracket(), "[2.1.1.2]")
        self.assertAlmostEqual(r.fukusho, 4 / 6)

    def test_waku_range_filter(self):
        r = attrsplit.cross_stat(self._outs(),
                                 {"sire": "モーリス", "waku": (4, 8)})
        # 4-8枠: 1,1,2,3 → [2.1.1.0]
        self.assertEqual(r.bracket(), "[2.1.1.0]")

    def test_split_by_sire(self):
        d = attrsplit.split(self._outs(), lambda o: o.attrs["sire"], min_n=2)
        self.assertIn("モーリス", d)
        self.assertNotIn("ディープ", d)  # 1走のみ→min_n=2で除外

    def test_split_table_roundtrip(self):
        t = attrsplit.SplitTable.build(
            self._outs(),
            subject_fn=lambda o: o.attrs["sire"],
            cond_fn=lambda o: f"{o.attrs['surface']}{o.attrs['distance']}",
            min_n=2,
        )
        rec = t.lookup("モーリス", "芝1400")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.bracket(), "[2.1.1.2]")
        t2 = attrsplit.SplitTable.from_json(t.to_json())
        self.assertEqual(t2.lookup("モーリス", "芝1400").bracket(), "[2.1.1.2]")


if __name__ == "__main__":
    unittest.main()
