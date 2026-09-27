#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ここ3走の調教と厩舎の話を、1頭ぶんまとめて出す。

競馬ブック地方の3ページを使う。
  /chihou/syutuba/{rid}       → 出走馬と umacd
  /db/uma/{umacd}             → その馬の過去走（16桁レースIDつき）
  /chihou/cyokyo/1/0/{rid}    → その日の全馬の調教
  /chihou/danwa/1/{rid}       → その日の厩舎の話

出力の約束（転載しないため）:
  ・調教の時計は数値を出さない。レース内順位と脚色だけにする。
  ・厩舎の話は原文を出さず、読み取れた向き（前向き／慎重／状態の言及）だけを出す。
    原文で確認したいときは --raw をつける（手元で読む用。記事には貼らない）。

使い方:
  export KEIBABOOK_COOKIE="$(cat scratchpad/.kbcookie)"
  # 馬番で指定（当該レースの出馬表から引く）
  python3 scripts/last3_chokyo.py --race 2026071205050605 --umaban 1
  # レース全頭
  python3 scripts/last3_chokyo.py --race 2026071205050605 --all
  # 日付と場とRから引く
  python3 scripts/last3_chokyo.py --date 20260605 --place 船橋 --r 5 --all
"""
from __future__ import annotations
import argparse, json, os, re, sys, time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import keibabook_chokyo as kb  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

SLEEP = 1.8
_CACHE: dict[str, str] = {}

# 脚色の負荷（軽→強）。horse_chokyo_profile.py と揃える。
KYAKU = {"馬なり": 0, "馬也": 0, "直強め": 1, "末強め": 2, "強め": 3, "一杯": 4}
POS = ("仕上が", "上昇", "絞れ", "良化", "気配良", "上々", "文句な", "抜群", "デキ良",
       "動き良", "手応え良", "順調", "変わり身", "使える", "楽しみ", "期待")
NEG = ("変わり身無", "太", "一息", "平凡", "物足", "余裕", "案外", "イマイチ", "ズブ",
       "感じない", "重い", "並", "こんなもの", "半信半疑", "недо")


def get(path: str) -> str:
    if path in _CACHE:
        return _CACHE[path]
    for i in range(4):
        try:
            h = kb._get(path)
            _CACHE[path] = h
            time.sleep(SLEEP)
            return h
        except Exception:
            time.sleep(2 * (i + 1))
    raise RuntimeError("取得できず: " + path)


def race_id(date: str, place: str, r: int) -> str:
    for x in kb.race_ids_for_date(date):
        if x["place"] == place and x["race_no"] == r:
            return x["id"]
    raise SystemExit("%s %s %dR が見つからない" % (date, place, r))


# /db/uma/ の成績表は20列固定。空セルを潰すとずれるので位置で取る。
COL = dict(date=0, place=1, baba=2, cls=4, fs=5, gate=6, pop=7, fin=8, kin=10,
           jockey=11, dist=12, time=13, diff=14, corner=15, pace=16, top=17, wt=18)


def past_runs(umacd: str) -> list[dict]:
    """/db/uma/ から過去走を古い順で返す。"""
    s = BeautifulSoup(get("/db/uma/%s" % umacd), "html.parser")
    out = []
    for tr in s.find_all("tr"):
        rid = None
        for a in tr.find_all("a", href=True):
            m = re.search(r"/chihou/\w+/(\d{16})", a["href"])
            if m:
                rid = m.group(1)
                break
        tds = [re.sub(r"\s+", " ", td.get_text(" ", strip=True)) for td in tr.find_all("td")]
        if not rid or len(tds) < 19 or not re.match(r"^\d{4}/\d{2}/\d{2}$", tds[0]):
            continue
        r = {k: tds[i] for k, i in COL.items()}
        r["rid"] = rid
        out.append(r)
    return out


def corner4(c: str):
    """通過順 "3 3 4 4" の4角（最後の数字）。"** ** ** **" は不明。"""
    ns = re.findall(r"\d+", c or "")
    return int(ns[-1]) if ns else None


def _fin_time(oi: dict):
    """終い1F相当（時計リストの末尾）を秒で。無ければ None。"""
    t = oi.get("時計") or []
    if not t:
        return None
    try:
        return float(t[-1])
    except ValueError:
        return None


def chokyo_of(rid: str) -> list[dict]:
    return kb._parse_horses(BeautifulSoup(get("/chihou/cyokyo/1/0/%s" % rid), "html.parser"))


def danwa_of(rid: str) -> dict:
    """{馬名: 話本文} を返す。"""
    s = BeautifulSoup(get("/chihou/danwa/1/%s" % rid), "html.parser")
    out = {}
    for tr in s.find_all("tr"):
        c = [re.sub(r"\s+", " ", td.get_text(" ", strip=True)) for td in tr.find_all("td")]
        c = [x for x in c if x]
        if len(c) < 6:
            continue
        txt = c[-1]
        if "師" not in txt and "――" not in txt:
            continue
        nm = next((x for x in c if re.fullmatch(r"[ァ-ヶー]{2,}", x)), None)
        if nm:
            out[nm] = txt
    return out


def tone(txt: str) -> str:
    if not txt:
        return "―"
    p = sum(1 for w in POS if w in txt)
    n = sum(1 for w in NEG if w in txt)
    if p and not n:
        return "前向き"
    if n and not p:
        return "慎重"
    if p and n:
        return "前向き＋不安"
    return "中立"


def rank_in_race(horses: list[dict], name: str):
    """最終追いの終い時計で、レース内順位を返す (順位, 母数)。"""
    vals = []
    for h in horses:
        oi = (h.get("追切") or [])
        if not oi:
            continue
        v = _fin_time(oi[-1])
        if v is not None:
            vals.append((v, h["馬名"]))
    vals.sort()
    for i, (_, nm) in enumerate(vals, 1):
        if nm == name:
            return i, len(vals)
    return None, len(vals)


def report(name: str, umacd: str, n_back: int, raw: bool):
    runs = past_runs(umacd)
    if not runs:
        print("  過去走が取れない")
        return
    tgt = runs[-n_back:] if len(runs) >= n_back else runs
    print("\n■ %s  （直近%d走）" % (name, len(tgt)))
    for r in reversed(tgt):
        hs = chokyo_of(r["rid"])
        me = next((h for h in hs if h["馬名"] == name), None)
        dw = danwa_of(r["rid"]).get(name, "")
        c4 = corner4(r["corner"])
        print("  %s %s %s %s %s  %s着/%s頭 %s番人気 ／ 4角%s ／ %skg ／ %s" % (
            r["date"], r["place"], r["dist"], r["baba"], r["cls"],
            r["fin"] or "?", r["fs"] or "?", r["pop"] or "?",
            "%d番手" % c4 if c4 else "不明", r["wt"] or "?", r["pace"] or "?"))
        if not me or not me.get("追切"):
            print("    調教  ─（この日は取れない）")
        else:
            oi = me["追切"]
            pos, tot = rank_in_race(hs, name)
            last = oi[-1]
            ld = KYAKU.get(last.get("脚色", ""), None)
            print("    調教  本数%d本 ／ 最終追い %s（負荷%s） ／ 終い %s"
                  % (len(oi), last.get("脚色") or "?",
                     "%d/4" % ld if ld is not None else "?",
                     "%d位/%d頭" % (pos, tot) if pos else "順位不明"))
            print("           コース %s・馬場 %s ／ 短評の向き %s ／ 総評の向き %s"
                  % (last.get("コース") or "?", last.get("馬場") or "?",
                     tone(last.get("短評", "")), tone(me.get("総評", ""))))
        print("    厩舎の話  %s" % (tone(dw) if dw else "─（なし）"))
        if raw and dw:
            print("      原文: %s" % dw)
        if raw and me:
            print("      短評: %s ／ 総評: %s"
                  % (" / ".join((o.get("短評") or "") for o in me["追切"]), me.get("総評") or ""))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--race", help="競馬ブックの16桁レースID")
    ap.add_argument("--date"); ap.add_argument("--place"); ap.add_argument("--r", type=int)
    ap.add_argument("--umaban", type=int)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--back", type=int, default=3, help="何走ぶん（既定3）")
    ap.add_argument("--raw", action="store_true", help="原文も出す（手元確認用。記事に貼らない）")
    a = ap.parse_args()
    if not os.environ.get("KEIBABOOK_COOKIE"):
        sys.exit("KEIBABOOK_COOKIE が未設定")
    rid = a.race or race_id(a.date, a.place, a.r)
    probe = get("/chihou/cyokyo/1/0/%s" % rid)
    if 'href="/login/login"' in probe or len(re.findall(r"umalink_click", probe)) <= 1:
        print("⚠️ Cookie が切れている。調教は先頭馬のみ、厩舎の話は3頭のみの無料プレビューになる。\n"
              "   競馬ブックに入り直して scratchpad/.kbcookie を取り直すと全頭出る。"
              "（過去走・4角・馬体重は会員でなくても出る）\n")
    fld = kb.field(rid)
    time.sleep(SLEEP)
    tgts = fld if a.all else [h for h in fld if h["umaban"] == a.umaban]
    if not tgts:
        sys.exit("対象馬が見つからない")
    print("■ レース %s ／ 対象%d頭" % (rid, len(tgts)))
    if a.raw:
        print("  ※--raw は手元確認用。競馬ブックの原文なので記事には貼らない。")
    for h in tgts:
        if not h.get("umacd"):
            print("\n■ %s  umacd が取れない" % h["name"]); continue
        report(h["name"], h["umacd"], a.back, a.raw)


if __name__ == "__main__":
    main()
