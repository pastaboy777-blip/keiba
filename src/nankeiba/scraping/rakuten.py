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

    def cache_path(self, path: str):
        """その URL パスがキャッシュされる先。cache_dir が無ければ None。"""
        if not self.cache_dir:
            return None
        key = re.sub(r"[^0-9A-Za-z]+", "_", path).strip("_")
        return self.cache_dir / f"{key}.html"

    def get(self, path: str, *, use_cache: bool = True, retries: int = 3) -> str:
        url = path if path.startswith("http") else BASE + path
        cache = self.cache_path(path)
        if cache is not None:
            # ⚠️ use_cache=False は「読まない」だけで、取り直した結果は**必ず書く**。
            #    書かないと、次に既定（use_cache=True）で呼んだとき古いものが返る。
            #    実際 2026-08-10 浦和で、5R以降がまだ確定していない時刻に取った
            #    「結果0頭」のページが残り、確定後に取り直しても
            #    use_cache=False では上書きされず、既定呼び出しが延々と
            #    「未確定」を返し続けた。
            if use_cache and cache.exists():
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


def parse_baba(html: str) -> str | None:
    """当日の馬場状態を返す('良'/'稍重'/'重'/'不良')。取れなければ None。

    ⚠️ ページ内を単に「重」で検索してはいけない。**馬体重**の「重」や、馬柱に載る
    **過去走の馬場**を誤爆する（実際その誤爆で「全レース重馬場」という誤った分析を
    一度出している）。当日の馬場はヘッダの「天候：晴 ダ：稍重」形式にしか無いので、
    タグを剥がしたうえで **天候アンカー** で拾う。
    """
    txt = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html)))
    m = re.search(r"天候[：:]\s*\S+\s*[ダ芝][：:]\s*(不良|稍重|重|良)", txt)
    return m.group(1) if m else None


def _time_to_sec(t: str) -> float | None:
    m = re.match(r"(\d+):(\d\d)\.(\d)$", t)
    return round(int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 10, 1) if m else None


# 1過去走セルのパターン
_RUN_RE = re.compile(
    r"^(\d+)\s+(良|稍|重|不)\s+(\d+)頭"          # 着順 馬場 頭数
    r".*?\s(\S+?)\s+(\d\d)\.(\d\d)\.(\d\d)\s+"    # 競馬場 日付(YY.MM.DD)
    r"(.*?)(\d{3,4})([左右内外]*)([芝ダ])\s+"     # レース名+クラス 距離 回り 馬場種
    r"(\d+)人\s+(\S+?)\s+([\d.]+)\s+"             # 人気 騎手 斤量
    r"(\d+:\d\d\.\d)\s+\(([^)]*)\)\s+"           # タイム (着差)
    r"([\d.]+)\s+(\d+)k\s+"                       # 上り3F 馬体重(kg)
    r"(\d+)番\s+([\d\-]+)"                        # (当時)馬番 通過順
)


def _parse_run(cell: str) -> RunRecord | None:
    """1過去走セル文字列を RunRecord に。芝は None(ダート指数のため除外)。"""
    m = _RUN_RE.match(cell.strip())
    if not m:
        return None
    (fin, baba, fld, place, yy, mm, dd, rname, dist, _turn, surf,
     pop, jockey, _kin, tm, _marg, ag, wt, umb, corner) = m.groups()
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
        weight=int(wt) if wt else None,
        kinryo=float(_kin) if _kin else None,
        race_name=re.sub(r"\s+", " ", (rname or "")).strip() or None,
        # ⚠️ 人気とゲート番号は正規表現で拾っていたのに **捨てていた**。
        #    「激走（人気を大きく上回る好走）」の判定に人気が要る（Mの法則の
        #    硬直＝反動を見るのに必須）。枠順ショックにはゲート番号が要る。
        popularity=int(pop) if pop else None,
        gate=int(umb) if umb else None,
    )


