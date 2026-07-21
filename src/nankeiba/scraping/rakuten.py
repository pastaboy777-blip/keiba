"""楽天競馬(keiba.rakuten.co.jp)からの取得クライアント。

楽天競馬の出馬表(race_card)ページは、各馬の馬柱(近走成績)を**タイムも通過順も
インラインで**持っている(無料・ログイン不要)。したがって 1 レース = 1 ページ取得で、
スピード指数(タイム)と展開予想グリッド(通過順)の両方を作れる。

出馬表URL: https://keiba.rakuten.co.jp/race_card/list/RACEID/{race_id}
  race_id = 日付(8) + 場コード(2) + 開催コード(6) + レース番号(2)
  例) 大井 2026/07/22 11R = 202607222015060311

各馬の1過去走セルの例(スペース区切り):
  9 良 9頭 過去映像 船橋 25.08.27 フリオーソレ ４上 1800左ダ 8人 藤田凌 56.0
    1:57.2 (6.1) 40.4 526k 4番 6-6-8-9 サントノーレ
  = 着順 馬場 頭数 [映像] 競馬場 日付 レース名 クラス 距離+回り+馬場種 人気 騎手
    斤量 タイム (着差) 上り3F 馬体重 (当時)馬番 通過順 1着馬

⚠️ 会員サイトではないが、節度を持って利用すること(アクセス間隔・個人利用・
   取得データの再配布はしない)。

依存: 標準ライブラリのみ(urllib)。プロキシ・CA bundle は環境変数から拾う。
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

from ..core.interval import RunRecord

BASE = "https://keiba.rakuten.co.jp"
_UA = "Mozilla/5.0 (nankeiba; personal-use)"


# ---------------------------------------------------------------------------
# 低レベル取得
# ---------------------------------------------------------------------------

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


class KeibaRakuten:
    """楽天競馬クライアント(レート制限・キャッシュ付き。Cookie 不要)。"""

    def __init__(self, *, min_interval: float = 1.2,
                 cache_dir: str | Path | None = "data/cache/rakuten",
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
                    html = raw.decode("utf-8", "replace")
                if cache is not None:
                    cache.write_text(html, encoding="utf-8")
                return html
            except Exception as e:                       # noqa: BLE001
                last_err = e
                time.sleep(2 ** i)
        raise RuntimeError(f"取得失敗: {url}: {last_err}")

    # --- 日付・競馬場・レース番号 → race_id ---
    def find_race_id(self, date: str, place: str, race_no: int) -> str:
        """date='YYYYMMDD', place='大井', race_no=11 → race_id を解決する。"""
        day = self.get(f"/race_card/list/RACEID/{date}0000000000")
        target = place.replace("　", "").replace(" ", "")
        for m in re.finditer(
            r'href="[^"]*race_card/list/RACEID/(\d{18})"[^>]*>(.*?)</a>', day, re.S
        ):
            txt = unescape(re.sub(r"<[^>]+>", "", m.group(2))).replace("　", "").replace(" ", "").strip()
            if txt == target:
                return m.group(1)[:-2] + f"{race_no:02d}"
        raise RuntimeError(f"{date} の {place} が見つからない(開催なし?)")


# ---------------------------------------------------------------------------
# パース
# ---------------------------------------------------------------------------

def _clean(s: str) -> str:
    return unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def _time_to_sec(t: str) -> float | None:
    m = re.match(r"(\d+):(\d\d)\.(\d)$", t)
    return round(int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 10, 1) if m else None


# 1過去走セルのパターン
_RUN_RE = re.compile(
    r"^(\d+)\s+(良|稍|重|不)\s+(\d+)頭"          # 着順 馬場 頭数
    r".*?\s(\S+?)\s+(\d\d)\.(\d\d)\.(\d\d)\s+"    # 競馬場 日付(YY.MM.DD)
    r".*?(\d{3,4})([左右内外]*)([芝ダ])\s+"       # 距離 回り 馬場種
    r"(\d+)人\s+(\S+?)\s+([\d.]+)\s+"             # 人気 騎手 斤量
    r"(\d+:\d\d\.\d)\s+\(([^)]*)\)\s+"           # タイム (着差)
    r"([\d.]+)\s+\d+k\s+"                         # 上り3F 馬体重
    r"(\d+)番\s+([\d\-]+)"                        # (当時)馬番 通過順
)


def _parse_run(cell: str) -> RunRecord | None:
    """1過去走セル文字列を RunRecord に。芝は None(ダート指数のため除外)。"""
    m = _RUN_RE.match(cell.strip())
    if not m:
        return None
    (fin, baba, fld, place, yy, mm, dd, dist, _turn, surf,
     _pop, jockey, _wt, tm, _marg, ag, _umb, corner) = m.groups()
    if surf == "芝":
        return None
    corner_pos = [int(x) for x in corner.split("-") if x.isdigit()]
    return RunRecord(
        date=f"20{yy}-{mm}-{dd}",
        place=place,
        distance=int(dist),
        field_size=int(fld),
        finish_pos=int(fin),
        jockey=jockey or None,
        baba=baba,
        corner_pos=corner_pos,
        last3f_sec=float(ag) if ag else None,
        time_sec=_time_to_sec(tm),
    )


def parse_card(html: str) -> dict:
    """出馬表HTMLから header と entries(各馬の馬柱つき)を返す。

    return: {
      "header": {"place","race_no","distance","race_name","post_time"},
      "entries": [{"umaban","name","horseid","history":[RunRecord,...]}, ...],
    }
    """
    # ヘッダ(タイトル基準で誤検出を避ける)
    title = (re.search(r"<title>(.*?)</title>", html) or [None, ""])[1]
    place = (re.search(r"(\S+?)競馬場", title) or [None, None])[1]
    rno = re.search(r"(\d+)R", title) or re.search(r"(\d+)R", html)
    # 距離: レース条件の <... class="distance"> ダ1,600m(内) を最優先(カンマ許容)。
    dist_m = re.search(r'class="distance"[^>]*>\s*[ダ芝]?\s*([\d,]{3,5})m', html) \
        or re.search(r"(?<!\d)([1-9]\d{2,3})m\s*[（(]?\s*[内外右左]", html)
    header = {
        "place": place,
        "race_no": int(rno.group(1)) if rno else None,
        "distance": int(dist_m.group(1).replace(",", "")) if dist_m else None,
        "race_name": (re.search(r'class="raceTitle"[^>]*>\s*(?:<[^>]+>\s*)*([^<]{2,30})', html) or [None, None])[1],
        "post_time": (re.search(r"発走[^0-9]*([0-2]?\d:\d\d)", html) or [None, None])[1],
    }

    entries = []
    for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        row = m.group(1)
        hm = re.search(r"horse_detail/detail/HORSEID/(\d+)\"[^>]*>(.*?)</a>", row, re.S)
        if not hm:
            continue
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        cells = [_clean(t) for t in tds]
        # 馬番: 行内の最初の 1〜2桁数値セル
        umaban = None
        for c in cells:
            if re.fullmatch(r"\d{1,2}", c):
                umaban = int(c)
                break
        if umaban is None:
            continue
        runs = [r for c in cells if (r := _parse_run(c)) is not None]
        entries.append({
            "umaban": umaban,
            "name": _clean(hm.group(2)),
            "horseid": hm.group(1),
            "history": runs,
        })
    entries.sort(key=lambda e: e["umaban"])
    return {"header": header, "entries": entries}
