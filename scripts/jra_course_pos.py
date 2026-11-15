"""コースの「勝つ位置」の表(中央)。回収率などは測らない。

    python3 scripts/jra_course_pos.py                     # models/course_pos.json を作り直す
    python3 scripts/jra_course_pos.py --show 東京 芝       # 場×芝ダの表を画面に出す

材料: data/jra/races.jsonl の平地(芝・ダ、障害を除く)。4角の通過順(corner_pos の最後)がある馬だけ数える。
区分: 4角の順位を 1〜2 / 3〜4 / 5〜7 / 8〜10 / 11〜 に分け、1着の馬・3着内の馬がどこにいたかの割合。
     あわせて「4角で前1/3(順位 ≤ 頭数/3)にいた馬の3着内率」(前残りの強さ)と、
     後ろ1/3にいた馬の3着内率。
まとめ方: 場×芝ダ×距離。鞍数が MIN_N 未満の距離は距離帯(短 ≤1400 / マ 1500〜1700 / 中 1800〜2200 / 長 2300〜)で引く。
         馬場は 良 と 渋(稍・重・不)で分けた版も持つ。

models/course_pos.json の形:
  {"buckets": [...], "min_n": 40,
   "course": {"東京|芝|1600": {"all": S, "良": S, "渋": S}, ...},      # 距離ごと(件数を問わず全部入れる)
   "band":   {"東京|芝|マ":   {...}},                                  # 距離帯
   "place":  {"東京|芝":      {...}}}                                  # 場×芝ダ
  S = {"n": 鞍数, "fs": 平均頭数, "win": [5区分の割合], "top3": [5区分の割合],
       "p_win"/"p_top3": その区分にいた馬1頭あたりの勝率・3着内率(区分の頭数の違いをならした見方),
       "front3": 前1/3の3着内率, "back3": 後ろ1/3の3着内率}
引き方は lookup(place, surface, dist, baba): 距離で MIN_N 以上あればそれ、無ければ距離帯、無ければ場×芝ダ。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

OUT = ROOT / "models" / "course_pos.json"
BUCKETS = ["1-2", "3-4", "5-7", "8-10", "11-"]
MIN_N = 40


def bucket(c4: int) -> int:
    return 0 if c4 <= 2 else 1 if c4 <= 4 else 2 if c4 <= 7 else 3 if c4 <= 10 else 4


def band(dist: int) -> str:
    return "短" if dist <= 1400 else "マ" if dist <= 1700 else "中" if dist <= 2200 else "長"


def baba_grp(b) -> str | None:
    return "良" if b == "良" else "渋" if b in ("稍", "重", "不") else None


def is_flat(d) -> bool:
    if d.get("surface") not in ("芝", "ダ"):
        return False
    s = (d.get("race_type") or "") + (d.get("name") or "")
    return "障害" not in s and "ジャンプ" not in s


def race_rows(d):
    """(4角順位, 着順, 頭数) のリスト。4角が取れていない鞍は None。"""
    xs = [(x["corner_pos"][-1], x["finish_pos"]) for x in d["result"]
          if x.get("corner_pos") and isinstance(x.get("finish_pos"), int) and x["finish_pos"] > 0]
    n = d.get("field_size") or len(d["result"])
    if len(xs) < max(5, 0.8 * len(d["result"])) or not any(f == 1 for _, f in xs):
        return None
    return xs, n


class Acc:
    def __init__(self):
        self.n = 0
        self.fs = 0
        self.win = [0] * 5
        self.top3 = [0] * 5
        self.cnt = [0] * 5
        self.f_n = self.f_h = self.b_n = self.b_h = 0

    def add(self, xs, n):
        self.n += 1
        self.fs += n
        for c4, f in xs:
            b = bucket(c4)
            self.cnt[b] += 1
            if f == 1:
                self.win[b] += 1
            if f <= 3:
                self.top3[b] += 1
            if c4 <= n / 3:
                self.f_n += 1
                self.f_h += f <= 3
            elif c4 > n * 2 / 3:
                self.b_n += 1
                self.b_h += f <= 3

    def out(self):
        sw, st3 = sum(self.win) or 1, sum(self.top3) or 1
        return {"n": self.n, "fs": round(self.fs / max(1, self.n), 1),
                "win": [round(v / sw, 3) for v in self.win], "top3": [round(v / st3, 3) for v in self.top3],
                "p_win": [round(w / c, 3) if c else None for w, c in zip(self.win, self.cnt)],
                "p_top3": [round(w / c, 3) if c else None for w, c in zip(self.top3, self.cnt)],
                "front3": round(self.f_h / max(1, self.f_n), 3), "back3": round(self.b_h / max(1, self.b_n), 3)}


def build(rows, since=None, before=None):
    acc = {"course": {}, "band": {}, "place": {}}
    seen = set()
    for d in rows:
        if d["race_id"] in seen or not is_flat(d) or not d.get("result"):
            continue
        if (since and d["date"] < since) or (before and d["date"] >= before):
            continue
        seen.add(d["race_id"])
        rr = race_rows(d)
        if not rr:
            continue
        sf, pl, dist = d["surface"], d["place"], d["distance"]
        keys = {"course": f"{pl}|{sf}|{dist}", "band": f"{pl}|{sf}|{band(dist)}", "place": f"{pl}|{sf}"}
        for lvl, k in keys.items():
            for bg in ("all", baba_grp(d.get("baba"))):
                if bg:
                    acc[lvl].setdefault(k, {}).setdefault(bg, Acc()).add(*rr)
    return {lvl: {k: {bg: a.out() for bg, a in v.items()} for k, v in sorted(m.items())} for lvl, m in acc.items()}


_M = None


def lookup(place, surface, dist, baba=None, M=None):
    """(表のキー, S)。馬場を渡すと 良/渋 の版(その版の鞍数が MIN_N 未満なら all)。"""
    global _M
    if M is None:
        if _M is None:
            _M = json.load(open(OUT))
        M = _M
    bg = baba_grp(baba) or "all"
    for lvl, k in (("course", f"{place}|{surface}|{dist}"), ("band", f"{place}|{surface}|{band(dist)}"),
                   ("place", f"{place}|{surface}")):
        e = M[lvl].get(k)
        if e and e["all"]["n"] >= MIN_N:
            s = e.get(bg) if e.get(bg) and e[bg]["n"] >= MIN_N else e["all"]
            return k, s
    return None, None


def fmt(k, s):
    pc = lambda v: f"{v * 100:4.0f}%"  # noqa: E731
    return (f"| {k} | {s['n']} | {s['fs']} | " + " | ".join(pc(v) for v in s["win"]) + " | "
            + " | ".join(pc(v) for v in s["top3"]) + f" | {pc(s['front3'])} | {pc(s['back3'])} |")


def header():
    b = " | ".join(BUCKETS)
    return (f"| コース | 鞍 | 頭数 | 1着 {b} | 3着内 {b} | 前1/3の3着内率 | 後1/3の3着内率 |\n"
            "|---|---:|---:|" + "---:|" * 12)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data" / "jra" / "races.jsonl"))
    ap.add_argument("--show", nargs=2, metavar=("場", "芝ダ"))
    ap.add_argument("--baba", choices=["all", "良", "渋"], default="all")
    ap.add_argument("--rate", action="store_true", help="割合でなく1頭あたりの勝率・3着内率を出す")
    a = ap.parse_args()
    if a.show:
        M = json.load(open(OUT))
        pl, sf = a.show
        print(header())
        for lvl in ("course", "band", "place"):
            for k, v in M[lvl].items():
                if k.startswith(f"{pl}|{sf}") and a.baba in v:
                    s = dict(v[a.baba])
                    if a.rate:
                        s["win"], s["top3"] = [x or 0 for x in s["p_win"]], [x or 0 for x in s["p_top3"]]
                    print(fmt(k.replace("|", " "), s))
        return
    rows = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    rows.sort(key=lambda d: (d["date"], d["race_id"]))
    M = build(rows)
    dates = [d["date"] for d in rows if is_flat(d)]
    M = {"buckets": BUCKETS, "min_n": MIN_N, "period": [min(dates), max(dates)], **M}
    json.dump(M, open(OUT, "w"), ensure_ascii=False, indent=1)
    n = sum(v["all"]["n"] for v in M["place"].values())
    print(f"{OUT} を書きました({n}鞍、{M['period'][0]}〜{M['period'][1]})")


if __name__ == "__main__":
    main()
