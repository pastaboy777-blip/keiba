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

穴2 列位置を決め打ちしない（★これが一番やられる）
    出馬表の予想家の欄（「大木尚」「善林浩」…）は **開催や場によって本数が変わる**。
    成績の本文行には、見出しに無いセルが1つ入る（重量の直後の減量印）。
    決め打ちすると、ある日は通るのに別の日だけ静かにずれる。
    9/14の大井11Rは、レース後の出馬表で1頭だけ行が崩れて馬名欄に着順が入った。
    → syutuba()/seiseki() は **見出し行から列名で引く**。増えても減っても合う。

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

穴6 名前で引き当てる処理は、ずれても例外を出さない
    馬名の欄に馬番が入っても Python は落ちない。ただ全件ヒットしなくなるだけ。
    9/15はこれで上がり順位が全頭 None になり、しばらく気づかなかった。
    → 取ったあとに **件数を必ず突き合わせる**（出馬表の頭数＝成績の頭数）。

穴7 通過順位・前半3F は【開催当日しか生値で出ない】
    有料欄だと思い込んでいたが違う。**時間が経つとマスクされる**。
    競馬ブックの結果ページは開催直後だけ通過順を生値で出し、その後 `****` になる。
    9/15の鞍を翌日02時に取りに行って全部 `****` だった。cookieの問題ではない。
    → 脚質が要るなら **開催当日に scripts/ana/capture.py で取る**。
      蓄積先は scripts/ana/tsuka_data.jsonl。隊列・ペースは taretsu.py。
      取り損ねた日は seiseki() の pas が None になるので、
      「着順 − 上がり順位」で代用する（マイナスなら前で粘った馬）。

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


def _header(html: str, must: str) -> tuple[list[str], int] | tuple[None, None]:
    """表の見出し行を探して、正規化した列名の並びを返す。

    ★列位置を決め打ちしてはいけない（穴2）。出馬表の予想家の欄（「大木尚」「善林浩」…）は
      **開催や場によって本数が変わる**。決め打ちすると、ある日は通るのに別の日だけ
      静かにずれる。見出しから引けば、増えても減っても勝手に合う。
    """
    for tr in _TR.finditer(html):
        c = [re.sub(r"\s+", "", x) for x in cells(tr.group(1))]
        if must in c:
            return c, 0
    return None, None


def _idx(head: list[str], *names) -> int | None:
    for n in names:
        if n in head:
            return head.index(n)
    return None


def syutuba(rid: str, force: bool = False) -> tuple[dict, list[dict]]:
    """出馬表 → (レース条件, 出走馬)。馬体重は発走直前まで空欄なので force で取り直す。"""
    h = get(f"/chihou/syutuba/{rid}", f"syu_{rid}.html", force=force)
    head, _ = _header(h, "馬名")
    if not head:
        return meta(h), []
    I = {k: _idx(head, *v) for k, v in dict(
        waku=("枠番",), ub=("馬番",), name=("馬名",), sex=("性齢",), jk=("騎手",),
        kin=("斤量",), stable=("厩舎",), w=("馬体重(kg)", "馬体重"), dw=("増減",),
        odds=("単勝",), nin=("人気",)).items()}
    if I["ub"] is None or I["name"] is None:
        return meta(h), []
    out = []
    for tr in _TR.finditer(h):
        c = cells(tr.group(1))
        m = re.search(r'/db/uma/(\w+)[^>]*>(?:<[^>]+>)*([^<]+)', tr.group(1))
        if not m or len(c) < len(head):
            continue
        # ★馬名リンクの文字と、名前の列が一致するかを必ず確かめる（穴2）。
        #   合わなければ1つずらして再確認する。黙って通すと1頭ぶん行が壊れる。
        real = m.group(2).replace("★", "").strip()
        # 名前の列が本当に名前か。ずれていれば1つだけ寄せて再確認する。
        off = 0
        if real and I["name"] < len(c) and real not in c[I["name"]]:
            off = next((d for d in (1, -1)
                        if 0 <= I["name"] + d < len(c) and real in c[I["name"] + d]), None)
            if off is None:
                continue
        g = lambda k: (c[I[k] + off] if I[k] is not None and 0 <= I[k] + off < len(c) else "")
        if not g("ub").isdigit():
            continue
        # ★セルが結合されている行がまれにある（騎手と斤量が1つになる等）。
        #   列数が合わないぶんは信用しないが、**行ごと落とすことはしない**。
        #   落とすと、その馬が検討そのものから消える。9/14の大井11Rで1頭消えた。
        bad = len(c) != len(head)
        out.append(dict(waku=g("waku"), ub=int(g("ub")), name=real,
                        sex=g("sex"),
                        jk=None if bad else g("jk"), kin=None if bad else g("kin"),
                        stable=None if bad else g("stable"),
                        w=None if bad else (g("w") or None),
                        dw=None if bad else (g("dw") or None),
                        odds=None if bad else (g("odds") or None),
                        nin=None if bad else (g("nin") or None),
                        partial=bad, umacd=m.group(1)))
    return meta(h), out


def seiseki(rid: str, force: bool = False) -> tuple[dict, list[dict]]:
    """成績 → (レース条件, 着順どおりの行)。

    ★成績の本文行には、見出しに無いセルが1つ入る（重量の直後の減量印）。
      見出しから引いたうえで、重量より右の列だけ +1 する。
    """
    h = get(f"/chihou/seiseki/{rid}", f"sei_{rid}.html", force=force)
    head, _ = _header(h, "馬名")
    if not head:
        return meta(h), []
    I = {k: _idx(head, *v) for k, v in dict(
        chaku=("着順",), waku=("枠番",), ub=("馬番",), name=("馬名",), sex=("性齢",),
        kin=("重量",), jk=("騎手",), time=("タイム",), sa=("着差",), pas=("通過順位",),
        first3=("前半3F",), agari=("上り3F",), nin=("単人気", "人気"),
        odds=("単勝オッズ", "単勝"), w=("馬体重",), dw=("増減",)).items()}
    if I["chaku"] is None or I["name"] is None:
        return meta(h), []
    kin = I["kin"] if I["kin"] is not None else 10**6
    out = []
    for tr in _TR.finditer(h):
        c = cells(tr.group(1))
        if len(c) != len(head) + 1 or not c[I["chaku"]].isdigit():
            continue
        def g(k):
            j = I[k]
            if j is None:
                return ""
            j += 1 if j > kin else 0
            return c[j] if j < len(c) else ""
        m = re.search(r"/db/uma/(\w+)", tr.group(1))
        out.append(dict(chaku=int(g("chaku")), waku=g("waku"), ub=g("ub"),
                        name=g("name"), sex=g("sex"), kin=g("kin"), jk=g("jk"),
                        time=g("time"), sa=g("sa"),
                        pas=None if masked(g("pas")) else g("pas"),
                        first3=fnum(g("first3")), agari=fnum(g("agari")),
                        nin=g("nin") or None, odds=fnum(g("odds")),
                        w=g("w") or None, dw=g("dw") or None,
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
