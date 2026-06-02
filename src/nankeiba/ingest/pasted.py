"""netkeiba のレース結果テーブル(コピペ)を取り込むパーサ。

想定する列(タブ区切り):
    着順 枠 馬番 馬名 性齢 斤量 馬体重 増減 騎手 調教師 タイム 着差 上がり3F 通過順 人気

馬の永続IDは馬名で代用する(同名馬は南関では稀なため実用上問題ない)。
上がり3F順位は、レース内の上がりタイムを比較して算出する。
馬場・距離・日付はテーブルに無いので呼び出し側で渡す。

依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

import re


def _to_float(s: str) -> float | None:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def parse_result_table(
    text: str,
    *,
    place: str,
    date: str,
    distance: int,
    baba: str | None = None,
    race_id: str | None = None,
) -> dict:
    """コピペした結果テーブルを core/dataset.py の JSONL レコードに変換する。"""
    rows: list[dict] = []
    for line in text.strip().splitlines():
        if not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) < 14:  # タブが失われた場合のフォールバック
            cols = re.split(r"\s{2,}|\t", line.strip())
        if len(cols) < 14:
            continue
        try:
            finish = int(cols[0])
            umaban = int(cols[2])
        except ValueError:
            continue
        name = cols[3].strip()
        jockey = cols[8].strip()
        trainer = cols[9].strip()
        agari = _to_float(cols[12])
        corner = [int(x) for x in cols[13].split("-") if x.strip().isdigit()]
        pop = int(cols[14]) if len(cols) > 14 and cols[14].strip().isdigit() else None
        rows.append({
            "finish_pos": finish, "umaban": umaban, "name": name,
            "jockey": jockey, "trainer": trainer, "agari": agari,
            "corner": corner, "popularity": pop,
        })

    # 上がり3F順位(レース内でタイムの速い順、データ欠損は末尾扱い)
    field = len(rows)
    have_agari = [r for r in rows if r["agari"] is not None]
    order = sorted(have_agari, key=lambda r: r["agari"])
    rank_of = {id(r): i + 1 for i, r in enumerate(order)}

    result = []
    for r in rows:
        result.append({
            "finish_pos": r["finish_pos"],
            "umaban": r["umaban"],
            "horse_id": r["name"],         # 馬名を永続IDに
            "horse_name": r["name"],
            "jockey": r["jockey"],
            "trainer": r["trainer"],
            "popularity": r["popularity"],
            "baba": baba,
            "corner_pos": r["corner"],
            "agari_rank": rank_of.get(id(r)),
        })

    return {
        "race_id": race_id or f"{date.replace('-', '')}_{place}_{distance}",
        "date": date, "place": place, "distance": distance,
        "field_size": field, "baba": baba,
        "result": result, "trio_odds": {}, "trifecta_odds": {},
    }
