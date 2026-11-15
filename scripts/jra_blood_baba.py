"""研究: 渋った芝で、父系(と母の父の系統)によって3着内の来やすさが変わるか。回収率は測らない。

    python3 scripts/jra_blood_baba.py            # 2026-11-15 を除いた中央3年分
    python3 scripts/jra_blood_baba.py --with-day # 11/15 も含める

材料: data/jra/races.jsonl(芝の平地)、data/jra/pedigree.jsonl(取得途中・読むだけ)、
      data/jra/shutuba_*.jsonl の sire/damsire(血統が無い馬の補い)。系統は scripts/sire_line.py。

出すもの
  1. 血統の分かる出走の数と割合。
  2. 系統 × 馬場(良/稍/重・不) の 出走数・3着内率・「頭数から見た期待(3/頭数)との差」。
  3. 同じ馬どうし: 良と渋り(稍・重・不)の両方を走った馬について、
     着順率 = (着順-1)/(頭数-1)  (0=1着, 1=最下位) の 渋り平均 − 良平均 を馬ごとに出し、
     系統ごとに 重み w = n良*n渋/(n良+n渋) で平均。走数で縮める(0 に向けて K=10 の擬似重み)。
     マイナス＝渋ると着順が上がる。3着内率の差(渋り−良)も同じ重みで出す。
  4. 父系・母の父の系統・「父か母の父」(11/15 の分析の定義) の3通り。
"""
from __future__ import annotations

import collections
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from sire_line import LINES, line_of  # noqa: E402

DAY = "2026-11-15"
K_SHRINK = 10.0
BABA = ["良", "稍", "重不"]


def load_ped():
    ped = {}
    for l in open(ROOT / "data/jra/pedigree.jsonl", encoding="utf-8"):
        try:
            d = json.loads(l)
        except Exception:
            continue  # 追記中の途中行
        if d.get("horse_id"):
            ped[d["horse_id"]] = (d.get("sire"), d.get("damsire"))
    n_ped = len(ped)
    for f in sorted((ROOT / "data/jra").glob("shutuba_*.jsonl")):
        for l in open(f, encoding="utf-8"):
            try:
                s = json.loads(l)
            except Exception:
                continue
            for h in s.get("result", []):
                if h.get("horse_id") and h.get("sire") and h["horse_id"] not in ped:
                    ped[h["horse_id"]] = (h.get("sire"), h.get("damsire"))
    return ped, n_ped


def runs(with_day: bool):
    out = []
    for l in open(ROOT / "data/jra/races.jsonl", encoding="utf-8"):
        r = json.loads(l)
        if r.get("surface") != "芝":
            continue
        if r["date"] == DAY and not with_day:
            continue
        b = r.get("baba")
        b = "重不" if b in ("重", "不") else b
        if b not in ("良", "稍", "重不"):
            continue
        res = [h for h in r["result"] if isinstance(h.get("finish_pos"), int) and h["finish_pos"] > 0]
        n = len(res)
        if n < 5:
            continue
        for h in res:
            out.append(dict(hid=h["horse_id"], date=r["date"], place=r["place"], baba=b, n=n,
                            pos=h["finish_pos"], top3=h["finish_pos"] <= 3, exp3=min(3, n) / n,
                            pr=(h["finish_pos"] - 1) / (n - 1)))
    return out


def pct(x):
    return f"{100 * x:5.1f}"


def table(rows, key, title):
    print(f"\n### {title}: 系統 × 馬場（出走数 / 3着内率% / 期待との差pt）")
    agg = collections.defaultdict(lambda: [0, 0, 0.0])
    for x in rows:
        for k in (key(x), "全体"):
            a = agg[(k, x["baba"])]
            a[0] += 1
            a[1] += x["top3"]
            a[2] += x["exp3"]
    print("| 系統 | " + " | ".join(f"{b} 走 | {b} 3内% | {b} 差" for b in BABA) + " | 渋り−良(差の差) |")
    print("|---|" + "---|" * (3 * len(BABA) + 1))
    for k in LINES + ["?", "全体"]:
        if not any(agg[(k, b)][0] for b in BABA):
            continue
        cells = []
        ex = {}
        for b in BABA:
            n, t, e = agg[(k, b)]
            if n == 0:
                cells += ["0", "-", "-"]
                continue
            ex[b] = (t - e) / n
            flag = "※少" if n < 100 else ""
            cells += [f"{n}{flag}", pct(t / n), f"{100 * (t - e) / n:+.1f}"]
        sh = [agg[(k, b)] for b in ("稍", "重不")]
        ns = sum(a[0] for a in sh)
        dd = "-"
        if ns and "良" in ex:
            dd = f"{100 * ((sum(a[1] for a in sh) - sum(a[2] for a in sh)) / ns - ex['良']):+.1f}"
        print(f"| {k} | " + " | ".join(cells) + f" | {dd} |")


