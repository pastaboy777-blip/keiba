"""展開図の先頭候補(ハナ)の出し方を過去の鞍で比べる(中央)。回収率などは測らない。

    python3 scripts/jra_hana_hikaku.py --n 300 --since 2025-06-01

比べる順:
  order … fc.order(tenkai.forecast の序盤位置の直近加重。jra_kensho.py が数えている順)
  pos1  … 位置モデルの1角(r["pos1"]。kawa の見解「1コーナーで前に行くのは」が使っている順)
  hana  … ハナ専用モデル(r["hana"]。apply_hana_model の線形→LightGBM)
当たり: 1頭目が実際の1角先頭か / 上位3頭に1角先頭がいるか。

材料: jra_kensho.py と同じく one_race の組み立て(from_data → build)を、その鞍の日付より前の走だけで行う。
その鞍の行は出走馬・枠・騎手・斤量・馬体重だけ残し、着順・通過順・タイム・上がり・人気を消してから渡す
(from_data は同じ race_id の最初の行を使うので、消した行を先頭に置く)。ペース・盤面の描画は順に関係しないので呼ばない。
鞍の選び方: 平地(芝・ダ)・新馬と障害を除く・1角の通過順がある鞍を日付順に並べて等間隔に n 鞍。
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import jra_tenkai_zu as Z  # noqa: E402
from jra_kensho import is_shinba, is_shogai  # noqa: E402

KEEP = ("umaban", "horse_id", "horse_name", "waku", "jockey", "kinryo", "weight", "weight_diff")
HANA_CUT = json.load(open(ROOT / "models" / "hana_model.json"))["cut"]


def sanitize(d):
    d = dict(d)
    d["result"] = [{k: x.get(k) for k in KEEP} for x in d["result"]]
    for k in ("corners", "lap", "time"):
        d.pop(k, None)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data" / "jra" / "races.jsonl"))
    ap.add_argument("--since", default="2025-06-01")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--out", help="鞍ごとの結果を JSONL で書く")
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    seen, cand = set(), []
    for d in sorted(rows, key=lambda d: (d["date"], d["race_id"])):
        if d["race_id"] in seen or d["date"] < a.since:
            continue
        seen.add(d["race_id"])
        if d.get("surface") not in ("芝", "ダ") or is_shogai(d) or is_shinba(d) or not d.get("result"):
            continue
        if not any(x.get("corner_pos") and x["corner_pos"][0] == 1 for x in d["result"]):
            continue
        cand.append(d)
    step = len(cand) / a.n
    pick = [cand[int(i * step)] for i in range(min(a.n, len(cand)))]
    print(f"候補 {len(cand)}鞍 → {len(pick)}鞍 ({pick[0]['date']}〜{pick[-1]['date']})", file=sys.stderr)

    base = [d for d in rows]
    key = "__hikaku__"
    res = []
    for i, d in enumerate(pick):
        Z._ROWS_CACHE[key] = [sanitize(d)] + base   # 先頭のその鞍(結果を消した行)が使われる。過去走は日付より前だけ
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                past, waku, name, info, klass, date, place, jockeys = Z.from_data(key, d["race_id"])
                fc, rr, rk = Z.build(past, waku, place=place, dist=d["distance"], surface=d["surface"],
                                     baba=d.get("baba"), jockeys=jockeys)
        except Exception as e:  # noqa: BLE001
            print("  失敗", d["race_id"], repr(e), file=sys.stderr)
            continue
        lead = {x["umaban"] for x in d["result"] if x.get("corner_pos") and x["corner_pos"][0] == 1}
        known = sum(1 for r in rr if r.get("pos") is not None) / max(1, len(rr))
        e = {"race_id": d["race_id"], "date": d["date"], "lead": sorted(lead), "known": round(known, 2),
             "oos": d["date"] >= HANA_CUT}
        orders = {"order": list(fc.order),
                  "pos1": [r["ub"] for r in sorted([r for r in rr if r.get("pos1") is not None], key=lambda r: -r["pos1"])],
                  "hana": [r["ub"] for r in sorted([r for r in rr if "hana" in r], key=lambda r: -r["hana"])]}
        for k, o in orders.items():
            e[k] = o[:3]
            if o:
                e[k + "1"] = o[0] in lead
                e[k + "3"] = bool(set(o[:3]) & lead)
        res.append(e)
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(pick)}", file=sys.stderr)

    if a.out:
        with open(a.out, "w", encoding="utf-8") as fo:
            for e in res:
                fo.write(json.dumps(e, ensure_ascii=False) + "\n")

    def line(lab, es):
        out = [f"{lab}({len(es)}鞍)"]
        for k in ("order", "pos1", "hana"):
            g = [e for e in es if k + "1" in e]
            h1, h3 = sum(e[k + "1"] for e in g), sum(e[k + "3"] for e in g)
            out.append(f"  {k:5s} 1頭目 {h1}/{len(g)} ({h1 / max(1, len(g)):.1%})  上位3頭 {h3}/{len(g)} ({h3 / max(1, len(g)):.1%})")
        print("\n".join(out))

    line("全体", res)
    line(f"ハナモデルの学習より後(>= {HANA_CUT})", [e for e in res if e["oos"]])
    line(f"ハナモデルの学習期間(< {HANA_CUT})", [e for e in res if not e["oos"]])
    line("通過順の記録がある馬 7割以上", [e for e in res if e["known"] >= 0.7])


if __name__ == "__main__":
    main()
