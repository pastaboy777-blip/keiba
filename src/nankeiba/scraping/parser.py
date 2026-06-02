"""楽天競馬(keiba.rakuten.co.jp)のページをパースする。

対象:
  - レース一覧/出馬表ページ … 各レースの実 RACEID リンクを収集(parse_race_links)
  - 競走成績ページ(race_performance) … 着順・馬・騎手・調教師・人気を抽出
    (parse_result_page)

楽天競馬の HTML 構造に合わせて実装・検証済み(2026-06 時点)。
サイト改修でクラス名等が変わった場合はここを調整する。

BeautifulSoup が必要: pip install beautifulsoup4
"""

from __future__ import annotations

import re
from dataclasses import dataclass

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore

from .race_id import parse_race_id


@dataclass
class ParsedRow:
    finish_pos: int
    umaban: int | None
    waku: int | None
    horse_id: str
    horse_name: str
    jockey: str
    trainer: str | None
    popularity: int | None
    time: str | None


@dataclass
class ParsedRace:
    race_id: str
    date: str            # 'YYYY-MM-DD'
    place: str
    distance: int
    surface: str         # 'ダ' / '芝'
    field_size: int
    rows: list[ParsedRow]  # 着順順


# ---------------------------------------------------------------------------
# レース一覧 / 出馬表ページ -> 各レースの RACEID
# ---------------------------------------------------------------------------

_RACE_HREF = re.compile(r"/race_card/list/RACEID/(\d{18})")


def parse_race_links(html: str, *, date_yyyymmdd: str, jyo_code: str) -> list[tuple[int, str]]:
    """一覧/出馬表ページから、その日・その場のレース RACEID を昇順で返す。

    返り値: [(race_no, race_id), ...]  (race_no=1..12)
    日付(YYYYMMDD)と場コードの一致する 18桁 RACEID のうち、末尾2桁(R)が
    01..12 のものだけを採用する(末尾00はインデックスなので除外)。
    """
    prefix = f"{date_yyyymmdd}{jyo_code}"
    seen: dict[int, str] = {}
    for rid in _RACE_HREF.findall(html):
        if not rid.startswith(prefix):
            continue
        rno = int(rid[16:18])
        if 1 <= rno <= 12:
            seen.setdefault(rno, rid)
    return sorted(seen.items())


# ---------------------------------------------------------------------------
# 競走成績ページ -> ParsedRace
# ---------------------------------------------------------------------------

def parse_result_page(html: str, race_id: str) -> ParsedRace:
    """競走成績ページ(race_performance)をパースする。"""
    if BeautifulSoup is None:
        raise ImportError("beautifulsoup4 が必要です: pip install beautifulsoup4")
    soup = BeautifulSoup(html, "html.parser")

    info = parse_race_id(race_id)
    # 場名は RACEID の場コードが最も確実(本文には「大井・川崎…」等の説明文が
    # 混ざるため text スキャンは誤検出しうる)。コード不明時のみ本文から補完。
    place = info["place"] or _extract_place(soup)
    distance, surface = _extract_distance(soup)

    rows: list[ParsedRow] = []
    table = _find_result_table(soup)
    if table is not None:
        body = table.find("tbody") or table
        for tr in body.find_all("tr"):
            order_td = tr.find("td", class_="order")
            if order_td is None:
                continue
            finish_pos = _safe_int(order_td)
            if finish_pos is None:  # 中止・除外・取消などは着順なし
                continue
            horse_a = tr.find("a", href=lambda h: h and "HORSEID/" in h)
            rows.append(ParsedRow(
                finish_pos=finish_pos,
                umaban=_safe_int(tr.find("td", class_="number")),
                waku=_safe_int(tr.find(class_="position")),
                horse_id=_href_id(horse_a["href"]) if horse_a else "",
                horse_name=horse_a.get_text(strip=True) if horse_a else "",
                jockey=_clean_person(tr.find("td", class_="jockey")),
                trainer=_clean_person(tr.find("td", class_="tamer")) or None,
                popularity=_safe_int(tr.find("td", class_="rank")),
                time=_safe_text(tr.find("td", class_="time")) or None,
            ))

    rows.sort(key=lambda r: r.finish_pos)
    return ParsedRace(
        race_id=race_id, date=info["date"], place=place,
        distance=distance, surface=surface,
        field_size=len(rows), rows=rows,
    )


# --- 小物 ---

def _find_result_table(soup):
    """着順表(th.order と td.horse を持つ table)を探す。"""
    for table in soup.find_all("table"):
        if table.find(class_="order") and table.find(class_="horse"):
            return table
    return None


def _safe_text(node) -> str:
    return node.get_text(strip=True) if node else ""


def _safe_int(node) -> int | None:
    txt = _safe_text(node)
    m = re.search(r"\d+", txt)
    return int(m.group()) if m else None


def _clean_person(node) -> str:
    """騎手/調教師セルから所属(船橋)等・改行を除いた名前を返す。"""
    if node is None:
        return ""
    txt = node.get_text(" ", strip=True)
    txt = re.sub(r"[（(].*?[）)]", "", txt)  # (船橋) 等の所属を除去
    return re.sub(r"\s+", "", txt)


def _href_id(href: str) -> str:
    m = re.search(r"HORSEID/(\d+)", href)
    return m.group(1) if m else ""


def _extract_distance(soup) -> tuple[int, str]:
    """li.distance("ダ1,200m" 等)から距離と馬場(ダ/芝)を取る。"""
    node = soup.find(class_="distance")
    txt = _safe_text(node) or soup.get_text()
    m = re.search(r"([ダ芝])\s*([\d,]+)\s*m", txt)
    if not m:
        return 0, ""
    return int(m.group(2).replace(",", "")), m.group(1)


def _extract_place(soup) -> str:
    for p in ("大井", "川崎", "船橋", "浦和"):
        if p in soup.get_text():
            return p
    return ""
