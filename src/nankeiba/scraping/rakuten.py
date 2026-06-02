"""楽天競馬(keiba.rakuten.co.jp / 地方競馬 NAR)用のスクレイパ。

netkeiba 版(race_id.py / parser.py / odds.py)と同じ思想の楽天版。出力は
core/dataset.py の JSONL 形式に正規化し、build_dataset.py の入力にできる。

⚠️ 重要(netkeiba 版と同じ運用上の前提):
  - 楽天競馬は HTML 構造を変えることがある。本モジュールのセレクタ・URL・場コード
    は「実データに合わせて調整する出発点」であり、本リポジトリの実行環境は
    egress プロキシで keiba.rakuten.co.jp が遮断されているため**ライブ未検証**。
    ローカル(ネットあり)で実データを見ながら調整すること。
  - レート制限(client.PoliteClient 既定 1.5 秒)を守り、サーバに負荷をかけない。
  - robots.txt と楽天競馬の利用規約を尊重し、個人利用の範囲にとどめる。

設計方針:
  - RACEID は「日次レース一覧ページのリンクから抽出」を主経路にする
    (build_raceid の桁構成はサイト依存で変わりやすいため、リンク抽出が頑健)。
  - オッズは楽天では HTML テーブルで描画される(netkeiba の JSON API と違う)。
    行テキストから「組番 + オッズ」をヒューリスティックに拾う。

BeautifulSoup が必要: pip install beautifulsoup4
"""

from __future__ import annotations

import re

try:
    from bs4 import BeautifulSoup
except ImportError:  # ローカルで未導入なら案内
    BeautifulSoup = None  # type: ignore

# netkeiba 版と同じデータ構造を再利用し、出力 JSONL 形式を統一する
from .parser import ParsedRace, ParsedRow

# --- エンドポイント(要・実データ確認)-------------------------------------
BASE = "https://keiba.rakuten.co.jp"
RACE_LIST_URL = BASE + "/race_card/list/RACEID/{raceid}"       # 出馬表(一覧)
RESULT_URL = BASE + "/race_performance/list/RACEID/{raceid}"   # レース結果
ODDS_URL = {
    "trio": BASE + "/odds/sanrenpuku/RACEID/{raceid}",         # 三連複
    "trifecta": BASE + "/odds/sanrentan/RACEID/{raceid}",      # 三連単
}

# 南関4場の楽天/NAR 場コード(jyoCD)。サイト仕様変更で変わりうるため要確認。
NANKAN_CODES: dict[str, str] = {
    "浦和": "18",
    "船橋": "19",
    "大井": "20",
    "川崎": "21",
}

# 組番(例 "1-2-3" / 全角ハイフン混在も許容)
_COMBO_RE = re.compile(r"(\d{1,2})\s*[-‐－―ー]\s*(\d{1,2})\s*[-‐－―ー]\s*(\d{1,2})")
# オッズらしき小数 or 整数(末尾倍率)
_ODDS_RE = re.compile(r"\d{1,6}(?:\.\d+)?")
# 結果ページの RACEID をリンクから拾う
_RACEID_RE = re.compile(r"/RACEID/(\w+)")


def odds_url(raceid: str, bet_type: str) -> str:
    return ODDS_URL[bet_type].format(raceid=raceid)


def result_url(raceid: str) -> str:
    return RESULT_URL.format(raceid=raceid)


# --- RACEID 抽出(主経路)----------------------------------------------------

def extract_raceids(html: str) -> list[str]:
    """一覧ページHTMLの a[href] から RACEID を重複なく抽出(出現順保持)。

    BeautifulSoup が無くても動くよう、正規表現でも拾えるようにしてある。
    """
    seen: dict[str, None] = {}
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            m = _RACEID_RE.search(a["href"])
            if m:
                seen.setdefault(m.group(1), None)
    else:  # フォールバック
        for m in _RACEID_RE.finditer(html):
            seen.setdefault(m.group(1), None)
    return list(seen)


# --- 結果ページのパース ------------------------------------------------------

