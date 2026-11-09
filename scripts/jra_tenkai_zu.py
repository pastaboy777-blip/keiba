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
  - 終い1〜3位 = 芝1800m以上の近走の上がり3F中央値が速い順(場・流れの補正なし)。
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


def build(past: dict, waku: dict, *, place: str, dist: int, surface: str, baba: str | None):
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
            "ub": u, "name": v["name"], "waku": waku.get(u),
            "pos": 1 - st.median(c4) if c4 else None,         # 1=前
            "gain": (st.median(c1) - st.median(c4)) if c4 else None,
            "l": st.median(ag) if ag else None,
            "e": st.median(es) if es else None,
            "adv": fc.advantage.get(u, 0.0), "style": fc.styles[u].style,
            "nige": fc.styles[u].nige_rate, "last": v["runs"][0] if v["runs"] else None,
        })
    rk = {r["ub"]: i + 1 for i, r in enumerate(sorted([r for r in rows if r["l"]], key=lambda r: r["l"]))}
    return fc, rows, rk


def learned_pace(data_path: str, before: str, *, place, dist, surface, n) -> tuple[float, int]:
    """条件(距離・直線・頭数・芝ダ)で決まる前後半差[秒]を、before より前の鞍だけで学習して返す。

    notes/live/jra_learn_01.md: ペースは条件でほぼ決まり(検証相関 +0.71)、
    逃げ率などメンバー構成の上乗せはゼロだった。+ は後半が速い(前半ゆったり)。
    """
    import json
    sys.path.insert(0, str(ROOT / "scripts"))
    import jra_learn as J
    from nankeiba.core import course as cs
    from nankeiba.scraping.db_race import pace_of
    X = lambda pl, di, su, fs: [1.0, di / 1000, cs.front_bias(pl, su), fs / 18, 1.0 if su == "芝" else 0.0]  # noqa: E731
    xs, ys = [], []
    for line in open(data_path, encoding="utf-8"):
        d = json.loads(line)
        if d.get("date", "") >= before or d.get("surface") not in ("芝", "ダ"):
            continue
        pc = pace_of(d.get("lap") or [], d["distance"])
        if pc:
            xs.append(X(d["place"], d["distance"], d["surface"], d["field_size"]))
            ys.append(pc["diff"])
    w = J.ols(xs, ys)
    return sum(a * b for a, b in zip(w, X(place, dist, surface, n))), len(ys)


def apply_learned_pace(fc, rows, diff: float, *, adv_scale: float = 0.6, lone_bonus: float = 0.15):
    """学習したペースで fc のペース表示と展開利を置き換える。

    コース形状は条件モデルに入っているので、展開利は「ペースの傾き」だけで決める
    (前後半差 + = 前半ゆったり = 前の馬に向く)。
    """
    fc.diff_pred = diff
    fc.pace_index = max(-1.0, min(1.0, -diff / 2))
    fc.pace = "ハイ" if diff <= -0.5 else ("スロー" if diff >= 0.5 else "ミドル")
    tilt = -fc.pace_index
    for u, sp in fc.styles.items():
        adv = adv_scale * (0.5 - sp.early_or()) * tilt
        if u == fc.lone_leader:
            adv += lone_bonus
        fc.advantage[u] = adv
    for r in rows:
        r["adv"] = fc.advantage.get(r["ub"], 0.0)


def render_race(rno, name, dist, surface, baba, n, fc, rows, rk) -> str:
    hs = sorted([r for r in rows if r["pos"] is not None], key=lambda r: -r["pos"])
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
            % (int(x), 14 + lane * LANE, HORSE.format(c=col), CHEV.format(c=cc), wc[0], wc[1],
               "#00000055" if r["waku"] == 1 else "rgba(255,255,255,.45)",
               r["ub"], H.escape(r["name"]), t, so))

    pcls, ptag = {"スロー": ("slow", "S"), "ミドル": ("mid", "M"), "ハイ": ("high", "H")}[fc.pace]
    mark = max(0.02, min(0.98, 0.5 + fc.pace_index * 0.667))
    flow = {
        "slow": "→ 前が楽。前で運べる馬が残る形",
        "mid": "→ 中団から前へ出てくる馬が届く",
        "high": "→ 前が垂れる。後ろから差せる形",
    }[pcls]
    es = sorted([r["e"] for r in rows if r["e"]], reverse=True)
    if getattr(fc, "diff_pred", None) is not None:
        flow_sub = ("条件(距離・直線・頭数・芝ダ)で決まる前後半差 %+.2f秒(%s)・%d鞍から学習"
                    % (fc.diff_pred, "後半が速い＝前半ゆったり" if fc.diff_pred > 0 else "前半が速い",
                       getattr(fc, "n_learn", 0)))
    elif len(es) >= 3:
        flow_sub = ("先頭圏3頭の前半速度 %.2fm/s(この鞍の中央値 %.2fm/s)・コース %s"
                    % (st.mean(es[:3]), st.median(es),
                       "差し有利" if fc.front_bias < -0.05 else ("前有利" if fc.front_bias > 0.05 else "平坦")))
    else:
        flow_sub = ""
    memo = make_memo(fc, rows, rk)
    missing = [r for r in rows if r["pos"] is None]
    miss = ""
    if missing:
        miss = ('<div class="miss">4角の記録なし … %s —— 測れないだけで、弱いという意味ではありません</div>'
                % "・".join("%d %s" % (r["ub"], H.escape(r["name"])) for r in missing))
    return (
        '<div class="race"><div class="rh"><span class="rn">%sR</span>'
        '<span class="rd">%s　<b>%s%dm</b> ／ %d頭 ／ %s</span>'
        '<span class="pace p-%s"><b>%s</b> %s想定</span></div>'
        '<div class="pbar p-%s"><div class="bar"><span>ゆっくり</span><span>ふつう</span><span>速い</span>'
        '<i style="left:%.1f%%"></i></div><div class="flow"><b>%s</b>　<small>%s</small></div></div>'
        '<div class="board"><div class="track" style="height:%dpx"><div class="goal"></div>%s</div></div>'
        '<div class="xlab"><span>後方</span><span>中団</span><span>前　→　ゴール</span></div>'
        '<div class="kenkai"><div class="kt">見解</div>%s</div>%s</div>'
        % (rno, H.escape(name), surface, dist, n, H.escape(baba or ""),
           pcls, ptag, fc.pace, pcls, mark * 100, flow, flow_sub,
           NL * LANE + 24, "\n".join(hh), memo, miss))


