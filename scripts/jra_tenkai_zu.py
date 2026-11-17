"""中央競馬の展開図(HTML)を描く。scripts/ana/zu.py と同じ見た目。

出馬表(shutuba)の枠と、馬柱(shutuba_past)の近5走だけを使う。
レース当日以降の走は除外するので、レース後に実行しても結果は混ざらない。

    python3 scripts/jra_tenkai_zu.py --race-id 202605050211 --date 2026-11-08 \
        --out scripts/daily/zu_jra_20261108_tokyo11.html
    # 保存済みHTMLから
    python3 scripts/jra_tenkai_zu.py --shutuba s.html --past p.html --date 2026-11-08 \
        --place 東京 --race-no 11 --out out.html

図の読み方(zu.py と同じ約束)
  - 横 = 過去走の4コーナー位置の中央値。右が前。
  - 縦 = 重なりを避けて並べただけ。内外ではない(内外の帯は描かない)。
  - 青 ▲押し上げ = 1角→4角で位置を上げる馬 / ▼下がる = 下げる馬。
  - 終い1〜3位 = ag(同じ芝ダ・距離±400m の過去走の「その鞍の上がり順位」の中央値、近5走)が小さい順。
    距離帯の違う上がりは持ち込まない(CLAUDE.md ルール2)。その距離帯の走が無い馬は付けない。
    ※上がり順位は集めたデータ(--from-data)の agari_rank から引く。馬柱HTMLからは取れないので付かない。
  - 候補の札(notes/live/jra_course_pos.md の研究から。--no-kouho で消す)
      終い候補 = 芝16頭以上・予想4角が後ろ1/3(鞍の中の順位)・ag ≤ 3
      押上候補 = そのコースの「4角前1/3の3着内率」(models/course_pos.json)が 0.40 以上・gain ≥ 0.20
  - ペース = core/tenkai.forecast の pace_index(逃げ候補・先行勢・距離・単騎逃げ)。
"""

from __future__ import annotations

import argparse
import html as H
import re
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "ana"))

from nankeiba.core.interval import RunRecord
from nankeiba.core import tenkai as tk
from nankeiba.scraping.race_id import place_of
from horse_svg import HORSE, CHEV  # noqa: E402

SHUTUBA_URL = "https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
PAST_URL = "https://race.netkeiba.com/race/shutuba_past.html?race_id={race_id}"

WAKU = {1: ("#ffffff", "#111"), 2: ("#1b1b1b", "#fff"), 3: ("#e03a30", "#fff"),
        4: ("#2d6fd0", "#fff"), 5: ("#f2d231", "#111"), 6: ("#2f9e57", "#fff"),
        7: ("#f08a24", "#111"), 8: ("#f29ab8", "#111")}
WID, LANE, PAD, GAP = 900, 88, 64, 134
WEEK = "MON TUE WED THU FRI SAT SUN".split()


