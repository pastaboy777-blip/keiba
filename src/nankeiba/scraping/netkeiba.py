"""netkeiba(中央競馬/JRA)用の取得・パース層。

地方(楽天)用の client/parser と別系統で、中央競馬の出馬表・結果・ラップ・通過順・
オッズを netkeiba から取る。結果ページ(db.netkeiba.com)は EUC-JP、出馬表/オッズ
(race.netkeiba.com)は UTF-8。レースIDは12桁: 年(4)+場(2)+回(2)+日(2)+R(2)。

netkeiba はブラウザ相当の User-Agent でないと弾かれるため、専用UAで PoliteClient を使う。
利用規約・レート制限を尊重して個人利用の範囲で使うこと。

主な関数:
  race_ids_for_date(client, ymd)  … その日の全レースID(race_list_sub.html)
  kaisai_dates(client, y, m)      … その月の開催日一覧(カレンダー)
  parse_result(html)              … 結果テーブル(着順/馬番/通過/上り/人気/単勝 …)
  parse_laps(html)                … ラップタイム[秒]リスト
"""

from __future__ import annotations

import re

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore

from .client import PoliteClient

# JRA 場コード(netkeiba 12桁IDの5-6桁目)
JRA_PLACE = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
    "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉",
}

RESULT_URL = "https://db.netkeiba.com/race/{race_id}/"
# 直近(数日内)の結果は db に未反映。ライブ結果は race.netkeiba 側にある。
RESULT_LIVE_URL = "https://race.netkeiba.com/race/result.html?race_id={race_id}"
SHUTUBA_URL = "https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
RACE_LIST_SUB = "https://race.netkeiba.com/top/race_list_sub.html?kaisai_date={ymd}"
CALENDAR_URL = "https://race.netkeiba.com/top/calendar.html?year={y}&month={m}"

# netkeiba 用ブラウザ相当UA(既定UAだと弾かれる)
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def make_client(*, use_cache: bool = True) -> PoliteClient:
    """netkeiba 用 PoliteClient(ブラウザUA・1.5秒間隔)。文字コードはページ毎に自動判定。"""
    return PoliteClient(user_agent=_UA, use_cache=use_cache, min_interval=1.5)


def race_ids_for_date(client: PoliteClient, ymd: str) -> list[str]:
    """その開催日(YYYYMMDD)の全レースID(12桁)を昇順で返す。"""
    html = client.get(RACE_LIST_SUB.format(ymd=ymd))
    return sorted(set(re.findall(r"race_id=(\d{12})", html)))


def kaisai_dates(client: PoliteClient, year: int, month: int) -> list[str]:
    """その年月の開催日(YYYYMMDD)一覧。"""
    html = client.get(CALENDAR_URL.format(y=year, m=month))
    return sorted(set(re.findall(r"kaisai_date=(\d{8})", html)))


def place_of(race_id: str) -> str:
    return JRA_PLACE.get(race_id[4:6], "?")


def _header_index(rows):
    """結果テーブルのヘッダ→列indexの対応を作る(列順変動に強くする)。"""
    head = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
    idx = {}
    for i, h in enumerate(head):
        for key in ("着順", "馬番", "枠番", "馬名", "騎手", "タイム", "通過", "上り",
                    "単勝", "人気", "馬体重"):
            if h.startswith(key) and key not in idx:
                idx[key] = i
    return idx


def _to_int(s):
    m = re.search(r"-?\d+", s or "")
    return int(m.group()) if m else None


def _to_float(s):
    m = re.search(r"\d+\.\d+", s or "")
    return float(m.group()) if m else None


def parse_result(html: str) -> list[dict]:
    """結果ページHTMLを着順行のリストに正規化する。

    各行: finish_pos, umaban, waku, horse, jockey, time, corner(str),
          agari(float), popularity(int), win_odds(float), last_corner_pos(int|None)
    """
    if BeautifulSoup is None:
        raise ImportError("beautifulsoup4 が必要です")
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_=re.compile(r"race_table_01|RaceTable"))
    if table is None:
        return []
    rows = table.find_all("tr")
    if len(rows) < 2:
        return []
    idx = _header_index(rows)
    out = []
    for tr in rows[1:]:
        tds = tr.find_all("td")
        if len(tds) <= max(idx.values() or [0]):
            continue

        def cell(key):
            return tds[idx[key]].get_text(strip=True) if key in idx else ""

        fp = _to_int(cell("着順"))
        if fp is None:          # 取消・除外・中止は着順なし
            continue
        corner = cell("通過")
        last_pos = None
        if corner:
            nums = re.findall(r"\d+", corner)
            if nums:
                last_pos = int(nums[-1])    # 最終コーナーの位置=脚質判定に使う
        out.append({
            "finish_pos": fp,
            "umaban": _to_int(cell("馬番")),
            "waku": _to_int(cell("枠番")),
            "horse": cell("馬名"),
            "jockey": cell("騎手"),
            "time": cell("タイム") or None,
            "corner": corner or None,
            "last_corner_pos": last_pos,
            "agari": _to_float(cell("上り")),
            "popularity": _to_int(cell("人気")),
            "win_odds": _to_float(cell("単勝")),
        })
    out.sort(key=lambda r: r["finish_pos"])
    return out


