"""楽天競馬(keiba.rakuten.co.jp)の出馬表ページを取り込むパーサ。

出馬表ページ(race_card/list/RACEID/<id>)のHTMLから、レース条件と各馬の
出馬情報・前5走(着順/競馬場/距離/頭数/馬場/コーナー通過順位/上がり3F/人気)を抽出する。

netkeiba 版(scraping/parser.py)と違い、楽天は1つの出馬表ページに前5走の
馬柱まで含むため、これ1枚から脚質・末脚・出走間隔・叩きの評価に必要な
データがすべて揃う。

RACEID の構造(18桁): YYYYMMDD + 10桁。末尾2桁がレース番号(00=一覧)。
  例) 川崎 2026-06-15 = 202606152135030100、6R = ...0106 ではなく ...06
      (基準IDの末尾2桁 "00" をレース番号に置換する)

馬の永続IDは馬名で代用する(同名馬は地方では稀なため実用上問題ない)。
上がり3F「順位」はページに無いため、上がりタイム(秒)のみ保持する
(レース内順位は他馬との比較が必要で過去走単体からは出せない)。

依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

import html
import re

_PLACES = (
    "川崎|大井|船橋|浦和|門別|盛岡|水沢|金沢|笠松|名古屋|"
    "園田|姫路|高知|佐賀|帯広"
)


def _text(s: str) -> str:
    """タグを除去して空白を畳んだプレーンテキストにする。"""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def race_id(base_id: str, race_no: int) -> str:
    """一覧の基準RACEID(末尾00)をレース番号付きRACEIDに変換する。"""
    return f"{base_id[:-2]}{race_no:02d}"


def race_card_url(rid: str) -> str:
    return f"https://keiba.rakuten.co.jp/race_card/list/RACEID/{rid}"


# ---------------------------------------------------------------------------
# レース条件
# ---------------------------------------------------------------------------

def parse_meta(page: str) -> dict:
    """レース条件(日付・距離・馬場・発走時刻・レース名・場・R)を抽出する。"""
    title = re.search(r"<title>([^<]+)</title>", page).group(1)
    place = re.search(r"(%s)競馬場" % _PLACES, title)
    rno = re.search(r"(\d+)R", title)
    flat = _text(page)
    m = re.search(
        r"(\d{4})年(\d{1,2})月(\d{1,2})日.*?"
        r"([ダ芝])([\d,]+)m\s*天候：\s*(\S+)\s*[ダ芝]：\s*(\S+)\s*"
        r"発走時刻\s*(\d{1,2}:\d{2})",
        flat,
    )
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    name_m = re.search(r"<h2[^>]*>(.*?)</h2>", page, re.S)
    return {
        "place": place.group(1) if place else None,
        "race_no": int(rno.group(1)) if rno else None,
        "date": f"{y:04d}-{mo:02d}-{d:02d}",
        "surface": m.group(4),
        "distance": int(m.group(5).replace(",", "")),
        "weather": m.group(6),
        "baba": m.group(7),
        "post_time": m.group(8),
        "race_name": _text(name_m.group(1)) if name_m else None,
    }


# ---------------------------------------------------------------------------
# 出馬情報 + 前5走
# ---------------------------------------------------------------------------

def _parse_run(td: str) -> dict | None:
    """前N走の1セル(class="race place..")を1走分の辞書に変換する。"""
    fm = re.search(r'class="place">(\d+)</span>', td)
    if not fm:
        return None  # 空セル(出走数が5走未満)
    txt = _text(td)
    baba = re.search(r'class="stateInfo">([^<]+)</span>', td)
    field = re.search(r'class="numberInfo">(\d+)頭', td)
    dm = re.search(r"(%s)\s+(\d{2})\.(\d{2})\.(\d{2})" % _PLACES, txt)
    distm = re.search(r"(\d{3,4})[左右内外]*[ダ芝]", txt)
    # コーナー通過順位 "5-4-4-4"
    cm = re.search(r"(\d+(?:-\d+){1,3})", txt)
    corner = [int(x) for x in cm.group(1).split("-")] if cm else []
    # 上がり3F: "1:33.7 (1.9) 41.3 396k 5番" の "41.3"(着差カッコの直後)
    agm = re.search(r"\)\s+([\d.]+)\s+\d+k", txt)
    return {
        "finish_pos": int(fm.group(1)),
        "place": dm.group(1) if dm else None,
        "date": f"20{dm.group(2)}-{dm.group(3)}-{dm.group(4)}" if dm else None,
        "distance": int(distm.group(1)) if distm else None,
        "field_size": int(field.group(1)) if field else None,
        "baba": baba.group(1) if baba else None,
        "corner_pos": corner,
        "agari": float(agm.group(1)) if agm else None,
    }


def parse_horses(page: str) -> list[dict]:
    """出馬表本体テーブルから各馬の情報と前5走を抽出する。"""
    table = re.search(r"<table[^>]*>.*?</table>", page, re.S).group(0)
    # 各馬は3行(rowspan=3)構成。馬番セルを持つ先頭行だけを馬ブロックとして拾う。
    horses: list[dict] = []
    for b in re.split(r'(?=<tr class="box\d+")', table):
        um = re.search(r'class="number">\s*(\d+)', b)
        if not um:
            continue
        umaban = int(um.group(1))
        # 馬名: mainHorse のリンク。リンクが無い場合は td.name の2行目で代替。
        name_m = re.search(r'class="mainHorse">\s*<a[^>]*>([^<]+)</a>', b)
        if name_m:
            name = name_m.group(1).strip()
        else:
            nt = re.search(r'class="name">(.*?)</td>', b, re.S)
            parts = _text(nt.group(1)).split() if nt else []
            name = parts[1] if len(parts) > 1 else (parts[0] if parts else "?")
        # rate セルは人気馬=<span class="hot">、穴馬=<span class="dark"> で
        # オッズが内側spanに入るため、rate領域全体からタグを除いて抽出する。
        rate_m = re.search(r'class="rate">(.*?)</td>', b, re.S)
        odds = pop = None
        if rate_m:
            rt = _text(rate_m.group(1))
            om = re.search(r"([\d.]+)\s*(?:倍)?\s*（\s*(\d+)\s*人気", rt)
            if om:
                odds, pop = float(om.group(1)), int(om.group(2))
            else:  # 人気表記が無い場合は先頭の数値をオッズとして拾う
                om2 = re.search(r"([\d.]+)", rt)
                odds = float(om2.group(1)) if om2 else None
        jm = re.search(r"JOCKEYID/\d+\">([^<]+)</a>", b)
        jockey = jm.group(1).strip() if jm else None
        # 調教師: profile セルの 3着内率】の直後の行
        tm = re.search(r"】\s*<br>\s*([^<]+?)\s*<br>\s*</td>", b)
        trainer = tm.group(1).strip() if tm else None

        runs = []
        for td in re.findall(r'<td[^>]*class="race place\d+">(.*?)</td>', b, re.S):
            r = _parse_run(td)
            if r:
                runs.append(r)
        horses.append({
            "umaban": umaban, "name": name, "odds": odds, "popularity": pop,
            "jockey": jockey, "trainer": trainer, "runs": runs,
        })
    return horses


def parse_race_card(page: str) -> dict:
    """出馬表ページHTMLを {meta, horses} にまとめて返す。"""
    meta = parse_meta(page)
    meta["horses"] = parse_horses(page)
    return meta
