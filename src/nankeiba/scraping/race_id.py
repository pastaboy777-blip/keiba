"""楽天競馬(keiba.rakuten.co.jp)の RACEID ユーティリティ。

楽天競馬の RACEID は18桁:
    YYYYMMDD(8) + 場コード(2) + 開催回(2) + 開催日(2) + R(2) ※末尾は2桁のレース番号

    例) 202606021914030201
        = 2026/06/02・船橋(19)・…・1R

場コードは地方競馬全国協会(NAR)準拠で、南関4場は次の通り:
    浦和=18, 船橋=19, 大井=20, 川崎=21

レース番号を構築するための「開催回・開催日」は事前に分からないことが多い。
そこで本実装では **日付+場コードのインデックス RACEID** を入口に使い、
出馬表/成績ページから各レースの実 RACEID リンクを収集する方式を採る
(parser.parse_race_links)。これによりサイト内部の開催回採番に依存しない。

    インデックス RACEID = YYYYMMDD + 場コード + "00000000"
        例) 202606021900000000  (2026/06/02 船橋)
"""

from __future__ import annotations

# 楽天競馬(NAR)場コード。南関4場のみを対象とする(楽天競馬専用)。
NANKAN_CODES: dict[str, str] = {
    "浦和": "18",
    "船橋": "19",
    "大井": "20",
    "川崎": "21",
}

# コード -> 場名 の逆引き
CODE_TO_PLACE: dict[str, str] = {v: k for k, v in NANKAN_CODES.items()}


def day_index_race_id(date_yyyymmdd: str, place: str) -> str:
    """その日・その場の「インデックス RACEID」を返す。

    date_yyyymmdd: "20260602" のような8桁文字列。
    出馬表/成績ページの入口として使い、各レースの実 RACEID をリンクから収集する。
    """
    if len(date_yyyymmdd) != 8 or not date_yyyymmdd.isdigit():
        raise ValueError(f"date は YYYYMMDD の8桁: {date_yyyymmdd!r}")
    code = NANKAN_CODES[place]
    return f"{date_yyyymmdd}{code}00000000"


def parse_race_id(race_id: str) -> dict:
    """RACEID を構成要素に分解する。"""
    if len(race_id) != 18 or not race_id.isdigit():
        raise ValueError(f"RACEID は18桁の数字: {race_id!r}")
    code = race_id[8:10]
    return {
        "date": f"{race_id[0:4]}-{race_id[4:6]}-{race_id[6:8]}",
        "jyo_code": code,
        "place": CODE_TO_PLACE.get(code, ""),
        "race_no": int(race_id[16:18]),
    }


def is_nankan(race_id: str) -> bool:
    """南関4場の RACEID か。"""
    return len(race_id) == 18 and race_id[8:10] in CODE_TO_PLACE
