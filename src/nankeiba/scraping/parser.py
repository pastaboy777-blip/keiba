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


@dataclass
class PastRun:
    """出馬表に載る各馬の1走分の近走履歴(前のセッションで重視した観点の素)。"""
    date: str | None         # 'YYYY-MM-DD'(間隔・叩き判定の核)
    place: str | None        # 競馬場(場替わり判定)
    distance: int | None     # 距離[m](距離変更判定)
    surface: str | None      # 'ダ' / '芝'
    field_size: int | None
    finish_pos: int | None
    popularity: int | None
    jockey: str | None       # 乗り替わり判定
    weight_carried: float | None
    time: str | None
    agari: float | None      # 上がり3F[秒]
    horse_weight: int | None
    gate: int | None
    corner: list[int]        # コーナー通過順(脚質)
    baba: str | None
    race_name: str | None


@dataclass
class CardEntry:
    """出馬表の1頭分。"""
    umaban: int | None
    waku: int | None
    horse_id: str
    horse_name: str
    sire: str | None
    dam: str | None
    broodmare_sire: str | None
    sex_age: str | None
    weight_carried: float | None
    jockey: str | None
    jockey_affil: str | None
    jockey_win_rate: float | None    # 騎手【勝率】= 追える力の代理
    jockey_top3_rate: float | None   # 騎手【3着内率】
    trainer: str | None
    horse_weight: int | None
    horse_weight_diff: int | None
    exp_odds: float | None           # 出馬表時点の予想オッズ
    exp_pop: int | None              # 予想人気
    recent_runs: list[PastRun]


@dataclass
class ParsedCard:
    race_id: str
    date: str
    place: str
    distance: int
    surface: str
    field_size: int
    race_name: str
    entries: list[CardEntry]


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


# ---------------------------------------------------------------------------
# レース条件(天候・馬場・発走時刻) ※成績/出馬表ページ共通
# ---------------------------------------------------------------------------

_BABA_SHORT = {"良": "良", "稍重": "稍", "稍": "稍", "重": "重", "不良": "不", "不": "不"}


def parse_conditions(html: str) -> dict:
    """ページから天候・馬場(ダ/芝)・発走時刻を抜く。

    返り値: {"weather": "雨", "baba": "不", "baba_full": "不良", "post_time": "14:30"}
    取れない項目は None。
    """
    weather = _search(r"天候[：:]\s*</dt>\s*<dd>\s*([^<\s]+)", html)
    bm = re.search(r"<dt>\s*[ダ芝][：:]\s*</dt>\s*<dd>\s*([良稍重不]+)", html)
    baba_full = bm.group(1) if bm else None
    post = _search(r"発走時刻\s*</dt>\s*<dd>\s*([0-9]{1,2}:[0-9]{2})", html)
    return {
        "weather": weather,
        "baba_full": baba_full,
        "baba": _BABA_SHORT.get(baba_full) if baba_full else None,
        "post_time": post,
    }


# ---------------------------------------------------------------------------
# 出馬表(race_card)ページ -> ParsedCard(各馬の近走履歴つき)
# ---------------------------------------------------------------------------

def parse_card_page(html: str, race_id: str) -> ParsedCard:
    """出馬表ページをパースし、各馬の基本情報 + 前5走の近走履歴を返す。"""
    if BeautifulSoup is None:
        raise ImportError("beautifulsoup4 が必要です: pip install beautifulsoup4")
    soup = BeautifulSoup(html, "html.parser")
    info = parse_race_id(race_id)
    distance, surface = _extract_distance(soup)
    race_name = _safe_text(soup.find("h1", class_="unique"))

    entries: list[CardEntry] = []
    for tr in soup.find_all("tr"):
        name_td = tr.find("td", class_="name")
        if name_td is None or not name_td.find("a", href=lambda h: h and "HORSEID/" in h):
            continue
        entries.append(_parse_card_entry(tr))

    return ParsedCard(
        race_id=race_id, date=info["date"], place=info["place"] or _extract_place(soup),
        distance=distance, surface=surface, field_size=len(entries),
        race_name=race_name, entries=entries,
    )


