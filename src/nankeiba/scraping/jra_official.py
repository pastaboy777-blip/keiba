"""JRA公式(www.jra.go.jp)の過去レース結果ページをパースする。

netkeiba(db.netkeiba.com)と同じ dataset 形式(JSONL 1行=1レース)を返すので、
data/jra/races.jsonl にそのまま足せる。race_id も netkeiba と同じ12桁
(年4 + 場2 + 回2 + 日2 + R2)、horse_id も netkeiba と同じ10桁(JRA の馬リンクから取る)。

ページは POST(cname=...)で開き、Shift_JIS。リンクはすべて「cname + チェックサム」
の形でページ内に書かれているので、月 → 開催日 → レース の順にたどる:
  月の一覧   pw01skl10YYYYMM/XX          (チェックサムは過去レース結果検索ページの objParam)
  開催日     pw01srl10…/XX               (月の一覧ページ内のリンク)
  レース     pw01sde10<場><年><回><日><R><YYYYMMDD>/XX  (開催日ページ内のリンク)

依存ライブラリなし(正規表現のみ)。
"""

from __future__ import annotations

import re
from html import unescape

PAY_CLASSES = {"win": "win", "place": "place", "wakuren": "bracket", "umaren": "quinella",
               "wide": "wide", "umatan": "exacta", "trio": "trio", "tierce": "trifecta"}
PLACE_CODES = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
               "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"}


def _txt(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _secs(s: str) -> float | None:
    m = re.match(r"(?:(\d+):)?(\d+)\.(\d)", s or "")
    return int(m.group(1) or 0) * 60 + int(m.group(2)) + int(m.group(3)) / 10 if m else None


def _int(s):
    try:
        return int(re.sub(r"[^\d]", "", s))
    except (TypeError, ValueError):
        return None


def links(html: str, prefix: str) -> list[str]:
    """ページ内の doAction(…, 'prefix…/XX') と ?CNAME=prefix…/XX の cname を重複なく返す。"""
    pat = r"(%s[0-9]+/[0-9A-F]{2})" % prefix
    return sorted(set(re.findall(r"'" + pat + "'", html)) | set(re.findall(r"CNAME=" + pat, html)))


def month_checksums(html: str) -> dict[str, str]:
    """過去レース結果検索ページの objParam → {"YYMM": "XX"}"""
    return dict(re.findall(r'objParam\["(\d{4})"\]="([0-9A-F]{2})"', html))


def race_id_of(cname: str) -> str | None:
    """pw01sde10 05 2026 05 02 11 20261108/00 → 202605050211"""
    m = re.match(r"pw01sde10(\d{2})(\d{4})(\d{2})(\d{2})(\d{2})(\d{8})/", cname)
    if not m:
        return None
    jyo, year, kai, nichi, r, _ = m.groups()
    return f"{year}{jyo}{kai}{nichi}{r}"


def parse_race(html: str, race_id: str) -> dict | None:
    """結果ページ → dataset 形式の dict。着順表が無ければ None。"""
    tb = re.search(r"<table[^>]*>(.*?)</table>", html, re.S)
    if not tb:
        return None
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tb.group(1), re.S)[1:]:
        cells = dict((c, v) for c, v in re.findall(r'<td class="([a-z_]+)"[^>]*>(.*?)</td>', tr, re.S))
        fin = _int(_txt(cells.get("place", "")))
        if fin is None:
            continue  # 取消・除外・中止
        hid = re.search(r"pw01dud\d{2}(\d{10})/", tr)
        corner = [int(x) for x in re.findall(r"\d+", _txt(cells.get("corner", "")))]
        wt = re.match(r"(\d+)\(([+\-]?\d+)\)", _txt(cells.get("h_weight", "")).replace(" ", ""))
        rows.append({
            "finish_pos": fin, "waku": _int(_txt(cells.get("waku", ""))) or None,
            "umaban": _int(_txt(cells.get("num", ""))),
            "horse_id": hid.group(1) if hid else _txt(cells.get("horse", "")),
            "horse_name": _txt(cells.get("horse", "")),
            "sex_age": _txt(cells.get("age", "")), "kinryo": float(_txt(cells.get("weight", "0")) or 0),
            "jockey": _txt(cells.get("jockey", "")).replace(" ", "") or None,
            "trainer": _txt(cells.get("trainer", "")).replace(" ", "") or None,
            "time": _secs(_txt(cells.get("time", ""))), "margin": _txt(cells.get("margin", "")),
            "corner_pos": corner, "agari": _float(_txt(cells.get("f_time", ""))),
            "popularity": _int(_txt(cells.get("pop", ""))),
            "weight": int(wt.group(1)) if wt else None, "weight_diff": int(wt.group(2)) if wt else None,
            "win_odds": None,
        })
    if not rows:
        return None
    have = sorted((r for r in rows if r["agari"]), key=lambda r: r["agari"])
    for i, r in enumerate(have):
        r["agari_rank"] = i + 1

    body = _txt(html)
    dist = re.search(r"コース：\s*([\d,]+)\s*メートル\s*（(芝|ダート|障害)", body)
    baba = re.search(r"(芝|ダート)\s*(良|稍重|重|不良)", body)
    date = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", body)
    name = re.search(r'<span class="race_name">(.*?)</span>', html, re.S)
    lap = re.search(r"ハロンタイム.*?<td[^>]*>(.*?)</td>", html, re.S)
    corners = {}
    for k in "1234":
        m = re.search(r"%sコーナー\s*</th>\s*<td[^>]*>(.*?)</td>" % k, html, re.S)
        if m:
            corners[k] = _txt(m.group(1)).replace(" ", "")
    payouts: dict[str, dict[str, int]] = {}
    for cls, key in PAY_CLASSES.items():
        li = re.search(r'<li class="%s">(.*?)</li>' % cls, html, re.S)
        if li:
            payouts[key] = {_txt(n).replace(" ", ""): _int(_txt(y)) for n, y in re.findall(
                r'<div class="num">(.*?)</div>\s*<div class="yen">(.*?)</div>', li.group(1), re.S) if _int(_txt(y))}
    s = dist.group(2) if dist else None
    surface = {"芝": "芝", "ダート": "ダ", "障害": "障"}.get(s)
    return {
        "race_id": race_id,
        "date": "%s-%02d-%02d" % (date.group(1), int(date.group(2)), int(date.group(3))) if date else "",
        "place": PLACE_CODES.get(race_id[4:6], ""),
        "name": _txt(name.group(1)) if name else "",
        "distance": _int(dist.group(1)) if dist else 0,
        "surface": surface,
        "baba": baba.group(2)[0] if baba else None,
        "field_size": len(rows),
        "result": sorted(rows, key=lambda r: r["finish_pos"]),
        "lap": [float(x) for x in re.findall(r"\d+\.\d", _txt(lap.group(1)))] if lap else [],
        "corners": corners, "payouts": payouts,
        "trio_odds": {}, "trifecta_odds": {}, "source": "jra.go.jp",
    }


def _float(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None
