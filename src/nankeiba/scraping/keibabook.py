"""競馬ブック(p.keibabook.co.jp)からの取得クライアント。

会員 Cookie を使って、地方(南関)レースの出馬表と各馬のDB成績を取得し、
指数・新聞生成に使う RunRecord / PaperEntry へ正規化する。

取得できるページ(このアカウントの権限で確認済み):
  - 日程   /chihou/nittei/YYYYMMDD           … 開催・レース一覧(place→race_id)
  - 出馬表 /chihou/syutuba/{race_id}          … 馬番/馬名/性齢/騎手/厩舎/馬コード
  - DB成績 /db/uma/{umacd}/seiseki            … 過去走(年月日/場/馬場/頭数/着/距離/
                                                タイム/着差/上り3F/ペース)

⚠️ 通過順(コーナー通過位置)と前半3F は、このプランでは "****" でマスクされており
   取得できない(展開予想グリッドの構築には別途データが必要)。タイム系は全て取得可。

⚠️ 節度を持って利用すること: 会員本人の個人利用の範囲で、アクセス間隔を空け、
   競馬ブックの利用規約を尊重すること。取得データの再配布はしない。

依存: 標準ライブラリのみ(urllib)。プロキシと CA bundle は環境変数から拾う。
"""

from __future__ import annotations

import gzip
import os
import re
import ssl
import time
import urllib.request
from html import unescape
from pathlib import Path
from typing import Iterable

from ..core.interval import RunRecord

BASE = "https://p.keibabook.co.jp"
_UA = "Mozilla/5.0 (nankeiba; personal-use)"
_PLACES = ["大井", "川崎", "船橋", "浦和", "笠松", "名古屋", "名古", "金沢",
           "園田", "姫路", "高知", "佐賀", "門別", "盛岡", "水沢", "帯広", "浦和"]
_NANKAN = {"大井", "川崎", "船橋", "浦和"}


# ---------------------------------------------------------------------------
# 低レベル取得(Cookie・プロキシ・レート制限)
# ---------------------------------------------------------------------------

def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    for env in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        p = os.environ.get(env)
        if p and os.path.exists(p):
            ctx.load_verify_locations(p)
            return ctx
    for p in ("/root/.ccr/ca-bundle.crt",):
        if os.path.exists(p):
            ctx.load_verify_locations(p)
            return ctx
    return ctx


def load_cookie(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8").strip()


class KeibabookClient:
    """会員 Cookie 付きの取得クライアント(レート制限・キャッシュ付き)。"""

    def __init__(self, cookie: str, *, min_interval: float = 1.5,
                 cache_dir: str | Path | None = "data/cache/keibabook",
                 timeout: float = 25.0):
        self.cookie = cookie
        self.min_interval = min_interval
        self.timeout = timeout
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._ctx = _ssl_context()
        self._last = 0.0
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler(urllib.request.getproxies()),
            urllib.request.HTTPSHandler(context=self._ctx),
        )
        self._opener = opener

    @classmethod
    def from_cookie_file(cls, path: str | Path, **kw) -> "KeibabookClient":
        return cls(load_cookie(path), **kw)

    def _throttle(self):
        dt = time.monotonic() - self._last
        if dt < self.min_interval:
            time.sleep(self.min_interval - dt)
        self._last = time.monotonic()

    def get(self, path: str, *, use_cache: bool = True, retries: int = 3) -> str:
        url = path if path.startswith("http") else BASE + path
        cache = None
        if self.cache_dir and use_cache:
            key = re.sub(r"[^0-9A-Za-z]+", "_", path).strip("_")
            cache = self.cache_dir / f"{key}.html"
            if cache.exists():
                return cache.read_text(encoding="utf-8")
        last_err: Exception | None = None
        for i in range(retries):
            try:
                self._throttle()
                req = urllib.request.Request(url, headers={
                    "User-Agent": _UA, "Cookie": self.cookie,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Encoding": "gzip",
                })
                with self._opener.open(req, timeout=self.timeout) as r:
                    raw = r.read()
                    if r.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    html = raw.decode("utf-8", "replace")
                if cache is not None:
                    cache.write_text(html, encoding="utf-8")
                return html
            except Exception as e:               # noqa: BLE001
                last_err = e
                time.sleep(2 ** i)
        raise RuntimeError(f"取得失敗: {url}: {last_err}")


