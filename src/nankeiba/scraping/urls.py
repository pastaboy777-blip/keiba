"""netkeiba の URL(地方 NAR / 中央 JRA)。race_id の場コードで自動判定する。"""

from __future__ import annotations

from .race_id import is_jra

NAR_RESULT_URL = "https://nar.netkeiba.com/race/result.html?race_id={race_id}"
JRA_RESULT_URL = "https://race.netkeiba.com/race/result.html?race_id={race_id}"


def result_url(race_id: str) -> str:
    tmpl = JRA_RESULT_URL if is_jra(race_id) else NAR_RESULT_URL
    return tmpl.format(race_id=race_id)
