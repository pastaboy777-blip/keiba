"""騎手の集計(3年分): 前に行かせる癖・外に出す癖・勝率・3着内率。展開図(jra_tenkai_zu.py)が使う。

    python3 scripts/jra_jockey.py --data data/jra/races.jsonl --before 2026-11-15

  前付け(front_bias) … その騎手が乗った時の1角位置 − 乗った馬のいつもの序盤位置(過去走だけ)。− なら前に行かせる。
                       件数で縮める(10騎乗ぶん0へ寄せる)。jra_position_model2 の jk_bias と同じ作り。
  外出し(outer_rate) … 4角で横並びになった時に組の外側だった割合(件数で全体平均へ縮める)。
  勝率・3着内率 … 全体と芝・ダ別。
--before より前の鞍だけを使う(その日以降の結果は入れない)。出力: models/jockey_stats.json
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.core import dataset as ds, tenkai as tk  # noqa: E402
from nankeiba.core.backtest import record_result  # noqa: E402


def groups(s):
    out = {}
    for m in re.finditer(r"\(([^)]*)\)|(\d+)", s.replace("*", "")):
        if m.group(1) is not None:
            g = [int(x) for x in re.findall(r"\d+", m.group(1))]
            for i, u in enumerate(g):
                out[u] = (i + 1, len(g))
    return out


def norm_name(s: str | None) -> str:
    """全角→半角(NFKC)、印・空白を除く。"""
    import unicodedata
    return re.sub(r"[\s▲△☆◇★▽]", "", unicodedata.normalize("NFKC", s or ""))


def merge_short(S):
    """netkeiba の略名(例 M.デム・西村淳)を JRA公式の正式名(M.デムーロ・西村淳也)へ寄せる。
    略名が「ちょうど1人の正式名の先頭」に一致するときだけ寄せる。"""
    names = list(S)
    for short in names:
        if short not in S:
            continue
        longs = [l for l in names if l != short and l in S and len(l) > len(short)
                 and (l.startswith(short) or l.split(".")[-1] == short)]
        if len(longs) == 1:
            dst, src = S[longs[0]], S.pop(short)
            for k in ("n", "win", "top3", "lat_n", "outer"):
                dst[k] += src[k]
            dst["front"] += src["front"]
            for sf in ("芝", "ダ"):
                dst[sf][0] += src[sf][0]
                dst[sf][1] += src[sf][1]
    return S


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/jra/races.jsonl")
    ap.add_argument("--before", default="9999-12-31")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "models" / "jockey_stats.json"))
    a = ap.parse_args()
    raw = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    raw = [d for d in raw if d.get("surface") in ("芝", "ダ") and d["date"] < a.before]
    raw.sort(key=lambda d: (d["date"], d["race_id"]))
    h: dict = {}
    S = collections.defaultdict(lambda: {"n": 0, "win": 0, "top3": 0, "front": [], "lat_n": 0, "outer": 0,
                                         "芝": [0, 0], "ダ": [0, 0]})
    for d in raw:
        r = ds.race_from_dict(d)
        n = len(r.entries)
        G = groups(d["corners"].get("4") or d["corners"].get("3") or "")
        for x in d["result"]:
            j = norm_name(x.get("jockey"))
            if not j:
                continue
            s = S[j]
            s["n"] += 1
            s["win"] += x["finish_pos"] == 1
            s["top3"] += x["finish_pos"] <= 3
            s[d["surface"]][0] += 1
            s[d["surface"]][1] += x["finish_pos"] <= 3
            sp = tk.style_profile(h.get(x["horse_id"], []))
            if x.get("corner_pos") and sp.early is not None and n > 1:
                s["front"].append((x["corner_pos"][0] - 1) / (n - 1) - sp.early)
            g = G.get(x["umaban"])
            if g and g[1] >= 2:
                s["lat_n"] += 1
                s["outer"] += g[0] == g[1]
        record_result(r, h)
    S = merge_short(dict(S))
    all_lat = sum(s["lat_n"] for s in S.values())
    base_outer = sum(s["outer"] for s in S.values()) / max(1, all_lat)
    out = {}
    for j, s in S.items():
        out[j] = {"n": s["n"], "win": round(s["win"] / s["n"], 3), "top3": round(s["top3"] / s["n"], 3),
                  "front_bias": round(sum(s["front"]) / (len(s["front"]) + 10), 4) if s["front"] else 0.0,
                  "outer_rate": round((s["outer"] + base_outer * 10) / (s["lat_n"] + 10), 3),
                  "top3_turf": round(s["芝"][1] / s["芝"][0], 3) if s["芝"][0] else None,
                  "top3_dirt": round(s["ダ"][1] / s["ダ"][0], 3) if s["ダ"][0] else None}
    json.dump({"before": a.before, "base_outer": round(base_outer, 3), "jockeys": out},
              open(a.out, "w"), ensure_ascii=False, indent=0)
    top = sorted((v for v in out.items() if v[1]["n"] >= 200), key=lambda kv: kv[1]["front_bias"])
    print(f"騎手 {len(out)}人  集計 {len(raw)}鞍(〜{a.before})  横並びで外側の全体平均 {base_outer:.1%}")
    print("前に行かせる(200騎乗以上):", " ".join(f"{k}{v['front_bias']:+.3f}" for k, v in top[:8]))
    print("控える:", " ".join(f"{k}{v['front_bias']:+.3f}" for k, v in top[-8:]))


if __name__ == "__main__":
    main()
