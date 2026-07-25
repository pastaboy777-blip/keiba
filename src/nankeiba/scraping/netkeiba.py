"""netkeiba（db.netkeiba.com）5代血統表パーサ＋取得クライアント。

cross.py（クロス濃縮スコア）に流す **5代血統の祖先出現（父方/母方×代数）** を作る。
楽天は父/母父までしか取れないため、5×4 のような近いクロス検出には netkeiba の
血統頁（/horse/ped/{horse_id}/）が要る。

血統表(table.blood_table)は rowspan で代を表現する:
  5代表なら 本体32行、gen1のセルは rowspan16(2頭)、gen2=8(4頭)、gen3=4(8頭)、
  gen4=2(16頭)、gen5=1(32頭)。→ 代数 = round(log2(maxRowspan / rowspan)) + 1。
  各代のセルは HTML 文書順＝血統表の上→下順（＝父方が先、母方が後）に並ぶので、
  各代の前半＝父方 / 後半＝母方 で side を割れる（cross.occurrences_from_5gen と一致）。

db.netkeiba.com は EUC-JP。取得はレート制限・キャッシュ付き（Cookie不要）。
⚠️ 節度を持って利用（個人利用・アクセス間隔）。依存: 標準ライブラリのみ。
"""

from __future__ import annotations

import gzip
import math
import os
import re
import ssl
import time
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path

from ..core import cross

BASE = "https://db.netkeiba.com"
_UA = "Mozilla/5.0 (nankeiba; personal-use)"


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


# ---------------------------------------------------------------------------
# パーサ（ネット非依存・テスト可能）
# ---------------------------------------------------------------------------

def _cell_name(cell_html: str) -> str:
    """血統表セルのHTMLから馬名だけ抜く（<a>優先、無ければ生年・毛色を除去）。"""
    m = re.search(r"<a[^>]*>(.*?)</a>", cell_html, re.S)
    raw = m.group(1) if m else cell_html
    txt = unescape(re.sub(r"<[^>]+>", " ", raw))
    txt = txt.replace("　", " ").strip()
    # 生年（4桁）・毛色以降を切る（<a>を使えた場合は既に名前だけ）
    txt = re.split(r"\s{2,}", txt)[0]
    txt = re.sub(r"\s*\d{4}.*$", "", txt).strip()
    return txt


def parse_ped(html: str) -> dict[int, list[str]]:
    """血統頁HTML → {代: [祖先名を父方→母方順に並べたリスト]}。

    table.blood_table を優先。無ければページ内で最初に現れる rowspan 付き
    テーブルを血統表とみなす。
    """
    m = re.search(r'<table[^>]*class="[^"]*blood_table[^"]*"[^>]*>(.*?)</table>',
                  html, re.S)
    body = m.group(1) if m else html

    # (rowspan, name) を文書順で収集
    cells: list[tuple[int, str]] = []
    for cm in re.finditer(r"<td\b([^>]*)>(.*?)</td>", body, re.S):
        attrs, inner = cm.group(1), cm.group(2)
        rsm = re.search(r'rowspan\s*=\s*"?(\d+)', attrs)
        rs = int(rsm.group(1)) if rsm else 1
        name = _cell_name(inner)
        if name:
            cells.append((rs, name))
    if not cells:
        return {}

    max_rs = max(rs for rs, _ in cells)
    by_gen: dict[int, list[str]] = {}
    for rs, name in cells:
        gen = round(math.log2(max_rs / rs)) + 1 if rs > 0 else 1
        by_gen.setdefault(gen, []).append(name)
    return by_gen


def occurrences(html_or_ped) -> list[cross.Occurrence]:
    """血統頁HTML または parse_ped結果 → cross.Occurrence 列。"""
    ped = html_or_ped if isinstance(html_or_ped, dict) else parse_ped(html_or_ped)
    return cross.occurrences_from_5gen(ped)


# ---------------------------------------------------------------------------
# 取得クライアント
# ---------------------------------------------------------------------------

class Netkeiba:
    """netkeiba 取得クライアント（レート制限・キャッシュ付き・Cookie不要）。"""

    def __init__(self, *, min_interval: float = 1.5,
                 cache_dir: str | Path | None = "data/cache/netkeiba",
                 timeout: float = 25.0):
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
                })
                with self._opener.open(req, timeout=self.timeout) as r:
                    raw = r.read()
                    if r.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                # db.netkeiba は EUC-JP。meta から拾えれば従う。
                enc = "euc-jp"
                cm = re.search(rb'charset=["\']?([\w-]+)', raw[:2048], re.I)
                if cm:
                    enc = cm.group(1).decode("ascii", "replace").lower()
                    if enc in ("shift_jis", "shift-jis", "sjis"):
                        enc = "cp932"
                html = raw.decode(enc, "replace")
                if cache is not None:
                    cache.write_text(html, encoding="utf-8")
                return html
            except Exception as e:                       # noqa: BLE001
                last_err = e
                time.sleep(2 ** i)
        raise RuntimeError(f"取得失敗: {url}: {last_err}")

    def ped_html(self, horse_id: str) -> str:
        """5代血統頁のHTMLを取得。"""
        return self.get(f"/horse/ped/{horse_id}/")

    def pedigree(self, horse_id: str) -> dict[int, list[str]]:
        """horse_id → {代: [祖先名]}。"""
        return parse_ped(self.ped_html(horse_id))

    def occurrences(self, horse_id: str) -> list[cross.Occurrence]:
        return occurrences(self.pedigree(horse_id))

    def cross_score(self, horse_id: str, *, surface: str | None = None,
                    baba: str | None = None, distance: int | None = None
                    ) -> cross.CrossScore:
        """horse_id と今日の条件 → クロス濃縮スコア（cross.score）。"""
        return cross.score(self.occurrences(horse_id), surface=surface,
                           baba=baba, distance=distance)

    def search_horse_id(self, name: str) -> str | None:
        """馬名 → horse_id（best-effort。netkeibaの馬名検索を叩く）。"""
        html = self.get(f"/?pid=horse_list&word={urllib.parse.quote(name)}",
                        use_cache=False)
        m = re.search(r"/horse/(\d+)/", html)
        return m.group(1) if m else None
