"""db.netkeiba.com のレース結果ページ(/race/<race_id>/)をパースする。中央・地方共通。

1ページに「着順表・通過順・上がり・単勝/人気・ラップ・コーナー通過順・払戻」が揃うので、
展開の検証(予想した隊列/ペース vs 実際のラップ)と学習の両方に使える。

出力は core/dataset.py の JSONL 形式の上位互換(余分なキーは無視される):
    race_id, date, place, distance, surface, baba, field_size, name,
    result[{finish_pos, waku, umaban, horse_id, horse_name, jockey, trainer,
            time, agari, agari_rank, corner_pos, win_odds, popularity, weight}],
    lap[...], corners{"1": "...", ...}, payouts{"trio": {"3-6-12": 4520}, ...},
    trio_odds{}, trifecta_odds{}   # 過去レースの全通りオッズは取れないので空

依存ライブラリなし(正規表現のみ)。
"""

from __future__ import annotations

import re
from html import unescape

from .race_id import place_of


def _txt(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _secs(s: str) -> float | None:
    m = re.match(r"(?:(\d+):)?(\d+)\.(\d)", s or "")
    if not m:
        return None
    return int(m.group(1) or 0) * 60 + int(m.group(2)) + int(m.group(3)) / 10


def _int(s: str) -> int | None:
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def _float(s: str) -> float | None:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


_PAY_KEYS = {"単勝": "win", "複勝": "place", "枠連": "bracket", "馬連": "quinella",
             "ワイド": "wide", "馬単": "exacta", "三連複": "trio", "三連単": "trifecta"}


def parse_db_race(html: str, race_id: str) -> dict | None:
    """結果ページ → dict。着順表が無ければ None(未開催・中止など)。"""
    tab = re.search(r"<table[^>]*race_table_01.*?</table>", html, re.S)
    if not tab:
        return None
    heads = [_txt(x).replace(" ", "") for x in re.findall(r"<th[^>]*>(.*?)</th>", tab.group(0), re.S)]

    def col(*names):
        for i, h in enumerate(heads):
            if any(h.startswith(n) for n in names):
                return i
        return None

    ci = {k: col(*v) for k, v in {
        "fin": ("着順",), "waku": ("枠",), "um": ("馬番",), "name": ("馬名",),
        "jockey": ("騎手",), "time": ("タイム",), "corner": ("通過",), "agari": ("上り",),
        "odds": ("単勝",), "pop": ("人気",), "weight": ("馬体重",), "trainer": ("調教師",),
    }.items()}

    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tab.group(0), re.S)[1:]:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        g = lambda k: _txt(tds[ci[k]]) if ci.get(k) is not None and ci[k] < len(tds) else ""  # noqa: E731
        fin = _int(g("fin"))
        if fin is None:
            continue  # 取消・除外・中止
        hid = re.search(r"/horse/(\w+)", tr)
        rows.append({
            "finish_pos": fin, "waku": _int(g("waku")), "umaban": _int(g("um")),
            "horse_id": hid.group(1) if hid else g("name"), "horse_name": g("name"),
            "jockey": g("jockey") or None, "trainer": g("trainer") or None,
            "time": _secs(g("time")), "agari": _float(g("agari")),
            "corner_pos": [int(x) for x in re.findall(r"\d+", g("corner"))],
            "win_odds": _float(g("odds")), "popularity": _int(g("pop")),
            "weight": _int((re.match(r"\d+", g("weight")) or [None])[0]),
        })
    if not rows:
        return None
    have = sorted((r for r in rows if r["agari"]), key=lambda r: r["agari"])
    for i, r in enumerate(have):
        r["agari_rank"] = i + 1

    body = _txt(html[:200000])
    cond = re.search(r"(芝|ダ|障)\S{0,4}?(\d{3,4})m", body)
    baba = re.search(r"(?:芝|ダート)\s*:\s*(良|稍重|重|不良)", body)
    date = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", body)
    title = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)

    lap = re.search(r"<th[^>]*>ラップ</th>\s*<td[^>]*>(.*?)</td>", html, re.S)
    corners = {m.group(1): _txt(m.group(2)).replace(" ", "") for m in re.finditer(
        r"<th[^>]*>(\d)コーナー</th>\s*<td[^>]*>(.*?)</td>", html, re.S)}

    payouts: dict[str, dict[str, int]] = {}
    for tr in re.findall(r"<tr>\s*<th[^>]*>(.*?)</tr>", html, re.S):
        head = _txt(tr.split("</th>")[0])
        key = _PAY_KEYS.get(head)
        if not key:
            continue
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(tds) < 2:
            continue
        combos = [c.strip() for c in re.split(r"<br\s*/?>", tds[0]) if _txt(c)]
        pays = [c.strip() for c in re.split(r"<br\s*/?>", tds[1]) if _txt(c)]
        payouts[key] = {
            "-".join(re.findall(r"\d+", _txt(c))): int(_txt(p).replace(",", ""))
            for c, p in zip(combos, pays) if _txt(p).replace(",", "").isdigit()
        }

    s = cond.group(1) if cond else None
    return {
        "race_id": race_id,
        "date": "%s-%02d-%02d" % (date.group(1), int(date.group(2)), int(date.group(3))) if date else "",
        "place": place_of(race_id) or "",
        "name": _txt(title.group(1)) if title else "",
        "distance": int(cond.group(2)) if cond else 0,
        "surface": s,
        "baba": baba.group(1)[0] if baba else None,
        "field_size": len(rows),
        "result": sorted(rows, key=lambda r: r["finish_pos"]),
        "lap": [float(x) for x in re.findall(r"\d+\.\d", _txt(lap.group(1)))] if lap else [],
        "corners": corners,
        "payouts": payouts,
        "trio_odds": {}, "trifecta_odds": {},
    }


def pace_of(lap: list[float], distance: int) -> dict | None:
    """ラップ → 前後半の指標。

    front3 / last3 … 最初/最後の600mの時計(先頭区間が100m等の端数なら補間)
    diff         … 前半3F − 後半3F(負=前傾=ハイ、正=後傾=スロー)
    """
    if not lap or distance <= 0:
        return None
    first = distance - 200 * (len(lap) - 1)  # 最初の区間の距離(100 or 200)
    segs = [(first, lap[0])] + [(200, x) for x in lap[1:]]

    def take(seq, meters):
        t, m = 0.0, 0
        for d, x in seq:
            if m + d <= meters:
                t += x
                m += d
            else:
                t += x * (meters - m) / d
                return t
        return t if m >= meters else None

    f3 = take(segs, 600)
    l3 = take(list(reversed(segs)), 600)
    if f3 is None or l3 is None:
        return None
    return {"front3": round(f3, 2), "last3": round(l3, 2), "diff": round(f3 - l3, 2)}
