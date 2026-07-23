"""レース結果のラップ／ペース分析（南関・楽天データ版）。

楽天の結果には区間ラップ(1ハロンごと)は無いが、各馬の
**走破タイム**と**推定上がり3F**が取れる。これを使って:

  ・レースの前後半バランス（前半平均F vs 上がり平均F）
  ・ペース判定 H(ハイ)/M(平均)/S(スロー)
  ・決着傾向（前残り / 差し・追込有利）
  ・上がり3F上位（速い脚を使った馬＝次走の狙い目）

を出す。指数予想の「展開読み」が当たっていたかの答え合わせに使う。

前提: 走破タイムは 距離(m) を走った秒。前半 = 走破タイム − 上がり3F、
前半の距離 = 距離 − 600m。1ハロン=200m。依存ライブラリなし。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LapAnalysis:
    distance: int
    win_time: float | None            # 勝ちタイム(秒)
    avg_furlong: float | None         # 全体の平均1ハロン(秒)
    first_pace: float | None          # 前半(上がり除く)の平均1ハロン(秒)
    last_pace: float | None           # 上がり3Fの平均1ハロン(秒)
    balance: float | None             # 前半F − 上がりF（負=前半速い=ハイ）
    pace: str                         # "H"/"M"/"S"/"?"
    pace_label: str                   # 日本語ラベル
    bias: str                         # 決着傾向
    agari_top: list[tuple]            # [(umaban, name, agari, finish), ...] 上がり順

    def summary(self) -> str:
        L = [f"距離{self.distance}m 勝ちタイム"
             + (f"{self.win_time:.1f}秒" if self.win_time else "―")]
        if self.avg_furlong:
            L.append(f"平均{self.avg_furlong:.1f}秒/F")
        if self.first_pace and self.last_pace:
            L.append(f"前半{self.first_pace:.1f}→上がり{self.last_pace:.1f}"
                     f"（差{self.balance:+.1f}）")
        L.append(f"{self.pace_label}／{self.bias}")
        return " ".join(L)


def analyze(result: list[dict], distance: int) -> LapAnalysis:
    """parse_result の戻り値と距離から、ラップ／ペース分析を返す。"""
    if not result or not distance:
        return LapAnalysis(distance, None, None, None, None, None, "?", "データ不足", "―", [])

    win = min(result, key=lambda r: r["finish"])
    wt = win.get("time_sec")
    wa = win.get("agari")

    avg_f = wt / (distance / 200.0) if wt else None
    first_pace = last_pace = balance = None
    pace, plabel, bias = "?", "データ不足", "―"

    if wt and wa and distance > 600:
        first_dist = distance - 600            # 上がり3F(600m)を除いた前半
        first_pace = (wt - wa) / (first_dist / 200.0)
        last_pace = wa / 3.0
        balance = first_pace - last_pace       # 負=前半が速い=ハイペース
        if balance <= -0.5:
            pace, plabel, bias = "H", "ハイペース", "差し・追込有利（前が垂れる）"
        elif balance >= 0.6:
            pace, plabel, bias = "S", "スローペース", "前残り・逃げ先行有利"
        else:
            pace, plabel, bias = "M", "平均ペース", "紛れ少・地力勝負"

    # 上がり3F上位（速い順）。取れた馬のみ。
    with_ag = [(r["umaban"], r.get("name", ""), r["agari"], r["finish"])
               for r in result if r.get("agari")]
    with_ag.sort(key=lambda t: t[2])

    return LapAnalysis(distance, wt, avg_f, first_pace, last_pace, balance,
                       pace, plabel, bias, with_ag[:5])
