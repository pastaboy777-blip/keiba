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


#: 出馬表の見出し → 返すキー。見出し文字列は全角スペース等を落として突合する。
_SYU_COLS = {
    "馬番": "umaban", "馬名": "name", "性齢": "sex_age", "騎手": "jockey",
    "重量": "kinryo", "厩舎": "stable", "短評": "comment",
    "レイティング": "rating", "単勝": "odds", "人気": "popularity",
    "枠番": "waku", "馬体重(kg)": "weight",
}


def parse_entries(html: str) -> list[dict]:
    """出馬表テーブルから各馬の情報を返す。

    ⚠️ 予想家の印の列数はレース／表示設定で変わるため、**位置決め打ちは禁止**。
    必ず見出し行(<th>)から列番号を引くこと。楽天の parse_result で踏んだのと
    同じ轍で、決め打ちだと列がずれて静かに壊れる。

    返すキー: umaban, name, sex_age, umacd, jockey, kinryo, stable, comment,
              rating, odds, popularity, waku, weight, row

    **odds / popularity は前日夕方の前売り時点で既に入っている**（JRAは前日発売）。
    近走人気で市場側を代用する必要は無い ── 本物のオッズがあるならそちらを使う。
    """
    mt = re.search(r'<table[^>]*syutuba[^>]*>.*?</table>', html, re.S)
    if not mt:
        return []
    rows = re.findall(r"<tr.*?</tr>", mt.group(0), re.S)
    heads = [re.sub(r"\s+", "", _text(x))
             for x in re.findall(r"<th[^>]*>(.*?)</th>", rows[0] if rows else "", re.S)]
    col = {_SYU_COLS[h]: i for i, h in enumerate(heads) if h in _SYU_COLS}
    if "umaban" not in col or "name" not in col:
        return []

    def num(s, cast=float):
        m = re.search(r"\d+(?:\.\d+)?", (s or ""))
        return cast(m.group(0)) if m else None

    entries = []
    for r in rows[1:]:
        um = re.search(r'/db/uma/(\d+)', r)
        cells = _cells(r)
        if not um or len(cells) <= max(col.values()):
            continue
        try:
            umaban = int(re.sub(r"\D", "", cells[col["umaban"]]))
        except ValueError:
            continue
        name = cells[col["name"]].replace("★", "").replace("☆", "").strip()
        e = {"umaban": umaban, "name": name or f"{umaban}番",
             "umacd": um.group(1), "row": " ".join(cells)}
        for key in ("sex_age", "jockey", "stable", "comment"):
            if key in col:
                e[key] = cells[col[key]] or None
        for key, cast in (("kinryo", float), ("rating", float), ("odds", float),
                          ("popularity", int), ("waku", int), ("weight", int)):
            e[key] = num(cells[col[key]], cast) if key in col else None
        entries.append(e)
    return entries


# ---------------------------------------------------------------------------
# DB成績 → RunRecord(過去走・新しい順)
# ---------------------------------------------------------------------------

def parse_history(html: str, *, limit: int = 12,
                  drop_turf: bool = True) -> list[RunRecord]:
    """/db/uma/{umacd}/seiseki の成績テーブルを RunRecord 列に変換。

    drop_turf=True(既定・南関向け)は芝走を除外。中央の指数では False にして
    surface('芝'/'ダ')を保持する。"""
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
        if drop_turf and surf == "芝":
            continue                       # ダート指数のため芝走は除外(南関)
        t = parse_time(c[13])
        try:
            field_size = int(re.sub(r"\D", "", c[5]) or 0)
        except ValueError:
            field_size = 0
        try:
            finish = int(re.sub(r"\D", "", c[8]) or 0)
        except ValueError:
            finish = 0
        # ペース後3F 例 'H 39.0' → ペース記号 H と 上がり3F 39.0
        m3 = re.search(r"(\d{2}\.\d)", c[16]) if len(c) > 16 else None
        last3f = float(m3.group(1)) if m3 else None
        mp = re.match(r"\s*([HMS])", c[16]) if len(c) > 16 else None
        pace_mark = mp.group(1) if mp else None
        # タイム差(c[14])。勝ち馬は 2着との差が入るので 0.0 に潰す。
        mm = re.match(r"-?\d+\.\d", (c[14] or "").strip())
        margin = abs(float(mm.group(0))) if mm else None
        if finish == 1:
            margin = 0.0
        try:
            pop = int(re.sub(r"\D", "", c[7]) or 0) or None
        except ValueError:
            pop = None
        # 通過順(中央は公開・'4 5'や'7 6 6'形式。南関は**でマスクされ空になる)
        corner = [int(x) for x in re.findall(r"\d+", c[15])] if len(c) > 15 else []
        runs.append(RunRecord(
            date=ymd.replace("/", "-"),
            place=normalize_place(c[1]),
            distance=dist or 0,
            field_size=field_size,
            finish_pos=finish or (field_size or 99),
            jockey=c[11] or None,
            popularity=pop,
            baba=normalize_baba(c[2]),
            corner_pos=corner,
            last3f_sec=last3f,
            time_sec=t,
            surface=surf,
            race_name=(c[4] or None),
            race_class=(c[3] or c[4] or None),
            margin_sec=margin,
            pace_mark=pace_mark,
        ))
        if len(runs) >= limit:
            break
    return runs