def _clean(cell: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", cell).replace("&nbsp;", " "))


def _time_sec(s: str) -> float | None:
    m = re.match(r"(?:(\d+):)?(\d+)\.(\d)", s)
    if not m:
        return None
    return int(m.group(1) or 0) * 60 + int(m.group(2)) + int(m.group(3)) / 10


def parse_past(html: str, race_date: str) -> dict[int, dict]:
    """馬柱 → {馬番: {name, runs:[{date,place,surface,dist,n,fin,corner,agari,time,baba}]}}"""
    out: dict[int, dict] = {}
    for tr in re.findall(r'<tr class="HorseList.*?</tr>', html, re.S):
        um = (re.search(r'<td class="Waku\d*[^"]*"[^>]*>.*?</td>\s*<td[^>]*>\s*(\d+)', tr, re.S)
              or re.search(r'class="Umaban[^"]*"[^>]*>\s*(\d+)', tr))
        h = re.search(r'/horse/\w+[^>]*>([^<]+)<', tr)
        if not um or not h:
            continue
        runs = []
        for _, cell in re.findall(r'<td class="(Past[^"]*)"[^>]*>(.*?)</td>', tr, re.S):
            x = _clean(cell)
            d = re.search(r"(\d{4})\.(\d{2})\.(\d{2})\s*(\S+?)\s", x)
            if not d:
                continue
            date = f"{d.group(1)}-{d.group(2)}-{d.group(3)}"
            if date >= race_date:
                continue  # 当日以降(=結果)は使わない
            fin = re.search(r"\|\s*(\d+)\s*\|", x[d.end():])
            cs = re.search(r"(芝|ダ|障)(\d{3,4})\S*\s+([\d:.]+)", x)
            n = re.search(r"(\d+)頭", x)
            if not (fin and cs and n):
                continue
            corner = re.search(r"\|\s*([\d\-]+)\s+\((\d+\.\d)\)", x)
            baba = re.search(r"\|\s*(良|稍|重|不)\s*\|", x)
            runs.append({
                "date": date, "place": re.sub(r"\d", "", d.group(4)),
                "surface": cs.group(1), "dist": int(cs.group(2)), "time": _time_sec(cs.group(3)),
                "n": int(n.group(1)), "fin": int(fin.group(1)),
                "corner": [int(c) for c in corner.group(1).split("-")] if corner else [],
                "agari": float(corner.group(2)) if corner else None,
                "baba": baba.group(1) if baba else None,
            })
        runs.sort(key=lambda r: r["date"], reverse=True)
        out[int(um.group(1))] = {"name": h.group(1).strip(), "runs": runs}
    return out


def parse_class(html: str) -> dict:
    """出馬表の RaceData02 とグレードのアイコンから クラス・年齢条件・グレード を取る。"""
    import unicodedata
    m = re.search(r'class="RaceData02">(.*?)</div>', html, re.S)
    t = unicodedata.normalize("NFKC", _clean(m.group(1))) if m else ""
    typ = re.search(r"(\d歳以上|\d歳)", t)
    cls = re.search(r"(新馬|未勝利|\d勝クラス|オープン)", t)
    g = re.search(r"Icon_GradeType([123])\b", html)
    return {"race_type": typ.group(1) if typ else None, "race_class": cls.group(1) if cls else None,
            "grade": ("G" + g.group(1)) if g else None}


def waku_of(umaban: int, n: int) -> int:
    """JRAの枠順: 8頭以下は馬番=枠。9頭以上は各枠 n//8 頭、余りは外の枠(8枠,7枠,…)に1頭ずつ足す。"""
    if n <= 8:
        return umaban
    counts = [n // 8] * 8
    for i in range(n % 8):
        counts[7 - i] += 1
    k = 0
    for w, c in enumerate(counts, 1):
        k += c
        if umaban <= k:
            return w
    return 8


_ROWS_CACHE: dict = {}
_PACE_CACHE: dict = {}


def _is_jump(d: dict) -> bool:
    try:
        from nankeiba.scraping.jra_official import is_jump
    except ImportError:   # 取り込み側が無い環境でも同じ判定
        def is_jump(race_type, name="", grade=""):
            return ("障害" in (race_type or "") or "ジャンプ" in (name or "") or "障害" in (name or "")
                    or "J・G" in (grade or "") or "J.G" in (grade or ""))
    return is_jump(d.get("race_type"), d.get("name"), d.get("grade"))


def load_rows(data_path: str) -> list:
    """JSONL を読む。障害の鞍は surface を「障」にそろえる。
    取り込みの時期や出馬表によって障害が「芝」のまま入っていることがあり、
    図は surface が同じ過去走を拾うので、食い違うと位置が変わる。"""
    import json
    if data_path not in _ROWS_CACHE:
        rows = [json.loads(l) for l in open(data_path, encoding="utf-8") if l.strip()]
        for d in rows:
            if d.get("surface") != "障" and _is_jump(d):
                d["surface"] = "障"
        _ROWS_CACHE[data_path] = rows
    return _ROWS_CACHE[data_path]


def from_data(data_path: str, race_id: str):
    """集めたデータ(jra_harvest / jra_official_harvest の JSONL)だけで、その鞍の出走馬と過去走を組み立てる。

    ネットに取りに行かない。過去走はその鞍の日付より前の走だけ(結果は使わない)。
    返り値: (past, waku, name, info, klass, date, place)  ※ past は parse_past と同じ形
    """
    rows = load_rows(data_path)
    me = next(d for d in rows if d["race_id"] == race_id)
    hist = {}
    for d in sorted(rows, key=lambda d: (d["date"], d["race_id"])):
        if d["date"] >= me["date"]:
            break
        for x in d["result"]:
            hist.setdefault(x["horse_id"], []).append({
                "race_id": d["race_id"], "date": d["date"], "place": d["place"], "surface": d.get("surface"), "dist": d["distance"],
                "time": x.get("time"), "n": d["field_size"], "fin": x["finish_pos"],
                "corner": x.get("corner_pos") or [], "agari": x.get("agari"), "baba": d.get("baba"),
                "agari_rank": x.get("agari_rank")})
    past = {}
    for x in me["result"]:
        hs = sorted(hist.get(x["horse_id"], []), key=lambda r: r["date"], reverse=True)
        past[x["umaban"]] = {"name": x["horse_name"], "runs": hs[:5], "hist": hs}   # hist は終い(ag)用
    waku = {x["umaban"]: x.get("waku") or waku_of(x["umaban"], me["field_size"]) for x in me["result"]}
    info = f"{me.get('surface')}{me['distance']}m {me.get('baba') or ''}"
    klass = {"race_class": me.get("race_class"), "race_type": me.get("race_type"), "grade": me.get("grade")}
    jockeys = {x["umaban"]: x.get("jockey") for x in me["result"]}
    global EXTRA, DAY_SHAPE, ME_RACE, ME_PAST
    ME_RACE, ME_PAST = me, {x["umaban"]: hist.get(x["horse_id"], []) for x in me["result"]}
    prev = [d for d in rows if d["date"] == me["date"] and d["place"] == me["place"]
            and d.get("surface") == me.get("surface") and d["race_id"] < race_id]
    frs = []
    for d in prev:
        top = [x for x in d["result"][:3] if x.get("corner_pos")]
        if len(top) == 3 and d["field_size"] > 1:
            frs.append(st.mean((x["corner_pos"][-1] - 1) / (d["field_size"] - 1) for x in top))
    DAY_SHAPE = (st.mean(frs), len(frs)) if len(frs) >= 2 else None
    EXTRA = {x["umaban"]: {"kinryo": x.get("kinryo"), "weight": x.get("weight"), "dw": x.get("weight_diff")}
             for x in me["result"]}
    return past, waku, me.get("name") or "", info, klass, me["date"], me["place"], jockeys


def parse_jockeys(html: str) -> dict[int, str]:
    """出馬表 → 馬番 → 騎手名"""
    out = {}
    for tr in re.findall(r'<tr class="HorseList.*?</tr>', html, re.S):
        u = re.search(r'<td class="Umaban\d*[^"]*"[^>]*>\s*(\d+)', tr)
        j = re.search(r'/jockey/[^>]*>\s*([^<]+?)\s*<', tr)
        if u and j:
            out[int(u.group(1))] = j.group(1)
    return out


def parse_shutuba(html: str) -> tuple[dict[int, int], str, str]:
    """出馬表 → (馬番→枠, レース名, 条件文字列)"""
    waku = {}
    for tr in re.findall(r'<tr class="HorseList.*?</tr>', html, re.S):
        w = re.search(r'<td class="Waku(\d)', tr)
        u = re.search(r'<td class="Umaban\d*[^"]*"[^>]*>\s*(\d+)', tr)
        if w and u:
            waku[int(u.group(1))] = int(w.group(1))
    t = re.search(r"<title>(.*?)</title>", html, re.S)
    name = re.sub(r"\s*出馬表.*", "", t.group(1)).strip() if t else ""
    m = re.search(r'class="RaceData01">(.*?)</div>', html, re.S)
    info = _clean(m.group(1)) if m else ""
    return waku, name, info


def build(past: dict, waku: dict, *, place: str, dist: int, surface: str, baba: str | None, jockeys=None):
    field = {u: [RunRecord(date=r["date"], place=r["place"], distance=r["dist"],
                           field_size=r["n"], finish_pos=r["fin"], surface=r["surface"],
                           baba=r["baba"], corner_pos=r["corner"]) for r in v["runs"]]
             for u, v in past.items()}
    fc = tk.forecast(field, place=place, distance=dist, surface=surface)

    rows = []
    for u, v in past.items():
        c4 = [(r["corner"][-1] - 1) / max(1, r["n"] - 1) for r in v["runs"] if r["corner"]]
        c1 = [(r["corner"][0] - 1) / max(1, r["n"] - 1) for r in v["runs"] if r["corner"]]
        ag = [r["agari"] for r in v["runs"]
              if r["agari"] and r["surface"] == "芝" and r["dist"] >= 1800]
        # 前半速度[m/s] = (距離−600) / (走破−上がり)。同じ馬場・距離±400m の走だけ
        es = [(r["dist"] - 600) / (r["time"] - r["agari"]) for r in v["runs"]
              if r["time"] and r["agari"] and r["surface"] == surface
              and abs(r["dist"] - dist) <= 400]
        rows.append({
            "ub": u, "name": v["name"], "waku": waku.get(u), "jockey": (jockeys or {}).get(u),
            "pos": 1 - st.median(c4) if c4 else None,         # 1=前
            "gain": (st.median(c1) - st.median(c4)) if c4 else None,
            "l": st.median(ag) if ag else None,
            "e": st.median(es) if es else None,
            "adv": fc.advantage.get(u, 0.0), "style": fc.styles[u].style,
            "nige": fc.styles[u].nige_rate, "last": v["runs"][0] if v["runs"] else None,
        })
    # 終い: 同じ芝ダ・距離±400m の過去走の上がり順位の中央値(近5走)。jra_oshiage_kensho.py の ag と同じ
    for r in rows:
        v = past[r["ub"]]
        ags = [x["agari_rank"] for x in (v.get("hist") or v["runs"])
               if x.get("agari_rank") and x.get("surface") == surface and abs(x["dist"] - dist) <= 400][:5]
        r["ag"], r["nag"] = (st.median(ags) if ags else None), len(ags)
    rk = {r["ub"]: i + 1 for i, r in enumerate(sorted([r for r in rows if r["ag"] is not None],
                                                     key=lambda r: (r["ag"], -r["nag"], r["ub"])))}
    apply_position_model(rows, field, fc, dist=dist, surface=surface)
    mark_kouho(rows, place=place, dist=dist, surface=surface)
    return fc, rows, rk


KOUHO_OFF = False   # --no-kouho


def mark_kouho(rows, *, place, dist, surface):
    """候補の札 r["kouho"](notes/live/jra_course_pos.md の 2・3)。予想(位置・ペース)は変えない。
    終い候補: 芝16頭以上で、予想4角(pos)の鞍の中の順位が後ろ1/3、かつ ag ≤ 3。そのうち ag の小さい順に最大2頭
              (同値は nag の多い順)。
    押上候補: そのコースの前1/3の3着内率 ≥ 0.40(前で決まりやすい場)で gain ≥ 0.20。"""
    known = sorted([r for r in rows if r.get("pos") is not None], key=lambda r: -r["pos"])
    nk = len(known)
    third = {r["ub"]: (i / max(1, nk - 1)) for i, r in enumerate(known)} if nk >= 3 else {}
    try:
        from jra_course_pos import lookup
        _, cs = lookup(place, surface, dist)
    except Exception:  # noqa: BLE001  (表が無い環境では押上候補を出さない)
        cs = None
    front3 = cs["front3"] if cs else None
    # 終い候補は 1鞍に最大2頭: 後ろ1/3 かつ ag≤3 の馬を ag の小さい順(同値は nag の多い順→馬番)に2頭まで。
    # 3年分(芝16頭以上・後ろ1/3、584鞍)で ag≤3 全部: 1.36頭/鞍・3着内21%、上位2頭: 1.10頭/鞍・23%。
    shimai = []
    if surface == "芝" and len(rows) >= 16:
        shimai = sorted([r for r in rows if third.get(r["ub"], 0) > 2 / 3
                         and r.get("ag") is not None and r["ag"] <= 3],
                        key=lambda r: (r["ag"], -(r.get("nag") or 0), r["ub"]))[:2]
    shimai = {r["ub"] for r in shimai}
    for r in rows:
        q = third.get(r["ub"])
        r["_third"] = None if q is None else ("前" if q < 1 / 3 else "中" if q <= 2 / 3 else "後")
        r["_front3"] = front3
        k = []
        if r["ub"] in shimai:
            k.append("終い候補")
        if front3 is not None and front3 >= 0.40 and r.get("gain") is not None and r["gain"] >= 0.20:
            k.append("押上候補")
        r["kouho"] = k


POSITION_MODEL = ROOT / "models" / "position_model.json"
JOCKEY_STATS = ROOT / "models" / "jockey_stats.json"
_JK = None


def jockey_stat(name):
    """騎手の集計(scripts/jra_jockey.py)を引く。略名・頭文字つきの名前にも当てる。無ければ None。"""
    global _JK
    import json
    import unicodedata
    if _JK is None:
        _JK = json.load(open(JOCKEY_STATS))["jockeys"] if JOCKEY_STATS.exists() else {}
    if not name:
        return None
    n = re.sub(r"[\s▲△☆◇★▽]", "", unicodedata.normalize("NFKC", name))
    if n in _JK:
        return dict(_JK[n], name=n)
    c = [k for k in _JK if k.startswith(n) or k.split(".")[-1] == n or n.startswith(k)]
    return dict(_JK[c[0]], name=c[0]) if len(c) == 1 else None


_GB: dict = {}


def _lgbm(M, lab):
    if lab + "_lgbm" not in M:
        return None
    if lab not in _GB:
        try:
            import lightgbm as lgb
            _GB[lab] = lgb.Booster(model_str=M[lab + "_lgbm"])
        except ImportError:
            _GB[lab] = None
    return _GB[lab]


def apply_position_model(rows, field, fc, *, dist, surface):
    """学習した4角位置モデル(scripts/jra_position_model2.py)で前後の想定を置き換える。

    検証: 4角の順位相関 +0.434(中央値) → +0.462。騎手の癖・ペース想定はここでは 0 扱い
    (騎手名を出馬表から取っていないため。係数への影響は小さい)。
    """
    import json
    if not POSITION_MODEL.exists():
        return
    M = json.load(open(POSITION_MODEL))
    if not M.get("4角"):
        return
    norm = lambda x, i: (x.corner_pos[i] - 1) / max(1, x.field_size - 1)  # noqa: E731
    for r in rows:
        past = field.get(r["ub"], [])
        runs = [x for x in past if x.corner_pos and x.field_size > 1]
        if not runs:
            continue
        sp = fc.styles[r["ub"]]
        sim = [x for x in runs if x.surface == surface and abs(x.distance - dist) <= 200]
        last = past[0]
        early = sp.early_or(0.5)
        f = {"1": 1.0, "early": early, "known": 1.0, "nige": sp.nige_rate,
             "med_c4": st.median(norm(x, -1) for x in runs),
             "sim_c1": st.median(norm(x, 0) for x in sim) if sim else early,
             "sim_c4": st.median(norm(x, -1) for x in sim) if sim else early,
             "has_sim": 1.0 if sim else 0.0,
             "dist_diff": (dist - last.distance) / 1000,
             "surf_change": 1.0 if last.surface and last.surface != surface else 0.0,
             "gain": st.median(norm(x, 0) - norm(x, -1) for x in runs),
             "jk_bias": (jockey_stat(r.get("jockey")) or {}).get("front_bias", 0.0), "jk_change": 0.0,
             "gate": (r["ub"] - 1) / max(1, len(rows) - 1),
             "gate_x_short": ((r["ub"] - 1) / max(1, len(rows) - 1)) * (1.0 if dist <= 1400 else 0.0),
             "pace": 0.0, "pace_x_early": 0.0}
        ss = [x for x in past if x.surface == surface]
        sp_ss = tk.style_profile(ss)
        sp_sim = tk.style_profile([x for x in ss if abs(x.distance - dist) <= 300])
        chg = 1.0 if last.surface and last.surface != surface else 0.0
        f.update({"early_ss": sp_ss.early_or(early), "has_ss": 1.0 if sp_ss.early is not None else 0.0,
                  "early_ss_x_chg": sp_ss.early_or(early) * chg,
                  "early_sim": sp_sim.early_or(early), "has_sim2": 1.0 if sp_sim.early is not None else 0.0,
                  "long_x_sim": sp_sim.early_or(early) * (1.0 if dist >= 2000 else 0.0), "n_runs": min(len(runs), 5) / 5})
        for lab, key in (("1角", "_p1"), ("4角", "_p4")):
            gb = _lgbm(M, lab)
            if gb is not None:   # LightGBM があれば非線形(検証 1角+0.536・4角+0.494、線形より+0.006)
                import numpy as np
                r[key] = float(gb.predict(np.array([[f.get(k, 0.0) for k in M[lab + "_lgbm_features"]]]))[0])
            else:
                m = M.get(lab) or M["4角"]
                r[key] = sum(w * f.get(k, 0.0) for k, w in zip(m["features"], m["coef"]))
    # 学習モデルの値は平均へ縮むので、そのままでは横に広がらない
    # 値の差(固まり具合)は残して 1(先頭)〜0(最後方) に引き伸ばす
    for key, out in (("_p1", "pos1"), ("_p4", "pos")):
        vals = [r[key] for r in rows if key in r]
        if not vals:
            continue
        lo, hi = min(vals), max(vals)
        for r in rows:
            if key in r:
                r[out] = 1 - (r[key] - lo) / max(1e-9, hi - lo)
    for r in rows:
        if "pos1" in r:
            r["pos3"] = (r["pos1"] + r["pos"]) / 2
    apply_hana_model(rows, field, fc, dist=dist, surface=surface)


def apply_hana_model(rows, field, fc, *, dist, surface):
    """ハナ(1角先頭)専用モデル(scripts/jra_hana_kenkyu.py)のスコアを r["hana"] に入れる。

    検証(2,846鞍): 1番手的中 31.8%(隊列の1番手 29.3%)、上位3頭に入る 64.3%。
    1番手と2番手の差が大きい鞍は 40%、小さい鞍は 23%。
    """
    import json
    path = ROOT / "models" / "hana_model.json"
    if not path.exists():
        return
    M = json.load(open(path))
    n = len(rows)
    for r in rows:
        past = field.get(r["ub"], [])
        runs = [x for x in past if x.corner_pos and x.field_size > 1]
        if not runs:
            continue
        sp = fc.styles[r["ub"]]
        sim = [x for x in runs if x.surface == surface and abs(x.distance - dist) <= 200]
        gate = (r["ub"] - 1) / max(1, n - 1)
        f = {"1": 1.0, "nige": sp.nige_rate, "early": sp.early_or(0.5),
             "min_c1": min((x.corner_pos[0] - 1) / (x.field_size - 1) for x in runs),
             "last_c1": (runs[0].corner_pos[0] - 1) / (runs[0].field_size - 1),
             "last_lead": 1.0 if runs[0].corner_pos[0] == 1 else 0.0,
             "sim_nige": (sum(x.corner_pos[0] == 1 for x in sim) / len(sim)) if sim else sp.nige_rate,
             "jk_bias": (jockey_stat(r.get("jockey")) or {}).get("front_bias", 0.0), "gate": gate, "gate_x_short": gate * (1.0 if dist <= 1400 else 0.0),
             "dist_diff": (dist - past[0].distance) / 1000, "n_runs": min(len(runs), 5) / 5, "field": n / 18}
        r["hana"] = sum(w * f[k] for k, w in zip(M["features"], M["coef"]))
        r["_hf"] = f
    # 相手との比較 + LightGBM(scripts/jra_hana_kenkyu.py、検証 1番手 31.8→34.2%)
    pg = ROOT / "models" / "hana_model_lgbm.json"
    hr = [r for r in rows if "_hf" in r]
    if not (pg.exists() and len(hr) >= 2):
        return
    try:
        import lightgbm as lgb
        import numpy as np
    except ImportError:
        return
    G = json.load(open(pg))
    for key in ("nige", "sim_nige", "min_c1", "early"):
        hi = key in ("nige", "sim_nige")
        vals = sorted((r["_hf"][key] for r in hr), reverse=hi)
        for r in hr:
            v = r["_hf"][key]
            r["_hf"][key + "_rk"] = vals.index(v) / max(1, len(vals) - 1)
            others = [o["_hf"][key] for o in hr if o is not r]
            best = (max(others) if hi else min(others)) if others else v
            r["_hf"][key + "_gap"] = (v - best) if hi else (best - v)
    nl = sum(1 for r in hr if r["_hf"]["nige"] >= 0.3)
    for r in hr:
        r["_hf"]["n_leaders"] = nl / 5
    gb = lgb.Booster(model_str=G["lgbm"])
    pv = gb.predict(np.array([[r["_hf"].get(k, 0.0) for k in G["features2"]] for r in hr]))
    for r, v in zip(hr, pv):
        r["hana"] = float(v)


def learned_pace(data_path: str, before: str, *, place, dist, surface, n, baba=None, race_id=None, klass=None):
    """前後半差[秒]の想定と確度。before より前の鞍だけで作る(当日の前のレースは使う)。

    scripts/jra_pace_model.py の比較で最良だった「コース(場×芝ダ×距離)平均 + 馬場 + 当日のずれ」。
    検証(706鞍): 3区分の的中 64%、大外れ(スロー⇔ハイ) 2.8%。
    確度は想定値が区分の境目からどれだけ離れているか: 高(≥0.99秒)的中84% / 中(≥0.39秒)59% / 低 50%。
    返り値: (想定差, 学習鞍数, 確度, (ハイ境, スロー境))
    """
    import json
    import statistics as st_
    sys.path.insert(0, str(ROOT / "scripts"))
    from jra_pace_model import PaceModel
    from nankeiba.scraping.db_race import pace_of
    rows = [d for d in load_rows(data_path)
            if d.get("surface") in ("芝", "ダ") and pace_of(d.get("lap") or [], d["distance"])]
    key = (data_path, before)
    if key not in _PACE_CACHE:   # 1日分を描くときに同じモデルを何度も作らない
        tr = [d for d in rows if d["date"] < before]
        _PACE_CACHE[key] = (PaceModel().fit(tr), sorted(pace_of(d["lap"], d["distance"])["diff"] for d in tr), len(tr))
    m, v, ntr = _PACE_CACHE[key]
    tr = range(ntr)
    q = (v[len(v) // 3], v[2 * len(v) // 3])
    me = {"place": place, "distance": dist, "surface": surface, "field_size": n, "baba": baba, **(klass or {})}
    pred = m.predict(me)
    prev = [pace_of(d["lap"], d["distance"])["diff"] - m.predict(d) for d in rows
            if d["date"] == before and d["place"] == place and d["surface"] == surface
            and race_id and d["race_id"] < race_id]
    if prev:   # 当日の前のレースの流れ(scripts/jra_toujitsu.py: ペースは2割足すのが最適、効果は小さい)
        pred += _toujitsu_weight("dp", 0.2) * st_.mean(prev)
    margin = min(abs(pred - q[0]), abs(pred - q[1]))
    conf = "高" if margin >= 0.99 else ("中" if margin >= 0.39 else "低")
    est = estimate_times(rows, me, before, race_id)
    return pred, len(tr), conf, q, est


def pace_lgbm_diff(data_path, before, fc, base):
    """ペースの LightGBM(scripts/jra_pace_lgbm.py、検証 3区分 64.6→65.7%・ダ 58.4→60.3%)で前後半差を出す。
    材料が揃う --from-data のときだけ。使えなければ None。"""
    import json
    path = ROOT / "models" / "pace_lgbm.json"
    if ME_RACE is None or not path.exists():
        return None
    try:
        import lightgbm as lgb
        import numpy as np
    except ImportError:
        return None
    sys.path.insert(0, str(ROOT / "scripts"))
    from jra_wind_kenkyu import wind_at
    from jra_class_kenkyu import cls_x
    from nankeiba.core import course as cs
    from nankeiba.scraping.db_race import pace_of
    M = json.load(open(path))
    reg = lgb.Booster(model_str=M["reg"])
    d = ME_RACE
    pm = _PACE_CACHE[(data_path, before)][0]
    rows = {r["race_id"]: r for r in load_rows(data_path)}

    def resid(rid):
        r = rows.get(rid)
        pc = pace_of(r.get("lap") or [], r["distance"]) if r else None
        return (pc["diff"] - pm.predict(r)) if pc else None

    n = d["field_size"]
    known = [sp for sp in fc.styles.values() if sp.early is not None]
    lr = []
    for u in fc.order[:3]:
        rs = [resid(x["race_id"]) for x in ME_PAST.get(u, []) if x.get("corner") and x["corner"][0] <= 2 and x.get("race_id")]
        rs = [x for x in rs if x is not None]
        if rs:
            lr.append(st.mean(rs[-3:]))
    day = [resid(r["race_id"]) for r in rows.values() if r["date"] == d["date"] and r["place"] == d["place"]
           and r.get("surface") == d["surface"] and r["race_id"] < d["race_id"]]
    day = [x for x in day if x is not None]
    if not day:   # 前日に描くときは同じ開催の前の開催日のずれ
        day = [x for x in (resid(r["race_id"]) for r in _meeting_rows(list(rows.values()), d["place"], d["surface"], d["date"])) if x is not None]
        fc.meeting_shift = st.mean(day) if day else None
    w = wind_at(d["place"], d["date"], int(d["race_id"][-2:])) or (0.0, 0.0, 0.0)
    PL = ["札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"]
    base = pm.predict(d)   # 学習と同じく、当日のずれを足す前のコース平均の想定
    x = [base, d["distance"] / 1000, n / 18, 1.0 if d["surface"] == "芝" else 0.0,
         {"良": 0, "稍": 1, "重": 2, "不": 3}.get(d.get("baba") or "良", 0), cs.front_bias(d["place"], d["surface"]),
         PL.index(d["place"]) if d["place"] in PL else -1, int(d["date"][5:7]),
         sum(sp.nige_rate for sp in known), sum(1 for sp in known if sp.early <= 0.25) / max(1, n),
         len(known) / max(1, n), st.mean(lr) if lr else 0.0, len(lr),
         st.mean(day) if day else 0.0, len(day), w[0], w[1], w[2], int(d["race_id"][-2:])] + cls_x(d)
    rp = ROOT / "models" / "pace_lgbm_rel.json"
    if rp.exists():   # このコースにしては速いか遅いか(決着の形と結びつくのはこちら。jra_pace_teigi.py)
        try:
            from jra_wind_choku import head_cross
            hc = head_cross(d["place"], d["date"], int(d["race_id"][-2:]))
            R_ = json.load(open(rp))
            xr = list(x)
            xr[13] = st.mean(day) if day else 0.0   # 当日のずれは同じ定義(コース平均との差)
            pr = lgb.Booster(model_str=R_["clf"]).predict(np.array([xr + [hc[0] if hc else 0.0, hc[1] if hc else 0.0]]))[0]
            fc.rel = (["遅め", "平均", "速め"][int(pr.argmax())], float(pr.max()), [float(v) for v in pr])
        except Exception:  # noqa: BLE001
            fc.rel = None
    return float(reg.predict(np.array([x]))[0])


def _toujitsu_weight(key, default):
    import json
    p = ROOT / "models" / "toujitsu_weight.json"
    return json.load(open(p)).get(key, default) if p.exists() else default


BASE_BABA = None  # --base-baba: 時計の基準にする馬場(例 稍)。ユーザー指定 2026-11-14「雨降る」「先週の稍重 1:10.3」
BASE_DAY = None   # --base-day: 時計の基準にする開催日(例 前日の良馬場だけ)。ユーザー指定 2026-11-14「昨日の時計で想定しよう」
_UNSET = object()
BASE_BABA_DIRT = _UNSET  # --base-baba-dirt: ダートの鞍の基準の馬場(指定が無ければ BASE_BABA)
BASE_DAY_DIRT = _UNSET   # --base-day-dirt: ダートの鞍の基準の開催日(指定が無ければ BASE_DAY)


def _base_for(surface):
    """その芝ダの時計の基準(開催日の集合, 馬場の集合)。ダートは --base-*-dirt があればそちら。"""
    if surface == "ダ":
        return (BASE_DAY if BASE_DAY_DIRT is _UNSET else BASE_DAY_DIRT,
                BASE_BABA if BASE_BABA_DIRT is _UNSET else BASE_BABA_DIRT)
    return BASE_DAY, BASE_BABA


def _meeting_rows(rows, place, surface, date):
    """同じ開催の、前の開催日の同じ場・同じ芝ダの鞍(8日以内)。--base-day があればその日だけ。
    ダートの鞍は --base-day-dirt / --base-baba-dirt(無ければ芝と同じ値)。"""
    import datetime as dt_
    d0 = dt_.date.fromisoformat(date)
    bday, bbaba = _base_for(surface)
    return [d for d in rows if d.get("place") == place and d.get("surface") == surface
            and d.get("lap") and d["date"] < date and (bday is None or d["date"] in bday)
            and (bbaba is None or d.get("baba") in bbaba)
            and (d0 - dt_.date.fromisoformat(d["date"])).days <= 8]


def estimate_times(rows, me, before, race_id):
    """推定 前半3F・後半3F・タイム(scripts/jra_time_model.py の係数)。検証の平均誤差 0.65/0.65/1.22秒。"""
    import json
    import statistics as st_
    path = ROOT / "models" / "time_model.json"
    if not path.exists():
        return None
    sys.path.insert(0, str(ROOT / "scripts"))
    from jra_time_model import TimeModel, target
    M = json.load(open(path))
    out = {}
    for k in ("front3", "last3", "time"):
        m = TimeModel(k)
        m.w, m.cell, m.wb, m.wc = M[k]["w"], M[k]["cell"], M[k]["wb"], M[k].get("wc")
        v = m.predict(me)
        prev = [target(d, k) - m.predict(d) for d in rows
                if d["date"] == before and d["place"] == me["place"] and d["surface"] == me["surface"]
                and race_id and d["race_id"] < race_id and d["result"][0].get("time")]
        same = [d for d in _meeting_rows(rows, me["place"], me["surface"], before)
                if d.get("distance") == me.get("distance") and d["result"][0].get("time")]
        if len(same) >= 3 and "laps" not in out:   # ラップ想定 = 同じ開催・同じ距離の各ハロンの中央値
            nl = min(len(d.get("lap") or []) for d in same)
            if nl:
                out["laps"] = [st_.median(d["lap"][i] for d in same) for i in range(nl)]
        if len(same) >= 3:   # 同じ開催・同じ距離が3鞍以上 → その実際の時計(中央値)をそのまま。クラスは見ない
            out[k] = st_.median(target(d, k) for d in same)   # (福島芝1200 2026-11: 2歳未勝利〜OPで1:09.8〜1:10.7)
            continue
        if not prev:   # 当日の前の鞍が無い(前日に描く)ときは、同じ開催の前の開催日のずれ(ユーザー指摘 2026-11-13)
            prev = [target(d, k) - m.predict(d) for d in _meeting_rows(rows, me["place"], me["surface"], before)
                    if d["result"][0].get("time")]
        if prev:   # 当日の馬場の速さ(jra_toujitsu.py: 時計は6割足すと後半の誤差 1.30→1.13秒)
            v += _toujitsu_weight("dt", M.get("day_weight", 0.5)) * st_.mean(prev)
        out[k] = v
    return out


def apply_learned_pace(fc, rows, diff: float, *, q=(-0.5, 0.5), adv_scale: float = 0.6, lone_bonus: float = 0.15):
    """学習したペースで fc のペース表示と展開利を置き換える。

    コース形状は条件モデルに入っているので、展開利は「ペースの傾き」だけで決める
    (前後半差 + = 前半ゆったり = 前の馬に向く)。
    """
    fc.diff_pred = diff
    fc.pace_index = max(-1.0, min(1.0, -diff / 2))
    fc.pace = "ハイ" if diff < q[0] else ("スロー" if diff > q[1] else "ミドル")
    tilt = -fc.pace_index
    for u, sp in fc.styles.items():
        adv = adv_scale * (0.5 - sp.early_or()) * tilt
        if u == fc.lone_leader:
            adv += lone_bonus
        fc.advantage[u] = adv
    for r in rows:
        r["adv"] = fc.advantage.get(r["ub"], 0.0)


LATERAL_MODEL = ROOT / "models" / "lateral_model.json"   # scripts/jra_tairetsu2d.py の学習結果(係数のみ)


def lateral_layout(rows, fc, n, *, band=0.10, min_gap=104, key="pos"):
    """2次元の隊列: 横=前後の想定、縦=内外の想定(上が内)。

    内外は scripts/jra_tairetsu2d.py で学習した「4角で併走組の外側になる度合い」
    (検証: 相関 +0.43、効いているのはほぼ馬番)。前後の想定が band 以内の馬を同じ組にして、
    組の中を内→外に並べる。組どうしは min_gap px 以上あける(順序は保つ)。
    返り値: [(row, x, 内からの順0始まり)], 組の数
    """
    import json
    coef = json.load(open(LATERAL_MODEL))
    w = dict(zip(coef["features"], coef["coef"]))
    hs = sorted([r for r in rows if r.get(key) is not None], key=lambda r: -r[key])
    out = {}
    for r in hs:
        f = {"1": 1.0, "gate": (r["ub"] - 1) / max(1, n - 1), "out_rate": 0.43, "n_lat": 0.0,
             "nige": fc.styles[r["ub"]].nige_rate, "front": r[key], "field": n / 18}
        out[r["ub"]] = sum(w[k] * f[k] for k in w)
        # 騎手の外出し癖(jra_jockey.py の outer_rate、全体平均43%)。検証で 馬番だけ +0.418 → +0.429
        js = jockey_stat(r.get("jockey"))
        if js:
            out[r["ub"]] += 0.74 * (js["outer_rate"] - 0.431)
        r["outer_score"] = out[r["ub"]]
    groups, cur, head = [], [], None
    for r in hs:
        if head is None or head - r[key] <= band:
            cur.append(r)
            head = r[key] if head is None else head
        else:
            groups.append(cur)
            cur, head = [r], r[key]
    if cur:
        groups.append(cur)
    xs, prev = [], None
    for g in groups:
        x = PAD + g[0][key] * (WID - 2 * PAD)
        if prev is not None:
            x = min(x, prev - min_gap)
        xs.append(x)
        prev = x
    if xs and xs[-1] < PAD:  # はみ出したら全体を縮める(順序と間隔の比は保つ)
        hi = xs[0]
        xs = [PAD + (x - xs[-1]) * (hi - PAD) / max(1, hi - xs[-1]) for x in xs]
    cells = []
    for g, x in zip(groups, xs):
        for li, r in enumerate(sorted(g, key=lambda r: out[r["ub"]])):
            r["lane"] = li + 1
            cells.append((r, x, li))
    return cells, len(groups)


def render_race(rno, name, dist, surface, baba, n, fc, rows, rk) -> str:
    hs = sorted([r for r in rows if r["pos"] is not None], key=lambda r: -r["pos"])
    two_d = LATERAL_MODEL.exists()
    stages = two_d and all("pos1" in r for r in rows if r["pos"] is not None)
    if two_d:
        cells, _ = lateral_layout(rows, fc, n)
        NL = max(1, max((lane for _, _, lane in cells), default=0) + 1)
    else:
        cells, lanes = [], []
        for r in hs:
            x = PAD + r["pos"] * (WID - 2 * PAD)
            for i, last in enumerate(lanes):
                if x < last - GAP:
                    lanes[i] = x
                    cells.append((r, x, i))
                    break
            else:
                lanes.append(x)
                cells.append((r, x, len(lanes) - 1))
        NL = max(1, len(lanes))
    hh = []
    for r, x, lane in cells:
        col, cc, t = "#d8c7ae", "#b9b9c4", ""
        if r["gain"] is not None and r["gain"] >= 0.20:
            col = cc = "#6fc0ff"
            t = '<span class="upq">▲押し上げ</span>'
        elif r["gain"] is not None and r["gain"] <= -0.20:
            t = '<span class="dn">▼下がる</span>'
        so = '<span class="sm">終い%d位</span>' % rk[r["ub"]] if rk.get(r["ub"], 99) <= 3 else ""
        wc = WAKU.get(r["waku"], ("#15110d", "#f2f2f4"))
        hh.append(
            '<div class="horse" style="left:%dpx;top:%dpx"><div class="fig">%s%s</div>'
            '<div class="lab"><span class="n" style="background:%s;color:%s;border-color:%s">%d</span>'
            '<span class="nm">%s</span></div>%s%s</div>'
            % (int(x), 14 + lane * LANE, uma_fig(r["waku"], r["ub"], col), CHEV.format(c=cc), wc[0], wc[1],
               "#00000055" if r["waku"] == 1 else "rgba(255,255,255,.45)",
               r["ub"], H.escape(r["name"][:4] if two_d else r["name"]), t, so))

    board_html = ('<div class="board">%s<div class="track" style="height:%dpx"><div class="goal"></div>%s</div></div>'
                  '<div class="xlab"><span>後方</span><span>中団</span><span>前　→　ゴール</span></div>'
                  % (('<div class="ylab"><span>内（ラチ側）</span><span>外</span></div>' if two_d else ""),
                     NL * LANE + 24, "\n".join(hh)))
    if STYLE == "kawa":
        board_html = kawa_board(rows, fc, n, rk)
        if yon_wanted(globals().get("_CUR_RNO")):   # --yon: 4コーナーの盤面をもう1枚(1枚目の値は変えない)
            keep = {r["ub"]: (r.get("outer_score"), r.get("lane")) for r in rows}
            # 横に並べる(ユーザー指定 2026-11-16「横に並べて」): 左に1角、右に4角。見出し・ペース欄・傾向・見解は共通で1つ
            board_html = '<div class="kpair">%s%s</div>' % (board_html, kawa_board(rows, fc, n, rk, yon=True))
            for r in rows:
                r["outer_score"], r["lane"] = keep[r["ub"]]
    elif stages and STYLE == "simple":
        board_html = simple_board(rows, fc, n, rk)
    elif stages:
        board_html = "".join(stage_board(rows, fc, n, key, prev, lab, rk)
                             for key, prev, lab in (("pos1", None, "スタート後"), ("pos3", "pos1", "3コーナー"),
                                                    ("pos", "pos3", "4コーナー")))
    if surface == "芝":   # 芝は緑の盤面(ダートは茶のまま)
        board_html = board_html.replace('class="track"', 'class="track turf"')
    pcls, ptag = {"スロー": ("slow", "S"), "ミドル": ("mid", "M"), "ハイ": ("high", "H")}[fc.pace]
    mark = max(0.02, min(0.98, 0.5 + fc.pace_index * 0.667))
    q = getattr(fc, "q", None)
    if q and getattr(fc, "diff_pred", None) is not None:   # バーの3区分を想定の区分の境目に合わせる
        dpr = fc.diff_pred
        if dpr > q[1]:
            mark = 1 / 3 * max(0.06, 1 - (dpr - q[1]) / 2.0)
        elif dpr >= q[0]:
            mark = 1 / 3 + 1 / 3 * (q[1] - dpr) / max(1e-6, q[1] - q[0])
        else:
            mark = 2 / 3 + 1 / 3 * min(0.94, (q[0] - dpr) / 2.0)
    flow = {
        "slow": "前半はゆっくり → 前に行った馬がそのまま残りやすい",
        "mid": "前半はふつう → 前の組が基本、中団から外へ出す馬も届く",
        "high": "前半が速い → 前の組がいちばん来るが、差すなら外",
    }[pcls]
    es = sorted([r["e"] for r in rows if r["e"]], reverse=True)
    est = getattr(fc, "est", None)
    est_html = ""
    if est:
        mm, ss = divmod(est["time"], 60)
        est_html = ('<div class="est"><span>推定タイム <b>%d:%04.1f</b></span><span>推定前半3F <b>%.1f</b></span>'
                    '<span>推定後半3F <b>%.1f</b></span></div>' % (mm, ss, est["front3"], est["last3"]))
    if getattr(fc, "diff_pred", None) is not None:
        flow_sub = ("想定の前後半差 %+.2f秒(%s)・<b>ペース確度 %s</b>・コース平均+馬場+当日の流れ、%d鞍から学習"
                    % (fc.diff_pred, "後半が速い＝前半ゆったり" if fc.diff_pred > 0 else "前半が速い",
                       getattr(fc, "conf", "-"), getattr(fc, "n_learn", 0)))
    elif len(es) >= 3:
        flow_sub = ("先頭圏3頭の前半速度 %.2fm/s(この鞍の中央値 %.2fm/s)・コース %s"
                    % (st.mean(es[:3]), st.median(es),
                       "差し有利" if fc.front_bias < -0.05 else ("前有利" if fc.front_bias > 0.05 else "平坦")))
    else:
        flow_sub = ""
    memo = make_memo_simple(fc, rows, rk, name, dist, surface) if (stages and STYLE == "simple") else make_memo(fc, rows, rk, name)
    known = sum(1 for r in rows if r["pos"] is not None) / max(1, len(rows))
    if known < 0.7:
        memo = ('<p class="hold"><b>隊列は判定保留</b>(通過順の記録がある馬が %d%%)。'
                '学習では、記録が揃わない鞍の隊列予想は当てずっぽうと変わらなかった。</p>' % round(known * 100)) + memo
    else:
        memo = ('<p class="sure">隊列確度: 通過順の記録がある馬 %d%%(検証では順位相関 +0.49・ハナ的中28%%)</p>'
                % round(known * 100)) + memo
    if STYLE == "kawa":   # 川崎の図の形: 見解は1段落、ペース欄はバーと一言だけ
        est = getattr(fc, "est", None)
        lvl = ""
        if est:
            mm, ss = divmod(est["time"], 60)
            lvl = "推定 %d:%04.1f(前3F %.1f・上がり %.1f)" % (mm, ss, est["front3"], est["last3"])
            if getattr(fc, "meeting_shift", None) is not None:
                lvl += "　※今開催の馬場のずれ込み"
        start = (getattr(fc, "_start", "") or "")
        fc.arekata = arekata_fuda(fc, rows, surface, n)
        return (
            '<div class="race kawa%s">%s<div class="rh"><span class="rn">%sR</span>'
            '<span class="rd"><span class="st">%s</span>%s%dm ／ %d頭 ／ %s</span>%s'
            '<span class="pace p-%s"><b>%s</b> %s</span>%s</div>'
            '<div class="pbar p-%s"><div class="bar"><span>ゆっくり</span><span>ふつう</span><span>速い</span>'
            '<i style="left:%.1f%%"></i></div><div class="flow">→ <b>%s</b>　<small>%s</small></div>%s</div>'
            '%s%s<div class="kenkai"><div class="kt">見解</div><p>%s</p></div>%s</div>'
            % ((" nopace" if globals().get("_CUR_RNO") in HIDE_PACE else "")
               + (" yon2" if yon_wanted(globals().get("_CUR_RNO")) else ""),
               nankan_head(fc, rows, rk, baba) if NANKAN else "",
               rno, start, surface, dist, n, H.escape(name),
               arekata_html(fc.arekata), pcls, ptag,
               {"スロー": "スロー", "ミドル": "ミドル", "ハイ": "ハイ"}[fc.pace] + "想定",
               (('<span class="tbase"><b>%d:%04.1f</b> の時計をベースにしています%s</span>'
                 % (*divmod(est["time"], 60), _lap_text(est)))
                if (est and globals().get("_CUR_RNO") in HIDE_PACE) else ""),
               pcls, mark * 100, flow.split("→ ")[-1], lvl,
               (_today_line(fc) or (('<div class="lanebias">今開催は4角で%sが来ている(前の開催日の3着内 %d頭のうち外 %d%%、ふだん49%%) → %s◎の札</div>'
                 % (fc.lane[0], fc.lane[2], fc.lane[1] * 100, fc.lane[0])) if getattr(fc, "lane", (None,))[0] else "")),
               board_html, getattr(fc, "trend", "") or "", kawa_memo(fc, rows, rk, dist, surface), jiten_html()))
    missing = [r for r in rows if r["pos"] is None]
    miss = ""
    if missing:
        miss = ('<div class="miss">4角の記録なし … %s —— 測れないだけで、弱いという意味ではありません</div>'
                % "・".join("%d %s" % (r["ub"], H.escape(r["name"])) for r in missing))
    return (
        '<div class="race"><div class="rh"><span class="rn">%sR</span>'
        '<span class="rd">%s　<b>%s%dm</b> ／ %d頭 ／ %s</span>'
        '<span class="pace p-%s"><b>%s</b> %s</span></div>'
        '<div class="pbar p-%s"><div class="bar"><span>ゆっくり</span><span>ふつう</span><span>速い</span>'
        '<i style="left:%.1f%%"></i></div><div class="flow"><b>%s</b>　<small>%s</small></div>%s%s</div>'
        '%s'
        '<div class="kenkai"><div class="kt">見解</div>%s</div>%s</div>'
        % (rno, H.escape(name), surface, dist, n, H.escape(baba or ""),
           pcls, ptag, {"スロー": "スロー", "ミドル": "平均", "ハイ": "ハイ"}[fc.pace] + "想定",
           pcls, mark * 100, flow, flow_sub, est_html, wind_html(fc),
           board_html, memo, miss + jiten_html()))


JITEN_OFF = False   # --no-jiten: 図の下の「データ: 何Rまでの結果を反映」を出さない


def jiten_line(data_path, date, place) -> str:
    """読み込んだデータに、その日のその場の結果(着順の入った行)が何Rまで入っていたか。
    ユーザー指定 2026-11-17「図には何Rまでの結果で作ったかを書く」(11/15東京12Rで後から結果が入り並びが変わった)。
    出馬表の行(着順なし)は数えない。抜けている芝ダの鞍があれば「(4Rなし)」と添える。障害の鞍は結果が入らないので抜けに数えない。"""
    if not date:
        return "データ: 当日の結果なし"
    md = "%d/%d" % (int(date[5:7]), int(date[8:10]))
    rows = load_rows(data_path) if data_path else []
    got, card = set(), set()
    for d in rows:
        if d.get("date") != date or d.get("place") != place:
            continue
        r = int(d["race_id"][-2:])
        if any(x.get("finish_pos") for x in d.get("result") or []):
            got.add(r)
        elif d.get("surface") in ("芝", "ダ"):
            card.add(r)
    if not got:
        return "データ: %s %s 当日の結果なし" % (md, place)
    last = max(got)
    miss = sorted(r for r in card if r < last and r not in got)
    return "データ: %s %s %dRまでの結果を反映%s" % (md, place, last, ("(%sなし)" % "・".join("%dR" % r for r in miss)) if miss else "")


def jiten_html() -> str:
    if JITEN_OFF:
        return ""
    t = jiten_line(globals().get("_DATA_PATH"), globals().get("_CUR_DATE"), globals().get("_CUR_PLACE"))
    return '<div class="knote" style="margin:4px 16px 8px">%s</div>' % H.escape(t)


def _today_line(fc):
    td = getattr(fc, "today", None)
    if not td or td["n"] < 6:
        return ""
    fr = "前" if td["front"] >= td["front0"] + 0.15 else ("差し" if td["front"] <= td["front0"] - 0.15 else "")
    ln = (getattr(fc, "lane", None) or (None,))[0] or ""
    sig = "・".join(x for x in ((fr + "が来ている") if fr else "", (ln + "が来ている") if ln else "") if x)
    out_txt = ("外%d%%(ふだん%d%%)" % (td["out"] * 100, td["out0"] * 100)) if td["out"] is not None else ""
    return ('<div class="lanebias">今日ここまで%d鞍の3着内: 4角で前1/3から%d%%(ふだん%d%%)・%s%s</div>'
            % (td["races"], td["front"] * 100, td["front0"] * 100, out_txt,
               (" → <b>%s</b>" % sig) if sig else " → 偏りなし"))


def _lap_text(est):
    """ラップ想定(各ハロンの中央値を、推定の走破時計に合うよう後半2ハロンで調整)。"""
    laps = est.get("laps")
    if not laps:
        return ""
    laps = [round(x, 1) for x in laps]
    d = round(est["time"] - sum(laps), 1)
    if abs(d) <= 1.0 and len(laps) >= 2:
        h = round(d / 2, 1)
        laps[-2] = round(laps[-2] + h, 1)
        laps[-1] = round(laps[-1] + d - h, 1)
    return '<span class="lap">ラップ想定 %s</span>' % "-".join("%.1f" % x for x in laps)


SHOW_KIKOU = False   # 気候の札は出さない(ユーザー指定 2026-11-14「あの表示消して」「パクッてると思われちゃう」)。--kikou で出す


def kikou_tag(ub):
    """今日の気候(発走時の気温 寒<10/涼<20/暖<25/暑)が得意な馬に札。note むねひろ の「気候／◯」を
    こちらのデータで作ったもの(scripts/jra_kikou_kenkyu.py: 力が同じ層で 得意 > 苦手 に3着内率 +3〜7pt)。
    その気候で2走以上・他の気候で2走以上、3着内率が他より 0.25 以上高いときだけ。"""
    if not SHOW_KIKOU or ME_RACE is None or ub not in ME_PAST:
        return ""
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from jra_kikou_kenkyu import kikou, temp_at
    except Exception:  # noqa: BLE001
        return ""
    k = kikou(temp_at(ME_RACE["place"], ME_RACE["date"], int(ME_RACE["race_id"][-2:])))
    if not k:
        return ""
    same, other = [0, 0], [0, 0]
    for x in ME_PAST[ub]:
        if not x.get("race_id"):
            continue
        kx = kikou(temp_at(x["place"], x["date"], int(x["race_id"][-2:])))
        if not kx:
            continue
        t = same if kx == k else other
        t[0] += 1
        t[1] += 1 if (x.get("fin") or 99) <= 3 else 0
    if same[0] >= 2 and other[0] >= 2 and same[1] / same[0] - other[1] / other[0] >= 0.25:
        return '<span class="kik">気候◎ %s %d/%d</span>' % (k, same[1], same[0])
    return ""


def wind_html(fc):
    out = ""
    rel = getattr(fc, "rel", None)
    if rel:
        lab, p, pr = rel
        conf = "高" if p >= 0.52 else ("中" if p >= 0.44 else "低")
        hint = {"遅め": "前が残りやすい", "平均": "形は互角", "速め": "差しが届きやすい"}[lab]
        out = ('<div class="wind">このコースにしては <b>%s</b>(確度%s 遅め%d%%・平均%d%%・速め%d%%) → %s'
               '　<small>※決着の形と結びつくのはこちら</small></div>'
               % (lab, conf, pr[0] * 100, pr[1] * 100, pr[2] * 100, hint))
    w = getattr(fc, "wind", None)
    if not w or w[0] is None:
        return out
    h, c, _ = w
    if abs(h) < 1.5 and c < 3:
        t = "直線の風は弱い"
    elif abs(h) >= 1.5:
        t = ("直線 <b>向かい風 %.1fm</b> → 上がりがかかる(ハイ寄り)" % h) if h > 0 else ("直線 <b>追い風 %.1fm</b> → 上がりが速くなる(スロー寄り)" % -h)
    else:
        t = "直線 横風 %.1fm" % c
    return out + '<div class="wind">%s</div>' % t


def wind_head(place, date, rno):
    """その鞍の直線の風(向かい風m/s、横風m/s、前後差の補正秒)。直線の向きは note の風傾向の全記述から
    (models/course_straight.json)、風は Open-Meteo(過去=archive、当日=forecast を data/jra/wind/ に)。"""
    import json
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from jra_wind_choku import head_cross
        hc = head_cross(place, date, rno) if rno else None
        if not hc:
            return None
        coef = json.load(open(ROOT / "models" / "wind_head.json"))["coef_diff_per_head"]
        k = coef.get(getattr(sys.modules[__name__], "_CUR_SURF", "芝"), -0.055)
        return hc[0], hc[1], k * max(-6.0, min(6.0, hc[0]))
    except Exception:  # noqa: BLE001
        return None


_UMA_CACHE: dict = {}


def uma_img(waku, ub, px=50, face_left=False):
    """もらったイラスト(scripts/ana/uma/、uma_img.py)で、枠の色の勝負服・ゼッケンに馬番を描いた馬の絵(data URI)。
    頭が右(ゴール側)を向く(ユーザー指定 2026-11-11「馬の向き逆ね」。元絵の都合で left=True がこの向き)。無ければ None。"""
    key = (waku, ub, px, face_left)
    if key in _UMA_CACHE:
        return _UMA_CACHE[key]
    try:
        import base64
        import io
        sys.path.insert(0, str(ROOT / "scripts" / "ana"))
        import uma_img as U
        im = U.horse(waku or 1, ub, px=px, left=not face_left)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        _UMA_CACHE[key] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:  # noqa: BLE001
        _UMA_CACHE[key] = None
    return _UMA_CACHE[key]


def uma_fig(waku, ub, col):
    """展開図の馬は、もらったイラスト(枠色の帽子・勝負服、ゼッケンに馬番)が既定。無ければシルエット。"""
    img = uma_img(waku, ub)
    return ('<img class="uma" src="%s" alt="">' % img) if img else HORSE.format(c=col)


_DATA_PATH = None


def lane_bias(place, surface, date):
    """同じ開催の前の開催日(8日以内)、4角の通過順で3着内の馬が組(2頭以上)の外にいた割合。
    3年の芝で外49%・内40%、1日ごとの外率は中央50%・上位10%が67%(2026-11-14 福島芝は75%)。
    返り値 ("外"|"内"|None, 外率, 頭数)"""
    import re as re_
    import datetime as dt_
    if not _DATA_PATH or not date:
        return None, None, 0
    d0 = dt_.date.fromisoformat(date)
    c = {"外": 0, "内": 0, "中": 0}
    for d in load_rows(_DATA_PATH):
        if d.get("place") != place or d.get("surface") != surface or not d.get("lap") or d["date"] >= date:
            continue
        if (d0 - dt_.date.fromisoformat(d["date"])).days > 8:
            continue
        gs = [[int(x) for x in re_.findall(r"\d+", t)]
              for t in re_.findall(r"\([^)]*\)|\d+", ((d.get("corners") or {}).get("4") or "").replace("*", ""))]
        for r in d["result"]:
            if (r.get("finish_pos") or 99) <= 3:
                for g in gs:
                    if r["umaban"] in g and len(g) >= 2:
                        c["外" if g[-1] == r["umaban"] else "内" if g[0] == r["umaban"] else "中"] += 1
    n = sum(c.values())
    if n < 8:
        return None, None, n
    sh = c["外"] / n
    return ("外" if sh >= 0.67 else "内" if sh <= 0.33 else None), sh, n


_BASE_SHAPE: dict = {}


def _shape_of(races):
    """3着内の馬の 4角の組での外/内/中 と、4角で前1/3にいたかを数える。"""
    import re as re_
    c = {"外": 0, "内": 0, "中": 0, "前": 0, "n": 0}
    for d in races:
        n = d.get("field_size") or 0
        gs = [[int(x) for x in re_.findall(r"\d+", t)]
              for t in re_.findall(r"\([^)]*\)|\d+", ((d.get("corners") or {}).get("4") or "").replace("*", ""))]
        for r in d["result"]:
            if (r.get("finish_pos") or 99) <= 3 and r.get("corner_pos") and n >= 2:
                c["n"] += 1
                c["前"] += (r["corner_pos"][-1] - 1) / (n - 1) <= 1 / 3
                for g in gs:
                    if r["umaban"] in g and len(g) >= 2:
                        c["外" if g[-1] == r["umaban"] else "内" if g[0] == r["umaban"] else "中"] += 1
    return c


def day_shape(place, surface, date, race_id):
    """当日のここまでの鞍(同じ場・芝ダ、この鞍より前)で、3着内の馬が4角で外にいた割合・前1/3にいた割合。
    ふだん(この場・芝ダの3年)と比べる。ユーザー指定 2026-11-14「どこを狙うか当日で決める」。"""
    if not _DATA_PATH or not date or not race_id:
        return None
    rows = load_rows(_DATA_PATH)
    key = (place, surface)
    if key not in _BASE_SHAPE:
        _BASE_SHAPE[key] = _shape_of([d for d in rows if d.get("place") == place and d.get("surface") == surface
                                      and d.get("lap") and d["date"] < date])
    today = [d for d in rows if d.get("place") == place and d.get("surface") == surface and d["date"] == date
             and d.get("lap") and d["race_id"] < race_id and d["result"] and d["result"][0].get("time")]
    if not today:
        return None
    c, b = _shape_of(today), _BASE_SHAPE[key]
    lanes = c["外"] + c["内"] + c["中"]
    bl = b["外"] + b["内"] + b["中"]
    return {"races": len(today), "n": c["n"], "front": c["前"] / max(1, c["n"]), "front0": b["前"] / max(1, b["n"]),
            "out": c["外"] / lanes if lanes else None, "out0": b["外"] / bl if bl else None, "lanes": lanes}


HIDE_PACE: set = set()   # ペース想定の札を出さない R(--hide-pace "12")
# コース1周の長さと最後の直線(4角出口→ゴール)、m(JRA コース紹介のおおよその値)。芝は主に使うコース
COURSE_LAP = {("東京", "芝"): (2083, 526), ("東京", "ダ"): (1899, 502), ("中山", "芝"): (1667, 310),
              ("中山", "ダ"): (1493, 308), ("京都", "芝"): (1894, 404), ("京都", "ダ"): (1608, 329),
              ("阪神", "芝"): (2089, 474), ("阪神", "ダ"): (1517, 353), ("中京", "芝"): (1705, 413),
              ("中京", "ダ"): (1530, 411), ("新潟", "芝"): (2223, 659), ("新潟", "ダ"): (1472, 354),
              ("福島", "芝"): (1600, 292), ("福島", "ダ"): (1444, 296), ("小倉", "芝"): (1615, 293),
              ("小倉", "ダ"): (1445, 291), ("札幌", "芝"): (1641, 266), ("札幌", "ダ"): (1487, 264),
              ("函館", "芝"): (1627, 262), ("函館", "ダ"): (1476, 260)}
LEFT_TURN = {"東京", "新潟", "中京"}
# ユーザーが見て決めた向き(計算より優先)。True=左が前
FRONT_OVERRIDE: dict = {}   # 例 {("東京", "芝", 1400): False}(右が前)。2026-11-14 東京芝1400を一度右に戻したが、ユーザーが取り消し


def starts_on_homestretch(place, surface, dist):
    """スタートが正面(ゴール前の直線〜4角の手前)か。front_is_left と同じ判定(r = dist % 1周、r <= 直線+200)。
    分からないコースは None。"""
    if (place, surface) not in COURSE_LAP or not dist:
        return None
    lap, home = COURSE_LAP[(place, surface)]
    r = dist % lap if dist > lap else dist
    return r <= home + 200


def first_corner_name(place, surface, dist):
    """正面スタートなら「1コーナー」、向こう正面などからなら「最初のコーナー」(2角/3角は決め打ちしない)。"""
    return "1コーナー" if starts_on_homestretch(place, surface, dist) else "最初のコーナー"


def front_is_left(place, surface, dist):
    """スタンドから見たとき、最初のコーナーあたりで馬が右→左に走るか(=図の左が前)。
    スタートが正面(ゴール前の直線〜4角の手前)なら 左回り:左→右 / 右回り:右→左、
    向こう正面(1角のポケット〜3角)なら逆。ユーザー指摘 2026-11-14「東京11R 位置も向きも逆」「12Rも逆」。"""
    if (place, surface, dist) in FRONT_OVERRIDE:
        return FRONT_OVERRIDE[(place, surface, dist)]
    if (place, surface) not in COURSE_LAP or not dist:
        return False
    lap, home = COURSE_LAP[(place, surface)]
    r = dist % lap if dist > lap else dist
    homestretch = r <= home + 200
    return (not homestretch) if place in LEFT_TURN else homestretch


UCHI_UE = False   # --uchi-ue: 盤面の上下を元に戻す(常に内が上。inner_is_down を使わない)
YON: set = set()   # --yon: 4コーナーの盤面も出す R。"all" で全鞍
YON_ALL = False


def yon_wanted(rno) -> bool:
    return YON_ALL or (rno in YON)


def inner_is_down(place, flip) -> bool:
    """スタンドから見た盤面で、内(ラチ側)が下か(ユーザー指摘 2026-11-16「2000mスタート ラチ沿い下だ」)。
    左回りは馬の左手が内: 左が前(右→左)なら左手はスタンド側=下、右が前なら上。右回りは逆。
    → 内が上は (左回り かつ 右が前) か (右回り かつ 左が前) のときだけ。分からない場は今までどおり上。"""
    if UCHI_UE or not place or place not in {p for p, _ in COURSE_LAP}:   # --uchi-ue: 507db35 より前の向き(常に内が上)
        return False
    return flip if place in LEFT_TURN else not flip


def yon_front_is_left(place):
    """4コーナーを回って直線を向いたところを、スタンドから見たとき左が前か。
    直線はスタンドの前を通るので front_is_left の「スタートが正面」と同じ向き:
    左回り(東京・新潟・中京)は左→右(右が前)、右回りは右→左(左が前)。分からない場は右が前。"""
    if not place or place not in {p for p, _ in COURSE_LAP}:
        return False
    return place not in LEFT_TURN


CIRCLE: dict = {}
CIRCLE_EACH = False   # --circle-each: 赤丸も1頭ずつ(ユーザー指定 2026-11-14「全部○で囲って」)
CIRCLE2: dict = {}  # 相手の丸(白)。--circle2 "7:15,10"。本命は --circle(赤)   # 手で丸を付ける馬 {R番号(int): {馬番}}。--circle "12:6,12,15;3:8"


ARE_OFF = False   # --no-arekata で荒れ方の札を消す


def arekata_fuda(fc, rows, surface, n) -> list:
    """荒れ方の札(scripts/jra_arekata.py の fuda をそのまま使う。notes/live/jra_arekata.md §5)。
    予想ペース版: A 先行過多・荒れ目 / B 前残り・堅め / C 差し届き・荒れ目。人気・オッズは使わない。
    盤面を描いたあと(outer_score が jra_arekata の予想と同じく pos1 で付いたあと)に呼ぶ。
    ペースは学習したペース(fc.q がある時)だけ使う。無いときは C(ペース不問)だけ判定。"""
    if ARE_OFF:
        return []
    from jra_arekata import fuda
    hs = [{"ub": r["ub"], "pos1": r.get("pos1"), "outer": r.get("outer_score"), "nige": r.get("nige"),
           "kouho": r.get("kouho") or []} for r in rows]
    return fuda(fc.pace if getattr(fc, "q", None) else None, hs, surface, n)


def arekata_html(keys) -> str:
    from jra_arekata import FUDA
    return "".join('<span class="are are-%s"><b>%s</b><small>%s</small></span>'
                   % ("hot" if FUDA[k][1] == "are" else "calm", FUDA[k][0], FUDA[k][2])
                   for k in keys)


SHOW_TREND = True   # --no-trend で消す。盤面の下・見解の上の「過去の傾向」欄
_GENERIC_NAME = re.compile(r"(障害)?\d歳(以上)?(未勝利|新馬|\d勝クラス|オープン)|メイクデビュー.*|新馬.*|")
_BABA3 = {"良": "良", "稍": "稍重", "重": "重以上", "不": "重以上"}


def _race_key_name(name):
    """レース名の主要部分。「第◯回」・(G1) などを除く。一般戦名(1勝クラス・未勝利・新馬…)は None。"""
    s = re.sub(r"第\s*[0-9０-９]+\s*回", "", name or "")
    s = re.sub(r"[（(][^)）]*[)）]", "", s).strip()
    if _GENERIC_NAME.fullmatch(s) or len(s) < 3:
        return None
    return s


def _corner_side(d, ub):
    """4角の通過順で、その馬が組(括弧)の 外/内/中、1頭なら 単独。括弧の中は内から並ぶ。"""
    for t in re.findall(r"\([^)]*\)|\d+", ((d.get("corners") or {}).get("4") or "").replace("*", "")):
        g = [int(x) for x in re.findall(r"\d+", t)]
        if ub in g:
            if len(g) < 2:
                return "単独"
            return "外" if g[-1] == ub else "内" if g[0] == ub else "中"
    return ""


_BUCKET_LABEL = ("1-2番手", "3-4", "5-7", "8-10", "11-")


def course_win_line(place, surface, dist, baba=None):
    """models/course_pos.json(scripts/jra_course_pos.py)から「このコースの勝ち馬の4角」の1行。
    馬場(良/渋)の版が鞍数十分(MIN_N 以上)なら、その日の馬場の版も添える。表示だけで予想には使わない。"""
    try:
        import datetime as _dt
        import jra_course_pos as CP
        k, s = CP.lookup(place, surface, dist)
    except Exception:  # noqa: BLE001  (表が無い環境では出さない)
        return ""
    if not s:
        return ""
    lvl = len(k.split("|"))
    what = ("このコース" if lvl == 3 and k.split("|")[2].isdigit()
            else "この距離帯(%s)" % k.split("|")[2] if lvl == 3 else "この場の%s" % surface)
    try:
        p0, p1 = CP._M["period"]
        yrs = "%d年 " % max(1, round((_dt.date.fromisoformat(p1) - _dt.date.fromisoformat(p0)).days / 365))
    except Exception:  # noqa: BLE001
        yrs = ""
    pc = lambda v: "%d%%" % round(v * 100)  # noqa: E731
    seg = lambda w: "・".join("%s %s" % (lb, pc(v)) if i else "%s%s" % (lb, pc(v))  # noqa: E731
                              for i, (lb, v) in enumerate(zip(_BUCKET_LABEL, w)))
    out = "%sの勝ち馬の4角(%s%d鞍): %s" % (what, yrs, s["n"], seg(s["win"]))
    if baba:
        _, sb = CP.lookup(place, surface, dist, baba)
        if sb is not None and sb is not s:
            g = "良" if baba == "良" else "渋"
            out += "　／　今日の馬場(%s・%d鞍): %s" % (g, sb["n"], seg(sb["win"]))
        else:   # 版はあるが鞍数が足りない
            g = "良" if baba == "良" else "渋" if baba in ("稍", "重", "不") else None
            e = (CP._M.get("course") or {}).get(k, {}).get(g) if g and lvl == 3 else None
            if e and e is not s:
                out += "　／　今日の馬場(%s)は%d鞍で少ないので全体のみ" % (g, e["n"])
    return '<span class="tl">勝つ位置</span>' + out


def trend_html(data_path, date, place, surface, dist, name, baba=None):
    """「過去の傾向」欄(ユーザー指定 2026-11-15)。その鞍の日付より前の行だけを使う。
    1) 同じレース名の過去の回(最大3回): 年・馬場・1〜3着の 4角位置/頭数・組の外内・人気(人気は表示だけ)
    2) 同じ場・芝ダ・距離を馬場(良/稍重/重以上)で分け、3着内の馬の 4角前/中/後1/3 の割合・組の外の割合・鞍数
    3) このコースの勝ち馬の4角の区分(models/course_pos.json。こちらは表全体で、日付で切っていない)"""
    if not data_path or not date:
        return ""
    seen, past = set(), []
    for d in load_rows(data_path):
        if d["date"] >= date or d["race_id"] in seen or not d.get("result"):
            continue
        if not any(x.get("finish_pos") for x in d["result"]):
            continue
        seen.add(d["race_id"])
        past.append(d)
    lines = []
    key = _race_key_name(name)
    if key:
        same = []
        for d in past:
            k2 = _race_key_name(d.get("name"))
            if k2 and (key in k2 or k2 in key):
                same.append(d)
        same.sort(key=lambda d: d["date"], reverse=True)
        parts = []
        for d in same[:3]:
            n = d.get("field_size") or len(d["result"])
            top = sorted((x for x in d["result"] if (x.get("finish_pos") or 99) <= 3), key=lambda x: x["finish_pos"])
            hs = []
            for x in top:
                cp = x.get("corner_pos") or []
                pos = "4角%d/%d%s" % (cp[-1], n, _corner_side(d, x["umaban"])) if cp else "4角-"
                hs.append("%d着 %s%s" % (x["finish_pos"], pos, "(%d人)" % x["popularity"] if x.get("popularity") else ""))
            other = "" if (d.get("place"), d.get("surface"), d.get("distance")) == (place, surface, dist) else \
                "%s%s%d " % (d.get("place"), d.get("surface"), d.get("distance"))
            parts.append("<span class=\"ty\"><b>%s</b> %s%s %s</span>" % (d["date"][:4], other, {"稍": "稍重", "不": "不良"}.get(d.get("baba"), d.get("baba") or ""),
                                                "・".join(hs)))
        if parts:
            lines.append('<span class="tl">過去の回</span>' + "　／　".join(parts))
    cond = [d for d in past if d.get("place") == place and d.get("surface") == surface and d.get("distance") == dist]
    if cond:
        segs = []
        for b in ("良", "稍重", "重以上"):
            rs = [d for d in cond if _BABA3.get(d.get("baba")) == b]
            if not rs:
                segs.append("%s(なし)" % b)
                continue
            fmc = [0, 0, 0]
            side = {"外": 0, "内": 0, "中": 0}
            for d in rs:
                n = d.get("field_size") or 0
                for x in d["result"]:
                    if (x.get("finish_pos") or 99) <= 3 and x.get("corner_pos") and n >= 2:
                        r = (x["corner_pos"][-1] - 1) / (n - 1)
                        fmc[0 if r <= 1 / 3 else 1 if r <= 2 / 3 else 2] += 1
                        sd = _corner_side(d, x["umaban"])
                        if sd in side:
                            side[sd] += 1
            tot, ls = sum(fmc), sum(side.values())
            few = "・少ない" if len(rs) < 10 else ""
            if not tot:
                segs.append("%s(%d鞍%s)" % (b, len(rs), few))
                continue
            segs.append("<span class=\"ty\">%s(%d鞍%s) 前%d・中%d・後%d%%%s"
                        % (b, len(rs), few, *(round(c * 100 / tot) for c in fmc),
                           ("・外%d%%" % round(side["外"] * 100 / ls)) if ls else "") + "</span>")
        if segs:
            lines.append('<span class="tl">この条件%s%s%dm</span>' % (place, surface, dist)
                         + "3着内の4角　" + "　／　".join(segs))
    cw = course_win_line(place, surface, dist, baba)
    if cw:
        lines.append(cw)
    if not lines:
        return ""
    return '<div class="ktrend"><div class="kt">過去の傾向</div>%s</div>' % "".join("<p>%s</p>" % l for l in lines)


# ── 競馬ブックの厩舎の話(data/kb/danwa_YYYYMMDD.jsonl, scripts/kb_jra.py が作る)から拾う小さな札 ──
# 有料の中身なので、図に出すのは札だけ(コメントの文は載せない)。予想(位置・ペース・時計)には使わない。
# 言葉は kb_jra.py --summary のキーワードを元に、向き(歓迎か苦手か)が読めるものだけに絞った。
KB_PATH = None       # --kb。None なら data/kb/danwa_<日付>.jsonl があれば使う
KB_OFF = False       # --no-kb
KB_DEBUG = False     # --kb-debug
_KB: dict = {}       # 日付 → {(場, R, 馬番): (馬名, [(札, 語)])}
KB_ORDER = ("良◎", "道悪○", "道悪×", "ハナ", "控え")
# 先に消す語(誤検出): 渋太い・動きが渋い・重賞・ハナ差 など
KB_NG = (r"渋太|渋とい|渋く|動きが渋|渋い|重賞|体重|ハナ差|ハナ負け|鼻|差し支え|差し返|差し込|差し替|"
         r"逃げ馬を|逃げた馬|逃げ切られ|逃げ残|逃げる馬|逃げ粘る馬|控え室")
KB_PAT = [
    ("道悪×", r"(道悪|雨馬場|重馬場|渋った馬場|渋馬場|渋い馬場|悪い馬場|馬場が悪)(は|が|も|に|で)?(少し|ちょっと)?"
             r"(応え|こたえ|堪え|どうか|苦手|下手|ダメ|駄目|良くない|よくない|合わない|向かない|不向き|嫌|マイナス|割り引)"),
    ("道悪○", r"(道悪|雨馬場|重馬場|渋った馬場|渋馬場|渋い馬場)(は|も|が|で|に)?(全然|全く|むしろ)?"
             r"(ＯＫ|OK|大丈夫|こなす|こなせ|苦にしない|苦にせず|問題ない|問題なく|平気|上手|得意|歓迎|巧|合う|向く|プラス|良い|いい)"
             r"|道悪巧者|渋馬場歓迎|道悪歓迎|道悪ＯＫ|(馬場が|馬場は)?渋って(も|くれ)(辛抱|こなせ|こなす|大丈夫|問題|平気|いい|良い|プラス|歓迎|走れ|やれ)"
             r"|降雨があっても|雨が降っても|雨(予報)?(が|は|も)?(歓迎|苦にしない|降ってほしい|降れば)|脚抜きの(いい|良い)馬場(に|なら|が|は|を)"),
    ("良◎", r"良馬場(で|なら|が|の|を|希望|向き|ベスト|理想)|パンパン|乾いた馬場|良(い)?馬場で(走|競馬|や)"),
    ("ハナ", r"ハナ(を|に|へ|は|が|で|だ|主張|切|立|奪|を切|を主張|を取)|先手(を)?(取|主張|奪|必勝)|単騎(逃げ|で逃|の逃|で行)"
             r"|逃げ(たい|る競馬|の手|に出|て(粘|しぶと|マイペース|淡々)|が理想|が?ベスト|切りたい|れれば|られれば|が決ま|を打|が持ち味|てこそ|に徹)"),
    ("控え", r"控え(たい|て|る形|る競馬|た方|ても|る作戦|させ)|脚を?(ため|溜め|貯め)|溜めて|ためて(の|から|直線|運|弾け|伸び)"
             r"|差し(が利|が決ま|に回|に徹|の形|脚を|て(くる|きた|きまし|伸び)|を生か|馬|で(勝|来|伸))|後方から|追い込み|後ろから"),
]
# 否定(拾ったあと、その直後に来たら捨てる): 「控える競馬は合わない」「ハナにはこだわらない」
KB_NEG = r"^[^。、]{0,8}?(は|が|も|に|で)?(は)?(合わない|向かない|良くない|よくない|ダメ|駄目|嫌う|嫌がる|こだわらな|こだわる必要はな|行かな|無理|難しい|しない|せず|できな|出来な|叩かれ|を?試し|行っても|行くことになっても)"


def kb_words(short: str, comment: str) -> list:
    """一言(short)とコメントから [(札, 拾った語)]。同じ札は1回だけ。"""
    out, seen = [], set()
    for text in (short or "", comment or ""):
        t = re.sub(KB_NG, lambda m: "＿" * len(m.group(0)), text)
        for tag, pat in KB_PAT:
            if tag in seen:
                continue
            for m in re.finditer(pat, t):
                rest = re.split(r"[。！？]", t[m.end():])[0]
                if re.match(KB_NEG, rest) or re.search(r"が、今回は", rest):   # 「〜した方がいいですが、今回は…」
                    continue
                if tag == "道悪○" and "道悪×" in seen:
                    break
                out.append((tag, m.group(0)))
                seen.add(tag)
                break
    if "道悪×" in seen and "道悪○" in seen:   # 両方拾ったら苦手のほうを残す(向きが読めない)
        out = [x for x in out if x[0] != "道悪○"]
    return sorted(out, key=lambda x: KB_ORDER.index(x[0]))


def _norm_name(s: str) -> str:
    import unicodedata
    return re.sub(r"\s", "", unicodedata.normalize("NFKC", s or ""))


def kb_load(date: str) -> dict:
    if KB_OFF or not date:
        return {}
    if date in _KB:
        return _KB[date]
    import json
    p = Path(KB_PATH) if KB_PATH else ROOT / "data" / "kb" / ("danwa_%s.jsonl" % date.replace("-", ""))
    res = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if d.get("date") and d["date"] != date:
                continue
            for h in d.get("horses", []):
                w = kb_words(h.get("short", ""), h.get("comment", ""))
                res[(d["place"], int(d["race_no"]), int(h["umaban"]))] = (h.get("name", ""), w)
    elif KB_PATH:
        print("厩舎の話が無い:", p, file=sys.stderr)
    _KB[date] = res
    return res


def kb_list(ub, name) -> list:
    """今の鞍のこの馬の [(札, 語)]。場・R・馬番で引き、馬名が違えば付けない。"""
    kb = kb_load(globals().get("_CUR_DATE") or "")
    v = kb.get((globals().get("_CUR_PLACE"), globals().get("_CUR_RNO"), ub))
    if not v or _norm_name(v[0]) != _norm_name(name):
        return []
    return v[1]


def kb_tag_html(ub, name) -> str:
    return "".join('<span class="kbt">%s</span>' % H.escape(t) for t, _ in kb_list(ub, name))


def kb_debug(rows):
    if not KB_DEBUG:
        return
    kb = kb_load(globals().get("_CUR_DATE") or "")
    print("[厩舎の話] %s%sR" % (globals().get("_CUR_PLACE"), globals().get("_CUR_RNO")))
    for r in sorted(rows, key=lambda r: r["ub"]):
        v = kb.get((globals().get("_CUR_PLACE"), globals().get("_CUR_RNO"), r["ub"]))
        if v and _norm_name(v[0]) != _norm_name(r["name"]):
            print("  %2d: 馬名が違うので付けない(出馬表=%s 競馬ブック=%s)" % (r["ub"], r["name"], v[0]))
            continue
        for t, w in kb_list(r["ub"], r["name"]):
            print("  %2d: %s ← %s" % (r["ub"], t, w))


def kawa_board(rows, fc, n, rk, key="pos1", yon=False) -> str:
    """川崎の図(ユーザー指定 2026-11-13「こういう風に」「〇つけないで」)と同じ形。
    1コーナーでの隊列、右が前。小さな馬の絵(枠色・ゼッケンに馬番)の下に 丸数字＋馬名。赤い丸は付けない。
    1角から4角で押し上げる馬は矢印を青くする。
    yon=True: 2枚目の「4コーナー」の盤面(--yon)。前後は位置モデルの4角予想(pos)、内外は同じ内外モデル
    (もともと4角の併走の内外を学習したもの)を4角の前後で当て直した値。向きは直線を向いたところ(yon_front_is_left)。
    r["outer_score"]/r["lane"] を書き換えるので、呼ぶ側で1枚目の値に戻す(render_race)。"""
    if yon:
        key = "pos"
    k = key if any(r.get(key) is not None for r in rows) else "pos"
    lateral_layout(rows, fc, n, key=k, band=0.07)
    hs = sorted([r for r in rows if r.get(k) is not None], key=lambda r: -r[k])
    med = st.median(r.get("outer_score", 0) for r in hs) if hs else 0
    nod = [r for r in rows if r.get(k) is None]          # 過去走が無い馬も描く(後方に置いて札)
    hs += nod
    W, P, G = 940, 22, 138    # 盤面の幅の目安(px)。置くときは % に直すので画面幅が違っても切れない
    lb0 = (getattr(fc, "lane", None) or (None,))[0]
    ANA = set(nk_ana(rows)) if NANKAN else set()   # --nankan: 穴 道中で下げない の札
    pad = NK_PAD if (NANKAN and OBI) else 0   # 帯ラベルの余白は --obi のときだけ

    def wid(r):   # 名前と札の幅の目安(札1つ +58px)。右隣の馬の名前に札がかからないように
        if yon:   # 2枚目は札を付けない(番号と馬名だけ。過去走なしの札だけ残す)
            return G + 8 * max(0, len(r.get("name") or "") - 7) + (58 if r.get(k) is None else 0)
        nt = (1 if kikou_tag(r["ub"]) else 0) + (1 if r.get(k) is None else 0) + (1 if lb0 else 0)
        nk = len(kb_list(r["ub"], r.get("name")))   # 厩舎の話の札(短いので 1つ +40px)
        nkh = 0 if KOUHO_OFF else len(r.get("kouho") or [])   # 候補の札(1つ +50px)
        return G + 8 * max(0, len(r.get("name") or "") - 7) + 58 * nt + 40 * nk + 50 * nkh + (66 if r["ub"] in ANA else 0)
    flip = (yon_front_is_left(globals().get("_CUR_PLACE")) if yon else
            front_is_left(globals().get("_CUR_PLACE"), globals().get("_CUR_SURF"), globals().get("_CUR_DIST")))
    span = W - 2 * P - 130
    lanes, cells = [], []
    for r in hs:   # 前の馬から順に置く
        if r.get(k) is not None:
            f = r[k]
        else:   # 過去走が無い馬は並びが読めないので、横に散らして置く(馬番順)
            j = nod.index(r)
            f = (0.9 - 0.8 * j / max(1, len(nod) - 1)) if len(nod) > 1 else 0.0
        x = P + (1 - f) * span if flip else P + f * span   # flip: 左が前(スタンドから見て右→左に走る)
        i = 0 if r.get("outer_score", 0) <= med else 1
        while True:
            while len(lanes) <= i:
                lanes.append(None)
            if flip:   # 前の馬(左)の名前の右端より右に置く
                ok = lanes[i] is None or x > lanes[i] - 4
            else:      # 前の馬(右)の左端より、自分の名前の右端が左
                ok = lanes[i] is None or x + wid(r) < lanes[i] + 4
            if ok:
                lanes[i] = x + wid(r) if flip else x
                cells.append((r, x, i))
                break
            i += 1
    if inner_is_down(globals().get("_CUR_PLACE"), flip):   # 内が下の向き: 段の並びを上下に返すだけ(どの馬がどの段かは同じ)
        nl = max(1, len(lanes))
        cells = [(r, x, nl - 1 - i) for r, x, i in cells]
        inv = True
    else:
        inv = False
    LN = 76
    hh = []
    for r, x, lane in cells:
        up = r.get("gain") is not None and r["gain"] >= 0.20
        cc = "#4fa8ff" if up else "#b9b9c4"
        wc = WAKU.get(r["waku"], ("#15110d", "#f2f2f4"))
        img = uma_img(r["waku"], r["ub"], px=64, face_left=flip)
        fig = ('<img class="uk" src="%s" alt="">' % img) if img else HORSE.format(c="#d8c7ae")
        tag = kikou_tag(r["ub"])
        lb = (getattr(fc, "lane", None) or (None,))[0]
        osc = r.get("outer_score", 0)
        if lb == "外" and hs and osc >= sorted(x.get("outer_score", 0) for x in hs)[len(hs) * 2 // 3]:
            tag += '<span class="klane">外◎</span>'
        elif lb == "内" and hs and osc <= sorted(x.get("outer_score", 0) for x in hs)[len(hs) // 3]:
            tag += '<span class="klane">内◎</span>'
        td = getattr(fc, "today", None)
        if td and td["n"] >= 6 and r.get("pos") is not None:
            if td["front"] >= td["front0"] + 0.15 and r["pos"] >= 2 / 3:
                tag += '<span class="klane">前◎</span>'
            elif td["front"] <= td["front0"] - 0.15 and r["pos"] <= 1 / 2:
                tag += '<span class="klane">差◎</span>'
        tag += kb_tag_html(r["ub"], r["name"])
        if not KOUHO_OFF:
            tag += "".join('<span class="kko">%s</span>' % t for t in r.get("kouho") or [])
        if r["ub"] in ANA:
            tag += '<span class="kana">穴 下げない</span>'
        if yon:
            tag = ""
        if r.get(k) is None:
            tag = '<span class="knd">過去走なし</span>' + tag
        chev = '<span class="kc" style="color:%s">%s</span>' % (cc, "&laquo;" if flip else "&raquo;")
        hh.append('<div class="kh" style="left:%.2f%%;top:%dpx"><div class="kf">%s</div>'
                  '<div class="kl"><span class="kn" style="background:%s;color:%s">%d</span>%s%s</div></div>'
                  % (x / W * 100, 10 + pad + lane * LN, (chev + fig) if flip else (fig + chev), wc[0], wc[1], r["ub"],
                     H.escape(r["name"]), tag))
    if not yon:
        _, fc.zone_horses = draw_zone([(r, x, l) for r, x, l in cells], fc, ellipse=True)   # 見解用に計算だけ(描かない)
    ring = ""
    want = CIRCLE.get(globals().get("_CUR_RNO"), set())
    sel = [(x, lane) for r, x, lane in cells if r["ub"] in want]
    spread = sel and (CIRCLE_EACH or (max(x for x, _ in sel) - min(x for x, _ in sel)) > W * 0.45)
    if sel and spread:   # 離れている馬は1頭ずつ囲む(間の馬を巻き込まない)
        ring = "".join('<div class="kring" style="left:calc(%.2f%% - 14px);top:%dpx;width:158px;height:%dpx"></div>'
                       % (x / W * 100, 10 + l * LN - 8, LN - 2) for x, l in sel)
    elif sel:   # 指定した馬をまとめて丸1つで囲む。左端と右端の馬を結ぶ向きに傾けた楕円(間の他の馬にかぶりにくい)
        import math
        pts = sorted(((x + 62) / W * 940, 10 + l * LN + 30) for x, l in sel)
        (ax, ay), (bx, by) = pts[0], pts[-1]
        ang = math.degrees(math.atan2(by - ay, bx - ax))
        length = math.hypot(bx - ax, by - ay) + 150
        hgt = 62 + max(abs(y - (ay + (by - ay) * (x - ax) / max(1, bx - ax))) for x, y in pts) * 2
        cx, cy = (ax + bx) / 2, (ay + by) / 2
        ring = ('<div class="kring" style="left:calc(%.2f%% - %dpx);top:%dpx;width:%dpx;height:%dpx;'
                'transform:rotate(%.1fdeg)"></div>' % (cx / 940 * 100, length / 2, cy - hgt / 2, length, hgt, ang))
    for x, l in [(x, l) for r, x, l in cells if r["ub"] in CIRCLE2.get(globals().get("_CUR_RNO"), set())]:
        ring += ('<div class="kring k2" style="left:calc(%.2f%% - 14px);top:%dpx;width:158px;height:%dpx"></div>'
                 % (x / W * 100, 10 + l * LN - 8, LN - 2))
    turf = " turf" if globals().get("_CUR_SURF") == "芝" else ""
    legend = ""
    if ring:
        legend = ('<div class="klegend"><span class="lr"></span>赤丸＝狙い'
                  + ('<span class="lw"></span>白丸＝相手候補' if 'k2"' in ring else "") + '</div>')
    if yon:
        legend += ('<div class="knote">前後＝位置モデルの4角の予想。内外＝4角の併走の内外を学んだモデル(ほぼ馬番と騎手)を'
                   '4角の前後で当て直したもので、1枚目と同じ物差し(4角専用に作り込んではいない)</div>')
    return ('<div class="kboard%s"><div class="kdir">%s</div><div class="ktrack%s%s%s" style="height:%dpx"><div class="goal"></div><div class="kin">内（ラチ側）</div><div class="kout">外</div>%s</div>%s</div>'
            % (" kyon" if yon else "",
               ("4コーナー(直線を向いたところ)" if yon else
                first_corner_name(globals().get("_CUR_PLACE"), globals().get("_CUR_SURF"), globals().get("_CUR_DIST")))
               + ("　← 左が前（スタンドから見た向き）" if flip else "　右が前（スタンドから見た向き） →"), turf, " kflip" if flip else "",
               " kinv" if inv else "",
               max(1, len(lanes)) * LN + 24 + pad,
               (nk_bands(cells, rows, flip, W, yon, max(1, len(lanes)), LN) if (NANKAN and OBI) else "") + ring + "\n".join(hh), legend))


# ---- --nankan: 南関の図と同じ見せ方(ユーザー了承 2026-11-17「よいと思う！」) ----------------------
# 鞍の先頭に見出し(日付・場・馬場／展開予想／逃げ馬／道中で順位が上がる／上がり／穴 道中で下げない)、
# --obi を付けたときだけ盤面を前・中・後ろの帯(頭数で3等分)に薄く塗る。--nankan なしの HTML は前と1バイトも変わらない。
NANKAN = False
OBI = False   # --obi: --nankan の盤面に前・中・後ろの帯を塗る(既定は出さない。ユーザー 2026-11-17「あんまり帯意味ないね」)
NK_PAD = 20   # 盤面の上に帯のラベルを置く余白(px)。1角・4角の両方で同じだけ下げて高さを揃える


def nk_ranks(rows):
    """1角(pos1)と4角(pos)の鞍の中の順位(1=先頭)と、1角の順位の帯(0=前 1=中 2=後ろ、頭数で3等分)。両方そろう馬だけ。"""
    kn = [r for r in rows if r.get("pos1") is not None and r.get("pos") is not None]
    r1 = {r["ub"]: i + 1 for i, r in enumerate(sorted(kn, key=lambda r: (-r["pos1"], r["ub"])))}
    r4 = {r["ub"]: i + 1 for i, r in enumerate(sorted(kn, key=lambda r: (-r["pos"], r["ub"])))}
    band = {u: (v - 1) * 3 // max(1, len(kn)) for u, v in r1.items()}
    return r1, r4, band


def nk_ana(rows):
    """穴 道中で下げない(前で粘れる型): 1角で前の帯 かつ 4角の順位が1角の順位より後ろにならない予想。4角の順位順。
    人気は使わない(中央は人気を使わない決まり)。"""
    r1, r4, band = nk_ranks(rows)
    return sorted([u for u in r1 if band[u] == 0 and r4[u] <= r1[u]], key=lambda u: r4[u])


def nankan_head(fc, rows, rk, baba) -> str:
    """鞍の先頭の見出し。
    逃げ馬 = ハナ専用モデル(r["hana"])の1位
    道中で順位が上がる = 1角の順位 − 4角の順位(位置モデルの pos1・pos の鞍の中の順位)が正の馬、大きい順に5頭
    上がり = rk(同じ芝ダ・距離±400m の近5走の上がり順位の中央値。見解の「終い一番手」と同じ)の1〜3位
    穴 道中で下げない = nk_ana"""
    import datetime as dt
    circ = lambda u: "&#%d;" % (9311 + u) if 1 <= u <= 20 else str(u)  # noqa: E731
    nm = {r["ub"]: H.escape(r["name"]) for r in rows}
    date = globals().get("_CUR_DATE") or ""
    kick = ""
    if date:
        y, m, d = date.split("-")
        kick = "%s.%s.%s %s — %s／馬場 %s" % (y, m, d, WEEK[dt.date(int(y), int(m), int(d)).weekday()],
                                           globals().get("_CUR_PLACE") or "", baba or "-")
    r1, r4, band = nk_ranks(rows)
    hn = sorted([r for r in rows if r.get("hana") is not None], key=lambda r: -r["hana"])
    nige = ('<span class="nkh">%s%s</span>' % (circ(hn[0]["ub"]), nm[hn[0]["ub"]])) if hn else "—"
    ups = sorted([u for u in r1 if r1[u] - r4[u] > 0], key=lambda u: (-(r1[u] - r4[u]), r4[u]))[:5]
    up = "".join('<span class="nkh">%s%s <b>+%d</b></span>' % (circ(u), nm[u], r1[u] - r4[u]) for u in ups) or "—"
    top = sorted((u for u, v in rk.items() if v <= 3), key=lambda u: rk[u])
    ag = "".join('<span class="nkh"><i>%d位</i> %s%s</span>' % (rk[u], circ(u), nm[u]) for u in top) or "—"
    ana = "".join('<span class="nkh">%s%s</span>' % (circ(u), nm[u]) for u in nk_ana(rows)) or "該当なし"
    return ('<div class="nkhead"><div class="nkk">%s</div><div class="nkt">展開予想</div>'
            '<div class="nkr"><span class="nkl nk-b">逃げ馬</span>%s</div>'
            '<div class="nkr"><span class="nkl nk-r">▲ 道中で順位が上がる</span>%s</div>'
            '<div class="nkr"><span class="nkl nk-g">上がり</span>%s</div>'
            '<div class="nkr"><span class="nkl nk-y">穴 道中で下げない</span>%s</div></div>'
            % (kick, nige, up, ag, ana))


def nk_bands(cells, rows, flip, W, yon=False, nl=1, LN=76) -> str:
    """盤面の前・中・後ろの帯(頭数で3等分。1角は1角の順位、4角は4角の順位)。
    段(lane)ごとに境を置くので、同じ位置の馬が帯の境で切れない。境の目安は隣り合う帯の馬の絵の中心の中間で、
    その段の馬の絵がまたがるときは絵の端まで寄せる(階段状になる)。"""
    r1, r4, band = nk_ranks(rows)
    if yon:
        band = {u: (v - 1) * 3 // max(1, len(r4)) for u, v in r4.items()}
    FW = 76   # 馬の絵(矢印込み)の幅の目安
    cs = [(band[r["ub"]], x, l) for r, x, l in cells if r["ub"] in band]
    grp = [[x + FW / 2 for b, x, _ in cs if b == bb] for bb in range(3)]
    if not all(grp):
        return ""
    g = [((max(grp[b]) + min(grp[b + 1])) / 2 if flip else (min(grp[b]) + max(grp[b + 1])) / 2) for b in range(2)]
    H_ = nl * LN + 24 + NK_PAD
    out = []
    for i in range(nl):
        cuts = []
        for b in range(2):
            fr = [x for bb, x, l in cs if l == i and bb <= b]
            bk = [x for bb, x, l in cs if l == i and bb > b]
            if flip:   # 前が左
                lo, hi = (max(fr) + FW if fr else -1e9), (min(bk) if bk else 1e9)
            else:      # 前が右
                lo, hi = (max(bk) + FW if bk else -1e9), (min(fr) if fr else 1e9)
            cuts.append(min(max(g[b], lo), hi) if lo <= hi else (lo + hi) / 2)
        spans = ([(0, cuts[0]), (cuts[0], cuts[1]), (cuts[1], W)] if flip
                 else [(cuts[0], W), (cuts[1], cuts[0]), (0, cuts[1])])
        y0 = 0 if i == 0 else 10 + NK_PAD + i * LN - 6
        y1 = H_ if i == nl - 1 else 10 + NK_PAD + (i + 1) * LN - 6
        for b, (a, z) in enumerate(spans):
            lab = ('<span>%s %d頭</span>' % (("前の帯", "中の帯", "後ろの帯")[b], len(grp[b]))) if i == 0 else ""
            edge = " nkr0" if (b < 2 and flip) or (b > 0 and not flip) else ""
            out.append('<div class="nkband nkb%d%s" style="left:%.2f%%;width:%.2f%%;top:%dpx;height:%dpx">%s</div>'
                       % (b, edge, a / W * 100, max(0, z - a) / W * 100, y0, y1 - y0, lab))
    return "".join(out)


CSS_NANKAN = """.nkhead{padding:18px 22px 14px;border-bottom:3px solid #e8384f;margin-bottom:6px}
.nkk{color:#ff5a6e;font-size:13px;letter-spacing:.14em;font-weight:800}
.nkt{font-size:34px;font-weight:900;margin:4px 0 10px;color:#f2f2f4}
.nkr{display:flex;align-items:center;flex-wrap:wrap;gap:4px 18px;margin:6px 0;font-size:15px;font-weight:700;color:#f2f2f4}
.nkl{display:inline-block;min-width:150px;padding:3px 10px;border-radius:5px;font-size:13px;font-weight:900;color:#0c0c0e;text-align:center}
.nk-b{background:#5aa0ff}.nk-r{background:#ff5a6e}.nk-g{background:#56c271}.nk-y{background:#f2d231}
.nkh b{color:#ff8a98;margin-left:2px}.nkh i{font-style:normal;color:#9fe0b0;margin-right:2px}
.nkband{position:absolute;z-index:0;pointer-events:none}.nkband.nkr0{border-right:1px dashed rgba(255,255,255,.45)}
.nkband span{position:absolute;top:3px;left:8px;font-size:11.5px;font-weight:900;color:#fff;background:rgba(0,0,0,.42);padding:1px 7px;border-radius:3px;white-space:nowrap}
.nkb0{background:rgba(255,90,110,.16)}.nkb1{background:rgba(255,230,120,.10)}.nkb2{background:rgba(90,150,255,.16)}
.kana{display:inline-block;font-size:8.5px;color:#0c0c0e;background:#f2d231;border-radius:3px;padding:0 4px;margin:0 0 0 3px;font-weight:900}
"""


def kawa_memo(fc, rows, rk, dist, surface) -> str:
    """川崎の図の見解: 1段落。1角で前に行く馬・その後ろ・押し上げる馬・終い一番手。"""
    k = "pos1" if any(r.get("pos1") is not None for r in rows) else "pos"
    hs = sorted([r for r in rows if r.get(k) is not None], key=lambda r: -r[k])
    circ = lambda u: "&#%d;" % (9311 + u) if 1 <= u <= 20 else str(u)  # noqa: E731
    c1 = first_corner_name(globals().get("_CUR_PLACE"), surface, dist)
    out = []
    if hs:
        out.append("%s%dm、%sで前に行くのは%s" % (surface, dist, c1, "".join(circ(r["ub"]) for r in hs[:3])))
        if len(hs) > 5:
            out.append("その後ろに%s" % "".join(circ(r["ub"]) for r in hs[3:6]))
    # ハナ候補はハナ専用モデル(apply_hana_model → r["hana"])の上位3頭。
    # 過去の比較(notes/live/jra_hana_hikaku.md)で上位3頭にハナが入る率は pos1 の並びより4〜6pt良い
    hn = sorted([r for r in rows if r.get("hana") is not None], key=lambda r: -r["hana"])
    if hn:
        out.append("ハナ候補は%s" % "".join(circ(r["ub"]) for r in hn[:3]))
    ups = [r for r in rows if r.get("gain") is not None and r["gain"] >= 0.20]
    for r in sorted(ups, key=lambda r: -r["gain"])[:2]:
        out.append("%s%sは%s%.2fから4コーナー%.2fまで押し上げる型"
                   % (circ(r["ub"]), H.escape(r["name"]), c1, 1 - (r.get(k) or 0), 1 - (r.get("pos") or 0)))
    top = sorted((u for u, v in rk.items() if v <= 2), key=lambda u: rk[u])
    if top:
        out.append("終い一番手は%s" % "".join(circ(u) for u in top))
    nodata = [r for r in rows if r.get(k) is None]
    if nodata:
        out.append("%sは過去走が無く材料が薄い" % "".join(circ(r["ub"]) for r in nodata))
    return "。".join(out) + "。"


def simple_board(rows, fc, n, rk) -> str:
    """川崎の図(scripts/ana/zu.py)と同じ1枚の4角盤面。縦は内外の想定、狙う帯を赤い丸で囲む。"""
    lateral_layout(rows, fc, n, key="pos", band=0.07)   # outer_score を付けるため
    # 川崎の図と同じく、名前がぶつからない間隔(GAP)で段に振り分ける。内寄りの馬は上の段から、外寄りは2段目から探す
    hs = sorted([r for r in rows if r.get("pos") is not None], key=lambda r: -r["pos"])
    med = st.median(r.get("outer_score", 0) for r in hs) if hs else 0
    lanes, cells, gap = [], [], 168
    for r in hs:
        x = PAD + r["pos"] * (WID - 2 * PAD - 90)   # 右端の馬の名前が切れないように余白
        start = 0 if r.get("outer_score", 0) <= med else 1
        i = start
        while True:
            while len(lanes) <= i:
                lanes.append(1e9)
            if x < lanes[i] - gap:
                lanes[i] = x
                cells.append((r, x, i))
                break
            i += 1
    NL = max(1, len(lanes))
    sc = sorted(r["outer_score"] for r, _, _ in cells if "outer_score" in r)
    lo_q = sc[len(sc) // 4] if sc else 0
    hi_q = sc[3 * len(sc) // 4] if sc else 0
    hh = []
    for r, x, lane in cells:
        col, cc, t = "#d8c7ae", "#b9b9c4", ""
        osc = r.get("outer_score", 0)
        if r.get("gain") is not None and r["gain"] >= 0.20:
            if osc >= hi_q:
                col = cc = "#ff9f52"
                t = '<span class="upo">▲外から押し上げ</span>'
            elif osc <= lo_q:
                col = cc = "#5fe07a"
                t = '<span class="upi">▲内のまま押し上げ</span>'
            else:
                col = cc = "#6fc0ff"
                t = '<span class="upq">▲押し上げ</span>'
        elif r.get("gain") is not None and r["gain"] <= -0.20:
            t = '<span class="dn">▼下がる</span>'
        so = '<span class="sm">終い%d位</span>' % rk[r["ub"]] if rk.get(r["ub"], 99) <= 3 else ""
        if "outer_score" in r and osc <= lo_q and "upi" not in t:
            so += '<span class="sin">内に入りがち</span>'
        elif "outer_score" in r and osc >= hi_q and "upo" not in t:
            so += '<span class="so">外に出せる</span>'
        so += kikou_tag(r["ub"])
        wc = WAKU.get(r["waku"], ("#15110d", "#f2f2f4"))
        img = uma_img(r["waku"], r["ub"])
        fig = ('<img class="uma" src="%s" alt="">' % img) if img else HORSE.format(c=col)
        hh.append('<div class="horse wide" style="left:%dpx;top:%dpx"><div class="fig">%s%s</div>'
                  '<div class="lab"><span class="n" style="background:%s;color:%s;border-color:%s">%d</span>'
                  '<span class="nm">%s</span></div>%s%s</div>'
                  % (int(x), 14 + lane * LANE, fig, CHEV.format(c=cc), wc[0], wc[1],
                     "#00000055" if r["waku"] == 1 else "rgba(255,255,255,.45)", r["ub"], H.escape(r["name"]), t, so))
    zone, fc.zone_horses = draw_zone(cells, fc, ellipse=True)
    return ('<div class="board"><div class="ylab"><span>内（ラチ側）</span><span>外</span></div>'
            '<div class="track" style="height:%dpx"><div class="goal"></div>%s%s</div></div>'
            '<div class="xlab"><span>後方</span><span>中団</span><span>前　→　ゴール</span></div>'
            % (NL * LANE + 24, zone, "\n".join(hh)))


def stage_board(rows, fc, n, key, prev, label, rk) -> str:
    """1時点ぶんの隊列盤面(横=前後、縦=内外)。前の時点から3頭分以上順位が動いた馬に印。"""
    cells, _ = lateral_layout(rows, fc, n, key=key, band=0.07)
    NL = max(1, max((lane for _, _, lane in cells), default=0) + 1)
    rank = lambda k: {r["ub"]: i for i, r in enumerate(sorted([r for r in rows if r.get(k) is not None],  # noqa: E731
                                                             key=lambda r: -r[k]))}
    now, before = rank(key), (rank(prev) if prev else {})
    hh = []
    for r, x, lane in cells:
        col, cc, t = "#d8c7ae", "#b9b9c4", ""
        if prev and r["ub"] in before:
            mv = before[r["ub"]] - now[r["ub"]]
            if mv >= 3:
                col = cc = "#6fc0ff"
                t = '<span class="upq">▲%d頭分上げる</span>' % mv
            elif mv <= -3:
                t = '<span class="dn">≪%d頭分下げる</span>' % -mv
        so = '<span class="sm">終い%d位</span>' % rk[r["ub"]] if key == "pos" and rk.get(r["ub"], 99) <= 3 else ""
        wc = WAKU.get(r["waku"], ("#15110d", "#f2f2f4"))
        hh.append('<div class="horse" style="left:%dpx;top:%dpx"><div class="fig">%s%s</div>'
                  '<div class="lab"><span class="n" style="background:%s;color:%s;border-color:%s">%d</span>'
                  '<span class="nm">%s</span></div>%s%s</div>'
                  % (int(x), 14 + lane * LANE, uma_fig(r["waku"], r["ub"], col), CHEV.format(c=cc), wc[0], wc[1],
                     "#00000055" if r["waku"] == 1 else "rgba(255,255,255,.45)", r["ub"],
                     H.escape(r["name"][:4]) + ('<span class="jk">%s</span>' % H.escape((r.get("jockey") or "")[:4])
                                                if r.get("jockey") else ""), t, so))
    zone = ""
    if key == "pos":
        zone, fc.zone_horses = draw_zone(cells, fc)
    return ('<div class="stg">%s</div><div class="board"><div class="ylab"><span>内（ラチ側）</span><span>外</span></div>'
            '<div class="track" style="height:%dpx"><div class="goal"></div>%s%s</div></div>'
            '<div class="xlab"><span>後方</span><span>中団</span><span>前　→　ゴール</span></div>'
            % (label, NL * LANE + 24, zone, "\n".join(hh)))


# 想定ペースごとの狙う帯(3年分の検証: 4角前1/3にいた穴=7番人気以下の3着内率)
#   スロー: 内(併走の最内)15.3% > 2頭目以降11.9% > 外の列9.4%   → 前1/3 × 内(組の1〜2頭目)
#   ミドル: 外の列19.3% > 2頭目以降14.9% > 内11.8%             → 前1/3 × 外(組の2頭目以降)
#   ハイ:   外の列23.9% > 2頭目以降19.5% > 内14.3%             → 前1/3 × 外(組の2頭目以降)
EXTRA: dict = {}
ME_RACE = None       # --from-data のときの今回の鞍(ペースの LightGBM に使う)
ME_PAST: dict = {}
DAY_SHAPE = None     # 当日それより前のレースの「1〜3着の4角位置の平均」(0=前〜1=後ろ), 鞍数      # 馬番 → 今回の斤量・馬体重(分かるときだけ)
STYLE = "simple"     # simple = 川崎の図と同じ1枚の4角盤面＋赤丸／stages = 3段
ZONE_FRONT = 0.4   # 帯の前後の幅(前から何割)。--zone-front で変えられる。0.5 なら 帯の3着内率34.4%・1〜3着が全部入る31%
ZONE_RULE = {"スロー": ("内", "前%d割 × 内寄り", "検証: 3着内31%・鞍平均の1.32倍、穴 内11.1% 対 外9.5%"),
             "ミドル": ("両", "前%d割(内外とも)", "検証: 3着内30%・鞍平均の1.40倍、内外の差はほぼ無し"),
             "ハイ": ("外", "前%d割 × 外寄り", "検証: 3着内31%・鞍平均の1.51倍、穴 外11.6% 対 内9.2%")}


def draw_zone(cells, fc, ellipse=False):
    """4角の盤面に、想定ペースの狙う帯を金色の点線で囲む。返り値: (html, 帯に入った馬番)"""
    rule = ZONE_RULE.get(fc.pace)
    if not rule:
        return "", []
    side, lab, why = rule
    # 学習した帯(scripts/jra_zone_kenkyu.py → models/zone_rule.json)があればそれを使う
    import json
    zr_path = ROOT / "models" / "zone_rule.json"
    zr = json.load(open(zr_path)) if zr_path.exists() else {}
    key = {"スロー": "S", "ミドル": "M", "ハイ": "H"}[fc.pace]
    front_frac = ZONE_FRONT
    if key in zr and ZONE_FRONT == 0.4:      # --zone-front を指定していなければ学習した帯
        front_frac, side = zr[key][0], {"内": "内", "外": "外", "両方": "両"}[zr[key][1]]
    fc.zone_front = front_frac
    if not cells:          # 新馬戦など、過去走のある馬がいない
        return "", []
    xs = sorted({x for _, x, _ in cells}, reverse=True)
    n = len(cells)
    # 前4割まで(3年分のスロー想定3,273鞍: 前1/3→前4割で 帯の3着内率 36.8→36.0%、1〜3着が全部帯に入る鞍 13.9→21.7%)
    front = sorted(cells, key=lambda c: -c[1])[: max(1, round(n * front_frac))]
    fx = min(c[1] for c in front)
    if all("outer_score" in c[0] for c in front):   # 内外は外度(馬番+騎手)の中央値で分ける(学習と同じ)
        med = st.median(c[0]["outer_score"] for c in front)
        sel = [c for c in front if side == "両" or (side == "内" and c[0]["outer_score"] <= med)
               or (side == "外" and c[0]["outer_score"] > med)]
    else:
        sel = [c for c in cells if c[1] >= fx and ((c[2] <= 1) if side == "内" else (c[2] >= 1))]
    if not sel:
        return "", []
    left = max(4, min(c[1] for c in sel) - 70)
    right = min(WID + 36, max(c[1] for c in sel) + 70)
    top = 14 + min(c[2] for c in sel) * LANE - 8
    bottom = 14 + max(c[2] for c in sel) * LANE + 80
    if ellipse:
        left, right = max(0, left - 30), min(WID - 10, right + 40)
        top, bottom = max(0, top - 6), bottom + 6
        html = ('<div class="ring" style="left:%dpx;width:%dpx;top:%dpx;height:%dpx"></div>'
                % (left, right - left, top, bottom - top))
    else:
        html = ('<div class="zone" style="left:%dpx;width:%dpx;top:%dpx;height:%dpx">'
                '<div class="zlab">%s想定の狙い</div></div>'
                % (left, right - left, top, bottom - top, fc.pace))
    return html, [c[0]["ub"] for c in sorted(sel, key=lambda c: -c[1])]


KANGAE = {
    "スロー": ("前半がゆったり流れ、<b>先行力</b>が問われる一戦になりそうです。"
              "前で運べる馬が残りやすく、後ろの馬は届きにくい形です"
              "(検証: スロー想定で隊列予想の前1/3は3着内31%、後1/3は18%)。"
              "前の組では<b>内で脚をためられる馬</b>が有利になりやすい流れです"
              "(4角前1/3の穴: 内15% 対 外の列9%)。"),
    "ミドル": ("<b>先行力と末脚の両方</b>が求められる展開になりそうです。"
              "前の組が基本ですが、中団から<b>外へ持ち出して伸びる馬</b>も届きます"
              "(検証: 4角後ろ半分では外12% 対 内8%)。"),
    "ハイ": ("前半から流れ、<b>位置を取りに行く脚</b>と<b>しぶとさ</b>が問われる展開になりそうです。"
            "ただし中央では、ハイ想定でも隊列予想の前1/3が最も来ています(28% 対 後1/3は12%)。"
            "差すなら<b>外を回した馬</b>です(4角前1/3の穴: 外の列24% 対 内14%)。"),
}


def course_pace(place, surface, dist):
    """コース(場×芝ダ×距離)の3年間の スロー/平均/ハイ の割合(models/course_pace.json)。"""
    import json
    p = ROOT / "models" / "course_pace.json"
    if not (p.exists() and place and surface and dist):
        return None
    C = json.load(open(p))["courses"]
    me = C.get(f"{place}|{surface}|{dist}")
    if me and me["n"] >= 20:
        return me
    # 鞍数が少ないコースは、同じ場・芝ダで距離±200mのコースとまとめる(例: 東京芝2500m ← 2400m)
    near = [v for k, v in C.items() if k.startswith(f"{place}|{surface}|") and abs(int(k.split("|")[2]) - dist) <= 200]
    n = sum(v["n"] for v in near)
    if n < 20:
        return me
    out = {k: sum(v[k] * v["n"] for v in near) / n for k in ("S", "M", "H")}
    out.update(n=n, near=True)
    return out


def make_memo_simple(fc, rows, rk, name, dist, surface) -> str:
    """川崎の図の見解と同じ書き方: 先頭争い → 囲みの馬を1頭ずつ材料で → 距離延長の頭数 → 末脚。"""
    by = {r["ub"]: r for r in rows}
    nm = lambda u: "%s%s" % (chr(0x2460 + u - 1) if u <= 20 else str(u), by[u]["name"])  # noqa: E731
    lines = []
    est = getattr(fc, "est", None)
    cp = course_pace(getattr(fc, "_place", None), getattr(fc, "_surface", None), getattr(fc, "_dist", None))
    if cp:
        top = max(("S", "M", "H"), key=lambda k: cp[k])
        hard = cp[top] < 0.5
        lines.append("<b>このコース%sの3年間のペース</b>: スロー%.0f%%・平均%.0f%%・ハイ%.0f%%(%d鞍)。%s"
                     % ("(近い距離とまとめて)" if cp.get("near") else "", cp["S"] * 100, cp["M"] * 100, cp["H"] * 100, cp["n"],
                        "<b>どれにも偏らない読みにくいコース</b>。想定の確度に注意。" if hard else
                        ("ほぼ%sで決まるコース。" % {"S": "スロー", "M": "平均", "H": "ハイ"}[top] if cp[top] >= 0.8 else "")))
    lines.append("<b>%sペース想定</b>(確度 %s%s)。%s"
                 % (fc.pace, getattr(fc, "conf", "-"),
                    ("、推定前半3F %.1f・後半3F %.1f" % (est["front3"], est["last3"])) if est else "",
                    {"スロー": "前に行った馬がそのまま残りやすい流れ。",
                     "ミドル": "前の組が基本で、中団から外へ持ち出す馬も届く。",
                     "ハイ": "前半から流れるが、前の組がいちばん来る。差すなら外。"}[fc.pace]))
    hn = sorted([r for r in rows if "hana" in r], key=lambda r: -r["hana"])
    if len(hn) >= 3:
        gap = hn[0]["hana"] - hn[1]["hana"]
        lines.append("<b>先頭を主張するのは %s</b>。%s"
                     % ("・".join(nm(r["ub"]) for r in hn[:3]),
                        "%sが行き切れそう。" % nm(hn[0]["ub"]) if gap >= 0.08 else "これだけ並ぶと誰が引くかは読みにくい。"))
    kin = [EXTRA[u]["kinryo"] for u in by if EXTRA.get(u, {}).get("kinryo")]
    wts = [EXTRA[u]["weight"] for u in by if EXTRA.get(u, {}).get("weight")]
    if DAY_SHAPE:
        # scripts/jra_day_bias.py: 当日の前のレースの平均を三等分した境目は 0.20 / 0.27
        v, k = DAY_SHAPE
        if v > 0.274:
            lines.append("<b>今日は差しの日</b>(前の%d鞍の1〜3着は4角で平均%.0f%%の位置)。差しの日は"
                         "<b>前×内が割引</b>(鞍平均の1.30倍→1.14倍)、前×外は落ちない。" % (k, v * 100))
        elif v <= 0.201:
            lines.append("<b>今日は前残りの日</b>(前の%d鞍の1〜3着は4角で平均%.0f%%の位置)。前の組は内外とも鞍平均の1.30倍。"
                         % (k, v * 100))
    if getattr(fc, "zone_horses", []) and fc.pace in ZONE_RULE:
        lines.append("<b>赤丸は %s</b>(%s)。"
                     % (ZONE_RULE[fc.pace][1] % round(getattr(fc, "zone_front", ZONE_FRONT) * 10), ZONE_RULE[fc.pace][2]))
    for u in getattr(fc, "zone_horses", []):
        r = by[u]
        bits = []
        last = r.get("last")
        if last:
            dd = dist - last["dist"]
            bits.append("前走%s%s%dm %d着%s" % (last["place"], last["surface"] or "", last["dist"], last["fin"],
                                             ("(%+dm)" % dd) if dd else ""))
        e = EXTRA.get(u, {})
        if e.get("weight") and wts:
            bits.append("%dkg(平均比%+d%s)" % (e["weight"], round(e["weight"] - st.mean(wts)),
                                           ("・増減%+d" % e["dw"]) if e.get("dw") else ""))
        if e.get("kinryo") and kin:
            dk = e["kinryo"] - st.mean(kin)
            if abs(dk) >= 1:
                bits.append("斤量%.1fkg(平均比%+.1f)" % (e["kinryo"], dk))
        js = jockey_stat(r.get("jockey"))
        if js:
            bits.append("%s(前付け%+.0f%%)" % (js["name"], js["front_bias"] * 100))
        tag = []
        if rk.get(u, 99) <= 3:
            tag.append("<b>終い%d位</b>" % rk[u])
        if r.get("gain") is not None and r["gain"] >= 0.2:
            tag.append("押し上げ(%+.2f)" % r["gain"])
        lines.append("<b>%s</b>%s ── %s。" % (nm(u), ("は" + "・".join(tag)) if tag else "", "、".join(bits)))
    ext = [r for r in rows if r.get("last") and dist - r["last"]["dist"] >= 200]
    if ext:
        lines.append("<b>%d頭中%d頭が距離延長</b>(%s)。延長の馬は前に行きやすい(隊列の学習で係数 −0.1〜−0.2)。"
                     % (len(rows), len(ext), "・".join("%s%+dm" % (chr(0x2460 + r["ub"] - 1), dist - r["last"]["dist"])
                                                     for r in sorted(ext, key=lambda r: r["ub"]))))
    top = sorted(rk, key=rk.get)[:3]
    if top:
        lines.append("末脚上位は %s。%s" % ("・".join(nm(u) for u in top),
                                       "スローでは前の組に絡めるかが鍵。" if fc.pace == "スロー" else "外から届く余地あり。"))
    return "".join("<p>%s</p>" % x for x in lines)


def make_memo(fc, rows, rk, name: str = "") -> str:
    by = {r["ub"]: r for r in rows}
    nm = lambda u: "%s%s" % (chr(0x2460 + u - 1) if u <= 20 else str(u), by[u]["name"])  # noqa: E731
    lines = []
    if getattr(fc, "diff_pred", None) is not None and "pos1" in next(iter(by.values()), {}):
        title = re.sub(r"\(.*?\)", "", name) or "このレース"
        est = getattr(fc, "est", None)
        t = ("推定前半3F %.1f・後半3F %.1f" % (est["front3"], est["last3"])) if est else ""
        lines.append("<b>%sは%sペースが予想されます</b>(確度 %s%s)。%s"
                     % (H.escape(title), fc.pace, getattr(fc, "conf", "-"), ("、" + t) if t else "", KANGAE[fc.pace]))
        r1 = sorted([r for r in rows if "pos1" in r], key=lambda r: -r["pos1"])
        hn = sorted([r for r in rows if "hana" in r], key=lambda r: -r["hana"])
        if len(hn) >= 3:
            gap = hn[0]["hana"] - hn[1]["hana"]
            lines.append("スタートダッシュで<b>先頭を奪う可能性が高いのは %s</b>(ハナ確度 %s)。"
                         "ハナはこの3頭のどれか ── %s(検証: 上位3頭に入る 64%%)。"
                         % (nm(hn[0]["ub"]), "高" if gap >= 0.08 else ("中" if gap >= 0.03 else "低"),
                            "・".join(nm(r["ub"]) for r in hn[:3])))
        elif r1:
            lead = r1[0]
            lines.append("スタートダッシュで<b>先頭を奪う可能性が高いのは %s</b>。続くのは %s。"
                         % (nm(lead["ub"]), "・".join(nm(r["ub"]) for r in r1[1:3])))
        r4 = sorted([r for r in rows if "pos1" in r], key=lambda r: -r["pos"])
        rk1 = {r["ub"]: i for i, r in enumerate(r1)}
        steady = [r for r in r4[:6] if abs(rk1[r["ub"]] - r4.index(r)) <= 1][:3]
        if steady:
            lines.append("3コーナーから4コーナーにかけて<b>前で安定した位置取り</b>ができそうなのは %s。"
                         % "・".join(nm(r["ub"]) for r in steady))
        up = sorted([r for r in rows if "pos1" in r and rk1[r["ub"]] - r4.index(r) >= 3],
                    key=lambda r: r4.index(r) - rk1[r["ub"]])[:3]
        if up:
            lines.append("道中で位置を上げてくるのは %s。" % "・".join(nm(r["ub"]) for r in up))
        zh = getattr(fc, "zone_horses", [])
        if zh and fc.pace in ZONE_RULE:
            lines.append("<b>%s想定で狙う帯(図の金色の囲み)は %s</b> ── %s。%s"
                         % (fc.pace, ZONE_RULE[fc.pace][1] % round(getattr(fc, "zone_front", ZONE_FRONT) * 10), "・".join(nm(u) for u in zh),
                            ZONE_RULE[fc.pace][2] + "(3年分の検証)。"))
        js = [(r, jockey_stat(r.get("jockey"))) for r in rows]
        js = [(r, j) for r, j in js if j and j["n"] >= 100]
        if js:
            fw = sorted([x for x in js if x[1]["front_bias"] <= -0.02], key=lambda x: x[1]["front_bias"])[:3]
            bk = sorted([x for x in js if x[1]["front_bias"] >= 0.03], key=lambda x: -x[1]["front_bias"])[:3]
            fmt = lambda x: "%s(%s %+.0f%%)" % (nm(x[0]["ub"]), x[1]["name"], x[1]["front_bias"] * 100)  # noqa: E731
            sj = []
            if fw:
                sj.append("<b>前に行かせる騎手</b>は " + "・".join(fmt(x) for x in fw))
            if bk:
                sj.append("<b>控える騎手</b>は " + "・".join(fmt(x) for x in bk))
            best = sorted(js, key=lambda x: -x[1]["top3"])[:3]
            sj.append("騎手の3着内率上位は " + "・".join("%s(%s %.0f%%)" % (nm(r["ub"]), j["name"], j["top3"] * 100)
                                                  for r, j in best))
            lines.append("。".join(sj) + "(3年分。%は乗った馬のいつもの位置からのずれ、−が前)。")
        top = sorted(rk, key=rk.get)[:3]
        if top:
            lines.append("<b>末脚</b>(近走の上がり)上位は %s。%s"
                         % ("・".join(nm(u) for u in top),
                            "スローでは届きにくく、前の組に絡めるかが鍵です。" if fc.pace == "スロー" else
                            "流れが落ち着かなければ上位進出の可能性があります。"))
        return "".join("<p>%s</p>" % x for x in lines)
    if getattr(fc, "diff_pred", None) is not None:
        lines.append("<b>流れは%s想定(前後半差 %+.2f秒)。</b>学習(1,000鞍超)では、ペースは距離・直線・頭数・芝ダで"
                     "ほぼ決まり、逃げ馬の頭数はほとんど効かなかった。"
                     % (fc.pace, fc.diff_pred))
        if fc.leaders:
            lines.append("ハナ候補は %s。" % "・".join(nm(u) for u in fc.leaders))
    elif fc.leaders:
        if fc.lone_leader is not None:
            lines.append("<b>%s の単騎逃げが濃厚。</b>競りかける馬がおらず、流れは落ち着きやすい。"
                         % nm(fc.lone_leader))
        else:
            lines.append("<b>ハナを主張するのが%d頭(%s)。</b>序盤から競り合いになる形。"
                         % (len(fc.leaders), "・".join(nm(u) for u in fc.leaders)))
    front = [u for u in fc.order[:6] if u not in fc.leaders][:4]
    if front:
        lines.append("その後ろに %s。先行勢が厚い。" % "・".join(nm(u) for u in front)
                     if len(front) >= 3 else "番手は %s。" % "・".join(nm(u) for u in front))
    top = sorted(rk, key=rk.get)[:3]
    if top:
        lines.append("<b>終い上位3頭は %s。</b>" % "・".join(nm(u) for u in top))
    fav = sorted(rows, key=lambda r: -r["adv"])[:4]
    unf = sorted(rows, key=lambda r: r["adv"])[:3]
    lines.append("展開が向くのは %s。向かないのは %s。"
                 % ("・".join(nm(r["ub"]) for r in fav), "・".join(nm(r["ub"]) for r in unf)))
    ups = [r for r in rows if r["gain"] is not None and r["gain"] >= 0.20]
    if ups:
        lines.append("1角→4角で押し上げるのは %s。" % "・".join(
            "%s(%+.2f)" % (nm(r["ub"]), r["gain"]) for r in sorted(ups, key=lambda r: -r["gain"])))
    return "".join("<p>%s</p>" % s for s in lines)


CSS_EXTRA = """
.sm{display:inline-block;font-size:9.5px;color:#0c0c0e;background:#5fe07a;border-radius:3px;padding:0 5px;font-weight:800;margin-top:2px}
.rd b{color:#f2f2f4}
.pbar{margin:12px 16px 6px;padding:10px 14px;border-radius:8px;border:1px solid}
.pbar.p-slow{border-color:rgba(57,135,229,.45)}.pbar.p-mid{border-color:rgba(216,168,74,.45)}.pbar.p-high{border-color:rgba(232,54,47,.5)}
.bar{position:relative;display:flex;height:20px;border-radius:4px;overflow:hidden}
.bar span{flex:1;text-align:center;font-size:10.5px;line-height:20px;color:#c9c9d2}
.bar span:nth-child(1){background:#26344a}.bar span:nth-child(2){background:#3b3022}.bar span:nth-child(3){background:#4a1f1f}
.bar i{position:absolute;top:-2px;width:4px;height:24px;background:#fff;border-radius:2px;transform:translateX(-50%)}
.kik{display:inline-block;font-size:9.5px;color:#0c0c0e;background:#8fd0ff;border-radius:3px;padding:0 5px;font-weight:800;margin:2px 0 0 3px}
.wind{margin-top:6px;font-size:12px;color:var(--dim)}.wind b{color:#9fd3ff}
.est{display:flex;gap:26px;margin-top:8px;font-size:12px;color:var(--dim)}.est b{color:#f2f2f4;font-size:16px;margin-left:6px}
.zone .zlab{left:auto;right:10px;top:auto;bottom:-12px}
.ring{position:absolute;border:5px solid rgba(232,40,40,.95);border-radius:50%;z-index:1;
 box-shadow:0 0 12px rgba(232,40,40,.55)}
.horse.wide{width:170px}
.kboard{margin:8px 16px}.ktrack{position:relative;background:#3a2f26;border-radius:4px;border-top:3px solid #ddd}
.ktrack.turf{background:repeating-linear-gradient(90deg,#3f7d3a 0 56px,#3a7536 56px 58px)}
.kh{position:absolute;width:auto}.kf{display:flex;align-items:center;height:42px}
.kf img.uk{height:40px;width:auto;filter:drop-shadow(0 1px 1px rgba(0,0,0,.5))}
.kc{font-size:19px;font-weight:900;margin-left:1px;letter-spacing:-3px}
.kl{display:flex;align-items:center;gap:3px;font-size:10.5px;color:#f2f2f4;font-weight:700;white-space:nowrap;
 text-shadow:0 1px 2px rgba(0,0,0,.9)}
.kn{display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;border-radius:50%;
 font-size:10px;font-weight:900;box-shadow:0 0 0 1.5px rgba(0,0,0,.5)}
.ktrack.kflip .goal{right:auto;left:24px}
.kin,.kout{position:absolute;right:calc(100% + 1px);writing-mode:vertical-rl;font-size:10.5px;line-height:13px;font-weight:800;color:#c9c9d2;letter-spacing:1px;white-space:nowrap}
.kin{top:2px}.kout{bottom:2px}
.race.yon2{width:1984px}.kpair{display:flex;gap:16px;margin:8px 16px}.kpair .kboard{flex:1;min-width:0;margin:0}.knote{font-size:10.5px;color:#9a9aa6;margin:6px 4px 0;line-height:1.5}
.kdir{font-size:11px;color:#9a9aa6;margin:0 2px 4px;font-weight:700}
.klegend{display:flex;align-items:center;gap:6px;margin:8px 4px 0;font-size:13px;font-weight:700;color:#f2f2f4}
.klegend span{display:inline-block;width:26px;height:14px;border-radius:50%;margin-left:12px}
.klegend .lr{border:3px solid rgba(232,40,40,.95);margin-left:0}.klegend .lw{border:3px solid #fff}
.kring.k2{border-color:rgba(255,255,255,.95);box-shadow:0 0 8px rgba(255,255,255,.5)}
.race.kawa.nopace .rh .pace,.race.kawa.nopace .kenkai,.race.kawa.nopace .bar i{display:none}
.tbase{margin-left:auto;padding:6px 14px;border:2px solid #d8a84a;border-radius:8px;color:#f2e2b8;font-size:13px;font-weight:700;white-space:nowrap}
.race.kawa .rd{white-space:nowrap}
.tbase b{font-size:22px;color:#ffd77a;margin-right:4px}
.tbase .lap{margin-left:14px;padding-left:14px;border-left:1px solid #d8a84a;font-size:14px;color:#f2f2f4;letter-spacing:.3px}
.kring{position:absolute;border:5px solid rgba(232,40,40,.95);border-radius:50%;
 box-shadow:0 0 12px rgba(232,40,40,.55);pointer-events:none;z-index:0}
.kh{z-index:2}
.klane{display:inline-block;font-size:8.5px;color:#0c0c0e;background:#ffb347;border-radius:3px;padding:0 4px;margin:0 0 0 3px;font-weight:800}
.lanebias{margin-top:4px;font-size:12px;color:#ffb347;font-weight:700}
.kbt{display:inline-block;font-size:8.5px;color:#e9e1d2;background:rgba(0,0,0,.28);border:1px solid #a89a84;border-radius:3px;padding:0 3px;margin:0 0 0 3px;line-height:1.25}
.kko{display:inline-block;font-size:8.5px;color:#cfe0ea;background:rgba(80,130,160,.22);border:1px solid #6f97ad;border-radius:3px;padding:0 3px;margin:0 0 0 3px;line-height:1.25}
.knd{display:inline-block;font-size:8.5px;color:#fff;background:#d9577a;border-radius:3px;padding:0 4px;margin:0 0 0 3px}
.kh .kik{font-size:8.5px;padding:0 3px;margin:0 0 0 3px}
.race.kawa .rd .st{color:#e8a33a;margin-right:8px;font-weight:700}
.race.kawa .rh{flex-wrap:wrap;row-gap:8px}
.are{display:inline-flex;flex-direction:column;align-items:flex-start;padding:4px 12px;border-radius:7px;line-height:1.25;white-space:nowrap}
.are b{font-size:15px;font-weight:900;letter-spacing:.5px}.are small{font-size:10.5px;font-weight:700;margin-top:1px}
.are.are-hot{background:#c8322b;border:2px solid #ff6a5c;color:#fff}.are.are-hot small{color:#ffe1dc}
.are.are-calm{background:#1d2a36;border:2px solid #6f97ad;color:#cfe0ea}.are.are-calm small{color:#9fb6c6}
.race.kawa .kenkai p{font-size:12px;line-height:1.7;margin:4px 0}
.ktrend{margin:4px 16px 0;padding:6px 12px;background:#17171c;border-radius:6px;border-left:3px solid #8a8a96;font-size:11.5px;color:#c9c9d2;line-height:1.65}
.ktrend p{margin:2px 0}.ktrend .ty{white-space:nowrap}.ktrend b{color:#f2f2f4}
.ktrend .kt{color:#b9b9c4}.ktrend .tl{display:inline-block;color:#ffd77a;font-weight:800;margin-right:8px}
.fig img.uma{height:46px;width:auto;filter:drop-shadow(0 2px 2px rgba(0,0,0,.45))}
.track.turf{background:repeating-linear-gradient(90deg,#3f7d3a 0 56px,#3a7536 56px 58px)}
.track.turf .nm{text-shadow:0 1px 3px rgba(0,0,0,.95),0 0 2px rgba(0,0,0,.9)}
.track.turf .n{box-shadow:0 0 0 2px rgba(0,0,0,.55)}
.track{overflow:hidden}
.jk{display:block;font-size:9px;color:#b9b9c4;font-weight:600;margin-top:-1px}
.stg{display:inline-block;margin:14px 16px 0;background:#2e4a2a;color:#e6f2df;font-weight:800;font-size:13px;padding:4px 16px;border-radius:14px}
.flow{margin-top:7px;font-size:12.5px}.flow small{color:var(--dim);font-size:11px}
.kenkai{margin:6px 16px 14px;border-left:3px solid var(--acc2);background:#121216;border-radius:6px;padding:10px 14px;
 font-size:12.6px;color:#c9c9d2;line-height:1.9}
.kenkai b{color:#f2f2f4}.kt{color:var(--acc2);font-size:11px;font-weight:800}
.hold{color:#f08d88}.sure{color:#9fb6cf;font-size:11.5px}
.miss{margin:0 16px 12px;font-size:11.5px;color:var(--dim)}
.note{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin-bottom:15px;
 font-size:12.5px;color:#c9c9d2;line-height:1.8}
.note b{color:#f2f2f4}.note .q{color:#6fc0ff;font-weight:800}
"""


# 内が下の盤面(507db35)の CSS。--uchi-ue のときは入れない(507db35 より前と同じ HTML になるように)
CSS_KINV = ".ktrack.kinv{border-top:none;border-bottom:3px solid #ddd}.ktrack.kinv .kin{top:auto;bottom:2px}.ktrack.kinv .kout{bottom:auto;top:2px}\n"


def _css_extra() -> str:
    nk = CSS_NANKAN if NANKAN else ""   # --nankan のときだけ末尾に足す
    if UCHI_UE:
        return CSS_EXTRA + nk
    i = CSS_EXTRA.index(".race.yon2{")   # 507db35 で入れた位置(.kin,.kout の次の行)に差し込む
    return CSS_EXTRA[:i] + CSS_KINV + CSS_EXTRA[i:] + nk


def page(date: str, place: str, rno: str, body: str, learned: bool = False) -> str:
    css_path = ROOT / "scripts" / "ana" / "zu.css"
    css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""
    y, m, d = date.split("-")
    import datetime as dt
    wd = WEEK[dt.date(int(y), int(m), int(d)).weekday()]
    if STYLE == "kawa":   # 川崎の図と同じ見出し
        return ('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>展開予想 %s %s</title>'
                '<style>%s%s</style></head><body>'
                '%s%s'
                '<div class="tail">印は買い目の保証ではありません。</div></body></html>'
                % (date, place, css, _css_extra(),
                   "" if NANKAN else
                   ('<div class="head"><div class="kicker">%s.%s.%s %s — %s</div><h1>展開予想</h1>'
                    '<div class="sub"><b>最初のコーナーでの隊列想定</b></div></div>' % (y, m, d, wd, place)),
                   body))
    return (
        '<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>展開予想 %s %sR</title>'
        '<style>%s%s</style></head><body>'
        '<div class="head"><div class="kicker">%s.%s.%s %s — %s</div><h1>展開予想 ／ %sR</h1>'
        '<div class="sub">%s<b>右が前</b>、馬番は枠の色'
        '(1白 2黒 3赤 4青 5黄 6緑 7橙 8桃)。</div></div>'
        '<div class="note"><span class="sm">終い○位</span> は同じ芝ダ・距離±400mの近5走の上がり順位(中央値)が'
        'この鞍で何番目に良いか(距離帯の違う上がりは使わない)。<span class="q">青＝1角から4角で押し上げる馬</span>。'
        '%s</div>'
        '%s<div class="tail">印は買い目の保証ではありません。レース当日以降の走は使っていません。</div>'
        '</body></html>'
        % (date, rno, css, _css_extra(), y, m, d, wd, place, rno,
           ("過去走の<b>4コーナー通過順</b>で隊列を組み、流れは<b>過去の中央の鞍から学習した"
            "「距離・直線・頭数・芝ダで決まる前後半差」</b>で読んだものです。" if learned else
            "過去走の<b>4コーナー通過順</b>で隊列を組み、<b>逃げ候補の数・先行勢の厚み・距離</b>と"
            "<b>直線の長さ</b>から流れを読んだものです。"),
           (("<b>縦は重なりを避けて段に分けたもの</b>。馬番と騎手から学習した「4角で外を回る度合い」(検証 相関+0.43)で"
             "内寄りと想定した馬を上の段から置いている。赤い丸がペース想定ごとの狙う帯。") if STYLE == "simple" else
            "<b>縦は4コーナーの内外の想定(上がラチ側)</b>。前後の想定が近い馬を横並びの組にし、組の中を"
            "馬番などから学習した「4角で外を回る度合い」で内→外に並べた(検証 相関+0.43)。"
            if LATERAL_MODEL.exists() else "縦の並びは重なりを避けただけで、内・外ではありません。"),
           body))


def main() -> None:
    ap = argparse.ArgumentParser(description="中央競馬 展開図")
    ap.add_argument("--race-id")
    ap.add_argument("--shutuba")
    ap.add_argument("--past")
    ap.add_argument("--date", default="")
    ap.add_argument("--place")
    ap.add_argument("--race-no")
    ap.add_argument("--day", help="YYYY-MM-DD。--place の1日分を1ページに(集めたデータから)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--jockey-stats", help="騎手の集計(jra_jockey.py の出力)。過去の鞍を描くときはその日より前で作ったものを渡す")
    ap.add_argument("--from-data", action="store_true", help="出馬表をネットから取らず、--pace-data の集めたデータから組み立てる")
    ap.add_argument("--style", choices=["kawa", "simple", "stages"], default="kawa",
                    help="simple=4角1枚+赤丸(川崎の図と同じ形) / stages=スタート後・3角・4角の3段")
    ap.add_argument("--zone-front", type=float, default=0.4, help="狙う帯の前後の幅(前から何割、既定0.4)")
    ap.add_argument("--base-time", help='時計の基準を手で決める(例 "1:11.8")。ラップ想定は出さない')
    ap.add_argument("--kikou", action="store_true", help="気候の札を出す(既定は出さない)")
    ap.add_argument("--base-day", help="時計の基準にする開催日 YYYY-MM-DD(カンマで複数)。同じ場・芝ダ・距離の実際の時計の中央値")
    ap.add_argument("--base-baba", help="時計の基準にする馬場(良/稍/重/不、カンマで複数)")
    ap.add_argument("--base-day-dirt", help="ダートの鞍の基準の開催日(書式は --base-day。指定が無ければ芝と同じ、空文字なら日を絞らない)")
    ap.add_argument("--base-baba-dirt", help="ダートの鞍の基準の馬場(書式は --base-baba。指定が無ければ芝と同じ、空文字なら絞らない)")
    ap.add_argument("--hide-pace", default="", help='ペース想定の札(右上のS/M/H)を消す R。"12" や "3,12"')
    ap.add_argument("--yon", nargs="?", const="all", default="",
                    help='4コーナー(直線を向いたところ)の盤面をもう1枚出す R。"12" や "3,12"、値なしか "all" で全鞍(既定は出さない)')
    ap.add_argument("--uchi-ue", action="store_true",
                    help="kawa の盤面を常に内(ラチ側)が上にする(507db35 より前の向き。既定は内外をスタンドから見た向きに合わせる)")
    ap.add_argument("--nankan", action="store_true",
                    help="南関の図と同じ見せ方(鞍の先頭に 逃げ馬/道中で順位が上がる/上がり/穴 道中で下げない の見出し、"
                         "--yon と組み合わせる想定。既定は出さない)")
    ap.add_argument("--obi", action="store_true",
                    help="--nankan の盤面を前・中・後ろの帯(頭数で3等分)に塗り、帯のラベルを付ける(既定は出さない)")
    ap.add_argument("--no-jiten", action="store_true",
                    help="各鞍の下の「データ: 11/15 東京 8Rまでの結果を反映」(当日の結果が何Rまで入っていたか)を出さない")
    ap.add_argument("--circle-each", action="store_true", help="赤丸を1頭ずつ付ける(まとめて1つにしない)")
    ap.add_argument("--circle2", default="", help='相手を白い丸で囲む馬。"7:15,10,8"')
    ap.add_argument("--circle", default="", help='手で赤丸を付ける馬。"12:6,12,15;3:8"(R:馬番)')
    ap.add_argument("--no-trend", action="store_true", help="盤面の下の「過去の傾向」欄を出さない(既定は出す)")
    ap.add_argument("--no-arekata", action="store_true",
                    help="見出しの荒れ方の札(先行過多・荒れ目/前残り・堅め/差し届き・荒れ目。scripts/jra_arekata.py)を出さない")
    ap.add_argument("--pace-data", help="jra_harvest の JSONL。指定すると学習したペースで描く")
    ap.add_argument("--kb", help="競馬ブックの厩舎の話(kb_jra.py の JSONL)。省略時は data/kb/danwa_<日付>.jsonl があれば使う")
    ap.add_argument("--no-kouho", action="store_true", help="候補の札(終い候補/押上候補)を出さない")
    ap.add_argument("--no-kb", action="store_true", help="厩舎の話の札(良◎/道悪○/道悪×/ハナ/控え)を出さない")
    ap.add_argument("--dump-kouho", help="丸の候補(位置・終い/押上・ハナ・厩舎の話の札)を鞍ごとに JSON で書き出す")
    ap.add_argument("--kb-debug", action="store_true", help="厩舎の話の札を、鞍ごとに「馬番: 札 ← 拾った語」で出す")
    a = ap.parse_args()
    global KB_PATH, KB_OFF, KB_DEBUG
    KB_PATH, KB_OFF, KB_DEBUG = a.kb, a.no_kb, a.kb_debug
    global KOUHO_OFF
    KOUHO_OFF = a.no_kouho
    global ZONE_FRONT, JOCKEY_STATS, STYLE
    STYLE = a.style
    global BASE_DAY, BASE_BABA, BASE_DAY_DIRT, BASE_BABA_DIRT, SHOW_KIKOU, CIRCLE_EACH
    CIRCLE_EACH = a.circle_each
    global SHOW_TREND
    SHOW_TREND = not a.no_trend
    global ARE_OFF
    ARE_OFF = a.no_arekata
    SHOW_KIKOU = a.kikou
    BASE_DAY = set(a.base_day.split(",")) if a.base_day else None
    BASE_BABA = set(a.base_baba.split(",")) if a.base_baba else None
    BASE_DAY_DIRT = _UNSET if a.base_day_dirt is None else (set(a.base_day_dirt.split(",")) if a.base_day_dirt else None)
    BASE_BABA_DIRT = _UNSET if a.base_baba_dirt is None else (set(a.base_baba_dirt.split(",")) if a.base_baba_dirt else None)
    HIDE_PACE.update(int(x) for x in a.hide_pace.split(",") if x.strip().isdigit())
    global YON_ALL, UCHI_UE, JITEN_OFF, NANKAN, OBI
    UCHI_UE = a.uchi_ue
    NANKAN = a.nankan
    OBI = a.obi
    JITEN_OFF = a.no_jiten
    YON_ALL = a.yon.strip() == "all"
    YON.update(int(x) for x in a.yon.split(",") if x.strip().isdigit())
    for part in filter(None, a.circle2.split(";")):
        rr, uu = part.split(":")
        CIRCLE2[int(rr)] = {int(x) for x in uu.split(",") if x}
    for part in filter(None, a.circle.split(";")):
        rr, uu = part.split(":")
        CIRCLE[int(rr)] = {int(x) for x in uu.split(",") if x}
    ZONE_FRONT = a.zone_front
    if a.jockey_stats:
        JOCKEY_STATS = Path(a.jockey_stats)

    if a.day:
        if not (a.pace_data and a.place):
            ap.error("--day には --pace-data と --place が要ります(集めたデータから組み立てる)")
        a.from_data, a.date = True, a.day
        ids = sorted({d["race_id"] for d in load_rows(a.pace_data) if d["date"] == a.day and d["place"] == a.place
                      and d.get("surface") in ("芝", "ダ")})   # 結果と出馬表の両方にある鞍は1回だけ
        bodies, kouho = [], []
        for rid in ids:
            a.race_id, a.race_no = rid, str(int(rid[-2:]))
            body, place, rno, fc = one_race(a, ap)
            bodies.append(body)
            kouho.append(kouho_of(fc, place))
            print(rno + "R", fc.summary())
        rno = "%s〜%sR" % (str(int(ids[0][-2:])), str(int(ids[-1][-2:]))) if ids else ""
        body = "\n".join(bodies)
        place = a.place
    else:
        body, place, rno, fc = one_race(a, ap)
        kouho = [kouho_of(fc, place)]
        print(fc.summary())
    if a.dump_kouho:
        import json
        Path(a.dump_kouho).parent.mkdir(parents=True, exist_ok=True)
        Path(a.dump_kouho).write_text(json.dumps(kouho, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(page(a.date, place, rno.rstrip("R"), body, learned=bool(a.pace_data)), encoding="utf-8")
    print("→", a.out)


KB_BABA = {"良": ("良◎",), "稍": ("良◎", "道悪○", "道悪×"), "重": ("道悪○", "道悪×"), "不": ("道悪○", "道悪×")}


def kouho_of(fc, place) -> dict:
    """丸の候補(表示だけ。予想は変えない)。
    位置: 予想4角(pos。1=先頭)の順位が、そのコースで1着の割合の高い上位2区分(course_pos の win)に入る馬
    終い/押上: r["kouho"]、ハナ: ハナ専用モデルの上位3頭、札: 厩舎の話のうちその日の馬場に関わるもの"""
    rows, baba = getattr(fc, "_rows", []), getattr(fc, "_baba", None)
    surface, dist = fc._surface, fc._dist
    out = {"place": place, "race": int(fc._rno) if str(fc._rno).isdigit() else fc._rno,
           "surface": surface, "dist": dist, "baba": baba, "n": len(rows)}
    try:
        from jra_course_pos import bucket, lookup
        _, cs = lookup(place, surface, dist, baba)
    except Exception:  # noqa: BLE001
        cs = None
    pos = []
    if cs:
        top2 = sorted(range(5), key=lambda i: -cs["win"][i])[:2]
        out["pos_buckets"] = [_BUCKET_LABEL[i].replace("番手", "") for i in sorted(top2)]
        known = sorted([r for r in rows if r.get("pos") is not None], key=lambda r: (-r["pos"], r["ub"]))
        pos = sorted(r["ub"] for i, r in enumerate(known) if bucket(i + 1) in top2)
    out["pos"] = pos
    out["n_known"] = sum(1 for r in rows if r.get("pos") is not None)
    out["shimai"] = sorted(r["ub"] for r in rows if "終い候補" in (r.get("kouho") or []))
    out["oshiage"] = sorted(r["ub"] for r in rows if "押上候補" in (r.get("kouho") or []))
    hn = sorted([r for r in rows if r.get("hana") is not None], key=lambda r: -r["hana"])
    out["hana"] = [r["ub"] for r in hn[:3]]
    kb = {}
    for r in sorted(rows, key=lambda r: r["ub"]):
        for t, _ in kb_list(r["ub"], r["name"]):
            if t in KB_BABA.get(baba or "良", ()):
                kb.setdefault(t, [])
                if r["ub"] not in kb[t]:
                    kb[t].append(r["ub"])
    out["kb"] = {t: kb[t] for t in KB_ORDER if t in kb}
    out["kb_day"] = bool(kb_load(globals().get("_CUR_DATE") or ""))
    from jra_arekata import FUDA
    out["arekata"] = [FUDA[k][0] for k in (getattr(fc, "arekata", None) or [])]
    return out


def one_race(a, ap):
    """1鞍ぶんを組み立てて (本文HTML, 場, R, fc) を返す。"""
    klass = None
    if a.race_id and a.pace_data and not a.shutuba and getattr(a, "from_data", False):
        past, waku, name, info, klass, _, place_d, jockeys = from_data(a.pace_data, a.race_id)
        sh = ""
        a.place = a.place or place_d
    elif a.shutuba and a.past:
        sh = Path(a.shutuba).read_text(encoding="utf-8", errors="replace")
        ps = Path(a.past).read_text(encoding="utf-8", errors="replace")
    elif a.race_id:
        from nankeiba.scraping.client import PoliteClient
        c = PoliteClient()
        sh = c.get(SHUTUBA_URL.format(race_id=a.race_id))
        ps = c.get(PAST_URL.format(race_id=a.race_id))
    else:
        ap.error("--race-id か (--shutuba と --past) を指定してください")

    if klass is None:
        waku, name, info = parse_shutuba(sh)
        jockeys = parse_jockeys(sh)
        past = parse_past(ps, a.date)
    place = a.place or (place_of(a.race_id) if a.race_id else "") or ""
    rno = a.race_no or (str(int(a.race_id[-2:])) if a.race_id else "")
    m = re.search(r"(芝|ダ)(\d{3,4})m", info)
    surface, dist = (m.group(1), int(m.group(2))) if m else ("芝", 0)
    bm = re.search(r"(良|稍|重|不)", info)
    baba = bm.group(1) if bm else None

    fc, rows, rk = build(past, waku, place=place, dist=dist, surface=surface, baba=baba, jockeys=jockeys)
    globals()["_CUR_SURF"] = surface
    globals()["_CUR_PLACE"] = place
    globals()["_CUR_DIST"] = dist
    globals()["_CUR_RNO"] = int(rno) if str(rno).isdigit() else None
    globals()["_DATA_PATH"] = a.pace_data
    globals()["_CUR_DATE"] = a.date or (ME_RACE or {}).get("date")
    kb_debug(rows)
    fc.lane = lane_bias(place, surface, a.date) if a.pace_data else (None, None, 0)
    fc.today = day_shape(place, surface, a.date, a.race_id) if a.pace_data else None
    if fc.today and fc.today["lanes"] >= 6 and fc.today["out"] is not None:   # 当日の内外が分かれば、それを優先
        sh = fc.today["out"]
        fc.lane = (("外" if sh >= 0.67 else "内" if sh <= 0.33 else None), sh, fc.today["lanes"])
    fc._start = (ME_RACE or {}).get("start") if getattr(a, "from_data", False) else None
    if a.pace_data:
        diff, nl, conf, q, est = learned_pace(a.pace_data, a.date, place=place, dist=dist, surface=surface,
                                         n=len(rows), baba=baba, race_id=a.race_id,
                                         klass=klass if klass is not None else parse_class(sh))
        fc.wind = wind_head(place, a.date, int(rno) if str(rno).isdigit() else 0)
        if fc.wind and fc.wind[0] is not None:   # 直線の向かい風1mにつき前後差 −0.05〜0.06秒(models/wind_head.json)
            diff += fc.wind[2]
        dl = pace_lgbm_diff(a.pace_data, a.date, fc, diff - (_toujitsu_weight("dp", 0.2) * 0))
        if dl is not None:
            diff = dl
            margin = min(abs(diff - q[0]), abs(diff - q[1]))
            conf = "高" if margin >= 0.78 else ("中" if margin >= 0.35 else "低")
            fc.pace_model = "LightGBM"
        apply_learned_pace(fc, rows, diff, q=q)
        if getattr(a, "base_time", None) and est:
            mm_, ss_ = a.base_time.split(":")
            est = dict(est, time=int(mm_) * 60 + float(ss_))
            est.pop("laps", None)
        fc.n_learn, fc.conf, fc.est, fc.q = nl, conf, est, q
    fc._place, fc._surface, fc._dist = place, surface, dist
    fc.trend = (trend_html(a.pace_data, a.date or (ME_RACE or {}).get("date"), place, surface, dist, name, baba)
                if (SHOW_TREND and STYLE == "kawa" and a.pace_data) else "")
    fc._rows, fc._baba, fc._rno = rows, baba, rno
    return render_race(rno, name, dist, surface, baba, len(rows), fc, rows, rk), place, rno, fc



if __name__ == "__main__":
    main()
