"""netkeiba のレース結果ページ(地方 NAR / 中央 JRA)をパースする。

重要: netkeiba は HTML 構造を変えることがある。以下のセレクタは
あくまで出発点で、実データを見ながら調整する前提(本環境はネット遮断のため未検証)。
列位置は固定インデックスではなく、ヘッダ行(th)の文言「着順・馬番・騎手・通過・上り…」
から特定するので、地方/中央で列順が違っても追従しやすい。

パース結果は core.interval.RunRecord と core.backtest.Race にマッピングする。
通過順(corner_pos)と上がり3F順位(agari_rank)は展開予想(core/tenkai.py)に使う。

BeautifulSoup が必要: pip install beautifulsoup4
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .race_id import place_of, ALL_CODES

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore


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
    corner_pos: list[int] = field(default_factory=list)
    agari: float | None = None        # 上がり3Fタイム(秒)
    agari_rank: int | None = None     # レース内の上がり順位(1=最速)


@dataclass
class ParsedRace:
    race_id: str
    date: str            # 'YYYY-MM-DD'
    place: str
    distance: int
    field_size: int
    rows: list[ParsedRow]  # 着順順
    surface: str | None = None   # '芝' / 'ダ'
    baba: str | None = None      # '良' / '稍' / '重' / '不'


# ヘッダ文言 → 列キー(部分一致)
_HEADER_KEYS = {
    "着順": "finish", "馬番": "umaban", "馬名": "name", "騎手": "jockey",
    "調教師": "trainer", "厩舎": "trainer", "通過": "corner", "上り": "agari",
    "上がり": "agari", "人気": "pop", "単勝": "odds",
}


def parse_result_page(html: str, race_id: str) -> ParsedRace:
    """結果ページHTMLをパースする(セレクタは要調整)。"""
    if BeautifulSoup is None:
        raise ImportError("beautifulsoup4 が必要です: pip install beautifulsoup4")
    soup = BeautifulSoup(html, "html.parser")

    info = _safe_text(soup.select_one(".RaceData01")) or soup.get_text(" ", strip=True)[:3000]
    distance, surface = _extract_distance_surface(info)
    baba = _extract_baba(info)
    place = place_of(race_id) or _extract_place(soup)
    date = _extract_date(soup, race_id)

    table = soup.select_one("table.RaceTable01") or soup.find("table")
    rows: list[ParsedRow] = []
    if table is not None:
        trs = table.find_all("tr")
        col = _header_columns(trs[0]) if trs else {}
        for tr in trs[1:]:
            row = _parse_row(tr, col)
            if row is not None:
                rows.append(row)

    _fill_agari_rank(rows)
    return ParsedRace(
        race_id=race_id, date=date, place=place, distance=distance,
        field_size=len(rows), rows=rows, surface=surface, baba=baba,
    )


def _header_columns(tr) -> dict[str, int]:
    col: dict[str, int] = {}
    for i, th in enumerate(tr.find_all(["th", "td"])):
        t = th.get_text(strip=True)
        for label, key in _HEADER_KEYS.items():
            if label in t and key not in col:
                col[key] = i
    return col


def _parse_row(tr, col: dict[str, int]) -> ParsedRow | None:
    tds = tr.find_all("td")
    if len(tds) < 5:
        return None

    def cell(key, default_idx=None):
        i = col.get(key, default_idx)
        return tds[i] if i is not None and i < len(tds) else None

    try:
        finish_pos = int(_safe_text(cell("finish", 0)))
    except ValueError:
        return None  # 取消・除外・中止
    horse_a = tr.find("a", href=lambda h: h and "/horse/" in h)
    jockey_a = tr.find("a", href=lambda h: h and "/jockey/" in h)
    trainer_a = tr.find("a", href=lambda h: h and "/trainer/" in h)
    corner_txt = _safe_text(cell("corner"))
    return ParsedRow(
        finish_pos=finish_pos,
        umaban=_safe_int(cell("umaban", 2)),
        horse_id=_href_id(horse_a["href"]) if horse_a else "",
        horse_name=horse_a.get_text(strip=True) if horse_a else _safe_text(cell("name")),
        jockey=jockey_a.get_text(strip=True) if jockey_a else _safe_text(cell("jockey", 6)),
        trainer=(trainer_a.get_text(strip=True) if trainer_a else _safe_text(cell("trainer"))) or None,
        popularity=_safe_int(cell("pop", 10)),
        odds=_safe_float(cell("odds", 9)),
        corner_pos=parse_corner(corner_txt),
        agari=_safe_float(cell("agari")),
    )


def parse_corner(txt: str) -> list[int]:
    """'3-3-2-1' のような通過順文字列を [3,3,2,1] に。"""
    return [int(x) for x in re.findall(r"\d+", txt or "")]


def _fill_agari_rank(rows: list[ParsedRow]) -> None:
    have = sorted((r for r in rows if r.agari is not None), key=lambda r: r.agari)
    for i, r in enumerate(have):
        r.agari_rank = i + 1


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


def _extract_distance_surface(txt: str) -> tuple[int, str | None]:
    """'芝1600m' / 'ダ1400m' / 'ダート1200m' から (距離, '芝'|'ダ')。障害は '障'。"""
    m = re.search(r"(芝|ダート|ダ|障)\D{0,6}?(\d{3,4})m", txt)
    if m:
        s = m.group(1)
        return int(m.group(2)), ("ダ" if s.startswith("ダ") else s)
    m = re.search(r"(\d{3,4})m", txt)
    return (int(m.group(1)) if m else 0), None


def _extract_baba(txt: str) -> str | None:
    m = re.search(r"馬場\s*[:：]\s*(良|稍|重|不)", txt)
    return m.group(1) if m else None


def _extract_date(soup, race_id: str) -> str:
    """ページ内の 'YYYY年M月D日' か、<title>/日付リンクから日付を拾う。"""
    txt = soup.get_text(" ", strip=True)
    m = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", txt)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d}"
    m = re.search(r"kaisai_date=(20\d{2})(\d{2})(\d{2})", str(soup))
    if m:
        return "-".join(m.groups())
    return ""


def _extract_place(soup) -> str:
    text = soup.get_text()
    for p in ALL_CODES:
        if p in text:
            return p
    return ""
