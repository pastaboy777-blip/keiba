"""当日の終わった鞍の結果を JRA公式から取り込み、展開図を作り直す(後半の鞍に「今日ここまでの傾向」が入る)。

    python3 scripts/jra_today.py --date 2026-11-15 --png
    python3 scripts/jra_today.py --date 2026-11-15 --png --baba 京都=重 --baba-dirt 京都=不   # 昼に馬場が変わった
    python3 scripts/jra_today.py --date 2026-11-15 --place 福島 --extra '--circle 7:11 --circle2 7:15,10'

1) 結果ページ(月 → 開催日 → レース)から、その日の終わった鞍を data/jra/races.jsonl に足す(3秒間隔、済みは飛ばす)
2) data/jra/all_YYYYMMDD.jsonl = 出馬表(data/jra/shutuba_YYYYMMDD.jsonl。先頭) + 取り込み後の races.jsonl
   - 出馬表の行を先に置く: jra_tenkai_zu.py は同じ race_id の最初の行をその鞍として使うので、
     終わった鞍も予想は出馬表の行で組まれ、結果(実際の頭数・馬場・着順)は混ざらない。
     結果の行は後ろにあり、後半の鞍の「今日ここまでの傾向」・ペースの当日のずれに使われる
   - 出馬表の行の馬場は朝の値(data/jra/morning_YYYYMMDD.json)で埋める。--baba/--baba-dirt があればそれで上書き
3) scripts/daily/zu_jra_YYYYMMDD_<場>.html を作り直す
   - data/jra/morning_YYYYMMDD.json(scripts/jra_morning.py が残す)があれば、場ごとに朝と同じ
     時計の基準・丸などで作る。--baba/--baba-dirt で馬場を変えた場は、時計の基準をその馬場で選び直す
   - 無ければ今までどおり(--extra だけ)
   - --extra は朝の引数の後ろに足す
4) --png で 1鞍ずつのPNG(data/zu_png/YYYYMMDD/<場>_<R>R.png)も作り直す。2分割(split)は作り直さない
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import jra_official_harvest as H  # noqa: E402
from jra_morning import BABA_LONG, base_args, parse_baba, shoot  # noqa: E402
from nankeiba.scraping.jra_official import links, month_checksums, parse_race, race_id_of  # noqa: E402


def fetch_results(ymd: str, data: Path) -> int:
    have = {json.loads(l)["race_id"] for l in open(data) if l.strip()}
    f = H.Fetcher(3.0)
    ck = month_checksums(f.post(H.SEARCH))
    yymm = ymd[2:6]
    new = 0
    with data.open("a", encoding="utf-8") as fo:
        for day in links(f.post(f"pw01skl00{ymd[:6]}/{ck[yymm]}"), "pw01srl"):
            if ymd not in day:
                continue
            for c in links(f.post(day), "pw01sde"):
                rid = race_id_of(c)
                if not rid or c[-11:-3] != ymd or rid in have:
                    continue
                d = parse_race(f.post(c), rid)
                if d and d["result"] and all(r.get("time") for r in d["result"][:3]) and d.get("lap"):
                    fo.write(json.dumps(d, ensure_ascii=False) + "\n")
                    have.add(rid)
                    new += 1
                    print("結果", d["place"], int(rid[-2:]), "R", flush=True)
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", help="作り直す場(省略で出馬表にある全場。カンマで複数)")
    ap.add_argument("--extra", default="", help="jra_tenkai_zu.py に渡す追加の引数(朝の設定の後ろに足す)")
    ap.add_argument("--baba", default="", help='芝の馬場を上書き "京都=重"(昼に馬場が変わったとき)')
    ap.add_argument("--baba-dirt", default="", help="ダートの馬場を上書き(書かない場は朝の値)")
    ap.add_argument("--png", action="store_true", help="1鞍ずつのPNGも作り直す")
    ap.add_argument("--no-fetch", action="store_true", help="結果を取りに行かず、作り直しだけ")
    a = ap.parse_args()
    ymd = a.date.replace("-", "")
    jra = ROOT / "data" / "jra"
    data = jra / "races.jsonl"
    over_t, over_d = parse_baba(a.baba), parse_baba(a.baba_dirt)
    if not a.no_fetch:
        try:
            print(f"新しく取り込んだ鞍 {fetch_results(ymd, data)}")
        except Exception as e:   # 取れなくても図の作り直しはする
            print(f"結果の取り込みに失敗: {e!r}", file=sys.stderr)

    sb = jra / f"shutuba_{ymd}.jsonl"
    shutuba = [json.loads(l) for l in open(sb, encoding="utf-8") if l.strip()]
    races_text = data.read_text(encoding="utf-8")
    races = [json.loads(l) for l in races_text.splitlines() if l.strip()]
    done = {d["race_id"] for d in races}

    mp = jra / f"morning_{ymd}.json"
    morning = json.loads(mp.read_text(encoding="utf-8")).get("places", {}) if mp.exists() else {}
    if morning:
        print("朝の設定:", mp.relative_to(ROOT))
    else:
        print("朝の設定なし(--extra だけで作ります)")
    turf = {p: m["turf"] for p, m in morning.items()} | over_t
    dirt = {p: m["dirt"] for p, m in morning.items()} | over_d
    fill = bool(morning or over_t or over_d)

    allp = jra / f"all_{ymd}.jsonl"
    with allp.open("w", encoding="utf-8") as fo:
        for d in shutuba:
            if fill:
                d = dict(d)
                p = d["place"]
                t = turf.get(p, "良")
                d["baba"] = dirt.get(p, t) if d.get("surface") == "ダ" else t
            fo.write(json.dumps(d, ensure_ascii=False) + "\n")
        fo.write(races_text)
        if races_text and not races_text.endswith("\n"):
            fo.write("\n")
    print(f"今日の結果あり {sum(1 for d in shutuba if d['race_id'] in done)}/{len(shutuba)} 鞍")

    places = sorted({d["place"] for d in shutuba})
    if a.place:
        places = [p for p in places if p in a.place.split(",")]
    pngdir = ROOT / "data" / "zu_png" / ymd
    if a.png:
        pngdir.mkdir(parents=True, exist_ok=True)
    for p in places:
        m = morning.get(p)
        args = []
        if m or p in over_t or p in over_d:
            t = turf.get(p, "良")
            dd = dirt.get(p, t)
            if m and p not in over_t and p not in over_d:
                args += m["base_args"]
                note = f"朝の基準(芝{BABA_LONG[t]}・ダ{BABA_LONG[dd]})"
            else:
                bb, desc = base_args(races, p, {"芝": t, "ダ": dd}, a.date)
                args += bb
                note = f"芝{BABA_LONG[t]}・ダ{BABA_LONG[dd]}で選び直し: {desc}"
            args += (m or {}).get("mark_args", [])
            print(f"[{p}] {note}  丸など {' '.join((m or {}).get('mark_args', [])) or 'なし'}", flush=True)
        out = ROOT / "scripts" / "daily" / f"zu_jra_{ymd}_{p}.html"
        cmd = [sys.executable, str(ROOT / "scripts" / "jra_tenkai_zu.py"), "--day", a.date, "--place", p,
               "--pace-data", str(allp), "--out", str(out)] + args + shlex.split(a.extra)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            sys.stderr.write(r.stderr[-3000:])
            print(f"[{p}] 失敗", file=sys.stderr)
            continue
        print("→", out.relative_to(ROOT))
        if a.png:
            shoot(out, pngdir, p)
            print("→", (pngdir / f"{p}_*R.png").relative_to(ROOT))


if __name__ == "__main__":
    main()
