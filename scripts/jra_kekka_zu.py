"""結果の4コーナー隊列図(実際の通過順から起こす)。事前の展開図(jra_tenkai_zu.py)と並べて答え合わせする。

    python3 scripts/jra_kekka_zu.py --race-id 202508040411 --data data/jra/races.jsonl --out out.html

横 = 4角の通過順(右が前)、縦 = 横並びの組の中の位置(上が内)。括弧は横並び・中は内→外(netkeiba/JRA の表記)。
単独で通過した馬は横の位置が記録されないので、いちばん上(内)に置いて「横不明」の印を付ける。
1〜3着に着順の札、人気を添える。
"""

from __future__ import annotations

import argparse
import html as H
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ana"))

import jra_tenkai_zu as Z  # noqa: E402
from horse_svg import HORSE, CHEV  # noqa: E402
from nankeiba.scraping.db_race import pace_of  # noqa: E402


def parse_corner(s: str):
    """通過順 → [(馬番, 前からの組番号, 組の中の内からの順, 組の頭数)]"""
    out, gi = [], 0
    for m in re.finditer(r"\(([^)]*)\)|(\d+)", s.replace("*", "")):
        g = [int(x) for x in re.findall(r"\d+", m.group(1))] if m.group(1) is not None else [int(m.group(2))]
        for i, u in enumerate(g):
            out.append((u, gi, i, len(g)))
        gi += 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--race-id", required=True)
    ap.add_argument("--data", default="data/jra/races.jsonl")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    d = next(json.loads(l) for l in open(a.data, encoding="utf-8") if json.loads(l)["race_id"] == a.race_id)
    res = {x["umaban"]: x for x in d["result"]}
    cells = parse_corner(d["corners"].get("4") or d["corners"].get("3") or "")
    ng = max(c[1] for c in cells) + 1
    WID, PAD = Z.WID, Z.PAD
    hh = []
    for u, gi, li, gs in cells:
        x = WID - PAD - gi * (WID - 2 * PAD) / max(1, ng - 1)
        r = res.get(u, {})
        fin = r.get("finish_pos")
        wc = Z.WAKU.get(r.get("waku") or Z.waku_of(u, d["field_size"]), ("#15110d", "#f2f2f4"))
        col = "#ffcf5a" if fin and fin <= 3 else "#d8c7ae"
        tag = ('<span class="hit">%d着 %s人気</span>' % (fin, r.get("popularity") or "-")) if fin and fin <= 3 else ""
        side = "" if gs >= 2 else '<span class="sin">横不明</span>'
        hh.append('<div class="horse" style="left:%dpx;top:%dpx"><div class="fig">%s%s</div>'
                  '<div class="lab"><span class="n" style="background:%s;color:%s;border-color:%s">%d</span>'
                  '<span class="nm">%s</span></div>%s%s</div>'
                  % (int(x), 14 + li * Z.LANE, HORSE.format(c=col), CHEV.format(c=col), wc[0], wc[1],
                     "#00000055" if (r.get("waku") or Z.waku_of(u, d["field_size"])) == 1 else "rgba(255,255,255,.45)", u, H.escape((r.get("horse_name") or "")[:4]), tag, side))
    nl = max(c[2] for c in cells) + 1
    p = pace_of(d["lap"], d["distance"])
    body = ('<div class="race"><div class="rh"><span class="rn">結果</span><span class="rd">%s %s　<b>%s%dm</b> ／ %d頭 ／ %s</span>'
            '<span class="pace p-%s"><b>実際</b> 前%.1f 後%.1f</span></div>'
            '<div class="stg">4コーナー(実際)</div><div class="board"><div class="ylab"><span>内（組の中）</span><span>外</span></div>'
            '<div class="track" style="height:%dpx"><div class="goal"></div>%s</div></div>'
            '<div class="xlab"><span>後方</span><span>中団</span><span>前　→　ゴール</span></div>'
            '<div class="kenkai"><div class="kt">通過順</div><p>4角 %s</p><p>ラップ %s</p></div></div>'
            % (d["date"], H.escape(d.get("name") or ""), d["surface"], d["distance"], d["field_size"], d.get("baba") or "",
               "slow" if p["diff"] > 0.2 else ("high" if p["diff"] < -1.5 else "mid"), p["front3"], p["last3"],
               nl * Z.LANE + 24, "\n".join(hh), H.escape(d["corners"].get("4") or ""), "-".join(map(str, d["lap"]))))
    if d.get("surface") == "芝":
        body = body.replace('class="track"', 'class="track turf"')
    css = (Z.ROOT / "scripts" / "ana" / "zu.css").read_text(encoding="utf-8")
    Path(a.out).write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>結果の隊列</title>'
                           '<style>%s%s</style></head><body>%s</body></html>' % (css, Z.CSS_EXTRA, body), encoding="utf-8")
    print("→", a.out)


if __name__ == "__main__":
    main()
