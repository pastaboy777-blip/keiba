"""レース結果のラップ／ペース分析（南関・楽天データ版）。

楽天の結果ページ本文には **ハロンタイム（1ハロン=200mごとの実測ラップ）** と
**上がり4F/3F**、さらに **今走のコーナー通過順位** が載っている。これを使って:

  ・テン3F（前半3ハロン）と上がり3F の比較＝前傾/後傾
  ・ペース判定 H(ハイ)/M(平均)/S(スロー)
  ・決着傾向（前残り / 差し・追込有利）
  ・ラップの緩急（中盤が緩んだか＝瞬発力勝負か）
  ・上がり3F上位（速い脚を使った馬＝次走の狙い目）

実測ハロンタイムが取れない場合は、走破タイム−推定上がり3F で近似する。
指数予想の「展開読み」が当たっていたかの答え合わせに使う。依存ライブラリなし。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LapAnalysis:
    distance: int
    win_time: float | None            # 勝ちタイム(秒)
    avg_furlong: float | None         # 全体の平均1ハロン(秒)
    ten3f: float | None               # テン3F（前半3ハロン合計・秒）
    last3f: float | None              # 上がり3F（秒）
    balance: float | None             # テン3F − 上がり3F（負=前傾=ハイ）
    pace: str                         # "H"/"M"/"S"/"?"
    pace_label: str                   # 日本語ラベル
    bias: str                         # 決着傾向
    agari_top: list[tuple]            # [(umaban, name, agari, finish), ...]
    furlongs: list[float] = field(default_factory=list)   # 実測ラップ列
    source: str = "近似"              # "実測ラップ" / "近似"

    def lap_curve(self) -> str:
        return "-".join(f"{x:.1f}" for x in self.furlongs) if self.furlongs else "―"

    def summary(self) -> str:
        L = [f"距離{self.distance}m 勝ちタイム"
             + (f"{self.win_time:.1f}秒" if self.win_time else "―")]
        if self.avg_furlong:
            L.append(f"平均{self.avg_furlong:.1f}秒/F")
        if self.ten3f and self.last3f:
            L.append(f"テン3F{self.ten3f:.1f}→上がり3F{self.last3f:.1f}"
                     f"（差{self.balance:+.1f}）")
        L.append(f"{self.pace_label}／{self.bias}")
        L.append(f"[{self.source}]")
        return " ".join(L)


def _judge(balance: float) -> tuple[str, str, str]:
    """テン3F−上がり3F から ペース/ラベル/決着傾向。負=前傾=ハイ。"""
    if balance <= -1.0:
        return "H", "ハイペース", "差し・追込有利（前が垂れる消耗戦）"
    if balance >= 1.0:
        return "S", "スローペース", "前残り・逃げ先行有利（瞬発力勝負）"
    return "M", "平均ペース", "紛れ少・地力勝負"


def analyze(result: list[dict], distance: int, laps: dict | None = None) -> LapAnalysis:
    """parse_result と距離、任意で parse_lap の実測ラップから分析を返す。"""
    if not result or not distance:
        return LapAnalysis(distance, None, None, None, None, None, "?", "データ不足", "―", [])

    win = min(result, key=lambda r: r["finish"])
    wt = win.get("time_sec")
    avg_f = wt / (distance / 200.0) if wt else None

    ten3f = last3f = balance = None
    pace, plabel, bias = "?", "データ不足", "―"
    furlongs: list[float] = []
    source = "近似"

    # 1) 実測ハロンタイム優先
    if laps and laps.get("furlongs") and len(laps["furlongs"]) >= 6:
        furlongs = laps["furlongs"]
        ten3f = round(sum(furlongs[:3]), 1)
        last3f = laps.get("agari3f") or round(sum(furlongs[-3:]), 1)
        balance = round(ten3f - last3f, 1)
        pace, plabel, bias = _judge(balance)
        source = "実測ラップ"
    else:
        # 2) 近似: 前半(走破−上がり)平均F と 上がり平均F を比較
        wa = win.get("agari")
        if wt and wa and distance > 600:
            first_pace = (wt - wa) / ((distance - 600) / 200.0)
            last_pace = wa / 3.0
            last3f = wa
            balance = round((first_pace - last_pace) * 3, 1)   # 3F換算に揃える
            pace, plabel, bias = _judge(balance)

    with_ag = [(r["umaban"], r.get("name", ""), r["agari"], r["finish"])
               for r in result if r.get("agari")]
    with_ag.sort(key=lambda t: t[2])

    return LapAnalysis(distance, wt, avg_f, ten3f, last3f, balance,
                       pace, plabel, bias, with_ag[:5], furlongs, source)
