"""三連複・三連単オッズの取得とパース。

netkeiba(地方)はオッズを JavaScript から JSON API で読み込む。代表的には
    https://nar.netkeiba.com/api/api_get_jra_odds.html?race_id=<id>&type=<n>
のような XHR で、馬番の組み合わせ -> オッズ の辞書が返る。
※ エンドポイントURLと type コード(三連複/三連単の別)はサイト仕様変更で
   変わりうるため、実環境で要確認。本リポジトリはネット遮断のため未検証。

ここでは「組み合わせ文字列 -> オッズ」の JSON を Race 用の辞書に正規化する
パース部分を提供する(この部分はオフラインでテスト可能)。

組み合わせ文字列の想定: 三連複 "3-5-8"(順不同), 三連単 "5-3-8"(着順)。
netkeiba の生キーが "030508" のような連結数値の場合もあるため両対応する。
"""

from __future__ import annotations

import json
from typing import Mapping

# type コード(要確認のためのプレースホルダ)
ODDS_TYPE = {"trio": "b7", "trifecta": "b8"}
ODDS_API = "https://nar.netkeiba.com/api/api_get_jra_odds.html?race_id={race_id}&type={type}"


def odds_api_url(race_id: str, bet_type: str) -> str:
    return ODDS_API.format(race_id=race_id, type=ODDS_TYPE[bet_type])


def _split_combo_key(key: str, *, ordered: bool, width: int = 2) -> tuple[int, ...]:
    """生キーを馬番タプルに変換する。

    "3-5-8" のような区切り、または "030508" のような固定幅連結の両方に対応。
    ordered=False(三連複)は昇順に並べ替える。
    """
    if "-" in key:
        nums = tuple(int(x) for x in key.split("-"))
    else:
        nums = tuple(int(key[i:i + width]) for i in range(0, len(key), width))
    return nums if ordered else tuple(sorted(nums))


def parse_odds_payload(
    payload: Mapping | str, *, bet_type: str
) -> dict[tuple[int, ...], float]:
    """オッズ JSON(または dict)を {馬番タプル: オッズ} に正規化する。

    payload は {"odds": {"3-5-8": "42.1", ...}} のような構造、または
    その中の odds 辞書そのものを受け取る。値は文字列/数値どちらも可。
    """
    if isinstance(payload, str):
        payload = json.loads(payload)
    raw = payload.get("odds", payload) if isinstance(payload, Mapping) else payload
    ordered = bet_type == "trifecta"
    out: dict[tuple[int, ...], float] = {}
    for k, v in raw.items():
        try:
            o = float(v)
        except (TypeError, ValueError):
            continue
        if o <= 0:
            continue
        out[_split_combo_key(str(k), ordered=ordered)] = o
    return out
