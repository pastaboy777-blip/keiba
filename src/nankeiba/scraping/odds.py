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
ODDS_KIND = {"trio": "sanrenfuku", "trifecta": "sanrentan"}
ODDS_URL = "https://keiba.rakuten.co.jp/odds/{kind}/RACEID/{race_id}"

# 組番(馬番3つ)を取り出す: "8-9-10" / "9→10→8" の双方に対応
_COMBO_RE = re.compile(r"^\s*(\d+)\s*[-－→]\s*(\d+)\s*[-－→]\s*(\d+)\s*$")


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