#: クラス表記の1トークン。細分は漢数字（Ｃ２三四）と全角数字（３歳２）の両方あり。
_CLS_TOKEN = re.compile(
    r"(?:[ＡＢＣ][１-３]|[２-４]歳|オープン|重賞)[一二三四五六七八九十０-９]*")


def _race_class(text: str) -> str | None:
    """レース名の行から南関のクラス表記を取り出す。

        '甘さいっぱい 梨の郷 蓮田賞 Ｃ１三'        → 'Ｃ１三'
        'お年玉（としだま）賞 Ｃ３ ４歳選定馬'      → 'Ｃ３'
        '一富士（いちふじ）賞 Ｂ２Ｂ３ 選定馬'      → 'Ｂ２Ｂ３'
        '２０２４幕開け賞 ３歳２'                  → '３歳２'

    ⚠️ 末尾アンカーで書くと「選定馬」「デビュー馬限定」などの後置条件で外れる
       （実測で取得率が46%まで落ちた）。**隣接するトークンを繋いで**返す。
    """
    ms = list(_CLS_TOKEN.finditer(text or ""))
    if not ms:
        return None
    best: list = []
    cur = [ms[0]]
    for a, b in zip(ms, ms[1:]):
        if b.start() <= a.end() + 1:
            cur.append(b)
        else:
            best = cur if len(cur) > len(best) else best
            cur = [b]
    best = cur if len(cur) > len(best) else best
    return text[best[0].start():best[-1].end()].replace(" ", "")


