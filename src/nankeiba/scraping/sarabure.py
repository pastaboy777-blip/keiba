"""サラブレモバイル（sarabure.jp）取得＋穴ぐさ／好走実績リストのパーサ。

穴ぐさ（独自視点の穴馬推奨）と、その **好走実績リスト**（＝的中した推奨の
人気・着順・単オッズ・自信グレード付き）を構造化して取り込む。用途:
  ・穴ぐさのコメントから [x.x.x.x] スプリット・クロス・角度を機械抽出（attrsplit/cross へ）。
  ・好走リストを **ラベル付きデータ** として蓄積し、どの角度・グレードが実際に走るか
    を正直に検証する（CLAUDE.md rule4：盛らずに実測）。

⚠️ 発見: 穴ぐさは推奨ボックスの class（anagusa-horse **a/b/c**）に**自信グレード**を
   持たせている。好走リストにも同じ A/B/C が末尾に付く。→ グレード別の的中率が測れる。

会員 Cookie が要る（data/.sarabure_cookie、gitignore済）。取得データの再配布はしない
＝個人分析用（収集物は data/cache 配下でgitignore）。依存: 標準ライブラリのみ。
"""

from __future__ import annotations

import gzip
import os
import re
import ssl
import time
import urllib.request
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path

BASE = "https://sarabure.jp"
_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120 Safari/537.36")
_STAT_RE = re.compile(r"\[\d+\.\d+\.\d+\.\d+\](?:（複勝率[\d.]+％）|\(複勝率[\d.]+％\))?")
# 祖先名は「カタカナ(長音ーを含む)＋ラテン」の連続。長音符ー(U+30FC)を必ず含める。
_CROSS_RE = re.compile(r"([゠-ヿA-Za-z・][゠-ヿA-Za-z・]*)の(\d×\d)")


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    for env in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        p = os.environ.get(env)
        if p and os.path.exists(p):
            ctx.load_verify_locations(p)
            return ctx
    if os.path.exists("/root/.ccr/ca-bundle.crt"):
        ctx.load_verify_locations("/root/.ccr/ca-bundle.crt")
    return ctx


def load_cookie(path: str | Path = "data/.sarabure_cookie") -> str:
    return Path(path).read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# データ構造
# ---------------------------------------------------------------------------

def _txt(html: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", html)).replace("\xa0", " ").strip()


def _stats(text: str) -> list[str]:
    return _STAT_RE.findall(text)


def _crosses(text: str) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2)) for m in _CROSS_RE.finditer(text)]


@dataclass
class Anagusa:
    place: str
    race_no: int | None
    race_name: str
    umaban: int | None
    name: str
    grade: str | None                       # 自信グレード a/b/c（section class 由来）
    comment: str
    stats: list[str] = field(default_factory=list)     # [x.x.x.x]（複勝率）群
    crosses: list[tuple[str, str]] = field(default_factory=list)  # (祖先, '5×4')


