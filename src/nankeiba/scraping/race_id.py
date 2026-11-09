"""netkeiba の race_id ユーティリティ(地方 NAR / 中央 JRA)。

race_id は12桁。
  地方(nar.netkeiba.com):  YYYY + 場コード(2) + 月(2) + 日(2) + R(2)
                           ※本リポジトリでは引数名を kai/day としている(従来互換)
  中央(race.netkeiba.com): YYYY + 場コード(2) + 開催回(2) + 開催日目(2) + R(2)
                           例: 2024年 第5回東京 8日目 11R → 202405050811

南関4場の netkeiba 場コード:  浦和=42, 船橋=43, 大井=44, 川崎=45
中央10場の場コード(JRA 標準): 札幌=01 函館=02 福島=03 新潟=04 東京=05
                              中山=06 中京=07 京都=08 阪神=09 小倉=10
※ コードは netkeiba の仕様変更で変わりうるため、実データで要確認。
"""

from __future__ import annotations

NANKAN_CODES: dict[str, str] = {
    "浦和": "42",
    "船橋": "43",
    "大井": "44",
    "川崎": "45",
}

JRA_CODES: dict[str, str] = {
    "札幌": "01",
    "函館": "02",
    "福島": "03",
    "新潟": "04",
    "東京": "05",
    "中山": "06",
    "中京": "07",
    "京都": "08",
    "阪神": "09",
    "小倉": "10",
}

ALL_CODES: dict[str, str] = {**NANKAN_CODES, **JRA_CODES}
_PLACE_OF_CODE: dict[str, str] = {v: k for k, v in ALL_CODES.items()}


def build_race_id(year: int, place: str, kai: int, day: int, race_no: int) -> str:
    code = ALL_CODES[place]
    return f"{year:04d}{code}{kai:02d}{day:02d}{race_no:02d}"


def is_nankan(race_id: str) -> bool:
    return len(race_id) == 12 and race_id[4:6] in NANKAN_CODES.values()


def is_jra(race_id: str) -> bool:
    return len(race_id) == 12 and race_id[4:6] in JRA_CODES.values()


def place_of(race_id: str) -> str | None:
    """race_id から競馬場名を返す(未知のコードは None)。"""
    if len(race_id) != 12:
        return None
    return _PLACE_OF_CODE.get(race_id[4:6])
