#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""当日の調教を「追った日」ごとに順位付けする。

なぜ日ごとか:
  レース内で終い時計を並べても、馬によって追った日が違う。同じ船橋外でも
  日で馬場が変わる（9/19は良、9/24は稍）ので、日をまたいだ比較は歪む。
  そこで 追日 × コース(内/外) × 馬場 で束ねて、その中の順位を出す。
  母数を作るため、その日の全レースぶんの調教を集める。

取れないもの:
  過去走の調教は競馬ブックに残っていない。過去レースのページに出るのは
  日付なしの ■/◇ 行で、中身はレースが変わっても同じ固定行。だから
  「ここ3走の調教」は作れない。今走だけを見る。

列は16列固定:
  2=日付 3=コース 4=馬場 8=5F(4F) 9=半哩(3F) 10=3F(2F) 11=1F
  12=回り位置 13=脚色 14=短評
  3F列(10)は100%埋まるので順位の基準に使う。半哩(9)は94%。

出す数字の約束:
  時計そのものは出さない。順位と脚色だけ。

使い方:
  export KEIBABOOK_COOKIE="$(cat scratchpad/.kbcookie)"
  python3 scripts/chokyo_dayrank.py --date 20260928 --place 船橋 --r 1
  python3 scripts/chokyo_dayrank.py --date 20260928 --place 船橋 --all
