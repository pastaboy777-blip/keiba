#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""競馬ブック(地方) 調教データ取得＆仕上がりスコア。

南関(NAR)の調教タイムは楽天/公式に無い。競馬ブック地方版 p.keibabook.co.jp が
「日付/コース/馬場/5F-4F-3F-1F全体時計/脚色(一杯/強め/馬なり)/短評/総評」を持つ。
本モジュールで取得→構造化→v2に足す「仕上がりスコア」を出す。

⚠️ 全馬の調教は有料ログインの内側。非会員は各レース"先頭馬のみ"無料プレビュー
   (/cyokyo/N/0/ は常に1頭目へ302)。全馬取得は環境変数 KEIBABOOK_COOKIE に
   ログイン済みセッションCookieを入れる（例: `export KEIBABOOK_COOKIE="PHPSESSID=...; ..."`）。

id体系(実測)：{YYYY}{開催4}{場2}{R2}{MMDD} の16桁。日付の nittei ページから確実に引く。
  例) 2026071105010710 = 川崎(05) 1R / 開催日 07/10。場コード: 川崎05・園田06・笠松03 等は
      nittei から都度判定（syutuba/cyokyo ページ表題の場名で確定）。
"""
from __future__ import annotations
import os, re, sys, time
import urllib.request
from bs4 import BeautifulSoup

BASE = "https://p.keibabook.co.jp"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")
_KYAKU_W = {"一杯": 1.0, "直強め": 0.85, "末強め": 0.75, "強め": 0.7, "馬なり": 0.4, "": 0.5}
_POS = ("仕上が", "上昇", "絞れ", "良化", "気配良", "上々", "文句な", "抜群", "デキ良")
_NEG = ("変わり身無", "太", "一息", "平凡", "物足", "余裕", "案外", "イマイチ", "ズブ")


def _get(path: str, use_cookie: bool = True) -> str:
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
    ck = os.environ.get("KEIBABOOK_COOKIE")
    if use_cookie and ck:
        req.add_header("Cookie", ck)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


_PLACES = ("浦和", "川崎", "船橋", "大井", "金沢", "佐賀", "園田", "名古屋",
           "笠松", "高知", "門別", "盛岡", "水沢")


def race_ids_for_date(yyyymmdd: str) -> list[dict]:
    """nittei ページから当日の全レース id を会場付きで返す。[{id, race_no, place}]。
    ★id[8:10] は会場でなく開催インデックス（同一コードに複数会場が混在し得る）。
      会場は日程ページの会場ブロック（祖先要素のテキスト）から判定する。"""
    html = _get(f"/chihou/nittei/{yyyymmdd}")
    s = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for a in s.find_all("a", href=re.compile(r"/chihou/syutuba/\d{16}")):
        rid = re.search(r"(\d{16})", a["href"]).group(1)
        if rid in seen:
            continue
        place = None
        for anc in a.parents:  # 最も近い「会場が1つだけ」の祖先を採用
            t = anc.get_text(" ", strip=True) if anc else ""
            found = [p for p in _PLACES if p in t]
            if len(found) == 1 and len(t) < 4000:
                place = found[0]
                break
        seen.add(rid)
        out.append({"id": rid, "race_no": int(rid[10:12]), "place": place})
    return out


def field(raceid: str) -> list[dict]:
    """syutuba ページから全出走馬 [{umaban, name, umacd}]（楽天マッピング用）。"""
    html = _get(f"/chihou/syutuba/{raceid}")
    s = BeautifulSoup(html, "html.parser")
    out = []
    for a in s.find_all(class_="umalink_click"):
        tr = a.find_parent("tr")
        umaban = None
        if tr and tr.find(class_="umaban"):
            m = re.search(r"\d+", tr.find(class_="umaban").get_text())
            umaban = int(m.group()) if m else None
        out.append({"umaban": umaban, "name": a.get_text(strip=True),
                    "umacd": a.get("umacd")})
    return out


def _sire_name(cell_text: str) -> str:
    """血統セル "アイルハヴアナザーUSA I'll Have Another 栗毛 2009 …" から先頭の種牡馬名を抽出。"""
    m = re.match(r'\s*([ァ-ヶ・ーＡ-ＺA-Za-z’\'\.\s]+?)(?:USA|GB|IRE|FR|GER|JPN|AUS|CAN|[A-Z]{2,3}\b|\s{2,}|[栗鹿青芦黒白]毛|\d{4})',
                 cell_text)
    if m:
        nm = re.match(r'([ァ-ヶ・ー]+)', m.group(1).strip())
        if nm:
            return nm.group(1)
    nm = re.match(r'\s*([ァ-ヶ・ー]+)', cell_text)
    return nm.group(1) if nm else cell_text.strip()[:12]


def sires(raceid: str) -> dict:
    """kettouページから {馬番: 父名} を返す（確実に取れる父のみ）。
    class="kettou" セルは先頭N個(=出走頭数)が父を umaban順で列挙(後半N個は同一の重複)。
    ★母父はkettouクラスに無く(=父の2回列挙のみ)、per-horse血統ツリーの無印セルにある。
      多単語名の分割と母の位置特定が絡み堅牢抽出が困難＝TODO(母父パイプは要ground-truth検証の別実装)。"""
    horses = field(raceid)                      # umaban順の出走馬
    n = len(horses)
    s = BeautifulSoup(_get(f"/chihou/kettou/{raceid}"), "html.parser")
    ket = [_sire_name(k.get_text(" ", strip=True)) for k in s.find_all(class_="kettou")]
    out = {}
    if n and len(ket) >= n:
        for i, h in enumerate(horses):
            if h["umaban"]:
                out[h["umaban"]] = ket[i]
    return out


def _parse_workouts(soup: BeautifulSoup) -> list[dict]:
    """cyokyo ページの調教明細(16列固定)を [{日付?,コース,馬場,時計[],脚色,短評}] で返す。"""
    runs = []
    for tr in soup.find_all("tr"):
        cells = [re.sub(r"\s+", " ", td.get_text(" ", strip=True)) for td in tr.find_all("td")]
        joined = " ".join(cells)
        if not any(k in joined for k in ("一杯", "馬なり", "強め")):
            continue
        # ヘッダ/集約行を除外（見出し語を含む・脚色が複数＝複数走まとめ）
        if any(w in joined for w in ("騎乗者", "回り", "位置", "動 画", "短評")):
            continue
        kyaku = next((c for c in cells if c in _KYAKU_W and c), "")
        if not kyaku:
            continue
        times = [c for c in cells if re.fullmatch(r"\d{2,3}\.\d", c)]
        if len(times) > 4:  # 単一追い切りは時計3〜4本まで。超過は集約行
            continue
        course = next((c for c in cells if ("調教場" in c or c.endswith("本") or "坂" in c)), "")
        baba = next((c for c in cells if c in ("良", "稍", "重", "不")), "")
        # 短評は脚色の次以降の非空セル
        try:
            ki = cells.index(kyaku)
            tan = next((c for c in cells[ki + 1:] if c and c not in ("良", "稍", "重", "不")), "")
        except ValueError:
            tan = ""
        runs.append({"コース": course, "馬場": baba, "時計": times, "脚色": kyaku, "短評": tan})
    return runs


def race_meta(html: str) -> dict:
    """ページ<title>から {place, date, race_no} を抽出。例: '調教 | 2026年7月10日川崎1R | …'"""
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日([^\d|]+?)(\d{1,2})R", html)
    if not m:
        return {}
    return {"date": f"{m.group(1)}{int(m.group(2)):02d}{int(m.group(3)):02d}",
            "place": m.group(4).strip(), "race_no": int(m.group(5))}


def _parse_horses(s: BeautifulSoup) -> list[dict]:
    horses: list[dict] = []
    cur: dict | None = None
    for tr in s.find_all("tr"):
        cells = [re.sub(r"\s+", " ", td.get_text(" ", strip=True)) for td in tr.find_all("td")]
        vals = [c for c in cells if c]
        # 馬ヘッダ: umabanクラス＋馬名(カナ)＋総評
        if tr.find(class_="umaban") and not tr.find("th"):
            nm = ""
            a = tr.find(class_="umalink_click")
            if a:
                nm = a.get_text(strip=True)
            else:
                nm = next((c for c in vals if re.fullmatch(r"[ァ-ヶー]{3,}", c)), "")
            if nm and len(vals) >= 3 and any(v.isdigit() for v in vals[:2]):
                nums = [v for v in vals if v.isdigit()]
                soubyou = next((c for c in vals if not c.isdigit() and c != nm and len(c) >= 3), "")
                umacd = a.get("umacd") if a else None  # 馬固有コード＝個体キー(改名しても不変)
                cur = {"馬番": int(nums[-1]) if nums else None, "馬名": nm, "umacd": umacd,
                       "総評": soubyou, "追切": []}
                horses.append(cur)
                continue
        # 調教明細
        joined = " ".join(cells)
        if cur is not None and any(k in joined for k in ("一杯", "馬なり", "強め")):
            if any(w in joined for w in ("騎乗者", "回り", "位置", "動 画", "短評")):
                continue
            kyaku = next((c for c in cells if c in _KYAKU_W and c), "")
            times = [c for c in cells if re.fullmatch(r"\d{2,3}\.\d", c)]
            if not kyaku or len(times) > 4:
                continue
            course = next((c for c in cells if ("調教場" in c or c.endswith("本") or "坂" in c)), "")
            baba = next((c for c in cells if c in ("良", "稍", "重", "不")), "")
            # 追い切り日付: "6/20(土)" 形式のセル → "MM/DD"
            oidate = ""
            for c in cells:
                md = re.match(r"^(\d{1,2})/(\d{1,2})", c)
                if md:
                    oidate = f"{int(md.group(1)):02d}/{int(md.group(2)):02d}"
                    break
            try:
                ki = cells.index(kyaku)
                tan = next((c for c in cells[ki + 1:] if c and c not in ("良", "稍", "重", "不")), "")
            except ValueError:
                tan = ""
            cur["追切"].append({"追日": oidate, "コース": course, "馬場": baba, "時計": times,
                               "脚色": kyaku, "短評": tan})
    for h in horses:
        h["仕上がり"] = shiagari_score(h)
    return horses


def cyokyo_all(raceid: str) -> list[dict]:
    """会員(Cookie)ログイン時、1ページに全馬の調教が入る。全馬を返す。
    非会員は先頭馬のみ（＝Cookie未設定/失効の検出に使える）。"""
    return _parse_horses(BeautifulSoup(_get(f"/chihou/cyokyo/1/0/{raceid}"), "html.parser"))


def chokyo_race(raceid: str) -> dict:
    """1フェッチで {race_id, meta(place/date/race_no), horses[]} を返す（コレクター用）。"""
    html = _get(f"/chihou/cyokyo/1/0/{raceid}")
    s = BeautifulSoup(html, "html.parser")
    return {"race_id": raceid, **race_meta(html), "horses": _parse_horses(s)}


def cyokyo(raceid: str, umaban: int = 1) -> dict:
    """1頭ぶんの調教。{馬名, 総評, 追切:[...]}。全馬は KEIBABOOK_COOKIE 必須。"""
    html = _get(f"/chihou/cyokyo/{umaban}/0/{raceid}")
    s = BeautifulSoup(html, "html.parser")
    name = ""
    a = s.find(class_="umalink_click")
    if a:
        name = a.get_text(strip=True)
    soubyou = ""
    for tr in s.find_all("tr"):
        if tr.find(class_="umaban") and not tr.find("th"):
            vals = [re.sub(r"\s+", " ", td.get_text(" ", strip=True)) for td in tr.find_all("td")]
            vals = [v for v in vals if v]
            if len(vals) >= 4 and vals[0].isdigit():
                soubyou = vals[3]
                break
    return {"馬名": name, "総評": soubyou, "追切": _parse_workouts(s)}


def shiagari_score(rec: dict) -> float:
    """仕上がりスコア(0〜1目安)。最終追いの脚色×終い時計×加速ラップ×本数×総評ワード。"""
    runs = rec.get("追切") or []
    if not runs:
        return 0.0
    last = runs[-1]
    kyaku = _KYAKU_W.get(last.get("脚色", ""), 0.5)
    # 終い(最後の時計=ラスト1F/3F想定)が速いほど良い。相対基準が無いので簡易正規化。
    t = [float(x) for x in last.get("時計", []) if re.fullmatch(r"\d{2,3}\.\d", x)]
    cand = [x for x in t if 35.0 <= x <= 45.0]  # 終い3F帯(1Fの11-14sを誤採用しない)
    last3f = min(cand) if cand else (min(t) if t else 40.0)
    fast = max(0.0, min(1.0, (41.0 - last3f) / 4.0))  # 37→1.0, 41→0.0 目安
    # ※加速ラップ(accel_lap)は7/20-21南関で検証→効かず(複勝lift0.59・勝ち馬も低加速)＝
    #   南関地方の追い切り時計は計測がバラバラで加速判定がnoise。統合は撤回(rule4)。
    #   accel_lap関数は残置(中央用＋データ蓄積後の再検証用)。
    n = min(len(runs), 5) / 5.0
    txt = (rec.get("総評", "") + " " + " ".join(r.get("短評", "") for r in runs))
    pos = sum(1 for w in _POS if w in txt)
    neg = sum(1 for w in _NEG if w in txt)
    word = max(-1.0, min(1.0, (pos - neg) / 2.0))
    return round(0.45 * kyaku + 0.30 * fast + 0.10 * n + 0.15 * (word + 1) / 2, 3)


def accel_lap(times) -> float:
    """加速ラップ度(0〜1)。追い切りの累積時計から"終いに向けてハロンが加速しているか"を判定。
    高中晶敏「加速ラップ調教」(競馬の天才!)＝各ハロンが段々速い・終い最速＝好調・勝負気配。
    keibabook地方の累積時計[5F,4F,3F(,1F)]から 道中1F平均 − 終い1F平均 を"加速度"として合成。"""
    t = sorted([float(x) for x in times if re.fullmatch(r"\d{2,3}\.\d", str(x))], reverse=True)
    if len(t) < 2:
        return 0.0
    last3f = next((x for x in t if 34.0 <= x <= 42.0), None)  # 終い3F帯
    if last3f is None:
        return 0.0
    span = t[0] - last3f            # 道中(先頭〜終い3F手前)の所要
    if span <= 1.0:
        return 0.0
    nf = max(1, round(span / 13.5))  # 道中のハロン数推定(1F≒13.5s)
    mid_pf = span / nf               # 道中1F平均
    fin_pf = last3f / 3.0            # 終い1F平均
    accel = mid_pf - fin_pf          # 正＝終いが道中より速い＝加速
    a = max(0.0, min(1.0, accel / 3.0))            # 3秒差で満点
    f = max(0.0, min(1.0, (12.8 - fin_pf) / 1.3))  # 終い1F 12.8→0 / 11.5→1(絶対的な速さ)
    return round(0.6 * a + 0.4 * f, 3)


def junsei_3f(l2f: float, l1f: float) -> float:
    """純正3ハロン＝ラスト2F目 + (ラスト1F × 2)。久保和功「京大式純正3ハロン」。
    上がり3Fのラスト1Fを2倍に重み付け＝道中惰性を除いた真の終い脚(小さいほど優秀)。
    ※レース馬別は楽天が上がり3F(600m)のみで L2F/L1F 個別が取れず算出不可＝
      持続巡航(§11)が馬別の終い脚を既にカバー。本関数はL2F/L1Fが取れる場面(レースの
      ハロンタイム=先頭基準、または個別ハロンを持つ調教/中央データ)で用いる。"""
    return round(l2f + l1f * 2, 2)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="競馬ブック地方 調教取得＆仕上がりスコア")
    ap.add_argument("--raceid", help="16桁 raceid（未指定なら --date から一覧）")
    ap.add_argument("--date", help="YYYYMMDD（当日の raceid 一覧を表示）")
    ap.add_argument("--umaban", type=int, default=1, help="取得する馬番（会員Cookie無しは1のみ）")
    ap.add_argument("--field", action="store_true", help="出馬表(全馬)を表示")
    args = ap.parse_args()

    if args.date and not args.raceid:
        for r in race_ids_for_date(args.date):
            print(f"  {r['id']}  場{r['jyo_code']} {r['race_no']}R")
        return
    if not args.raceid:
        ap.error("--raceid か --date が必要")
    if args.field:
        for e in field(args.raceid):
            print(f"  {e['umaban']:>2} {e['name']} (umacd={e['umacd']})")
        return
    rec = cyokyo(args.raceid, args.umaban)
    print(f"■ {rec['馬名']}  総評[{rec['総評']}]  仕上がり={shiagari_score(rec):.3f}")
    for w in rec["追切"]:
        print(f"   {w['コース']}/{w['馬場']}  時計{'-'.join(w['時計'])}  {w['脚色']}  「{w['短評']}」")
    if not os.environ.get("KEIBABOOK_COOKIE"):
        print("  ※全馬取得は KEIBABOOK_COOKIE（会員セッション）を設定してください。")


if __name__ == "__main__":
    main()