@dataclass
class Kosou:
    """好走実績（的中した穴ぐさ）。"""

    date: str
    place: str
    race_no: int | None
    race_name: str
    distance: str
    name: str
    ninki: int | None                       # 人気
    finish: int | None                      # 着順
    odds: float | None                      # 単勝オッズ
    jockey: str
    grade: str | None                       # A/B/C
    comment: str
    stats: list[str] = field(default_factory=list)
    crosses: list[tuple[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# パーサ（ネット非依存・テスト可能）
# ---------------------------------------------------------------------------

def _parse_place_line(s: str) -> tuple[str, int | None, str]:
    """'新潟 2R メイクデビュー新潟' → ('新潟', 2, 'メイクデビュー新潟')。"""
    m = re.match(r"(\S+)\s+(\d+)R\s*(.*)", s)
    if m:
        return m.group(1), int(m.group(2)), m.group(3).strip()
    return s.strip(), None, ""


def _parse_name_line(s: str) -> tuple[int | None, str]:
    """'12 ミカミッチー' → (12, 'ミカミッチー')。"""
    s = s.replace("\xa0", " ").strip()
    m = re.match(r"(\d+)\s+(.*)", s)
    if m:
        return int(m.group(1)), m.group(2).strip()
    return None, s


def parse_anagusa_list(html: str) -> list[Anagusa]:
    """穴ぐさ一覧HTML → Anagusa 群（section.anagusa-horse を1件ずつ）。"""
    out: list[Anagusa] = []
    for sm in re.finditer(
        r'<section class="anagusa-horse\s*([abc])?"[^>]*>(.*?)</section>',
        html, re.S,
    ):
        grade = sm.group(1)
        block = sm.group(2)
        pm = re.search(r'<div class="place"[^>]*>(.*?)</div>', block, re.S)
        nm = re.search(r'<div class="name"[^>]*>.*?<span>(.*?)</span>', block, re.S)
        cm = re.search(r'<div class="anagusa-box".*?<p>(.*?)</p>', block, re.S)
        if not (pm and nm):
            continue
        place, rno, rname = _parse_place_line(_txt(pm.group(1)))
        umaban, name = _parse_name_line(_txt(nm.group(1)))
        comment = _txt(cm.group(1)) if cm else ""
        out.append(Anagusa(place=place, race_no=rno, race_name=rname,
                           umaban=umaban, name=name, grade=grade, comment=comment,
                           stats=_stats(comment), crosses=_crosses(comment)))
    return out


def _to_float(s: str) -> float | None:
    try:
        return float(s)
    except ValueError:
        return None


def parse_kosou_list(html: str) -> list[Kosou]:
    """好走実績リストHTML → Kosou 群（div.re-txt-area>p を1件ずつ）。"""
    out: list[Kosou] = []
    for pm in re.finditer(r'<div class="re-txt-area">\s*<p>(.*?)</p>', html, re.S):
        # <br> 区切りで各フィールド
        parts = [_txt(x) for x in re.split(r"<br\s*/?>", pm.group(1))]
        parts = [p for p in parts if p != ""]
        if len(parts) < 6:
            continue
        date = parts[0]
        place, rno, rname = _parse_place_line(parts[1])
        distance = parts[2]
        name = parts[3]
        rm = re.search(r"(\d+)人気\s*(\d+)着.*?単オッズ([\d.]+)倍", parts[4])
        ninki = int(rm.group(1)) if rm else None
        finish = int(rm.group(2)) if rm else None
        odds = _to_float(rm.group(3)) if rm else None
        jockey = parts[5]
        comment = " ".join(parts[6:]).strip()
        grade = None
        gm = re.search(r"([A-C])\s*$", comment)
        if gm:
            grade = gm.group(1)
            comment = comment[: gm.start()].strip()
        out.append(Kosou(date=date, place=place, race_no=rno, race_name=rname,
                         distance=distance, name=name, ninki=ninki, finish=finish,
                         odds=odds, jockey=jockey, grade=grade, comment=comment,
                         stats=_stats(comment), crosses=_crosses(comment)))
    return out


# ---------------------------------------------------------------------------
# 取得クライアント
# ---------------------------------------------------------------------------

class Sarabure:
    def __init__(self, *, cookie: str | None = None,
                 cookie_path: str | Path = "data/.sarabure_cookie",
                 min_interval: float = 1.5,
                 cache_dir: str | Path | None = "data/cache/sarabure",
                 timeout: float = 30.0):
        self.cookie = cookie or load_cookie(cookie_path)
        self.min_interval = min_interval
        self.timeout = timeout
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._last = 0.0
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler(urllib.request.getproxies()),
            urllib.request.HTTPSHandler(context=_ssl_context()),
        )

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
                    "User-Agent": _UA, "Accept-Encoding": "gzip",
                    "Accept": "text/html,application/xhtml+xml",
                    "Cookie": self.cookie,
                })
                with self._opener.open(req, timeout=self.timeout) as r:
                    raw = r.read()
                    if r.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    html = raw.decode("utf-8", "replace")
                if cache is not None:
                    cache.write_text(html, encoding="utf-8")
                return html
            except Exception as e:                       # noqa: BLE001
                last_err = e
                time.sleep(2 ** i)
        raise RuntimeError(f"取得失敗: {url}: {last_err}")

    def anagusa_list(self, date: str) -> list[Anagusa]:
        """date='YYYY-MM-DD' の穴ぐさ一覧。"""
        return parse_anagusa_list(self.get(f"/anagusa/list/{date}"))

    def kosou_list(self, *, use_cache: bool = False) -> list[Kosou]:
        """好走実績リスト（最新ページ）。"""
        return parse_kosou_list(self.get("/anagusa_search/", use_cache=use_cache))
