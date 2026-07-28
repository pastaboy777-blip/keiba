"""前走で先着した相手が、その後どう走ったか — 点数にせず**事実のまま**出す。

ユーザーの指摘（2026-07-28）:
    「普通に考えなよ。数値化したらみんな0.75に収束するじゃん。競馬というゲーム
      なんだから。それを分析してどうするの？」

そのとおりだった。レースレベルを平均・中央値・lift に畳んだ版は、どの定義でも
lift 0.95〜1.40 の範囲に潰れた。**平均を取った時点で情報が消える**。
市場が織り込んでいる以上、集計値はベースラインに収束する。

実例（同日 2026-07-28 川崎11R）:
    ③クラウニングカップ（**11番人気3着**）の前走は 船橋1500「手賀沼特別」**1着**。
    そこで負かした相手がその後 重賞で3着に来ていた。
    人が見れば一発で分かるこの事実を、集計指標は一切拾えなかった
    （しかも船橋のそのレースは未収録で「格」が計算すらできなかった）。

よってこのモジュールは **スコアを返さない**。
「前走で先着した相手が、その後どこで何着だったか」を**そのまま並べる**。
判断は人がする。

依存ライブラリなし。
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field

from ..scraping import rakuten as rk

CACHE = "data/cache/rakuten"

#: 重賞・特別の見分け（レース名に含まれる語）。南関の表記ゆれを広めに拾う。
STAKES_WORDS = ("記念", "賞", "特別", "カップ", "杯", "ステークス", "S")


@dataclass
class Rival:
    """前走で先着した相手 1頭。"""

    name: str
    finish_then: int                       # そのレースでの着順
    after: list[tuple] = field(default_factory=list)   # [(日付, 場, 距離, 着順, レース名)]

    def best(self) -> tuple | None:
        """その後の最高着順（同着順ならレース名が特別・重賞っぽいものを優先）。"""
        if not self.after:
            return None
        return min(self.after, key=lambda a: (a[3], 0 if is_stakes(a[4]) else 1))

    def line(self) -> str:
        b = self.best()
        if not b:
            return f"{self.name}（その後の出走なし）"
        d, pl, di, fin, nm = b
        tag = "★" if is_stakes(nm) and fin <= 3 else ""
        return (f"{self.name} → その後 {pl}{di} {nm or ''}".rstrip()
                + f" {fin}着{tag}（{d}）")


@dataclass
class PrevRaceRivals:
    """前走で先着した相手たちの、その後。"""

    date: str
    place: str
    distance: int
    race_name: str | None
    my_finish: int
    rivals: list[Rival] = field(default_factory=list)

    def highlights(self, top: int = 3) -> list[Rival]:
        """その後よく走った順に。特別・重賞での好走を優先して上に出す。"""
        def key(r: Rival):
            b = r.best()
            if not b:
                return (9, 99)
            return (0 if (is_stakes(b[4]) and b[3] <= 3) else 1, b[3])
        return sorted(self.rivals, key=key)[:top]

    def summary(self) -> str:
        head = (f"前走 {self.place}{self.distance} "
                f"{self.race_name or ''} {self.my_finish}着".replace("  ", " "))
        hl = [r.line() for r in self.highlights() if r.best()]
        return head + ("　／　" + " ／ ".join(hl) if hl else "　／　先着相手のその後なし")


def is_stakes(name: str | None) -> bool:
    """レース名が特別・重賞っぽいか。クラス表記（３歳二 など）は除く。"""
    if not name:
        return False
    n = name.strip()
    if not n or n[0].isdigit() or n.startswith(("３歳", "２歳", "４歳", "Ｃ", "Ｂ", "Ａ")):
        return False
    return any(w in n for w in STAKES_WORDS)


# ---------------------------------------------------------------------------
# 索引（結果ページ＝全出走馬 / 馬柱＝その後の走り）
# ---------------------------------------------------------------------------

class Index:
    """レースの出走馬名簿と、馬ごとの全走を持つ索引。"""

    def __init__(self, cache_dir: str = CACHE):
        self.roster: dict[tuple, list[tuple[str, int]]] = {}
        self.runs: dict[str, dict[str, tuple]] = {}
        self._load(cache_dir)

    def _load(self, cache_dir: str) -> None:
        for pf in sorted(glob.glob(os.path.join(
                cache_dir, "race_performance_list_RACEID_*.html"))):
            rid = pf.rsplit("_", 1)[-1].removesuffix(".html")
            cf = os.path.join(cache_dir, f"race_card_list_RACEID_{rid}.html")
            if not os.path.exists(cf):
                continue
            try:
                hd = rk.parse_card(open(cf, encoding="utf-8").read())["header"]
                res = rk.parse_result(open(pf, encoding="utf-8").read())
            except Exception:                      # noqa: BLE001
                continue
            if not hd.get("place") or not hd.get("distance") or not res:
                continue
            key = (f"{rid[0:4]}-{rid[4:6]}-{rid[6:8]}", hd["place"], hd["distance"])
            self.roster[key] = [(r["name"], r["finish"]) for r in res if r.get("name")]
        for cf in sorted(glob.glob(os.path.join(
                cache_dir, "race_card_list_RACEID_*.html"))):
            try:
                card = rk.parse_card(open(cf, encoding="utf-8").read())
            except Exception:                      # noqa: BLE001
                continue
            for e in card["entries"]:
                d = self.runs.setdefault(e["name"], {})
                for r in e["history"]:
                    if r.finish_pos:
                        d[r.date] = (r.date, r.place, r.distance,
                                     r.finish_pos, r.race_name)

    def beaten(self, history, name: str) -> PrevRaceRivals | None:
        """前走で**先着した**相手を集め、その後の走りを付けて返す。"""
        if not history:
            return None
        p = history[0]
        key = (p.date, p.place, p.distance)
        rs = self.roster.get(key)
        if not rs:
            return None
        me = next((f for nm, f in rs if nm == name), p.finish_pos)
        out = PrevRaceRivals(date=p.date, place=p.place, distance=p.distance,
                             race_name=p.race_name, my_finish=me)
        for nm, fin in rs:
            if nm == name or fin <= me:
                continue                       # 自分より下の着順＝先着した相手
            after = [v for d, v in self.runs.get(nm, {}).items() if d > p.date]
            out.rivals.append(Rival(name=nm, finish_then=fin, after=after))
        return out if out.rivals else None