def parse_card(html: str) -> dict:
    """出馬表HTMLから header と entries(各馬の馬柱つき)を返す。

    return: {
      "header": {"place","race_no","distance","race_name","post_time"},
      "entries": [{"umaban","name","horseid","sex_age","age","jockey","kinryo",
                   "birth","odds","popularity","history":[RunRecord,...]}, ...],
    }

    ⚠️ 性齢・騎手・誕生日は**出馬表に載っている**。長らく拾っていなかったが、
       「ズブさ」を見るのに年齢が、「乗り替わり」を見るのに騎手が要る。
       オッズ・人気は**発売前は "-（-人気）"** なので None になる。前日夜に
       取ると必ず None。当日の発売後に取り直すこと。
    """
    # ヘッダ(タイトル基準で誤検出を避ける)
    title = (re.search(r"<title>(.*?)</title>", html) or [None, ""])[1]
    place = (re.search(r"(\S+?)競馬場", title) or [None, None])[1]
    rno = re.search(r"(\d+)R", title) or re.search(r"(\d+)R", html)
    # 距離: レース条件の <... class="distance"> ダ1,600m(内) を最優先(カンマ許容)。
    dist_m = re.search(r'class="distance"[^>]*>\s*[ダ芝]?\s*([\d,]{3,5})m', html) \
        or re.search(r"(?<!\d)([1-9]\d{2,3})m\s*[（(]?\s*[内外右左]", html)
    # ⚠️ **クラスは出馬表のヘッダに載っている。**長らく馬柱の race_name から
    #    逆引きしていたが、(日付,場,距離) が一意でないため別レースを掴む事故が
    #    起きていた（§31）。<h2> に「レース名＋クラス」、<ul class="horseCondition">
    #    に「サラブレッド系　一般」、<dl class="prizeMoney"> に1着賞金がある。
    #    par をクラス別に作るには、ここを読むのが唯一正しい。
    body = html[html.find("</head>"):] or html
    h2 = re.search(r"<h2[^>]*>(.*?)</h2>", body, re.S)
    h2t = _clean(h2.group(1)).replace("\u3000", " ").strip() if h2 else ""
    # 末尾のクラス表記（Ａ１ Ｂ２三 Ｃ１三四 ２歳 ３歳 オープン …）を切り出す
    #    ⚠️ **末尾に固定しないこと。**「Ｃ３ 選定馬」「３歳 川崎デビュー馬限定選定馬」
    #    のように後ろへ条件が続く形が多く、末尾アンカーだと取得率が46%に落ちる。
    #    細分は漢数字（Ｃ２三四）と全角数字（３歳２）の両方がある。
    #    「Ｂ１二Ｂ２一」のような併合クラスは**隣接する複数トークン**なので繋げる。
    mc = _race_class(h2t)
    prize = re.search(r"1着([\d,]+)円", body)
    header = {
        "place": place,
        "race_no": int(rno.group(1)) if rno else None,
        "distance": int(dist_m.group(1).replace(",", "")) if dist_m else None,
        "race_name": (re.search(r'class="raceTitle"[^>]*>\s*(?:<[^>]+>\s*)*([^<]{2,30})', html) or [None, None])[1],
        "post_time": (re.search(r"発走[^0-9]*([0-2]?\d:\d\d)", html) or [None, None])[1],
        "date": (lambda m: f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}" if m else None)(
            re.search(r"(20\d\d)年(\d{1,2})月(\d{1,2})日", body)),
        "title": re.sub(r"\s*(?:[ＡＢＣ][１-３]|[２-４]歳|オープン)[一二三四五六七八九十]*\s*$",
                        "", h2t).strip() or None,
        "race_class": mc,
        "condition": (re.search(r'class="horseCondition"[^>]*>\s*<li[^>]*>(.*?)</li>', body, re.S)
                      or [None, None])[1],
        "weather": (re.search(r"天候[：:]\s*</dt>\s*<dd[^>]*>\s*(\S+?)\s*</dd>", body) or [None, None])[1],
        "baba": (re.search(r"[ダ芝][：:]\s*</dt>\s*<dd[^>]*>\s*(不良|稍重|重|良)", body) or [None, None])[1],
        "prize1": int(prize.group(1).replace(",", "")) if prize else None,
    }
    if header["condition"]:
        header["condition"] = _clean(header["condition"]).replace("\u3000", " ")

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
        name = _clean(hm.group(2))
        sire, bms = _parse_pedigree(cells, name)
        runs = [r for c in cells if (r := _parse_run(c)) is not None]
        txt = _clean(re.sub(r"<[^>]+>", " ", row))
        sa = re.search(r"([牡牝セン]+)\s*(\d{1,2})(?!\d)", txt)
        jk = re.search(r"(\d{2}\.\d)\s+([一-龥ぁ-んァ-ヶ]{2,4})\s*（", txt)
        bd = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})生", txt)
        od = re.search(r"(\d+\.\d)\s*[（(]\s*(\d+)\s*人気", txt)
        entries.append({
            "umaban": umaban,
            "name": name,
            "horseid": hm.group(1),
            "sex_age": (sa.group(1) + sa.group(2)) if sa else None,
            "age": int(sa.group(2)) if sa else None,
            "jockey": jk.group(2) if jk else None,
            "kinryo": float(jk.group(1)) if jk else None,
            "birth": f"{bd.group(1)}-{int(bd.group(2)):02d}-{int(bd.group(3)):02d}" if bd else None,
            "odds": float(od.group(1)) if od else None,
            "popularity": int(od.group(2)) if od else None,
            "sire": sire,
            "bms": bms,
            "history": runs,
        })
    entries.sort(key=lambda e: e["umaban"])
    return {"header": header, "entries": entries}


def fetch_card(client, race_id: str) -> dict:
    """出馬表を取り、**出走馬が0頭ならキャッシュを疑って取り直す**。

    ⚠️ 発売前に取得した出馬表は枠順が未確定で、馬柱がまるごと入っていない。
    それをキャッシュしたまま当日に使うと、そのレースだけ静かに消える。
    実際 2026-07-27 川崎1R が、前日取得の 37KB 版（0頭）に当たって
    検証から丸ごと脱落していた（当日の実物は 131KB / 9頭）。
    """
    card = parse_card(client.get(f"/race_card/list/RACEID/{race_id}"))
    if not card["entries"]:
        card = parse_card(client.get(f"/race_card/list/RACEID/{race_id}",
                                     use_cache=False))
    return card