def _parse_card_entry(tr) -> CardEntry:
    name_td = tr.find("td", class_="name")
    horse_a = name_td.find("a", href=lambda h: h and "HORSEID/" in h)
    horse_name = horse_a.get_text(strip=True)
    name_txt = name_td.get_text(" ", strip=True)
    sire = name_txt.split(horse_name)[0].strip() or None
    dam = None
    after = name_txt.split(horse_name, 1)[-1].lstrip()
    if after and not after[0] in "(（":
        dam = after.split("(")[0].split("（")[0].strip() or None
    # 母父: 馬名の後の最初の括弧(人気の「（N人気）」より前に出る)
    bms_m = re.search(r"[（(]\s*([^）)0-9]+?)\s*[）)]", after)
    broodmare_sire = bms_m.group(1).strip() if bms_m else None
    m_odds = re.search(r"([\d.]+)\s*[（(]\s*(\d+)\s*人気", name_txt)
    exp_odds = float(m_odds.group(1)) if m_odds else None
    exp_pop = int(m_odds.group(2)) if m_odds else None

    prof = tr.find("td", class_="profile")
    prof_txt = prof.get_text(" ", strip=True) if prof else ""
    sex_age = _search(r"([牡牝セ騸せん]+\d+)", prof_txt)
    rates = re.findall(r"【\s*([\d.]+)\s*%", prof_txt)
    win_rate = float(rates[0]) if rates else None
    top3_rate = float(rates[1]) if len(rates) > 1 else None
    affil_m = re.search(r"[（(]([^）)]+)[）)]", prof_txt)
    jockey_affil = re.sub(r"\s+", "", affil_m.group(1)) if affil_m else None
    weight_carried = _searchf(r"(\d{2,3}\.\d)", prof_txt)
    # 騎手名: 負担重量と所属（…）の間
    jockey = None
    jm = re.search(r"\d{2,3}\.\d\s+(\S+?)\s*[（(]", prof_txt)
    if jm:
        jockey = jm.group(1)
    trainer = prof_txt.rsplit("】", 1)[-1].strip() or None if "】" in prof_txt else None

    wd = tr.find("td", class_="weightDistance")
    horse_weight = horse_weight_diff = None
    if wd:
        wt = wd.get_text(" ", strip=True)
        hw = re.search(r"(\d+)", wt)
        df = re.search(r"([+-]\d+)", wt)
        horse_weight = int(hw.group(1)) if hw else None
        horse_weight_diff = int(df.group(1)) if df else None

    runs = [_parse_past_run(td)
            for td in tr.find_all("td", class_=re.compile(r"\bplace\d+"))]

    return CardEntry(
        umaban=_safe_int(tr.find("td", class_="number")),
        waku=_safe_int(tr.find(class_="position")),
        horse_id=_href_id(horse_a["href"]), horse_name=horse_name,
        sire=sire, dam=dam, broodmare_sire=broodmare_sire,
        sex_age=sex_age, weight_carried=weight_carried,
        jockey=jockey, jockey_affil=jockey_affil,
        jockey_win_rate=win_rate, jockey_top3_rate=top3_rate, trainer=trainer,
        horse_weight=horse_weight, horse_weight_diff=horse_weight_diff,
        exp_odds=exp_odds, exp_pop=exp_pop, recent_runs=runs,
    )


def _parse_past_run(td) -> PastRun:
    finish_pos = _safe_int(td.find("span", class_="place"))
    baba = _safe_text(td.find("span", class_="stateInfo")) or None
    field_size = _safe_int(td.find("span", class_="numberInfo"))
    race_name = _safe_text(td.find("span", class_="raceName")) or None
    # 日付は近走リンクの RACEID(YYYYMMDD…)が最も確実
    date = None
    link = td.find("a", href=re.compile(r"RACEID/\d{8}"))
    if link:
        m = re.search(r"RACEID/(\d{4})(\d{2})(\d{2})", link["href"])
        if m:
            date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # 残りテキストを行で解析(firstInfo/raceName を除去)
    work = BeautifulSoup(str(td), "html.parser")
    for el in work.find_all(class_=["firstInfo", "raceName"]):
        el.extract()
    lines = [x.strip() for x in work.get_text("\n").split("\n") if x.strip()]

    place = lines[0].split()[0] if lines else None
    if date is None and lines:  # フォールバック: "YY.MM.DD"
        dm = re.search(r"(\d{2})\.(\d{2})\.(\d{2})", lines[0])
        if dm:
            date = f"20{dm.group(1)}-{dm.group(2)}-{dm.group(3)}"
    blob = "\n".join(lines)
    dm = re.search(r"(\d{3,4})\s*([左右直]?)\s*([ダ芝])", blob)
    distance = int(dm.group(1)) if dm else None
    surface = dm.group(3) if dm else None
    popularity = None
    pm = re.search(r"(?m)^\s*(\d+)人\s*$", blob)
    jockey = weight_carried = None
    if pm:
        popularity = int(pm.group(1))
        # 人気の次行 = 騎手、その次 = 負担重量
        idx = lines.index(pm.group(0).strip()) if pm.group(0).strip() in lines else None
        if idx is not None and idx + 1 < len(lines):
            jockey = re.sub(r"^[▲△☆◇★]+", "", lines[idx + 1]).strip() or None
        if idx is not None and idx + 2 < len(lines):
            wm = re.match(r"^(\d{2,3}\.\d)$", lines[idx + 2])
            weight_carried = float(wm.group(1)) if wm else None
    agm = re.search(r"(\d{2}\.\d)\s+(\d+)k\s+(\d+)番", blob)
    agari = float(agm.group(1)) if agm else None
    horse_weight = int(agm.group(2)) if agm else None
    gate = int(agm.group(3)) if agm else None
    time = _search(r"(\d:\d{2}\.\d)", blob)
    cm = re.search(r"(?m)^\s*(\d+(?:-\d+)+)\s*$", blob)
    corner = [int(x) for x in cm.group(1).split("-")] if cm else []

    return PastRun(
        date=date, place=place, distance=distance, surface=surface,
        field_size=field_size, finish_pos=finish_pos, popularity=popularity,
        jockey=jockey, weight_carried=weight_carried, time=time, agari=agari,
        horse_weight=horse_weight, gate=gate, corner=corner, baba=baba,
        race_name=race_name,
    )


# --- 小物 ---

def _search(pat: str, text: str) -> str | None:
    m = re.search(pat, text)
    return m.group(1) if m else None


def _searchf(pat: str, text: str) -> float | None:
    m = re.search(pat, text)
    return float(m.group(1)) if m else None


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