def same_horse(rows, key, title, wet=("稍", "重不")):
    print(f"\n### {title}: 同じ馬の 渋り({'・'.join(wet)}) − 良（着順率は−が良化、3内率は+が良化。K={K_SHRINK:g}で縮小）")
    by = collections.defaultdict(lambda: {"g": [], "w": []})
    lk = {}
    for x in rows:
        if x["baba"] == "良":
            by[x["hid"]]["g"].append(x)
        elif x["baba"] in wet:
            by[x["hid"]]["w"].append(x)
        lk[x["hid"]] = key(x)
    agg = collections.defaultdict(lambda: [0, 0.0, 0.0, 0.0, [], 0])  # 頭, Σw, Σw*d着順率, Σw*d3内, [d], 渋走数
    for hid, v in by.items():
        g, w = v["g"], v["w"]
        if not g or not w:
            continue
        wt = len(g) * len(w) / (len(g) + len(w))
        d_pr = sum(x["pr"] for x in w) / len(w) - sum(x["pr"] for x in g) / len(g)
        d_t3 = sum(x["top3"] - x["exp3"] for x in w) / len(w) - sum(x["top3"] - x["exp3"] for x in g) / len(g)
        for k in (lk[hid], "全体"):
            a = agg[k]
            a[0] += 1; a[1] += wt; a[2] += wt * d_pr; a[3] += wt * d_t3; a[4].append(d_pr); a[5] += len(w)
    print("| 系統 | 頭数 | 渋り走 | 着順率の差(縮小) | ±1SE | 3内率の差pt(縮小) |")
    print("|---|---|---|---|---|---|")
    res = {}
    for k in LINES + ["?", "全体"]:
        a = agg.get(k)
        if not a or a[0] == 0:
            continue
        m_pr = a[2] / (a[1] + K_SHRINK)
        m_t3 = a[3] / (a[1] + K_SHRINK)
        ds = a[4]
        mu = sum(ds) / len(ds)
        se = math.sqrt(sum((d - mu) ** 2 for d in ds) / max(1, len(ds) - 1) / len(ds))
        flag = "※少" if a[0] < 50 else ""
        print(f"| {k} | {a[0]}{flag} | {a[5]} | {m_pr:+.3f} | {se:.3f} | {100 * m_t3:+.1f} |")
        res[k] = (a[0], m_pr, se, m_t3)
    return res


def day_check(ped):
    """11/15 京都芝の再現(父か母の父がロベルト)。"""
    for l in open(ROOT / "data/jra/races.jsonl", encoding="utf-8"):
        r = json.loads(l)
        if r["date"] != DAY or r["place"] != "京都" or r["surface"] != "芝":
            continue
        rr = [h for h in r["result"] if isinstance(h.get("finish_pos"), int)]
        ro = [h for h in rr if "ロベルト" in [line_of(s) for s in ped.get(h["horse_id"], (None, None))]]
        print(f"  {r['race_id'][-2:]}R {r['distance']} {r['baba']} ロベルト(父か母父) {len(ro)}頭 3着内 "
              f"{sum(h['finish_pos'] <= 3 for h in ro)}")


def main():
    with_day = "--with-day" in sys.argv
    ped, n_ped = load_ped()
    allr = runs(with_day)
    print(f"# 渋った芝 × 系統（{'11/15 含む' if with_day else '11/15 を除く'}）")
    print(f"pedigree.jsonl {n_ped}頭 ＋ 出馬表で補い → {len(ped)}頭")
    known = [x for x in allr if x["hid"] in ped]
    for x in known:
        s, d = ped[x["hid"]]
        x["sl"], x["dl"] = line_of(s), line_of(d)
        x["either"] = "ロベルト" if "ロベルト" in (x["sl"], x["dl"]) else ("欧州" if "欧州" in (x["sl"], x["dl"]) else "その他")
    print(f"芝の平地の出走 {len(allr)} 走のうち 血統あり {len(known)} 走 ({100 * len(known) / len(allr):.1f}%)、"
          f"馬 {len({x['hid'] for x in allr})}頭中 {len({x['hid'] for x in known})}頭")
    for b in BABA:
        a = [x for x in allr if x["baba"] == b]
        k = [x for x in a if x["hid"] in ped]
        print(f"  {b}: {len(k)}/{len(a)} ({100 * len(k) / len(a):.1f}%)")
    by_year = collections.Counter(x["date"][:4] for x in allr)
    by_year_k = collections.Counter(x["date"][:4] for x in known)
    print("  年別: " + ", ".join(f"{y} {by_year_k[y]}/{by_year[y]}" for y in sorted(by_year)))
    print(f"  父の系統が?: {sum(x['sl'] == '?' for x in known)}走、母父の系統が?: {sum(x['dl'] == '?' for x in known)}走")
    unk = collections.Counter(ped[x['hid']][0] for x in known if x['sl'] == '?')
    print("  父?の上位: " + ", ".join(f"{s}:{c}" for s, c in unk.most_common(10)))
    unk = collections.Counter(ped[x['hid']][1] for x in known if x['dl'] == '?')
    print("  母父?の上位: " + ", ".join(f"{s}:{c}" for s, c in unk.most_common(10)))

    table(known, lambda x: x["sl"], "父の系統")
    same_horse(known, lambda x: x["sl"], "父の系統")
    same_horse(known, lambda x: x["sl"], "父の系統（重・不だけ）", wet=("重不",))
    table(known, lambda x: x["dl"], "母の父の系統")
    same_horse(known, lambda x: x["dl"], "母の父の系統")
    same_horse(known, lambda x: x["dl"], "母の父の系統（重・不だけ）", wet=("重不",))
    print("\n（11/15 の定義: 父か母の父がロベルト → ロベルト、そうでなく欧州 → 欧州）")
    table(known, lambda x: x["either"], "父か母の父")
    same_horse(known, lambda x: x["either"], "父か母の父")
    same_horse(known, lambda x: x["either"], "父か母の父（重・不だけ）", wet=("重不",))

    # 京都だけ(馬場の質が違うかもしれないので参考)
    kyo = [x for x in known if x["place"] == "京都"]
    table(kyo, lambda x: x["either"], "京都だけ・父か母の父")
    print("\n## 2026-11-15 京都芝の再現")
    day_check(ped)


if __name__ == "__main__":
    main()
