"""並び(隊列)×展開(ハイ/ミドル/スロー)ごとの「荒れ方」を中央の過去の鞍で調べる。回収率は測らない。

    python3 scripts/jra_arekata.py --n 2000 --out data/jra/arekata_rows.jsonl     # 予想を作って保存(重い。途中から再開できる)
    python3 scripts/jra_arekata.py --load data/jra/arekata_rows.jsonl             # 保存した行から集計だけ

予想の作り方(jra_kensho.py / jra_hana_hikaku.py と同じ)
  その鞍の行は出走馬・枠・騎手・斤量・馬体重だけ残し、着順・通過順・タイム・上がり・人気・ラップを消して先頭に置き、
  jra_tenkai_zu.one_race(--from-data と同じ組み立て)を呼ぶ。過去走はその鞍の日付より前だけ。
  ペースの想定は one_race の中の learned_pace → 風 → LightGBM(fc.diff_pred, fc.pace, fc.q, fc.rel)。
  馬ごとの値は build の rows(pos1, pos, gain, outer_score, nige, kouho)。jra_tenkai_zu.py は変えない。
  ※ 位置・ペースの LightGBM の係数は3年分で学習した表なので、その鞍自身が学習にわずかに混ざっている(既存の検証と同じ)。

人気は「穴＝6番人気以下」の定義と配当の集計にだけ使い、並びの分類には使わない。

並び(レース前に分かるもの)
  nige   … 逃げ候補(nige_rate≥0.3)の頭数 0/1/2/3+
  lone   … 単騎逃げの見込み(fc.lone_leader)あり/なし
  fside  … 予想1角(pos1)の順で前1/3の馬の outer_score の平均 − 全体の平均。抽出全体の3等分で 内寄り/中/外寄り
  shimai … 終い候補の有無(芝16頭以上でしか付かない)
  oshi   … 押上候補の有無
  front  … 予想1角 pos1≥0.67 の馬の割合。抽出全体の3等分で 先行少/先行中/先行多
  n      … 〜11/12〜15/16〜、sf … 芝/ダ、db … 〜1400/1500〜1800/1900〜
展開
  予想ペース fc.pace(境は fc.q = learned_pace の学習期間の3等分)、実際のペース pace_of(lap)["diff"] を同じ q で切る。
荒れ方
  3着内の6番人気以下の頭数、3連複の中央値・1万円以上の割合、勝ち馬が6番人気以下の割合。
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import io
import itertools
import json
import re
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

ANA = 6          # 6番人気以下を穴
BIG = 10000      # 3連複1万円以上


# ---------------------------------------------------------------- 予想を作る
def pick_races(rows, since, n):
    seen, cand = set(), []
    from jra_kensho import is_shinba, is_shogai
    for d in sorted(rows, key=lambda d: (d["date"], d["race_id"])):
        if d["race_id"] in seen or d["date"] < since:
            continue
        seen.add(d["race_id"])
        if d.get("surface") not in ("芝", "ダ") or is_shogai(d) or is_shinba(d) or not d.get("result"):
            continue
        if sum(1 for x in d["result"] if x.get("corner_pos")) < 0.8 * len(d["result"]):
            continue
        if not d.get("lap") or not (d.get("payouts") or {}).get("trio"):
            continue
        if not all(x.get("popularity") for x in d["result"] if isinstance(x.get("finish_pos"), int) and x["finish_pos"] <= 3):
            continue
        cand.append(d)
    return [cand[int(i * len(cand) / n)] for i in range(min(n, len(cand)))], len(cand)


def make(a):
    import jra_tenkai_zu as Z
    from jra_hana_hikaku import sanitize
    from nankeiba.scraping.db_race import pace_of
    rows = list(Z.load_rows(a.data))
    pick, nc = pick_races(rows, a.since, a.n)
    done = set()
    if Path(a.out).exists():
        done = {json.loads(l)["race_id"] for l in open(a.out, encoding="utf-8") if l.strip()}
    print(f"候補 {nc}鞍 → {len(pick)}鞍 ({pick[0]['date']}〜{pick[-1]['date']})、済み {len(done)}", file=sys.stderr)
    cap = {}
    orig = Z.build

    def spy(*x, **k):
        r = orig(*x, **k)
        cap["rows"] = r[1]
        return r

    Z.build = spy
    key = "__arekata__"
    cur_date = None
    fo = open(a.out, "a", encoding="utf-8")
    for i, d in enumerate(pick):
        if d["race_id"] in done:
            continue
        if d["date"] != cur_date:   # 日付が変わったらペースモデルの作り置きを捨てる(メモリ)
            Z._PACE_CACHE.clear()
            cur_date = d["date"]
        Z._ROWS_CACHE[key] = [sanitize(d)] + rows
        ns = argparse.Namespace(race_id=d["race_id"], shutuba=None, past=None, date=d["date"], place=None,
                                race_no=str(int(d["race_id"][-2:])), day=None, out="x", jockey_stats=None,
                                from_data=True, style="kawa", zone_front=0.4, pace_data=key, circle="", circle2="",
                                circle_each=False, hide_pace="", base_day=None, base_baba=None, base_day_dirt=None,
                                base_baba_dirt=None, base_time=None, kikou=False, no_trend=True)
        cap.clear()
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                _, _, _, fc = Z.one_race(ns, None)
        except Exception as e:  # noqa: BLE001
            print("  失敗", d["race_id"], repr(e), file=sys.stderr)
            continue
        pc = pace_of(d.get("lap") or [], d["distance"])
        res = {x["umaban"]: x for x in d["result"]}
        hs = []
        for r in cap.get("rows", []):
            x = res.get(r["ub"]) or {}
            hs.append({"ub": r["ub"], "pos1": r.get("pos1"), "pos": r.get("pos"), "gain": r.get("gain"),
                       "outer": r.get("outer_score"), "nige": r.get("nige"), "kouho": r.get("kouho") or [],
                       "fin": x.get("finish_pos"), "pop": x.get("popularity"), "c": x.get("corner_pos") or []})
        e = {"race_id": d["race_id"], "date": d["date"], "place": d["place"], "surface": d["surface"],
             "dist": d["distance"], "n": d["field_size"], "baba": d.get("baba"),
             "pace": fc.pace, "diff_pred": getattr(fc, "diff_pred", None), "q": list(getattr(fc, "q", None) or []),
             "rel": (fc.rel[0] if getattr(fc, "rel", None) else None), "lone": fc.lone_leader,
             "diff_act": pc["diff"] if pc else None, "c4": (d.get("corners") or {}).get("4"),
             "trio": list(d["payouts"]["trio"].values())[0] if d["payouts"].get("trio") else None,
             "trifecta": (list(d["payouts"]["trifecta"].values())[0] if d["payouts"].get("trifecta") else None),
             "h": hs}
        fo.write(json.dumps(e, ensure_ascii=False) + "\n")
        fo.flush()
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(pick)} {d['date']}", file=sys.stderr)
    fo.close()
    Z.build = orig


# ---------------------------------------------------------------- 集計
def c4_side(s):
    """4角の通過順の文字列 → 馬番 → 内/中/外(括弧の組の中で)・単独"""
    out = {}
    if not s:
        return out
    s = s.replace("*", "")
    for m in re.finditer(r"\(([^)]*)\)|(\d+)", s):
        if m.group(2):
            out[int(m.group(2))] = "単独"
            continue
        us = [int(t) for t in re.split(r"[,\s]+", m.group(1)) if t.strip().isdigit()]
        for i, u in enumerate(us):
            out[u] = "内" if i == 0 else "外" if i == len(us) - 1 else "中"
    return out


def tert(v, lo, hi):
    return 0 if v < lo else 2 if v >= hi else 1


def rank_third(hs, key):
    """予想の値(大きいほど前)の鞍の中の順位 → ub → 前/中/後"""
    kn = sorted([h for h in hs if h.get(key) is not None], key=lambda h: -h[key])
    if len(kn) < 3:
        return {}
    return {h["ub"]: ("前" if i / (len(kn) - 1) < 1 / 3 else "中" if i / (len(kn) - 1) <= 2 / 3 else "後")
            for i, h in enumerate(kn)}


def enrich(es):
    """鞍ごとの並び・展開・荒れ方を付ける"""
    out = []
    for e in es:
        hs = [h for h in e["h"] if isinstance(h["fin"], int) and h["fin"] > 0]
        if len(hs) < 5 or not e["q"] or e["diff_act"] is None or not e["trio"]:
            continue
        q = e["q"]
        e["pace_act"] = "ハイ" if e["diff_act"] < q[0] else ("スロー" if e["diff_act"] > q[1] else "ミドル")
        top = [h for h in hs if h["fin"] <= 3]
        e["ana3"] = sum(1 for h in top if h["pop"] and h["pop"] >= ANA)
        e["ana_win"] = any(h["fin"] == 1 and h["pop"] and h["pop"] >= ANA for h in hs)
        e["big"] = e["trio"] >= BIG
        nk = [h for h in hs if h.get("nige") is not None]
        nc = sum(1 for h in nk if h["nige"] >= 0.3)
        e["f_nige"] = "逃げ候補0" if nc == 0 else "逃げ候補1" if nc == 1 else "逃げ候補2" if nc == 2 else "逃げ候補3+"
        e["f_lone"] = "単騎逃げあり" if e["lone"] is not None else "単騎逃げなし"
        t1 = rank_third(hs, "pos1")
        fr = [h["outer"] for h in hs if t1.get(h["ub"]) == "前" and h.get("outer") is not None]
        al = [h["outer"] for h in hs if h.get("outer") is not None]
        e["_fside"] = (st.mean(fr) - st.mean(al)) if fr and al else None
        p1 = [h for h in hs if h.get("pos1") is not None]
        e["_front"] = (sum(1 for h in p1 if h["pos1"] >= 0.67) / len(hs)) if len(p1) >= 0.6 * len(hs) else None
        e["f_shimai"] = ("終い候補あり" if any("終い候補" in h["kouho"] for h in hs) else "終い候補なし") \
            if (e["surface"] == "芝" and e["n"] >= 16) else None
        e["f_oshi"] = "押上候補あり" if any("押上候補" in h["kouho"] for h in hs) else "押上候補なし"
        e["f_n"] = "〜11頭" if e["n"] <= 11 else "12〜15頭" if e["n"] <= 15 else "16頭〜"
        e["f_sf"] = e["surface"]
        e["f_db"] = "〜1400" if e["dist"] <= 1400 else "1500〜1800" if e["dist"] <= 1800 else "1900〜"
        out.append(e)
    fs = sorted(e["_fside"] for e in out if e["_fside"] is not None)
    ff = sorted(e["_front"] for e in out if e["_front"] is not None)
    cut = {"fside": (fs[len(fs) // 3], fs[2 * len(fs) // 3]), "front": (ff[len(ff) // 3], ff[2 * len(ff) // 3])}
    for e in out:
        e["f_fside"] = None if e["_fside"] is None else ("前組 内寄り", "前組 中", "前組 外寄り")[tert(e["_fside"], *cut["fside"])]
        e["f_front"] = None if e["_front"] is None else ("先行少", "先行中", "先行多")[tert(e["_front"], *cut["front"])]
    return out, cut


STRUCT = {"f_n", "f_sf", "f_db"}
FEATS = ["f_nige", "f_lone", "f_fside", "f_front", "f_shimai", "f_oshi", "f_n", "f_sf", "f_db"]


def stats(es):
    n = len(es)
    if not n:
        return None
    a = collections.Counter(min(e["ana3"], 3) for e in es)
    return {"n": n, "big": sum(e["big"] for e in es) / n, "med": st.median(e["trio"] for e in es),
            "win": sum(e["ana_win"] for e in es) / n, "any": sum(e["ana3"] >= 1 for e in es) / n,
            "a": [a[k] / n for k in range(4)], "mean": sum(e["ana3"] for e in es) / n}


def fmt_row(lab, s):
    return (f"| {lab} | {s['n']} | {s['big']:.0%} | {s['med']:,.0f} | {s['win']:.0%} | {s['any']:.0%} | "
            + " / ".join(f"{v:.0%}" for v in s["a"]) + f" | {s['mean']:.2f} |")


HDR = ("| 区分 | 鞍 | 3連複1万↑ | 3連複中央値 | 勝ち馬が穴 | 穴が3着内に1頭↑ | 穴の頭数 0/1/2/3 | 穴の平均頭数 |\n"
       "|---|---:|---:|---:|---:|---:|---|---:|")


def ana_origin(es):
    """3着内の穴馬の出どころ: 実際の4角(前/中/後・組の内外)、予想4角、予想1角、候補の札"""
    cnt = collections.defaultdict(collections.Counter)
    tot = 0
    for e in es:
        hs = [h for h in e["h"] if isinstance(h["fin"], int) and h["fin"] > 0]
        side = c4_side(e.get("c4"))
        t4, t1 = rank_third(hs, "pos"), rank_third(hs, "pos1")
        n = e["n"]
        for h in hs:
            if not (h["fin"] <= 3 and h["pop"] and h["pop"] >= ANA):
                continue
            tot += 1
            if h["c"]:
                v = (h["c"][-1] - 1) / max(1, n - 1)
                cnt["act4"]["前" if v < 1 / 3 else "中" if v <= 2 / 3 else "後"] += 1
            cnt["side"][side.get(h["ub"], "?")] += 1
            cnt["pred4"][t4.get(h["ub"], "?")] += 1
            cnt["pred1"][t1.get(h["ub"], "?")] += 1
            cnt["kouho"]["終い候補" if "終い候補" in h["kouho"] else "押上候補" if "押上候補" in h["kouho"] else "札なし"] += 1
            g = h.get("gain")
            cnt["gain"]["gain≥0.10" if g is not None and g >= 0.10 else "gain<0.10" if g is not None else "?"] += 1
    return tot, cnt


def origin_line(tot, cnt):
    if not tot:
        return "穴馬なし"
    f = lambda k, keys: " ".join(f"{x}{cnt[k][x] / tot:.0%}" for x in keys)  # noqa: E731
    return (f"穴{tot}頭 | 実4角 {f('act4', ['前', '中', '後'])} | 組 {f('side', ['内', '中', '外', '単独'])} | "
            f"予想4角 {f('pred4', ['前', '中', '後', '?'])} | 予想1角 {f('pred1', ['前', '中', '後'])} | "
            f"押し上げ(gain≥0.10) {cnt['gain']['gain≥0.10'] / tot:.0%} | {f('kouho', ['終い候補', '押上候補'])}")


def shuffle_outcomes(es, seed):
    """偶然の目安: 結果(配当・穴の頭数)だけを 頭数帯×芝ダ×距離帯 の中で入れ替える。並びと結果の結びつきが消える"""
    import random
    rnd = random.Random(seed)
    g = collections.defaultdict(list)
    for e in es:
        g[(e["f_n"], e["f_sf"], e["f_db"])].append(e)
    for v in g.values():
        outs = [(e["trio"], e["ana3"], e["ana_win"], e["big"]) for e in v]
        rnd.shuffle(outs)
        for e, o in zip(v, outs):
            e["trio"], e["ana3"], e["ana_win"], e["big"] = o


def report(es, min_n, thr, shuffle=None):
    es, cut = enrich(es)
    if shuffle is not None:
        shuffle_outcomes(es, shuffle)
    es.sort(key=lambda e: (e["date"], e["race_id"]))
    mid = es[len(es) // 2]["date"]
    H1 = [e for e in es if e["date"] < mid]
    H2 = [e for e in es if e["date"] >= mid]
    print(f"# 並び×展開と荒れ方(中央)\n\n対象 {len(es)}鞍 ({es[0]['date']}〜{es[-1]['date']})。"
          f"前半 {len(H1)}鞍(〜{mid}の前日) / 後半 {len(H2)}鞍({mid}〜)")
    print(f"前組の内外の境(前1/3の outer_score 平均 − 全体平均): 内寄り < {cut['fside'][0]:+.3f} ≤ 中 < {cut['fside'][1]:+.3f} ≤ 外寄り")
    print(f"先行の多さの境(予想1角 pos1≥0.67 の馬の割合): 少 < {cut['front'][0]:.2f} ≤ 中 < {cut['front'][1]:.2f} ≤ 多")

    B = stats(es)
    print("\n## 1. 基準\n")
    print(HDR)
    print(fmt_row("全体", B))
    print(fmt_row("前半", stats(H1)))
    print(fmt_row("後半", stats(H2)))
    for f in ("f_sf", "f_n", "f_db"):
        for v in sorted({e[f] for e in es}):
            print(fmt_row(v, stats([e for e in es if e[f] == v])))
    tot, cnt = ana_origin(es)
    print("\n穴馬(3着内の6番人気以下)の出どころ、全体: " + origin_line(tot, cnt))
    for pk, plab in (("pace", "予想"), ("pace_act", "実際")):
        for p in ("ハイ", "ミドル", "スロー"):
            tot, cnt = ana_origin([e for e in es if e[pk] == p])
            print(f"- {plab}{p}: " + origin_line(tot, cnt))

    print("\n### 予想ペースと実際のペースの一致(鞍数)\n")
    print("| 予想＼実際 | ハイ | ミドル | スロー |\n|---|---:|---:|---:|")
    for p in ("ハイ", "ミドル", "スロー"):
        print(f"| {p} | " + " | ".join(str(sum(e['pace'] == p and e['pace_act'] == a for e in es))
                                      for a in ("ハイ", "ミドル", "スロー")) + " |")

    for pk, plab in (("pace", "予想ペース"), ("pace_act", "実際のペース")):
        print(f"\n## 2. {plab}だけで\n")
        print(HDR)
        for p in ("ハイ", "ミドル", "スロー"):
            print(fmt_row(p, stats([e for e in es if e[pk] == p])))

    def cells(pk):
        out = []
        combos = [(f,) for f in FEATS] + list(itertools.combinations(FEATS, 2))
        for fs in combos:
            vals = [sorted({e[f] for e in es if e[f] is not None}) for f in fs]
            for vs in itertools.product(*vals):
                for p in ("ハイ", "ミドル", "スロー", None):
                    sel = lambda E: [e for e in E if all(e[f] == v for f, v in zip(fs, vs)) and (p is None or e[pk] == p)]  # noqa: E731
                    s = sel(es)
                    if len(s) < min_n:
                        continue
                    if p is None and all(f in STRUCT for f in fs):   # 頭数・芝ダ・距離だけの組は並びではない
                        continue
                    lab = " × ".join(vs) + (f" × {p}" if p else "")
                    base_np = [e for e in es if all(e[f] == v for f, v in zip(fs, vs))] if p else None
                    out.append((lab, s, sel(H1), sel(H2), base_np, fs))
        return out

    # 期待値: 頭数帯×芝ダ×距離帯 の割合(前半・後半それぞれの中で作る)。並びの差はこれとの差で見る
    def strat_rates(E):
        g = collections.defaultdict(list)
        for e in E:
            g[(e["f_n"], e["f_sf"], e["f_db"])].append(e)
        return {k: {m: sum(e[m] if m == "big" else e["ana3"] >= 1 for e in v) / len(v) for m in ("big", "any")}
                for k, v in g.items()}
    R0, R1, R2 = strat_rates(es), strat_rates(H1), strat_rates(H2)

    def expect(E, m, R):
        return sum(R[(e["f_n"], e["f_sf"], e["f_db"])][m] for e in E) / len(E)

    print("\n## 2b. ペースだけで、頭数・芝ダ・距離から見込む割合との差\n")
    print("| ペース | 鞍 | 3連複1万↑ | 見込み | 差 | 穴が3着内 | 見込み | 差 |\n|---|---:|---:|---:|---:|---:|---:|---:|")
    for pk, plab in (("pace", "予想"), ("pace_act", "実際")):
        for p in ("ハイ", "ミドル", "スロー"):
            s_ = [e for e in es if e[pk] == p]
            a = stats(s_)
            eb, ea = expect(s_, "big", R0), expect(s_, "any", R0)
            print(f"| {plab}{p} | {a['n']} | {a['big']:.0%} | {eb:.0%} | {(a['big'] - eb) * 100:+.0f} | "
                  f"{a['any']:.0%} | {ea:.0%} | {(a['any'] - ea) * 100:+.0f} |")

    for pk, plab in (("pace", "予想ペース版(レース前に使える)"), ("pace_act", "実際のペース版(展開が分かったときの形)")):
        print(f"\n## 3. パターン — {plab}\n")
        print(f"条件: 鞍{min_n}以上。「見込み」= その鞍の頭数帯×芝ダ×距離帯の割合の平均(前半・後半はそれぞれの中で作る)。"
              f"全体で見込みとの差が ±{thr * 100:.0f}pt 以上、前半・後半それぞれも同じ向きで ±{thr * 50:.0f}pt 以上。"
              "物差しは「3連複1万円以上の割合」と「穴が3着内に1頭以上の割合」。")
        found = []
        for lab, s_, s1, s2, bnp, fs in cells(pk):
            if not s1 or not s2:
                continue
            a, a1, a2 = stats(s_), stats(s1), stats(s2)
            for m in ("big", "any"):
                x0, x1, x2 = expect(s_, m, R0), expect(s1, m, R1), expect(s2, m, R2)
                d0, d1, d2 = a[m] - x0, a1[m] - x1, a2[m] - x2
                if abs(d0) >= thr and d1 * d0 > 0 and d2 * d0 > 0 and abs(d1) >= thr / 2 and abs(d2) >= thr / 2:
                    found.append((m, d0, lab, s_, a, a1, a2, d1, d2, bnp, x0))
        print(f"\n調べた組み合わせ {sum(1 for _ in cells(pk))}、条件を満たしたもの {len(found)}(3連複 {sum(x[0] == 'big' for x in found)} / 穴 {sum(x[0] == 'any' for x in found)})")
        if not found:
            print("\n見つからなかった。")
            continue
        for m, mlab in (("big", "3連複1万円以上"), ("any", "穴が3着内に1頭以上")):
            fm = sorted([x for x in found if x[0] == m], key=lambda x: -abs(x[1]))
            print(f"\n### {mlab}の割合(全体 {B[m]:.0%})\n")
            if not fm:
                print("該当なし")
                continue
            print("| 並び × 展開 | 鞍 | 実際 | 見込み | 差 | 前半(鞍) 差 | 後半(鞍) 差 | 同じ並びでペース問わず | 3連複中央値 | 勝ち馬が穴 | 穴の平均頭数 |")
            print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
            for _, d0, lab, s_, a, a1, a2, d1, d2, bnp, x0 in fm:
                nb = f"{stats(bnp)[m]:.0%}({len(bnp)})" if bnp else "-"
                print(f"| {lab} | {a['n']} | {a[m]:.0%} | {x0:.0%} | {d0 * 100:+.0f} | {a1[m]:.0%}({a1['n']}) {d1 * 100:+.0f} | "
                      f"{a2[m]:.0%}({a2['n']}) {d2 * 100:+.0f} | {nb} | {a['med']:,.0f} | {a['win']:.0%} | {a['mean']:.2f} |")
        print("\n#### 穴馬の出どころ(上の表に出た組み合わせ。重複は1回)\n")
        tot, cnt = ana_origin(es)
        print("- (比較)全体: " + origin_line(tot, cnt))
        seen = set()
        for x in sorted(found, key=lambda x: -abs(x[1])):
            if x[2] in seen:
                continue
            seen.add(x[2])
            tot, cnt = ana_origin(x[3])
            print(f"- {x[2]} ({x[4]['n']}鞍): " + origin_line(tot, cnt))

    theme_report(es, H1, H2, expect, R0, R1, R2)


THEMES = [   # 3. で前半・後半とも同じ向きに出た組をまとめた形(並び, ペース)
    ("先行多 × ハイ", lambda e: e["f_front"] == "先行多", "ハイ"),
    ("逃げ候補3+ × ハイ", lambda e: e["f_nige"] == "逃げ候補3+", "ハイ"),
    ("先行多 かつ 逃げ候補3+ × ハイ", lambda e: e["f_front"] == "先行多" and e["f_nige"] == "逃げ候補3+", "ハイ"),
    ("逃げ候補1 × スロー", lambda e: e["f_nige"] == "逃げ候補1", "スロー"),
    ("先行少 × スロー", lambda e: e["f_front"] == "先行少", "スロー"),
    ("前組 外寄り × スロー", lambda e: e["f_fside"] == "前組 外寄り", "スロー"),
    ("前組 内寄り × 終い候補あり(芝16頭↑)", lambda e: e["f_fside"] == "前組 内寄り" and e["f_shimai"] == "終い候補あり", None),
    ("(比較)全体", lambda e: True, None),
]


def ana_rates(es):
    """6番人気以下の馬のうち3着内に来た割合を、予想の位置・札・実際の4角で分ける"""
    g = collections.defaultdict(lambda: [0, 0])
    for e in es:
        hs = [h for h in e["h"] if isinstance(h["fin"], int) and h["fin"] > 0]
        t4, t1 = rank_third(hs, "pos"), rank_third(hs, "pos1")
        side = c4_side(e.get("c4"))
        for h in hs:
            if not (h["pop"] and h["pop"] >= ANA):
                continue
            hit = h["fin"] <= 3
            keys = ["全", "予4" + t4.get(h["ub"], "?"), "予1" + t1.get(h["ub"], "?")]
            gn = h.get("gain")
            keys.append("g+" if gn is not None and gn >= 0.10 else "g-")
            if "終い候補" in h["kouho"]:
                keys.append("終い")
            if "押上候補" in h["kouho"]:
                keys.append("押上")
            if h["c"]:
                v = (h["c"][-1] - 1) / max(1, e["n"] - 1)
                keys.append("実4" + ("前" if v < 1 / 3 else "中" if v <= 2 / 3 else "後"))
            keys.append("組" + side.get(h["ub"], "?"))
            for k in keys:
                g[k][0] += hit
                g[k][1] += 1
    return g


def theme_report(es, H1, H2, expect, R0, R1, R2):
    print("\n## 4. まとめた形(3. で前半・後半とも同じ向きに出た組を、並び1つ×ペースにまとめたもの)\n")
    for pk, plab in (("pace", "予想ペース"), ("pace_act", "実際のペース")):
        print(f"\n### {plab}\n")
        print("| 形 | 鞍 | 3連複1万↑ | 見込み | 差 | 前半 差 | 後半 差 | 穴が3着内 | 見込み | 差 | 前半 差 | 後半 差 | 3連複中央値 | 勝ち馬が穴 |")
        print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for lab, f, p in THEMES:
            sel = lambda E: [e for e in E if f(e) and (p is None or e[pk] == p)]  # noqa: E731
            s_, s1, s2 = sel(es), sel(H1), sel(H2)
            if not s_ or not s1 or not s2:
                continue
            a, a1, a2 = stats(s_), stats(s1), stats(s2)
            cells_ = []
            for m in ("big", "any"):
                x0, x1, x2 = expect(s_, m, R0), expect(s1, m, R1), expect(s2, m, R2)
                cells_.append(f"{a[m]:.0%} | {x0:.0%} | {(a[m] - x0) * 100:+.0f} | {(a1[m] - x1) * 100:+.0f} | {(a2[m] - x2) * 100:+.0f}")
            print(f"| {lab} | {a['n']} | " + " | ".join(cells_) + f" | {a['med']:,.0f} | {a['win']:.0%} |")
        print(f"\n#### 穴馬はどこから来るか({plab}): 6番人気以下の馬のうち3着内に来た割合(来た頭数/その位置の穴馬の頭数)\n")
        cols = [("全", "穴馬全体"), ("予4前", "予想4角 前"), ("予4中", "予想4角 中"), ("予4後", "予想4角 後"),
                ("g+", "押し上げ gain≥0.10"), ("終い", "終い候補"), ("押上", "押上候補"),
                ("実4前", "実4角 前"), ("実4中", "実4角 中"), ("実4後", "実4角 後"),
                ("組内", "組の内"), ("組外", "組の外"), ("組単独", "単独")]
        print("| 形 | " + " | ".join(c[1] for c in cols) + " |")
        print("|---|" + "---:|" * len(cols))
        for lab, f, p in THEMES:
            g = ana_rates([e for e in es if f(e) and (p is None or e[pk] == p)])
            print(f"| {lab} | " + " | ".join(
                (f"{g[k][0] / g[k][1]:.1%}({g[k][0]}/{g[k][1]})" if g[k][1] >= 20 else (f"-({g[k][0]}/{g[k][1]})" if g[k][1] else "-"))
                for k, _ in cols) + " |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data" / "jra" / "races.jsonl"))
    ap.add_argument("--since", default="2024-06-01")
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--out", default=str(ROOT / "data" / "jra" / "arekata_rows.jsonl"))
    ap.add_argument("--load", help="保存した行から集計だけ")
    ap.add_argument("--min-n", type=int, default=100)
    ap.add_argument("--thr", type=float, default=0.08)
    ap.add_argument("--shuffle", type=int, help="偶然の目安: 結果を同じ頭数帯×芝ダ×距離帯の中で入れ替えて(この種で)同じ集計をする")
    a = ap.parse_args()
    if not a.load:
        make(a)
        a.load = a.out
    es = [json.loads(l) for l in open(a.load, encoding="utf-8") if l.strip()]
    report(es, a.min_n, a.thr, a.shuffle)


if __name__ == "__main__":
    main()
