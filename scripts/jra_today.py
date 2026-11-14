"""当日の終わった鞍の結果を JRA公式から取り込み、展開図を作り直す(後半の鞍に「今日ここまでの傾向」が入る)。

    python3 scripts/jra_today.py --date 2026-11-15
    python3 scripts/jra_today.py --date 2026-11-15 --place 福島 --extra '--circle 7:11 --circle2 7:15,10'

1) 結果ページ(月 → 開催日 → レース)から、その日の終わった鞍を data/jra/races.jsonl に足す(3秒間隔、済みは飛ばす)
2) races.jsonl + 出馬表(data/jra/shutuba_YYYYMMDD.jsonl)で scripts/daily/zu_jra_YYYYMMDD_<場>.html を作り直す
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
from nankeiba.scraping.jra_official import links, month_checksums, parse_race, race_id_of  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", help="作り直す場(省略で出馬表にある全場)")
    ap.add_argument("--extra", default="", help="jra_tenkai_zu.py に渡す追加の引数(丸・時計の基準など)")
    a = ap.parse_args()
    ymd = a.date.replace("-", "")
    data = ROOT / "data" / "jra" / "races.jsonl"
    have = {json.loads(l)["race_id"] for l in open(data)}
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
    print(f"新しく取り込んだ鞍 {new}")
    sb = ROOT / "data" / "jra" / f"shutuba_{ymd}.jsonl"
    allp = ROOT / "data" / "jra" / f"all_{ymd}.jsonl"
    allp.write_text(open(data, encoding="utf-8").read() + open(sb, encoding="utf-8").read(), encoding="utf-8")
    places = [a.place] if a.place else sorted({json.loads(l)["place"] for l in open(sb, encoding="utf-8")})
    for p in places:
        out = ROOT / "scripts" / "daily" / f"zu_jra_{ymd}_{p}.html"
        cmd = [sys.executable, str(ROOT / "scripts" / "jra_tenkai_zu.py"), "--day", a.date, "--place", p,
               "--pace-data", str(allp), "--out", str(out)] + shlex.split(a.extra)
        subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL)
        print("→", out)


if __name__ == "__main__":
    main()