"""
from __future__ import annotations
import argparse, os, re, sys, time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import keibabook_chokyo as kb  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

SLEEP = 1.8
TCOL = {8: "5F", 9: "半哩", 10: "3F", 11: "1F"}
RANKCOL = 10  # 3F。100%埋まる。
# 脚色の負荷（軽→強）。実データに出た値を全部入れた。
KYAKU = {"楽走": 0, "馬なり": 0, "馬也": 0, "直仕掛": 1, "直強め": 2, "末強め": 2,
         "稍強め": 2, "強め": 3, "稍一杯": 3.5, "末一杯": 3.5, "一杯": 4}
POS = ("仕上が", "上昇", "絞れ", "良化", "気配良", "上々", "文句な", "抜群", "デキ良",
       "動き良", "キビキビ", "順調", "変わり身", "伸び良", "まずまず", "楽しみ")
NEG = ("変わり身無", "太", "一息", "平凡", "物足", "余裕", "案外", "イマイチ", "ズブ",
       "手控え", "軽め", "重い", "こんなもの")
_C: dict[str, str] = {}


def get(path: str) -> str:
    if path in _C:
        return _C[path]
    for i in range(4):
        try:
            h = kb._get(path)
            _C[path] = h
            time.sleep(SLEEP)
            return h
        except Exception:
            time.sleep(2 * (i + 1))
    raise RuntimeError("取得できず: " + path)


def tone(txt: str) -> str:
    if not txt:
        return "―"
    p = sum(1 for w in POS if w in txt)
    n = sum(1 for w in NEG if w in txt)
    return ("前向き＋不安" if p and n else "前向き" if p else "慎重" if n else "中立")


def parse_race(rid: str) -> list[dict]:
    """1レースの全馬。追切は16列の行だけを読む（27列や10列の断片は捨てる）。"""
    s = BeautifulSoup(get("/chihou/cyokyo/1/0/%s" % rid), "html.parser")
    out: list[dict] = []
    cur = None
    for tr in s.find_all("tr"):
        cells = [re.sub(r"\s+", " ", td.get_text(" ", strip=True)) for td in tr.find_all("td")]
        vals = [c for c in cells if c]
        if tr.find(class_="umaban") and not tr.find("th"):
            a = tr.find(class_="umalink_click")
            nm = a.get_text(strip=True) if a else ""
            nums = [v for v in vals if v.isdigit()]
            if nm and nums:
                cur = dict(馬番=int(nums[-1]), 馬名=nm, umacd=a.get("umacd") if a else None,
                           総評=next((c for c in vals if not c.isdigit() and c != nm
                                      and len(c) >= 3), ""), 追切=[])
                out.append(cur)
            continue
        if cur is None or len(cells) != 16 or not cells[13] or cells[13] == "脚色":
            continue
        t = {i: float(cells[i]) for i in TCOL if re.fullmatch(r"\d{2,3}\.\d", cells[i])}
        if not t:
            continue
        md = re.match(r"^(\d{1,2})/(\d{1,2})", cells[2])
        cur["追切"].append(dict(
            追日=("%02d/%02d" % (int(md.group(1)), int(md.group(2)))) if md else "",
            記号="" if md else cells[2], コース=cells[3], 馬場=cells[4], t=t,
            位置=cells[12], 脚色=cells[13], 短評=cells[14]))
    return out


def collect_day(date: str, place: str):
    """その日その場の全レースを集める。{R: [horses]} と追い切りの全リスト。"""
    rids = sorted(x["id"] for x in kb.race_ids_for_date(date) if x["place"] == place)
    if not rids:
        raise SystemExit("%s %s の開催が見つからない" % (date, place))
    time.sleep(SLEEP)
    byr, allw = {}, []
    for rid in rids:
        hs = parse_race(rid)
        r = int(rid[10:12])
        byr[r] = hs
        for h in hs:
            h["R"] = r
            for w in h["追切"]:
                w["馬名"] = h["馬名"]
                w["R"] = r
                allw.append(w)
    return byr, allw


def load_bucket(kyaku: str) -> str:
    """脚色を2つに束ねる。生の順位は流した馬が下に沈むだけなので、
       追った組／流した組に分けた中の順位のほうが読める。"""
    ld = KYAKU.get(kyaku)
    return "追" if ld is not None and ld >= 2 else "流" if ld is not None else "?"


def build_ranks(allw: list[dict]) -> None:
    """追日×コース×馬場 で束ねて順位を書き込む。脚色をそろえた順位も出す。"""
    g, gb, gk = defaultdict(list), defaultdict(list), defaultdict(list)
    for w in allw:
        if not w["追日"] or RANKCOL not in w["t"]:
            continue
        k = (w["追日"], w["コース"], w["馬場"])
        g[k].append(w)
        gb[k + (load_bucket(w["脚色"]),)].append(w)
        gk[k + (w["脚色"],)].append(w)
    for tag, grp in (("", g), ("束", gb), ("脚色内", gk)):
        for ws in grp.values():
            ws.sort(key=lambda x: x["t"][RANKCOL])
            for i, w in enumerate(ws, 1):
                w[tag + "順位"], w[tag + "母数"] = i, len(ws)


def last_dated(h: dict):
    d = [w for w in h["追切"] if w["追日"]]
    return d[-1] if d else None


def show(hs: list[dict], r: int) -> None:
    print("\n■ %dR ── %d頭" % (r, len(hs)))
    for h in sorted(hs, key=lambda x: x["馬番"]):
        w = last_dated(h)
        n_d = sum(1 for x in h["追切"] if x["追日"])
        if not w:
            print("  %2d %-13s 日付のある追い切りなし（固定行だけ）／総評 %s"
                  % (h["馬番"], h["馬名"][:13], tone(h["総評"])))
            continue
        def r(tag):
            # 分母はそのまま出す。何頭の中の順位かは読む側が見て判断する。
            if not w.get(tag + "順位"):
                return "―"
            return "%d/%d" % (w[tag + "順位"], w[tag + "母数"])
        ld = KYAKU.get(w["脚色"])
        bk = load_bucket(w["脚色"])
        print("  %2d %-13s %s %s %s ／ %-5s(負荷%s) ／ %s組 %-7s ／ その日 %-7s ／ 同脚色 %-6s ／ %d本"
              % (h["馬番"], h["馬名"][:13], w["追日"], w["コース"], w["馬場"],
                 w["脚色"], ("%.1f" % ld).rstrip("0").rstrip(".") if ld is not None else "?",
                 bk, r("束"), r(""), r("脚色内"), n_d))
        print("     %-13s 短評 %s ／ 総評 %s%s"
              % ("", tone(w["短評"]), tone(h["総評"]),
                 ("／ 回り位置 %s" % w["位置"]) if w["位置"] else ""))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--r", type=int)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--pools", action="store_true", help="束ねた中身も出す")
    a = ap.parse_args()
    if not os.environ.get("KEIBABOOK_COOKIE"):
        sys.exit("KEIBABOOK_COOKIE が未設定")
    byr, allw = collect_day(a.date, a.place)
    n_h = sum(len(v) for v in byr.values())
    if n_h <= len(byr):
        sys.exit("Cookie が切れている（各レース先頭馬のみ）。scratchpad/.kbcookie を取り直す。")
    build_ranks(allw)
    dated = [w for w in allw if w["追日"]]
    print("■ %s %s ── %dR %d頭 ／ 追い切り %d本（日付あり %d本・固定行 %d本）"
          % (a.date, a.place, len(byr), n_h, len(allw), len(dated), len(allw) - len(dated)))
    if a.pools:
        g = defaultdict(int)
        for w in dated:
            g[(w["追日"], w["コース"], w["馬場"])] += 1
        print("\n【束ねた中身（追日×コース×馬場）】")
        for k, n in sorted(g.items(), key=lambda x: -x[1]):
            if n >= 3:
                print("  %s %-8s %-3s %3d本" % (k[0], k[1], k[2], n))
    for r in sorted(byr):
        if a.all or r == a.r:
            show(byr[r], r)


if __name__ == "__main__":
    main()
