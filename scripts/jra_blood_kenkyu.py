"""研究: 血統(父)で新馬戦の隊列・ハナが読めるか。先の情報は使わない(時系列で産駒の成績を貯める)。

    python3 scripts/jra_blood_kenkyu.py

父ごとに「それまでの」産駒の1角相対位置(0=先頭)を、芝ダ別に縮めた平均で持つ(産駒が少ない父は全体平均へ)。
新馬戦で: 父の数字の順位と実際の1角順位の相関、ハナ(1角先頭)を当てる率を、
  枠だけ / 騎手(1角3番手以内率)だけ / 父だけ / 枠+騎手+父 で比べる。
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def spearman(a, b):
    n = len(a)
    if n < 3:
        return None
    ra = {i: r for r, i in enumerate(sorted(range(n), key=lambda i: a[i]))}
    rb = {i: r for r, i in enumerate(sorted(range(n), key=lambda i: b[i]))}
    d = sum((ra[i] - rb[i]) ** 2 for i in range(n))
    return 1 - 6 * d / (n * (n * n - 1))


def main():
    P = {json.loads(l)["horse_id"]: json.loads(l) for l in open(ROOT / "data/jra/pedigree.jsonl")}
    raw = [json.loads(l) for l in open(ROOT / "data/jra/races.jsonl")]
    raw = [d for d in raw if d.get("surface") in ("芝", "ダ")]
    raw.sort(key=lambda d: (d["date"], d["race_id"]))
    sire = collections.defaultdict(lambda: [0, 0.0, 0])        # (父, 芝ダ) → [走, 位置合計, ハナ]
    jk = collections.defaultdict(lambda: [0, 0])                 # 騎手 → [騎乗, 1角3番手以内]
    allm = [0, 0.0]
    res = collections.defaultdict(list)
    hana = collections.Counter()
    nr = 0
    K = 8.0
    for d in raw:
        c = (d.get("race_class") or "") + (d.get("name") or "")
        n = d["field_size"]
        rs = [r for r in d["result"] if r.get("corner_pos")]
        if ("新馬" in c or "デビュー" in c) and len(rs) >= 6 and d["date"] >= "2024-06-01":
            have = [r for r in rs if r["horse_id"] in P]
            if len(have) >= 0.8 * len(rs):
                mu = allm[1] / max(1, allm[0])
                f = {}
                for r in rs:
                    p = P.get(r["horse_id"])
                    s = sire[(p["sire"], d["surface"])] if p else [0, 0.0, 0]
                    sv = (s[1] + K * mu) / (s[0] + K)
                    j = jk[r.get("jockey")]
                    jv = -(j[1] + 1) / (j[0] + 5)
                    g = (r["umaban"] - 1) / max(1, n - 1)
                    f[r["umaban"]] = {"枠": g, "騎手": jv, "父": sv, "枠+騎手+父": 0.3 * g + 1.5 * jv + 1.0 * (sv - mu) * 3}
                act = [(r["corner_pos"][0] - 1) / max(1, n - 1) for r in rs]
                lead = [r["umaban"] for r in rs if r["corner_pos"][0] == 1]
                nr += 1
                for k in ("枠", "騎手", "父", "枠+騎手+父"):
                    sc = [f[r["umaban"]][k] for r in rs]
                    rho = spearman(sc, act)
                    if rho is not None:
                        res[k].append(rho)
                    top = min(rs, key=lambda r: f[r["umaban"]][k])["umaban"]
                    hana[k] += top in lead
                    top3 = sorted(rs, key=lambda r: f[r["umaban"]][k])[:3]
                    hana[k + "3"] += any(r["umaban"] in lead for r in top3)
        for r in rs:
            p = P.get(r["horse_id"])
            pos = (r["corner_pos"][0] - 1) / max(1, n - 1)
            if p:
                s = sire[(p["sire"], d["surface"])]
                s[0] += 1; s[1] += pos; s[2] += r["corner_pos"][0] == 1
                allm[0] += 1; allm[1] += pos
            j = jk[r.get("jockey")]
            j[0] += 1; j[1] += r["corner_pos"][0] <= 3
    print(f"新馬戦 {nr}鞍(2024-06以降、8割以上の馬の血統あり)")
    print("材料            1角順位の相関   ハナ1頭目で的中   上位3頭に入る")
    for k in ("枠", "騎手", "父", "枠+騎手+父"):
        print(f"  {k:12s}  {sum(res[k])/len(res[k]):+.3f}          {hana[k]/nr:.1%}            {hana[k+'3']/nr:.1%}")


if __name__ == "__main__":
    main()
