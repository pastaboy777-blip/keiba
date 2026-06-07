"""楽天競馬(keiba.rakuten.co.jp)からレース成績(ラップ含む)を取得・パースする。

楽天競馬の成績ページは race_performance/list/RACEID/<RACEID> にあり、
「ハロンタイム」「上がり」「コーナー通過順位」が掲載されている。
RACEID は 18桁で先頭8桁が YYYYMMDD、続く8桁が場・開催コード、末尾2桁がレース番号。
場コードは開催ごとに変わるため、日付一覧ページから場名で引き当てる。

注意:
  - 成績ページは Cookie とリファラが無いと空ページ(0000/00/00)を返す。
    RakutenClient は一覧ページで Cookie を温めてからリファラ付きで取得する。
  - 礼儀として取得間隔を空け、ローカルキャッシュを使う。
  - requests が必要(scraping/client.py と同様)。

本環境(クラウド)からは楽天競馬へ到達できることを確認済みだが、サイト構造は
変わりうるのでセレクタは実HTMLに合わせて調整すること。
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from pathlib import Path

try:
    import requests
except ImportError:  # ローカル未導入なら案内
    requests = None  # type: ignore

BASE = "https://keiba.rakuten.co.jp"
LIST_URL = BASE + "/race_card/list/RACEID/{rid}"
PERF_URL = BASE + "/race_performance/list/RACEID/{rid}"

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)


@dataclass
class RakutenRace:
    """成績ページからパースしたラップ関連の生データ。"""
    race_id: str
    place: str
    race_no: int
    date: str            # 'YYYY-MM-DD'
    race_name: str
    surface: str         # 'ダ'/'芝'
    distance: int        # m
    going: str           # 馬場状態
    weather: str         # 天候
    furlong_str: str     # ハロンタイム '12.7-12.7-...'
    last_3f: float | None
    corners: list[str]   # コーナー通過順位の各角


class RakutenClient:
    def __init__(
        self,
        cache_dir: str | Path = "data/cache_rakuten",
        *,
        min_interval: float = 1.5,
        timeout: float = 15.0,
    ):
        if requests is None:
            raise ImportError("requests が必要です: pip install requests")
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.min_interval = min_interval
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = _BROWSER_UA
        self._last = 0.0
        self._warmed: set[str] = set()

    def _cache_path(self, url: str) -> Path:
        key = hashlib.sha256(url.encode()).hexdigest()[:24]
        return self.cache / f"{key}.html"

    def _throttle(self) -> None:
        wait = self.min_interval - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()

    def get(self, url: str, *, referer: str | None = None, use_cache: bool = True) -> str:
        cp = self._cache_path(url)
        if use_cache and cp.exists():
            return cp.read_text(encoding="utf-8")
        self._throttle()
        headers = {"Referer": referer} if referer else {}
        resp = self.session.get(url, headers=headers, timeout=self.timeout)
        if not resp.encoding or resp.encoding.lower() in ("iso-8859-1", "ascii"):
            resp.encoding = resp.apparent_encoding
        resp.raise_for_status()
        html = resp.text
        cp.write_text(html, encoding="utf-8")
        return html

    # -- 日付一覧から場の RACEID ベースを引き当てる --
    def resolve_place_base(self, date_yyyymmdd: str, place: str) -> str | None:
        """指定日の一覧から place(例 '大井')の RACEID ベース(末尾RR=00)を返す。"""
        rid = f"{date_yyyymmdd}0000000000"
        html = self.get(LIST_URL.format(rid=rid))
        for m in re.finditer(
            r'race_card/list/RACEID/(' + re.escape(date_yyyymmdd) + r'\d{10})"[^>]*>(.*?)</a>',
            html, re.S,
        ):
            cand, txt = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
            # 場名は「大　井」のように全角空白を挟むことがある
            if place in txt.replace("　", "").replace(" ", ""):
                return cand
        return None

    def fetch_performance(self, race_id: str, *, place_base: str | None = None) -> str:
        """成績ページHTMLを取得(Cookie温め + リファラ付き)。"""
        # 同一開催の一覧で一度だけ Cookie を温める
        warm_key = race_id[:8]
        ref = LIST_URL.format(rid=(place_base or (race_id[:-2] + "00")))
        if warm_key not in self._warmed:
            try:
                self.get(ref, use_cache=False)
            except Exception:
                pass
            self._warmed.add(warm_key)
        return self.get(PERF_URL.format(rid=race_id), referer=ref)


# ---------------------------------------------------------------------------
# パース
# ---------------------------------------------------------------------------

def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def _to_date(jp: str) -> str:
    m = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", jp)
    if not m:
        return ""
    y, mo, d = m.groups()
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def parse_performance(html: str, race_id: str) -> RakutenRace:
    """成績ページHTMLを RakutenRace にパースする。"""
    place = ""
    m = re.search(r'class="racePlace">([^<]+)</span>', html)
    if m:
        place = _clean(m.group(1))
    race_no = 0
    m = re.search(r'class="raceNumber"><span class="num">(\d+)</span>', html)
    if m:
        race_no = int(m.group(1))
    elif race_id[-2:].isdigit():
        race_no = int(race_id[-2:])

    date = ""
    m = re.search(r'class="trackState">(.*?)</ul>', html, re.S)
    if m:
        date = _to_date(_clean(m.group(1)))

    surface, distance = "", 0
    m = re.search(r'class="distance">(.*?)</li>', html, re.S)
    if m:
        dtxt = _clean(m.group(1))
        if "芝" in dtxt:
            surface = "芝"
        elif "ダ" in dtxt:
            surface = "ダ"
        dm = re.search(r"([\d,]+)\s*m", dtxt)
        if dm:
            distance = int(dm.group(1).replace(",", ""))

    weather = ""
    m = re.search(r"天候：</dt><dd>([^<]+)</dd>", html)
    if m:
        weather = _clean(m.group(1))
    going = ""
    m = re.search(r"[ダ芝]：</dt><dd>([^<]+)</dd>", html)
    if m:
        going = _clean(m.group(1))

    race_name = ""
    m = re.search(r"</ul>\s*<h2>(.*?)</h2>", html, re.S)
    if m:
        race_name = _clean(m.group(1))

    furlong_str = ""
    m = re.search(r"ハロンタイム</th>\s*<td>(.*?)</td>", html, re.S)
    if m:
        furlong_str = _clean(m.group(1))

    last_3f = None
    m = re.search(r">上がり</th>\s*<td>(.*?)</td>", html, re.S)
    if m:
        agtxt = _clean(m.group(1))
        a3 = re.search(r"3F\s*([\d.]+)", agtxt)
        if a3:
            try:
                last_3f = float(a3.group(1))
            except ValueError:
                pass

    corners: list[str] = []
    cm = re.search(r"コーナー通過順位.*?</table>", html, re.S)
    if cm:
        for row in re.finditer(r'<th[^>]*>([^<]+)</th>\s*<td[^>]*>([^<]*)</td>', cm.group(0)):
            corners.append(f"{_clean(row.group(1))} {_clean(row.group(2))}")

    return RakutenRace(
        race_id=race_id, place=place, race_no=race_no, date=date,
        race_name=race_name, surface=surface, distance=distance,
        going=going, weather=weather, furlong_str=furlong_str,
        last_3f=last_3f, corners=corners,
    )
