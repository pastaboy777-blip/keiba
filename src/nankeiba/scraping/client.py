"""礼儀正しいHTTPクライアント(レート制限 + ローカルキャッシュ)。

netkeiba 等の公開サイトを個人利用の範囲で取得するための薄いラッパー。
- アクセス間隔を min_interval 秒以上空ける(サーバ負荷をかけない)
- 取得済みページはローカルにキャッシュし、再取得しない
  (注意: 結果未確定のページもキャッシュされる。確定直後に検証する時は
   use_cache=False で再取得すること。PoliteClient(use_cache=False) で一括無効化可)
- robots.txt と各サイトの利用規約を尊重して使うこと

requests が必要: pip install requests
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

try:
    import requests
except ImportError:  # ローカルで未導入なら案内
    requests = None  # type: ignore


class PoliteClient:
    def __init__(
        self,
        cache_dir: str | Path = "data/cache",
        *,
        min_interval: float = 1.5,
        encoding: str | None = None,
        user_agent: str = "nankeiba-research/0.1 (personal use)",
        timeout: float = 15.0,
        use_cache: bool = True,
    ):
        if requests is None:
            raise ImportError("requests が必要です: pip install requests")
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.min_interval = min_interval
        self.encoding = encoding
        self.timeout = timeout
        self.use_cache = use_cache          # インスタンス既定。結果確定直後の検証では False 推奨
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self._last = 0.0

    def _cache_path(self, url: str) -> Path:
        key = hashlib.sha256(url.encode()).hexdigest()[:24]
        return self.cache / f"{key}.html"

    def get(self, url: str, *, use_cache: bool | None = None) -> str:
        # 明示指定があればそれを優先、無ければインスタンス既定に従う。
        # (結果未確定時に掴んだページを後で再利用しないよう、検証時は False に)
        if use_cache is None:
            use_cache = self.use_cache
        cp = self._cache_path(url)
        if use_cache and cp.exists():
            return cp.read_text(encoding="utf-8")

        # レート制限
        wait = self.min_interval - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()

        resp = self.session.get(url, timeout=self.timeout)
        # 文字コード: 明示指定 > メタ宣言/推定(新nar=UTF-8, 旧db=EUC-JP 両対応)
        if self.encoding:
            resp.encoding = self.encoding
        elif not resp.encoding or resp.encoding.lower() in ("iso-8859-1", "ascii"):
            resp.encoding = resp.apparent_encoding
        resp.raise_for_status()
        html = resp.text
        cp.write_text(html, encoding="utf-8")
        return html