def fetch_result(client, race_id: str) -> list[dict]:
    """結果を取り、**0頭ならキャッシュを疑って取り直す**。`fetch_card` の結果版。

    ⚠️ **まだ発走していないレースの結果ページをキャッシュしてはいけない。**
       開催中に取ると、未確定のレースが「0頭」で保存される。以後は既定の
       `get()` がそれを返し続けるので、**確定後に何度取り直しても未確定のまま**
       になる。実際 2026-08-10 浦和で、4Rまで確定の時点で全12Rを取得した結果、
       5R以降が0頭で固定され、全レース確定後の分析が4レース分しか出なかった。

       取り直しても0頭のままなら**本当に未確定**なので、キャッシュを消して返す。
       残すと次回また同じことになる。
    """
    path = f"/race_performance/list/RACEID/{race_id}"
    res = parse_result(client.get(path))
    if res:
        return res
    res = parse_result(client.get(path, use_cache=False))
    if not res:
        p = client.cache_path(path)
        if p is not None:
            p.unlink(missing_ok=True)
    return res


def _parse_pedigree(cells: list[str], name: str) -> tuple[str | None, str | None]:
    """馬情報セル「父名 馬名 母名 (母父名) …」から (父, 母父) を取り出す。"""
    for c in cells:
        if name and name in c and "(" in c or (name in c and "（" in c):
            # 父 = 馬名の直前トークン
            before = c.split(name, 1)[0].strip()
            sire = before.split()[-1] if before.split() else None
            # 母父 = 名前より後で最初の括弧（人気/株/生 は除外）
            after = c.split(name, 1)[1]
            bms = None
            for mm in re.finditer(r"[（(]([^）)]+)[）)]", after):
                g = mm.group(1).strip()
                if not any(x in g for x in ("人気", "株", "生", "有")) and len(g) >= 2:
                    bms = g
                    break
            return sire, bms
    return None, None


def _res_time_to_sec(s: str) -> float | None:
    """結果表用: '1:43.4'(タイム) と '39.7'(上がり) の両形式を秒に。"""
    s = s.strip()
    m = re.match(r"(?:(\d+):)?(\d+)\.(\d)$", s)
    if not m:
        return None
    mm = int(m.group(1)) if m.group(1) else 0
    return round(mm * 60 + int(m.group(2)) + int(m.group(3)) / 10.0, 1)


#: 結果表の見出し → 返すキー
_RES_COLS = {"着順": "finish", "馬番": "umaban", "馬名": "name", "騎手": "jockey",
             "タイム": "time", "推定上がり": "agari", "調教師": "trainer",
             "人気": "popularity", "馬体重増減": "weight", "性齢": "sexage",
             "負担重量": "kinryo"}


def _weight(s: str | None) -> dict:
    """'483 +4' / '452 -3' / '計不' → {"weight": 483, "weight_diff": 4}。"""
    m = re.match(r"(\d{3})\s*([+-]\d+)?", (s or "").strip())
    if not m:
        return {"weight": None, "weight_diff": None}
    return {"weight": int(m.group(1)),
            "weight_diff": int(m.group(2)) if m.group(2) else 0}


