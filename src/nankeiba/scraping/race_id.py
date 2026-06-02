"""netkeiba(地方競馬 / NAR)の race_id ユーティリティ。

race_id は12桁: YYYY(年) + 場コード(2) + 開催回(2) + 開催日(2) + R(2)
南関4場の netkeiba 場コード:
    浦和=42, 船橋=43, 大井=44, 川崎=45
※ コードは netkeiba の仕様変更で変わりうるため、実データで要確認。
"""

from __future__ import annotations

NANKAN_CODES: dict[str, str] = {
    "浦和": "42",
    "船橋": "43",
    "大井": "44",
    "川崎": "45",
}


def build_race_id(year: int, place: str, kai: int, day: int, race_no: int) -> str:
    code = NANKAN_CODES[place]
    return f"{year:04d}{code}{kai:02d}{day:02d}{race_no:02d}"


def is_nankan(race_id: str) -> bool:
    return len(race_id) == 12 and race_id[4:6] in NANKAN_CODES.values()
