"""相対の3層 ── 上がりと時計は、3つの相対の中でしか意味を持たない。

ユーザーによる言語化（2026-08-14）:

    **上がりの絶対値には意味がない。「レース平均との差」を「どの位置から」
    「前が有利か不利かの中で」出したか。この3つが揃って初めて、その脚が
    濃いか薄いかが決まる。**

    ① レース内相対 … 順位ではなく、そのレースの**平均上がりとの差**[秒]
    ② 位置相対     … どこから使った脚か
    ③ 展開相対     … 前が有利だったか

⚠️⚠️ **①②③は独立ではない。②は③の中でしか意味を持たない。**
   南関7,555レースの実測（平均上がりとの差の平均）:

                     前が楽な流れ    前が止まった流れ
       4角 前25%        **-0.59**        **+0.51**
       4角 中            +0.01           -0.06
       4角 後40%        **+0.31**        **-0.23**

   「後方の馬は上がりが速く出て当たり前」は **前が止まったときだけ**成り立つ。
   前が楽な流れでは、後方はむしろ **+0.31 と遅くなる**（脚を使えていない）。

   ⚠️ 最初これを**展開で分けずに**測って「南関では前の馬のほうが上がりが速い」
      という逆の結論を出しかけた。プールすると 前25% は −0.59 と +0.51 の
      加重平均で −0.18 になり、構造が消える。**②を測るときは必ず③で層別する。**

── なぜ絶対値が使えないか ──────────────────────────────

   レース内で中心化すると、**走破タイムと上がりの相関は r = +0.849**。
   同じレースの中では、上がりと走破タイムは**85%まで同じことを言っている**。
   「上がり最速だった」を材料に足すと、着順をもう一度数えることになる。

── 狙う形 ───────────────────────────────────────

    **前が楽に残った流れで、後方から平均を上回る上がりを使ったのに着外だった馬。**
    次に「前が止まる流れ・内枠・斤量減」が来たとき、
    **同じ脚のまま順位だけが上がる。**

    市場は着順を見るので、着外だった馬は人気が据え置かれる。そこが取りどころ。

    実例（ジューンアカデミー・大井1200m）:
        7/22  4角9番手/9頭・前が楽な流れ  平均差 -0.62 → **5着8人気**
        8/14  4角8番手/16頭・前が止まった  平均差 -0.65 → **2着8人気**
        脚は2回とも同じ。変わったのは流れと位置（8枠→2枠）と斤量（-3kg）だけ。
        **能力は動いていない。評価だけが動いた。**

⚠️ 未検証。この形の再現性は測っていない（恒久ルール5）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean

#: 位置帯の切り方（4角位置 ÷ 頭数）。
FRONT = 0.25
MIDDLE = 0.60
#: 「前が止まった」とみなす、逃げ・先行馬の平均差[秒]。0より大きければ垂れている。
STOPPED = 0.0

#: **位置帯 × 展開** ごとの、平均上がりとの差の期待値[秒]。
#: 南関7,555レース・86,483頭の実測。⚠️ 推定ではなく測った値。
EXPECTED = {
    ("前", "楽"): -0.59, ("前", "止"): +0.51,
    ("中", "楽"): +0.01, ("中", "止"): -0.06,
    ("後", "楽"): +0.31, ("後", "止"): -0.23,
}


def pos_band(corner4: int | None, field_size: int | None) -> str | None:
    """4角位置を '前' / '中' / '後' に。"""
    if not corner4 or not field_size:
        return None
    p = corner4 / field_size
    return "前" if p <= FRONT else ("中" if p <= MIDDLE else "後")


@dataclass
class RaceRelative:
    """1レース分の相対。"""

    mean_agari: float
    front_diff: float                  # ③ 逃げ・先行馬の平均差。**＋なら前が止まった**
    n: int = 0

    @property
    def flow(self) -> str:
        return "止" if self.front_diff > STOPPED else "楽"

    def note(self) -> str:
        return (f"前が{'止まった' if self.flow == '止' else '楽だった'}"
                f"（先行勢の平均差 {self.front_diff:+.2f}秒）")


@dataclass
class HorseRelative:
    """1頭分の相対。"""

    name: str
    agari: float
    diff: float                        # ① レース平均との差。マイナスが速い
    band: str | None                   # ② 位置帯
    expected: float | None             # ②×③ から期待される平均差
    residual: float | None             # **これが「濃さ」**。マイナスほど濃い
    finish: int | None = None
    popularity: int | None = None

    def note(self) -> str:
        if self.residual is None:
            return f"平均差{self.diff:+.2f}（位置不明）"
        return (f"平均差{self.diff:+.2f} ／ {self.band}から"
                f"（この位置・この流れの標準は{self.expected:+.2f}）"
                f" → **残差{self.residual:+.2f}**")


def analyse(runners) -> tuple[RaceRelative, list]:
    """1レースの出走馬から、①②③をまとめて出す。

    `runners` は `agari` / `corner4` / `field_size` / `finish` を持つ dict の列。

    ⚠️ **③は「逃げ・先行馬がどれだけ落ちたか」で測る。**ラップやペース記号では
       なく、実際に前にいた馬の上がりで見る。前が止まったかどうかは、
       前にいた馬の結果にしか現れない。
    """
    ok = [x for x in runners if x.get("agari")]
    if len(ok) < 4:
        return RaceRelative(0.0, 0.0, len(ok)), []
    n = len(ok)
    ma = mean(x["agari"] for x in ok)
    fr = [x["agari"] - ma for x in ok
          if pos_band(x.get("corner4"), x.get("field_size") or n) == "前"]
    rr = RaceRelative(mean_agari=round(ma, 2),
                      front_diff=round(mean(fr), 2) if fr else 0.0, n=n)
    out = []
    for x in ok:
        b = pos_band(x.get("corner4"), x.get("field_size") or n)
        d = round(x["agari"] - ma, 2)
        e = EXPECTED.get((b, rr.flow)) if b else None
        out.append(HorseRelative(
            name=x.get("name", ""), agari=x["agari"], diff=d, band=b,
            expected=e, residual=(round(d - e, 2) if e is not None else None),
            finish=x.get("finish"), popularity=x.get("popularity")))
    out.sort(key=lambda h: (h.residual if h.residual is not None else 9))
    return rr, out


#: 狙い目とみなす残差[秒]。これより速ければ「この位置・この流れにしては濃い」。
KOI = -0.40
#: 着外とみなす着順。
KENGAI = 4


def target(rr: RaceRelative, h: HorseRelative) -> tuple[bool, str]:
    """**次に狙える形**か。前が楽な流れで、濃い脚を使ったのに着外だった馬。

    ⚠️ **前が止まった流れで後方から速い上がり、は狙いではない。**それは
       位置が向いただけで、期待値どおり（後40%×止 の標準が -0.23）。
       前が楽なのに後方から脚を使った馬こそ、次に流れが向けば順位が上がる。
    """
    if h.residual is None or h.finish is None:
        return False, ""
    if rr.flow != "楽":
        return False, ""
    if h.band == "前":
        return False, ""
    if h.residual > KOI or h.finish < KENGAI:
        return False, ""
    return True, (f"前が楽な流れ（先行勢{rr.front_diff:+.2f}）を{h.band}から"
                  f"残差{h.residual:+.2f}で走って{h.finish}着"
                  + (f"（{h.popularity}人気）" if h.popularity else ""))