def make_memo(fc, rows, rk) -> str:
    by = {r["ub"]: r for r in rows}
    nm = lambda u: "%s%s" % (chr(0x2460 + u - 1) if u <= 20 else str(u), by[u]["name"])  # noqa: E731
    lines = []
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
.flow{margin-top:7px;font-size:12.5px}.flow small{color:var(--dim);font-size:11px}
.kenkai{margin:6px 16px 14px;border-left:3px solid var(--acc2);background:#121216;border-radius:6px;padding:10px 14px;
 font-size:12.6px;color:#c9c9d2;line-height:1.9}
.kenkai b{color:#f2f2f4}.kt{color:var(--acc2);font-size:11px;font-weight:800}
.miss{margin:0 16px 12px;font-size:11.5px;color:var(--dim)}
.note{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin-bottom:15px;
 font-size:12.5px;color:#c9c9d2;line-height:1.8}
.note b{color:#f2f2f4}.note .q{color:#6fc0ff;font-weight:800}
"""


def page(date: str, place: str, rno: str, body: str, learned: bool = False) -> str:
    css_path = ROOT / "scripts" / "ana" / "zu.css"
    css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""
    y, m, d = date.split("-")
    import datetime as dt
    wd = WEEK[dt.date(int(y), int(m), int(d)).weekday()]
    return (
        '<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>展開予想 %s %sR</title>'
        '<style>%s%s</style></head><body>'
        '<div class="head"><div class="kicker">%s.%s.%s %s — %s</div><h1>展開予想 ／ %sR</h1>'
        '<div class="sub">%s<b>右が前</b>、馬番は枠の色'
        '(1白 2黒 3赤 4青 5黄 6緑 7橙 8桃)。</div></div>'
        '<div class="note"><span class="sm">終い○位</span> は芝1800m以上の近走の上がり3F(中央値)が'
        'この鞍で何番目に速いか(場・流れの補正なし)。<span class="q">青＝1角から4角で押し上げる馬</span>。'
        '縦の並びは重なりを避けただけで、内・外ではありません。</div>'
        '%s<div class="tail">印は買い目の保証ではありません。レース当日以降の走は使っていません。</div>'
        '</body></html>'
        % (date, rno, css, CSS_EXTRA, y, m, d, wd, place, rno,
           ("過去走の<b>4コーナー通過順</b>で隊列を組み、流れは<b>過去の中央の鞍から学習した"
            "「距離・直線・頭数・芝ダで決まる前後半差」</b>で読んだものです。" if learned else
            "過去走の<b>4コーナー通過順</b>で隊列を組み、<b>逃げ候補の数・先行勢の厚み・距離</b>と"
            "<b>直線の長さ</b>から流れを読んだものです。"), body))


def main() -> None:
    ap = argparse.ArgumentParser(description="中央競馬 展開図")
    ap.add_argument("--race-id")
    ap.add_argument("--shutuba")
    ap.add_argument("--past")
    ap.add_argument("--date", required=True)
    ap.add_argument("--place")
    ap.add_argument("--race-no")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pace-data", help="jra_harvest の JSONL。指定すると学習したペースで描く")
    a = ap.parse_args()

    if a.shutuba and a.past:
        sh = Path(a.shutuba).read_text(encoding="utf-8", errors="replace")
        ps = Path(a.past).read_text(encoding="utf-8", errors="replace")
    elif a.race_id:
        from nankeiba.scraping.client import PoliteClient
        c = PoliteClient()
        sh = c.get(SHUTUBA_URL.format(race_id=a.race_id))
        ps = c.get(PAST_URL.format(race_id=a.race_id))
    else:
        ap.error("--race-id か (--shutuba と --past) を指定してください")

    waku, name, info = parse_shutuba(sh)
    past = parse_past(ps, a.date)
    place = a.place or (place_of(a.race_id) if a.race_id else "") or ""
    rno = a.race_no or (str(int(a.race_id[-2:])) if a.race_id else "")
    m = re.search(r"(芝|ダ)(\d{3,4})m", info)
    surface, dist = (m.group(1), int(m.group(2))) if m else ("芝", 0)
    bm = re.search(r"(良|稍|重|不)", info)
    baba = bm.group(1) if bm else None

    fc, rows, rk = build(past, waku, place=place, dist=dist, surface=surface, baba=baba)
    if a.pace_data:
        diff, nl = learned_pace(a.pace_data, a.date, place=place, dist=dist, surface=surface, n=len(rows))
        apply_learned_pace(fc, rows, diff)
        fc.n_learn = nl
    body = render_race(rno, name, dist, surface, baba, len(rows), fc, rows, rk)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(page(a.date, place, rno, body, learned=bool(a.pace_data)), encoding="utf-8")
    print(fc.summary())
    print("→", a.out)


if __name__ == "__main__":
    main()