# ---------------------------------------------------------------------------
# パース用ユーティリティ
# ---------------------------------------------------------------------------

def _text(s: str) -> str:
    return unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s))).strip()


def _cells(row_html: str) -> list[str]:
    return [_text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S)]


def parse_time(s: str) -> float | None:
    """'1.43.5'→103.5、'59.3'→59.3、'2.38.6'→158.6。"""
    m = re.match(r"(?:(\d+)\.)?(\d{1,2})\.(\d)$", (s or "").strip())
    if not m:
        return None
    return round(int(m.group(1) or 0) * 60 + int(m.group(2)) + int(m.group(3)) / 10, 1)


def parse_distance(s: str) -> tuple[int | None, str | None]:
    """'ダ1600'→(1600,'ダ')、'芝1400'→(1400,'芝')。"""
    surf = "ダ" if "ダ" in s else ("芝" if "芝" in s else None)
    d = re.sub(r"\D", "", s)
    return (int(d) if d else None, surf)


def normalize_place(s: str) -> str:
    """'3阪神6'→'阪神'、'大井'→'大井'。前後の開催回数字を除去。"""
    return re.sub(r"\d+", "", s or "").strip()


def normalize_baba(s: str) -> str | None:
    for c in (s or ""):
        if c in "良稍重不":
            return c
    return None


# ---------------------------------------------------------------------------
# 日程 → race_id
# ---------------------------------------------------------------------------

def list_races_by_place(html: str) -> dict[str, list[str]]:
    """日程ページ(または raceindex)から place→[race_id] を作る。

    raceindex の keibajyo リストが place と現在レースの race_id を持つ。
    ここでは日程ページ全体から (place見出し, syutuba race_id) を紐づける。
    """
    # raceindex の keibajyo: <li ..><a href="{race_id}">大井</a></li>
    out: dict[str, list[str]] = {}
    for m in re.finditer(r'<a href="(\d{16})">(大井|川崎|船橋|浦和|笠松|名古屋|金沢|園田|門別|高知|佐賀|盛岡|水沢|帯広)</a>', html):
        rid, place = m.group(1), m.group(2)
        # 同一開催の全レースは末尾以外を共有: prefix(10)+RR(2)+MMDD(4)
        prefix, mmdd = rid[:10], rid[12:]
        ids = [f"{prefix}{rr:02d}{mmdd}" for rr in range(1, 13)]
        out.setdefault(place, ids)
    return out


def find_meeting(client: KeibabookClient, date: str, place: str) -> list[str]:
    """place(例 '大井')の当該開催の race_id 12 レースを返す。"""
    # syutuba ページの raceindex が最も確実(place→現race_id)
    html = client.get(f"/chihou/nittei/{date}")
    races = list_races_by_place(html)
    if place in races:
        return races[place]
    # フォールバック: 任意 syutuba を開いて raceindex から解決
    m = re.search(r"/chihou/syutuba/(\d{16})", html)
    if m:
        idx = client.get(f"/chihou/syutuba/{m.group(1)}")
        races = list_races_by_place(idx)
        if place in races:
            return races[place]
    raise RuntimeError(f"{date} の {place} が見つからない")


# ---------------------------------------------------------------------------
# 出馬表 → エントリ(馬番/馬名/騎手/厩舎/馬コード)
# ---------------------------------------------------------------------------

_HEADER_RE = re.compile(r"(20\d\d)年(\d+)月(\d+)日([^\d<|]+?)(\d+)R([^<|]*)")


