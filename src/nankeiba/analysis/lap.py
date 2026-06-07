"""ハロンタイム(200mごとのラップ)を区間分析する純ロジック(標準ライブラリのみ)。

入力は「12.7-12.7-13.0-...」のような200mごとのラップ列。これに対して
  - スタート〜直線のコーナー区間ラベル付け(大井の標準コース構成に基づく目安)
  - テン3F / 上がり3F / 中盤、前後半バランス
  - ペース判定(ハイ/ミドル/スロー)
  - 200m換算の系列(グラフ用)
を計算する。可視化は render.py が担当する。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# ラップ列のパース
# ---------------------------------------------------------------------------

def parse_furlong_times(s: str) -> list[float]:
    """'12.7-12.7-13.0' のような文字列を [12.7, 12.7, 13.0] に変換する。

    区切りは「-」「－(全角)」「,」「空白」を許容。数値以外は無視する。
    """
    if not s:
        return []
    tokens = re.split(r"[-－,\s]+", s.strip())
    out: list[float] = []
    for t in tokens:
        t = t.strip()
        if not t:
            continue
        try:
            out.append(round(float(t), 2))
        except ValueError:
            continue
    return out


# ---------------------------------------------------------------------------
# 大井コースの区間ラベル付け(目安)
# ---------------------------------------------------------------------------
# 画像の1600m(8ハロン)に一致するよう、先頭4区間を head、末尾4区間を tail に
# 固定し、距離が伸びた分(中盤)は「向正面」を補う。短距離は head 側を削る。
# あくまで標準的なコース構成からの目安で、施行位置の微差は無視している。

_HEAD = ["スタート〜1C", "1C〜2C", "2C〜向正面", "向正面"]
_TAIL = ["向正面〜3C", "3C〜4C", "4C〜直線", "直線"]


def oi_segment_labels(n: int) -> list[str]:
    """200m区間が n 個あるときの大井コーナー区間ラベル列を返す。"""
    if n <= 0:
        return []
    if n <= len(_TAIL):
        # 1〜4区間しかない(超短距離)。末尾側だけ使う。
        return _TAIL[len(_TAIL) - n:]
    head_room = n - len(_TAIL)
    if head_room < len(_HEAD):
        # 中距離未満。head の後ろ側だけ採用(スタート寄りを削る)。
        head = _HEAD[len(_HEAD) - head_room:]
        return head + _TAIL
    # 中盤を「向正面」で埋める
    mid = ["向正面"] * (head_room - len(_HEAD))
    return _HEAD + mid + _TAIL


# ---------------------------------------------------------------------------
# 分析結果
# ---------------------------------------------------------------------------

@dataclass
class LapAnalysis:
    distance: int                 # m
    furlongs: list[float]         # 200mごとのラップ
    cum: list[float]              # 累積タイム(各200m通過)
    marks: list[int]              # 各区間の終端距離 [200,400,...]
    labels: list[str]             # コーナー区間ラベル
    race_time: float              # 走破タイム(ラップ合計)
    ten_3f: float | None          # テン3F(前半3ハロン)
    last_3f: float | None         # 上がり3F(後半3ハロン)
    first_half: float | None      # 前半(距離半分)
    second_half: float | None     # 後半
    first_half_n: int             # 前半のハロン数
    second_half_n: int            # 後半のハロン数
    avg_furlong: float            # 平均ハロン
    fastest_idx: int              # 最速ハロンの位置(0始まり)
    slowest_idx: int              # 最遅ハロンの位置
    pace: str                     # 'ハイペース'/'ミドルペース'/'スローペース'
    balance: str                  # 前傾/後傾/平坦
    note: str = ""                # 距離が200mで割り切れない等の注記


def _sum(xs: list[float]) -> float:
    return round(sum(xs), 2)


def analyze(furlongs: list[float], distance: int, *, reported_last_3f: float | None = None) -> LapAnalysis:
    """200mラップ列を分析する。distance は m(例: 2000)。"""
    n = len(furlongs)
    note = ""
    if n == 0:
        raise ValueError("ラップ(ハロンタイム)が空です")
    if distance <= 0:
        distance = n * 200
    # 距離とハロン数の整合チェック(端数距離=最初の区間が200m未満のことがある)
    expected = distance / 200.0
    if abs(expected - n) >= 1:
        note = f"距離{distance}mに対しハロン数{n}が不整合(端数距離の可能性)"

    cum: list[float] = []
    acc = 0.0
    for x in furlongs:
        acc = round(acc + x, 2)
        cum.append(acc)
    marks = [200 * (i + 1) for i in range(n)]

    race_time = _sum(furlongs)
    ten_3f = _sum(furlongs[:3]) if n >= 3 else None
    # 上がり3Fは公式値があればそれを優先(端数区間で末尾がずれるため)
    if reported_last_3f is not None:
        last_3f = round(reported_last_3f, 2)
    else:
        last_3f = _sum(furlongs[-3:]) if n >= 3 else None
    half = n // 2
    first_half = _sum(furlongs[:half]) if half else None
    second_half = _sum(furlongs[half:]) if half else None
    avg_furlong = round(race_time / n, 2)
    fastest_idx = min(range(n), key=lambda i: furlongs[i])
    slowest_idx = max(range(n), key=lambda i: furlongs[i])

    # ペース判定: テン3Fと上がり3Fの差で前後半の緩急を見る
    pace = "ミドルペース"
    balance = "平坦"
    if ten_3f is not None and last_3f is not None:
        diff = round(ten_3f - last_3f, 2)  # 正=前半が遅い(後半勝負), 負=前傾(前半速い)
        if diff <= -0.8:
            pace, balance = "ハイペース", "前傾(前半速い)"
        elif diff >= 0.8:
            pace, balance = "スローペース", "後傾(上がり勝負)"
        else:
            pace, balance = "ミドルペース", "平坦"

    return LapAnalysis(
        distance=distance, furlongs=furlongs, cum=cum, marks=marks,
        labels=oi_segment_labels(n), race_time=race_time,
        ten_3f=ten_3f, last_3f=last_3f, first_half=first_half, second_half=second_half,
        first_half_n=half, second_half_n=(n - half),
        avg_furlong=avg_furlong, fastest_idx=fastest_idx, slowest_idx=slowest_idx,
        pace=pace, balance=balance, note=note,
    )


def analyze_str(furlong_str: str, distance: int, **kw) -> LapAnalysis:
    """'12.7-12.7-...' 文字列を直接分析するショートカット。"""
    return analyze(parse_furlong_times(furlong_str), distance, **kw)


@dataclass
class RaceLap:
    """1レース分のメタ情報 + ラップ分析。render に渡す単位。"""
    race_id: str
    place: str
    race_no: int
    date: str                 # 'YYYY-MM-DD'
    race_name: str
    surface: str              # 'ダ'/'芝'
    distance: int
    going: str                # 馬場状態(良/稍重/重/不良)
    weather: str              # 天候
    furlong_str: str          # 元のハロンタイム文字列
    analysis: LapAnalysis
    corners: list[str] = field(default_factory=list)  # コーナー通過順位(任意)