def parse_result_page(html: str, raceid: str) -> ParsedRace:
    """結果ページHTMLを ParsedRace に。セレクタは要・実データ調整。

    楽天の結果テーブルはクラス名がバージョンで揺れるため、
    「着順の数字で始まる行を拾う」防御的パースにしてある。
    """
    if BeautifulSoup is None:
        raise ImportError("beautifulsoup4 が必要です: pip install beautifulsoup4")
    soup = BeautifulSoup(html, "html.parser")

    date = _extract_date(soup)
    place = _extract_place(soup)
    distance = _extract_distance(soup)

    rows: list[ParsedRow] = []
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        finish_pos = _safe_int(tds[0])
        if finish_pos is None or finish_pos <= 0:
            continue  # 着順行でない(ヘッダ/除外/取消等)
        umaban = _safe_int(tds[1]) if len(tds) > 1 else None
        horse_a = tr.find("a", href=lambda h: h and "/horse/" in h)
        jockey_a = tr.find("a", href=lambda h: h and "/jockey/" in h)
        rows.append(ParsedRow(
            finish_pos=finish_pos,
            umaban=umaban,
            horse_id=_href_id(horse_a["href"]) if horse_a else "",
            horse_name=horse_a.get_text(strip=True) if horse_a else "",
            jockey=jockey_a.get_text(strip=True) if jockey_a else "",
            trainer=None,
            popularity=None,
            odds=None,
        ))

    rows.sort(key=lambda r: r.finish_pos)
    return ParsedRace(
        race_id=raceid, date=date, place=place, distance=distance,
        field_size=len(rows), rows=rows,
    )


# --- オッズ(HTMLテーブル)のパース ------------------------------------------

def parse_odds_html(html: str, *, bet_type: str) -> dict[tuple[int, ...], float]:
    """三連複/三連単オッズHTMLを {馬番タプル: オッズ} に正規化する。

    各 <tr> の中から「組番」と「オッズらしき数値」を1つずつ拾うヒューリスティック。
    bet_type='trio' は順不同なので昇順タプルに統一、'trifecta' は着順を保持。
    BeautifulSoup が無い場合は行テキスト分割のフォールバックで処理する。
    """
    ordered = bet_type == "trifecta"
    out: dict[tuple[int, ...], float] = {}

    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")
        row_texts = (tr.get_text(" ", strip=True) for tr in soup.find_all("tr"))
    else:
        row_texts = (line for line in html.splitlines())

    for text in row_texts:
        m = _COMBO_RE.search(text)
        if not m:
            continue
        combo = tuple(int(g) for g in m.groups())
        # 組番の直後に現れる数値をオッズとみなす
        tail = text[m.end():]
        om = _ODDS_RE.search(tail)
        if not om:
            continue
        try:
            o = float(om.group())
        except ValueError:
            continue
        if o <= 0:
            continue
        key = combo if ordered else tuple(sorted(combo))
        out[key] = o
    return out


# --- 小物(netkeiba 版 parser.py と同等)-------------------------------------

def _safe_text(node) -> str:
    return node.get_text(strip=True) if node else ""


def _safe_int(node) -> int | None:
    try:
        return int(re.sub(r"\D", "", _safe_text(node)))
    except (ValueError, TypeError):
        return None


def _href_id(href: str) -> str:
    return href.rstrip("/").split("/")[-1]


def _extract_date(soup) -> str:
    """ページテキストから 'YYYY-MM-DD' を抽出(YYYY年M月D日 / YYYY/MM/DD 両対応)。"""
    txt = soup.get_text(" ", strip=True)
    m = re.search(r"(\d{4})[年/](\d{1,2})[月/](\d{1,2})", txt)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d}"
    return ""


def _extract_distance(soup) -> int:
    m = re.search(r"(\d{3,4})\s*m", soup.get_text(" ", strip=True))
    return int(m.group(1)) if m else 0


def _extract_place(soup) -> str:
    txt = soup.get_text()
    for p in NANKAN_CODES:
        if p in txt:
            return p
    return ""
