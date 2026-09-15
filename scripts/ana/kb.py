#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""競馬ブック（地方）から読むための土台。取得とHTMLの解釈だけを持つ。

★ここに書いてあるのは、2026-09-15に大井で実際に踏んだ穴の記録でもある。
  同じところで二度転ばないように、理由つきで残す。

穴1 馬場の略記
    馬ページの馬場欄は 良/稍/重/不 の1文字。出馬表・成績ページは 良/稍重/重/不良。
    `baba in ("重","不良")` と書くと **不良だけ落ちる**。9/15はこれで
    「フェスティヴルディ 道悪3走0勝1好走」と出した。実際は不良4走4勝4好走だった。
    → WET / HEAVY を使う。自前で文字列を並べない。

穴2 成績ページの列数が 19 と 20 で揺れる
    減量印（☆▲△★）のセルが有る日と無い日がある。位置決め打ちは壊れる。
    → seiseki() が吸収する。

穴3 日程ページから会場を拾うとき
    HTMLのタグを消しただけでは改行と空白が残り、会場名が窓から外れる。
    → 必ず \\s+ を潰してから探す。9/15はこれで「大井なし」と出た。

穴4 出走間隔
    馬ページの履歴は、当日のレースが走り終わると **その日の行が増える**。
    素直に最後の行を取ると間隔が0日になる。
    → last_run() は基準日の行を除いてから最後を取る。

穴5 レースIDの並べ替え
    rid = 年(4)+開催コード(6)+R(2)+MMDD(4)。真ん中6桁は日付順ではない。
    → 並べ替えキーは ymd()＝年+MMDD。文字列そのままの比較は禁止。

穴6 成績ページの列ずれは「枠番から先すべて」
    当日ページは19列。過去ページは『本紙』欄が1つ多い20列。ずれるのは枠番以降。
    騎手から先にだけ足すと、**馬名の欄に馬番が入る**。名前で引き当てる処理が
    すべて静かに空振りする（9/15はこれで上がり順位が全部 None になった）。

穴7 通過順位・前半3F は有料欄
    cookieが無いと `****` `*` で返る。脚質は直接測れない。
    → cookie があれば passing() が中身を返す。無ければ None を返すので、
      呼ぶ側は agari.style()（着順−上がり順位）で代用する。

cookie:
    scripts/ana/kb.conf に curl の -K 形式で置く。**絶対にコミットしない**（.gitignore済み）。
        header = "Cookie: ..."