# ---------------------------------------------------------------------------
# 中央(JRA)対応: 開催検索・結果取得(/cyuou/)
# ---------------------------------------------------------------------------

_JRA_PLACES = ["札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"]


def _meetings_cyuou(html: str) -> dict[str, str]:
    """中央 nittei から {競馬場: 開催prefix(10桁)} を作る。

    競馬場名の出現位置と syutuba リンク位置を突き合わせ、各リンクを最寄りの
    (直前の)場名に割り当て、場ごとに最頻の開催prefixを採る。
    """
    import bisect
    from collections import Counter
    names = [(m.start(), m.group(1))
             for m in re.finditer("(" + "|".join(_JRA_PLACES) + ")", html)]
    npos = [p for p, _ in names]
    links = [(m.start(), m.group(1))
             for m in re.finditer(r"/cyuou/syutuba/(\d{12})", html)]
    buckets: dict[str, Counter] = {}
    for lp, rid in links:
        i = bisect.bisect_left(npos, lp) - 1
        if i < 0:
            continue
        buckets.setdefault(names[i][1], Counter())[rid[:-2]] += 1
    return {pl: cnt.most_common(1)[0][0] for pl, cnt in buckets.items()}


def find_meeting_cyuou(client: KeibabookClient, date: str, place: str) -> list[str]:
    """中央の place の当該開催の race_id 12レースを返す(/cyuou/)。"""
    meetings = _meetings_cyuou(client.get(f"/cyuou/nittei/{date}"))
    if place not in meetings:
        raise RuntimeError(f"{date} の {place}(中央) が見つからない。開催: {list(meetings)}")
    prefix = meetings[place]
    return [f"{prefix}{n:02d}" for n in range(1, 13)]


#: ナビ帯の1レース分。例:
#:   <li class="otherrace_new" id="03" value="2歳新馬 <br>芝内・1400m"><a href="202602070303">3R</a>
_NAV_RACE_RE = re.compile(
    r'<li[^>]*class="[^"]*otherrace[^"]*"[^>]*value="(.*?)"[^>]*>\s*'
    r'<a[^>]*href="[^"]*?(\d{12})"[^>]*>\s*(\d{1,2})R', re.S)


def parse_meeting_races_cyuou(html: str) -> dict[str, dict]:
    """中央の任意のページのナビ帯から、**その開催12レース分**の条件を返す。

    ⚠️ レース条件をページ本文から正規表現で拾ってはいけない。ナビ帯（他レースへの
       リンク）が本文より先に現れるため、素直に検索すると **どのレースを開いても
       1Rの条件が返る**。実際 2026-08-01 新潟で12レース全部が「芝1000m」になり、
       その距離基準で指数を計算してしまった。必ず race_id で引くこと。

    return: {race_id: {"race_no","race_name","surface","course","distance"}}
            course は新潟・京都などの '内'/'外'（回り）。無ければ None。
    """
    out: dict[str, dict] = {}
    for val, rid, rno in _NAV_RACE_RE.findall(html):
        txt = unescape(re.sub(r"<[^>]+>", " ", val))
        m = re.search(r"(芝|ダート|ダ|障)([内外])?[・\s右左]{0,3}([\d０-９]{3,4})\s*[mメ]", txt)
        if not m:
            continue
        name = txt[:m.start()].strip(" 　・")
        out[rid] = {
            "race_no": int(rno),
            "race_name": name or None,
            "surface": ("ダ" if m.group(1).startswith("ダ")
                        else "障" if m.group(1) == "障" else "芝"),
            "course": m.group(2),
            "distance": int(m.group(3).translate(
                {c: c - 0xFEE0 for c in range(0xFF10, 0xFF1A)})),
        }
    return out


