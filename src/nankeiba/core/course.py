"""競馬場(コース)の基本情報。南関4場 + 中央競馬(JRA)10場。

展開予想(core/tenkai.py)と出走間隔プライアの切り替えに使う。

- org:      'NAR'(地方・南関)/ 'JRA'(中央)
- straight: 最後の直線の長さ[m](芝/ダート別。内外回りがある場は代表値=外回り)
- turn:     回り('右'/'左')

直線が短いほど「前に行った馬が残りやすい(先行有利)」、長いほど
「差し・追込が届きやすい」。この直線長を展開の地形バイアスとして使う。

値は公表値ベースの概算(改修で変わりうる)。厳密さより相対比較が目的。
依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Course:
    place: str
    org: str                       # 'NAR' or 'JRA'
    straight_turf: int | None      # 芝コースの直線[m](芝が無ければ None)
    straight_dirt: int             # ダートコースの直線[m]
    turn: str                      # '右' / '左'
    inner_straight_turf: int | None = None  # 内回りの芝直線(新潟・京都・阪神)

    def straight(self, surface: str | None = None, *, inner: bool = False) -> int:
        """指定馬場の直線長。surface は '芝' / 'ダ'(None ならダート扱い)。"""
        if surface and surface.startswith("芝") and self.straight_turf:
            if inner and self.inner_straight_turf:
                return self.inner_straight_turf
            return self.straight_turf
        return self.straight_dirt


COURSES: dict[str, Course] = {
    # --- 南関(NAR)。全場ダートのみ ---
    "大井": Course("大井", "NAR", None, 386, "右"),
    "川崎": Course("川崎", "NAR", None, 300, "左"),
    "船橋": Course("船橋", "NAR", None, 308, "左"),
    "浦和": Course("浦和", "NAR", None, 220, "左"),
    # --- 中央(JRA)10場 ---
    "札幌": Course("札幌", "JRA", 266, 264, "右"),
    "函館": Course("函館", "JRA", 262, 260, "右"),
    "福島": Course("福島", "JRA", 292, 296, "右"),
    "新潟": Course("新潟", "JRA", 659, 354, "左", inner_straight_turf=359),
    "東京": Course("東京", "JRA", 526, 502, "左"),
    "中山": Course("中山", "JRA", 310, 308, "右"),
    "中京": Course("中京", "JRA", 413, 411, "左"),
    "京都": Course("京都", "JRA", 404, 329, "右", inner_straight_turf=328),
    "阪神": Course("阪神", "JRA", 474, 352, "右", inner_straight_turf=356),
    "小倉": Course("小倉", "JRA", 293, 291, "右"),
}

JRA_PLACES: tuple[str, ...] = tuple(p for p, c in COURSES.items() if c.org == "JRA")
NANKAN_PLACES: tuple[str, ...] = tuple(p for p, c in COURSES.items() if c.org == "NAR")


def get_course(place: str) -> Course | None:
    return COURSES.get(place)


def org_of(place: str) -> str:
    """競馬場の主催('JRA'/'NAR')。未知の場は 'NAR' 扱い(本パイプラインの既定)。"""
    c = COURSES.get(place)
    return c.org if c else "NAR"


def is_jra(place: str) -> bool:
    return org_of(place) == "JRA"


# 直線長 → 先行有利度(front_bias)。基準 350m で 0、短いほど +、長いほど −。
# 例: 浦和220m → +0.33 / 中山310m → +0.10 / 東京526m → −0.44 / 新潟外659m → −0.77
_STRAIGHT_REF = 350.0
_STRAIGHT_SCALE = 400.0


def front_bias(place: str, surface: str | None = None, *, inner: bool = False) -> float:
    """コース形状による先行有利度(−1〜+1 目安)。未知の場は 0。"""
    c = COURSES.get(place)
    if c is None:
        return 0.0
    s = c.straight(surface, inner=inner)
    return max(-1.0, min(1.0, (_STRAIGHT_REF - s) / _STRAIGHT_SCALE))