"""
from __future__ import annotations

import os
import re
import subprocess
import time
import datetime as dt

BASE = "https://p.keibabook.co.jp"
HERE = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.join(HERE, "kb.conf")
CACHE = os.environ.get("KB_CACHE", "/tmp/kbcache")

WET = ("重", "不", "不良")              # 道悪＝重＋不良（★略記の「不」を必ず入れる）
HEAVY = ("不", "不良")                  # 不良だけ
DAMP = ("稍", "稍重")                   # 稍重

_TAG = re.compile(r"<[^>]+>")
_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_TD = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)


# ────────────────────────── 取得 ──────────────────────────

def get(path: str, name: str, force: bool = False, minsize: int = 2000) -> str:
    """BASE+path を取って中身を返す。取れなければ空文字（例外を投げない）。"""
    os.makedirs(CACHE, exist_ok=True)
    out = os.path.join(CACHE, name)
    if not force and os.path.exists(out) and os.path.getsize(out) > minsize:
        return open(out, encoding="utf-8", errors="replace").read()
    cmd = ["curl", "-s", "-L", "--max-time", "40", "--retry", "2"]
    if os.path.exists(CONF):
        cmd += ["-K", CONF]                      # cookie があれば有料欄も開く
    cmd += [BASE + path, "-o", out]
    subprocess.run(cmd, check=False)
    time.sleep(0.3)
    if not os.path.exists(out):                  # curl がファイルを作らない場合がある
        return ""
    return open(out, encoding="utf-8", errors="replace").read()


def has_cookie() -> bool:
    return os.path.exists(CONF)


# ────────────────────────── 素の解釈 ──────────────────────────

def text(html: str) -> str:
    """タグを消し、空白を1つに潰す。★潰さないと会場名の検索が外れる（穴3）。"""
    return re.sub(r"\s+", " ", _TAG.sub(" ", html))


def cells(tr: str) -> list[str]:
    return [re.sub(r"\s+", " ", _TAG.sub(" ", x)).strip() for x in _TD.findall(tr)]


def rows(html: str):
    for tr in _TR.finditer(html):
        yield cells(tr.group(1))


def masked(v: str) -> bool:
    """有料欄が伏せられている値か（'****' '*' '※'）。"""
    return not v or set(v) <= set("*※")


def fnum(v: str):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def ymd(rid: str) -> str:
    """rid の並べ替えキー。年(4)+MMDD(4)。★rid の文字列比較は日付順にならない（穴5）。"""
    return rid[:4] + rid[12:16]


# ────────────────────────── ページごと ──────────────────────────

def prefix(date: str, venue: str) -> str | None:
    """日程ページ → その日そのvenueの開催コード(10桁)。date は YYYYMMDD。"""
    h = get(f"/chihou/nittei/{date}", f"nittei_{date}.html")
    found = None
    for rid in sorted(set(re.findall(r"/chihou/(?:syutuba|seiseki)/(\d{16})", h))):
        pre = rid[:10]
        j = h.find(pre)
        if j < 0:
            continue
        if venue in text(h[max(0, j - 2600):j])[-120:]:
            found = pre
    return found


def rid_of(pre: str, r: int, date: str) -> str:
    return f"{pre}{r:02d}{date[4:]}"


def meta(html: str) -> dict:
    """出馬表・成績ページの見出しから レース条件を取る。"""
    t = text(html)
    m = re.search(r"発走 (\d+:\d+).{0,90}?(\d{3,4})m \(ダート・([^)]+)\)(?: ([^ ]+))?", t)
    ttl = re.search(r"<title>(.*?)</title>", html, re.S)
    out = dict(start=None, dist=None, course=None, baba=None,
               title=(ttl.group(1).strip() if ttl else ""))
    if m:
        out.update(start=m.group(1), dist=int(m.group(2)), course=m.group(3))
        w = m.group(4) or ""
        b = re.search(r"(良|稍重|重|不良)", w)
        out["baba"] = b.group(1) if b else None
    if not out["baba"]:
        b = re.search(r"(?:晴|曇|雨|小雨|雪)・(良|稍重|重|不良)", t)
        out["baba"] = b.group(1) if b else None
    return out


def syutuba(rid: str, force: bool = False) -> tuple[dict, list[dict]]:
    """出馬表 → (レース条件, 出走馬)。馬体重は発走直前まで空欄なので force で取り直す。"""
    h = get(f"/chihou/syutuba/{rid}", f"syu_{rid}.html", force=force)
    out = []
    for tr in _TR.finditer(h):
        c = cells(tr.group(1))
        if len(c) < 20 or not c[1].isdigit():
            continue
        m = re.search(r"/db/uma/(\w+)", tr.group(1))
        out.append(dict(waku=c[0], ub=int(c[1]), name=c[8].replace("★", "").strip(),
                        sex=c[10], jk=c[12], kin=c[13], stable=c[14],
                        w=c[16] or None, dw=c[17] or None,
                        odds=c[18] or None, nin=c[19] or None,
                        umacd=m.group(1) if m else None))
    return meta(h), out


def seiseki(rid: str, force: bool = False) -> tuple[dict, list[dict]]:
    """成績 → (レース条件, 着順どおりの行)。★列数 19/20 の揺れを吸収する（穴2）。"""
    h = get(f"/chihou/seiseki/{rid}", f"sei_{rid}.html", force=force)
    out = []
    for tr in _TR.finditer(h):
        c = cells(tr.group(1))
        if len(c) < 19 or not c[0].isdigit():
            continue
        # ★当日ページは19列。過去ページは「本紙」欄がもう1つ入って20列。
        #   ずれるのは【枠番から先すべて】。jk 以降だけに足すと 馬名が馬番になる。
        o = 0 if len(c) == 19 else 1
        m = re.search(r"/db/uma/(\w+)", tr.group(1))
        out.append(dict(chaku=int(c[0]), waku=c[2 + o], ub=c[3 + o], name=c[4 + o],
                        sex=c[5 + o], kin=c[6 + o],
                        jk=c[8 + o], time=c[9 + o], sa=c[10 + o],
                        pas=None if masked(c[11 + o]) else c[11 + o],
                        first3=fnum(c[12 + o]), agari=fnum(c[13 + o]),
                        nin=c[14 + o] or None, odds=fnum(c[15 + o]),
                        w=c[16 + o] or None, dw=c[17 + o] or None,
                        umacd=m.group(1) if m else None))
    return meta(h), out


def uma(umacd: str, force: bool = False) -> list[dict]:
    """馬ページ → 競走成績（古い順）。馬場欄は 良/稍/重/不 の1文字（★穴1）。"""
    h = get(f"/db/uma/{umacd}", f"uma_{umacd}.html", force=force)
    out = []
    for tr in _TR.finditer(h):
        c = cells(tr.group(1))
        if len(c) < 19 or not re.fullmatch(r"\d{4}/\d{2}/\d{2}", c[0]):
            continue
        out.append(dict(date=c[0], place=c[1], baba=c[2], klass=c[3], race=c[4],
                        n=c[5], gate=c[6], nin=c[7], chaku=c[8], kin=c[10],
                        jk=c[11], dist=c[12], time=c[13], sa=c[14],
                        pas=None if masked(c[15]) else c[15],
                        pace=c[16], rival=c[17], w=c[18]))
    out.sort(key=lambda x: x["date"])
    return out


def sire(umacd: str) -> str | None:
    h = get(f"/db/uma/{umacd}", f"uma_{umacd}.html")
    m = re.search(r"父\s*</t[dh]>\s*<t[dh][^>]*>(.*?)</t[dh]>", h, re.S)
    return _TAG.sub("", m.group(1)).replace("▶", "").strip() if m else None


# ────────────────────────── 履歴からの読み取り ──────────────────────────

def dist_of(s: str | None):
    m = re.search(r"(\d{3,4})", s or "")
    return int(m.group(1)) if m else None


def to_date(s: str) -> dt.date:
    y, m, d = s.split("/")
    return dt.date(int(y), int(m), int(d))


def last_run(hist: list[dict], base: dt.date):
    """基準日より前で最後の1走。★当日の行を必ず除く（穴4）。"""
    past = [h for h in hist if to_date(h["date"]) < base]
    return past[-1] if past else None


def interval(hist: list[dict], base: dt.date):
    l = last_run(hist, base)
    return (base - to_date(l["date"])).days if l else None


def record(hist: list[dict], pred) -> tuple[int, int, int]:
    """(走数, 勝, 3着内)。pred は1走を受け取る関数。"""
    s = [h for h in hist if pred(h)]
    w = sum(1 for h in s if h["chaku"] == "1")
    t = sum(1 for h in s if h["chaku"].isdigit() and int(h["chaku"]) <= 3)
    return len(s), w, t


def wet(hist, base=None):
    """道悪（重＋不良）の成績。★WET を使う。文字列を自分で並べない。"""
    f = lambda h: h["baba"] in WET and (base is None or to_date(h["date"]) < base)
    return record(hist, f)


def at(hist, place: str, dist: int, base=None):
    """同じ場・同じ距離の成績。"""
    f = lambda h: (place in (h["place"] or "") and dist_of(h["dist"]) == dist
                   and (base is None or to_date(h["date"]) < base))
    return record(hist, f)