def parse_result(html: str) -> list[dict]:
    """競走成績(race_performance)ページの着順表を返す。

    return: [{"finish","umaban","name","jockey","trainer","popularity",
              "time_sec","agari"}, ...] 着順昇順。
      time_sec … 走破タイム(秒)  agari … 推定上がり3F(秒)  ※取得不可なら None

    ⚠️ タイム列を `m:ss.s` の正規表現で**探して**はいけない。900m など60秒未満で
    決まるレースは `55.6` 形式で載るため取りこぼし、その日の馬場差の実測から
    短距離戦が丸ごと落ちる（実際 2026-07-27 川崎3R が欠測した）。
    列の位置は**見出し行**から引く。
    """
    mt = re.search(r'class="dataTable".*?</table>', html, re.S)
    if not mt:
        return []
    rows = [[_clean(x) for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)]
            for r in re.findall(r"<tr[^>]*>(.*?)</tr>", mt.group(0), re.S)]
    # 見出しが取れない断片HTML向けの既定の並び
    col: dict[str, int] = {"finish": 0, "umaban": 2, "name": 3, "jockey": 7,
                           "time": 8, "agari": 10, "trainer": 11, "popularity": 12}
    for c in rows:
        hit = {_RES_COLS[h]: i for i, x in enumerate(c)
               if (h := x.replace(" ", "").split("/")[0]) in _RES_COLS}
        if len(hit) >= 4:            # 見出し行とみなす
            col = hit
            break

    def cell(c: list[str], key: str) -> str | None:
        i = col.get(key)
        return c[i] if i is not None and i < len(c) else None

    out = []
    for c in rows:
        if len(c) < 4 or not c[0].isdigit():
            continue
        try:
            finish = int(c[0])
            umaban = int(cell(c, "umaban") or "")
        except (TypeError, ValueError):
            continue
        pop_s = cell(c, "popularity")
        if pop_s is None:                       # 見出しが取れない場合の保険
            for x in reversed(c):
                if x.isdigit() and 1 <= int(x) <= 18:
                    pop_s = x
                    break
        out.append({
            "finish": finish, "umaban": umaban, "name": cell(c, "name"),
            "jockey": cell(c, "jockey"), "trainer": cell(c, "trainer"),
            "popularity": int(pop_s) if (pop_s or "").isdigit() else None,
            "time_sec": _res_time_to_sec(cell(c, "time") or ""),
            "agari": _res_time_to_sec(cell(c, "agari") or ""),
            **_weight(cell(c, "weight")),
            "sexage": cell(c, "sexage"),
            "kinryo": float(k) if (k := (cell(c, "kinryo") or "")).replace(".", "", 1).isdigit() else None,
        })
    out.sort(key=lambda x: x["finish"])
    return out


def parse_lap(html: str) -> dict | None:
    """結果ページ本文の「ハロンタイム …」「上がり 4F..-3F..」「コーナー通過順位」を抽出。

    return: {"furlongs":[12.9,...], "agari4f":52.3, "agari3f":39.7, "corners":"..."}
      取得できなければ None。furlongs は1ハロン(200m)ごとの実測ラップ(秒)。
    """
    txt = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html)))
    furlongs: list[float] = []
    m = re.search(r"ハロンタイム\s*([\d.\-\s]+?)(?:上がり|■|コーナー|$)", txt)
    if m:
        furlongs = [float(x) for x in re.findall(r"\d+\.\d", m.group(1))]
    a = re.search(r"上がり\s*4F\s*([\d.]+)\s*-\s*3F\s*([\d.]+)", txt)
    agari4 = float(a.group(1)) if a else None
    agari3 = float(a.group(2)) if a else None
    cm = re.search(r"コーナー通過順位\s*(.+?)(?:払戻|レース|<|$)", txt)
    corners = cm.group(1).strip()[:200] if cm else None
    if not furlongs and agari3 is None:
        return None
    return {"furlongs": furlongs, "agari4f": agari4, "agari3f": agari3, "corners": corners}


def parse_payout(html: str) -> dict | None:
    """結果ページ本文から主要払戻を抽出。三連単は本命の穴指標に使う。

    return: {"trifecta":(combo,円), "trio":(..), "exacta":(..), "win":(..)} 取れたものだけ。
    """
    txt = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html)))
    out: dict = {}
    pats = {
        "trifecta": r"三連単\s*([\d\-]+)\s*([\d,]+)\s*円",
        "trio":     r"三連複\s*([\d\-]+)\s*([\d,]+)\s*円",
        "exacta":   r"馬単\s*([\d\-]+)\s*([\d,]+)\s*円",
        "win":      r"単勝\s*(\d+)\s*([\d,]+)\s*円",
    }
    for key, pat in pats.items():
        m = re.search(pat, txt)
        if m:
            out[key] = (m.group(1), int(m.group(2).replace(",", "")))
    return out or None
