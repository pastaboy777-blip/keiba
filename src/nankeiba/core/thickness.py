"""南関のレースを「中身が濃かったか」で並べる。

ユーザー指定（2026-07-29）:
    「時計だけじゃなくてラップとか見てる」
    「中身の濃いレースはどれだったか？ 時計の早さだけじゃだめだよ」
    「馬場補正かけた？？ 出走メンバーのれべるは？」

**速い＝濃い、ではない。** 逃げ馬が楽に行った1200mは時計だけ速く出るし、
高速馬場の日は全レースが速い。濃いレースとは

    テンから速くて、しかも上がりも落ちなかったレース

＝前半も後半もごまかしが効かなかったレース。そこで走った馬は次走で買える。

3つの物差しを**別々に**出す。1つに畳まないこと（畳むと平均に収束して情報が消える）。

  濃さ     … テン3F差 ＋ 上がり差（どちらも同条件の中央値との差、当日馬場差を補正後）
             **マイナスほど濃い。** 実測でいちばん効いている。
  時計レベル … 勝ちタイムが標準（par_win）＋当日馬場差より何秒速いか。プラスが速い。
             クラスを見ないので、上位に上級条件が並ぶのは当然。
  格       … 出走馬の「そのレースより前の1着経験率」の中央値（`race_level`）。
             メンバーが揃っていたか。

⚠️ 当日馬場差（`track_bias`）を必ず引くこと。引かないと「高速馬場の日のレース」が
   全部濃いことになる。テン・上がりはどちらも3ハロンなので `馬場差 × 3` を引く。

⚠️ **距離が200で割り切れないレース（1500m/1900m など）のテン3Fは信用しない。**
   先頭に100mの半端な区間が入るため、ハロン割りがずれる。実測で
   2026-07-28 川崎3R が「テン3F 30.2 / 差 −11.6」というあり得ない値になった。
   `ten3f_ok()` が False のレースは濃さを None にして、時計レベルだけで見る。

⚠️ 「その後どう走ったか」はレース後の情報なので予想には使えない（リークする）。
   振り返りにだけ使うこと（`scripts/race_sheet.py` の注意書きと同じ）。

依存ライブラリなし（標準ライブラリのみ）。
"""

from __future__ import annotations

import glob
import os
from collections import defaultdict
from dataclasses import dataclass
from statistics import median

from ..scraping import rakuten as rk
from . import lap as lapmod
from . import race_level as rl
from . import track_bias
from .datapath import cache_dir

#: テン・上がりはどちらも3ハロン。当日馬場差[s/F] にこれを掛けて引く。
FURLONGS = 3
#: 同条件の中央値を作るのに要る最低レース数。
MIN_SAMPLES = 8


def ten3f_ok(distance: int | None) -> bool:
    """テン3F を信用してよい距離か。

    ⚠️ 1500m や 1900m は先頭に100mの半端な区間が入るのでハロン割りがずれる。
       200で割り切れる距離だけ True。
    """
    return bool(distance) and distance % 200 == 0


@dataclass
class RaceLevel:
    """1レース分の「濃さ」まわり。"""

    date: str
    place: str
    race_no: int | None
    distance: int
    field_size: int
    baba: str | None = None
    win_time: float | None = None
    bias: float = 0.0                     # 当日その場の馬場差[s/F]
    ten_d: float | None = None            # テン3F差（馬場補正後・マイナスほど速い）
    ag_d: float | None = None             # 上がり差（同上）
    thick: float | None = None            # 濃さ = ten_d + ag_d（マイナスほど濃い）
    time_lv: float | None = None          # 標準より何秒速いか（プラスが速い）
    grade: float | None = None            # メンバーの格
    pace: str | None = None
    lap: str | None = None
    best_agari: float | None = None

    @property
    def key(self) -> tuple:
        """レースを一意に決める鍵。

        ⚠️ (日付, 場, 距離) では足りない。同じ日の同じ距離が2レース組まれることが
           あり、実際それで**別のレースを掴んで頭数が合わない**事故が起きた。
           必ず頭数まで含めること。
        """
        return (self.date, self.place, self.distance, self.field_size)

    def label(self) -> str:
        return (f"{self.date} {self.place}{self.race_no or '?'}R "
                f"ダ{self.distance}m {self.field_size}頭")

    def line(self) -> str:
        t = f"{self.thick:+.1f}" if self.thick is not None else "  -  "
        tv = f"{self.time_lv:+.2f}" if self.time_lv is not None else "  -  "
        g = f"{self.grade:.2f}" if self.grade is not None else " -  "
        return (f"{self.label():<34} 濃さ{t:>6} "
                f"(テン{self.ten_d:+.1f} 上がり{self.ag_d:+.1f}) "
                f"時計{tv:>6}秒 格{g} {self.pace or ''}"
                if self.thick is not None else
                f"{self.label():<34} 濃さ  - （テン3F不可）      "
                f"時計{tv:>6}秒 格{g} {self.pace or ''}")


