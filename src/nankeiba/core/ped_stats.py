"""大系統×距離帯の複勝率（南関ダート実測）と、血統フィット判定。

`scripts/pedigree_stats.py` が楽天実データから測定した複勝率を既定テーブルとして
埋め込む。data/pedigree_stats.json があればそれで上書きできる(再測定して更新)。

血統フィット: 今回の距離帯でその大系統の複勝率が全体基準を上回れば「○(得意)」、
下回れば「▽(苦手)」。血統ビームの「今日走る大系統」をデータで裏付けるための指標。

⚠️ 距離帯別は母数が小さいものもある(特にマイナー系)。あくまで参考。
依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

import json
import os

# 南関ダート実測(2026-07-02〜07-21・204R)。全体複勝率 baseline=0.283。
BASELINE = 0.283
GOOD_MARGIN = 0.04

# (大系統key, 距離帯) -> 複勝率 (母数>=15 のみ)
_DEFAULT_RATE: dict[tuple[str, str], float] = {
    ("minor", "短(〜1400)"): 0.483,
    ("minor", "中(1500-1700)"): 0.438,
    ("nasrullah", "中(1500-1700)"): 0.344,
    ("turnto", "短(〜1400)"): 0.318,
    ("sunday", "短(〜1400)"): 0.317,
    ("nasrullah", "短(〜1400)"): 0.295,
    ("sunday", "中(1500-1700)"): 0.295,
    ("turnto", "中(1500-1700)"): 0.293,
    ("sunday", "長(1800〜)"): 0.292,
    ("nasrullah", "長(1800〜)"): 0.292,
    ("mrprospector", "中(1500-1700)"): 0.278,
    ("mrprospector", "長(1800〜)"): 0.259,
    ("northern", "短(〜1400)"): 0.258,
    ("mrprospector", "短(〜1400)"): 0.212,
    ("northern", "中(1500-1700)"): 0.172,
    ("turnto", "長(1800〜)"): 0.125,
}


def dist_band(distance: int) -> str:
    if distance <= 1400:
        return "短(〜1400)"
    if distance <= 1700:
        return "中(1500-1700)"
    return "長(1800〜)"


_RATE = dict(_DEFAULT_RATE)


def load_override(path: str = "data/pedigree_stats.json", *, min_starts: int = 15) -> bool:
    """測定JSONで複勝率テーブルを上書き。成功で True。"""
    global _RATE, BASELINE
    if not os.path.exists(path):
        return False
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:                                # noqa: BLE001
        return False
    tbl = {}
    for key, v in d.get("system_band", {}).items():
        if v.get("starts", 0) >= min_starts and "|" in key:
            sys_, band = key.split("|", 1)
            tbl[(sys_, band)] = v["hit3"] / v["starts"]
    sys_all = d.get("system", {})
    ts = sum(x["starts"] for x in sys_all.values())
    th = sum(x["hit3"] for x in sys_all.values())
    if ts:
        BASELINE = round(th / ts, 3)
    if tbl:
        _RATE = tbl
    return True


def rate(system: str | None, distance: int) -> float | None:
    if not system:
        return None
    return _RATE.get((system, dist_band(distance)))


def fit(system: str | None, distance: int) -> str:
    """血統フィット: ○(得意)/▽(苦手)/''(基準内・データ無)。"""
    r = rate(system, distance)
    if r is None:
        return ""
    if r >= BASELINE + GOOD_MARGIN:
        return "○"
    if r <= BASELINE - GOOD_MARGIN:
        return "▽"
    return ""
