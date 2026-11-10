"""前後と内外の2次元で隊列を想定し、「内から何頭目」を事前に決めて検証する。

    python3 scripts/jra_tairetsu2d.py --data data/jra/races.jsonl

前後: 過去走の4角位置の中央値(図と同じ)。
内外: 4角で併走したとき「組の外側」になる度合いを学習(前 2/3 で学習、後 1/3 で検証)。
       特徴 = 馬番(外枠ほど+)・過去の外率(件数で縮める)・逃げ率・前後位置・頭数
隊列の組: 前後の想定位置が近い馬(頭数で正規化した幅 band 以内)を同じ組にし、組の中を内外の想定で並べる。
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import statistics as st
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import jra_learn as J  # noqa: E402
from jra_pace_model import PaceModel  # noqa: E402
from nankeiba.core import dataset as ds, tenkai as tk  # noqa: E402
from nankeiba.core.backtest import record_result  # noqa: E402
from nankeiba.scraping.db_race import pace_of  # noqa: E402

LAT = ["1", "gate", "out_rate", "n_lat", "nige", "front", "field"]


def groups(s: str) -> dict[int, tuple[int, int]]:
    """通過順表記 → {馬番: (組の中の内からの順, 組の頭数)}。単独通過は (0, 1)。"""
    out = {}
    for m in re.finditer(r"\(([^)]*)\)|(\d+)", s.replace("*", "")):
        if m.group(1) is not None:
            g = [int(x) for x in re.findall(r"\d+", m.group(1))]
            for i, u in enumerate(g):
                out[u] = (i + 1, len(g))
        else:
            out[int(m.group(2))] = (0, 1)
    return out


def build_formation(front: dict, outer: dict, n: int, band: float = 0.12):
    """front: 馬番→前さ(1=先頭), outer: 馬番→外度。前から組を作り、組内を内→外に並べる。
    返り値: 馬番→(組番号, 組の中の内からの順)"""
    order = sorted(front, key=lambda u: -front[u])
    rows, cur, head = [], [], None
    for u in order:
        if head is None or head - front[u] <= band:
            cur.append(u)
            head = front[u] if head is None else head
        else:
            rows.append(cur)
            cur, head = [u], front[u]
    if cur:
        rows.append(cur)
    pos = {}
    for gi, g in enumerate(rows):
        for li, u in enumerate(sorted(g, key=lambda u: outer[u])):
            pos[u] = (gi, li + 1)
    return pos


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/jra/races.jsonl")
    ap.add_argument("--band", type=float, default=0.12)
    ap.add_argument("--k", type=int, default=3, help="内から何頭目までを選ぶか")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "models" / "lateral_model.json"))
    a = ap.parse_args()

    raw = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    raw = [d for d in raw if d.get("surface") in ("芝", "ダ") and pace_of(d.get("lap") or [], d["distance"])]
    raw.sort(key=lambda d: (d["date"], d["race_id"]))
    cut = raw[int(len(raw) * 2 / 3)]["date"]
    mid = raw[len(raw) // 2]["date"]
    mA = PaceModel().fit([d for d in raw if d["date"] < mid])
    mB = PaceModel().fit([d for d in raw if d["date"] >= mid])
    pred = {d["race_id"]: (mB if d["date"] < mid else mA).predict(d) for d in raw}
    v = sorted(pred.values())
    q = (v[len(v) // 3], v[2 * len(v) // 3])
    sozo = lambda d: "H" if pred[d["race_id"]] < q[0] else ("S" if pred[d["race_id"]] > q[1] else "M")  # noqa: E731

    h: dict = {}
    lat_hist: dict = collections.defaultdict(list)
    races = []
    for d in raw:
        r = ds.race_from_dict(d)
        n = len(r.entries)
        front, feats = {}, {}
        for e in r.entries:
            past = h.get(e.horse_id, [])
            c4 = [(x.corner_pos[-1] - 1) / max(1, x.field_size - 1) for x in past if x.corner_pos]
            if not c4:
                continue
            front[e.num()] = 1 - st.median(c4)
            lh = lat_hist[e.horse_id]
            feats[e.num()] = {
                "1": 1.0, "gate": ((e.umaban or 1) - 1) / max(1, n - 1),
                "out_rate": (sum(lh) + 0.43 * 4) / (len(lh) + 4), "n_lat": min(len(lh), 6) / 6,
                "nige": tk.style_profile(past).nige_rate, "front": front[e.num()], "field": n / 18,
            }
        c = d["corners"].get("4") or d["corners"].get("3") or ""
        G = groups(c) if c else {}
        if len(front) >= 0.7 * n and n >= 8 and G:
            races.append({"d": d, "front": front, "feats": feats, "G": G, "sozo": sozo(d)})
        for x in d["result"]:
            g = G.get(x["umaban"])
            if g and g[1] >= 2:
                lat_hist[x["horse_id"]].append(1 if g[0] == g[1] else 0)
        record_result(r, h)

    # 内外モデル(併走した馬のみで学習)
    def samples(rs):
        for rc in rs:
            for u, f in rc["feats"].items():
                g = rc["G"].get(u)
                if g and g[1] >= 2:
                    yield f, (g[0] - 1) / (g[1] - 1)   # 0=最内 1=外側
    tr = [rc for rc in races if rc["d"]["date"] < cut]
    te = [rc for rc in races if rc["d"]["date"] >= cut]
    S = list(samples(tr))
    w = J.ols([[f[k] for k in LAT] for f, _ in S], [y for _, y in S])
    outer = lambda f: sum(wi * f[k] for wi, k in zip(w, LAT))  # noqa: E731
    T = list(samples(te))
    print(f"鞍: 学習 {len(tr)} / 検証 {len(te)}(境 {cut})")
    print(f"内外モデル(検証・併走した馬 {len(T)}件): 予想外度 と 実際(組の中の内0〜外1) の相関 "
          f"{J.corr([outer(f) for f, _ in T], [y for _, y in T]):+.3f}  / 馬番だけ "
          f"{J.corr([f['gate'] for f, _ in T], [y for _, y in T]):+.3f}")
    print("  係数:", "  ".join(f"{k} {wi:+.2f}" for k, wi in zip(LAT, w)))

    # 2次元隊列 → 「内から k 頭目まで」ボックスを想定別に(検証区間)
    R = collections.defaultdict(collections.Counter)
    for rc in te:
        d = rc["d"]
        out = {u: outer(f) for u, f in rc["feats"].items()}
        pos = build_formation(rc["front"], out, d["field_size"], a.band)
        top3 = tuple(sorted(x["umaban"] for x in d["result"][:3]))
        trio = d["payouts"].get("trio", {})
        pay = trio.get("-".join(map(str, top3)), sum(trio.values()) if len(trio) == 1 else 0)
        inner = [u for u, (gi, li) in pos.items() if li <= a.k]
        frontN = sorted(rc["front"], key=lambda u: -rc["front"][u])[:len(inner)]
        # 実際に内(組の最内〜2頭目)を通った割合で、内外想定の当たりも見る
        for u in inner:
            g = rc["G"].get(u)
            if g and g[1] >= 2:
                R[rc["sozo"]]["inner_known"] += 1
                R[rc["sozo"]]["inner_ok"] += g[0] <= 2
        for name, sel in [(f"内{a.k}頭目まで", inner), ("前から同数", frontN)]:
            k = len(sel)
            if k < 3:
                continue
            s = R[rc["sozo"]]
            s[name + "鞍"] += 1
            s[name + "点"] += k * (k - 1) * (k - 2) // 6
            s[name + "頭"] += k
            if set(top3) <= set(sel):
                s[name + "的中"] += 1
                s[name + "払"] += pay
    for t, lab in [("S", "スロー想定"), ("M", "ミドル想定"), ("H", "ハイ想定")]:
        s = R[t]
        print(f"\n【{lab}】 内{a.k}頭目までと想定した馬が実際に併走組の内〜2頭目: "
              f"{s['inner_ok'] / max(1, s['inner_known']):.1%}(n={s['inner_known']})")
        for name in (f"内{a.k}頭目まで", "前から同数"):
            n = s[name + "鞍"]
            if n:
                print(f"  {name:<10s} {n}鞍 平均{s[name + '頭'] / n:.1f}頭・{s[name + '点'] / n:.0f}点  "
                      f"的中 {s[name + '的中'] / n:.1%}  回収率 {s[name + '払'] / max(1, s[name + '点'] * 100):.1%}")
    json.dump({"features": LAT, "coef": w, "cut": cut}, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
