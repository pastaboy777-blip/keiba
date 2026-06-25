"""楽天競馬(keiba.rakuten.co.jp)の三連複・三連単オッズを取得・パースする。

楽天競馬のオッズは JSON API ではなく HTML で配信される。確定後のページにも
確定オッズが残るため、結果と同時に収集できる。

ページ URL:
    三連複: https://keiba.rakuten.co.jp/odds/sanrenfuku/RACEID/<id>
    三連単: https://keiba.rakuten.co.jp/odds/sanrentan/RACEID/<id>

HTML 構造(2026-06 時点で検証済み):
  既定の「枠・馬番順」マトリクス表は頭数が多いと一部組を省略する(切り詰め)。
  一方、同ページ内の隠し要素 <div id="ninkiKohaitoJun">(人気高配当順)に
  **全組み合わせ** が「順位・組番・オッズ」のフラットな表で含まれる。こちらを使う。
    - 三連複: 組番は "8-9-10"(馬番をハイフン区切り・順不同)
    - 三連単: 組番は "9→10→8"(着順を矢印区切り)
  オッズ値は組番セル隣の <span> テキスト(発売外は "-")。

BeautifulSoup が必要: pip install beautifulsoup4
"""

from __future__ import annotations

import re

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore

# bet_type -> 楽天のオッズ種別パス
#   tanfuku = 単勝+複勝の複合ページ(parse_tanfuku で両方取れる)
#   wide    = ワイド(2頭・順不同)
ODDS_KIND = {"trio": "sanrenfuku", "trifecta": "sanrentan",
             "tanfuku": "tanfuku", "wide": "wide"}
ODDS_URL = "https://keiba.rakuten.co.jp/odds/{kind}/RACEID/{race_id}"

# 組番(馬番3つ)を取り出す: "8-9-10" / "9→10→8" の双方に対応
_COMBO_RE = re.compile(r"^\s*(\d+)\s*[-－→]\s*(\d+)\s*[-－→]\s*(\d+)\s*$")
# ワイドの組番(馬番2つ・順不同): "5-10"
_PAIR_RE = re.compile(r"^\s*(\d+)\s*[-－]\s*(\d+)\s*$")


def odds_url(race_id: str, bet_type: str) -> str:
    return ODDS_URL.format(kind=ODDS_KIND[bet_type], race_id=race_id)


def _to_float(text: str) -> float | None:
    text = text.strip().replace(",", "")
    if not text or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _range_low(text: str) -> float | None:
    """複勝・ワイドの『1.2-1.6』表記から下限(保守的な払戻)を返す。単値ならその値。"""
    text = text.strip().replace(",", "")
    if not text or text == "-":
        return None
    lo = text.split("-")[0].split("－")[0].strip()
    return _to_float(lo)


def parse_odds_html(html: str, *, bet_type: str) -> dict[tuple[int, ...], float]:
    """オッズページ HTML を {馬番タプル: オッズ} に正規化する。

    trio(三連複): キーは昇順タプル。trifecta(三連単): キーは着順タプル。
    人気高配当順の全組リスト(切り詰めなし)から抽出する。
    """
    if BeautifulSoup is None:
        raise ImportError("beautifulsoup4 が必要です: pip install beautifulsoup4")
    soup = BeautifulSoup(html, "html.parser")

    container = soup.find(id="ninkiKohaitoJun")
    if container is None:
        return {}

    ordered = bet_type == "trifecta"
    out: dict[tuple[int, ...], float] = {}
    for tr in container.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        m = _COMBO_RE.match(tds[1].get_text(strip=True))
        if not m:
            continue
        combo = tuple(int(x) for x in m.groups())
        if len(set(combo)) != 3:
            continue
        val = _to_float(tds[-1].get_text())
        if val is None or val <= 0:
            continue
        out[combo if ordered else tuple(sorted(combo))] = val
    return out


def parse_tanfuku_html(html: str) -> dict[str, dict[int, float]]:
    """単複ページ HTML を {"win": {馬番: 単勝}, "place": {馬番: 複勝下限}} に正規化する。

    人気高配当順の表は 馬番が <th>、<td> が [順位, 馬名, 単勝, 複勝] の並び。
    複勝はレンジ表記(例 "1.2-1.6")のため、保守的に下限を採用する。発売外(-)は除外。
    """
    if BeautifulSoup is None:
        raise ImportError("beautifulsoup4 が必要です: pip install beautifulsoup4")
    soup = BeautifulSoup(html, "html.parser")
    container = soup.find(id="ninkiKohaitoJun")
    win: dict[int, float] = {}
    place: dict[int, float] = {}
    if container is None:
        return {"win": win, "place": place}
    for tr in container.find_all("tr"):
        th = tr.find("th")
        tds = tr.find_all("td")
        if th is None or len(tds) < 4:
            continue
        try:
            um = int(th.get_text(strip=True))
        except ValueError:
            continue
        w = _to_float(tds[2].get_text())
        p = _range_low(tds[3].get_text())
        if w is not None and w > 0:
            win[um] = w
        if p is not None and p > 0:
            place[um] = p
    return {"win": win, "place": place}


def parse_wide_html(html: str) -> dict[tuple[int, int], float]:
    """ワイドページ HTML を {(馬番a,馬番b)昇順: オッズ下限} に正規化する。

    [順位, 組番, オッズ] の並び。組番は "5-10"、オッズはレンジ表記のため下限を採用。
    """
    if BeautifulSoup is None:
        raise ImportError("beautifulsoup4 が必要です: pip install beautifulsoup4")
    soup = BeautifulSoup(html, "html.parser")
    container = soup.find(id="ninkiKohaitoJun")
    out: dict[tuple[int, int], float] = {}
    if container is None:
        return out
    for tr in container.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        m = _PAIR_RE.match(tds[1].get_text(strip=True))
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if a == b:
            continue
        val = _range_low(tds[-1].get_text())
        if val is None or val <= 0:
            continue
        out[tuple(sorted((a, b)))] = val
    return out
