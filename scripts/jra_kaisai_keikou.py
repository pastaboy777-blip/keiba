"""今の開催(場×芝ダ×週)の決まり方を、結果のデータだけで並べる。

    python3 scripts/jra_kaisai_keikou.py --kaisai 202605 202608 [--course course.json]

--kaisai は race_id の先頭8桁(年4桁+場コード2桁+回2桁)(例 20260505 = 5回東京)。
--course は 京都芝1400/1600 の内回り・外回りを JRA 公式から取った {race_id: "芝・右 外"} の JSON。
          無ければ 1400/1600 は「内外不明」に入れる。

見るもの: 3着内の4角位置(頭数3等分)/4角先頭の着順/最終コーナー括弧内の位置/枠/ペース(前3F−後3F)/
上がり順位/勝ち時計/6番人気以下の3着内。数字は分子/分母で出す。回収率・的中率は測らない。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jra_tenkai_zu import waku_of  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def lanes(s: str) -> dict:
    """通過順の文字列 → {馬番: 最内/内/外/単独}。括弧の中は内から外の順に並んでいる。"""
    out, i = {}, 0
    s = s.replace("*", "")
    while i < len(s):
        c = s[i]
        if c == "(":
            j = s.index(")", i)
            g = [int(x) for x in re.findall(r"\d+", s[i:j])]
            for k, u in enumerate(g):
                out[u] = "最内" if k == 0 else ("内" if k < len(g) / 2 else "外")
            i = j + 1
        elif c.isdigit():
            m = re.match(r"\d+", s[i:])
            out[int(m.group())] = "単独"
            i += len(m.group())
        else:
            i += 1
    return out


def front_back(lap, dist):
    """前半600m・後半600mの時計。端数の距離は最初のラップが100m。"""
    if not lap:
        return None
    first = dist % 200 or 200
    cum, t, pts = [0], 0.0, [0.0]
    d = 0
    for k, x in enumerate(lap):
        d += first if k == 0 else 200
        t += x
        cum.append(d)
        pts.append(t)

    def at(m):
        for a in range(1, len(cum)):
            if cum[a] >= m:
                return pts[a - 1] + (pts[a] - pts[a - 1]) * (m - cum[a - 1]) / (cum[a] - cum[a - 1])
        return pts[-1]
    total = pts[-1]
    return at(600), total - at(dist - 600)


def band(pos, n):
    if pos is None:
        return None
    return "前" if pos <= n / 3 else ("中" if pos <= 2 * n / 3 else "後")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kaisai", nargs="+", default=["20260505", "20260805"])
    ap.add_argument("--data", default=str(ROOT / "data/jra/races.jsonl"))
    ap.add_argument("--course", default=None)
    ap.add_argument("--by-day", action="store_true", help="週でなく開催日(1〜6日目)ごとに並べる")
    a = ap.parse_args()
    course = json.load(open(a.course)) if a.course else {}
    wk = {}
    for p in sorted(ROOT.glob("data/jra/shutuba_*.jsonl")):
        for l in open(p, encoding="utf-8"):
            d = json.loads(l)
            for x in d["result"]:
                if x.get("waku"):
                    wk[(d["race_id"], x["umaban"])] = x["waku"]
    races = []
    for l in open(a.data, encoding="utf-8"):
        d = json.loads(l)
        rid = d["race_id"]
        if rid[:8] not in a.kaisai or d.get("surface") == "障":
            continue
        if not any(x.get("finish_pos") for x in d["result"]):
            continue
        races.append(d)
    races.sort(key=lambda d: d["race_id"])

    def key(d):
        s = d["surface"]
        if d["place"] == "京都" and s == "芝":
            c = course.get(d["race_id"])
            if d["distance"] in (1400, 1600):
                s += "外" if (c and "外" in c) else ("内" if c else "内外不明")
            else:
                s += "外" if d["distance"] in (1800, 2200, 2400, 3000, 3200) else "内"
        return d["place"], s

    groups = defaultdict(list)
    for d in races:
        groups[key(d)].append(d)
    for (place, surf), rs in groups.items():
        print(f"\n## {place} {surf}  ({len(rs)}鞍)")
        weeks = defaultdict(list)
        for d in rs:
            day = int(d["race_id"][8:10])
            weeks[day if a.by_day else (day + 1) // 2].append(d)
        for w in sorted(weeks) + ["計"]:
            ws = rs if w == "計" else weeks[w]
            st = defaultdict(Counter)
            for d in ws:
                n = d["field_size"]
                res = [x for x in d["result"] if x.get("finish_pos")]
                last = d["corners"][max(d["corners"])] if d.get("corners") else ""
                ln = lanes(last)
                fb = front_back(d.get("lap"), d["distance"])
                diff = fb[0] - fb[1] if fb else None
                pace = None if diff is None else ("H" if diff <= -1.0 else ("S" if diff >= 1.0 else "M"))
                st["pace"][pace] += 1
                for x in res:
                    top = x["finish_pos"] <= 3
                    cp = x.get("corner_pos") or []
                    b = band(cp[-1] if cp else None, n)
                    st["band_all"][b] += 1
                    lane = ln.get(x["umaban"])
                    st["lane_all"][lane] += 1
                    wa = wk.get((d["race_id"], x["umaban"])) or waku_of(x["umaban"], n)
                    wg = "1-3" if wa <= 3 else ("4-6" if wa <= 6 else "7-8")
                    st["waku_all"][wg] += 1
                    ar = x.get("agari_rank")
                    if ar and ar <= 3:
                        st["ag_all"]["1-3"] += 1
                    if top:
                        st["band"][b] += 1
                        st["lane"][lane] += 1
                        st["waku"][wg] += 1
                        st[f"band_{pace}"][b] += 1
                        if ar and ar <= 3:
                            st["ag"]["1-3"] += 1
                        if (x.get("popularity") or 0) >= 6:
                            st["ana"][b] += 1
                            st["ana_lane"][lane] += 1
                    if cp and cp[-1] == 1:
                        st["lead"][x["finish_pos"] if x["finish_pos"] <= 3 else "外"] += 1
                    if x["finish_pos"] == 1:
                        st["win_ag"][ar if ar and ar <= 3 else "4+"] += 1
                        st["win_band"][b] += 1
            T = sum(st["band"].values())
            f = lambda c, k: f"{c.get(k,0)}"
            print(f"[{('日' if a.by_day else '週') + str(w) if w != '計' else '計'}] {len(ws)}鞍 3着内{T}頭")
            print("  4角帯 3着内/出走: " + " ".join(f"{k}{st['band'][k]}/{st['band_all'][k]}" for k in "前中後")
                  + f"  勝ち馬 前{st['win_band']['前']} 中{st['win_band']['中']} 後{st['win_band']['後']}")
            print(f"  4角先頭: 1着{f(st['lead'],1)} 2着{f(st['lead'],2)} 3着{f(st['lead'],3)} 4着以下{f(st['lead'],'外')}")
            print("  括弧位置 3着内/出走: " + " ".join(f"{k}{st['lane'][k]}/{st['lane_all'][k]}" for k in ["最内", "内", "外", "単独"]))
            print("  枠 3着内/出走: " + " ".join(f"{k}枠{st['waku'][k]}/{st['waku_all'][k]}" for k in ["1-3", "4-6", "7-8"]))
            print("  ペース: " + " ".join(f"{k}{st['pace'][k]}" for k in "HMS") + "  | " +
                  " ".join(f"{k}:" + "/".join(str(st[f'band_{k}'][b]) for b in "前中後") for k in "HMS") + " (3着内 前/中/後)")
            print(f"  上がり1-3位 3着内{st['ag']['1-3']}/{st['ag_all']['1-3']}  勝ち馬の上がり "
                  + " ".join(f"{k}位{st['win_ag'][k]}" for k in [1, 2, 3, "4+"]))
            print("  6人気以下の3着内: 計" + str(sum(st["ana"].values())) + " 4角 " + " ".join(f"{k}{st['ana'][k]}" for k in "前中後")
                  + " | " + " ".join(f"{k}{st['ana_lane'][k]}" for k in ["最内", "内", "外", "単独"]))
        print("  時計(日 R 距離 クラス 馬場 勝ち時計 前3F-後3F):")
        for d in rs:
            w = next(x for x in d["result"] if x.get("finish_pos") == 1)
            fb = front_back(d.get("lap"), d["distance"])
            print(f"    {d['date'][5:]} {int(d['race_id'][10:]):>2}R {d['distance']} {(d.get('race_class') or '')[:6]:<6} "
                  f"{d.get('baba')} {w['time']} {fb[0]:.1f}-{fb[1]:.1f}" if fb else "")


if __name__ == "__main__":
    main()