def parse_race_header_cyuou(html: str, race_id: str | None = None) -> dict:
    """中央 syutuba ページから距離・馬場種・レース名・クラスを返す。

    race_id を渡すとナビ帯から**そのレースの**条件を引く（推奨）。省略した場合は
    ページ本文から推定するが、ナビ帯を先に踏むため信用しないこと
    （`parse_meeting_races_cyuou` の警告を読むこと）。

    return: {"distance":int|None, "surface":'芝'/'ダ'/'障'|None, "course":'内'/'外'|None,
             "race_name":str|None, "race_no":int|None}
    """
    title = (re.search(r"<title>(.*?)</title>", html, re.S) or [None, ""])[1]
    rno = re.search(r"(\d{1,2})R", title)

    nav = parse_meeting_races_cyuou(html)
    if race_id and race_id in nav:
        d = dict(nav[race_id])
        d.setdefault("race_no", int(rno.group(1)) if rno else None)
        return d

    txt = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html)))
    # 条件は "ダ・1200m" 等(中黒/回り記号あり)。全角数字も許容し 'm' 必須で馬柱誤検出を避ける
    m = re.search(r"(芝|ダート|ダ|障)[・\s右左内外]{0,3}([\d０-９]{3,4})\s*[mメ]", txt)
    surface = None
    distance = None
    if m:
        surface = "ダ" if m.group(1).startswith("ダ") else ("障" if m.group(1) == "障" else "芝")
        distance = int(m.group(2).translate({c: c - 0xFEE0 for c in range(0xFF10, 0xFF1A)}))
    # <h2> のクラス見出し(例 ３歳以上１勝クラス)を race_name に
    heads = [unescape(re.sub(r"<[^>]+>", "", x)).strip()
             for x in re.findall(r"<h[12][^>]*>(.*?)</h[12]>", html, re.S)]
    race_name = next((h for h in heads if ("クラス" in h or "賞" in h or "ステークス" in h
                                            or "特別" in h or "勝" in h)), None)
    return {"distance": distance, "surface": surface, "course": None,
            "race_name": race_name, "race_no": int(rno.group(1)) if rno else None}


def parse_pedigree_cyuou(html: str) -> tuple[str | None, str | None]:
    """中央 馬DBトップ /db/uma/{umacd}/ から (父, 母父) を返す。

    父 = 血統欄の先頭 uma リンク(カタカナ名)、母父 = 「母父 XXX」表記。
    """
    # 父: <th>父</th> 直後の最初の uma リンク名
    sire = None
    sm = re.search(r"父\s*</th>.*?<a[^>]*>\s*([ァ-ヶー・]{2,16})\s*</a>", html, re.S)
    if sm:
        sire = sm.group(1).replace("・", "")
    txt = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html)))
    bm = re.search(r"母父\s*([ァ-ヶー・]{2,16})", txt)
    bms = bm.group(1).replace("・", "") if bm else None
    return sire, bms


def parse_result_cyuou(html: str) -> list[dict]:
    """中央の競走成績(/cyuou/seiseki)から着順表を返す(馬名ベース)。

    列がずれやすい(My印/本紙/着差の空セル)ため、着順と馬名で拾い、馬番は
    呼び出し側で出馬表の馬名→馬番で突合する。人気はオッズ直前の整数から推定。

    return: [{"finish","name","popularity"}, ...] 着順昇順。
    """
    mt = None
    for m in re.finditer(r"<table[^>]*>.*?</table>", html, re.S):
        hdr = "".join(re.findall(r"<th[^>]*>(.*?)</th>", m.group(0), re.S))
        if "着" in hdr and "タイム" in hdr and "馬名" in hdr:
            mt = m
            break
    if not mt:
        return []
    out = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", mt.group(0), re.S):
        c = [_text(x) for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)]
        if len(c) < 5 or not c[0].isdigit():
            continue
        finish = int(c[0])
        name = next((x for x in c if re.fullmatch(r"[ァ-ヶ][ァ-ヶーヴ]{1,}", x)), None)
        if not name:
            continue
        # 人気: オッズ(小数)の直前の整数
        pop = None
        for i, x in enumerate(c):
            if re.fullmatch(r"\d{1,3}\.\d", x) and i > 0 and c[i - 1].isdigit():
                v = int(c[i - 1])
                if 1 <= v <= 18:
                    pop = v
                    break
        out.append({"finish": finish, "name": name, "popularity": pop})
    out.sort(key=lambda x: x["finish"])
    return out