def scan(cache: str | None = None, *, month: str = "",
         places: tuple = ("大井", "川崎", "船橋", "浦和")) -> list[RaceLevel]:
    """キャッシュ済みの結果ページを全部読んで、レースごとの濃さを付けて返す。

    par（同条件の中央値）と当日馬場差は**読み込んだ全レースから作る**ので、
    月を絞ると基準が痩せる。基準は全期間から作り、絞り込みは呼び出し側でやる方が
    よい（`month` は主に動作確認用）。
    """
    cdir = str(cache or cache_dir())
    raw_races = []
    ten_by: dict = defaultdict(list)
    ag_by: dict = defaultdict(list)
    day: dict = defaultdict(list)

    for pf in sorted(glob.glob(os.path.join(
            cdir, "race_performance_list_RACEID_*.html"))):
        rid = pf.rsplit("_", 1)[-1].removesuffix(".html")
        if month and not rid.startswith(month):
            continue
        cf = os.path.join(cdir, f"race_card_list_RACEID_{rid}.html")
        if not os.path.exists(cf):
            continue
        try:
            hd = rk.parse_card(open(cf, encoding="utf-8").read())["header"]
            raw = open(pf, encoding="utf-8").read()
            res = rk.parse_result(raw)
        except Exception:                              # noqa: BLE001
            continue
        pl, di = hd.get("place"), hd.get("distance")
        if pl not in places or not di or not res or not res[0].get("time_sec"):
            continue
        d = f"{rid[0:4]}-{rid[4:6]}-{rid[6:8]}"
        g = f"{pl}|{di}"
        la = lapmod.analyze(res, di, rk.parse_lap(raw))
        a3 = [r["agari"] for r in res[:3] if r.get("agari")]
        aall = [r["agari"] for r in res if r.get("agari")]
        a3m = sum(a3) / len(a3) if a3 else None
        ten = la.ten3f if (la.ten3f and ten3f_ok(di)) else None
        if ten:
            ten_by[g].append(ten)
        if a3m:
            ag_by[g].append(a3m)
        day[(d, pl)].append(dict(race_no=hd.get("race_no") or 0, place=pl,
                                 distance=di, win_time=res[0]["time_sec"]))
        raw_races.append((d, pl, hd, di, res, la, ten, a3m,
                          rk.parse_baba(raw), min(aall) if aall else None))

    tenp = {k: median(v) for k, v in ten_by.items() if len(v) >= MIN_SAMPLES}
    agp = {k: median(v) for k, v in ag_by.items() if len(v) >= MIN_SAMPLES}
    bias = {k: track_bias.measure(v).offset for k, v in day.items()}

    out: list[RaceLevel] = []
    for d, pl, hd, di, res, la, ten, a3m, baba, bestag in raw_races:
        g = f"{pl}|{di}"
        b = bias.get((d, pl), 0.0)
        ten_d = (ten - tenp[g] - b * FURLONGS) if (ten and g in tenp) else None
        ag_d = (a3m - agp[g] - b * FURLONGS) if (a3m and g in agp) else None
        par = track_bias.PAR_WIN.get(g)
        sf = res[0]["time_sec"] / (di / 200.0)
        lv = rl.level_of(d, pl, di)
        out.append(RaceLevel(
            date=d, place=pl, race_no=hd.get("race_no"), distance=di,
            field_size=len(res), baba=baba, win_time=res[0]["time_sec"], bias=b,
            ten_d=round(ten_d, 2) if ten_d is not None else None,
            ag_d=round(ag_d, 2) if ag_d is not None else None,
            thick=(round(ten_d + ag_d, 2)
                   if (ten_d is not None and ag_d is not None) else None),
            time_lv=(round((par - sf - b) * (di / 200.0), 2) if par else None),
            grade=lv.grade if lv else None,
            pace=la.pace, lap=la.lap_curve(), best_agari=bestag,
        ))
    return out


def rank(races: list[RaceLevel], *, by: str = "thick", top: int = 20,
         **where) -> list[RaceLevel]:
    """濃い順（既定）に並べる。`by="time"` なら時計レベル順、`"grade"` なら格順。

    where は単純な等値フィルタ（place="川崎", date="2026-07-30" など）。
    """
    sel = [r for r in races
           if all(getattr(r, k, None) == v for k, v in where.items())]
    if by == "thick":
        sel = [r for r in sel if r.thick is not None]
        sel.sort(key=lambda r: r.thick)                 # マイナスほど濃い
    elif by == "time":
        sel = [r for r in sel if r.time_lv is not None]
        sel.sort(key=lambda r: -r.time_lv)
    elif by == "grade":
        sel = [r for r in sel if r.grade is not None]
        sel.sort(key=lambda r: -r.grade)
    else:
        raise ValueError(f"by は thick/time/grade のどれか: {by}")
    return sel[:top]


def index_by_key(races: list[RaceLevel]) -> dict[tuple, RaceLevel]:
    """馬柱の1走から引けるように (日付,場,距離,頭数) で索引する。"""
    return {r.key: r for r in races}
