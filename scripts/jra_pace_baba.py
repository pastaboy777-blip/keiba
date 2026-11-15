"""渋った馬場でペース(前後半差)の予想は偏るか。芝ダ×馬場ごとの「実−予」と、補正の効き目。

    python3 scripts/jra_pace_baba.py --data data/jra/races.jsonl            # 表だけ
    python3 scripts/jra_pace_baba.py --data data/jra/races.jsonl --save     # 効けば models/pace_baba_adj.json

問い(2026-11-15): ペースの外れ17鞍のうち11鞍が「実際のほうが前半がゆるい」側、京都の重い芝3鞍はそろってスロー寄り。
渋った馬場でいつも起きる偏りか。

予想は jra_tenkai_zu.py と同じ作り方で、その鞍より前のデータだけで出す。
  PM      … PaceModel(コース平均+直線式+馬場)。月ごとに、その月より前の全鞍で作り直す(前向き)。
             + 当日の前の鞍のずれ × 0.2(展開図の learned_pace と同じ)。
  LGBM前日 … models/pace_lgbm.json の reg。学習は境(cut)より前なので、境より後の鞍だけ(検証区間)。
             当日のずれの欄は「同じ開催の前の開催日のずれ」(展開図を前日に描くとき)。
  LGBM当日 … 同じ reg。当日のずれの欄は当日の前の鞍(無ければ前の開催日)。展開図を当日に描き直すとき。
             学習(jra_pace_lgbm.py)では当日の前の鞍だけ(無ければ0)。展開図は前日に描くと開催のずれを入れる ── ここが違う。
区分の境 q は学習区間(cut より前)の前後半差の三分位。実−予 が + = 実際のほうが前半がゆるい(スロー寄り)。

補正: 芝ダ×馬場ごとの 実−予 の平均を件数で縮めた値(n/(n+k))。
  決める期間と確かめる期間は時系列で分ける(検証区間の前半で決め、後半で確かめる。PM は 3年の前半/後半でも)。
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jra_pace_model import PaceModel  # noqa: E402
from jra_wind_kenkyu import wind_at  # noqa: E402
from jra_class_kenkyu import cls_x  # noqa: E402
from nankeiba.core import dataset as ds, tenkai as tk, course as cs  # noqa: E402
from nankeiba.core.backtest import race_contexts, record_result  # noqa: E402
from nankeiba.scraping.db_race import pace_of  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PLACES = ["札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"]
BABA = ["良", "稍", "重", "不"]
BI = {"良": 0, "稍": 1, "重": 2, "不": 3}


def main() -> None:
    import lightgbm as lgb
    import numpy as np
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/jra/races.jsonl")
    ap.add_argument("--k", type=float, default=30.0, help="補正の縮め(n/(n+k))")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--dump", help="この日の鞍ごとの 予・実 を出す(例 2026-11-15)")
    a = ap.parse_args()
    raw = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    raw = [d for d in raw if d.get("surface") in ("芝", "ダ") and pace_of(d.get("lap") or [], d["distance"])]
    raw.sort(key=lambda d: (d["date"], d["race_id"]))
    M = json.load(open(ROOT / "models" / "pace_lgbm.json"))
    reg = lgb.Booster(model_str=M["reg"])
    cut = M["cut"]
    y_of = {d["race_id"]: pace_of(d["lap"], d["distance"])["diff"] for d in raw}
    v = sorted(y_of[d["race_id"]] for d in raw if d["date"] < cut)
    q = (v[len(v) // 3], v[2 * len(v) // 3])
    pm_cut = PaceModel().fit([d for d in raw if d["date"] < cut])   # LGBM の材料(学習と同じ)

    # PaceModel を月ごとに作り直す(その月より前の鞍だけ)
    months = sorted({d["date"][:7] for d in raw})
    pm_m = {}
    for mth in months:
        tr = [d for d in raw if d["date"] < mth + "-01"]
        if len(tr) >= 1500:
            pm_m[mth] = PaceModel().fit(tr)

    h: dict = {}
    front_hist: dict = {}
    day_res = collections.defaultdict(list)       # (日,場,芝ダ) → LGBM 材料の残差(pm_cut)
    day_res_m = collections.defaultdict(list)     # (日,場,芝ダ) → PM(月)の残差
    by_ps = collections.defaultdict(list)          # (場,芝ダ) → [(日, 残差pm_cut)]
    out = []
    for d in raw:
        r = ds.race_from_dict(d)
        c = race_contexts(r, h)
        fc = tk.forecast({e.num(): p for e, p, _ in c}, place=r.place, distance=r.distance, surface=r.surface)
        known = [s for s in fc.styles.values() if s.early is not None]
        n = d["field_size"]
        y = y_of[d["race_id"]]
        dk = (d["date"], d["place"], d["surface"])
        rec = {"d": d, "y": y}
        pm = pm_m.get(d["date"][:7])
        if pm is not None:
            prev = day_res_m[dk]
            rec["pm"] = pm.predict(d) + (0.2 * st.mean(prev) if prev else 0.0)
            rec["pm0"] = pm.predict(d)
            day_res_m[dk].append(y - pm.predict(d))
        base = pm_cut.predict(d)
        hid = {e.num(): e.horse_id for e in r.entries}
        lr = [st.mean(front_hist[hid[u]][-3:]) for u in fc.order[:3] if front_hist.get(hid[u])]
        d0 = dt.date.fromisoformat(d["date"])
        meet = [x for (dd, x) in by_ps[(d["place"], d["surface"])]
                if dd < d["date"] and (d0 - dt.date.fromisoformat(dd)).days <= 8]
        w = wind_at(d["place"], d["date"], int(d["race_id"][-2:])) or (0.0, 0.0, 0.0)
        xb = [base, d["distance"] / 1000, n / 18, 1.0 if d["surface"] == "芝" else 0.0,
              BI.get(d.get("baba") or "良", 0), cs.front_bias(d["place"], d["surface"]),
              PLACES.index(d["place"]) if d["place"] in PLACES else -1, int(d["date"][5:7]),
              sum(s.nige_rate for s in known), sum(1 for s in known if s.early <= 0.25) / max(1, n),
              len(known) / max(1, n), st.mean(lr) if lr else 0.0, len(lr),
              0.0, 0, w[0], w[1], w[2], int(d["race_id"][-2:])] + cls_x(d)
        if d["date"] >= cut:
            xs = []
            for day in (meet, day_res[dk] or meet):
                x = list(xb)
                x[13], x[14] = (st.mean(day) if day else 0.0), len(day)
                xs.append(x)
            p = reg.predict(np.array(xs))
            rec["lg_pre"], rec["lg_day"] = float(p[0]), float(p[1])
        out.append(rec)
        res = y - base
        day_res[dk].append(res)
        by_ps[(d["place"], d["surface"])].append((d["date"], res))
        for e in r.entries:
            if e.corner_pos and e.corner_pos[0] <= 2:
                front_hist.setdefault(e.horse_id, []).append(res)
        record_result(r, h)

    lab = lambda x: 2 if x < q[0] else (0 if x > q[1] else 1)  # noqa: E731   0=S 1=M 2=H
    print(f"全 {len(out)}鞍  LGBM の境 {cut}  区分の境 ハイ < {q[0]:+.2f} ≤ ミドル ≤ {q[1]:+.2f} < スロー")

    def table(title, recs, key, adj=None):
        print(f"\n## {title}")
        print(f"{'':6s} {'件数':>5s} {'実−予 平均':>10s} {'中央値':>7s} {'当たり':>7s} {'予より遅(S寄り)外れ':>16s} {'予より速(H寄り)外れ':>16s}")
        res = {}
        for sf in ("芝", "ダ"):
            for b in BABA + ["稍重不"]:
                g = [r_ for r_ in recs if key in r_ and r_["d"]["surface"] == sf
                     and ((r_["d"].get("baba") or "良") == b or (b == "稍重不" and (r_["d"].get("baba") or "良") != "良"))]
                if not g:
                    continue
                pr = [r_[key] + (adj.get(f"{sf}{r_['d'].get('baba') or '良'}", 0.0) if adj else 0.0) for r_ in g]
                e = [r_["y"] - p_ for r_, p_ in zip(g, pr)]
                hit = sum(lab(p_) == lab(r_["y"]) for r_, p_ in zip(g, pr))
                slow = sum(lab(r_["y"]) < lab(p_) for r_, p_ in zip(g, pr))   # 実際のほうがスロー寄り
                fast = sum(lab(r_["y"]) > lab(p_) for r_, p_ in zip(g, pr))
                res[f"{sf}{b}"] = (len(g), st.mean(e), hit / len(g))
                print(f"{sf}{b:<4s} {len(g):5d} {st.mean(e):+10.2f} {st.median(e):+7.2f} {hit / len(g):7.1%}"
                      f" {slow:9d}({slow / len(g):4.0%}) {fast:9d}({fast / len(g):4.0%})")
        g = [r_ for r_ in recs if key in r_]
        pr = [r_[key] + (adj.get(f"{r_['d']['surface']}{r_['d'].get('baba') or '良'}", 0.0) if adj else 0.0) for r_ in g]
        hit = sum(lab(p_) == lab(r_["y"]) for r_, p_ in zip(g, pr))
        big = sum({lab(p_), lab(r_["y"])} == {0, 2} for r_, p_ in zip(g, pr))
        print(f"{'全体':6s} {len(g):5d} {st.mean(r_['y'] - p_ for r_, p_ in zip(g, pr)):+10.2f} {'':7s} {hit / len(g):7.1%}  大外れ {big / len(g):.1%}")
        return res, hit / len(g), len(g)

    te = [r_ for r_ in out if r_["d"]["date"] >= cut]
    table("PM(PaceModel 月ごと作り直し + 当日のずれ0.2) 3年(最初の作り直しから)", out, "pm")
    table("PM 検証区間(cut 以降)", te, "pm")
    table("LGBM前日(開催のずれ) 検証区間", te, "lg_pre")
    table("LGBM当日(当日の前の鞍、無ければ開催) 検証区間", te, "lg_day")
    # 渋った芝は日ごとに固まる(同じ日の鞍は同じ馬場)。開催日ごとの平均のずれの散らばり
    print("\n## 芝 重・不 を開催日(日×場)ごとに: LGBM前日の 実−予 の日平均")
    dd = collections.defaultdict(list)
    for r_ in te:
        if r_["d"]["surface"] == "芝" and r_["d"].get("baba") in ("重", "不"):
            dd[(r_["d"]["date"], r_["d"]["place"])].append(r_["y"] - r_["lg_pre"])
    ms = sorted((st.mean(e), k, len(e)) for k, e in dd.items())
    print(f"  {len(ms)}日  日平均の平均 {st.mean(m for m, _, _ in ms):+.2f}  +0.3以上 {sum(m >= 0.3 for m, _, _ in ms)}日"
          f" / −0.3以下 {sum(m <= -0.3 for m, _, _ in ms)}日")
    for m, k, n_ in ms:
        print(f"    {k[0]} {k[1]} {n_}鞍 {m:+.2f}")
    if a.dump:
        print(f"\n## {a.dump} の鞍ごと(実−予、区分 予→実)")
        S = "SMH"
        for r_ in out:
            d = r_["d"]
            if d["date"] != a.dump:
                continue
            print(f"  {d['race_id']} {d['place']}{d['race_id'][-2:]}R {d['surface']}{d['distance']} {d.get('baba') or '-'}"
                  f"  実 {r_['y']:+.1f}  PM {r_.get('pm', 0):+.2f}({S[lab(r_.get('pm', 0))]})"
                  f"  LG前日 {r_.get('lg_pre', 0):+.2f}({S[lab(r_.get('lg_pre', 0))]})"
                  f"  LG当日 {r_.get('lg_day', 0):+.2f}({S[lab(r_.get('lg_day', 0))]})  実{S[lab(r_['y'])]}")
    # 検証区間の後半だけでも同じ向きか
    mid = te[len(te) // 2]["d"]["date"]
    te1 = [r_ for r_ in te if r_["d"]["date"] < mid]
    te2 = [r_ for r_ in te if r_["d"]["date"] >= mid]
    print(f"\n検証区間を {mid} で前後に分ける: 前 {len(te1)}鞍 / 後 {len(te2)}鞍")

    def fit_adj(recs, key):
        adj = {}
        for sf in ("芝", "ダ"):
            for b in BABA:
                e = [r_["y"] - r_[key] for r_ in recs if key in r_ and r_["d"]["surface"] == sf
                     and (r_["d"].get("baba") or "良") == b]
                if e:
                    adj[f"{sf}{b}"] = round(sum(e) / (len(e) + a.k), 3)
        return adj

    def wet_only(adj):   # 良は 0 に(良のずれは馬場の補正ではない)
        return {k: (0.0 if k.endswith("良") else v) for k, v in adj.items()}

    results = {}
    for key in ("pm", "lg_pre", "lg_day"):
        adj = wet_only(fit_adj(te1, key))
        print(f"\n===== {key}: 検証区間の前半で決めた補正 {adj}")
        _, h0, n0 = table(f"{key} 検証後半 補正なし", te2, key)
        _, h1, _ = table(f"{key} 検証後半 補正あり", te2, key, adj)
        results[key] = (adj, h0, h1, n0)
    # PM は3年の前後でも(最初の作り直しから中央で分ける)
    pmr = [r_ for r_ in out if "pm" in r_]
    m2 = pmr[len(pmr) // 2]["d"]["date"]
    adj = wet_only(fit_adj([r_ for r_ in pmr if r_["d"]["date"] < m2], "pm"))
    print(f"\n===== pm 3年: {m2} より前で決めた補正 {adj}")
    _, h0, n0 = table("pm 後半 補正なし", [r_ for r_ in pmr if r_["d"]["date"] >= m2], "pm")
    _, h1, _ = table("pm 後半 補正あり", [r_ for r_ in pmr if r_["d"]["date"] >= m2], "pm", adj)
    results["pm_3y"] = (adj, h0, h1, n0)
    print("\n## まとめ(後半の3区分の当たり 補正なし → あり)")
    for k_, (adj, h0, h1, n0) in results.items():
        print(f"  {k_:<7s} {h0:.1%} → {h1:.1%}  ({n0}鞍)")
    if a.save:
        adj_all = wet_only(fit_adj(te, "lg_pre"))
        json.dump({"adj": adj_all, "k": a.k, "from": cut, "note": "jra_pace_baba.py 芝ダ×馬場の 実−予 平均(縮め済)。良は0"},
                  open(ROOT / "models" / "pace_baba_adj.json", "w"), ensure_ascii=False, indent=1)
        print("保存 models/pace_baba_adj.json", adj_all)


if __name__ == "__main__":
    main()