def parse_race_header(html: str):
    """出馬表/成績ページのタイトルから (place, race_no, race_name) を返す。"""
    m = _HEADER_RE.search(html)
    if not m:
        return None
    place = normalize_place(m.group(4))
    name = re.split(r"[|｜]", m.group(6))[0]
    name = re.sub(r"(出馬表|能力表|成績|ＨＴＭＬ|HTML).*$", "", name).strip()
    return {"place": place.strip(), "race_no": int(m.group(5)), "race_name": name}


def parse_entries(html: str) -> list[dict]:
    """出馬表テーブルから各馬 {umaban,name,sex_age,jockey,trainer,umacd}。"""
    mt = re.search(r'<table[^>]*syutuba[^>]*>.*?</table>', html, re.S)
    if not mt:
        return []
    rows = re.findall(r"<tr.*?</tr>", mt.group(0), re.S)
    entries = []
    for r in rows:
        um = re.search(r'/db/uma/(\d+)', r)
        cells = _cells(r)
        if not um or len(cells) < 12:
            continue
        # 列: 枠 馬番 My印 ... 馬名★ 性齢 減量 騎手 斤量 厩舎 ...
        try:
            umaban = int(cells[1])
        except (ValueError, IndexError):
            continue
        name = next((c.replace("★", "").replace("☆", "").strip()
                     for c in cells if re.search(r"[ぁ-んァ-ヶ一-龠]", c) and "★" in c), None)
        # 性齢・騎手はセル位置が可変なので正規表現で拾う
        sex = next((c for c in cells if re.match(r"[牡牝セセン]", c)), None)
        row_txt = " ".join(cells)
        entries.append({
            "umaban": umaban,
            "name": name or f"{umaban}番",
            "sex_age": sex,
            "umacd": um.group(1),
            "row": row_txt,
        })
    return entries


# ---------------------------------------------------------------------------
# DB成績 → RunRecord(過去走・新しい順)
# ---------------------------------------------------------------------------

def parse_history(html: str, *, limit: int = 12) -> list[RunRecord]:
    """/db/uma/{umacd}/seiseki の成績テーブルを RunRecord 列に変換。"""
    tbl = None
    for m in re.finditer(r"<table[^>]*>.*?</table>", html, re.S):
        if "タイム" in m.group(0) and ("通過" in m.group(0) or "距離" in m.group(0)):
            tbl = m.group(0)
            break
    if tbl is None:
        return []
    runs: list[RunRecord] = []
    for r in re.findall(r"<tr.*?</tr>", tbl, re.S):
        c = _cells(r)
        if len(c) < 17:
            continue
        # 年月日 競馬場 馬場 クラス レース 頭数 ゲート 人気 着順 減量 重量 騎手 距離 タイム タイム差 通過順 ペース後3F ...
        ymd = c[0]
        if not re.match(r"20\d\d/\d\d?/\d\d?", ymd):
            continue
        dist, surf = parse_distance(c[12])
        if surf == "芝":
            continue                       # ダート指数のため芝走は除外
        t = parse_time(c[13])
        try:
            field_size = int(re.sub(r"\D", "", c[5]) or 0)
        except ValueError:
            field_size = 0
        try:
            finish = int(re.sub(r"\D", "", c[8]) or 0)
        except ValueError:
            finish = 0
        # ペース後3F 例 'H 39.0' の 39.0 が上がり3F
        m3 = re.search(r"(\d{2}\.\d)", c[16]) if len(c) > 16 else None
        last3f = float(m3.group(1)) if m3 else None
        try:
            pop = int(re.sub(r"\D", "", c[7]) or 0) or None
        except ValueError:
            pop = None
        runs.append(RunRecord(
            date=ymd.replace("/", "-"),
            place=normalize_place(c[1]),
            distance=dist or 0,
            field_size=field_size,
            finish_pos=finish or (field_size or 99),
            jockey=c[11] or None,
            popularity=pop,
            baba=normalize_baba(c[2]),
            corner_pos=[],                 # このプランでは通過順が非公開(****)
            last3f_sec=last3f,
            time_sec=t,
        ))
        if len(runs) >= limit:
            break
    return runs