def parse_result_live(html: str) -> list[dict]:
    """直近結果(race.netkeiba/result.html)を着順行に正規化する。

    列: 着順/枠/馬番/馬名/性齢/斤量/騎手/タイム/着差/人気/単勝オッズ/後3F/...
    通過は行内に無く、別セクション(コーナー通過順位)にあるため last_corner_order_live で取る。
    """
    if BeautifulSoup is None:
        raise ImportError("beautifulsoup4 が必要です")
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_=re.compile(r"RaceTable01"))
    if table is None:
        return []
    rows = table.find_all("tr")
    if len(rows) < 2:
        return []
    head = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]

    def col(name):
        for i, h in enumerate(head):
            if h.startswith(name):
                return i
        return None

    ci = {k: col(k) for k in ("着順", "馬番", "枠", "馬名", "騎手", "人気", "後3F", "単勝")}
    out = []
    for tr in rows[1:]:
        tds = tr.find_all(["td", "th"])
        if not tds or ci["着順"] is None:
            continue
        fp = _to_int(tds[ci["着順"]].get_text(strip=True))
        if fp is None:
            continue

        def cell(key):
            j = ci.get(key)
            return tds[j].get_text(strip=True) if j is not None and j < len(tds) else ""

        out.append({
            "finish_pos": fp,
            "umaban": _to_int(cell("馬番")),
            "waku": _to_int(cell("枠")),
            "horse": cell("馬名"),
            "jockey": cell("騎手"),
            "popularity": _to_int(cell("人気")),
            "agari": _to_float(cell("後3F")),
            "win_odds": _to_float(cell("単勝")),
        })
    out.sort(key=lambda r: r["finish_pos"])
    return out


def last_corner_order_live(html: str) -> list[int]:
    """コーナー通過順位セクションの最終コーナー並び(馬番・前→後)を返す。

    例 '1(2,12)(3,7)14(5,6)10(4,11)(8,13)9' → [1,2,12,3,7,14,5,6,10,4,11,8,13,9]。
    """
    i = html.find("コーナー通過順位")
    if i < 0:
        return []
    seg = html[i:i + 1500]
    pairs = re.findall(r"<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>", seg, re.S)
    last = ""
    for k, v in pairs:
        if re.search(r"コーナー", re.sub("<[^>]+>", "", k)):
            txt = re.sub("<[^>]+>", "", v).strip()
            if re.search(r"\d", txt):
                last = txt
    return [int(x) for x in re.findall(r"\d+", last)]


def parse_payoffs(html: str) -> dict:
    """結果ページの払戻テーブルから 単勝/複勝/ワイド/三連複 を取り出す(円・100円あたり)。

    返り値: {"win": {馬番: 円}, "place": {馬番: 円},
            "wide": {(a,b)昇順: 円}, "trio": {(a,b,c)昇順: 円}}
    """
    if BeautifulSoup is None:
        raise ImportError("beautifulsoup4 が必要です")
    soup = BeautifulSoup(html, "html.parser")
    out = {"win": {}, "place": {}, "wide": {}, "trio": {}}

    def yens(td):
        return [int(x.replace(",", "")) for x in re.findall(r"[\d,]+", td.decode_contents())]

    def combos(td):
        # "4-14|8-14" や "14|4|8" を br 区切りで分解 → 各々の馬番リスト
        raw = re.sub(r"<br/?>", "|", td.decode_contents())
        return [[int(x) for x in re.findall(r"\d+", part)] for part in raw.split("|") if part.strip()]

    for table in soup.find_all("table", class_=re.compile("pay_table")):
        for tr in table.find_all("tr"):
            th = tr.find("th")
            tds = tr.find_all("td")
            if not th or len(tds) < 2:
                continue
            kind = th.get_text(strip=True)
            cs, ps = combos(tds[0]), yens(tds[1])
            for combo, pay in zip(cs, ps):
                if kind == "単勝" and combo:
                    out["win"][combo[0]] = pay
                elif kind == "複勝" and combo:
                    out["place"][combo[0]] = pay
                elif kind == "ワイド" and len(combo) == 2:
                    out["wide"][tuple(sorted(combo))] = pay
                elif kind == "三連複" and len(combo) == 3:
                    out["trio"][tuple(sorted(combo))] = pay
    return out


def parse_laps(html: str) -> list[float]:
    """ラップタイム[秒]のリスト(全ハロン)。中央は全レース掲載。無ければ []。"""
    m = re.search(r"\d{1,2}\.\d(?:\s*-\s*\d{1,2}\.\d){3,}", html)
    if not m:
        return []
    return [float(x) for x in re.findall(r"\d{1,2}\.\d", m.group())]
