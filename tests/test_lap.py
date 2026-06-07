"""ラップ分析(analysis/lap.py, render.py, scraping/rakuten.py)のテスト。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.analysis import lap as L
from nankeiba.analysis import render as R
from nankeiba.scraping import rakuten as RK


def test_parse_furlong_times_variants():
    assert L.parse_furlong_times("12.7-11.6-13.5") == [12.7, 11.6, 13.5]
    assert L.parse_furlong_times("12.7－11.6") == [12.7, 11.6]  # 全角ハイフン
    assert L.parse_furlong_times("12.7, 11.6 13.5") == [12.7, 11.6, 13.5]
    assert L.parse_furlong_times("") == []


def test_segment_labels_match_image_1600():
    # 画像(大井1600m=8ハロン)のコーナー区間と一致すること
    assert L.oi_segment_labels(8) == [
        "スタート〜1C", "1C〜2C", "2C〜向正面", "向正面",
        "向正面〜3C", "3C〜4C", "4C〜直線", "直線",
    ]


def test_segment_labels_lengths():
    for n in range(1, 13):
        assert len(L.oi_segment_labels(n)) == n
    # 末尾は常に直線
    assert L.oi_segment_labels(10)[-1] == "直線"
    assert L.oi_segment_labels(6)[-1] == "直線"
    # 長距離は中盤を向正面で埋める
    assert L.oi_segment_labels(10).count("向正面") >= 2


def test_analyze_basic_1600():
    a = L.analyze_str("12.7-11.6-13.5-13.3-12.0-13.1-12.7-13.3", 1600)
    assert a.distance == 1600
    assert len(a.furlongs) == 8
    assert a.race_time == 102.2
    assert a.ten_3f == 37.8           # 12.7+11.6+13.5
    assert a.last_3f == 39.1          # 12.0+13.1... last3 = 13.1+12.7+13.3
    assert a.fastest_idx == 1         # 11.6
    assert a.slowest_idx == 2         # 13.5
    assert abs(a.avg_furlong - 12.78) < 0.01
    assert len(a.cum) == 8 and a.cum[-1] == 102.2


def test_analyze_uses_reported_last_3f():
    a = L.analyze_str("12.0-12.0-12.0-12.0-12.0-12.0", 1200, reported_last_3f=35.9)
    assert a.last_3f == 35.9


def test_pace_classification():
    # 前半速い → ハイペース
    hi = L.analyze_str("11.5-11.5-11.5-13.5-13.5-13.5", 1200)
    assert hi.pace == "ハイペース"
    # 後半速い → スローペース
    slow = L.analyze_str("13.5-13.5-13.5-11.5-11.5-11.5", 1200)
    assert slow.pace == "スローペース"
    # 平坦 → ミドル
    mid = L.analyze_str("12.5-12.5-12.5-12.5-12.5-12.5", 1200)
    assert mid.pace == "ミドルペース"


def test_render_text_and_html_smoke():
    a = L.analyze_str("12.7-11.6-13.5-13.3-12.0-13.1-12.7-13.3", 1600)
    race = L.RaceLap(
        race_id="x", place="大井", race_no=11, date="2026-05-18",
        race_name="テスト特別", surface="ダ", distance=1600, going="良",
        weather="晴", furlong_str="12.7-11.6-13.5-13.3-12.0-13.1-12.7-13.3",
        analysis=a,
    )
    txt = R.render_text(race)
    assert "大井11R" in txt and "ペース" in txt
    html = R.render_html([race], title="テスト")
    assert "<svg" in html and "ラップタイム" in html
    assert "スタート〜1C" in html and "直線" in html


# --- パーサ: 実HTML断片に近い構造でパースを検証 ---

_SAMPLE = """
<div class="raceTitle"><div class="placeNumber">
  <span class="racePlace">大井</span>
  <span class="raceNumber"><span class="num">9</span>R</span></div></div>
<div class="raceNote">
  <ul class="trackState"><li>2026年5月18日</li><li>第3回</li><li>大井競馬</li><li>第1日</li></ul>
  <ul class="trackState trackMainState">
    <li class="distance">ダ2,000m(外)</li>
    <li><dl><dt>天候：</dt><dd>晴</dd><dt>ダ：</dt><dd>良</dd><dt>発走時刻</dt><dd>18:55</dd></dl></li>
  </ul>
  <h2>東京ダービーチャレンジ競走　３歳　選抜馬オープン</h2>
</div>
<table class="contentsTable"><tbody class="record">
  <tr><th scope="row">ハロンタイム</th><td>12.7-12.7-13.0-13.5-13.3-12.8-12.8-13.3-12.3-12.7</td></tr>
  <tr><th scope="row">上がり</th><td>4F 51.1 - 3F 38.3</td></tr>
</tbody></table>
<h3>コーナー通過順位</h3><table><tbody class="record">
  <tr><th scope="row">１角</th><td class="time">4,6,(2,3),1,5-7</td></tr>
  <tr><th scope="row">２角</th><td class="time">4,6,(2,3)-1-5-7</td></tr>
</tbody></table>
"""


def test_parse_performance():
    rr = RK.parse_performance(_SAMPLE, "202605182015030109")
    assert rr.place == "大井"
    assert rr.race_no == 9
    assert rr.date == "2026-05-18"
    assert rr.surface == "ダ"
    assert rr.distance == 2000
    assert rr.going == "良"
    assert rr.weather == "晴"
    assert "東京ダービーチャレンジ" in rr.race_name
    assert rr.furlong_str == "12.7-12.7-13.0-13.5-13.3-12.8-12.8-13.3-12.3-12.7"
    assert rr.last_3f == 38.3
    assert len(rr.corners) == 2
    # パース結果がそのまま分析に流せること
    a = L.analyze(L.parse_furlong_times(rr.furlong_str), rr.distance, reported_last_3f=rr.last_3f)
    assert len(a.furlongs) == 10 and a.last_3f == 38.3
