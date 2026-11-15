"""当日の朝、馬場状態を入れるだけで全場・全レースの展開図(HTML)と画像(PNG)を作り直す。

    python3 scripts/jra_morning.py --date 2026-11-15 --baba 京都=稍,東京=良,福島=稍
    python3 scripts/jra_morning.py --date 2026-11-15 --baba 京都=重 --baba-dirt 京都=不 --refresh-shutuba
    python3 scripts/jra_morning.py --date 2026-11-15 --baba 福島=稍 --config scripts/daily/marks_20261115.json

引数
  --date            YYYY-MM-DD(必須)
  --baba            場ごとの芝の馬場 "京都=稍,東京=良"(良/稍/重/不。稍重・不良と書いてもよい)。書かない場は良
  --baba-dirt       同じ書式でダートの馬場(書かない場は芝と同じ)
  --refresh-shutuba 出馬表を取り直す(scripts/jra_shutuba.py)。当日は馬体重などが入る
  --config          手で決めた丸など(省略時 scripts/daily/marks_YYYYMMDD.json があれば読む)
                    {"福島": {"circle": "7:11", "circle2": "7:15,10", "hide_pace": "7", "circle_each": false},
                     "split": [{"place": "京都", "race": 11, "yaya": "10,5,6", "omo": "10,5,9",
                                "yaya_note": "…", "omo_note": "…"}]}
  --place           この場だけ作る(カンマで複数)
  --no-png          画像を作らない

動き
  1) data/jra/all_YYYYMMDD.jsonl = 出馬表(先頭。行の馬場を --baba/--baba-dirt で埋める) + races.jsonl
  2) 場ごとに時計の基準: 指定の馬場と同じ馬場だった、8日以内の同じ場の開催日
     芝 → --base-day / --base-baba、ダート → --base-day-dirt / --base-baba-dirt(芝ダ別々)
     (足りない距離は jra_tenkai_zu.py が通常の推定に戻す)
  3) scripts/daily/zu_jra_YYYYMMDD_<場>.html
  4) 1鞍ずつのPNG → data/zu_png/YYYYMMDD/<場>_<R>R.png
  5) config の split の鞍: 稍重版・重版を1鞍ずつ作り(赤丸を1頭ずつ)、左右2分割の
     data/zu_png/YYYYMMDD/split_<場><R>.png
     (途中の連結データは場×馬場で1つずつ作って使い回し、終わったら消す)
  6) 作ったファイルの一覧と、各場の時計の基準を表示
  6b) 丸の候補の一覧(鞍ごとに1行)を画面に出し、data/jra/kouho_YYYYMMDD.txt にも残す
     (jra_tenkai_zu.py --dump-kouho が場ごとに data/jra/kouho_YYYYMMDD_<場>.json を書く。表示だけで予想は変えない)
  7) 使った設定(場ごとの芝ダの馬場・jra_tenkai_zu.py へ渡した引数)を data/jra/morning_YYYYMMDD.json に残す
     → 昼に scripts/jra_today.py が読んで、同じ馬場・時計の基準・丸で作り直す

jra_tenkai_zu.py は呼ぶだけ(--dump-kouho で候補の JSON を書かせる)。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JRA = ROOT / "data" / "jra"
ZU = ROOT / "scripts" / "jra_tenkai_zu.py"
SHOT = ROOT / "scripts" / "shot_races.js"
FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
BABA_NORM = {"良": "良", "稍": "稍", "稍重": "稍", "重": "重", "不": "不", "不良": "不"}
BABA_LONG = {"良": "良", "稍": "稍重", "重": "重", "不": "不良"}
MARU = "⓪①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def parse_baba(s: str) -> dict[str, str]:
    out = {}
    for part in filter(None, (s or "").replace("、", ",").split(",")):
        k, _, v = part.partition("=")
        v = v.strip()
        if v not in BABA_NORM:
            sys.exit(f"馬場が読めません: {part}(良/稍/重/不)")
        out[k.strip()] = BABA_NORM[v]
    return out


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def base_days(races: list[dict], place: str, surface: str, baba: str, date: str) -> list[str]:
    """指定の馬場だった、8日以内(当日より前)の同じ場・同じ芝ダの開催日。"""
    d0 = dt.date.fromisoformat(date)
    days = set()
    for d in races:
        if (d.get("place") == place and d.get("surface") == surface and d.get("baba") == baba
                and d.get("lap") and d["date"] < date
                and (d0 - dt.date.fromisoformat(d["date"])).days <= 8):
            days.add(d["date"])
    return sorted(days)


def write_all(path: Path, races_text: str, shutuba: list[dict], turf: dict, dirt: dict, default=None):
    """出馬表 + races.jsonl(出馬表の行を先に置く)。出馬表の行の baba を埋める。default=(場, 馬場) でその場を上書き。
    jra_tenkai_zu.py の from_data は同じ race_id の最初の行をその鞍として使うので、結果を取り込み済みの鞍でも
    予想は出馬表の行で組まれる(結果の行は後ろにあり、当日の前の鞍の傾向・ペースのずれには使われる)。"""
    with path.open("w", encoding="utf-8") as fo:
        for d in shutuba:
            d = dict(d)
            p = d["place"]
            if default and p == default[0]:
                d["baba"] = default[1]
            else:
                d["baba"] = dirt.get(p, turf.get(p, "良")) if d.get("surface") == "ダ" else turf.get(p, "良")
            fo.write(json.dumps(d, ensure_ascii=False) + "\n")
        fo.write(races_text)
        if races_text and not races_text.endswith("\n"):
            fo.write("\n")


def base_args(races, place, babas_by_surface: dict[str, str], date) -> tuple[list[str], str]:
    """芝は --base-day/--base-baba、ダートは --base-day-dirt/--base-baba-dirt。芝ダは混ぜない。
    該当日が無いときは日を絞らない(芝は --base-day を付けない、ダートは --base-day-dirt "" で芝の日を引き継がない)。"""
    args, desc = [], []
    for surf, b in babas_by_surface.items():
        ds = base_days(races, place, surf, b, date)
        sfx = "-dirt" if surf == "ダ" else ""
        args += [f"--base-baba{sfx}", b]
        if ds or sfx:
            args += [f"--base-day{sfx}", ",".join(ds)]
        desc.append(f"{surf}{BABA_LONG[b]}: " + ("・".join(x[5:] for x in ds) if ds else "該当日なし(通常の推定)"))
    return args, " / ".join(desc)


def run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stdout[-2000:] + r.stderr[-4000:])
        sys.exit(f"失敗: {' '.join(cmd[:6])} …")
    return r.stdout


def shoot(html: Path, outdir: Path, prefix: str) -> None:
    run(["node", str(SHOT), str(html.resolve()), str(outdir.resolve()), prefix])


def split_png(left: Path, right: Path, out: Path, lt: str, ln: str, rt: str, rn: str) -> None:
    from PIL import Image, ImageDraw, ImageFont
    a, b = Image.open(left).convert("RGB"), Image.open(right).convert("RGB")
    top, gap = 70, 30
    W, Hh = a.width + gap + b.width, top + max(a.height, b.height)
    img = Image.new("RGB", (W, Hh), (16, 16, 20))
    img.paste(a, (0, top))
    img.paste(b, (a.width + gap, top))
    dr = ImageDraw.Draw(img)
    big, small = ImageFont.truetype(FONT, 30), ImageFont.truetype(FONT, 20)
    for x0, title, note, col in ((20, lt, ln, "#4fa8ff"), (a.width + gap + 20, rt, rn, "#ff6b4a")):
        dr.text((x0, 20), title, font=big, fill=col)
        tw = dr.textlength(title, font=big)
        dr.text((x0 + tw + 30, 26), note, font=small, fill=(230, 230, 235))
    img.save(out)


def maru(nums: str) -> str:
    return "".join(MARU[int(x)] if 0 < int(x) < len(MARU) else f"({x})" for x in nums.split(",") if x.strip())


def kouho_path(ymd: str, place: str) -> Path:
    return JRA / f"kouho_{ymd}_{place}.json"


def _m(us) -> str:
    return "".join(MARU[u] if 0 < u < len(MARU) else f"({u})" for u in us) or "なし"


def kouho_line(k: dict) -> str:
    """「京都11R 芝2200 重: 位置(1-2・5-7) ⑤⑦ ／ 終い候補 ⑫⑮ ／ 押上 なし ／ ハナ候補 ⑧⑩⑥ ／ 札 道悪○⑥ 道悪×③」"""
    head = f"{k['place']}{k['race']}R {k['surface']}{k['dist']} {BABA_LONG.get(k.get('baba') or '', k.get('baba') or '-')}"
    pb = "・".join(k.get("pos_buckets") or [])
    parts = ["位置 (過去走なし)" if not k.get("n_known", 1) else f"位置({pb}) {_m(k['pos'])}" if pb else "位置 (表なし)",
             f"終い候補 {_m(k['shimai'])}", f"押上 {_m(k['oshiage'])}", f"ハナ候補 {_m(k['hana'])}"]
    if k.get("kb_day"):
        parts.append("札 " + (" ".join(t + _m(v) for t, v in k["kb"].items()) or "なし"))
    return head + ": " + " ／ ".join(parts)


def kouho_report(date: str) -> Path | None:
    """その日の data/jra/kouho_YYYYMMDD_<場>.json を全部まとめて画面に出し、kouho_YYYYMMDD.txt に保存。"""
    ymd = date.replace("-", "")
    files = sorted(JRA.glob(f"kouho_{ymd}_*.json"))
    if not files:
        return None
    lines = []
    for f in files:
        ks = json.loads(f.read_text(encoding="utf-8"))
        lines += [kouho_line(k) for k in sorted(ks, key=lambda k: int(k["race"]))]
        lines.append("")
    out = JRA / f"kouho_{ymd}.txt"
    head = (f"丸の候補 {date}(位置=予想4角の順位がそのコースで1着の多い2区分に入る馬 / "
            "終い・押上=図の札 / ハナ=ハナ専用モデル上位3頭 / 札=厩舎の話のうち今日の馬場に関わるもの)")
    out.write_text(head + "\n" + "\n".join(lines), encoding="utf-8")
    print("\n== 丸の候補 ==")
    print("\n".join("  " + l if l else "" for l in lines).rstrip())
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", required=True)
    ap.add_argument("--baba", default="", help='場ごとの芝の馬場 "京都=稍,東京=良"(書かない場は良)')
    ap.add_argument("--baba-dirt", default="", help="ダートの馬場(書かない場は芝と同じ)")
    ap.add_argument("--refresh-shutuba", action="store_true")
    ap.add_argument("--config")
    ap.add_argument("--place", help="この場だけ(カンマで複数)")
    ap.add_argument("--no-png", action="store_true")
    a = ap.parse_args()
    ymd = a.date.replace("-", "")
    turf, dirt = parse_baba(a.baba), parse_baba(a.baba_dirt)

    sb = JRA / f"shutuba_{ymd}.jsonl"
    if a.refresh_shutuba or not sb.exists():
        print("出馬表を取ります …", flush=True)
        subprocess.run([sys.executable, str(ROOT / "scripts" / "jra_shutuba.py"), "--date", a.date], check=True)
    shutuba = read_jsonl(sb)
    races_text = (JRA / "races.jsonl").read_text(encoding="utf-8")
    races = [json.loads(l) for l in races_text.splitlines() if l.strip()]

    cfg_path = Path(a.config) if a.config else ROOT / "scripts" / "daily" / f"marks_{ymd}.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    if cfg:
        print("丸などの指定:", cfg_path)

    places = sorted({d["place"] for d in shutuba})
    if a.place:
        places = [p for p in places if p in a.place.split(",")]
    for p in list(turf) + list(dirt):
        if p not in {d["place"] for d in shutuba}:
            print(f"注意: {p} は出馬表にありません", file=sys.stderr)

    # 1) 連結データ
    allp = JRA / f"all_{ymd}.jsonl"
    write_all(allp, races_text, shutuba, turf, dirt)
    made: list[Path] = [allp]
    pngdir = ROOT / "data" / "zu_png" / ymd
    pngdir.mkdir(parents=True, exist_ok=True)

    report = []
    setting = {}
    for p in places:
        t = turf.get(p, "良")
        d = dirt.get(p, t)
        bb, desc = base_args(races, p, {"芝": t, "ダ": d}, a.date)
        report.append((p, f"芝{BABA_LONG[t]}・ダ{BABA_LONG[d]}", desc))
        c = cfg.get(p, {})
        extra = []
        for k in ("circle", "circle2", "hide_pace"):
            if c.get(k):
                extra += ["--" + k.replace("_", "-"), str(c[k])]
        if c.get("circle_each"):
            extra.append("--circle-each")
        if c.get("base_time"):
            extra += ["--base-time", c["base_time"]]
        if c.get("no_trend"):
            extra.append("--no-trend")
        setting[p] = {"turf": t, "dirt": d, "base_args": bb, "mark_args": extra, "zu_args": bb + extra}
        out = ROOT / "scripts" / "daily" / f"zu_jra_{ymd}_{p}.html"
        print(f"[{p}] 展開図 …", flush=True)
        print(run([sys.executable, str(ZU), "--day", a.date, "--place", p, "--pace-data", str(allp),
                   "--out", str(out), "--dump-kouho", str(kouho_path(ymd, p))] + bb + extra).rstrip())
        made.append(out)
        if not a.no_png:
            shoot(out, pngdir, p)
            made += sorted(pngdir.glob(f"{p}_*R.png"), key=lambda x: int(x.stem.split("_")[-1][:-1]))

    # 5) 稍重/重の2分割
    # 連結データは「場×馬場」で中身が決まる(その場の出馬表の行の馬場だけを書き換える)。
    # 鞍ごとに作らず、場ごと・馬場ごとに1つだけ作って同じ場の鞍で使い回し、使い終わったらすぐ消す。
    work = pngdir / "split_work"
    jobs: dict[str, list[tuple[dict, dict]]] = {}
    for s in cfg.get("split", []):
        p, r = s["place"], int(s["race"])
        if a.place and p not in places:
            continue
        me = next((x for x in shutuba if x["place"] == p and int(x["race_id"][-2:]) == r), None)
        if not me:
            print(f"注意: {p}{r}R が出馬表にありません", file=sys.stderr)
            continue
        jobs.setdefault(p, []).append((s, me))
    for p, items in jobs.items():
        work.mkdir(exist_ok=True)
        pics: dict[tuple[int, str], Path] = {}
        for key, b in (("yaya", "稍"), ("omo", "重")):
            data = work / f"all_{ymd}_{p}_{key}.jsonl"
            write_all(data, races_text, shutuba, turf, dirt, default=(p, b))
            try:
                for s, me in items:
                    r = int(s["race"])
                    bb, desc = base_args(races, p, {me["surface"]: b}, a.date)
                    html = work / f"{p}{r}_{key}.html"
                    run([sys.executable, str(ZU), "--from-data", "--race-id", me["race_id"], "--date", a.date,
                         "--race-no", str(r), "--place", p, "--pace-data", str(data), "--out", str(html),
                         "--circle", f"{r}:{s[key]}", "--circle-each"] + bb)
                    if not a.no_png:
                        shoot(html, work, f"{p}{key}")
                        pics[(r, key)] = work / f"{p}{key}_{r}R.png"
                    report.append((f"{p}{r}R({BABA_LONG[b]}版)", BABA_LONG[b], desc))
            finally:
                data.unlink(missing_ok=True)
        if not a.no_png:
            for s, _ in items:
                r = int(s["race"])
                out = pngdir / f"split_{p}{r}.png"
                split_png(pics[(r, "yaya")], pics[(r, "omo")], out,
                          "稍重なら", s.get("yaya_note") or maru(s["yaya"]),
                          "重なら", s.get("omo_note") or maru(s["omo"]))
                made.append(out)
    if work.exists():
        for f in work.glob("*.jsonl"):   # 前の版が残した連結データ
            f.unlink()

    # 7) 朝の設定を残す(--place で一部だけ作ったときは、前に残した他の場の設定を引き継ぐ)
    mp = JRA / f"morning_{ymd}.json"
    old = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
    keep = old.get("places", {}) if old.get("date") == a.date else {}
    keep.update(setting)
    mp.write_text(json.dumps({"date": a.date, "places": keep}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    made.append(mp)

    kp = kouho_report(a.date)
    if kp:
        made.append(kp)

    print("\n== 作ったファイル ==")
    for f in made:
        print(" ", f.relative_to(ROOT) if f.is_relative_to(ROOT) else f)
    print("\n== 時計の基準 ==")
    for p, b, desc in report:
        print(f"  {p}  {b}  基準日 {desc}")


if __name__ == "__main__":
    main()
