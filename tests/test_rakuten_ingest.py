"""楽天競馬 出馬表パーサ(ingest/rakuten.py)の単体テスト。

実サイトHTMLの要点だけを再現した最小フィクスチャで、
レース条件・馬番・馬名・単勝/人気(通常馬・人気馬hot・穴馬dark)・前走の
着順/場/距離/頭数/馬場/通過順/上がりが取れることを確認する。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.ingest import rakuten


FIXTURE = """
<html><head><title>川崎競馬場 出馬表 | 2026/06/15 6R ：楽天競馬</title></head>
<body>
2026年6月15日 第3回 川崎競馬 第1日 ダ1,400m 天候： 曇 ダ： 重 発走時刻 17:30
<h1>川崎競馬場 6R 出馬表</h1>
<h2>郭公（かっこう）賞　３歳４</h2>
<table>
<thead><tr><th>枠</th></tr></thead>
<tbody class="raceCard">
<tr class="box01" data-grouping="1">
  <th rowspan="3" class="position">1</th>
  <td rowspan="3" class="number">1</td>
  <td rowspan="3" class="name">シルバーステート<br>
    <span class="mainHorse"><a href="/horse/1">クイーンズステート</a></span><br>レザニティエ
    <div class="append">(Bernardini)
      <span class="rate">29.3 （6人気）</span>2023/1/28生<br>北原大史<br>追分ファーム生産</div></td>
  <td rowspan="3" class="profile">牝3<br>鹿毛<br>54.0<br>
    <a href="/jockey/JOCKEYID/31140">町田直</a><br>（川崎）<br>
    【<span class="hot">1.7%</span>】<br>【<span class="dark">14.0%</span>】<br>今井輝<br></td>
  <td rowspan="3" class="weight">390<br>|<br>394</td>
  <td rowspan="3" class="weightDistance">400<br>+4</td>
  <td rowspan="3" class="race place04"><div class="firstInfo">
    <span class="place">4</span><span class="noteInfo">
    <span class="stateInfo">良</span><span class="numberInfo">11頭</span></span></div>
    川崎 26.05.11<br><span class="raceName"><a href="/r">ブリーズ賞</a></span><br>
    ３歳４<br>1400左ダ 2人<br>野畑凌 54.0<br>1:33.7 (1.9)<br>41.3 396k 5番<br>5-4-4-4<br>ササキントモ<br></td>
</tr>
<tr class="box02"><td>x</td></tr><tr class="box03"><td>y</td></tr>
<tr class="box04" data-grouping="2">
  <th rowspan="3" class="position">2</th>
  <td rowspan="3" class="number">6</td>
  <td rowspan="3" class="name">チチ<br><span class="mainHorse"><a href="/h">ヒロキ</a></span><br>ハハ
    <div class="append">(Sire)<span class="rate"><span class="hot">1.3</span> （1人気）</span>2023生<br>馬主<br>牧場</div></td>
  <td rowspan="3" class="profile">牡3<br>栗毛<br>54.0<br>
    <a href="/jockey/JOCKEYID/1">騎手A</a><br>（川崎）<br>
    【<span class="hot">20%</span>】<br>【<span class="dark">40%</span>】<br>調教師A<br></td>
  <td rowspan="3" class="weight">500<br>|<br>500</td>
  <td rowspan="3" class="weightDistance">500<br>0</td>
  <td rowspan="3" class="race place01"><div class="firstInfo">
    <span class="place">1</span><span class="noteInfo">
    <span class="stateInfo">重</span><span class="numberInfo">12頭</span></span></div>
    川崎 26.06.01<br><span class="raceName"><a href="/r">特別</a></span><br>
    ３歳<br>1400左ダ 1人<br>騎手A 54.0<br>1:30.0 (0.5)<br>39.0 500k 1番<br>1-1-1-1<br>ウマ<br></td>
</tr>
</tbody>
</table>
</body></html>
"""


class TestRakutenIngest(unittest.TestCase):
    def setUp(self):
        self.card = rakuten.parse_race_card(FIXTURE)

    def test_meta(self):
        self.assertEqual(self.card["place"], "川崎")
        self.assertEqual(self.card["race_no"], 6)
        self.assertEqual(self.card["date"], "2026-06-15")
        self.assertEqual(self.card["distance"], 1400)
        self.assertEqual(self.card["surface"], "ダ")
        self.assertEqual(self.card["baba"], "重")
        self.assertEqual(self.card["post_time"], "17:30")
        self.assertIn("郭公", self.card["race_name"])

    def test_horses_basic(self):
        hs = {h["umaban"]: h for h in self.card["horses"]}
        self.assertEqual(set(hs), {1, 6})
        self.assertEqual(hs[1]["name"], "クイーンズステート")
        self.assertEqual(hs[1]["odds"], 29.3)
        self.assertEqual(hs[1]["popularity"], 6)
        self.assertEqual(hs[1]["jockey"], "町田直")
        self.assertEqual(hs[1]["trainer"], "今井輝")

    def test_hot_horse_odds(self):
        # 人気馬は <span class="hot"> 内にオッズが入る。取りこぼさないこと。
        hs = {h["umaban"]: h for h in self.card["horses"]}
        self.assertEqual(hs[6]["name"], "ヒロキ")
        self.assertEqual(hs[6]["odds"], 1.3)
        self.assertEqual(hs[6]["popularity"], 1)

    def test_past_run(self):
        h1 = {h["umaban"]: h for h in self.card["horses"]}[1]
        self.assertEqual(len(h1["runs"]), 1)
        r = h1["runs"][0]
        self.assertEqual(r["finish_pos"], 4)
        self.assertEqual(r["place"], "川崎")
        self.assertEqual(r["date"], "2026-05-11")
        self.assertEqual(r["distance"], 1400)
        self.assertEqual(r["field_size"], 11)
        self.assertEqual(r["baba"], "良")
        self.assertEqual(r["corner_pos"], [5, 4, 4, 4])
        self.assertEqual(r["agari"], 41.3)


if __name__ == "__main__":
    unittest.main()
