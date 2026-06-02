"""netkeiba 地方のレース結果ページをパースして RunRecord 化する。

重要: netkeiba は HTML 構造を変えることがある。以下のセレクタは
あくまで出発点で、実データを見ながら調整する前提(本環境はネット遮断のため未検証)。
パース結果は core.interval.RunRecord と core.backtest.Race にマッピングする。

BeautifulSoup が必要: pip install beautifulsoup4
"""

from __future__ import annotations

import re
from dataclasses import dataclass

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore

# race_id は12桁。リンク href から拾うためのパターン(構造変化に強い)。
_RACE_ID_RE = re.compile(r"race_id=(\d{12})")


@dataclass
class ParsedRow:
    finish_pos: int
    umaban: int | None
    horse_id: str
    horse_name: str
    jockey: str
    trainer: str | None
    popularity: int | None
    odds: float | None


@dataclass
class ParsedRace:
    race_id: str
    date: str            # 'YYYY-MM-DD'
    place: str
    distance: int
    field_size: int
    rows: list[ParsedRow]  # 着順順


def parse_race_ids_from_list(html: str, *, nankan_only: bool = True) -> list[str]:
    """日次の出走表/レース一覧ページから race_id を抽出する。

    テーブル構造ではなく href 内の ``race_id=XXXXXXXXXXXX`` を正規表現で拾うため、
    HTML レイアウト変更に強い。重複は除き、出現順を保つ。
    bs4 不要(正規表現のみ)なのでオフラインでもテスト可能。
    """
    from .race_id import is_nankan
    seen: set[str] = set()
    out: list[str] = []
    for rid in _RACE_ID_RE.findall(html):
        if rid in seen:
            continue
        if nankan_only and not is_nankan(rid):
            continue
        seen.add(rid)
        out.append(rid)
    return out


def parse_result_page(html: str, race_id: str) -> ParsedRace:
    """結果ページHTMLをパースする(セレクタは要調整)。"""
    if BeautifulSoup is None:
        raise ImportError("beautifulsoup4 が必要です: pip install beautifulsoup4")
    soup = BeautifulSoup(html, "html.parser")

    # --- レース情報(開催日・距離・場)---
    # 例: ".RaceData01" などに「ダ1400m」等。サイト構造に合わせて調整する。
    date = _safe_text(soup.select_one(".RaceData01"))  # TODO: 日付抽出ロジック
    distance = _extract_distance(soup)
    place = _extract_place(soup)

    rows: list[ParsedRow] = []
    # 結果テーブル(例: table.RaceTable01 tr)。サイト構造に合わせて調整する。
    for tr in soup.select("table.RaceTable01 tr")[1:]:
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue
        try:
            finish_pos = int(tds[0].get_text(strip=True))
        except ValueError:
            continue
        # 馬名リンク(/horse/<id>/)から馬の永続IDを取る
        horse_a = tr.find("a", href=lambda h: h and "/horse/" in h)
        horse_id = _href_id(horse_a["href"]) if horse_a else ""
        # 馬番(td.Num など)。無ければ td 列インデックスで代用。
        umaban = _safe_int(tr.select_one("td.Num")) or (_safe_int(tds[2]) if len(tds) > 2 else None)
        rows.append(ParsedRow(
            finish_pos=finish_pos,
            umaban=umaban,
            horse_id=horse_id,
            horse_name=horse_a.get_text(strip=True) if horse_a else "",
            jockey=_safe_text(tds[6]) if len(tds) > 6 else "",
            trainer=None,
            popularity=_safe_int(tds[10]) if len(tds) > 10 else None,
            odds=_safe_float(tds[9]) if len(tds) > 9 else None,
        ))

    return ParsedRace(
        race_id=race_id, date=date or "", place=place, distance=distance,
        field_size=len(rows), rows=rows,
    )


# --- 小物 ---

def _safe_text(node) -> str:
    return node.get_text(strip=True) if node else ""


def _safe_int(node) -> int | None:
    try:
        return int(_safe_text(node))
    except (ValueError, TypeError):
        return None


def _safe_float(node) -> float | None:
    try:
        return float(_safe_text(node))
    except (ValueError, TypeError):
        return None


def _href_id(href: str) -> str:
    return href.rstrip("/").split("/")[-1]


def _extract_distance(soup) -> int:
    import re
    txt = _safe_text(soup.select_one(".RaceData01"))
    m = re.search(r"(\d{3,4})m", txt)
    return int(m.group(1)) if m else 0


def _extract_place(soup) -> str:
    for p in ("大井", "川崎", "船橋", "浦和"):
        if p in soup.get_text():
            return p
    return ""
