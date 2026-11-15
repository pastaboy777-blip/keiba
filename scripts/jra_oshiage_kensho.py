"""展開図の「押し上げ(gain)」と「上がりの馬(rk)」が3着内に効くかを過去の鞍で見る(中央)。回収率は測らない。

    python3 scripts/jra_oshiage_kensho.py --n 300 --n16 300 --out data/jra/oshiage_kensho.jsonl
    python3 scripts/jra_oshiage_kensho.py --load data/jra/oshiage_kensho.jsonl     # 作った行から集計だけ

予想の作り方(jra_hana_hikaku.py と同じ)
  その鞍の行は出走馬・枠・騎手・斤量・馬体重だけ残し、着順・通過順・タイム・上がり・人気を消して先頭に置く。
  from_data → build で、過去走はその鞍の日付より前だけ。jra_tenkai_zu.py は変えない。
  予想4角 = r["pos"](位置モデルの4角、1=先頭〜0=最後方)。その鞍の中で順位にして前/中/後ろ 1/3 に分ける。
  押し上げ = r["gain"](過去走の 1角の相対位置 − 4角の相対位置 の中央値。+ が前へ出る)。
  上がり = rk(過去の芝1800m以上の上がりの中央値で、その鞍の中の速い順。展開図の「終い」)。
           芝1800未満の鞍では引けない馬が多いので、あわせて ag = 過去5走のうち同じ芝ダ・距離±400m で
           「その鞍の上がり順位」の中央値(races.jsonl の agari_rank、その鞍より前の走だけ)も持つ。
鞍の選び方
  --n:   平地(芝・ダ)・新馬と障害を除く・4角の通過順がある鞍を、--since から日付順に等間隔に n 鞍。
  --n16: そのうち芝で16頭以上の鞍から等間隔に n16 鞍(上の n 鞍と重なったものは1回だけ)。
場の前残りの強さ = models/course_pos.json(scripts/jra_course_pos.py)の「4角で前1/3にいた馬の3着内率」
  (場×芝ダ×距離、件数が少なければ距離帯)。※表は3年分全部で作っているので、その鞍自身も1/数百で混ざっている。
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import io
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import jra_tenkai_zu as Z  # noqa: E402
from jra_course_pos import lookup  # noqa: E402
from jra_hana_hikaku import sanitize  # noqa: E402
from jra_kensho import is_shinba, is_shogai  # noqa: E402


def pick_races(rows, since, n, n16):
    seen, cand = set(), []
    for d in sorted(rows, key=lambda d: (d["date"], d["race_id"])):
        if d["race_id"] in seen or d["date"] < since:
            continue
        seen.add(d["race_id"])
        if d.get("surface") not in ("芝", "ダ") or is_shogai(d) or is_shinba(d) or not d.get("result"):
            continue
        if sum(1 for x in d["result"] if x.get("corner_pos")) < 0.8 * len(d["result"]):
            continue
        cand.append(d)
    even = lambda c, k: [c[int(i * len(c) / k)] for i in range(min(k, len(c)))] if k else []  # noqa: E731
    p1 = even(cand, n)
    big = [d for d in cand if d["surface"] == "芝" and d["field_size"] >= 16]
    p2 = even(big, n16)
    out, ids = [], set()
    for d in p1 + p2:
        if d["race_id"] not in ids:
            ids.add(d["race_id"])
            out.append(d)
    return out, len(cand), len(big), {d['race_id'] for d in p1}


def agari_hist(rows):
    """horse_id → [(date, surface, dist, agari_rank)]"""
    h = collections.defaultdict(list)
    for d in rows:
        for x in d.get("result") or []:
            if x.get("agari_rank"):
                h[x["horse_id"]].append((d["date"], d.get("surface"), d["distance"], x["agari_rank"]))
    return h


def make(a):
    rows = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    pick, nc, nb, base = pick_races(rows, a.since, a.n, a.n16)
    print(f"候補 {nc}鞍(芝16頭以上 {nb}) → {len(pick)}鞍", file=sys.stderr)
    AH = agari_hist(rows)
    key = "__oshiage__"
    out = []
    for i, d in enumerate(pick):
        Z._ROWS_CACHE[key] = [sanitize(d)] + rows
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                past, waku, name, info, klass, date, place, jockeys = Z.from_data(key, d["race_id"])
                fc, rr, rk = Z.build(past, waku, place=place, dist=d["distance"], surface=d["surface"],
                                     baba=d.get("baba"), jockeys=jockeys)
        except Exception as e:  # noqa: BLE001
            print("  失敗", d["race_id"], repr(e), file=sys.stderr)
            continue
        ck, cs = lookup(d["place"], d["surface"], d["distance"])
        res = {x["umaban"]: x for x in d["result"]}
        n = len(rr)
        known = [r for r in rr if r.get("pos") is not None]
        order = sorted(known, key=lambda r: -r["pos"])
        prk = {r["ub"]: i + 1 for i, r in enumerate(order)}
        for r in rr:
            x = res.get(r["ub"]) or {}
            hid = x.get("horse_id")
            ags = [ar for (dt, sf, ds, ar) in sorted(AH.get(hid, []), reverse=True)
                   if dt < d["date"] and sf == d["surface"] and abs(ds - d["distance"]) <= 400][:5]
            out.append({
                "race_id": d["race_id"], "base": d["race_id"] in base, "date": d["date"], "place": d["place"], "surface": d["surface"],
                "dist": d["distance"], "n": d["field_size"], "baba": d.get("baba"),
                "front3": cs["front3"] if cs else None, "course_key": ck,
                "ub": r["ub"], "pos": r.get("pos"), "prk": prk.get(r["ub"]), "nk": len(known),
                "gain": r.get("gain"), "rk": rk.get(r["ub"]), "nrk": len(rk),
                "ag": st.median(ags) if ags else None, "nag": len(ags),
                "fin": x.get("finish_pos"), "c": x.get("corner_pos") or [],
            })
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(pick)}", file=sys.stderr)
    return out


def pct(h, n):
    return f"{h}/{n} ({h / n:.0%})" if n else "-"


def third(e):
    """予想4角の順位で 前/中/後"""
    if e["prk"] is None or e["nk"] < 3:
        return None
    q = (e["prk"] - 1) / max(1, e["nk"] - 1)
    return "前" if q < 1 / 3 else "中" if q <= 2 / 3 else "後"


def top3(e):
    return isinstance(e["fin"], int) and 0 < e["fin"] <= 3


def act_gain(e):
    c, n = e["c"], e["n"]
    if len(c) < 2 or n < 2:
        return None
    return ((c[0] - 1) - (c[-1] - 1)) / (n - 1)


def report(es_all, gcut):
    es_all = [e for e in es_all if isinstance(e["fin"], int) and e["fin"] > 0]
    es = [e for e in es_all if e["base"]]   # 2 は等間隔の n 鞍だけ(芝16頭以上の足しは 3 だけで使う)
    races = {e["race_id"] for e in es}
    print(f"\n対象 {len(races)}鞍・{len(es)}頭  (押し上げの線 gain ≥ {gcut:+.2f})")

    # 場の前残りの強さ: 抽出の鞍の front3 を3等分
    fr = sorted({e["race_id"]: e["front3"] for e in es if e["front3"] is not None}.values())
    t1, t2 = fr[len(fr) // 3], fr[2 * len(fr) // 3]
    grp = lambda e: None if e["front3"] is None else ("前残り強" if e["front3"] >= t2 else "前残り弱" if e["front3"] < t1 else "前残り中")  # noqa: E731
    print(f"場の前残りの強さ(前1/3の3着内率): 弱 < {t1:.3f} ≤ 中 < {t2:.3f} ≤ 強")

    print("\n## 2. 押し上げ: 予想4角の位置が同じ組の中で、gain が大きい馬とそれ以外の3着内率")
    print("| 場の前残り | 予想4角 | gain≥線 | それ以外 | 差 | gain≥線の馬の実際の1角→4角(平均) | それ以外 |")
    print("|---|---|---|---|---:|---:|---:|")
    for g in ("全体", "前残り強", "前残り中", "前残り弱"):
        for t in ("前", "中", "後", "計"):
            sel = [e for e in es if (g == "全体" or grp(e) == g) and (t == "計" or third(e) == t)
                   and e["gain"] is not None and third(e)]
            up = [e for e in sel if e["gain"] >= gcut]
            ot = [e for e in sel if e["gain"] < gcut]
            hu, ho = sum(map(top3, up)), sum(map(top3, ot))
            au = [v for v in map(act_gain, up) if v is not None]
            ao = [v for v in map(act_gain, ot) if v is not None]
            diff = (hu / len(up) - ho / len(ot)) if up and ot else None
            print(f"| {g} | {t} | {pct(hu, len(up))} | {pct(ho, len(ot))} | "
                  f"{'' if diff is None else f'{diff * 100:+.1f}pt'} | "
                  f"{(st.mean(au) if au else 0):+.3f} | {(st.mean(ao) if ao else 0):+.3f} |")

    print("\n### gain の段階別(全体、予想4角 中・後)")
    print("| gain | 予想4角 中 | 予想4角 後 |")
    print("|---|---|---|")
    for lo, hi in ((-9, 0.0), (0.0, 0.10), (0.10, 0.20), (0.20, 0.30), (0.30, 9)):
        cells = []
        for t in ("中", "後"):
            sel = [e for e in es if third(e) == t and e["gain"] is not None and lo <= e["gain"] < hi]
            cells.append(pct(sum(map(top3, sel)), len(sel)))
        lab = f"{lo:+.2f}〜{hi:+.2f}".replace("-9.00", "").replace("+9.00", "")
        print(f"| {lab} | " + " | ".join(cells) + " |")

    print("\n## 3. 上がりの馬: 芝16頭以上で予想4角が後ろ1/3の馬")
    big = [e for e in es_all if e["surface"] == "芝" and e["n"] >= 16 and third(e) == "後"]
    print(f"芝16頭以上 {len({e['race_id'] for e in big})}鞍、予想4角 後ろ1/3 {len(big)}頭")
    print("| 物差し | 区分 | 3着内 | 1着 |")
    print("|---|---|---|---|")
    for lab, sel in (
        ("rk(芝1800↑の上がり、鞍内順)", [("1〜3位", [e for e in big if e["rk"] and e["rk"] <= 3]),
                                       ("4位以下", [e for e in big if e["rk"] and e["rk"] > 3]),
                                       ("引けない", [e for e in big if not e["rk"]])]),
        ("ag(同距離帯の過去の上がり順位の中央値)", [("≤3", [e for e in big if e["ag"] is not None and e["ag"] <= 3]),
                                              ("3超〜6", [e for e in big if e["ag"] is not None and 3 < e["ag"] <= 6]),
                                              ("6超", [e for e in big if e["ag"] is not None and e["ag"] > 6]),
                                              ("引けない", [e for e in big if e["ag"] is None])]),
    ):
        for k, s in sel:
            print(f"| {lab} | {k} | {pct(sum(map(top3, s)), len(s))} | {pct(sum(e['fin'] == 1 for e in s), len(s))} |")
    print("\n### 距離で分けて(rk 1〜3位 / それ以外の後ろの馬)")
    print("| 距離 | rk 1〜3位 | それ以外 | ag≤3 | ag>3 |")
    print("|---|---|---|---|---|")
    for lab, f in (("〜1600", lambda e: e["dist"] <= 1600), ("1700〜", lambda e: e["dist"] >= 1700)):
        s = [e for e in big if f(e)]
        a1 = [e for e in s if e["rk"] and e["rk"] <= 3]
        a2 = [e for e in s if not (e["rk"] and e["rk"] <= 3)]
        b1 = [e for e in s if e["ag"] is not None and e["ag"] <= 3]
        b2 = [e for e in s if e["ag"] is not None and e["ag"] > 3]
        print(f"| {lab} | {pct(sum(map(top3, a1)), len(a1))} | {pct(sum(map(top3, a2)), len(a2))} | "
              f"{pct(sum(map(top3, b1)), len(b1))} | {pct(sum(map(top3, b2)), len(b2))} |")
    print("\n### 参考: 同じ物差しを予想4角 中・前でも(芝16頭以上)")
    print("| 予想4角 | rk 1〜3位 | それ以外 | ag≤3 | ag>3 |")
    print("|---|---|---|---|---|")
    for t in ("前", "中", "後"):
        s = [e for e in es_all if e["surface"] == "芝" and e["n"] >= 16 and third(e) == t]
        a1 = [e for e in s if e["rk"] and e["rk"] <= 3]
        a2 = [e for e in s if not (e["rk"] and e["rk"] <= 3)]
        b1 = [e for e in s if e["ag"] is not None and e["ag"] <= 3]
        b2 = [e for e in s if e["ag"] is not None and e["ag"] > 3]
        print(f"| {t} | {pct(sum(map(top3, a1)), len(a1))} | {pct(sum(map(top3, a2)), len(a2))} | "
              f"{pct(sum(map(top3, b1)), len(b1))} | {pct(sum(map(top3, b2)), len(b2))} |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data" / "jra" / "races.jsonl"))
    ap.add_argument("--since", default="2024-06-01")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--n16", type=int, default=300)
    ap.add_argument("--gain", type=float, default=0.20)
    ap.add_argument("--out")
    ap.add_argument("--load")
    a = ap.parse_args()
    if a.load:
        es = [json.loads(l) for l in open(a.load, encoding="utf-8") if l.strip()]
    else:
        es = make(a)
        if a.out:
            with open(a.out, "w", encoding="utf-8") as fo:
                for e in es:
                    fo.write(json.dumps(e, ensure_ascii=False) + "\n")
    report(es, a.gain)


if __name__ == "__main__":
    main()
