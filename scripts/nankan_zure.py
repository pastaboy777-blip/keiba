#!/usr/bin/env python3
"""**その馬自身の標準形からの逸脱を拾う。**＝ 調教パターンを変えた馬。

    python3 scripts/nankan_zure.py --place 大井 --date 20260904
    python3 scripts/nankan_zure.py --place 大井 --date 20260904 --race 11 --only

キャッシュだけを読む（取りに行かないので巡回と同時に回せる）。

── なぜ「逸脱」なのか ────────────────────────────────

**水準は市場が知っている。変化は馬柱に出ない。**

  この馬が速い／遅いは、走った結果として着順に現れ、人気に織り込まれる。
  **定数だから予測に使えない。**実際、他馬と比べる材料はこの開催で全滅した:

    矢印 ↗            1〜3人気 52%(n=23) ＜ → 61%(n=156)
    時計ゼロ           7人気以下 5%(n=20) ≒ 時計あり 6%(n=314)
    追い切りの脚色      7人気以下 どれも4〜5%
    * (11日以上空き)   60/60、30/30、10 vs 6
    ☆の時計の速さ(z)   4〜6人気 速い1/3 24% ＜ 中 40%   ← 逆
    併走で先着         7人気以下 先着7.7% ≒ 併走なし5.5%
        （大井 2026-08-31〜09-04・692頭）

  対して**「いつもと違うことをした」は厩舎の意図の変化**で、着順にも人気にも
  まだ出ていない。**定数ではなく変化なので、予測に使える。**

  ⚠️ n の問題も逆さになる:
        横断  穴馬を集める → この開催の人気薄好走は**19頭** → 詰む
        逸脱  走を集める   → 1頭が5戦していれば**5観測**で標準形が作れる

── 何を「標準形」とみなすか ───────────────────────────

過去N走の調教から、その馬のいつもの型を作る:

    course   いつも追う場所      大井外 / 小林坂 / 船橋外 …
    n_works  いつもの本数
    asiiro   いつもの追い切りの脚色  馬なり / 強め / 一杯
    time     いつもの☆の時計      同じコース・同じ欄での平均とばらつき
    awase    いつも併走するか
    notime   いつも「中間軽め」で済ませる馬か

── 何を「逸脱」とみなすか ───────────────────────────

    ★コース変更   いつも大井外 → 今回は坂路。**場所を変えたのは強い意図**
    ★強くなった   いつも馬なり → 今回は強め／一杯
      緩めた       逆
    ★時計が外れた  自分の分布から |z| ≧ 1.0（過去3本以上あるときだけ）
    ★併走を始めた  いつも単走 → 今回は併走（逆も）
    ★追い出した   いつも中間軽め → 今回は時計を出した（逆も）
      本数が変わった 中央値から±2本以上

  ⚠️⚠️ **向きは決めつけない。**「強くした＝良い」とは限らない。仕上げ切れて
     いないから追ったのかもしれない。**まず逸脱を数え、向きは結果で確かめる。**

── ⚠️ これは仮説であって、検証していない ────────────────────

**このリポジトリで調教が効くと確認できたことは一度もない。**
唯一検証済みのパドック材料は馬体重の増減だけ（人気薄374頭：−8〜−3kg で
11.8%、+9kg以上で3.6%、全体7.8%）。

正しい使い方は `paddock.py` と同じ:

    発走前に「この馬は逸脱している」と記録する → 結果と突き合わせる → 積む

**当たった馬だけ覚えていると必ず過大評価になる。**逸脱した馬は全部記録する。

⚠️ 恒久ルール5：目の前の開催の出走馬を見るだけ。過去開催の一括検証はしない。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics as stt
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import keibabook as kb                # noqa: E402
from nankeiba.scraping import rakuten as rk                  # noqa: E402

CACHE = "data/cache/keibabook"
#: `/chihou/` から引ける場。ここに無い場（JRA・門別ほか）は標準形に入らない。
NANKAN = ("大井", "川崎", "船橋", "浦和")
PREF = ("3F(2F)", "1F(1F)", "半哩(3F)", "5F(4F)")
DEFAULT_N = 5
#: 標準形を作るのに最低これだけの過去走が要る。**1走では「いつも」は言えない。**
MIN_PAST = 2
#: 脚色の強さの順。⚠️ **これはこのリポジトリの解釈**で、競馬ブックの定義ではない。
HARD = {"馬なり": 0, "稍強め": 1, "強め": 2, "仕掛け": 2, "末強め": 2,
        "追って": 3, "末一杯": 3, "稍一杯": 3, "一杯": 4, "直一杯": 4}
#: 時計がこれだけ自分の分布から外れたら逸脱とみなす（標準偏差の倍数）。
Z = 1.0


def norm(s: str | None) -> str:
    return re.sub(r"[\s　・]", "", s or "")


def cached(path: str) -> str | None:
    """**キャッシュにある時だけ読む。**取りに行かない。"""
    p = os.path.join(CACHE, re.sub(r"[^0-9A-Za-z]+", "_", path).strip("_") + ".html")
    return open(p, encoding="utf-8").read() if os.path.exists(p) else None


def index(ymd: str, place: str) -> dict:
    h = cached(f"/chihou/nittei/{ymd}")
    if not h:
        return {}
    by: dict[str, list[str]] = {}
    for i in sorted(set(re.findall(r"/chihou/syutuba/(\d+)", h))):
        by.setdefault(i[:8], []).append(i)
    for v in by.values():
        s = cached(f"/chihou/syutuba/{v[0]}")
        if not s or (kb.parse_race_header(s) or {}).get("place") != place:
            continue
        out = {}
        for rid in v:
            t = cached(f"/chihou/cyokyo/1/0/{rid}")
            if t:
                for x in kb.parse_cyokyo(t):
                    out[norm(x["name"])] = x
        return out
    return {}


def star(h: dict | None) -> dict | None:
    """その開催の追い切り（☆）1本。⚠️ 中間の時計は乗り込みと混ざるので使わない。"""
    if not h:
        return None
    for w in reversed(h.get("works") or []):
        if w.get("oikiri"):
            return w
    return None


def pick(w: dict) -> tuple[str, float] | None:
    for k in PREF:
        v = w["times"].get(k)
        if v is not None:
            return k, v
    return None


def profile(past: list[dict]) -> dict:
    """過去走からその馬の標準形を作る。"""
    stars = [x["star"] for x in past if x["star"]]
    courses = [w.get("course") for w in stars if w.get("course")]
    asi = [w.get("asiiro") for w in stars if w.get("asiiro")]
    mode_c = Counter(courses).most_common(1)[0][0] if courses else None
    # 時計は**同じコース・同じ欄でしか比べない**
    secs = []
    col = None
    for w in stars:
        p = pick(w)
        if p and w.get("course") == mode_c:
            if col is None:
                col = p[0]
            if p[0] == col:
                secs.append(p[1])
    return {
        "n": len(past),
        "course": mode_c,
        "course_share": (courses.count(mode_c) / len(courses)) if courses else 0.0,
        "asiiro": Counter(asi).most_common(1)[0][0] if asi else None,
        "col": col,
        "mu": stt.mean(secs) if len(secs) >= 3 else None,
        "sd": (stt.pstdev(secs) if len(secs) >= 3 and stt.pstdev(secs) > 0 else None),
        "secs": secs,
        "works_med": (stt.median([x["nworks"] for x in past]) if past else None),
        "awase_rate": (sum(1 for x in past if x["awase"]) / len(past)) if past else 0.0,
        "notime_rate": (sum(1 for x in past if x["notime"]) / len(past)) if past else 0.0,
    }


def deviations(pr: dict, now: dict, works: list, awase: bool, notime: bool) -> list:
    """標準形からの逸脱を並べる。**向きは決めつけず、事実だけ書く。**"""
    out = []
    c = now.get("course") if now else None
    if pr["course"] and c and c != pr["course"] and pr["course_share"] >= 0.6:
        out.append(f"★コース変更  いつも{pr['course']}"
                   f"（{pr['course_share']*100:.0f}%）→ 今回{c}")
    a = now.get("asiiro") if now else None
    if pr["asiiro"] and a and a != pr["asiiro"]:
        d = HARD.get(a, 9) - HARD.get(pr["asiiro"], 9)
        if d > 0:
            out.append(f"★強くした  いつも{pr['asiiro']} → 今回{a}")
        elif d < 0:
            out.append(f"　緩めた    いつも{pr['asiiro']} → 今回{a}")
    p = pick(now) if now else None
    if p and pr["mu"] is not None and pr["sd"] and c == pr["course"] \
            and p[0] == pr["col"]:
        z = (p[1] - pr["mu"]) / pr["sd"]
        if abs(z) >= Z:
            w = "速い" if z < 0 else "遅い"
            out.append(f"★時計が外れた  いつも{pr['mu']:.1f}±{pr['sd']:.1f} → "
                       f"今回{p[1]:.1f}（{z:+.1f}σ {w}）")
    if pr["n"] >= 3:
        if awase and pr["awase_rate"] <= 0.2:
            out.append(f"★併走を始めた  過去{pr['awase_rate']*100:.0f}% → 今回あり")
        if not awase and pr["awase_rate"] >= 0.8:
            out.append(f"　併走をやめた  過去{pr['awase_rate']*100:.0f}% → 今回なし")
        if not notime and pr["notime_rate"] >= 0.6:
            out.append("★追い出した  いつも中間軽め → 今回は時計を出した")
        if notime and pr["notime_rate"] <= 0.2:
            out.append("　止めた  いつも追う馬 → 今回は中間軽め")
    if pr["works_med"] and abs(len(works) - pr["works_med"]) >= 2:
        out.append(f"　本数  いつも{pr['works_med']:.0f}本 → 今回{len(works)}本")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="標準形からの逸脱＝調教を変えた馬")
    ap.add_argument("--place", default="大井")
    ap.add_argument("--date", required=True, help="YYYYMMDD")
    ap.add_argument("--race", type=int)
    ap.add_argument("-n", type=int, default=DEFAULT_N)
    ap.add_argument("--only", action="store_true", help="逸脱がある馬だけ")
    ap.add_argument("--jsonl", help="この名前で JSONL にも書く")
    args = ap.parse_args()

    rc = rk.KeibaRakuten()
    idx: dict[tuple, dict] = {}
    out = open(args.jsonl, "w", encoding="utf-8") if args.jsonl else None
    hit = weak = 0
    for rno in ([args.race] if args.race else range(1, 13)):
        try:
            rid = rc.find_race_id(args.date, args.place, rno)
            card = rk.parse_card(rc.get(f"/race_card/list/RACEID/{rid}"))
        except Exception:                                   # noqa: BLE001
            continue
        cur = index(args.date, args.place)
        printed = False
        for e in card.get("entries") or []:
            nm = norm(e.get("name"))
            past = []
            for h in reversed((e.get("history") or [])[:args.n]):
                d = (h.date or "").replace("-", "")
                if not d or h.place not in NANKAN:
                    continue
                if (d, h.place) not in idx:
                    idx[(d, h.place)] = index(d, h.place)
                got = idx[(d, h.place)].get(nm)
                if not got:
                    continue
                ws = got.get("works") or []
                past.append({"date": h.date, "finish": h.finish_pos,
                             "star": star(got), "nworks": len(ws),
                             "awase": bool(got.get("awase")),
                             "notime": bool(ws) and all(x.get("no_time_note")
                                                        for x in ws)})
            now_h = cur.get(nm)
            now = star(now_h)
            if len(past) < MIN_PAST or now is None:
                weak += 1
                if args.only:
                    continue
                desc = [f"判定不能（標準形を作る過去走が{len(past)}走）"]
            else:
                ws = (now_h.get("works") or [])
                desc = deviations(profile(past), now, ws,
                                  bool(now_h.get("awase")),
                                  bool(ws) and all(x.get("no_time_note") for x in ws))
                if not desc:
                    desc = ["標準形どおり"]
                elif any(x.startswith("★") for x in desc):
                    hit += 1
                if args.only and not any(x.startswith("★") for x in desc):
                    continue
            if not printed:
                printed = True
                print(f"\n{'='*96}\n {args.place} {args.date}  {rno}R\n{'='*96}")
            pop = f"{e['popularity']}人気" if e.get("popularity") else ""
            print(f"\n {e.get('umaban') or '':>2} {e.get('name',''):<14}{pop:>7}")
            for x in past:
                s = x["star"]
                p = pick(s) if s else None
                print(f"      {'○' if (x['finish'] or 99) <= 3 else '×'} {x['date']} "
                      f"{str(x['finish'] or '-'):>2}着  {(s.get('course') if s else ''):<7}"
                      f"{(s.get('baba') if s else ''):<3}"
                      f"{(f'{p[0]} {p[1]:.1f}' if p else '時計なし'):<16}"
                      f"{(s.get('asiiro') if s else ''):<5}"
                      f"{'併走' if x['awase'] else ''}")
            if now:
                p = pick(now)
                print(f"      ★ 今回        {(now.get('course') or ''):<7}"
                      f"{(now.get('baba') or ''):<3}"
                      f"{(f'{p[0]} {p[1]:.1f}' if p else '時計なし'):<16}"
                      f"{now.get('asiiro') or ''}")
            for line in desc:
                print(f"        {line}")
            if out:
                out.write(json.dumps({"date": args.date, "place": args.place,
                                      "race": rno, "umaban": e.get("umaban"),
                                      "name": e.get("name"),
                                      "pop": e.get("popularity"),
                                      "dev": desc}, ensure_ascii=False) + "\n")
    if out:
        out.close()
    print(f"\n■ ★逸脱あり {hit}頭 ／ 標準形を作れない {weak}頭", file=sys.stderr)
    print("⚠️ **向きは決めつけていない。**強くした＝良いとは限らない。"
          "発走前に記録して、結果と突き合わせて積むこと。", file=sys.stderr)


if __name__ == "__main__":
    main()
